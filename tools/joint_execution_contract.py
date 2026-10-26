"""Facts and fixed configuration for the independent UTC-day experiment."""

from dataclasses import dataclass, field, fields
from datetime import UTC, datetime, timedelta, timezone
from itertools import pairwise
from math import isfinite
from typing import cast

from ems_simulator.demo import create_demo_scenario
from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from tools.dynamic_constraint_probe import Case, FactSegment, battery
from tools.joint_strategy_adapter import MPC, STRATEGIES

DAY_SECONDS = 86400
START_UTC = datetime(2026, 1, 1, tzinfo=UTC)
POWER_TOL = 1e-9
SOC_TOL = 1e-9
TIME_TOL = 1e-7
ENERGY_TOL = 2e-9
DAY_ENERGY_TOL = 2.4e-8


def finite_number(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number")
    number = cast(float, value)
    if not isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return float(number)


@dataclass(frozen=True, slots=True)
class JointExecutionContext:
    duration_seconds: int = DAY_SECONDS
    pv_ac_max_kw: float = 6.0
    battery_parameters: BatteryParameters = field(default_factory=battery)
    strategy: str = "joint_reserve_v1"

    def __post_init__(self) -> None:
        if (
            type(self.duration_seconds) is not int
            or self.duration_seconds != DAY_SECONDS
        ):
            raise ValueError("daily context must cover exactly 86400 seconds")
        if finite_number(self.pv_ac_max_kw, "PV rating") != 6.0:
            raise ValueError("daily PV AC rating is explicitly 6 kW")
        if self.battery_parameters != battery():
            raise ValueError("daily battery must retain the accepted fixed parameters")
        if self.strategy not in (*STRATEGIES, MPC):
            raise ValueError("unknown strategy identifier")


@dataclass(frozen=True, slots=True)
class DailyEvent:
    at_s: int
    pv_kw: float | None = None
    load_kw: float | None = None
    grid_charge_allowed: bool | None = None
    zero_export: bool | None = None
    reserve_target_soc: float | None = None

    def __post_init__(self) -> None:
        if type(self.at_s) is not int or not 0 <= self.at_s < DAY_SECONDS:
            raise ValueError("event time must be an integer in [0,86400)")
        supplied = 0
        for item in fields(self):
            if item.name == "at_s":
                continue
            value = getattr(self, item.name)
            if value is None:
                continue
            supplied += 1
            if item.name in {"grid_charge_allowed", "zero_export"}:
                if type(value) is not bool:
                    raise ValueError(f"{item.name} must be boolean")
            else:
                number = finite_number(value, item.name)
                if number < 0:
                    raise ValueError(f"{item.name} cannot be negative")
                if item.name == "pv_kw" and number > 6:
                    raise ValueError("available PV exceeds the daily AC rating")
                if item.name == "reserve_target_soc" and not 0.2 <= number <= 1:
                    raise ValueError("reserve target must be in [0.2,1]")
        if not supplied:
            raise ValueError("empty event")


def validate_daily_case(case: Case, context: JointExecutionContext) -> None:
    if not isinstance(case, Case) or not isinstance(case.segments, tuple):
        raise TypeError("case must contain an immutable tuple of facts")
    soc = finite_number(case.initial_soc, "initial SOC")
    if not 0.2 <= soc <= 1:
        raise ValueError("initial SOC must be within hard boundaries")
    expected = 0
    for fact in case.segments:
        if not isinstance(fact, FactSegment):
            raise TypeError("invalid fact")
        if (
            type(fact.start) is not int
            or type(fact.end) is not int
            or fact.start != expected
            or fact.end <= fact.start
        ):
            raise ValueError(
                "facts must be ordered contiguous integer-second intervals"
            )
        for key in ("load_kw", "pv_kw"):
            if finite_number(getattr(fact, key), key) < 0:
                raise ValueError(f"negative {key}")
        if fact.pv_kw > context.pv_ac_max_kw:
            raise ValueError("available PV exceeds explicit AC rating")
        if (
            type(fact.grid_charge_allowed) is not bool
            or type(fact.zero_export) is not bool
        ):
            raise ValueError("permission and Zero Export must be boolean")
        if not 0.2 <= finite_number(fact.reserve_target_soc, "target") <= 1:
            raise ValueError("soft target must be in [0.2,1]")
        expected = fact.end
    if expected != context.duration_seconds:
        raise ValueError("facts must cover the complete UTC day")


def daily_case(
    source: DailySimulationScenarioInput | None = None,
    events: tuple[DailyEvent, ...] = (),
) -> Case:
    """Overlay explicit events; power overrides end at the next hourly input."""
    source = create_demo_scenario() if source is None else source
    if not isinstance(source, DailySimulationScenarioInput):
        raise TypeError("source must be the immutable daily scenario contract")
    context = JointExecutionContext(battery_parameters=source.battery_parameters)
    for hour, identity in enumerate(source.step_identities):
        stamp = identity.timestamp
        if stamp is None or not isinstance(stamp.tzinfo, timezone) or stamp.fold:
            raise ValueError(
                "only unambiguous UTC/fixed-offset timestamps are supported"
            )
        if stamp.astimezone(UTC) != START_UTC + timedelta(hours=hour):
            raise ValueError("input must identify the original UTC day exactly")
    if not isinstance(events, tuple):
        raise TypeError("events must be a tuple")
    updates: dict[int, dict[str, float | bool]] = {}
    previous = -1
    for event in events:
        if not isinstance(event, DailyEvent) or event.at_s < previous:
            raise ValueError("events must be ordered DailyEvent values")
        previous = event.at_s
        same_time = updates.setdefault(event.at_s, {})
        for item in fields(event):
            if item.name == "at_s":
                continue
            value = getattr(event, item.name)
            if value is not None:
                if item.name in same_time:
                    raise ValueError("duplicate same-time field assignment")
                same_time[item.name] = value
    times = sorted(set(range(0, DAY_SECONDS, 3600)) | set(updates) | {DAY_SECONDS})
    permission, zero, target = False, True, 0.2
    pv, load = 0.0, 0.0
    facts: list[FactSegment] = []
    for start, end in pairwise(times):
        if start % 3600 == 0:
            pv = source.pv_power_curve_kw[start // 3600]
            load = source.load_power_curve_kw[start // 3600]
        change = updates.get(start, {})
        pv = float(change.get("pv_kw", pv))
        load = float(change.get("load_kw", load))
        permission = bool(change.get("grid_charge_allowed", permission))
        zero = bool(change.get("zero_export", zero))
        target = float(change.get("reserve_target_soc", target))
        facts.append(FactSegment(start, end, load, pv, permission, zero, target))
    result = Case("original_utc_daily", source.initial_soc, tuple(facts))
    validate_daily_case(result, context)
    return result
