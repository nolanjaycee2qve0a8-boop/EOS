"""Tests for rolling PV opportunity to TASK-132 headroom composition."""

import ast
from dataclasses import FrozenInstanceError, dataclass, fields
from datetime import UTC, datetime, timedelta
from math import inf, nan
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationModel,
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunityWindowSelector,
    DeterministicRollingPVHeadroomRequirementCalculator,
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
    PVOpportunityWindow,
    PVOpportunityWindowConfiguration,
    PVOpportunityWindowSelectionBoundary,
    PVOpportunityWindowSelectionInput,
    RollingPVHeadroomRequirement,
    RollingPVHeadroomRequirementBoundary,
    RollingPVHeadroomRequirementInput,
)


def _point(hour: int, pv: float, load: float) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
    )


def _model(
    *,
    maximum: float = 1.0,
    charge_power: float = 3.0,
    efficiency: float = 0.95,
) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        10.0,
        0.2,
        maximum,
        charge_power,
        3.0,
        efficiency,
        0.95,
    )


def _input(
    points: tuple[ForecastPoint, ...],
    *,
    model: BatteryOptimizationModel | None = None,
    gap: int = 1,
    duration: float = 3600.0,
) -> RollingPVHeadroomRequirementInput:
    return RollingPVHeadroomRequirementInput(
        ForecastHorizon(points),
        model or _model(),
        duration,
        PVOpportunityWindowConfiguration(gap),
    )


def _calculator() -> DeterministicRollingPVHeadroomRequirementCalculator:
    return DeterministicRollingPVHeadroomRequirementCalculator(
        DeterministicPVOpportunityWindowSelector(),
        DeterministicPVHeadroomRequirementCalculator(),
    )


def test_input_is_frozen_slotted_and_preserves_exact_source_identity() -> None:
    horizon = ForecastHorizon((_point(0, 1.0, 0.0),))
    model = _model()
    configuration = PVOpportunityWindowConfiguration(1)
    requirement_input = RollingPVHeadroomRequirementInput(
        horizon,
        model,
        3600.0,
        configuration,
    )

    assert [field.name for field in fields(RollingPVHeadroomRequirementInput)] == [
        "forecast_horizon",
        "battery_model",
        "control_step_duration_seconds",
        "window_configuration",
    ]
    assert requirement_input.forecast_horizon is horizon
    assert requirement_input.battery_model is model
    assert requirement_input.window_configuration is configuration
    assert not hasattr(requirement_input, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, requirement_input).control_step_duration_seconds = 1800.0


@pytest.mark.parametrize("duration", [0.0, -1.0, nan, inf, True])
def test_input_rejects_invalid_duration(duration: object) -> None:
    with pytest.raises((TypeError, ValueError), match="control_step_duration_seconds"):
        RollingPVHeadroomRequirementInput(
            ForecastHorizon(()),
            _model(),
            cast(Any, duration),
            PVOpportunityWindowConfiguration(1),
        )


def test_clean_sunny_window_constructs_exact_selected_horizon() -> None:
    supplied = (
        _point(0, 0.0, 1.0),
        _point(1, 3.0, 1.0),
        _point(2, 4.0, 1.0),
        _point(3, 0.0, 1.0),
    )
    requirement_input = _input(supplied)
    result = _calculator().calculate(requirement_input)

    assert result.source_input is requirement_input
    assert result.opportunity_window.source_input.forecast_horizon is (
        requirement_input.forecast_horizon
    )
    assert result.opportunity_window.source_input.configuration is (
        requirement_input.window_configuration
    )
    assert tuple(step.source_index for step in result.opportunity_window.steps) == (
        1,
        2,
    )
    assert result.selected_forecast_horizon.points == supplied[1:3]
    assert all(
        selected is source
        for selected, source in zip(
            result.selected_forecast_horizon.points,
            supplied[1:3],
            strict=True,
        )
    )
    assert result.headroom_requirement.source_input.forecast_horizon is (
        result.selected_forecast_horizon
    )
    assert result.headroom_requirement.source_input.battery_model is (
        requirement_input.battery_model
    )
    assert result.headroom_requirement.total_forecast_pv_surplus_energy_kwh == 5.0


def test_repeating_future_opportunity_contributes_only_first_opportunity() -> None:
    result = _calculator().calculate(
        _input(
            (
                _point(0, 4.0, 1.0),
                _point(1, 3.0, 1.0),
                _point(2, 0.0, 1.0),
                _point(3, 0.0, 1.0),
                _point(4, 11.0, 1.0),
            )
        )
    )

    assert tuple(step.source_index for step in result.opportunity_window.steps) == (
        0,
        1,
    )
    assert len(result.selected_forecast_horizon.points) == 2
    assert result.headroom_requirement.total_forecast_pv_surplus_energy_kwh == 5.0


def test_confirmed_cloud_gap_is_retained_and_naturally_has_zero_surplus() -> None:
    supplied = (
        _point(0, 3.0, 1.0),
        _point(1, 1.0, 1.0),
        _point(2, 4.0, 1.0),
    )
    result = _calculator().calculate(_input(supplied, gap=1))

    assert tuple(step.source_index for step in result.opportunity_window.steps) == (
        0,
        1,
        2,
    )
    assert result.selected_forecast_horizon.points[1] is supplied[1]
    assert result.headroom_requirement.steps[1].pv_surplus_power_kw == 0.0
    assert result.headroom_requirement.total_forecast_pv_surplus_energy_kwh == 5.0


def test_empty_opportunity_reuses_task_132_empty_horizon_behavior() -> None:
    requirement_input = _input((_point(0, 0.0, 1.0), _point(1, 1.0, 1.0)))
    result = _calculator().calculate(requirement_input)

    assert result.opportunity_window.steps == ()
    assert result.selected_forecast_horizon.points == ()
    assert result.headroom_requirement.source_input.forecast_horizon is (
        result.selected_forecast_horizon
    )
    assert result.headroom_requirement.required_headroom_energy_kwh == 0.0
    assert result.headroom_requirement.required_headroom_soc_fraction == 0.0
    assert result.headroom_requirement.recommended_pre_pv_max_soc_fraction == 1.0


def test_current_active_opportunity_begins_at_source_index_zero() -> None:
    result = _calculator().calculate(
        _input((_point(0, 3.0, 1.0), _point(1, 4.0, 1.0), _point(2, 0.0, 1.0)))
    )

    assert result.opportunity_window.start_index == 0
    assert (
        result.selected_forecast_horizon.points[0]
        is (result.source_input.forecast_horizon.points[0])
    )


def test_existing_task_132_power_efficiency_and_usable_soc_cap_are_unchanged() -> None:
    result = _calculator().calculate(
        _input(
            (
                _point(0, 30.0, 0.0),
                _point(1, 30.0, 0.0),
                _point(2, 30.0, 0.0),
            ),
            model=_model(maximum=0.9, charge_power=3.0, efficiency=0.95),
        )
    )

    requirement = result.headroom_requirement
    assert tuple(step.absorbable_charge_power_kw for step in requirement.steps) == (
        3.0,
        3.0,
        3.0,
    )
    assert requirement.total_absorbable_pv_input_energy_kwh == 9.0
    assert requirement.required_headroom_energy_kwh == 7.0
    assert requirement.recommended_pre_pv_max_soc_fraction == pytest.approx(0.2)


@dataclass(slots=True)
class _CountingSelector(PVOpportunityWindowSelectionBoundary):
    calls: int = 0
    last_input: PVOpportunityWindowSelectionInput | None = None

    def select(
        self,
        selection_input: PVOpportunityWindowSelectionInput,
    ) -> PVOpportunityWindow:
        self.calls += 1
        self.last_input = selection_input
        return DeterministicPVOpportunityWindowSelector().select(selection_input)


@dataclass(slots=True)
class _CountingHeadroomCalculator(PVHeadroomRequirementBoundary):
    calls: int = 0
    last_input: PVHeadroomRequirementInput | None = None

    def calculate(
        self,
        requirement_input: PVHeadroomRequirementInput,
    ) -> PVHeadroomRequirement:
        self.calls += 1
        self.last_input = requirement_input
        return DeterministicPVHeadroomRequirementCalculator().calculate(
            requirement_input
        )


def test_composition_calls_each_dependency_once_with_exact_provenance() -> None:
    selector = _CountingSelector()
    headroom_calculator = _CountingHeadroomCalculator()
    calculator = DeterministicRollingPVHeadroomRequirementCalculator(
        selector,
        headroom_calculator,
    )
    requirement_input = _input((_point(0, 3.0, 1.0),))

    result = calculator.calculate(requirement_input)

    assert selector.calls == 1
    assert headroom_calculator.calls == 1
    assert selector.last_input is result.opportunity_window.source_input
    assert selector.last_input.forecast_horizon is requirement_input.forecast_horizon
    assert selector.last_input.configuration is requirement_input.window_configuration
    assert headroom_calculator.last_input is result.headroom_requirement.source_input
    assert (
        headroom_calculator.last_input.forecast_horizon
        is result.selected_forecast_horizon
    )
    assert (
        headroom_calculator.last_input.battery_model is requirement_input.battery_model
    )
    assert (
        headroom_calculator.last_input.control_step_duration_seconds
        == requirement_input.control_step_duration_seconds
    )


def test_output_rejects_reconstructed_selected_point_and_boundary_is_abstract() -> None:
    requirement_input = _input((_point(0, 3.0, 1.0),))
    result = _calculator().calculate(requirement_input)
    selected = result.selected_forecast_horizon.points[0]
    reconstructed = ForecastPoint(
        selected.timestamp,
        selected.pv_power_kw,
        selected.load_power_kw,
        selected.electricity_price_cny_per_kwh,
    )
    reconstructed_horizon = ForecastHorizon((reconstructed,))

    with pytest.raises(ValueError, match="exact selected ForecastPoint identity"):
        RollingPVHeadroomRequirement(
            requirement_input,
            result.opportunity_window,
            reconstructed_horizon,
            result.headroom_requirement,
        )
    with pytest.raises(TypeError):
        cast(Any, RollingPVHeadroomRequirementBoundary)()
    assert not hasattr(_calculator(), "__dict__")


def test_module_has_only_selection_and_headroom_dependencies() -> None:
    module_path = Path(optimization.__file__).parent / "rolling_pv_headroom.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "forecast",
        "math",
        "optimization.battery_planning",
        "optimization.pv_headroom",
        "optimization.pv_opportunity_window",
    }
    for forbidden in (
        "BatteryOptimizationState",
        "electricity_price_cny_per_kwh",
        "DecisionIntent",
        "OptimizationSolution",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
    ):
        assert forbidden not in source


def test_public_api_exports_rolling_pv_headroom_contracts() -> None:
    for name in (
        "RollingPVHeadroomRequirementInput",
        "RollingPVHeadroomRequirement",
        "RollingPVHeadroomRequirementBoundary",
        "DeterministicRollingPVHeadroomRequirementCalculator",
    ):
        assert name in optimization.__all__
