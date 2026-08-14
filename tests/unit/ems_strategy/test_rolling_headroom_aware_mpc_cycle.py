"""Tests for one rolling-headroom-aware MPC cycle and its evidence view."""

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
    MPCConfiguration,
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCCycleInput,
    MPCDecisionExplanationInput,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
    PhysicallyAwareMPCCycleInput,
    RollingHeadroomAwareMPCCycleBoundary,
    RollingHeadroomAwareMPCCycleResult,
    RollingHeadroomAwareSingleMPCCycleOrchestrator,
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
    DeterministicPVHeadroomRequirementCalculator,
    DeterministicPVOpportunityWindowSelector,
    DeterministicRollingHeadroomAwarePhysicalOptimizer,
    DeterministicRollingPVHeadroomRequirementCalculator,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationControlPlan,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationSolutionControlPlanBuilder,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
    PhysicallyAwareBaselineOptimizationInput,
    PVOpportunityWindowConfiguration,
    RollingHeadroomAwarePhysicalOptimizationBoundary,
    RollingHeadroomAwarePhysicalOptimizationSolveOutput,
)


class CountingRollingBoundary(RollingHeadroomAwarePhysicalOptimizationBoundary):
    __slots__ = ("_delegate",)
    calls: ClassVar[int] = 0

    def __init__(
        self, delegate: RollingHeadroomAwarePhysicalOptimizationBoundary
    ) -> None:
        self._delegate = delegate

    def solve_rolling_headroom_aware(
        self, optimization_input: PhysicallyAwareBaselineOptimizationInput
    ) -> RollingHeadroomAwarePhysicalOptimizationSolveOutput:
        self.__class__.calls += 1
        return self._delegate.solve_rolling_headroom_aware(optimization_input)


class CountingPlanConstructor(OptimizationSolutionControlPlanConstructionBoundary):
    __slots__ = ()
    calls: ClassVar[int] = 0
    received_solution: ClassVar[object | None] = None

    def construct(
        self, construction_input: OptimizationSolutionControlPlanConstructionInput
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
            context, translation.source_strategy, step.intent, step.requested_power_kw
        )


@pytest.fixture(autouse=True)
def reset_dependencies() -> None:
    CountingRollingBoundary.calls = 0
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


def point(hour: int, *, pv: float, load: float, price: float | None) -> ForecastPoint:
    return ForecastPoint(datetime(2026, 1, 1, hour, tzinfo=UTC), pv, load, price)


def make_input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.45,
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
        BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95),
    )


def make_boundary() -> RollingHeadroomAwarePhysicalOptimizationBoundary:
    return DeterministicRollingHeadroomAwarePhysicalOptimizer(
        DeterministicRollingPVHeadroomRequirementCalculator(
            DeterministicPVOpportunityWindowSelector(),
            DeterministicPVHeadroomRequirementCalculator(),
        ),
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
        PVOpportunityWindowConfiguration(1),
    )


def make_orchestrator(
    boundary: RollingHeadroomAwarePhysicalOptimizationBoundary | None = None,
) -> RollingHeadroomAwareSingleMPCCycleOrchestrator:
    return RollingHeadroomAwareSingleMPCCycleOrchestrator(
        boundary or make_boundary(),
        CountingPlanConstructor(),
        CountingExtractor(),
        MinimalDecisionTranslator(),
    )


def test_rolling_cheap_charge_and_final_decision_preserve_provenance() -> None:
    source = make_input(
        (
            point(1, pv=0.0, load=1.0, price=0.3),
            point(2, pv=3.0, load=0.0, price=None),
            point(3, pv=2.263157894736842, load=0.0, price=None),
        )
    )
    result = make_orchestrator().run_cycle(source)
    output = result.rolling_headroom_optimization_output

    assert output.source_input is result.physically_aware_input
    assert output.physical_output.source_input is result.physically_aware_input
    assert (
        output.physical_output.candidate_output
        is output.candidate_planning_result.final_output
    )
    assert result.decision.requested_power_kw == pytest.approx(0.5263157894736842)
    assert (
        CountingPlanConstructor.received_solution
        is output.physical_output.final_output.solution
    )


def test_current_opportunity_empty_opportunity_and_pv_surplus_remain_distinct() -> None:
    current = make_orchestrator().run_cycle(
        make_input((point(0, pv=3.0, load=0.0, price=None),), soc=0.2)
    )
    empty = make_orchestrator().run_cycle(
        make_input((point(0, pv=0.0, load=1.0, price=0.3),))
    )
    assert (
        current.rolling_headroom_optimization_output.rolling_headroom_requirement.opportunity_window.steps[
            0
        ].source_index
        == 0
    )
    assert (
        empty.rolling_headroom_optimization_output.rolling_headroom_requirement.selected_forecast_horizon.points
        == ()
    )
    assert current.decision.requested_power_kw == 3.0
    assert empty.decision.requested_power_kw == 3.0


def test_pv_surplus_and_soc_physical_revision_drive_only_final_plan() -> None:
    result = make_orchestrator().run_cycle(
        make_input((point(0, pv=6.0, load=0.0, price=None),), soc=0.98)
    )
    physical = result.rolling_headroom_optimization_output.physical_output
    assert physical.candidate_output.solution.steps[0].requested_power_kw == 6.0
    assert physical.final_output.solution.steps[0].requested_power_kw == pytest.approx(
        0.21052631578947364
    )
    assert result.decision.requested_power_kw == pytest.approx(0.21052631578947364)
    assert physical.revision.steps[0].reasons == ("charge_power_limit", "max_soc_limit")


def test_all_outer_and_physical_view_identities_and_explanation_are_exact() -> None:
    source = make_input((point(0, pv=6.0, load=0.0, price=None),), soc=0.2)
    result = make_orchestrator().run_cycle(source)
    output = result.rolling_headroom_optimization_output
    view = result.physical_cycle_view

    assert result.problem.context is source.cycle_input.context
    assert result.problem.forecast_horizon is source.cycle_input.forecast_horizon
    assert result.problem.objectives is source.cycle_input.objectives
    assert result.battery_input.battery_state is source.battery_state
    assert result.battery_input.battery_model is source.battery_model
    assert view.source_input is result.source_input
    assert view.problem is result.problem
    assert view.battery_input is result.battery_input
    assert view.physically_aware_input is result.physically_aware_input
    assert view.optimization_output is output.physical_output
    assert view.control_plan is result.control_plan
    assert view.current_action is result.current_action
    assert view.decision is result.decision
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        MPCDecisionExplanationInput(view)
    )
    assert explanation.candidate_requested_power_kw == 6.0
    assert explanation.final_requested_power_kw == 3.0


def test_rolling_boundary_and_downstream_boundaries_execute_once() -> None:
    result = make_orchestrator(CountingRollingBoundary(make_boundary())).run_cycle(
        make_input((point(0, pv=0.0, load=2.0, price=0.9),), soc=0.8)
    )
    assert (
        CountingRollingBoundary.calls,
        CountingPlanConstructor.calls,
        CountingExtractor.calls,
        MinimalDecisionTranslator.calls,
    ) == (1, 1, 1, 1)
    assert (
        result.physical_cycle_view.optimization_output
        is result.rolling_headroom_optimization_output.physical_output
    )


def test_unsupported_objective_preserves_existing_extractor_failure() -> None:
    with pytest.raises(ValueError, match="at least one step"):
        make_orchestrator().run_cycle(
            make_input(
                (point(0, pv=0.0, load=1.0, price=0.3),),
                objectives=(OptimizationObjective("unsupported", "minimize"),),
            )
        )
    assert CountingPlanConstructor.calls == 1
    assert CountingExtractor.calls == 1
    assert MinimalDecisionTranslator.calls == 0


def test_contract_is_frozen_slotted_and_boundary_is_abstract() -> None:
    result = make_orchestrator().run_cycle(
        make_input((point(0, pv=0.0, load=2.0, price=0.9),))
    )
    assert [field.name for field in fields(RollingHeadroomAwareMPCCycleResult)] == [
        "source_input",
        "problem",
        "battery_input",
        "physically_aware_input",
        "rolling_headroom_optimization_output",
        "control_plan",
        "current_action",
        "decision",
        "physical_cycle_view",
    ]
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).decision = result.decision
    assert issubclass(RollingHeadroomAwareMPCCycleBoundary, ABC)
    assert inspect.isabstract(RollingHeadroomAwareMPCCycleBoundary)
    assert RollingHeadroomAwareMPCCycleBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, RollingHeadroomAwareMPCCycleBoundary)()
    assert get_type_hints(RollingHeadroomAwareMPCCycleBoundary.run_cycle) == {
        "cycle_input": PhysicallyAwareMPCCycleInput,
        "return": RollingHeadroomAwareMPCCycleResult,
    }


def test_module_is_composition_only_and_public_api_is_exported() -> None:
    module_path = Path(ems_strategy.__file__).parent / "mpc_rolling_headroom_aware.py"
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(module_path.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom)
    }
    for forbidden in (
        "optimization.net_load_aware_baseline",
        "optimization.pv_headroom",
        "optimization.rolling_pv_headroom",
        "optimization.headroom_aware_candidate_planning",
        "optimization.physically_aware_baseline",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
    for name in (
        "RollingHeadroomAwareMPCCycleBoundary",
        "RollingHeadroomAwareMPCCycleResult",
        "RollingHeadroomAwareSingleMPCCycleOrchestrator",
    ):
        assert name in ems_strategy.__all__
