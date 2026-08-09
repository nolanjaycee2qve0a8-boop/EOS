"""Tests for the deterministic 24-hour EMS simulation runner."""

from collections.abc import Callable
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta

import pytest

from ems_simulator import (
    BatteryParameters,
    DailySimulationResult,
    DailySimulationRunner,
    DailySimulationScenarioInput,
)
from simulator import (
    SimulationModelBindingCollection,
    SimulationStepIdentity,
    SimulationStepInput,
    SimulationStepResult,
    SingleStepSimulationExecutor,
)


def make_source_input(
    *,
    pv_curve: tuple[float, ...] | None = None,
    load_curve: tuple[float, ...] | None = None,
    initial_soc: float = 0.5,
) -> DailySimulationScenarioInput:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    steps = tuple(
        SimulationStepIdentity(
            hour,
            3600.0,
            start + timedelta(hours=hour),
        )
        for hour in range(24)
    )
    return DailySimulationScenarioInput(
        step_identities=steps,
        pv_power_curve_kw=pv_curve or (0.0,) * 6 + (5.0,) * 12 + (0.0,) * 6,
        load_power_curve_kw=load_curve or (2.0,) * 24,
        tariff_curve_cny_per_kwh=(0.5,) * 24,
        battery_parameters=BatteryParameters(
            capacity_kwh=10.0,
            max_charge_power_kw=3.0,
            max_discharge_power_kw=3.0,
            charge_efficiency=0.95,
            discharge_efficiency=0.9,
            reserve_soc=0.2,
        ),
        initial_soc=initial_soc,
    )


def observed_values(result: DailySimulationResult) -> tuple[tuple[float, ...], ...]:
    return tuple(
        (
            trace.state.pv_result.actual_power_kw,
            trace.state.load_result.actual_power_kw,
            trace.state.battery_result.actual_power_kw,
            trace.state.grid_result.actual_grid_power_kw,
            trace.state.battery_result.next_state.soc,
        )
        for trace in result.traces
    )


def test_runner_executes_24_steps_once_in_caller_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_input = make_source_input()
    calls: list[SimulationStepInput] = []
    original_execute: Callable[
        [SimulationStepInput, SimulationModelBindingCollection],
        SimulationStepResult,
    ] = SingleStepSimulationExecutor.execute

    def recording_execute(
        simulation_input: SimulationStepInput,
        bindings: SimulationModelBindingCollection,
    ) -> SimulationStepResult:
        calls.append(simulation_input)
        return original_execute(simulation_input, bindings)

    monkeypatch.setattr(
        SingleStepSimulationExecutor,
        "execute",
        staticmethod(recording_execute),
    )

    result = DailySimulationRunner.run(source_input)

    assert result.source_input is source_input
    assert len(result.scenario.steps) == 24
    assert len(result.traces) == 24
    assert calls == list(result.scenario.steps)
    assert [step.step_identity.sequence for step in calls] == list(range(24))
    assert all(
        step.step_identity is source_input.step_identities[index]
        for index, step in enumerate(result.scenario.steps)
    )


def test_runner_preserves_trace_and_battery_progression_identity() -> None:
    result = DailySimulationRunner.run(make_source_input())

    assert len(result.progressions) == 23
    for index, trace in enumerate(result.traces):
        assert trace.simulation_input is result.scenario.steps[index]
        assert trace.step_result.simulation_input is trace.simulation_input
        assert trace.step_result.state is trace.state
        if index:
            previous = result.traces[index - 1]
            progression = result.progressions[index - 1]
            assert progression.previous_trace is previous
            assert progression.previous_result is previous.step_result
            assert progression.next_input is trace.simulation_input
            assert (
                trace.simulation_input.battery_input.source_state
                is previous.state.battery_result.next_state
            )


def test_runner_integrates_pv_load_battery_and_grid_results() -> None:
    pv_curve = (0.0, 5.0) + (0.0,) * 22
    load_curve = (2.0,) * 24
    result = DailySimulationRunner.run(
        make_source_input(pv_curve=pv_curve, load_curve=load_curve)
    )

    discharge_trace = result.traces[0]
    charge_trace = result.traces[1]

    assert discharge_trace.state.pv_result.actual_power_kw == 0.0
    assert discharge_trace.state.load_result.actual_power_kw == 2.0
    assert discharge_trace.state.battery_result.actual_power_kw == -2.0
    assert discharge_trace.state.grid_result.actual_grid_power_kw == 0.0

    assert charge_trace.state.pv_result.actual_power_kw == 5.0
    assert charge_trace.state.load_result.actual_power_kw == 2.0
    assert charge_trace.state.battery_result.actual_power_kw == 3.0
    assert charge_trace.state.grid_result.actual_grid_power_kw == 0.0


def test_runner_stops_discharging_at_reserve_soc() -> None:
    result = DailySimulationRunner.run(
        make_source_input(
            pv_curve=(0.0,) * 24,
            load_curve=(2.0,) * 24,
            initial_soc=0.2,
        )
    )

    assert all(
        trace.state.battery_result.actual_power_kw == 0.0 for trace in result.traces
    )
    assert all(
        trace.state.battery_result.next_state.soc == 0.2 for trace in result.traces
    )
    assert all(
        trace.state.grid_result.actual_grid_power_kw == 2.0 for trace in result.traces
    )


def test_runner_is_deterministic_for_the_same_source_input() -> None:
    source_input = make_source_input()

    first = DailySimulationRunner.run(source_input)
    second = DailySimulationRunner.run(source_input)

    assert first is not second
    assert first.source_input is source_input
    assert second.source_input is source_input
    assert observed_values(first) == observed_values(second)


def test_result_is_frozen_and_slotted() -> None:
    result = DailySimulationRunner.run(make_source_input())

    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        result.source_input = make_source_input()  # type: ignore[misc]


def test_runner_rejects_invalid_input() -> None:
    with pytest.raises(TypeError, match="DailySimulationScenarioInput"):
        DailySimulationRunner.run(object())  # type: ignore[arg-type]
