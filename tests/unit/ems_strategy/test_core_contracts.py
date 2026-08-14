"""Tests for immutable Phase 9 EMS Strategy core contracts."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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
from ems_strategy import EMSContext, EMSDecision, EMSStrategyDescriptor
from kernel.decision import DecisionContext
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)


def make_source_context() -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=4.0,
        load_power_kw=1.0,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )


def make_composition() -> tuple[
    ObjectiveCapabilityActivationComposition,
    CapabilityDescriptor,
]:
    required = CapabilityDescriptor("self-consumption", "Required capability.")
    available = CapabilityDescriptor("self-consumption", "Available capability.")
    required_collection = RequiredCapabilityCollection((required,))
    available_collection = AvailableCapabilityCollection((available,))
    matches = CapabilityMatchCollection(
        required_collection,
        available_collection,
        (CapabilityMatch(required, available),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (available,), ())
    objective = ObjectiveDescriptor("self-consumption", "Use local PV energy.")
    return ObjectiveCapabilityActivationComposition(objective, active), available


def make_ems_context() -> tuple[EMSContext, DecisionContext, CapabilityDescriptor]:
    source_context = make_source_context()
    composition, capability = make_composition()
    return (
        EMSContext(source_context, composition, capability),
        source_context,
        capability,
    )


def test_strategy_descriptor_is_immutable_slotted_identity_only() -> None:
    descriptor = EMSStrategyDescriptor("self-consumption", "1.0")

    assert [field.name for field in fields(EMSStrategyDescriptor)] == [
        "name",
        "version",
    ]
    assert EMSStrategyDescriptor.__slots__ == ("name", "version")
    assert not hasattr(descriptor, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, descriptor).name = "changed"


@pytest.mark.parametrize("field_name", ["name", "version"])
@pytest.mark.parametrize("value", ["", "   "])
def test_strategy_descriptor_rejects_empty_identity(
    field_name: str,
    value: str,
) -> None:
    values = {"name": "strategy", "version": "1.0"}
    values[field_name] = value

    with pytest.raises(ValueError, match=field_name):
        EMSStrategyDescriptor(**values)


def test_context_preserves_exact_source_and_capability_provenance() -> None:
    source_context = make_source_context()
    composition, capability = make_composition()

    context = EMSContext(source_context, composition, capability)

    assert context.source_context is source_context
    assert context.objective_composition is composition
    assert context.capability is capability


def test_context_rejects_reconstructed_equal_capability() -> None:
    source_context = make_source_context()
    composition, capability = make_composition()
    reconstructed = CapabilityDescriptor(
        capability.name,
        capability.description,
    )

    assert reconstructed == capability
    assert reconstructed is not capability
    with pytest.raises(ValueError, match="identity"):
        EMSContext(source_context, composition, reconstructed)


def test_context_is_immutable_slotted_and_has_no_mutable_fields() -> None:
    context, _, _ = make_ems_context()

    assert [field.name for field in fields(EMSContext)] == [
        "source_context",
        "objective_composition",
        "capability",
    ]
    assert EMSContext.__slots__ == (
        "source_context",
        "objective_composition",
        "capability",
    )
    assert not hasattr(context, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, context).capability = context.capability


@pytest.mark.parametrize(
    ("action", "requested_power_kw"),
    [("charge", 2.0), ("discharge", 1.5), ("idle", 0.0)],
)
def test_decision_preserves_exact_provenance(
    action: str,
    requested_power_kw: float,
) -> None:
    context, _, _ = make_ems_context()
    strategy = EMSStrategyDescriptor("test", "1.0")
    intent = DecisionIntent(cast(Any, action))

    decision = EMSDecision(context, strategy, intent, requested_power_kw)

    assert decision.source_context is context
    assert decision.source_strategy is strategy
    assert decision.intent is intent
    assert decision.requested_power_kw == requested_power_kw


def test_decision_is_immutable_slotted_and_has_no_mutable_fields() -> None:
    context, _, _ = make_ems_context()
    strategy = EMSStrategyDescriptor("test", "1.0")
    intent = DecisionIntent("charge")
    decision = EMSDecision(context, strategy, intent, 2.0)

    assert [field.name for field in fields(EMSDecision)] == [
        "source_context",
        "source_strategy",
        "intent",
        "requested_power_kw",
    ]
    assert EMSDecision.__slots__ == (
        "source_context",
        "source_strategy",
        "intent",
        "requested_power_kw",
    )
    assert not hasattr(decision, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, decision).requested_power_kw = 3.0


@pytest.mark.parametrize("value", [True, "1", None])
def test_decision_rejects_non_numeric_requested_power(value: object) -> None:
    context, _, _ = make_ems_context()
    strategy = EMSStrategyDescriptor("test", "1.0")

    with pytest.raises(TypeError, match="requested_power_kw"):
        EMSDecision(context, strategy, DecisionIntent("charge"), cast(Any, value))


@pytest.mark.parametrize("value", [-1.0, float("inf"), float("-inf"), float("nan")])
def test_decision_rejects_invalid_requested_power(value: float) -> None:
    context, _, _ = make_ems_context()
    strategy = EMSStrategyDescriptor("test", "1.0")

    with pytest.raises(ValueError, match="requested_power_kw"):
        EMSDecision(context, strategy, DecisionIntent("charge"), value)


@pytest.mark.parametrize(
    ("intent", "requested_power_kw"),
    [
        (DecisionIntent("idle"), 1.0),
        (DecisionIntent("charge"), 0.0),
        (DecisionIntent("discharge"), 0.0),
    ],
)
def test_decision_rejects_action_power_mismatch(
    intent: DecisionIntent,
    requested_power_kw: float,
) -> None:
    context, _, _ = make_ems_context()
    strategy = EMSStrategyDescriptor("test", "1.0")

    with pytest.raises(ValueError):
        EMSDecision(context, strategy, intent, requested_power_kw)


def test_core_contracts_reject_invalid_reference_types() -> None:
    source_context = make_source_context()
    composition, capability = make_composition()
    context = EMSContext(source_context, composition, capability)
    strategy = EMSStrategyDescriptor("test", "1.0")
    intent = DecisionIntent("idle")

    with pytest.raises(TypeError, match="source_context"):
        EMSContext(cast(Any, None), composition, capability)
    with pytest.raises(TypeError, match="objective_composition"):
        EMSContext(source_context, cast(Any, None), capability)
    with pytest.raises(TypeError, match="capability"):
        EMSContext(source_context, composition, cast(Any, None))
    with pytest.raises(TypeError, match="source_context"):
        EMSDecision(cast(Any, None), strategy, intent, 0.0)
    with pytest.raises(TypeError, match="source_strategy"):
        EMSDecision(context, cast(Any, None), intent, 0.0)
    with pytest.raises(TypeError, match="intent"):
        EMSDecision(context, strategy, cast(Any, None), 0.0)


def test_public_api_exports_strategy_contracts() -> None:
    assert ems_strategy.__all__ == [
        "EXPLAINABLE_MPC_DECISION_CSV_COLUMNS",
        "ActuationHandoffBoundary",
        "ActuationHandoffResult",
        "BatteryOperatingEnvelope",
        "BatteryOperatingEnvelopeBoundary",
        "BatteryOperatingEnvelopeFeasibility",
        "DecisionProvenance",
        "DeterministicExplainableMPCDecisionCSVFileExporter",
        "DeterministicExplainableMPCDecisionCSVRowMapper",
        "DeterministicExplainableMPCDecisionCSVSerializer",
        "DeterministicExplainableMPCDecisionJournalRecordBuilder",
        "DeterministicMPCDecisionExplanationBuilder",
        "DeterministicMPCDecisionExplanationFormatter",
        "EMSContext",
        "EMSDecision",
        "EMSStrategyBoundary",
        "EMSStrategyDescriptor",
        "ExplainableMPCDecisionCSVFileExportInput",
        "ExplainableMPCDecisionCSVFileExportResult",
        "ExplainableMPCDecisionCSVFileExporterBoundary",
        "ExplainableMPCDecisionCSVRow",
        "ExplainableMPCDecisionCSVRowMappingBoundary",
        "ExplainableMPCDecisionCSVRowMappingInput",
        "ExplainableMPCDecisionCSVSerializerBoundary",
        "ExplainableMPCDecisionJournalRecord",
        "ExplainableMPCDecisionJournalRecordBoundary",
        "ExplainableMPCDecisionJournalRecordInput",
        "FeasibilityBoundary",
        "FeasibleDecision",
        "FirstStepMPCCurrentActionExtractor",
        "FormattedMPCDecisionExplanation",
        "HeadroomAwareMPCCycleBoundary",
        "HeadroomAwareMPCCycleResult",
        "HeadroomAwareSingleMPCCycleOrchestrator",
        "MPCConfiguration",
        "MPCCurrentAction",
        "MPCCurrentActionExtractionBoundary",
        "MPCCycleBoundary",
        "MPCCycleInput",
        "MPCCycleResult",
        "MPCDecisionExplanation",
        "MPCDecisionExplanationBoundary",
        "MPCDecisionExplanationFormatInput",
        "MPCDecisionExplanationFormatterBoundary",
        "MPCDecisionExplanationInput",
        "MPCDecisionExplanationLocale",
        "MPCDecisionPhysicalExplanation",
        "MPCDecisionTranslationBoundary",
        "MPCDecisionTranslationInput",
        "MPCSolutionCycleBoundary",
        "MPCSolutionCycleResult",
        "MPCStrategyBoundary",
        "MPCStrategyInput",
        "PeakShavingConfiguration",
        "PeakShavingStrategy",
        "PhysicallyAwareMPCCycleBoundary",
        "PhysicallyAwareMPCCycleInput",
        "PhysicallyAwareMPCCycleResult",
        "PhysicallyAwareSingleMPCCycleOrchestrator",
        "RollingHeadroomAwareMPCCycleBoundary",
        "RollingHeadroomAwareMPCCycleResult",
        "RollingHeadroomAwareSingleMPCCycleOrchestrator",
        "SelfConsumptionStrategy",
        "SingleMPCCycleOrchestrator",
        "SolutionAwareSingleMPCCycleOrchestrator",
        "StrategyCoordinator",
        "StrategyCoordinatorConfiguration",
        "TOUStrategy",
        "TOUStrategyConfiguration",
        "ZeroExportBoundary",
        "ZeroExportFeasibility",
    ]
    assert ems_strategy.EMSContext is EMSContext
    assert ems_strategy.EMSDecision is EMSDecision
    assert ems_strategy.EMSStrategyDescriptor is EMSStrategyDescriptor


def test_package_has_no_simulator_runtime_device_or_command_dependency() -> None:
    forbidden_roots = {
        "ems_simulator",
        "simulator",
        "runtime",
        "device",
        "dispatch",
        "execution",
    }
    package_path = Path(ems_strategy.__file__).parent

    for module_path in package_path.glob("*.py"):
        if module_path.name == "handoff.py":
            continue
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert all(
            module is None or module.split(".", maxsplit=1)[0] not in forbidden_roots
            for module in imported_modules
        )
        source = inspect.getsource(
            __import__(
                f"ems_strategy.{module_path.stem}",
                fromlist=[module_path.stem],
            )
        )
        for forbidden_name in (
            "BatterySimulationActuation",
            "Command",
            "Simulator",
        ):
            assert forbidden_name not in source
        if module_path.name not in {
            "boundary.py",
            "battery_operating_envelope.py",
            "feasibility.py",
            "peak_shaving.py",
            "self_consumption.py",
            "coordinator.py",
            "mpc.py",
            "tou.py",
            "zero_export.py",
        }:
            assert "evaluate(" not in source
