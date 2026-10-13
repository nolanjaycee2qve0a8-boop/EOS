"""Analytical checks for explicit simulation time and delivered energy."""

from math import inf, nextafter, ulp

import pytest

from ems_simulator.input import BatteryParameters
from ems_simulator.time_energy import (
    PowerInterval,
    SimulationCadences,
    TimeEnergyInput,
    TimeEnergyResult,
    simulate_time_energy,
)


def parameters(*, capacity: float = 10.0, reserve: float = 0.0) -> BatteryParameters:
    return BatteryParameters(capacity, 10.0, 10.0, 1.0, 1.0, reserve)


def cadences(
    *, physical: float = 3600.0, decision: float = 900.0, record: float = 60.0
) -> SimulationCadences:
    return SimulationCadences(physical, decision, 1800.0, record, 5.0)


def evaluate(
    intervals: tuple[PowerInterval, ...],
    *,
    physical: float = 3600.0,
    decision: float = 900.0,
    record: float = 60.0,
    battery: BatteryParameters | None = None,
    soc: float = 0.5,
) -> TimeEnergyResult:
    return simulate_time_energy(
        TimeEnergyInput(
            cadences(physical=physical, decision=decision, record=record),
            intervals,
            battery or parameters(),
            soc,
        )
    )


def test_one_kw_for_one_hour_is_one_kwh_under_different_physical_steps() -> None:
    interval = (PowerInterval(0.0, 3600.0, 1.0, 0.0, 0.0),)

    for step in (15.0, 60.0, 900.0, 3600.0):
        result = evaluate(interval, physical=step)
        assert result.load_energy_kwh == pytest.approx(1.0)
        assert result.grid_import_energy_kwh == pytest.approx(1.0)
        assert result.grid_export_energy_kwh == 0.0
        assert result.final_soc == 0.5


def test_record_and_decision_periods_do_not_change_explicit_physics() -> None:
    intervals = (
        PowerInterval(0.0, 600.0, 1.0, 0.0, 0.0),
        PowerInterval(600.0, 3600.0, 1.0, 2.0, 0.0),
    )

    first = evaluate(intervals, physical=60.0, decision=300.0, record=5.0)
    second = evaluate(intervals, physical=900.0, decision=1800.0, record=3600.0)

    for result in (first, second):
        assert result.load_energy_kwh == pytest.approx(1.0)
        assert result.pv_energy_kwh == pytest.approx(5 / 3)
        assert result.grid_import_energy_kwh == pytest.approx(1 / 6)
        assert result.grid_export_energy_kwh == pytest.approx(5 / 6)


def test_soc_upper_event_splits_delivery_and_uses_actual_power() -> None:
    result = evaluate(
        (PowerInterval(0.0, 3600.0, 0.0, 0.0, 2.0),),
        battery=parameters(capacity=1.0),
        soc=0.5,
    )

    assert [(item.start_seconds, item.end_seconds) for item in result.slices] == [
        (0.0, 900.0),
        (900.0, 3600.0),
    ]
    assert [item.actual_battery_power_kw for item in result.slices] == [2.0, 0.0]
    assert [item.requested_battery_power_kw for item in result.slices] == [2.0, 2.0]
    assert result.battery_delivered_energy_kwh == pytest.approx(0.5)
    assert result.grid_import_energy_kwh == pytest.approx(0.5)
    assert result.final_soc == 1.0


@pytest.mark.parametrize("physical_step_seconds", [15.0, 60.0, 3600.0])
def test_soc_boundary_energy_is_stable_across_physical_steps(
    physical_step_seconds: float,
) -> None:
    result = evaluate(
        (PowerInterval(0.0, 3600.0, 0.0, 0.0, 2.0),),
        physical=physical_step_seconds,
        battery=parameters(capacity=1.0),
        soc=0.5,
    )

    assert result.battery_delivered_energy_kwh == pytest.approx(0.5)
    assert result.grid_import_energy_kwh == pytest.approx(0.5)
    assert result.final_soc == pytest.approx(1.0)
    assert all(
        slice_.grid_power_kw == slice_.actual_battery_power_kw
        for slice_ in result.slices
    )


def test_soc_lower_event_stops_delivery_at_reserve() -> None:
    result = evaluate(
        (PowerInterval(0.0, 3600.0, 2.0, 0.0, -2.0),),
        battery=parameters(capacity=1.0, reserve=0.2),
        soc=0.7,
    )

    assert [item.actual_battery_power_kw for item in result.slices] == [-2.0, 0.0]
    assert result.battery_delivered_energy_kwh == pytest.approx(-0.5)
    assert result.grid_import_energy_kwh == pytest.approx(1.5)
    assert result.final_soc == 0.2


def test_idle_then_discharge_reaches_lower_soc_without_zero_duration_slice() -> None:
    battery = BatteryParameters(1.0, 10.0, 10.0, 0.8, 0.9, 0.0)
    result = evaluate(
        (
            PowerInterval(0.0, 900.0, 0.0, 0.0, 0.0),
            PowerInterval(900.0, 1800.0, 0.0, 0.0, -5.0),
        ),
        battery=battery,
        soc=1.0,
    )

    assert [(item.start_seconds, item.end_seconds) for item in result.slices] == [
        (0.0, 900.0),
        (900.0, 1548.0),
        (1548.0, 1800.0),
    ]
    assert [item.actual_battery_power_kw for item in result.slices] == [
        0.0,
        -5.0,
        0.0,
    ]
    assert result.battery_delivered_energy_kwh == pytest.approx(-0.9)
    assert result.grid_export_energy_kwh == pytest.approx(0.9)
    assert result.final_soc == 0.0
    for item in result.slices:
        elapsed_hours = (item.end_seconds - item.start_seconds) / 3600.0
        if item.actual_battery_power_kw < 0:
            expected_soc = item.soc_before + (
                item.actual_battery_power_kw
                * elapsed_hours
                / (battery.discharge_efficiency * battery.capacity_kwh)
            )
        else:
            expected_soc = item.soc_before
        assert item.soc_after == pytest.approx(expected_soc, abs=1e-12)


@pytest.mark.parametrize("direction", ["charge", "discharge"])
@pytest.mark.parametrize("boundary_offset", [-1, 0, 1])
def test_soc_boundary_at_interval_edge_and_one_ulp_either_side_conserves_energy(
    direction: str, boundary_offset: int
) -> None:
    charge = direction == "charge"
    battery = BatteryParameters(1.0, 10.0, 10.0, 0.8, 0.9, 0.0)
    power = 5.0 if charge else -5.0
    initial_soc = 0.0 if charge else 1.0
    exact_event = 1800.0 if charge else 1548.0
    event = (
        nextafter(exact_event, -inf)
        if boundary_offset < 0
        else nextafter(exact_event, inf)
        if boundary_offset > 0
        else exact_event
    )
    end = 2100.0 if charge else 1800.0
    result = evaluate(
        (
            PowerInterval(0.0, 900.0, 0.0, 0.0, 0.0),
            PowerInterval(900.0, event, 0.0, 0.0, power),
            PowerInterval(event, end, 0.0, 0.0, power),
        ),
        battery=battery,
        soc=initial_soc,
    )

    assert result.final_soc == pytest.approx(1.0 if charge else 0.0, abs=1e-15)
    assert result.battery_delivered_energy_kwh == pytest.approx(
        1.25 if charge else -0.9, abs=1e-15
    )
    previous_end = 0.0
    for item in result.slices:
        assert item.start_seconds == previous_end
        assert item.end_seconds > item.start_seconds
        hours = (item.end_seconds - item.start_seconds) / 3600.0
        factor = (
            battery.charge_efficiency
            if item.actual_battery_power_kw > 0
            else 1.0 / battery.discharge_efficiency
            if item.actual_battery_power_kw < 0
            else 0.0
        )
        accounted_kwh = item.actual_battery_power_kw * hours * factor
        soc_energy_kwh = (item.soc_after - item.soc_before) * battery.capacity_kwh
        time_quantum_kwh = (
            abs(item.actual_battery_power_kw)
            * max(ulp(item.start_seconds), ulp(item.end_seconds))
            / 3600.0
            * factor
        )
        rounding_kwh = ulp(abs(accounted_kwh)) + ulp(abs(soc_energy_kwh))
        assert abs(accounted_kwh - soc_energy_kwh) <= (time_quantum_kwh + rounding_kwh)
        previous_end = item.end_seconds
    assert previous_end == end


@pytest.mark.parametrize(
    ("initial_soc", "power"),
    [(nextafter(1.0, 0.0), 5.0), (nextafter(0.0, 1.0), -5.0)],
)
def test_near_boundary_remainder_is_limited_to_one_time_quantum(
    initial_soc: float, power: float
) -> None:
    result = evaluate(
        (
            PowerInterval(0.0, 900.0, 0.0, 0.0, 0.0),
            PowerInterval(900.0, 1800.0, 0.0, 0.0, power),
        ),
        battery=BatteryParameters(1.0, 10.0, 10.0, 0.8, 0.9, 0.0),
        soc=initial_soc,
    )

    time_quantum_seconds = max(ulp(900.0), ulp(1800.0))
    assert abs(result.battery_delivered_energy_kwh) <= (
        abs(power) * time_quantum_seconds / 3600.0
    )
    if result.slices[-1].actual_battery_power_kw == 0.0:
        assert result.slices[-1].soc_after == result.slices[-1].soc_before
    else:
        assert result.slices[-1].end_seconds - result.slices[-1].start_seconds <= (
            time_quantum_seconds
        )


def test_repeated_evaluation_and_wall_clock_pause_do_not_accumulate_twice() -> None:
    intervals = (
        PowerInterval(0.0, 1800.0, 1.0, 0.0, 0.0),
        PowerInterval(1800.0, 3600.0, 1.0, 0.0, 0.0),
    )
    source = TimeEnergyInput(cadences(), intervals, parameters(), 0.5)

    first = simulate_time_energy(source)
    second = simulate_time_energy(source)
    uninterrupted = evaluate((PowerInterval(0.0, 3600.0, 1.0, 0.0, 0.0),))

    assert first is not second
    assert first.grid_import_energy_kwh == second.grid_import_energy_kwh == 1.0
    assert first.source_input is source
    assert second.source_input is source
    assert first.grid_import_energy_kwh == uninterrupted.grid_import_energy_kwh


def test_efficiency_and_power_limit_apply_once_to_delivered_energy() -> None:
    battery = BatteryParameters(2.0, 1.0, 1.0, 0.8, 0.9, 0.0)
    result = evaluate(
        (PowerInterval(0.0, 3600.0, 0.0, 0.0, 2.0),),
        battery=battery,
        soc=0.2,
    )

    assert result.slices[0].requested_battery_power_kw == 2.0
    assert result.slices[0].actual_battery_power_kw == 1.0
    assert result.battery_delivered_energy_kwh == pytest.approx(1.0)
    assert result.grid_import_energy_kwh == pytest.approx(1.0)
    assert result.final_soc == pytest.approx(0.6)


def test_duplicate_or_missing_simulation_intervals_fail_closed() -> None:
    first = PowerInterval(0.0, 900.0, 1.0, 0.0, 0.0)
    duplicate = PowerInterval(0.0, 900.0, 1.0, 0.0, 0.0)
    gap = PowerInterval(1800.0, 3600.0, 1.0, 0.0, 0.0)

    with pytest.raises(ValueError, match="contiguous"):
        TimeEnergyInput(cadences(), (first, duplicate), parameters(), 0.5)
    with pytest.raises(ValueError, match="contiguous"):
        TimeEnergyInput(cadences(), (first, gap), parameters(), 0.5)
