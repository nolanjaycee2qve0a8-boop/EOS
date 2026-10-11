"""Analytical checks for explicit simulation time and delivered energy."""

import pytest

from ems_simulator.input import BatteryParameters
from ems_simulator.time_energy import (
    PowerInterval,
    SimulationCadences,
    TimeEnergyInput,
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
):
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
