"""Tests for deterministic future-PV battery-headroom planning evidence."""

import ast
from dataclasses import FrozenInstanceError, fields
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
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
)


def make_model(
    *,
    minimum: float = 0.2,
    maximum: float = 1.0,
    charge_power: float = 3.0,
    efficiency: float = 0.95,
) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        10.0, minimum, maximum, charge_power, 3.0, efficiency, 0.95
    )


def point(
    hour: int,
    pv: float,
    load: float,
    price: float | None = None,
) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=hour),
        pv,
        load,
        price,
    )


def calculate(
    points: tuple[ForecastPoint, ...],
    *,
    model: BatteryOptimizationModel | None = None,
    duration: float = 3600.0,
) -> PVHeadroomRequirement:
    source = PVHeadroomRequirementInput(
        ForecastHorizon(points), model or make_model(), duration
    )
    return DeterministicPVHeadroomRequirementCalculator().calculate(source)


def test_input_is_frozen_slotted_and_preserves_exact_source_identity() -> None:
    horizon = ForecastHorizon((point(1, 2.0, 1.0),))
    model = make_model()
    source = PVHeadroomRequirementInput(horizon, model, 3600.0)

    assert [field.name for field in fields(PVHeadroomRequirementInput)] == [
        "forecast_horizon",
        "battery_model",
        "control_step_duration_seconds",
    ]
    assert source.forecast_horizon is horizon
    assert source.battery_model is model
    assert not hasattr(source, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, source).control_step_duration_seconds = 1800.0


@pytest.mark.parametrize("duration", [0.0, -1.0, nan, inf, True])
def test_input_rejects_invalid_duration(duration: object) -> None:
    with pytest.raises((TypeError, ValueError), match="control_step_duration_seconds"):
        PVHeadroomRequirementInput(
            ForecastHorizon((point(1, 2.0, 1.0),)), make_model(), cast(Any, duration)
        )


def test_no_pv_surplus_requires_no_headroom_and_keeps_max_soc() -> None:
    requirement = calculate((point(1, 1.0, 1.0), point(2, 0.0, 2.0)))

    assert requirement.total_forecast_pv_surplus_energy_kwh == 0.0
    assert requirement.total_absorbable_pv_input_energy_kwh == 0.0
    assert requirement.required_headroom_energy_kwh == 0.0
    assert requirement.required_headroom_soc_fraction == 0.0
    assert requirement.recommended_pre_pv_max_soc_fraction == 1.0


def test_surplus_below_charge_limit_retains_energy_and_efficiency() -> None:
    requirement = calculate((point(1, 3.0, 1.0),))
    step = requirement.steps[0]

    assert step.pv_surplus_power_kw == 2.0
    assert step.absorbable_charge_power_kw == 2.0
    assert step.absorbable_input_energy_kwh == 2.0
    assert step.stored_energy_delta_kwh == pytest.approx(1.9)
    assert requirement.total_forecast_pv_surplus_energy_kwh == 2.0
    assert requirement.total_absorbable_pv_input_energy_kwh == 2.0
    assert requirement.required_headroom_energy_kwh == pytest.approx(1.9)
    assert requirement.recommended_pre_pv_max_soc_fraction == pytest.approx(0.81)


def test_surplus_above_charge_power_preserves_distinct_pv_and_absorbable_facts() -> (
    None
):
    requirement = calculate((point(1, 6.0, 1.0),))
    step = requirement.steps[0]

    assert step.pv_surplus_power_kw == 5.0
    assert step.absorbable_charge_power_kw == 3.0
    assert step.absorbable_input_energy_kwh == 3.0
    assert step.stored_energy_delta_kwh == pytest.approx(2.85)
    assert requirement.total_forecast_pv_surplus_energy_kwh == 5.0
    assert requirement.total_absorbable_pv_input_energy_kwh == 3.0


def test_multiple_points_preserve_exact_forecast_identity_and_caller_order() -> None:
    supplied = (point(1, 5.0, 1.0, 99.0), point(2, 1.0, 3.0, -9.0))
    requirement = calculate(supplied, duration=1800.0)

    assert requirement.source_input.forecast_horizon.points is supplied
    assert requirement.steps[0].forecast_point is supplied[0]
    assert requirement.steps[1].forecast_point is supplied[1]
    assert requirement.total_forecast_pv_surplus_energy_kwh == 2.0
    assert requirement.total_absorbable_pv_input_energy_kwh == 1.5
    assert requirement.required_headroom_energy_kwh == pytest.approx(1.425)


def test_huge_future_pv_caps_headroom_to_usable_soc_window() -> None:
    requirement = calculate(
        (point(1, 30.0, 0.0), point(2, 30.0, 0.0), point(3, 30.0, 0.0)),
        model=make_model(minimum=0.2, maximum=0.9),
    )

    assert requirement.required_headroom_energy_kwh == 7.0
    assert requirement.required_headroom_soc_fraction == pytest.approx(0.7)
    assert requirement.recommended_pre_pv_max_soc_fraction == pytest.approx(0.2)


def test_empty_horizon_is_deterministic_zero_requirement() -> None:
    requirement = calculate(())

    assert requirement.steps == ()
    assert requirement.required_headroom_energy_kwh == 0.0
    assert requirement.recommended_pre_pv_max_soc_fraction == 1.0


def test_boundary_is_abstract_and_calculator_is_stateless() -> None:
    with pytest.raises(TypeError):
        cast(Any, PVHeadroomRequirementBoundary)()
    calculator = DeterministicPVHeadroomRequirementCalculator()
    assert DeterministicPVHeadroomRequirementCalculator.__slots__ == ()
    assert not hasattr(calculator, "__dict__")


def test_module_has_no_price_soc_decision_or_simulator_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "pv_headroom.py"
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
    }
    for forbidden in (
        "BatteryOptimizationState",
        "electricity_price_cny_per_kwh",
        "DecisionIntent",
        "OptimizationSolution",
        "BatterySolutionRevision",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
    ):
        assert forbidden not in source


def test_public_api_exports_pv_headroom_contracts() -> None:
    assert "PVHeadroomRequirementInput" in optimization.__all__
    assert "PVHeadroomForecastStep" in optimization.__all__
    assert "PVHeadroomRequirement" in optimization.__all__
    assert "PVHeadroomRequirementBoundary" in optimization.__all__
    assert "DeterministicPVHeadroomRequirementCalculator" in optimization.__all__
