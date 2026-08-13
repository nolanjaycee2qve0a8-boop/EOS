"""Tests for one headroom-aware MPC cycle and its physical compatibility view."""

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
from ems_strategy import (
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    FirstStepMPCCurrentActionExtractor,
    HeadroomAwareMPCCycleBoundary,
    HeadroomAwareMPCCycleResult,
    HeadroomAwareSingleMPCCycleOrchestrator,
    MPCConfiguration,
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCCycleInput,
    MPCDecisionExplanationInput,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
    PhysicallyAwareMPCCycleInput,
)
from ems_strategy.mpc_decision_explanation import (
    DeterministicMPCDecisionExplanationBuilder,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationModel,
    BatteryOptimizationState,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicHeadroomAwareCandidatePlanner,
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    DeterministicHeadroomAwarePhysicalOptimizer,
    DeterministicPVHeadroomRequirementCalculator,
    HeadroomAwarePhysicalOptimizationBoundary,
    HeadroomAwarePhysicalOptimizationSolveOutput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationControlPlan,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationSolutionControlPlanBuilder,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    PhysicallyAwareBaselineOptimizationInput,
)


class CountingHeadroomBoundary(HeadroomAwarePhysicalOptimizationBoundary):
    """Test-only wrapper proving TASK-136 is invoked exactly once."""

    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0

    def __init__(self, delegate: HeadroomAwarePhysicalOptimizationBoundary) -> None:
        self._delegate = delegate

    def solve_headroom_aware(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> HeadroomAwarePhysicalOptimizationSolveOutput:
        self.__class__.calls += 1
        return self._delegate.solve_headroom_aware(optimization_input)


class CountingPlanConstructor(OptimizationSolutionControlPlanConstructionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    received_solution: ClassVar[object | None] = None

    def construct(
        self,
        construction_input: OptimizationSolutionControlPlanConstructionInput,
    ) -> OptimizationControlPlan:
        self.__class__.calls += 1
        self.__class__.received_solution = construction_input.solution
        return OptimizationSolutionControlPlanBuilder().construct(construction_input)


class CountingExtractor(MPCCurrentActionExtractionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        self.__class__.calls += 1
        return FirstStepMPCCurrentActionExtractor().extract(plan)


class MinimalDecisionTranslator(MPCDecisionTranslationBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        self.__class__.calls += 1
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
def reset_dependencies() -> None:
    CountingHeadroomBoundary.calls = 0
    CountingPlanConstructor.calls = 0
    CountingPlanConstructor.received_solution = None
    CountingExtractor.calls = 0
    MinimalDecisionTranslator.calls = 0


def make_context() -> EMSContext:
    source_context = DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=0.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.3,
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
    return EMSContext(
        source_context,
        ObjectiveCapabilityActivationComposition(
            ObjectiveDescriptor("cost", "Describe cost without solving it."),
            ActiveCapabilityCollection(matches, (available,), ()),
        ),
        available,
    )


def forecast_point(
    hour: int, *, pv: float, load: float, price: float | None
) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, hour, tzinfo=UTC),
        pv,
        load,
        price,
    )


def make_input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.45,
    model: BatteryOptimizationModel | None = None,
    objectives: tuple[OptimizationObjective, ...] = (
        OptimizationObjective("energy_cost", "minimize"),
    ),
) -> PhysicallyAwareMPCCycleInput:
    cycle = MPCCycleInput(
        make_context(),
        ForecastHorizon(points),
        MPCConfiguration(len(points), 3600.0),
        OptimizationObjectiveCollection(objectives),
        EMSStrategyDescriptor("mpc", "1.0"),
    )
    return PhysicallyAwareMPCCycleInput(
        cycle,
        BatteryOptimizationState(soc),
        model or BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95),
    )


def make_headroom_boundary() -> HeadroomAwarePhysicalOptimizationBoundary:
    return DeterministicHeadroomAwarePhysicalOptimizer(
        DeterministicPVHeadroomRequirementCalculator(),
        DeterministicHeadroomAwareCandidatePlanner(
            NetLoadAwareBaselineOptimizer(
                NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)
            ),
            DeterministicHeadroomAwareGridChargeReservationCalculator(),
        ),
        DeterministicExplicitCandidatePhysicalReviser(
            DeterministicBatterySOCHorizonProjector(),
            DeterministicBatterySOCHorizonConstraintEvaluator(),
            DeterministicBatteryPowerHorizonConstraintEvaluator(),
            DeterministicBatteryHorizonConstraintAggregator(),
        ),
    )


def make_orchestrator(
    boundary: HeadroomAwarePhysicalOptimizationBoundary | None = None,
) -> HeadroomAwareSingleMPCCycleOrchestrator:
    return HeadroomAwareSingleMPCCycleOrchestrator(
        boundary or make_headroom_boundary(),
        CountingPlanConstructor(),
        CountingExtractor(),
        MinimalDecisionTranslator(),
    )


def test_cheap_grid_headroom_then_physical_then_decision_provenance() -> None:
    source = make_input(
        (
            forecast_point(1, pv=0.0, load=1.0, price=0.3),
            forecast_point(2, pv=3.0, load=0.0, price=None),
            forecast_point(3, pv=2.263157894736842, load=0.0, price=None),
        )
    )
    result = make_orchestrator().run_cycle(source)
    output = result.headroom_optimization_output
    planning = output.candidate_planning_result

    assert planning.source_candidate_output.solution.steps[0].requested_power_kw == 3.0
    assert planning.grid_charge_reservation is not None
    assert planning.final_output.solution.steps[0].requested_power_kw == pytest.approx(
        0.5263157894736842
    )
    assert output.physical_output.candidate_output is planning.final_output
    assert result.decision.requested_power_kw == pytest.approx(0.5263157894736842)
    assert result.decision.intent is result.current_action.selected_step.intent
    assert CountingPlanConstructor.received_solution is (
        output.physical_output.final_output.solution
    )


def test_pv_surplus_is_not_reserved_then_is_physically_power_limited() -> None:
    result = make_orchestrator().run_cycle(
        make_input((forecast_point(1, pv=6.0, load=0.0, price=0.3),), soc=0.2)
    )
    output = result.headroom_optimization_output
    planning = output.candidate_planning_result

    assert planning.grid_charge_reservation is None
    assert planning.final_output.solution.steps[0].requested_power_kw == 6.0
    assert (
        output.physical_output.final_output.solution.steps[0].requested_power_kw == 3.0
    )
    assert output.physical_output.revision.steps[0].reasons == ("charge_power_limit",)
    assert result.decision.requested_power_kw == 3.0


def test_high_price_discharge_and_all_exact_identity_links_are_preserved() -> None:
    source = make_input((forecast_point(1, pv=0.0, load=2.0, price=0.9),), soc=0.8)
    result = make_orchestrator().run_cycle(source)
    output = result.headroom_optimization_output

    assert result.problem.context is source.cycle_input.context
    assert result.problem.forecast_horizon is source.cycle_input.forecast_horizon
    assert result.problem.objectives is source.cycle_input.objectives
    assert result.battery_input.battery_state is source.battery_state
    assert result.battery_input.battery_model is source.battery_model
    assert output.source_input is result.physically_aware_input
    assert output.physical_output.source_input is result.physically_aware_input
    assert output.physical_output.candidate_output is (
        output.candidate_planning_result.final_output
    )
    assert (
        result.control_plan.source_result is output.physical_output.final_output.result
    )
    assert result.current_action.source_plan is result.control_plan
    assert result.decision.source_context is source.cycle_input.context
    assert result.decision.source_strategy is source.cycle_input.source_strategy
    assert result.decision.intent is result.current_action.selected_step.intent
    assert result.decision.intent.action == "discharge"


def test_physical_cycle_view_reuses_exact_artifacts_and_existing_builder() -> None:
    result = make_orchestrator().run_cycle(
        make_input((forecast_point(1, pv=6.0, load=0.0, price=0.3),), soc=0.2)
    )
    view = result.physical_cycle_view

    assert view.source_input is result.source_input
    assert view.problem is result.problem
    assert view.battery_input is result.battery_input
    assert view.physically_aware_input is result.physically_aware_input
    assert (
        view.optimization_output is result.headroom_optimization_output.physical_output
    )
    assert view.control_plan is result.control_plan
    assert view.current_action is result.current_action
    assert view.decision is result.decision
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        MPCDecisionExplanationInput(view)
    )
    assert explanation.candidate_requested_power_kw == 6.0
    assert explanation.final_requested_power_kw == 3.0
    assert explanation.physical_explanation.revision_reasons == ("charge_power_limit",)


def test_headroom_dependency_and_downstream_boundaries_execute_once() -> None:
    boundary = CountingHeadroomBoundary(make_headroom_boundary())
    result = make_orchestrator(boundary).run_cycle(
        make_input((forecast_point(1, pv=0.0, load=2.0, price=0.9),), soc=0.8)
    )

    assert (
        CountingHeadroomBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == (1, 1, 1, 1)
    assert result.physical_cycle_view.optimization_output is (
        result.headroom_optimization_output.physical_output
    )


def test_unsupported_objective_preserves_existing_extractor_failure() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        make_orchestrator().run_cycle(
            make_input(
                (forecast_point(1, pv=0.0, load=1.0, price=0.3),),
                objectives=(OptimizationObjective("unsupported", "minimize"),),
            )
        )
    assert CountingPlanConstructor.calls == 1
    assert CountingExtractor.calls == 1
    assert MinimalDecisionTranslator.calls == 0


def test_contracts_are_frozen_slotted_and_boundary_is_abstract() -> None:
    source = make_input((forecast_point(1, pv=0.0, load=2.0, price=0.9),))
    result = make_orchestrator().run_cycle(source)

    assert [field.name for field in fields(HeadroomAwareMPCCycleResult)] == [
        "source_input",
        "problem",
        "battery_input",
        "physically_aware_input",
        "headroom_optimization_output",
        "control_plan",
        "current_action",
        "decision",
        "physical_cycle_view",
    ]
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).decision = result.decision
    assert issubclass(HeadroomAwareMPCCycleBoundary, ABC)
    assert inspect.isabstract(HeadroomAwareMPCCycleBoundary)
    assert HeadroomAwareMPCCycleBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, HeadroomAwareMPCCycleBoundary)()
    hints = get_type_hints(HeadroomAwareMPCCycleBoundary.run_cycle)
    assert hints == {
        "cycle_input": PhysicallyAwareMPCCycleInput,
        "return": HeadroomAwareMPCCycleResult,
    }


def test_module_has_no_execution_or_direct_candidate_dependencies() -> None:
    module_path = Path(ems_strategy.__file__).parent / "mpc_headroom_aware.py"
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    for forbidden in (
        "optimization.net_load_aware_baseline",
        "optimization.pv_headroom",
        "optimization.headroom_aware_candidate_planning",
        "optimization.physically_aware_baseline",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules


def test_public_api_exports_headroom_aware_mpc_cycle_contracts() -> None:
    for name in (
        "HeadroomAwareMPCCycleBoundary",
        "HeadroomAwareMPCCycleResult",
        "HeadroomAwareSingleMPCCycleOrchestrator",
    ):
        assert name in ems_strategy.__all__
