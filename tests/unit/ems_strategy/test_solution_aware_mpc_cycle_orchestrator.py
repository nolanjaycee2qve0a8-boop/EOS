"""Tests for exactly one solution-aware MPC cycle integration path."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast, get_type_hints

import pytest

import ems_strategy
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import DecisionIntent
from ems_strategy import (
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    FirstStepMPCCurrentActionExtractor,
    MPCConfiguration,
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCCycleInput,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
    MPCSolutionCycleBoundary,
    MPCSolutionCycleResult,
    SolutionAwareSingleMPCCycleOrchestrator,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    OptimizationControlPlan,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
    OptimizationSolution,
    OptimizationSolutionBoundary,
    OptimizationSolutionControlPlanBuilder,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    OptimizationSolutionStep,
    OptimizationSolveOutput,
    PriceAwareBaselineOptimizationConfiguration,
    PriceAwareBaselineOptimizer,
)


class CountingSolutionBoundary(OptimizationSolutionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    empty_solution: ClassVar[bool] = False
    failure: ClassVar[Exception | None] = None
    foreign_problem: ClassVar[OptimizationProblem | None] = None

    def solve_with_solution(
        self, problem: OptimizationProblem
    ) -> OptimizationSolveOutput:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        source_problem = self.foreign_problem or problem
        result = OptimizationResult(source_problem, "optimal")
        if self.empty_solution:
            return OptimizationSolveOutput(result, OptimizationSolution(result, ()))
        solution = OptimizationSolution(
            result,
            (
                OptimizationSolutionStep(
                    datetime(2026, 1, 1, 1, tzinfo=UTC),
                    DecisionIntent("charge"),
                    1.0,
                ),
            ),
        )
        return OptimizationSolveOutput(result, solution)


class CountingPlanConstructor(OptimizationSolutionControlPlanConstructionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def construct(
        self,
        construction_input: OptimizationSolutionControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        return OptimizationSolutionControlPlanBuilder().construct(construction_input)


class CountingExtractor(MPCCurrentActionExtractionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        return FirstStepMPCCurrentActionExtractor().extract(plan)


class MinimalDecisionTranslator(MPCDecisionTranslationBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    failure: ClassVar[Exception | None] = None

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        self.__class__.calls += 1
        if self.failure is not None:
            raise self.failure
        step = translation.current_action.selected_step
        context = (
            translation.current_action.source_plan.source_result.source_problem.context
        )
        return EMSDecision(
            context,
            translation.source_strategy,
            step.intent,
            step.requested_power_kw,
        )


@pytest.fixture(autouse=True)
def reset_test_dependencies() -> None:
    for dependency in (
        CountingSolutionBoundary,
        CountingPlanConstructor,
        CountingExtractor,
        MinimalDecisionTranslator,
    ):
        dependency.calls = 0
        if dependency is CountingSolutionBoundary:
            dependency.empty_solution = False
        dependency.failure = None
    CountingSolutionBoundary.foreign_problem = None


def make_input(
    price: float = 0.2,
    objectives: tuple[OptimizationObjective, ...] = (
        OptimizationObjective("energy_cost", "minimize"),
    ),
) -> MPCCycleInput:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=1.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )
    required = CapabilityDescriptor("mpc", "Required MPC capability.")
    available = CapabilityDescriptor("mpc", "Available MPC capability.")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((required,)),
        AvailableCapabilityCollection((available,)),
        (CapabilityMatch(required, available),),
        (),
    )
    context = EMSContext(
        source_context,
        ObjectiveCapabilityActivationComposition(
            ObjectiveDescriptor("cost", "Describe cost without solving it."),
            ActiveCapabilityCollection(matches, (available,), ()),
        ),
        available,
    )
    return MPCCycleInput(
        context,
        ForecastHorizon(
            (
                ForecastPoint(
                    datetime(2026, 1, 1, 1, tzinfo=UTC),
                    pv_power_kw=1.0,
                    load_power_kw=2.0,
                    electricity_price_cny_per_kwh=price,
                ),
            )
        ),
        MPCConfiguration(1, 3600.0),
        OptimizationObjectiveCollection(objectives),
        EMSStrategyDescriptor("mpc", "1.0"),
    )


def make_counting_orchestrator() -> SolutionAwareSingleMPCCycleOrchestrator:
    return SolutionAwareSingleMPCCycleOrchestrator(
        CountingSolutionBoundary(),
        CountingPlanConstructor(),
        CountingExtractor(),
        MinimalDecisionTranslator(),
    )


def test_solution_cycle_boundary_is_abstract_empty_slotted_and_explicit() -> None:
    signature = inspect.signature(MPCSolutionCycleBoundary.run_cycle)
    hints = get_type_hints(MPCSolutionCycleBoundary.run_cycle)

    assert issubclass(MPCSolutionCycleBoundary, ABC)
    assert inspect.isabstract(MPCSolutionCycleBoundary)
    assert MPCSolutionCycleBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "cycle_input"]
    assert hints == {"cycle_input": MPCCycleInput, "return": MPCSolutionCycleResult}
    with pytest.raises(TypeError):
        MPCSolutionCycleBoundary()  # type: ignore[abstract]


def test_solution_cycle_result_is_frozen_slotted_and_preserves_full_chain() -> None:
    cycle_input = make_input()
    cycle_result = make_counting_orchestrator().run_cycle(cycle_input)

    assert [field.name for field in fields(MPCSolutionCycleResult)] == [
        "source_input",
        "problem",
        "solve_output",
        "optimization_result",
        "optimization_solution",
        "control_plan",
        "current_action",
        "decision",
    ]
    assert cycle_result.source_input is cycle_input
    assert cycle_result.solve_output.result is cycle_result.optimization_result
    assert cycle_result.solve_output.solution is cycle_result.optimization_solution
    assert cycle_result.optimization_result.source_problem is cycle_result.problem
    assert (
        cycle_result.optimization_solution.source_result
        is cycle_result.optimization_result
    )
    assert cycle_result.control_plan.source_result is cycle_result.optimization_result
    assert cycle_result.current_action.source_plan is cycle_result.control_plan
    assert cycle_result.decision.source_context is cycle_input.context
    assert cycle_result.decision.source_strategy is cycle_input.source_strategy
    assert (
        cycle_result.decision.intent is cycle_result.current_action.selected_step.intent
    )
    assert not hasattr(cycle_result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, cycle_result).decision = cycle_result.decision


def test_orchestrator_calls_every_dependency_once_in_exact_order() -> None:
    cycle_result = make_counting_orchestrator().run_cycle(make_input())

    assert (
        CountingSolutionBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == (1, 1, 1, 1)
    assert cycle_result.decision.requested_power_kw == 1.0


@pytest.mark.parametrize(
    ("price", "action"),
    [(0.2, "charge"), (1.0, "discharge")],
)
def test_real_price_optimizer_and_plan_builder_reach_decision_end_to_end(
    price: float,
    action: str,
) -> None:
    optimizer = PriceAwareBaselineOptimizer(
        PriceAwareBaselineOptimizationConfiguration(0.3, 0.8, 2.5)
    )
    orchestrator = SolutionAwareSingleMPCCycleOrchestrator(
        optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        MinimalDecisionTranslator(),
    )
    cycle_input = make_input(price)

    cycle_result = orchestrator.run_cycle(cycle_input)

    assert cycle_result.decision.intent.action == action
    assert cycle_result.decision.requested_power_kw == 2.5
    assert cycle_result.decision.source_context is cycle_input.context
    assert cycle_result.decision.source_strategy is cycle_input.source_strategy


@pytest.mark.parametrize(
    ("failure_stage", "expected_calls"),
    [
        ("solve", (1, 0, 0, 0)),
        ("plan", (1, 1, 0, 0)),
        ("extract", (1, 1, 1, 0)),
        ("translate", (1, 1, 1, 1)),
    ],
)
def test_first_failure_stops_without_retry_or_downstream_calls(
    failure_stage: str,
    expected_calls: tuple[int, int, int, int],
) -> None:
    failures: dict[str, type[Exception]] = {
        "solve": LookupError,
        "plan": ArithmeticError,
        "extract": KeyError,
        "translate": RuntimeError,
    }
    failure = failures[failure_stage]("stop")
    if failure_stage == "solve":
        CountingSolutionBoundary.failure = failure
    elif failure_stage == "plan":
        CountingPlanConstructor.failure = failure
    elif failure_stage == "extract":
        CountingExtractor.failure = failure
    else:
        MinimalDecisionTranslator.failure = failure

    with pytest.raises(failures[failure_stage], match="stop"):
        make_counting_orchestrator().run_cycle(make_input())

    assert (
        CountingSolutionBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == expected_calls


def test_invalid_solve_output_provenance_stops_before_plan_construction() -> None:
    cycle_input = make_input()
    CountingSolutionBoundary.foreign_problem = OptimizationProblem(
        cycle_input.context,
        cycle_input.forecast_horizon,
        cycle_input.objectives,
    )

    with pytest.raises(ValueError, match="problem identity"):
        make_counting_orchestrator().run_cycle(cycle_input)

    assert (
        CountingSolutionBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == (1, 0, 0, 0)


def test_empty_solution_propagates_existing_extraction_failure_without_idle() -> None:
    optimizer = PriceAwareBaselineOptimizer(
        PriceAwareBaselineOptimizationConfiguration(0.3, 0.8, 2.5)
    )
    unsupported = (OptimizationObjective("other", "minimize"),)
    orchestrator = SolutionAwareSingleMPCCycleOrchestrator(
        optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        MinimalDecisionTranslator(),
    )

    with pytest.raises(ValueError, match="at least one step"):
        orchestrator.run_cycle(make_input(0.2, unsupported))


def test_optimal_empty_solution_propagates_existing_extraction_failure_without_idle() -> (  # noqa: E501
    None
):
    CountingSolutionBoundary.empty_solution = True

    with pytest.raises(ValueError, match="at least one step"):
        make_counting_orchestrator().run_cycle(make_input())

    assert (
        CountingSolutionBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == (1, 1, 1, 0)


def test_solution_cycle_modules_have_no_execution_or_physical_dependency() -> None:
    package_path = Path(ems_strategy.__file__).parent
    forbidden_roots = {
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
    }
    for module_name in ("mpc_solution_cycle.py", "mpc_solution_orchestrator.py"):
        tree = ast.parse((package_path / module_name).read_text(encoding="utf-8"))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert all(
            module is None or module.split(".", maxsplit=1)[0] not in forbidden_roots
            for module in imported_modules
        )


def test_public_api_exports_solution_aware_cycle_contracts() -> None:
    for name in (
        "MPCSolutionCycleBoundary",
        "MPCSolutionCycleResult",
        "SolutionAwareSingleMPCCycleOrchestrator",
    ):
        assert name in ems_strategy.__all__
