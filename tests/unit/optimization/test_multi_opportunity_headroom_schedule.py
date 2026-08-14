"""Tests for pure multi-opportunity PV headroom schedule evidence."""

import ast
from dataclasses import FrozenInstanceError, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationModel,
    DeterministicMultiOpportunityHeadroomScheduleCalculator,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunitySequenceCalculator,
    MultiOpportunityHeadroomSchedule,
    MultiOpportunityHeadroomScheduleBoundary,
    MultiOpportunityHeadroomScheduleEntry,
    MultiOpportunityHeadroomScheduleInput,
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
    PVOpportunitySequence,
    PVOpportunitySequenceBoundary,
    PVOpportunitySequenceEntry,
    PVOpportunitySequenceInput,
    PVOpportunityWindowConfiguration,
)


def _point(hour: int, pv: float, load: float) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 2, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
    )


def _model(
    *, capacity: float = 10.0, discharge_efficiency: float = 1.0
) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        capacity,
        0.2,
        1.0,
        10.0,
        10.0,
        1.0,
        discharge_efficiency,
    )


def _input(
    points: tuple[ForecastPoint, ...],
    *,
    gap: int = 1,
    model: BatteryOptimizationModel | None = None,
) -> MultiOpportunityHeadroomScheduleInput:
    return MultiOpportunityHeadroomScheduleInput(
        ForecastHorizon(points),
        model or _model(),
        3600.0,
        PVOpportunityWindowConfiguration(gap),
    )


def _calculator() -> DeterministicMultiOpportunityHeadroomScheduleCalculator:
    return DeterministicMultiOpportunityHeadroomScheduleCalculator(
        DeterministicPVOpportunitySequenceCalculator(),
        DeterministicPVHeadroomRequirementCalculator(),
    )


def test_input_is_frozen_slotted_and_preserves_exact_source_identity() -> None:
    horizon = ForecastHorizon((_point(0, 1.0, 0.0),))
    model = _model()
    configuration = PVOpportunityWindowConfiguration(1)
    schedule_input = MultiOpportunityHeadroomScheduleInput(
        horizon, model, 3600.0, configuration
    )

    assert [field.name for field in fields(MultiOpportunityHeadroomScheduleInput)] == [
        "forecast_horizon",
        "battery_model",
        "control_step_duration_seconds",
        "opportunity_configuration",
    ]
    assert schedule_input.forecast_horizon is horizon
    assert schedule_input.battery_model is model
    assert schedule_input.opportunity_configuration is configuration
    assert not hasattr(schedule_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, schedule_input).control_step_duration_seconds = 1800.0


def test_no_pv_opportunity_produces_empty_schedule() -> None:
    schedule_input = _input((_point(0, 0.0, 1.0), _point(1, 1.0, 1.0)))
    schedule = _calculator().calculate(schedule_input)

    assert schedule.source_input is schedule_input
    assert schedule.opportunity_sequence.source_input.forecast_horizon is (
        schedule_input.forecast_horizon
    )
    assert schedule.opportunity_sequence.entries == ()
    assert schedule.entries == ()


def test_one_opportunity_schedule_target_equals_unchanged_task_132_target() -> None:
    schedule = _calculator().calculate(
        _input((_point(0, 3.0, 0.0), _point(1, 5.0, 0.0)))
    )

    assert len(schedule.entries) == 1
    entry = schedule.entries[0]
    assert entry.required_pre_opportunity_headroom_kwh == (
        entry.headroom_requirement.required_headroom_energy_kwh
    )
    assert entry.recommended_pre_opportunity_max_soc_fraction == (
        entry.headroom_requirement.recommended_pre_pv_max_soc_fraction
    )
    assert entry.gap_start_source_index is None
    assert entry.gap_end_source_index is None
    assert entry.battery_stored_energy_depletion_potential_kwh == 0.0


def test_two_separated_opportunities_preserve_exact_points_order_and_indexes() -> None:
    supplied = (
        _point(0, 3.0, 0.0),
        _point(1, 1.0, 1.0),
        _point(2, 4.0, 0.0),
        _point(3, 0.0, 1.0),
        _point(4, 0.0, 1.0),
        _point(5, 5.0, 0.0),
    )
    schedule_input = _input(supplied, gap=1)
    schedule = _calculator().calculate(schedule_input)

    assert [
        (entry.source_index_start, entry.source_index_end)
        for entry in schedule.opportunity_sequence.entries
    ] == [
        (0, 2),
        (5, 5),
    ]
    first, second = schedule.opportunity_sequence.entries
    assert tuple(step.source_index for step in first.steps) == (0, 1, 2)
    assert tuple(step.forecast_point for step in first.steps) == supplied[:3]
    assert all(
        point is supplied[index]
        for index, point in enumerate(first.selected_forecast_horizon.points)
    )
    assert second.selected_forecast_horizon.points[0] is supplied[5]
    assert schedule.entries[0].opportunity is first
    assert schedule.entries[0].headroom_requirement.source_input.forecast_horizon is (
        first.selected_forecast_horizon
    )


def test_confirmed_gap_within_tolerance_remains_in_one_opportunity() -> None:
    sequence = DeterministicPVOpportunitySequenceCalculator().decompose(
        PVOpportunitySequenceInput(
            ForecastHorizon(
                (_point(0, 3.0, 0.0), _point(1, 0.0, 1.0), _point(2, 3.0, 0.0))
            ),
            PVOpportunityWindowConfiguration(1),
        )
    )

    assert len(sequence.entries) == 1
    assert tuple(step.source_index for step in sequence.entries[0].steps) == (0, 1, 2)
    assert tuple(step.active for step in sequence.entries[0].steps) == (
        True,
        False,
        True,
    )


def test_gap_exceeding_tolerance_separates_opportunities() -> None:
    sequence = DeterministicPVOpportunitySequenceCalculator().decompose(
        PVOpportunitySequenceInput(
            ForecastHorizon(
                (
                    _point(0, 3.0, 0.0),
                    _point(1, 0.0, 1.0),
                    _point(2, 0.0, 1.0),
                    _point(3, 3.0, 0.0),
                )
            ),
            PVOpportunityWindowConfiguration(1),
        )
    )

    assert [
        (entry.source_index_start, entry.source_index_end) for entry in sequence.entries
    ] == [
        (0, 0),
        (3, 3),
    ]


def test_inter_opportunity_deficit_uses_load_side_energy_and_discharge_efficiency() -> (
    None
):
    schedule = _calculator().calculate(
        _input(
            (
                _point(0, 3.0, 0.0),
                _point(1, 0.0, 1.0),
                _point(2, 0.0, 2.0),
                _point(3, 4.0, 0.0),
            ),
            gap=0,
            model=_model(discharge_efficiency=0.5),
        )
    )

    first = schedule.entries[0]
    assert (first.gap_start_source_index, first.gap_end_source_index) == (1, 2)
    assert first.gap_net_deficit_load_energy_kwh == 3.0
    assert first.battery_stored_energy_depletion_potential_kwh == 6.0


def test_backward_recurrence_accounts_for_unrecreated_future_headroom() -> None:
    # own #1 = 3.8 kWh, own #2 = 4.2 kWh, gap potential = 2.0 kWh.
    schedule = _calculator().calculate(
        _input(
            (
                _point(0, 3.8, 0.0),
                _point(1, 0.0, 2.0),
                _point(2, 4.2, 0.0),
            ),
            gap=0,
        )
    )

    first, second = schedule.entries
    assert second.required_pre_opportunity_headroom_kwh == 4.2
    assert first.battery_stored_energy_depletion_potential_kwh == 2.0
    assert first.required_pre_opportunity_headroom_kwh == pytest.approx(6.0)
    assert first.recommended_pre_opportunity_max_soc_fraction == pytest.approx(0.4)


def test_zero_depletion_is_more_conservative_than_first_opportunity_only() -> None:
    schedule = _calculator().calculate(
        _input(
            (_point(0, 3.0, 0.0), _point(1, 0.0, 0.0), _point(2, 4.0, 0.0)),
            gap=0,
        )
    )

    first = schedule.entries[0]
    assert first.headroom_requirement.required_headroom_energy_kwh == 3.0
    assert first.battery_stored_energy_depletion_potential_kwh == 0.0
    assert first.required_pre_opportunity_headroom_kwh == 7.0


def test_large_depletion_converges_to_first_opportunity_standalone_requirement() -> (
    None
):
    schedule = _calculator().calculate(
        _input(
            (_point(0, 3.0, 0.0), _point(1, 0.0, 9.0), _point(2, 4.0, 0.0)),
            gap=0,
        )
    )

    first = schedule.entries[0]
    assert first.required_pre_opportunity_headroom_kwh == 3.0
    assert first.required_pre_opportunity_headroom_kwh == (
        first.headroom_requirement.required_headroom_energy_kwh
    )


def test_schedule_requirement_and_target_are_bounded_by_usable_battery_range() -> None:
    schedule = _calculator().calculate(
        _input(
            (_point(0, 20.0, 0.0), _point(1, 0.0, 0.0), _point(2, 20.0, 0.0)),
            gap=0,
        )
    )

    first = schedule.entries[0]
    assert first.required_pre_opportunity_headroom_kwh == 8.0
    assert first.recommended_pre_opportunity_max_soc_fraction == 0.2


@dataclass(slots=True)
class _CountingSequenceCalculator(PVOpportunitySequenceBoundary):
    calls: int = 0
    last_input: PVOpportunitySequenceInput | None = None

    def decompose(
        self, sequence_input: PVOpportunitySequenceInput
    ) -> PVOpportunitySequence:
        self.calls += 1
        self.last_input = sequence_input
        return DeterministicPVOpportunitySequenceCalculator().decompose(sequence_input)


@dataclass(slots=True)
class _CountingHeadroomCalculator(PVHeadroomRequirementBoundary):
    calls: int = 0
    inputs: list[PVHeadroomRequirementInput] | None = None

    def calculate(
        self,
        requirement_input: PVHeadroomRequirementInput,
    ) -> PVHeadroomRequirement:
        if self.inputs is None:
            self.inputs = []
        self.inputs.append(requirement_input)
        return DeterministicPVHeadroomRequirementCalculator().calculate(
            requirement_input
        )


def test_task_132_is_called_once_per_exact_selected_horizon() -> None:
    sequence_calculator = _CountingSequenceCalculator()
    headroom_calculator = _CountingHeadroomCalculator()
    calculator = DeterministicMultiOpportunityHeadroomScheduleCalculator(
        sequence_calculator,
        headroom_calculator,
    )
    schedule_input = _input(
        (_point(0, 3.0, 0.0), _point(1, 0.0, 1.0), _point(2, 4.0, 0.0)),
        gap=0,
    )

    schedule = calculator.calculate(schedule_input)

    assert sequence_calculator.calls == 1
    assert sequence_calculator.last_input is schedule.opportunity_sequence.source_input
    assert (
        sequence_calculator.last_input.forecast_horizon
        is schedule_input.forecast_horizon
    )
    assert headroom_calculator.inputs is not None
    assert len(headroom_calculator.inputs) == 2
    for requirement_input, entry in zip(
        headroom_calculator.inputs, schedule.entries, strict=True
    ):
        assert requirement_input is entry.headroom_requirement.source_input
        assert (
            requirement_input.forecast_horizon
            is entry.opportunity.selected_forecast_horizon
        )
        assert requirement_input.battery_model is schedule_input.battery_model


def test_reconstructed_value_equal_opportunity_is_rejected() -> None:
    schedule = _calculator().calculate(_input((_point(0, 3.0, 0.0),)))
    entry = schedule.entries[0]
    opportunity = entry.opportunity
    reconstructed = PVOpportunitySequenceEntry(
        opportunity.source_index_start,
        opportunity.source_index_end,
        opportunity.steps,
        opportunity.selected_forecast_horizon,
        opportunity.opportunity_start_timestamp,
        opportunity.opportunity_end_timestamp,
    )
    reconstructed_entry = MultiOpportunityHeadroomScheduleEntry(
        reconstructed,
        entry.headroom_requirement,
        entry.gap_start_source_index,
        entry.gap_end_source_index,
        entry.gap_net_deficit_load_energy_kwh,
        entry.battery_stored_energy_depletion_potential_kwh,
        entry.required_pre_opportunity_headroom_kwh,
        entry.recommended_pre_opportunity_max_soc_fraction,
    )

    with pytest.raises(ValueError, match="exact opportunity identity"):
        MultiOpportunityHeadroomSchedule(
            schedule.source_input,
            schedule.opportunity_sequence,
            (reconstructed_entry,),
        )


def test_boundaries_are_abstract_and_concrete_calculators_are_stateless() -> None:
    with pytest.raises(TypeError):
        cast(Any, PVOpportunitySequenceBoundary)()
    with pytest.raises(TypeError):
        cast(Any, MultiOpportunityHeadroomScheduleBoundary)()
    assert not hasattr(DeterministicPVOpportunitySequenceCalculator(), "__dict__")
    assert not hasattr(_calculator(), "__dict__")


def test_task_146_style_two_opportunity_profile_sits_between_extremes() -> None:
    # First opportunity: 1.2 + 1.7 + 1.1 = 4.0 kWh surplus; second: 8.8 kWh.
    # The 11:00-13:00 deficit recreates some, but not all, later headroom.
    schedule = _calculator().calculate(
        _input(
            (
                _point(8, 2.0, 0.8),
                _point(9, 2.5, 0.8),
                _point(10, 2.0, 0.9),
                _point(11, 0.4, 1.0),
                _point(12, 0.2, 1.1),
                _point(13, 0.1, 1.0),
                _point(14, 3.0, 1.0),
                _point(15, 4.0, 1.0),
                _point(16, 3.5, 1.0),
                _point(17, 2.5, 1.2),
            ),
            gap=1,
            model=_model(capacity=20.0, discharge_efficiency=0.95),
        )
    )

    first, second = schedule.entries
    first_only = first.headroom_requirement.required_headroom_energy_kwh
    blind_full = first_only + second.headroom_requirement.required_headroom_energy_kwh
    assert first_only < first.required_pre_opportunity_headroom_kwh < blind_full


def test_module_dependencies_remain_planning_only() -> None:
    module_path = (
        Path(optimization.__file__).parent / "multi_opportunity_headroom_schedule.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "datetime",
        "forecast",
        "math",
        "optimization.battery_planning",
        "optimization.pv_headroom",
        "optimization.pv_opportunity_window",
    }
    for forbidden in (
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "reservation",
        "DecisionIntent",
        "OptimizationSolution",
    ):
        assert forbidden not in source


def test_public_api_exports_multi_opportunity_schedule_contracts() -> None:
    for name in (
        "PVOpportunitySequenceInput",
        "PVOpportunitySequenceEntry",
        "PVOpportunitySequence",
        "PVOpportunitySequenceBoundary",
        "DeterministicPVOpportunitySequenceCalculator",
        "MultiOpportunityHeadroomScheduleInput",
        "MultiOpportunityHeadroomScheduleEntry",
        "MultiOpportunityHeadroomSchedule",
        "MultiOpportunityHeadroomScheduleBoundary",
        "DeterministicMultiOpportunityHeadroomScheduleCalculator",
    ):
        assert name in optimization.__all__
