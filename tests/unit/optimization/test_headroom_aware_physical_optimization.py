"""Tests for TASK-136 headroom-aware physical optimization composition."""

import ast
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast

import pytest

import optimization
from forecast import ForecastPoint
from optimization import (
    BatteryOptimizationInput,
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
    ExplicitCandidatePhysicalRevisionBoundary,
    ExplicitCandidatePhysicalRevisionInput,
    HeadroomAwareCandidatePlanningBoundary,
    HeadroomAwareCandidatePlanningInput,
    HeadroomAwareCandidatePlanningResult,
    HeadroomAwarePhysicalOptimizationBoundary,
    HeadroomAwarePhysicalOptimizationSolveOutput,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareOptimizationSolveOutput,
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
)
from tests.unit.optimization.test_price_aware_baseline_optimizer import (
    make_problem,
    point,
)


def make_input(
    points: tuple[ForecastPoint, ...],
    *,
    soc: float = 0.45,
    model: BatteryOptimizationModel | None = None,
    objectives: tuple[OptimizationObjective, ...] | None = None,
) -> PhysicallyAwareBaselineOptimizationInput:
    problem = make_problem(
        points,
        objectives
        if objectives is not None
        else (OptimizationObjective("energy_cost", "minimize"),),
    )
    return PhysicallyAwareBaselineOptimizationInput(
        BatteryOptimizationInput(
            problem,
            BatteryOptimizationState(soc),
            model or BatteryOptimizationModel(10.0, 0.2, 1.0, 3.0, 3.0, 0.95, 0.95),
        ),
        3600.0,
    )


def make_optimizer() -> DeterministicHeadroomAwarePhysicalOptimizer:
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


class TrackingHeadroomCalculator(PVHeadroomRequirementBoundary):
    """Test-only wrapper proving one exact dependency invocation."""

    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: PVHeadroomRequirementBoundary) -> None:
        self.delegate = delegate
        self.calls = 0
        self.received: object | None = None

    def calculate(
        self, requirement_input: PVHeadroomRequirementInput
    ) -> PVHeadroomRequirement:
        self.calls += 1
        self.received = requirement_input
        return self.delegate.calculate(requirement_input)


class TrackingCandidatePlanner(HeadroomAwareCandidatePlanningBoundary):
    """Test-only wrapper proving candidate planning is not re-run."""

    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: HeadroomAwareCandidatePlanningBoundary) -> None:
        self.delegate = delegate
        self.calls = 0
        self.received: object | None = None

    def plan(
        self, planning_input: HeadroomAwareCandidatePlanningInput
    ) -> HeadroomAwareCandidatePlanningResult:
        self.calls += 1
        self.received = planning_input
        return self.delegate.plan(planning_input)


class TrackingPhysicalReviser(ExplicitCandidatePhysicalRevisionBoundary):
    """Test-only wrapper proving one supplied candidate is revised once."""

    __slots__ = ("calls", "delegate", "received")

    def __init__(self, delegate: ExplicitCandidatePhysicalRevisionBoundary) -> None:
        self.delegate = delegate
        self.calls = 0
        self.received: object | None = None

    def revise(
        self, revision_input: ExplicitCandidatePhysicalRevisionInput
    ) -> PhysicallyAwareOptimizationSolveOutput:
        self.calls += 1
        self.received = revision_input
        return self.delegate.revise(revision_input)


def test_contract_is_frozen_slotted_and_boundary_is_abstract() -> None:
    output = make_optimizer().solve_headroom_aware(
        make_input((point(1, 0.3, pv=0.0, load=1.0),))
    )

    assert [
        field.name for field in fields(HeadroomAwarePhysicalOptimizationSolveOutput)
    ] == [
        "source_input",
        "headroom_requirement",
        "candidate_planning_result",
        "physical_output",
    ]
    assert not hasattr(output, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, output).source_input = output.source_input
    with pytest.raises(TypeError):
        cast(Any, HeadroomAwarePhysicalOptimizationBoundary)()
    assert DeterministicHeadroomAwarePhysicalOptimizer.__slots__ == (
        "headroom_calculator",
        "candidate_planner",
        "explicit_physical_reviser",
    )


def test_cheap_grid_charge_is_reservation_adjusted_then_physically_evidenced() -> None:
    source = make_input(
        (
            point(1, 0.3, pv=0.0, load=1.0),
            point(2, None, pv=3.0, load=0.0),
            point(3, None, pv=2.263157894736842, load=0.0),
        )
    )
    output = make_optimizer().solve_headroom_aware(source)

    planning = output.candidate_planning_result
    candidate = planning.source_candidate_output.solution.steps[0]
    headroom_final = planning.final_output.solution.steps[0]
    assert output.source_input is source
    assert output.headroom_requirement.source_input.forecast_horizon is (
        source.battery_input.problem.forecast_horizon
    )
    assert output.headroom_requirement.source_input.battery_model is (
        source.battery_input.battery_model
    )
    assert planning.source_input.battery_input is source.battery_input
    assert planning.source_input.headroom_requirement is output.headroom_requirement
    assert candidate.requested_power_kw == 3.0
    assert planning.grid_charge_reservation is not None
    assert headroom_final.requested_power_kw == pytest.approx(0.5263157894736842)
    assert output.physical_output.candidate_output is planning.final_output
    assert output.physical_output.revision.source_candidate_solution is (
        planning.final_output.solution
    )


def test_at_headroom_target_makes_cheap_grid_charge_idle_without_physical_reason() -> (
    None
):
    source = make_input(
        (
            point(1, 0.3, pv=0.0, load=1.0),
            point(2, None, pv=3.0, load=0.0),
            point(3, None, pv=2.263157894736842, load=0.0),
        ),
        soc=0.5,
    )
    output = make_optimizer().solve_headroom_aware(source)

    planning = output.candidate_planning_result
    assert planning.grid_charge_reservation is not None
    assert planning.grid_charge_reservation.allowed_grid_charge_power_kw == 0.0
    assert planning.final_output.solution.steps[0].intent.action == "idle"
    assert output.physical_output.final_output.solution.steps[0].intent.action == "idle"
    assert output.physical_output.revision.steps[0].reasons == ()


def test_pv_surplus_bypasses_reservation_then_physical_power_limit_applies() -> None:
    source = make_input(
        (point(1, 0.3, pv=6.0, load=0.0),),
        soc=0.2,
    )
    output = make_optimizer().solve_headroom_aware(source)

    planning = output.candidate_planning_result
    assert planning.grid_charge_reservation is None
    assert planning.final_output.solution.steps[0].requested_power_kw == 6.0
    final = output.physical_output.final_output.solution.steps[0]
    assert final.intent.action == "charge"
    assert final.requested_power_kw == 3.0
    assert output.physical_output.revision.steps[0].reasons == ("charge_power_limit",)


def test_high_price_discharge_remains_candidate_input_to_physical_revision() -> None:
    source = make_input((point(1, 0.9, pv=0.0, load=2.0),), soc=0.8)
    output = make_optimizer().solve_headroom_aware(source)

    planning = output.candidate_planning_result
    assert planning.grid_charge_reservation is None
    assert planning.final_output.solution.steps[0].intent.action == "discharge"
    assert planning.final_output.solution.steps[0].requested_power_kw == 2.0
    assert output.physical_output.candidate_output is planning.final_output
    assert (
        output.physical_output.final_output.solution.steps[0].intent.action
        == "discharge"
    )


def test_unsupported_candidate_remains_empty_and_unavailable_through_composition() -> (
    None
):
    source = make_input(
        (point(1, 0.3, pv=0.0, load=1.0),),
        objectives=(OptimizationObjective("peak", "minimize"),),
    )
    output = make_optimizer().solve_headroom_aware(source)

    assert output.candidate_planning_result.source_candidate_output.result.outcome == (
        "unavailable"
    )
    assert output.candidate_planning_result.final_output.solution.steps == ()
    assert output.physical_output.candidate_output is (
        output.candidate_planning_result.final_output
    )
    assert output.physical_output.final_output.solution.steps == ()


def test_dependencies_execute_once_with_exact_composed_provenance() -> None:
    headroom = TrackingHeadroomCalculator(
        DeterministicPVHeadroomRequirementCalculator()
    )
    planner = TrackingCandidatePlanner(
        DeterministicHeadroomAwareCandidatePlanner(
            NetLoadAwareBaselineOptimizer(
                NetLoadAwareBaselineOptimizationConfiguration(0.3, 0.8, 3.0)
            ),
            DeterministicHeadroomAwareGridChargeReservationCalculator(),
        )
    )
    reviser = TrackingPhysicalReviser(
        DeterministicExplicitCandidatePhysicalReviser(
            DeterministicBatterySOCHorizonProjector(),
            DeterministicBatterySOCHorizonConstraintEvaluator(),
            DeterministicBatteryPowerHorizonConstraintEvaluator(),
            DeterministicBatteryHorizonConstraintAggregator(),
        )
    )
    source = make_input((point(1, 0.9, pv=0.0, load=2.0),), soc=0.8)
    output = DeterministicHeadroomAwarePhysicalOptimizer(
        headroom, planner, reviser
    ).solve_headroom_aware(source)

    assert (headroom.calls, planner.calls, reviser.calls) == (1, 1, 1)
    assert cast(Any, headroom.received).forecast_horizon is (
        source.battery_input.problem.forecast_horizon
    )
    assert (
        cast(Any, planner.received).headroom_requirement is output.headroom_requirement
    )
    assert cast(Any, reviser.received).candidate_output is (
        output.candidate_planning_result.final_output
    )
    assert output.physical_output.candidate_output is (
        output.candidate_planning_result.final_output
    )


def test_public_api_and_module_dependencies_remain_composition_only() -> None:
    for name in (
        "HeadroomAwarePhysicalOptimizationSolveOutput",
        "HeadroomAwarePhysicalOptimizationBoundary",
        "DeterministicHeadroomAwarePhysicalOptimizer",
    ):
        assert name in optimization.__all__

    module_path = (
        Path(optimization.__file__).parent / "headroom_aware_physical_optimization.py"
    )
    source = module_path.read_text(encoding="utf-8")
    imported_modules = {
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }
    for forbidden in (
        "optimization.net_load_aware_baseline",
        "optimization.grid_charge_reservation",
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "command",
    ):
        assert forbidden not in imported_modules
