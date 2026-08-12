"""Tests for the one-pass price-candidate physical revision path."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from math import inf, nan
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import optimization
from forecast import ForecastPoint
from optimization import (
    BatteryHorizonConstraintAggregateBoundary,
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
    BatteryPowerHorizonConstraintBoundary,
    BatterySOCHorizonConstraintBoundary,
    BatterySOCHorizonProjectionBoundary,
    BatterySolutionRevision,
    BatterySolutionRevisionStep,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    OptimizationObjective,
    OptimizationSolutionStep,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareOptimizationBoundary,
    PhysicallyAwareOptimizationSolveOutput,
    PhysicallyAwarePriceBaselineOptimizer,
    PriceAwareBaselineOptimizationConfiguration,
    PriceAwareBaselineOptimizer,
)
from tests.unit.optimization.test_price_aware_baseline_optimizer import (
    make_problem,
    point,
)


def make_model(
    *,
    min_soc: float = 0.1,
    max_soc: float = 0.9,
    max_charge: float = 4.0,
    max_discharge: float = 4.0,
    charge_efficiency: float = 1.0,
    discharge_efficiency: float = 1.0,
) -> BatteryOptimizationModel:
    return BatteryOptimizationModel(
        10.0,
        min_soc,
        max_soc,
        max_charge,
        max_discharge,
        charge_efficiency,
        discharge_efficiency,
    )


def make_optimizer(power: float = 6.0) -> PhysicallyAwarePriceBaselineOptimizer:
    return PhysicallyAwarePriceBaselineOptimizer(
        PriceAwareBaselineOptimizer(
            PriceAwareBaselineOptimizationConfiguration(0.3, 0.8, power)
        ),
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )


def make_input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.5,
    model: BatteryOptimizationModel | None = None,
    objectives: tuple[OptimizationObjective, ...] | None = None,
) -> PhysicallyAwareBaselineOptimizationInput:
    problem = make_problem(
        points,
        objectives
        if objectives is not None
        else (OptimizationObjective("energy_cost", "minimize"),),
    )
    battery_input = BatteryOptimizationInput(
        problem,
        BatteryOptimizationState(soc),
        model or make_model(),
    )
    return PhysicallyAwareBaselineOptimizationInput(battery_input, 3600.0)


class MinimalPhysicalBoundary(PhysicallyAwareOptimizationBoundary):
    """Test-only stateless boundary preserving its explicit output."""

    __slots__ = ()

    def solve_physically(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> PhysicallyAwareOptimizationSolveOutput:
        return make_optimizer().solve_physically(optimization_input)


def test_input_and_revision_artifacts_are_frozen_slotted_and_validate_duration() -> (
    None
):
    physical_input = make_input(())
    output = make_optimizer().solve_physically(physical_input)

    assert [
        field.name for field in fields(PhysicallyAwareBaselineOptimizationInput)
    ] == [
        "battery_input",
        "control_step_duration_seconds",
    ]
    assert [field.name for field in fields(BatterySolutionRevision)] == [
        "source_candidate_solution",
        "revised_solution",
        "steps",
    ]
    assert physical_input.battery_input is physical_input.battery_input
    assert output.revision.steps == ()
    assert not hasattr(physical_input, "__dict__")
    assert not hasattr(output, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, physical_input).battery_input = physical_input.battery_input
    for invalid in (0, -1, nan, inf, True):
        with pytest.raises((TypeError, ValueError)):
            PhysicallyAwareBaselineOptimizationInput(
                physical_input.battery_input,
                cast(Any, invalid),
            )


def test_candidate_evidence_is_retained_exactly_and_final_evidence_is_feasible() -> (
    None
):
    physical_input = make_input((point(1, 0.2), point(2, 0.9)))
    output = make_optimizer().solve_physically(physical_input)

    assert output.source_input is physical_input
    assert output.candidate_output.solution is output.revision.source_candidate_solution
    assert (
        output.candidate_projection.source_input.solution
        is output.candidate_output.solution
    )
    assert (
        output.candidate_soc_evaluation.source_input.projection
        is output.candidate_projection
    )
    assert (
        output.candidate_constraint_evaluation.source_input.soc_evaluation
        is output.candidate_soc_evaluation
    )
    assert (
        output.candidate_constraint_evaluation.source_input.power_evaluation
        is output.candidate_power_evaluation
    )
    assert output.final_output.solution is output.revision.revised_solution
    assert output.final_projection.source_input.solution is output.final_output.solution
    assert output.final_constraint_evaluation.feasible is True
    assert output.final_soc_evaluation.feasible is True
    assert output.final_power_evaluation.feasible is True
    assert output.candidate_output.result is not output.final_output.result
    assert (
        output.candidate_output.result.source_problem
        is output.final_output.result.source_problem
    )


def test_power_and_soc_limits_revise_without_reversing_direction_and_explain_both() -> (
    None
):
    physical_input = make_input(
        (point(1, 0.2),),
        soc=0.7,
        model=make_model(max_soc=0.9, max_charge=5.0),
    )
    output = make_optimizer(8.0).solve_physically(physical_input)
    candidate = output.candidate_output.solution.steps[0]
    revised = output.final_output.solution.steps[0]
    evidence = output.revision.steps[0]

    assert candidate.intent.action == "charge"
    assert candidate.requested_power_kw == 8.0
    assert revised is evidence.revised_step
    assert revised is not candidate
    assert revised.intent.action == "charge"
    assert 0 < revised.requested_power_kw < 5.0
    assert evidence.reasons == ("charge_power_limit", "max_soc_limit")
    assert output.final_projection.steps[0].ending_soc_fraction <= 0.9


def test_discharge_power_and_minimum_soc_revisions_follow_sequential_physics() -> None:
    physical_input = make_input(
        (point(1, 0.9), point(2, 0.9)),
        soc=0.8,
        model=make_model(min_soc=0.1, max_discharge=4.0),
    )
    output = make_optimizer(6.0).solve_physically(physical_input)
    first, second = output.final_output.solution.steps

    assert first.intent.action == "discharge"
    assert first.requested_power_kw == 4.0
    assert output.revision.steps[0].reasons == ("discharge_power_limit",)
    assert second.intent.action == "discharge"
    assert 0 < second.requested_power_kw < 4.0
    assert output.revision.steps[1].reasons == (
        "discharge_power_limit",
        "min_soc_limit",
    )
    assert output.final_projection.steps[1].starting_soc_fraction == pytest.approx(
        output.final_projection.steps[0].ending_soc_fraction
    )
    assert output.final_constraint_evaluation.feasible is True


def test_zero_available_energy_becomes_idle_with_soc_reason_only() -> None:
    physical_input = make_input((point(1, 0.9),), soc=0.1)
    output = make_optimizer(3.0).solve_physically(physical_input)
    revised = output.final_output.solution.steps[0]

    assert revised.intent.action == "idle"
    assert revised.requested_power_kw == 0.0
    assert output.revision.steps[0].reasons == ("min_soc_limit",)


def test_feasible_candidate_is_semantically_unchanged_but_uses_explicit_new_steps() -> (
    None
):
    physical_input = make_input((point(1, 0.2),), model=make_model(max_charge=10.0))
    output = make_optimizer(2.0).solve_physically(physical_input)
    candidate = output.candidate_output.solution.steps[0]
    revised = output.final_output.solution.steps[0]

    assert output.candidate_constraint_evaluation.feasible is True
    assert revised is not candidate
    assert revised.intent.action == candidate.intent.action
    assert revised.requested_power_kw == candidate.requested_power_kw
    assert output.revision.steps[0].reasons == ()


def test_unsupported_candidate_remains_unavailable_and_empty_without_idle_steps() -> (
    None
):
    physical_input = make_input(
        (point(1, 0.2),),
        objectives=(OptimizationObjective("unsupported", "minimize"),),
    )
    output = make_optimizer().solve_physically(physical_input)

    assert output.candidate_output.result.outcome == "unavailable"
    assert output.final_output.result.outcome == "unavailable"
    assert output.candidate_output.solution.steps == ()
    assert output.final_output.solution.steps == ()
    assert output.revision.steps == ()
    assert output.final_constraint_evaluation.feasible is True


def test_revision_rejects_reconstructed_candidate_step_identity() -> None:
    physical_input = make_input((point(1, 0.2),))
    output = make_optimizer(2.0).solve_physically(physical_input)
    candidate_solution = output.candidate_output.solution
    reconstructed = OptimizationSolutionStep(
        candidate_solution.steps[0].timestamp,
        candidate_solution.steps[0].intent,
        candidate_solution.steps[0].requested_power_kw,
    )
    evidence = output.revision.steps[0]
    with pytest.raises(ValueError, match="candidate step identity"):
        BatterySolutionRevision(
            candidate_solution,
            output.final_output.solution,
            (
                BatterySolutionRevisionStep(
                    reconstructed,
                    evidence.revised_step,
                    0,
                    evidence.reasons,
                ),
            ),
        )


def test_boundary_contract_is_abstract_slotted_with_explicit_dependencies() -> None:
    signature = inspect.signature(PhysicallyAwareOptimizationBoundary.solve_physically)
    hints = get_type_hints(PhysicallyAwareOptimizationBoundary.solve_physically)
    optimizer = make_optimizer()

    assert issubclass(PhysicallyAwareOptimizationBoundary, ABC)
    assert inspect.isabstract(PhysicallyAwareOptimizationBoundary)
    assert PhysicallyAwareOptimizationBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "optimization_input"]
    assert hints == {
        "optimization_input": PhysicallyAwareBaselineOptimizationInput,
        "return": PhysicallyAwareOptimizationSolveOutput,
    }
    assert optimizer.price_optimizer is not None
    assert isinstance(optimizer.soc_projector, BatterySOCHorizonProjectionBoundary)
    assert isinstance(optimizer.soc_evaluator, BatterySOCHorizonConstraintBoundary)
    assert isinstance(optimizer.power_evaluator, BatteryPowerHorizonConstraintBoundary)
    assert isinstance(
        optimizer.constraint_aggregator,
        BatteryHorizonConstraintAggregateBoundary,
    )
    with pytest.raises(TypeError):
        PhysicallyAwareOptimizationBoundary()  # type: ignore[abstract]
    assert not hasattr(MinimalPhysicalBoundary(), "__dict__")


def test_module_has_no_strategy_feasibility_simulator_or_execution_dependency() -> None:
    module_path = Path(optimization.__file__).parent / "physically_aware_baseline.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    for forbidden_root in (
        "ems_strategy",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "dispatch",
        "execution",
        "scipy",
        "cvxpy",
        "pulp",
        "pyomo",
        "ortools",
    ):
        assert forbidden_root not in imported_modules
    assert "FeasibilityBoundary" not in source
    assert "BatterySimulationActuation" not in source


def test_public_api_exports_physically_aware_revision_contracts() -> None:
    for name in (
        "BatterySolutionRevision",
        "BatterySolutionRevisionReason",
        "BatterySolutionRevisionStep",
        "PhysicallyAwareBaselineOptimizationInput",
        "PhysicallyAwareOptimizationBoundary",
        "PhysicallyAwareOptimizationSolveOutput",
        "PhysicallyAwarePriceBaselineOptimizer",
    ):
        assert name in optimization.__all__
