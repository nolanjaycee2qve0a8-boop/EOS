"""Tests for read-only explanation of one completed physical MPC decision."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import ems_strategy
from ems_strategy import (
    DeterministicMPCDecisionExplanationBuilder,
    MPCDecisionExplanation,
    MPCDecisionExplanationBoundary,
    MPCDecisionExplanationInput,
)
from optimization import BatteryOptimizationModel
from tests.unit.ems_strategy.test_physically_aware_mpc_cycle import (
    make_orchestrator,
    make_physical_input,
    make_real_physical_optimizer,
)


def test_contracts_are_frozen_slotted_and_preserve_exact_cycle_identity() -> None:
    cycle_result = make_orchestrator().run_cycle(make_physical_input())
    explanation_input = MPCDecisionExplanationInput(cycle_result)
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        explanation_input
    )

    assert [field.name for field in fields(MPCDecisionExplanationInput)] == [
        "cycle_result"
    ]
    assert [field.name for field in fields(MPCDecisionExplanation)] == [
        "source_input",
        "selected_step_index",
        "decision",
        "candidate_action",
        "candidate_requested_power_kw",
        "final_action",
        "final_requested_power_kw",
        "revision_applied",
        "physical_explanation",
    ]
    assert explanation.source_input is explanation_input
    assert explanation.source_input.cycle_result is cycle_result
    assert explanation.decision is cycle_result.decision
    assert not hasattr(explanation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, explanation).decision = cycle_result.decision


def test_mapping_uses_exact_plan_index_and_retains_power_revision_evidence() -> None:
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        MPCDecisionExplanationInput(
            make_orchestrator().run_cycle(make_physical_input(soc=0.8))
        )
    )
    physical = explanation.physical_explanation

    assert explanation.selected_step_index == 0
    assert explanation.candidate_action.action == "discharge"
    assert explanation.candidate_requested_power_kw == 6.0
    assert explanation.final_requested_power_kw == 4.0
    assert explanation.decision.requested_power_kw == 4.0
    assert explanation.revision_applied is True
    assert physical.revision_reasons is physical.revision_step.reasons
    assert physical.revision_reasons == ("discharge_power_limit",)
    assert physical.candidate_power_violation_kinds == ("discharge_power_above_max",)
    assert physical.candidate_soc_violation_kinds == ()
    assert physical.final_battery_horizon_feasible is True


def test_soc_limited_explanation_reads_projection_evidence_without_recomputation() -> (
    None
):
    result = make_orchestrator().run_cycle(
        make_physical_input(
            soc=0.2,
            model=BatteryOptimizationModel(10.0, 0.1, 0.9, 10.0, 10.0, 1.0, 0.9),
        )
    )
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        MPCDecisionExplanationInput(result)
    )
    physical = explanation.physical_explanation
    candidate_projection = result.optimization_output.candidate_projection.steps[0]
    final_projection = result.optimization_output.final_projection.steps[0]

    assert "min_soc_limit" in physical.revision_reasons
    assert physical.candidate_soc_violation_kinds == ("below_min_soc",)
    assert (
        explanation.final_requested_power_kw < explanation.candidate_requested_power_kw
    )
    assert (
        physical.candidate_starting_soc_fraction
        == candidate_projection.starting_soc_fraction
    )
    assert (
        physical.candidate_ending_soc_fraction
        == candidate_projection.ending_soc_fraction
    )
    assert (
        physical.final_starting_soc_fraction == final_projection.starting_soc_fraction
    )
    assert physical.final_ending_soc_fraction == final_projection.ending_soc_fraction
    assert physical.final_soc_feasible is True


def test_no_revision_keeps_distinct_exact_artifacts_and_empty_reasons() -> None:
    result = make_orchestrator(make_real_physical_optimizer(2.0)).run_cycle(
        make_physical_input(
            model=BatteryOptimizationModel(10.0, 0.1, 0.9, 10.0, 10.0, 1.0, 1.0),
        )
    )
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        MPCDecisionExplanationInput(result)
    )

    assert explanation.revision_applied is False
    assert (
        explanation.candidate_requested_power_kw == explanation.final_requested_power_kw
    )
    assert (
        explanation.physical_explanation.candidate_step
        is not explanation.physical_explanation.final_step
    )
    assert explanation.physical_explanation.revision_reasons == ()


def test_boundary_is_abstract_slotted_and_builder_has_no_execution_dependency() -> None:
    signature = inspect.signature(MPCDecisionExplanationBoundary.explain)
    hints = get_type_hints(MPCDecisionExplanationBoundary.explain)
    module_path = Path(ems_strategy.__file__).parent / "mpc_decision_explanation.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert issubclass(MPCDecisionExplanationBoundary, ABC)
    assert inspect.isabstract(MPCDecisionExplanationBoundary)
    assert MPCDecisionExplanationBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "explanation_input"]
    assert hints == {
        "explanation_input": MPCDecisionExplanationInput,
        "return": MPCDecisionExplanation,
    }
    with pytest.raises(TypeError):
        MPCDecisionExplanationBoundary()  # type: ignore[abstract]
    assert not hasattr(DeterministicMPCDecisionExplanationBuilder(), "__dict__")
    for forbidden in ("ems_simulator", "runtime", "device", "execution", "scipy"):
        assert forbidden not in imported_modules


def test_public_api_exports_explanation_contracts() -> None:
    for name in (
        "MPCDecisionExplanationInput",
        "MPCDecisionPhysicalExplanation",
        "MPCDecisionExplanation",
        "MPCDecisionExplanationBoundary",
        "DeterministicMPCDecisionExplanationBuilder",
    ):
        assert name in ems_strategy.__all__
