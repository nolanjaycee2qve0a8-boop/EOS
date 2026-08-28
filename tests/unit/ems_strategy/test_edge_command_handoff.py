"""Public P0.5 Feasibility-to-Edge command handoff regressions."""

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import ems_strategy
import ems_strategy.edge_command_handoff as edge_command_handoff_module
from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import DecisionIntent
from edge_runtime import OperatingMode, PowerCommand
from ems_strategy import (
    DecisionProvenance,
    DeterministicEdgeCommandHandoff,
    EdgeCommandHandoffBoundary,
    EdgeCommandHandoffResult,
    EdgeCommandMetadata,
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    FeasibleDecision,
)
from ems_strategy.mpc_current_action import MPCCurrentAction
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor

NOW = datetime(2032, 1, 1, tzinfo=UTC)


def _feasible(
    source_action: str = "charge",
    source_power_kw: float = 3.0,
    approved_action: str | None = None,
    approved_power_kw: float | None = None,
) -> FeasibleDecision:
    source_context = DecisionContext(
        timestamp=NOW,
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
    capability = CapabilityDescriptor("test", "Test capability.")
    required = RequiredCapabilityCollection((capability,))
    available = AvailableCapabilityCollection((capability,))
    matches = CapabilityMatchCollection(
        required, available, (CapabilityMatch(capability, capability),), ()
    )
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("test", "Test objective."),
        ActiveCapabilityCollection(matches, (capability,), ()),
    )
    context = EMSContext(source_context, composition, capability)
    strategy = EMSStrategyDescriptor("test-strategy", "1.0")
    decision = EMSDecision(
        context, strategy, DecisionIntent(cast(Any, source_action)), source_power_kw
    )
    provenance = DecisionProvenance(context, strategy, decision)
    return FeasibleDecision(
        decision,
        provenance,
        DecisionIntent(cast(Any, approved_action or source_action)),
        source_power_kw if approved_power_kw is None else approved_power_kw,
    )


def _metadata(sequence: int = 7) -> EdgeCommandMetadata:
    return EdgeCommandMetadata(
        "caller-command",
        sequence,
        "feasible-provenance",
        NOW,
        NOW,
        NOW + timedelta(minutes=1),
        "approved_feasible_decision",
        "ems-feasibility",
        "caller-correlation",
    )


@pytest.mark.parametrize(
    (
        "source_action",
        "source_power",
        "approved_action",
        "approved_power",
        "power",
        "mode",
    ),
    [
        ("charge", 5.0, "charge", 2.0, 2.0, OperatingMode.NORMAL),
        ("discharge", 5.0, "discharge", 2.0, -2.0, OperatingMode.NORMAL),
        ("charge", 5.0, "idle", 0.0, 0.0, OperatingMode.SAFE_IDLE),
    ],
)
def test_handoff_maps_approved_feasible_action_and_power(
    source_action: str,
    source_power: float,
    approved_action: str,
    approved_power: float,
    power: float,
    mode: OperatingMode,
) -> None:
    feasible = _feasible(source_action, source_power, approved_action, approved_power)

    result = DeterministicEdgeCommandHandoff().handoff(feasible, metadata=_metadata())

    assert result.source_feasible_decision is feasible
    assert result.command.requested_battery_power_kw == power
    assert result.command.operating_mode is mode


def test_metadata_identity_and_every_field_are_preserved_exactly() -> None:
    feasible = _feasible("charge", 5.0, "charge", 2.0)
    metadata = _metadata()

    result = DeterministicEdgeCommandHandoff().handoff(feasible, metadata=metadata)

    assert result.metadata is metadata
    assert result.command.command_id == metadata.command_id
    assert result.command.sequence == metadata.sequence
    assert result.command.provenance_id == metadata.provenance_id
    assert result.command.issued_at is metadata.issued_at
    assert result.command.not_before is metadata.not_before
    assert result.command.expires_at is metadata.expires_at
    assert result.command.reason_code == metadata.reason_code
    assert result.command.source == metadata.source
    assert result.command.correlation_id == metadata.correlation_id


def test_command_uses_existing_schema_and_round_trips() -> None:
    result = DeterministicEdgeCommandHandoff().handoff(
        _feasible(), metadata=_metadata()
    )

    assert result.command.schema_version == "edge-power-command/v1"
    assert PowerCommand.from_dict(result.command.to_dict()) == result.command


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("command_id", "", ValueError),
        ("sequence", True, TypeError),
        ("sequence", -1, ValueError),
        ("issued_at", datetime(2032, 1, 1), ValueError),
        ("expires_at", NOW, ValueError),
    ],
)
def test_metadata_rejects_invalid_identity_sequence_and_time_facts(
    field: str, value: object, error: type[Exception]
) -> None:
    kwargs = {field: value}
    with pytest.raises(error):
        replace(_metadata(), **cast(Any, kwargs))


def test_contracts_are_frozen_slotted_and_metadata_has_no_power_authority() -> None:
    metadata = _metadata()
    result = DeterministicEdgeCommandHandoff().handoff(_feasible(), metadata=metadata)

    assert [field.name for field in fields(EdgeCommandMetadata)] == [
        "command_id",
        "sequence",
        "provenance_id",
        "issued_at",
        "not_before",
        "expires_at",
        "reason_code",
        "source",
        "correlation_id",
    ]
    assert [field.name for field in fields(EdgeCommandHandoffResult)] == [
        "source_feasible_decision",
        "metadata",
        "command",
    ]
    assert not hasattr(metadata, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, metadata).sequence = 8


def test_boundary_is_abstract_and_rejects_direct_non_feasible_inputs() -> None:
    assert issubclass(EdgeCommandHandoffBoundary, ABC)
    assert inspect.isabstract(EdgeCommandHandoffBoundary)
    with pytest.raises(TypeError):
        EdgeCommandHandoffBoundary()  # type: ignore[abstract]
    handoff = DeterministicEdgeCommandHandoff()
    with pytest.raises(TypeError, match="FeasibleDecision"):
        handoff.handoff(cast(Any, _feasible().source_decision), metadata=_metadata())
    with pytest.raises(TypeError, match="FeasibleDecision"):
        handoff.handoff(cast(Any, MPCCurrentAction), metadata=_metadata())


class _WrongOutputHandoff(EdgeCommandHandoffBoundary):
    __slots__ = ()

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        return cast(EdgeCommandHandoffResult, object())


class _ReconstructingHandoff(EdgeCommandHandoffBoundary):
    __slots__ = ()

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        reconstructed = FeasibleDecision(
            feasible_decision.source_decision,
            feasible_decision.source_provenance,
            feasible_decision.approved_intent,
            feasible_decision.approved_power_kw,
        )
        command = (
            DeterministicEdgeCommandHandoff()
            .handoff(reconstructed, metadata=metadata)
            .command
        )
        return EdgeCommandHandoffResult(reconstructed, metadata, command)


def test_boundary_rejects_wrong_result_and_reconstructed_source_identity() -> None:
    feasible = _feasible()
    with pytest.raises(TypeError, match="must return"):
        _WrongOutputHandoff().handoff(feasible, metadata=_metadata())
    with pytest.raises(ValueError, match="exact source_feasible_decision identity"):
        _ReconstructingHandoff().handoff(feasible, metadata=_metadata())


def test_result_rejects_metadata_rewrites_and_unapproved_power() -> None:
    feasible = _feasible("charge", 5.0, "charge", 2.0)
    metadata = _metadata()
    command = (
        DeterministicEdgeCommandHandoff().handoff(feasible, metadata=metadata).command
    )
    with pytest.raises(ValueError, match="command_id"):
        EdgeCommandHandoffResult(
            feasible, metadata, replace(command, command_id="other")
        )
    with pytest.raises(ValueError, match="approved charge mapping"):
        EdgeCommandHandoffResult(
            feasible,
            metadata,
            replace(command, requested_battery_power_kw=5.0),
        )


def test_result_contract_independently_rejects_corrupted_generator_charge_sign(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feasible = _feasible("charge", 5.0, "charge", 2.0)

    monkeypatch.setattr(
        edge_command_handoff_module, "_approved_signed_power", lambda _: -2.0
    )

    with pytest.raises(ValueError, match="approved charge mapping"):
        DeterministicEdgeCommandHandoff().handoff(feasible, metadata=_metadata())


def test_result_contract_independently_rejects_raw_source_power_generator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    feasible = _feasible("charge", 5.0, "charge", 2.0)

    monkeypatch.setattr(
        edge_command_handoff_module,
        "_approved_signed_power",
        lambda decision: decision.source_decision.requested_power_kw,
    )

    with pytest.raises(ValueError, match="approved charge mapping"):
        DeterministicEdgeCommandHandoff().handoff(feasible, metadata=_metadata())


@pytest.mark.parametrize(
    ("source_action", "approved_action", "command_power", "message"),
    [
        ("charge", "charge", -2.0, "approved charge mapping"),
        ("discharge", "discharge", 2.0, "approved discharge mapping"),
        ("charge", "charge", 5.0, "approved charge mapping"),
        ("charge", "idle", 5.0, "approved idle mapping"),
    ],
)
def test_result_contract_rejects_direct_forged_power_mapping(
    source_action: str,
    approved_action: str,
    command_power: float,
    message: str,
) -> None:
    feasible = _feasible(
        source_action,
        5.0,
        approved_action,
        2.0 if approved_action != "idle" else 0.0,
    )
    metadata = _metadata()
    command = (
        DeterministicEdgeCommandHandoff().handoff(feasible, metadata=metadata).command
    )
    forged = replace(
        command,
        requested_battery_power_kw=command_power,
        operating_mode=OperatingMode.NORMAL,
    )

    with pytest.raises(ValueError, match=message):
        EdgeCommandHandoffResult(feasible, metadata, forged)


def test_result_contract_independently_rejects_corrupted_idle_power() -> None:
    feasible = _feasible("charge", 5.0, "idle", 0.0)
    metadata = _metadata()
    command = (
        DeterministicEdgeCommandHandoff().handoff(feasible, metadata=metadata).command
    )

    object.__setattr__(command, "requested_battery_power_kw", 5.0)

    with pytest.raises(
        ValueError, match="command power must match approved idle mapping"
    ):
        EdgeCommandHandoffResult(feasible, metadata, command)


def test_result_contract_independently_rejects_corrupted_idle_mode() -> None:
    feasible = _feasible("charge", 5.0, "idle", 0.0)
    metadata = _metadata()
    command = (
        DeterministicEdgeCommandHandoff().handoff(feasible, metadata=metadata).command
    )

    object.__setattr__(command, "operating_mode", OperatingMode.NORMAL)

    with pytest.raises(
        ValueError, match="command mode must match approved idle mapping"
    ):
        EdgeCommandHandoffResult(feasible, metadata, command)


def test_calls_are_stateless_and_require_explicit_metadata_for_new_identity() -> None:
    handoff = DeterministicEdgeCommandHandoff()
    feasible = _feasible()
    first = handoff.handoff(feasible, metadata=_metadata(7))
    same = handoff.handoff(feasible, metadata=_metadata(7))
    distinct = handoff.handoff(feasible, metadata=replace(_metadata(7), sequence=8))

    assert first.command == same.command
    assert first.command is not same.command
    assert distinct.command.sequence == 8
    assert not hasattr(handoff, "__dict__")


def test_module_is_transport_neutral_and_has_no_execution_dependencies() -> None:
    module_path = Path(ems_strategy.__file__).parent / "edge_command_handoff.py"
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "datetime",
        "edge_runtime",
        "edge_runtime.validation",
        "ems_strategy.feasibility",
    }
    for forbidden in ("tick(", "Simulator", "Lifecycle", "datetime.now", "uuid"):
        assert forbidden not in source


def test_public_api_exports_p05_handoff_contracts() -> None:
    assert ems_strategy.EdgeCommandMetadata is EdgeCommandMetadata
    assert ems_strategy.EdgeCommandHandoffResult is EdgeCommandHandoffResult
    assert ems_strategy.EdgeCommandHandoffBoundary is EdgeCommandHandoffBoundary
    assert (
        ems_strategy.DeterministicEdgeCommandHandoff is DeterministicEdgeCommandHandoff
    )
