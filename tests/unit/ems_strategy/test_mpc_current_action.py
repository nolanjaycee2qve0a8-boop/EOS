"""Tests for explicit MPC current-action extraction and translation seams."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast, get_type_hints

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
    MPCCurrentAction,
    MPCCurrentActionExtractionBoundary,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    OptimizationControlPlan,
    OptimizationControlStep,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationProblem,
    OptimizationResult,
)


class MinimalCurrentActionExtractor(MPCCurrentActionExtractionBoundary):
    """Test-only extractor that explicitly selects the first plan step."""

    __slots__ = ()

    def extract(self, plan: OptimizationControlPlan) -> MPCCurrentAction:
        if not isinstance(plan, OptimizationControlPlan):
            raise TypeError("plan must be an OptimizationControlPlan")
        if not plan.steps:
            raise ValueError("plan must contain a step")
        return MPCCurrentAction(plan, plan.steps[0])


class MinimalDecisionTranslator(MPCDecisionTranslationBoundary):
    """Test-only translation of exactly one selected action to EMSDecision."""

    __slots__ = ()

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        if not isinstance(translation, MPCDecisionTranslationInput):
            raise TypeError("translation must be an MPCDecisionTranslationInput")
        selected_step = translation.current_action.selected_step
        context = (
            translation.current_action.source_plan.source_result.source_problem.context
        )
        return EMSDecision(
            source_context=context,
            source_strategy=translation.source_strategy,
            intent=selected_step.intent,
            requested_power_kw=selected_step.requested_power_kw,
        )


def make_result() -> OptimizationResult:
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
    horizon = ForecastHorizon(
        (
            ForecastPoint(
                datetime(2026, 1, 1, 1, tzinfo=UTC),
                pv_power_kw=1.0,
                load_power_kw=2.0,
            ),
        )
    )
    problem = OptimizationProblem(
        context,
        horizon,
        OptimizationObjectiveCollection((OptimizationObjective("cost", "minimize"),)),
    )
    return OptimizationResult(problem, "optimal")


def make_plan() -> tuple[
    OptimizationControlPlan,
    OptimizationControlStep,
    OptimizationControlStep,
]:
    first = OptimizationControlStep(
        datetime(2026, 1, 1, 1, tzinfo=UTC),
        DecisionIntent("charge"),
        1.0,
    )
    future = OptimizationControlStep(
        datetime(2026, 1, 1, 2, tzinfo=UTC),
        DecisionIntent("discharge"),
        2.0,
    )
    return OptimizationControlPlan(make_result(), (first, future)), first, future


def test_current_action_is_frozen_slotted_and_preserves_exact_plan_step_identity() -> (
    None
):
    plan, first, _ = make_plan()
    action = MPCCurrentAction(plan, first)

    assert [field.name for field in fields(MPCCurrentAction)] == [
        "source_plan",
        "selected_step",
    ]
    assert action.source_plan is plan
    assert action.selected_step is first
    assert not hasattr(action, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, action).selected_step = first


def test_current_action_rejects_reconstructed_or_foreign_step_identity() -> None:
    plan, first, _ = make_plan()
    reconstructed = OptimizationControlStep(
        first.timestamp,
        DecisionIntent(first.intent.action),
        first.requested_power_kw,
    )
    foreign_step = OptimizationControlStep(
        datetime(2026, 1, 1, 3, tzinfo=UTC),
        DecisionIntent("charge"),
        1.0,
    )

    with pytest.raises(ValueError, match="identity"):
        MPCCurrentAction(plan, reconstructed)
    with pytest.raises(ValueError, match="identity"):
        MPCCurrentAction(plan, foreign_step)
    with pytest.raises(TypeError, match="selected_step"):
        MPCCurrentAction(plan, cast(Any, None))


def test_first_step_extractor_selects_only_first_caller_ordered_step() -> None:
    plan, first, future = make_plan()
    extractor = FirstStepMPCCurrentActionExtractor()

    action = extractor.extract(plan)

    assert action.source_plan is plan
    assert action.selected_step is first
    assert action.selected_step is not future
    assert plan.steps[0] is first
    assert plan.steps[1] is future


def test_extractor_rejects_empty_plan_without_progression_or_mutation() -> None:
    empty_plan = OptimizationControlPlan(make_result(), ())

    with pytest.raises(ValueError, match="at least one"):
        FirstStepMPCCurrentActionExtractor().extract(empty_plan)
    assert empty_plan.steps == ()


def test_extraction_boundary_is_abstract_empty_slotted_and_minimal_fake_works() -> None:
    signature = inspect.signature(MPCCurrentActionExtractionBoundary.extract)
    hints = get_type_hints(MPCCurrentActionExtractionBoundary.extract)
    plan, first, _ = make_plan()

    assert issubclass(MPCCurrentActionExtractionBoundary, ABC)
    assert inspect.isabstract(MPCCurrentActionExtractionBoundary)
    assert MPCCurrentActionExtractionBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "plan"]
    assert hints == {"plan": OptimizationControlPlan, "return": MPCCurrentAction}
    with pytest.raises(TypeError):
        MPCCurrentActionExtractionBoundary()  # type: ignore[abstract]

    action = MinimalCurrentActionExtractor().extract(plan)
    assert action.selected_step is first
    assert MinimalCurrentActionExtractor.__slots__ == ()


def test_translation_preserves_context_descriptor_and_step_semantics() -> None:
    plan, first, _ = make_plan()
    current_action = MPCCurrentAction(plan, first)
    descriptor = EMSStrategyDescriptor("mpc", "1.0")
    translation = MPCDecisionTranslationInput(current_action, descriptor)

    decision = MinimalDecisionTranslator().translate(translation)

    assert [field.name for field in fields(MPCDecisionTranslationInput)] == [
        "current_action",
        "source_strategy",
    ]
    assert translation.current_action is current_action
    assert translation.source_strategy is descriptor
    assert decision.source_context is plan.source_result.source_problem.context
    assert decision.source_strategy is descriptor
    assert decision.intent is first.intent
    assert decision.requested_power_kw == first.requested_power_kw


def test_translation_boundary_is_abstract_stateless_and_rejects_invalid_input() -> None:
    signature = inspect.signature(MPCDecisionTranslationBoundary.translate)
    hints = get_type_hints(MPCDecisionTranslationBoundary.translate)

    assert issubclass(MPCDecisionTranslationBoundary, ABC)
    assert inspect.isabstract(MPCDecisionTranslationBoundary)
    assert MPCDecisionTranslationBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "translation"]
    assert hints == {"translation": MPCDecisionTranslationInput, "return": EMSDecision}
    with pytest.raises(TypeError):
        MPCDecisionTranslationBoundary()  # type: ignore[abstract]
    with pytest.raises(TypeError, match="translation"):
        MinimalDecisionTranslator().translate(cast(Any, None))
    assert not hasattr(MinimalDecisionTranslator(), "__dict__")
    assert not hasattr(MinimalDecisionTranslator(), "cache")


def test_mpc_current_action_module_has_no_solver_or_execution_dependency() -> None:
    module_path = Path(ems_strategy.__file__).parent / "mpc_current_action.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "ems_strategy.decision",
        "ems_strategy.descriptor",
        "optimization",
    }
    for forbidden_root in (
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


def test_public_api_exports_current_action_contracts() -> None:
    for name in (
        "FirstStepMPCCurrentActionExtractor",
        "MPCCurrentAction",
        "MPCCurrentActionExtractionBoundary",
        "MPCDecisionTranslationBoundary",
        "MPCDecisionTranslationInput",
    ):
        assert name in ems_strategy.__all__
