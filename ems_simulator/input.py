"""Immutable caller-supplied input for one 24-hour EMS simulation."""

from dataclasses import dataclass
from datetime import timedelta

from simulator import SimulationStepIdentity
from simulator.validation import (
    require_fraction,
    require_non_negative_number,
    require_number,
    require_positive_number,
)

HOURS_PER_DAY = 24
SECONDS_PER_HOUR = 3600.0


def _require_curve(
    value: object,
    field_name: str,
    *,
    non_negative: bool,
) -> tuple[float, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    if len(value) != HOURS_PER_DAY:
        raise ValueError(f"{field_name} must contain exactly 24 values")
    validator = require_non_negative_number if non_negative else require_number
    for item in value:
        validator(item, f"{field_name} item")
    return value


@dataclass(frozen=True, slots=True)
class BatteryParameters:
    """Caller-supplied physical parameters for the demo battery.

    Capacity is a finite positive raw value in kWh. Charge and discharge power
    limits are finite non-negative raw values in kW. Efficiencies are raw
    unitless fractions in ``(0, 1]``. ``reserve_soc`` is a raw unitless
    fraction in ``[0, 1]``.

    This artifact stores facts only. It does not update SOC, enforce limits, or
    execute battery physics.
    """

    capacity_kwh: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    charge_efficiency: float
    discharge_efficiency: float
    reserve_soc: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capacity_kwh",
            require_positive_number(self.capacity_kwh, "capacity_kwh"),
        )
        object.__setattr__(
            self,
            "max_charge_power_kw",
            require_non_negative_number(
                self.max_charge_power_kw,
                "max_charge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "max_discharge_power_kw",
            require_non_negative_number(
                self.max_discharge_power_kw,
                "max_discharge_power_kw",
            ),
        )
        for field_name in ("charge_efficiency", "discharge_efficiency"):
            value = require_fraction(getattr(self, field_name), field_name)
            if value == 0:
                raise ValueError(f"{field_name} must be greater than 0")
            object.__setattr__(self, field_name, value)
        object.__setattr__(
            self,
            "reserve_soc",
            require_fraction(self.reserve_soc, "reserve_soc"),
        )


@dataclass(frozen=True, slots=True)
class DailySimulationScenarioInput:
    """Preserve the explicit facts for one 24-hour hourly simulation.

    Every curve contains exactly 24 raw hourly values in caller order. PV and
    load values are finite non-negative kW. Tariff values are finite signed CNY
    per kWh, allowing an explicitly supplied negative price. ``initial_soc``
    is a raw unitless fraction in ``[0, 1]``.

    ``step_identities`` must contain 24 exact, caller-supplied hourly step
    identities with sequences 0 through 23 and consecutive timezone-aware
    timestamps. The input preserves all tuple and parameter identities; it
    never sorts, normalizes, copies, or constructs execution steps.
    """

    step_identities: tuple[SimulationStepIdentity, ...]
    pv_power_curve_kw: tuple[float, ...]
    load_power_curve_kw: tuple[float, ...]
    tariff_curve_cny_per_kwh: tuple[float, ...]
    battery_parameters: BatteryParameters
    initial_soc: float

    def __post_init__(self) -> None:
        self._validate_step_identities()
        _require_curve(
            self.pv_power_curve_kw,
            "pv_power_curve_kw",
            non_negative=True,
        )
        _require_curve(
            self.load_power_curve_kw,
            "load_power_curve_kw",
            non_negative=True,
        )
        _require_curve(
            self.tariff_curve_cny_per_kwh,
            "tariff_curve_cny_per_kwh",
            non_negative=False,
        )
        if not isinstance(self.battery_parameters, BatteryParameters):
            raise TypeError("battery_parameters must be BatteryParameters")
        object.__setattr__(
            self,
            "initial_soc",
            require_fraction(self.initial_soc, "initial_soc"),
        )

    def _validate_step_identities(self) -> None:
        if not isinstance(self.step_identities, tuple):
            raise TypeError("step_identities must be a tuple")
        if len(self.step_identities) != HOURS_PER_DAY:
            raise ValueError("step_identities must contain exactly 24 values")

        previous_timestamp = None
        for expected_sequence, step_identity in enumerate(self.step_identities):
            if not isinstance(step_identity, SimulationStepIdentity):
                raise TypeError(
                    "step_identities must contain only SimulationStepIdentity objects"
                )
            if step_identity.sequence != expected_sequence:
                raise ValueError("step identity sequences must be exactly 0 through 23")
            if step_identity.duration_seconds != SECONDS_PER_HOUR:
                raise ValueError("every step duration must be exactly 3600 seconds")
            if step_identity.timestamp is None:
                raise ValueError("every step timestamp must be explicitly supplied")
            if (
                previous_timestamp is not None
                and step_identity.timestamp != previous_timestamp + timedelta(hours=1)
            ):
                raise ValueError("step timestamps must be consecutive hourly values")
            previous_timestamp = step_identity.timestamp
