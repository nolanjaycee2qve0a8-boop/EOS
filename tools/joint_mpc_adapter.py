"""Offline bridge from the existing one-cycle MPC to the joint executor.

Forecasts are caller-owned, issued artifacts. This module neither produces a
forecast nor executes a battery command; only the first MPC request is returned
to the accepted joint executor. EMSContext uses the last delivered observation,
not an undelivered scenario fact; its net load is a planning proxy, not grid
telemetry.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from math import isfinite

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from ems_simulator.mpc_demo import _runner
from ems_strategy import (
    EMSContext,
    EMSStrategyDescriptor,
    MPCConfiguration,
    MPCCycleInput,
    PhysicallyAwareMPCCycleInput,
)
from forecast import ForecastHorizon
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    OptimizationObjective,
    OptimizationObjectiveCollection,
)
from tools.joint_execution_contract import DAY_SECONDS, START_UTC
from tools.joint_strategy_adapter import MPC, StrategyInput

CONTROL_STEP = timedelta(hours=1)
HORIZON_STEPS = 4
MAX_FORECAST_AGE = CONTROL_STEP


def _utc(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise TypeError(f"{name} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{name} must have a valid UTC offset")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class IssuedMPCForecast:
    """One four-hour forecast available for one exact hourly decision.

    The half-open coverage is [decision_at, decision_at + 4 hours). A forecast
    generated more than one hour before its decision is stale. Missing or
    invalid input fails before the simulation starts; there is no actual-value
    fallback. Source honesty remains the caller's responsibility.
    """

    decision_at: datetime
    generated_at: datetime
    available_at: datetime
    coverage_start: datetime
    coverage_end: datetime
    horizon: ForecastHorizon

    def __post_init__(self) -> None:
        decision = _utc(self.decision_at, "decision_at")
        generated = _utc(self.generated_at, "generated_at")
        available = _utc(self.available_at, "available_at")
        start = _utc(self.coverage_start, "coverage_start")
        end = _utc(self.coverage_end, "coverage_end")
        if not generated <= available <= decision:
            raise ValueError("forecast was not available at its decision")
        if decision - generated > MAX_FORECAST_AGE:
            raise ValueError("forecast is stale")
        if start != decision or end != decision + HORIZON_STEPS * CONTROL_STEP:
            raise ValueError("forecast coverage does not match the decision")
        if not isinstance(self.horizon, ForecastHorizon):
            raise TypeError("horizon must be a ForecastHorizon")
        if len(self.horizon.points) != HORIZON_STEPS:
            raise ValueError("forecast must contain exactly four hourly points")
        for index, point in enumerate(self.horizon.points):
            if _utc(point.timestamp, "point timestamp") != start + index * CONTROL_STEP:
                raise ValueError("forecast point is outside its hourly coverage")
            if point.electricity_price_cny_per_kwh is None:
                raise ValueError("price-aware MPC requires each forecast price")


def _build_mpc_request(
    forecasts: tuple[IssuedMPCForecast, ...],
) -> Callable[[StrategyInput], float]:
    """Preflight all 24 issued forecasts, then build the MPC request callback.

    No forecast or future actuals are retrieved during execution. The joint
    executor retains all permission, curtailment, SOC and physical authority.
    """
    if not isinstance(forecasts, tuple) or len(forecasts) != DAY_SECONDS // 3600:
        raise ValueError("exactly 24 issued forecasts are required")
    by_hour: dict[int, IssuedMPCForecast] = {}
    for hour, forecast in enumerate(forecasts):
        if not isinstance(forecast, IssuedMPCForecast):
            raise TypeError("forecasts must contain IssuedMPCForecast values")
        if _utc(forecast.decision_at, "decision_at") != START_UTC + hour * CONTROL_STEP:
            raise ValueError("forecast schedule must match the UTC decision hours")
        by_hour[hour] = forecast

    # Reuse the existing physically-aware price MPC composition. Its old daily
    # runner is not called, and it receives no simulation scenario or ledger.
    cycle = _runner().mpc_cycle_boundary
    capability = CapabilityDescriptor("mpc", "Physically-aware price MPC.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((capability,)),
        AvailableCapabilityCollection((capability,)),
        (CapabilityMatch(capability, capability),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (capability,), ())
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("energy_cost", "Minimize imported energy cost."), active
    )
    configuration = MPCConfiguration(HORIZON_STEPS, 3600.0)
    objectives = OptimizationObjectiveCollection(
        (OptimizationObjective("energy_cost", "minimize"),)
    )
    descriptor = EMSStrategyDescriptor(MPC, "1.0")

    def request(facts: StrategyInput) -> float:
        if facts.at_s not in range(0, DAY_SECONDS, 3600):
            raise ValueError("MPC may run only at an hourly decision")
        # A measurement is sampled at observed_at_s, arrives no earlier than
        # available_at_s (the accepted check's effect time), and may be used
        # only at a later/equal decision. Missing, impossible, or older than
        # one full check+observation+execution cycle is an explicit idle
        # request. No case truth or forecast-as-actual fallback is allowed.
        sampled = facts.observed_at_s
        available = facts.available_at_s
        age_limit = facts.max_observation_age_s
        if (
            facts.fact is None
            or type(sampled) is not int
            or type(available) is not int
            or type(age_limit) is not int
            or sampled < 0
            or age_limit < 0
            or not sampled <= available <= facts.at_s
            or facts.at_s - sampled > age_limit
        ):
            return 0.0
        frame = by_hour[facts.at_s // 3600]
        now = START_UTC + timedelta(seconds=facts.at_s)
        if _utc(frame.available_at, "available_at") > now:
            raise ValueError("forecast is not yet available")
        current_price = frame.horizon.points[0].electricity_price_cny_per_kwh
        if current_price is None:
            raise ValueError("current forecast price is missing")
        battery = facts.battery
        context = EMSContext(
            DecisionContext(
                timestamp=now,
                soc=facts.soc,
                battery_power_limit_kw=max(
                    battery.max_charge_power_kw, battery.max_discharge_power_kw
                ),
                battery_energy_capacity_kwh=battery.capacity_kwh,
                pv_power_kw=facts.fact.pv_kw,
                load_power_kw=facts.fact.load_kw,
                grid_power_kw=facts.fact.load_kw - facts.fact.pv_kw,
                electricity_price_cny_per_kwh=current_price,
                reserve_soc=battery.reserve_soc,
                export_limit_kw=0.0 if facts.fact.zero_export else 9.0,
            ),
            composition,
            capability,
        )
        result = cycle.run_cycle(
            PhysicallyAwareMPCCycleInput(
                MPCCycleInput(
                    context, frame.horizon, configuration, objectives, descriptor
                ),
                BatteryOptimizationState(facts.soc),
                BatteryOptimizationModel(
                    battery.capacity_kwh,
                    battery.reserve_soc,
                    1.0,
                    battery.max_charge_power_kw,
                    battery.max_discharge_power_kw,
                    battery.charge_efficiency,
                    battery.discharge_efficiency,
                ),
            )
        )
        decision = result.decision
        if decision.intent.action == "charge":
            return decision.requested_power_kw
        if decision.intent.action == "discharge":
            return -decision.requested_power_kw
        if decision.intent.action == "idle":
            return 0.0
        raise ValueError("MPC returned an unknown action")

    return request


@dataclass(frozen=True, slots=True)
class IssuedMPCRequestStrategy:
    """MPC cannot be constructed from an arbitrary same-label callback.

    Construction always validates the complete issued-forecast schedule.
    This is a trusted offline strategy boundary, not a Python code sandbox.
    """

    forecasts: tuple[IssuedMPCForecast, ...]
    _request: Callable[[StrategyInput], float] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_request", _build_mpc_request(self.forecasts))

    @property
    def identifier(self) -> str:
        return MPC

    def evaluate(self, facts: StrategyInput) -> float:
        value = self._request(facts)
        if type(value) not in (int, float) or not isfinite(value):
            raise ValueError("strategy must return a finite numeric request")
        return float(value)


def mpc_strategy(
    forecasts: tuple[IssuedMPCForecast, ...],
) -> IssuedMPCRequestStrategy:
    """Expose existing MPC only after the constructor's forecast preflight."""
    return IssuedMPCRequestStrategy(forecasts)
