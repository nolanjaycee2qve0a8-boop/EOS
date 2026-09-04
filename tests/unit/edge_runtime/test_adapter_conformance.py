"""Focused P0.8 tests over frozen public P0.4-P0.7 contracts only."""

import ast
import copy
import inspect
import pickle
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
    OperatingMode,
    TimingPolicy,
)
from edge_runtime.adapter_conformance import (
    AdapterConformanceCycleInput,
    AdapterConformanceFailureError,
    AdapterConformanceTranscript,
    AdapterConformanceTranscriptFact,
    AdapterConformanceTranscriptKind,
    DeterministicAdapterConformanceHarness,
)
from edge_runtime.controlled_composition import DeterministicControlledEdgeComposition
from edge_runtime.controlled_composition_session import (
    ControlledCompositionSession,
    ControlledCompositionSessionCreationInput,
    ControlledCompositionSessionTerminatedError,
)
from edge_runtime.controlled_runtime import ControlledEdgeRuntime
from edge_runtime.device_adapter import (
    AdapterFactAvailability,
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceObservation,
    DeviceTransmissionEvidence,
    DeviceTransmissionRequest,
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


def _ready_runtime() -> ControlledEdgeRuntime:
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
    return ControlledEdgeRuntime.start(
        DeterministicDeviceSimulator.start(configuration, at=VirtualClock(NOW))
    ).tick(None, duration=timedelta(seconds=1))


def _feasible(label: str) -> FeasibleDecision:
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
    capability = CapabilityDescriptor(label, "P0.8 test capability")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((capability,)),
        AvailableCapabilityCollection((capability,)),
        (CapabilityMatch(capability, capability),),
        (),
    )
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor(label, "P0.8 test objective"),
        ActiveCapabilityCollection(matches, (capability,), ()),
    )
    ems_context = EMSContext(context, composition, capability)
    strategy = EMSStrategyDescriptor(label, "1.0")
    decision = EMSDecision(ems_context, strategy, DecisionIntent("charge"), 2.0)
    return FeasibleDecision(
        decision,
        DecisionProvenance(ems_context, strategy, decision),
        DecisionIntent("charge"),
        2.0,
    )


def _metadata(at: datetime, sequence: int) -> EdgeCommandMetadata:
    return EdgeCommandMetadata(
        f"p08-{sequence}",
        sequence,
        "p08-provenance",
        at,
        at,
        at + timedelta(minutes=1),
        "approved",
        "p08-test",
        f"p08-{sequence}",
    )


class _CountingHandoff(DeterministicEdgeCommandHandoff):
    def __init__(self) -> None:
        self.calls = 0

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        self.calls += 1
        return super()._handoff(feasible_decision, metadata=metadata)


class _CountingComposition(DeterministicControlledEdgeComposition):
    def __init__(self) -> None:
        self.calls = 0

    def compose(self, composition_input):  # type: ignore[no-untyped-def]
        self.calls += 1
        return super().compose(composition_input)


class _CountingAdapter(ScriptedResidentialDeviceAdapter):
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
        self.ack_calls = 0
        self.actual_calls = 0

    def acquire_observation(self) -> DeviceObservation:
        self.acquire_calls += 1
        return super().acquire_observation()

    def transmit(self, request: DeviceTransmissionRequest):  # type: ignore[no-untyped-def]
        self.transmit_calls += 1
        return super().transmit(request)

    def observe_acknowledgement(self) -> DeviceAckObservation:
        self.ack_calls += 1
        return super().observe_acknowledgement()

    def observe_actual_telemetry(self) -> DeviceActualTelemetryObservation:
        self.actual_calls += 1
        return super().observe_actual_telemetry()


def _script(
    runtime: ControlledEdgeRuntime,
    metadata: EdgeCommandMetadata,
    *,
    ack_metadata: EdgeCommandMetadata | None = None,
    ack_availability: AdapterFactAvailability = AdapterFactAvailability.AVAILABLE,
) -> tuple[_CountingAdapter, AdapterConformanceTranscript]:
    probe = runtime.simulator.prepare_step()
    at = runtime.simulator.clock.now
    observation = DeviceObservation(
        at,
        AdapterFactAvailability.AVAILABLE,
        probe.raw_telemetry,
        probe.bms_capability,
        probe.pcs_capability,
        probe.runtime_health,
        None,
    )
    acknowledgement = DeviceAckObservation(
        at,
        ack_availability,
        (
            CommandAcknowledgement(
                (ack_metadata or metadata).command_id,
                (ack_metadata or metadata).sequence,
                AcknowledgementStatus.ACCEPTED,
                at,
                at,
                2.0,
                None,
                "accepted",
                (ack_metadata or metadata).correlation_id,
            )
            if ack_availability is AdapterFactAvailability.AVAILABLE
            else None
        ),
        None,
    )
    actual = DeviceActualTelemetryObservation(
        at, AdapterFactAvailability.AVAILABLE, probe.raw_telemetry, None
    )
    transmission = DeviceTransmissionEvidence(
        at,
        metadata.command_id,
        metadata.sequence,
        metadata.provenance_id,
        metadata.correlation_id,
        metadata.issued_at,
        metadata.not_before,
        metadata.expires_at,
        OperatingMode.NORMAL,
        2.0,
        TransmissionStatus.TRANSMITTED,
        None,
    )
    transcript = AdapterConformanceTranscript(
        (
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.OBSERVATION, observation
            ),
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.TRANSMISSION, transmission
            ),
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.ACKNOWLEDGEMENT, acknowledgement
            ),
            AdapterConformanceTranscriptFact(
                AdapterConformanceTranscriptKind.ACTUAL_TELEMETRY, actual
            ),
        )
    )
    return (
        _CountingAdapter(
            observations=(observation,),
            transmission_outcomes=(
                ScriptedTransmissionOutcome(at, TransmissionStatus.TRANSMITTED),
            ),
            acknowledgements=(acknowledgement,),
            actual_telemetry=(actual,),
        ),
        transcript,
    )


def _session(
    runtime: ControlledEdgeRuntime,
    adapter: _CountingAdapter,
) -> tuple[ControlledCompositionSession, _CountingComposition, _CountingHandoff]:
    composition = _CountingComposition()
    handoff = _CountingHandoff()
    return (
        ControlledCompositionSession.create(
            ControlledCompositionSessionCreationInput(
                "p08-session", runtime, adapter, handoff, composition
            )
        ),
        composition,
        handoff,
    )


def _input(
    session: ControlledCompositionSession,
    feasible: FeasibleDecision,
    metadata: EdgeCommandMetadata,
    transcript: AdapterConformanceTranscript,
) -> AdapterConformanceCycleInput:
    return AdapterConformanceCycleInput(
        session,
        session.initial_continuation,
        feasible,
        metadata,
        timedelta(seconds=1),
        0.01,
        transcript,
    )


def test_normal_admitted_transcript_has_exactly_one_frozen_chain() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter, transcript = _script(runtime, metadata)
    session, composition, handoff = _session(runtime, adapter)

    verdict = DeterministicAdapterConformanceHarness().evaluate(
        _input(session, _feasible("normal"), metadata, transcript)
    )

    assert verdict.ordinal == 1
    assert composition.calls == handoff.calls == 1
    assert (adapter.acquire_calls, adapter.transmit_calls) == (1, 1)
    assert (adapter.ack_calls, adapter.actual_calls) == (1, 1)
    evidence = verdict.evidence
    assert evidence.runtime_step.caller_command is evidence.handoff_result.command
    assert evidence.runtime_step.admitted_command is evidence.handoff_result.command
    assert evidence.adapter_evidence.transmission is not None


def test_non_admission_never_returns_success_or_transmission() -> None:
    runtime = ControlledEdgeRuntime.start(_ready_runtime().simulator)
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter, transcript = _script(runtime, metadata)
    session, composition, handoff = _session(runtime, adapter)

    with pytest.raises(AdapterConformanceFailureError):
        DeterministicAdapterConformanceHarness().evaluate(
            _input(session, _feasible("non-admission"), metadata, transcript)
        )

    assert composition.calls == handoff.calls == 1
    assert adapter.transmit_calls == 0
    assert session.is_terminal


def test_transcript_order_and_duplicates_fail_before_any_p07_execution() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter, transcript = _script(runtime, metadata)
    session, composition, handoff = _session(runtime, adapter)
    facts = transcript.facts

    with pytest.raises(ValueError, match="ordered and non-duplicated"):
        AdapterConformanceTranscript((facts[1], facts[0], facts[2], facts[3]))
    with pytest.raises(ValueError, match="ordered and non-duplicated"):
        AdapterConformanceTranscript((facts[0], facts[1], facts[1], facts[3]))
    with pytest.raises(TypeError, match="invalid value"):
        AdapterConformanceTranscriptFact(
            AdapterConformanceTranscriptKind.OBSERVATION, facts[2].value
        )

    assert composition.calls == handoff.calls == 0
    assert (adapter.acquire_calls, adapter.transmit_calls) == (0, 0)
    assert not session.is_terminal


def test_unavailable_and_ack_mismatch_fail_closed_without_verdict() -> None:
    unavailable_runtime = _ready_runtime()
    unavailable_metadata = _metadata(unavailable_runtime.simulator.clock.now, 1)
    unavailable_adapter, unavailable_transcript = _script(
        unavailable_runtime,
        unavailable_metadata,
        ack_availability=AdapterFactAvailability.MISSING,
    )
    unavailable_session, _, _ = _session(unavailable_runtime, unavailable_adapter)
    with pytest.raises(AdapterConformanceFailureError):
        DeterministicAdapterConformanceHarness().evaluate(
            _input(
                unavailable_session,
                _feasible("unavailable"),
                unavailable_metadata,
                unavailable_transcript,
            )
        )
    assert unavailable_session.is_terminal

    mismatch_runtime = _ready_runtime()
    metadata = _metadata(mismatch_runtime.simulator.clock.now, 2)
    wrong_metadata = _metadata(mismatch_runtime.simulator.clock.now, 99)
    mismatch_adapter, mismatch_transcript = _script(
        mismatch_runtime, metadata, ack_metadata=wrong_metadata
    )
    mismatch_session, _, _ = _session(mismatch_runtime, mismatch_adapter)
    with pytest.raises(AdapterConformanceFailureError):
        DeterministicAdapterConformanceHarness().evaluate(
            _input(
                mismatch_session,
                _feasible("ack-mismatch"),
                metadata,
                mismatch_transcript,
            )
        )
    assert mismatch_session.is_terminal


def test_actual_stays_distinct_from_p03_reconciliation() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter, transcript = _script(runtime, metadata)
    session, _, _ = _session(runtime, adapter)

    verdict = DeterministicAdapterConformanceHarness().evaluate(
        _input(session, _feasible("fact-separation"), metadata, transcript)
    )

    assert verdict.evidence.runtime_step.reconciliation.actual_power_kw == 2.0
    assert verdict.evidence.adapter_actual_telemetry is not None
    assert verdict.evidence.adapter_actual_telemetry.actual_battery_power_kw == 0.0


def test_transcript_actual_mismatch_fails_closed_and_consumes_the_session() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter, transcript = _script(runtime, metadata)
    session, _, _ = _session(runtime, adapter)
    actual = transcript.facts[3].value
    assert isinstance(actual, DeviceActualTelemetryObservation)
    assert actual.telemetry is not None
    mismatched_actual = AdapterConformanceTranscriptFact(
        AdapterConformanceTranscriptKind.ACTUAL_TELEMETRY,
        replace(
            actual,
            telemetry=replace(actual.telemetry, actual_battery_power_kw=1.0),
        ),
    )
    mismatch = AdapterConformanceTranscript(
        (
            transcript.facts[0],
            transcript.facts[1],
            transcript.facts[2],
            mismatched_actual,
        )
    )

    with pytest.raises(AdapterConformanceFailureError):
        DeterministicAdapterConformanceHarness().evaluate(
            _input(session, _feasible("actual-mismatch"), metadata, mismatch)
        )

    assert session.is_terminal


def test_verdict_is_audit_only_and_cannot_copy_pickle_or_restore_authority() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter, transcript = _script(runtime, metadata)
    session, _, _ = _session(runtime, adapter)
    verdict = DeterministicAdapterConformanceHarness().evaluate(
        _input(session, _feasible("audit-only"), metadata, transcript)
    )

    for value in (verdict, transcript):
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with pytest.raises(TypeError, match="cannot be copied or serialized"):
                operation(value)
    assert not hasattr(verdict, "session")
    assert not hasattr(verdict, "continuation")
    assert not hasattr(verdict, "runtime")
    assert not hasattr(verdict, "adapter")
    assert not hasattr(verdict, "handoff")
    assert not hasattr(verdict, "command")
    assert not any(
        hasattr(type(verdict), name) for name in ("from_dict", "restore", "hydrate")
    )


def test_transcript_mismatch_consumes_session_and_fresh_p07_session_recovers() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter, transcript = _script(runtime, metadata)
    session, _, _ = _session(runtime, adapter)
    wrong_ack = AdapterConformanceTranscriptFact(
        AdapterConformanceTranscriptKind.ACKNOWLEDGEMENT,
        DeviceAckObservation(
            runtime.simulator.clock.now,
            AdapterFactAvailability.AVAILABLE,
            CommandAcknowledgement(
                "wrong",
                99,
                AcknowledgementStatus.ACCEPTED,
                NOW,
                NOW,
                2.0,
                None,
                "wrong",
                "wrong",
            ),
            None,
        ),
    )
    mismatch = AdapterConformanceTranscript(
        (transcript.facts[0], transcript.facts[1], wrong_ack, transcript.facts[3])
    )
    with pytest.raises(AdapterConformanceFailureError):
        DeterministicAdapterConformanceHarness().evaluate(
            _input(session, _feasible("mismatch"), metadata, mismatch)
        )
    assert session.is_terminal
    with pytest.raises(ControlledCompositionSessionTerminatedError):
        _ = session.initial_continuation

    fresh_runtime = _ready_runtime()
    fresh_metadata = _metadata(fresh_runtime.simulator.clock.now, 2)
    fresh_adapter, fresh_transcript = _script(fresh_runtime, fresh_metadata)
    fresh_session, _, _ = _session(fresh_runtime, fresh_adapter)
    fresh = DeterministicAdapterConformanceHarness().evaluate(
        _input(fresh_session, _feasible("fresh"), fresh_metadata, fresh_transcript)
    )
    assert fresh.ordinal == 1


def test_public_surface_has_no_transport_imports_or_power_command_input() -> None:
    import edge_runtime.adapter_conformance as public

    assert set(public.__all__) == {
        "AdapterConformanceCycleInput",
        "AdapterConformanceFailureError",
        "AdapterConformanceTranscript",
        "AdapterConformanceTranscriptFact",
        "AdapterConformanceTranscriptKind",
        "AdapterConformanceVerdict",
        "DeterministicAdapterConformanceHarness",
    }
    assert "PowerCommand" not in AdapterConformanceCycleInput.__annotations__
    package = Path(inspect.getfile(public)).parent
    forbidden = {
        "socket",
        "http",
        "urllib",
        "requests",
        "can",
        "modbus",
        "serial",
        "threading",
        "asyncio",
        "subprocess",
    }
    for path in package.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".")[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import | ast.ImportFrom)
            for alias in node.names
        }
        assert not forbidden & imported
