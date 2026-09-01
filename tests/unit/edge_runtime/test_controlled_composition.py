"""P0.6 focused composition regressions over frozen P0.1-P0.5 contracts."""

import ast
import copy
import inspect
import pickle
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import DecisionIntent
from edge_runtime import (
    AcknowledgementStatus,
    CommandAcknowledgement,
    RuntimeState,
    TimingPolicy,
)
from edge_runtime.controlled_composition import (
    ControlledEdgeCompositionContinuation,
    ControlledEdgeCompositionEvidence,
    ControlledEdgeCompositionInput,
    DeterministicControlledEdgeComposition,
)
from edge_runtime.controlled_runtime import ControlledEdgeRuntime
from edge_runtime.device_adapter import (
    AdapterFactAvailability,
    AdapterFailureCode,
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceAdapterFailure,
    DeviceObservation,
    DeviceTransmissionEvidence,
    DeviceTransmissionRequest,
    ResidentialDeviceAdapterBoundary,
    ScriptedResidentialDeviceAdapter,
    ScriptedTransmissionOutcome,
    TransmissionStatus,
)
from edge_runtime.device_simulator import (
    DeterministicDeviceSimulator,
    DeviceSimulatorConfiguration,
    FaultSchedule,
    VirtualClock,
)
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
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor

NOW = datetime(2032, 1, 1, tzinfo=UTC)


def _runtime() -> ControlledEdgeRuntime:
    configuration = DeviceSimulatorConfiguration(
        10,
        0.5,
        0.2,
        1,
        3,
        3,
        0.95,
        0.95,
        timing_policy=TimingPolicy(
            timedelta(seconds=30),
            timedelta(seconds=30),
            timedelta(minutes=5),
            timedelta(seconds=2),
            timedelta(seconds=5),
            timedelta(seconds=30),
        ),
        fault_schedule=FaultSchedule(()),
    )
    runtime = ControlledEdgeRuntime.start(
        DeterministicDeviceSimulator.start(configuration, at=VirtualClock(NOW))
    )
    return runtime.tick(None, duration=timedelta(seconds=1))


def _feasible() -> FeasibleDecision:
    context = DecisionContext(
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
    capability = CapabilityDescriptor("p06", "P0.6 test capability")
    required = RequiredCapabilityCollection((capability,))
    available = AvailableCapabilityCollection((capability,))
    matches = CapabilityMatchCollection(
        required, available, (CapabilityMatch(capability, capability),), ()
    )
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("p06", "P0.6 test objective"),
        ActiveCapabilityCollection(matches, (capability,), ()),
    )
    ems_context = EMSContext(context, composition, capability)
    strategy = EMSStrategyDescriptor("p06", "1.0")
    decision = EMSDecision(ems_context, strategy, DecisionIntent("charge"), 2.0)
    return FeasibleDecision(
        decision,
        DecisionProvenance(ems_context, strategy, decision),
        DecisionIntent("charge"),
        2.0,
    )


def _metadata(runtime: ControlledEdgeRuntime, sequence: int = 1) -> EdgeCommandMetadata:
    now = runtime.simulator.clock.now
    return EdgeCommandMetadata(
        f"p06-{sequence}",
        sequence,
        "p06-provenance",
        now,
        now,
        now + timedelta(minutes=1),
        "approved",
        "p06-test",
        f"p06-{sequence}",
    )


def _adapter(
    runtime: ControlledEdgeRuntime,
    metadata: EdgeCommandMetadata,
    *,
    acknowledged_command_id: str | None = None,
    transmission: bool = True,
) -> ScriptedResidentialDeviceAdapter:
    probe = runtime.simulator.prepare_step()
    observation = DeviceObservation(
        runtime.simulator.clock.now,
        AdapterFactAvailability.AVAILABLE,
        probe.raw_telemetry,
        probe.bms_capability,
        probe.pcs_capability,
        probe.runtime_health,
        None,
    )
    acknowledgement = CommandAcknowledgement(
        acknowledged_command_id or metadata.command_id,
        metadata.sequence,
        AcknowledgementStatus.ACCEPTED,
        runtime.simulator.clock.now,
        runtime.simulator.clock.now,
        2.0,
        None,
        "accepted",
        metadata.correlation_id,
    )
    return ScriptedResidentialDeviceAdapter(
        observations=(observation,),
        transmission_outcomes=(
            (
                ScriptedTransmissionOutcome(
                    runtime.simulator.clock.now, TransmissionStatus.TRANSMITTED
                ),
            )
            if transmission
            else ()
        ),
        acknowledgements=(
            DeviceAckObservation(
                runtime.simulator.clock.now,
                AdapterFactAvailability.AVAILABLE,
                acknowledgement,
                None,
            ),
        ),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                runtime.simulator.clock.now,
                AdapterFactAvailability.AVAILABLE,
                probe.raw_telemetry,
                None,
            ),
        ),
    )


def _input(
    runtime: ControlledEdgeRuntime,
    adapter: ScriptedResidentialDeviceAdapter,
    metadata: EdgeCommandMetadata,
    *,
    feasible: FeasibleDecision | None = None,
    handoff: EdgeCommandHandoffBoundary | None = None,
) -> ControlledEdgeCompositionInput:
    return ControlledEdgeCompositionInput(
        feasible or _feasible(),
        metadata,
        handoff or DeterministicEdgeCommandHandoff(),
        runtime,
        adapter,
        timedelta(seconds=1),
    )


def _dataclass_graph(value: object, seen: set[int] | None = None) -> tuple[object, ...]:
    """Inspect retained dataclass facts without invoking producers or factories."""

    visited = seen if seen is not None else set()
    if id(value) in visited:
        return ()
    visited.add(id(value))
    values: tuple[object, ...] = (value,)
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            values += _dataclass_graph(getattr(value, field.name), visited)
    elif isinstance(value, tuple):
        for item in value:
            values += _dataclass_graph(item, visited)
    return values


class _CountingAdapter(ScriptedResidentialDeviceAdapter):
    """Count public boundary operations while retaining scripted P0.4 facts."""

    def __init__(
        self,
        *,
        observations: tuple[DeviceObservation, ...],
        transmission_outcomes: tuple[ScriptedTransmissionOutcome, ...],
        acknowledgements: tuple[DeviceAckObservation, ...],
        actual_telemetry: tuple[DeviceActualTelemetryObservation, ...],
    ) -> None:
        super().__init__(
            observations=observations,
            transmission_outcomes=transmission_outcomes,
            acknowledgements=acknowledgements,
            actual_telemetry=actual_telemetry,
        )
        self.acquire_calls = 0
        self.transmit_calls = 0
        self.acknowledgement_calls = 0
        self.actual_calls = 0

    def acquire_observation(self) -> DeviceObservation:
        self.acquire_calls += 1
        return super().acquire_observation()

    def transmit(
        self, request: DeviceTransmissionRequest
    ) -> DeviceTransmissionEvidence:
        self.transmit_calls += 1
        return super().transmit(request)

    def observe_acknowledgement(self) -> DeviceAckObservation:
        self.acknowledgement_calls += 1
        return super().observe_acknowledgement()

    def observe_actual_telemetry(self) -> DeviceActualTelemetryObservation:
        self.actual_calls += 1
        return super().observe_actual_telemetry()


class _CountingHandoff(EdgeCommandHandoffBoundary):
    def __init__(self) -> None:
        self.calls = 0

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        self.calls += 1
        return DeterministicEdgeCommandHandoff().handoff(
            feasible_decision, metadata=metadata
        )


def _counting_adapter(
    runtime: ControlledEdgeRuntime, metadata: EdgeCommandMetadata
) -> _CountingAdapter:
    probe = runtime.simulator.prepare_step()
    observation = DeviceObservation(
        runtime.simulator.clock.now,
        AdapterFactAvailability.AVAILABLE,
        probe.raw_telemetry,
        probe.bms_capability,
        probe.pcs_capability,
        probe.runtime_health,
        None,
    )
    acknowledgement = CommandAcknowledgement(
        metadata.command_id,
        metadata.sequence,
        AcknowledgementStatus.ACCEPTED,
        runtime.simulator.clock.now,
        runtime.simulator.clock.now,
        2.0,
        None,
        "accepted",
        metadata.correlation_id,
    )
    return _CountingAdapter(
        observations=(observation,),
        transmission_outcomes=(
            ScriptedTransmissionOutcome(
                runtime.simulator.clock.now, TransmissionStatus.TRANSMITTED
            ),
        ),
        acknowledgements=(
            DeviceAckObservation(
                runtime.simulator.clock.now,
                AdapterFactAvailability.AVAILABLE,
                acknowledgement,
                None,
            ),
        ),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                runtime.simulator.clock.now,
                AdapterFactAvailability.AVAILABLE,
                probe.raw_telemetry,
                None,
            ),
        ),
    )


def test_cycle_retains_layers_without_claiming_adapter_actual_is_execution() -> None:
    runtime = _runtime()
    metadata = _metadata(runtime)
    feasible = _feasible()
    adapter = _adapter(runtime, metadata)

    result = DeterministicControlledEdgeComposition().compose(
        _input(runtime, adapter, metadata, feasible=feasible)
    )

    evidence = result.evidence
    continuation = result.continuation
    assert isinstance(evidence, ControlledEdgeCompositionEvidence)
    assert isinstance(continuation, ControlledEdgeCompositionContinuation)
    assert evidence.handoff_result.source_feasible_decision is feasible
    assert evidence.handoff_result.metadata is metadata
    assert evidence.runtime_step is continuation.next_runtime.trace.steps[-1]
    assert evidence.runtime_step.caller_command is evidence.handoff_result.command
    assert evidence.runtime_step.admitted_command is evidence.handoff_result.command
    assert evidence.adapter_evidence.transmission is not None
    assert evidence.adapter_evidence.transmission.command_id == metadata.command_id
    assert evidence.correlated_acknowledgement is not None
    assert evidence.adapter_actual_telemetry is not None
    assert (
        evidence.adapter_actual_telemetry
        is evidence.adapter_evidence.actual_telemetry.telemetry
    )
    assert evidence.runtime_step.reconciliation.actual_power_kw == 2.0
    assert evidence.adapter_actual_telemetry.actual_battery_power_kw == 0.0
    assert (
        evidence.runtime_step.reconciliation.actual_power_kw
        != evidence.adapter_actual_telemetry.actual_battery_power_kw
    )
    with pytest.raises(FrozenInstanceError):
        result.evidence = evidence  # type: ignore[misc]


def test_normal_cycle_calls_each_public_stage_once_and_retains_exact_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    metadata = _metadata(runtime)
    adapter = _counting_adapter(runtime, metadata)
    handoff = _CountingHandoff()
    original_tick = ControlledEdgeRuntime.tick
    tick_calls = 0

    def counted_tick(
        runtime_self: ControlledEdgeRuntime,
        command: Any,
        *,
        duration: timedelta,
        tolerance_kw: float = 0.01,
    ) -> ControlledEdgeRuntime:
        nonlocal tick_calls
        tick_calls += 1
        return original_tick(
            runtime_self,
            command,
            duration=duration,
            tolerance_kw=tolerance_kw,
        )

    monkeypatch.setattr(ControlledEdgeRuntime, "tick", counted_tick)
    result = DeterministicControlledEdgeComposition().compose(
        _input(runtime, adapter, metadata, handoff=handoff)
    )

    assert handoff.calls == 1
    assert tick_calls == 1
    assert (adapter.acquire_calls, adapter.transmit_calls) == (1, 1)
    assert (adapter.acknowledgement_calls, adapter.actual_calls) == (1, 1)
    assert (
        result.evidence.runtime_step.caller_command
        is result.evidence.handoff_result.command
    )
    assert result.evidence.adapter_evidence.transmission is not None
    assert (
        result.continuation.next_runtime.trace.steps[-1] is result.evidence.runtime_step
    )


def test_evidence_and_current_caller_continuation_are_separate_and_non_replayable() -> (
    None
):
    runtime = _runtime()
    metadata = _metadata(runtime)
    handoff = DeterministicEdgeCommandHandoff()
    adapter = _adapter(runtime, metadata)
    source = _input(runtime, adapter, metadata, handoff=handoff)
    result = DeterministicControlledEdgeComposition().compose(source)
    evidence = result.evidence
    continuation = result.continuation

    assert tuple(field.name for field in fields(evidence)) == (
        "handoff_result",
        "runtime_step",
        "adapter_evidence",
        "correlated_acknowledgement",
        "adapter_actual_telemetry",
    )
    assert tuple(field.name for field in fields(continuation)) == ("next_runtime",)
    assert continuation.next_runtime is not runtime
    assert not any(
        hasattr(evidence, name)
        for name in (
            "source_input",
            "runtime",
            "adapter",
            "handoff_boundary",
            "request",
        )
    )
    assert not any(
        hasattr(continuation, name)
        for name in ("adapter", "handoff_boundary", "command", "metadata", "request")
    )
    forbidden_live_types = (
        ControlledEdgeCompositionInput,
        ControlledEdgeRuntime,
        ResidentialDeviceAdapterBoundary,
        EdgeCommandHandoffBoundary,
        DeviceTransmissionRequest,
    )
    assert not any(
        isinstance(value, forbidden_live_types) for value in _dataclass_graph(evidence)
    )
    for contract in (result, evidence, continuation):
        for name in ("to_dict", "from_dict", "hydrate", "from_evidence"):
            assert not hasattr(contract, name)
        with pytest.raises(TypeError, match=r"cannot be (copied|serialized)"):
            copy.copy(contract)
        with pytest.raises(TypeError, match=r"cannot be (copied|serialized)"):
            copy.deepcopy(contract)
        with pytest.raises(TypeError, match="cannot be serialized"):
            pickle.dumps(contract)
    for operation in (copy.copy, copy.deepcopy):
        with pytest.raises(TypeError, match="ControlledEdgeRuntime cannot be copied"):
            operation(continuation.next_runtime)
    with pytest.raises(TypeError, match="ControlledEdgeRuntime cannot be serialized"):
        pickle.dumps(continuation.next_runtime)


def test_unavailable_adapter_facts_are_explicit_audit_evidence_not_completion() -> None:
    runtime = _runtime()
    metadata = _metadata(runtime)
    now = runtime.simulator.clock.now
    unavailable = DeviceAdapterFailure(
        AdapterFailureCode.CHANNEL_UNAVAILABLE, now, "scripted unavailable"
    )
    adapter = ScriptedResidentialDeviceAdapter(
        observations=(
            DeviceObservation(
                now,
                AdapterFactAvailability.UNAVAILABLE,
                None,
                None,
                None,
                None,
                unavailable,
            ),
        ),
        transmission_outcomes=(
            ScriptedTransmissionOutcome(now, TransmissionStatus.FAILED, unavailable),
        ),
        acknowledgements=(
            DeviceAckObservation(
                now, AdapterFactAvailability.UNAVAILABLE, None, unavailable
            ),
        ),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                now, AdapterFactAvailability.UNAVAILABLE, None, unavailable
            ),
        ),
    )

    result = DeterministicControlledEdgeComposition().compose(
        _input(runtime, adapter, metadata)
    )

    assert result.evidence.runtime_step.reconciliation.actual_power_kw == 2.0
    assert (
        result.evidence.adapter_evidence.observation.availability
        is AdapterFactAvailability.UNAVAILABLE
    )
    assert result.evidence.adapter_evidence.transmission is not None
    assert (
        result.evidence.adapter_evidence.transmission.status
        is TransmissionStatus.FAILED
    )
    assert result.evidence.correlated_acknowledgement is None
    assert result.evidence.adapter_actual_telemetry is None


class _MalformedObservationAdapter(ResidentialDeviceAdapterBoundary):
    def acquire_observation(self) -> DeviceObservation:
        return cast(DeviceObservation, object())

    def transmit(
        self, request: DeviceTransmissionRequest
    ) -> DeviceTransmissionEvidence:
        raise AssertionError("malformed observation must fail before transmit")

    def observe_acknowledgement(self) -> DeviceAckObservation:
        raise AssertionError("malformed observation must fail before ACK")

    def observe_actual_telemetry(self) -> DeviceActualTelemetryObservation:
        raise AssertionError("malformed observation must fail before actual")


def test_malformed_adapter_fact_fails_closed_without_successful_cycle_evidence() -> (
    None
):
    runtime = _runtime()
    metadata = _metadata(runtime)

    with pytest.raises(TypeError, match="adapter must return a DeviceObservation"):
        DeterministicControlledEdgeComposition().compose(
            ControlledEdgeCompositionInput(
                _feasible(),
                metadata,
                DeterministicEdgeCommandHandoff(),
                runtime,
                _MalformedObservationAdapter(),
                timedelta(seconds=1),
            )
        )
    assert runtime.trace.steps[-1].caller_command is None


@pytest.mark.parametrize(
    "field_name", ["command_id", "sequence", "issued_at", "expires_at"]
)
def test_p06_preserves_each_p05_metadata_field_without_rewriting(
    field_name: str,
) -> None:
    runtime = _runtime()
    metadata = _metadata(runtime)
    result = DeterministicControlledEdgeComposition().compose(
        _input(runtime, _adapter(runtime, metadata), metadata)
    )
    evidence = result.evidence
    command = evidence.handoff_result.command
    assert getattr(command, field_name) == getattr(metadata, field_name)
    assert getattr(evidence.runtime_step.caller_command, field_name) == getattr(
        metadata, field_name
    )
    assert getattr(evidence.adapter_evidence.transmission, field_name) == getattr(
        metadata, field_name
    )


class _CorruptedEquivalentSourceHandoff(EdgeCommandHandoffBoundary):
    """Simulate a producer corrupting a typed P0.5 result after its outer gate."""

    def handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        valid = DeterministicEdgeCommandHandoff().handoff(
            feasible_decision, metadata=metadata
        )
        return EdgeCommandHandoffResult(_feasible(), metadata, valid.command)

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        raise AssertionError(
            "corruption harness must bypass the P0.5 public outer contract"
        )


class _CorruptedEquivalentMetadataHandoff(EdgeCommandHandoffBoundary):
    """Simulate a producer corrupting metadata after P0.5's outer contract."""

    def handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        valid = DeterministicEdgeCommandHandoff().handoff(
            feasible_decision, metadata=metadata
        )
        return EdgeCommandHandoffResult(
            feasible_decision, replace(metadata), valid.command
        )

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        raise AssertionError(
            "corruption harness must bypass the P0.5 public outer contract"
        )


@pytest.mark.parametrize(
    "handoff",
    [_CorruptedEquivalentSourceHandoff(), _CorruptedEquivalentMetadataHandoff()],
)
def test_corrupted_p05_source_or_metadata_fails_closed_before_runtime_tick(
    handoff: EdgeCommandHandoffBoundary,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = _runtime()
    metadata = _metadata(runtime)
    adapter = _counting_adapter(runtime, metadata)
    original_tick = ControlledEdgeRuntime.tick
    tick_calls = 0

    def counted_tick(
        runtime_self: ControlledEdgeRuntime,
        command: Any,
        *,
        duration: timedelta,
        tolerance_kw: float = 0.01,
    ) -> ControlledEdgeRuntime:
        nonlocal tick_calls
        tick_calls += 1
        return original_tick(
            runtime_self,
            command,
            duration=duration,
            tolerance_kw=tolerance_kw,
        )

    monkeypatch.setattr(ControlledEdgeRuntime, "tick", counted_tick)
    with pytest.raises(
        ValueError, match=r"exact (feasible_decision|metadata) identity"
    ):
        DeterministicControlledEdgeComposition().compose(
            _input(runtime, adapter, metadata, handoff=handoff)
        )
    assert tick_calls == 0
    assert (
        adapter.acquire_calls,
        adapter.transmit_calls,
        adapter.acknowledgement_calls,
        adapter.actual_calls,
        adapter.transmission_attempt_count,
    ) == (0, 0, 0, 0, 0)


def test_non_admitting_runtime_never_transmits_and_does_not_restore_history() -> None:
    starting = ControlledEdgeRuntime.start(_runtime().simulator)
    metadata = _metadata(starting)
    adapter = _adapter(starting, metadata, transmission=False)
    result = DeterministicControlledEdgeComposition().compose(
        _input(starting, adapter, metadata)
    )

    assert result.evidence.runtime_step.state_before is RuntimeState.STARTING
    assert result.evidence.runtime_step.admitted_command is None
    assert result.evidence.adapter_evidence.transmission is None
    assert result.evidence.correlated_acknowledgement is None
    assert adapter.transmission_attempt_count == 0


def test_reused_metadata_cannot_replay_after_completed_p03_cycle() -> None:
    runtime = _runtime()
    metadata = _metadata(runtime)
    first = DeterministicControlledEdgeComposition().compose(
        _input(runtime, _adapter(runtime, metadata), metadata)
    )
    second_adapter = _adapter(
        first.continuation.next_runtime, metadata, transmission=False
    )
    second = DeterministicControlledEdgeComposition().compose(
        _input(first.continuation.next_runtime, second_adapter, metadata)
    )

    assert first.evidence.runtime_step.admitted_command is not None
    assert second.evidence.runtime_step.admitted_command is None
    assert second.evidence.runtime_step.command_origin.value == "none"
    assert second.evidence.adapter_evidence.transmission is None
    assert second_adapter.transmission_attempt_count == 0


def test_mismatched_adapter_acknowledgement_fails_closed_before_evidence_return() -> (
    None
):
    runtime = _runtime()
    metadata = _metadata(runtime)
    with pytest.raises(ValueError, match="does not correlate"):
        DeterministicControlledEdgeComposition().compose(
            _input(
                runtime,
                _adapter(runtime, metadata, acknowledged_command_id="forged"),
                metadata,
            )
        )


def test_only_feasible_decision_and_no_transport_imports() -> None:
    runtime = _runtime()
    metadata = _metadata(runtime)
    with pytest.raises(TypeError, match="FeasibleDecision"):
        ControlledEdgeCompositionInput(
            cast(Any, object()),
            metadata,
            DeterministicEdgeCommandHandoff(),
            runtime,
            _adapter(runtime, metadata),
            timedelta(seconds=1),
        )
    package = Path(inspect.getfile(DeterministicControlledEdgeComposition)).parent
    imports: set[str] = set()
    for path in package.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
    forbidden = {
        "asyncio",
        "can",
        "http",
        "modbus",
        "mqtt",
        "requests",
        "serial",
        "socket",
        "subprocess",
        "threading",
        "urllib",
    }
    assert not any(module.split(".")[0] in forbidden for module in imports)
