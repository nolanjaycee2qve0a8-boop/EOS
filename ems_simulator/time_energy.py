"""Small, deterministic time and energy experiment independent of the daily runner.

All times are elapsed *simulation* seconds. A caller supplies changes of power
and request as explicit intervals. Cadences never sample or schedule commands.
"""

from dataclasses import dataclass
from math import ulp

from ems_simulator.input import BatteryParameters
from simulator.validation import (
    require_fraction,
    require_non_negative_number,
    require_number,
    require_positive_number,
)

SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True, slots=True)
class SimulationCadences:
    """Independent periods; only physical_step_seconds partitions physics."""

    physical_step_seconds: float
    decision_seconds: float
    forecast_seconds: float
    record_seconds: float
    display_seconds: float

    def __post_init__(self) -> None:
        for name in (
            "physical_step_seconds",
            "decision_seconds",
            "forecast_seconds",
            "record_seconds",
            "display_seconds",
        ):
            object.__setattr__(
                self, name, require_positive_number(getattr(self, name), name)
            )


@dataclass(frozen=True, slots=True)
class PowerInterval:
    """Caller-known constant powers during [start_seconds, end_seconds)."""

    start_seconds: float
    end_seconds: float
    load_power_kw: float
    pv_power_kw: float
    requested_battery_power_kw: float

    def __post_init__(self) -> None:
        start = require_non_negative_number(self.start_seconds, "start_seconds")
        end = require_positive_number(self.end_seconds, "end_seconds")
        if end <= start:
            raise ValueError("interval end must follow its start")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)
        for name in ("load_power_kw", "pv_power_kw"):
            object.__setattr__(
                self, name, require_non_negative_number(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "requested_battery_power_kw",
            require_number(
                self.requested_battery_power_kw, "requested_battery_power_kw"
            ),
        )


@dataclass(frozen=True, slots=True)
class TimeEnergyInput:
    cadences: SimulationCadences
    intervals: tuple[PowerInterval, ...]
    battery_parameters: BatteryParameters
    initial_soc: float

    def __post_init__(self) -> None:
        if not isinstance(self.cadences, SimulationCadences):
            raise TypeError("cadences must be SimulationCadences")
        if not isinstance(self.intervals, tuple) or not self.intervals:
            raise TypeError("intervals must be a nonempty tuple")
        if not isinstance(self.battery_parameters, BatteryParameters):
            raise TypeError("battery_parameters must be BatteryParameters")
        object.__setattr__(
            self, "initial_soc", require_fraction(self.initial_soc, "initial_soc")
        )
        expected_start = 0.0
        for interval in self.intervals:
            if not isinstance(interval, PowerInterval):
                raise TypeError("intervals must contain PowerInterval objects")
            if interval.start_seconds != expected_start:
                raise ValueError(
                    "intervals must be contiguous and ordered in simulation time"
                )
            expected_start = interval.end_seconds


@dataclass(frozen=True, slots=True)
class EnergySlice:
    """One interval with constant *delivered* power, ending at an event."""

    start_seconds: float
    end_seconds: float
    requested_battery_power_kw: float
    actual_battery_power_kw: float
    grid_power_kw: float
    soc_before: float
    soc_after: float


@dataclass(frozen=True, slots=True)
class TimeEnergyResult:
    source_input: TimeEnergyInput
    slices: tuple[EnergySlice, ...]
    load_energy_kwh: float
    pv_energy_kwh: float
    battery_delivered_energy_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    final_soc: float


def simulate_time_energy(source_input: TimeEnergyInput) -> TimeEnergyResult:
    """Evaluate explicit intervals once; retain no meter or runtime state."""
    if not isinstance(source_input, TimeEnergyInput):
        raise TypeError("source_input must be TimeEnergyInput")

    parameters = source_input.battery_parameters
    slices: list[EnergySlice] = []
    soc = source_input.initial_soc
    load_energy = pv_energy = battery_energy = import_energy = export_energy = 0.0

    for interval in source_input.intervals:
        cursor = interval.start_seconds
        while cursor < interval.end_seconds:
            physical_end = min(
                cursor + source_input.cadences.physical_step_seconds,
                interval.end_seconds,
            )
            if physical_end <= cursor:
                raise ValueError("physical step cannot advance simulation time")
            requested = interval.requested_battery_power_kw
            limited_power = (
                min(requested, parameters.max_charge_power_kw)
                if requested > 0
                else -min(-requested, parameters.max_discharge_power_kw)
            )
            if limited_power > 0:
                available_kwh = (1.0 - soc) * parameters.capacity_kwh
                seconds_to_boundary = (
                    available_kwh
                    * SECONDS_PER_HOUR
                    / (limited_power * parameters.charge_efficiency)
                )
            elif limited_power < 0:
                available_kwh = (
                    max(0.0, soc - parameters.reserve_soc) * parameters.capacity_kwh
                )
                seconds_to_boundary = (
                    available_kwh
                    * parameters.discharge_efficiency
                    * SECONDS_PER_HOUR
                    / -limited_power
                )
            else:
                seconds_to_boundary = physical_end - cursor

            # Absolute simulation timestamps cannot represent a positive duration
            # smaller than their ULP. Do not invent delivered energy for such a
            # remainder; keep its SOC unchanged and deliver zero for this step.
            boundary_time = cursor + seconds_to_boundary
            actual = (
                limited_power
                if seconds_to_boundary > 0 and boundary_time > cursor
                else 0.0
            )
            delivery_end = min(physical_end, boundary_time) if actual else physical_end
            if delivery_end <= cursor:
                raise ValueError("energy slice cannot advance simulation time")

            duration_hours = (delivery_end - cursor) / SECONDS_PER_HOUR
            if actual > 0:
                next_soc = min(
                    1.0,
                    soc
                    + actual
                    * duration_hours
                    * parameters.charge_efficiency
                    / parameters.capacity_kwh,
                )
            elif actual < 0:
                next_soc = max(
                    parameters.reserve_soc,
                    soc
                    + actual
                    * duration_hours
                    / (parameters.discharge_efficiency * parameters.capacity_kwh),
                )
            else:
                next_soc = soc

            # If the boundary is inside this step (or indistinguishable from its
            # end at the timestamp's one-ULP resolution), account for the *actual*
            # slice duration before setting the exact boundary SOC. This prevents
            # a sub-ULP SOC residue from requesting a non-advancing second slice.
            time_resolution_seconds = max(ulp(cursor), ulp(physical_end))
            reaches_boundary = bool(actual) and seconds_to_boundary <= (
                physical_end - cursor + time_resolution_seconds
            )
            if reaches_boundary:
                battery_factor = (
                    parameters.charge_efficiency
                    if actual > 0
                    else 1.0 / parameters.discharge_efficiency
                )
                accounted_kwh = abs(actual) * duration_hours * battery_factor
                time_quantum_kwh = (
                    abs(actual)
                    * time_resolution_seconds
                    / SECONDS_PER_HOUR
                    * battery_factor
                )
                rounding_kwh = ulp(available_kwh) + ulp(accounted_kwh)
                if abs(accounted_kwh - available_kwh) > (
                    time_quantum_kwh + rounding_kwh
                ):
                    raise ValueError("SOC boundary energy exceeds time resolution")
                next_soc = 1.0 if actual > 0 else parameters.reserve_soc

            grid_power = interval.load_power_kw + actual - interval.pv_power_kw
            slices.append(
                EnergySlice(
                    cursor, delivery_end, requested, actual, grid_power, soc, next_soc
                )
            )
            load_energy += interval.load_power_kw * duration_hours
            pv_energy += interval.pv_power_kw * duration_hours
            battery_energy += actual * duration_hours
            import_energy += max(grid_power, 0.0) * duration_hours
            export_energy += max(-grid_power, 0.0) * duration_hours
            soc = next_soc
            cursor = delivery_end

    return TimeEnergyResult(
        source_input,
        tuple(slices),
        load_energy,
        pv_energy,
        battery_energy,
        import_energy,
        export_energy,
        soc,
    )
