"""Focused P0.7 session tests over frozen P0.3-P0.6 public contracts."""

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
    TimingPolicy,
)
from edge_runtime.controlled_composition import (
    ControlledEdgeCompositionInput,
    ControlledEdgeCompositionResult,
    DeterministicControlledEdgeComposition,
)
from edge_runtime.controlled_composition_session import (
    ControlledCompositionSession,
    ControlledCompositionSessionCreationInput,
    ControlledCompositionSessionCycleInput,
    ControlledCompositionSessionFailureError,
    ControlledCompositionSessionTerminatedError,
)
from edge_runtime.controlled_runtime import ControlledEdgeRuntime
from edge_runtime.device_adapter import (
    AdapterFactAvailability,
    AdapterFailureCode,
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceAdapterFailure,
    DeviceObservation,
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
    capability = CapabilityDescriptor(label, "P0.7 test capability")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((capability,)),
        AvailableCapabilityCollection((capability,)),
        (CapabilityMatch(capability, capability),),
        (),
    )
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor(label, "P0.7 test objective"),
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
        f"p07-{sequence}",
        sequence,
        "p07-provenance",
        at,
        at,
        at + timedelta(minutes=1),
        "approved",
        "p07-test",
        f"p07-{sequence}",
    )


class _CountingComposition(DeterministicControlledEdgeComposition):
    def __init__(self) -> None:
        self.calls = 0

    def compose(
        self, composition_input: ControlledEdgeCompositionInput
    ) -> ControlledEdgeCompositionResult:
        self.calls += 1
        return super().compose(composition_input)


class _PostP06IdentityCorruptingComposition(_CountingComposition):
    """Return a type-correct P0.6 result with one post-production identity fault.

    ``super().compose`` performs the standard P0.6 handoff, logical runtime
    tick, and adapter audit first.  The wrapper then represents a corrupted
    producer result at the P0.6/P0.7 boundary; it deliberately does not claim
    that this is a pre-tick containment test.
    """

    def __init__(self, field: str) -> None:
        super().__init__()
        self._field = field

    def compose(
        self, composition_input: ControlledEdgeCompositionInput
    ) -> ControlledEdgeCompositionResult:
        result = super().compose(composition_input)
        handoff = result.evidence.handoff_result
        if self._field == "source_feasible_decision":
            corrupted_handoff = replace(
                handoff,
                source_feasible_decision=replace(handoff.source_feasible_decision),
            )
        elif self._field == "metadata":
            corrupted_handoff = replace(handoff, metadata=replace(handoff.metadata))
        elif self._field == "caller_command":
            step = result.evidence.runtime_step
            assert step.caller_command is handoff.command
            assert step.admitted_command is handoff.command
            self.original_caller_command = step.caller_command
            self.corrupted_caller_command = replace(step.caller_command)
            self.admitted_command = step.admitted_command
            # The result was produced by standard P0.6 first.  Mutating this
            # existing frozen trace object is a deliberately post-producer
            # corruption harness, so P0.6 evidence construction is not
            # re-entered and P0.7 must consume the mismatched fact.
            object.__setattr__(step, "caller_command", self.corrupted_caller_command)
            return result
        else:
            raise AssertionError(f"unsupported corruption field: {self._field}")
        return replace(
            result,
            evidence=replace(result.evidence, handoff_result=corrupted_handoff),
        )


class _CountingDeterministicHandoff(DeterministicEdgeCommandHandoff):
    """Count the standard P0.5 deterministic handoff without changing it."""

    def __init__(self) -> None:
        self.calls = 0

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        self.calls += 1
        return super()._handoff(feasible_decision, metadata=metadata)


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
        self.acknowledgement_calls = 0
        self.actual_calls = 0

    def acquire_observation(self) -> DeviceObservation:
        self.acquire_calls += 1
        return super().acquire_observation()

    def transmit(self, request: DeviceTransmissionRequest):  # type: ignore[no-untyped-def]
        self.transmit_calls += 1
        return super().transmit(request)

    def observe_acknowledgement(self) -> DeviceAckObservation:
        self.acknowledgement_calls += 1
        return super().observe_acknowledgement()

    def observe_actual_telemetry(self) -> DeviceActualTelemetryObservation:
        self.actual_calls += 1
        return super().observe_actual_telemetry()


def _adapter(
    runtime: ControlledEdgeRuntime, metadata: tuple[EdgeCommandMetadata, ...]
) -> _CountingAdapter:
    probe = runtime.simulator.prepare_step()
    at = runtime.simulator.clock.now
    observations = tuple(
        DeviceObservation(
            at,
            AdapterFactAvailability.AVAILABLE,
            probe.raw_telemetry,
            probe.bms_capability,
            probe.pcs_capability,
            probe.runtime_health,
            None,
        )
        for _ in metadata
    )
    acknowledgements = tuple(
        DeviceAckObservation(
            at,
            AdapterFactAvailability.AVAILABLE,
            CommandAcknowledgement(
                item.command_id,
                item.sequence,
                AcknowledgementStatus.ACCEPTED,
                at,
                at,
                2.0,
                None,
                "accepted",
                item.correlation_id,
            ),
            None,
        )
        for item in metadata
    )
    actuals = tuple(
        DeviceActualTelemetryObservation(
            at,
            AdapterFactAvailability.AVAILABLE,
            probe.raw_telemetry,
            None,
        )
        for _ in metadata
    )
    return _CountingAdapter(
        observations=observations,
        transmission_outcomes=tuple(
            ScriptedTransmissionOutcome(at, TransmissionStatus.TRANSMITTED)
            for _ in metadata
        ),
        acknowledgements=acknowledgements,
        actual_telemetry=actuals,
    )


def _session(
    runtime: ControlledEdgeRuntime,
    metadata: tuple[EdgeCommandMetadata, ...],
    *,
    session_id: str = "p07-session",
) -> tuple[
    ControlledCompositionSession,
    _CountingComposition,
    _CountingAdapter,
    _CountingDeterministicHandoff,
]:
    adapter = _adapter(runtime, metadata)
    handoff = _CountingDeterministicHandoff()
    composition = _CountingComposition()
    return (
        ControlledCompositionSession.create(
            ControlledCompositionSessionCreationInput(
                session_id, runtime, adapter, handoff, composition
            )
        ),
        composition,
        adapter,
        handoff,
    )


def _cycle(
    feasible: FeasibleDecision,
    metadata: EdgeCommandMetadata,
) -> ControlledCompositionSessionCycleInput:
    return ControlledCompositionSessionCycleInput(
        feasible, metadata, timedelta(seconds=1)
    )


def test_creation_has_no_p05_p03_or_p04_side_effects() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    session, composition, adapter, handoff = _session(runtime, (metadata,))

    assert session.initial_continuation.next_runtime is runtime
    assert composition.calls == handoff.calls == 0
    assert (adapter.acquire_calls, adapter.transmit_calls) == (0, 0)
    assert (adapter.acknowledgement_calls, adapter.actual_calls) == (0, 0)


def test_two_new_caller_cycles_compose_each_stage_once_and_keep_facts_separate() -> (
    None
):
    runtime = _ready_runtime()
    first_metadata = _metadata(runtime.simulator.clock.now, 1)
    second_metadata = _metadata(runtime.simulator.clock.now + timedelta(seconds=1), 2)
    session, composition, adapter, handoff = _session(
        runtime,
        (first_metadata, second_metadata),
    )

    first = session.run_cycle(
        _cycle(_feasible("p07-first"), first_metadata),
        session.initial_continuation,
    )
    second = session.run_cycle(
        _cycle(_feasible("p07-second"), second_metadata),
        first.continuation,
    )

    assert (first.ordinal, second.ordinal) == (1, 2)
    assert composition.calls == handoff.calls == 2
    assert (adapter.acquire_calls, adapter.transmit_calls) == (2, 2)
    assert (adapter.acknowledgement_calls, adapter.actual_calls) == (2, 2)
    assert (
        first.evidence.runtime_step.caller_command
        is first.evidence.handoff_result.command
    )
    assert (
        first.evidence.runtime_step.admitted_command
        is first.evidence.handoff_result.command
    )
    assert first.evidence.runtime_step.reconciliation.actual_power_kw == 2.0
    assert first.evidence.adapter_actual_telemetry is not None
    assert first.evidence.adapter_actual_telemetry.actual_battery_power_kw == 0.0


def test_reused_current_caller_metadata_and_decision_fail_before_p06_compose() -> None:
    runtime = _ready_runtime()
    first_metadata = _metadata(runtime.simulator.clock.now, 1)
    second_metadata = _metadata(runtime.simulator.clock.now + timedelta(seconds=1), 2)
    decision = _feasible("p07-reused")
    session, composition, adapter, _ = _session(
        runtime,
        (first_metadata, second_metadata),
    )
    receipt = session.run_cycle(
        _cycle(decision, first_metadata), session.initial_continuation
    )

    with pytest.raises(ControlledCompositionSessionFailureError) as failure:
        session.run_cycle(_cycle(decision, first_metadata), receipt.continuation)

    assert failure.value.failure_kind == "ValueError"
    assert composition.calls == 1
    assert (adapter.acquire_calls, adapter.transmit_calls) == (1, 1)
    assert session.is_terminal
    with pytest.raises(ControlledCompositionSessionTerminatedError):
        session.run_cycle(
            _cycle(_feasible("unused"), second_metadata),
            receipt.continuation,
        )


@pytest.mark.parametrize("field", ("source_feasible_decision", "metadata"))
def test_post_p06_identity_corruption_is_terminal_for_the_p07_consumer(
    field: str,
) -> None:
    """P0.7 rejects a type-correct but identity-corrupted P0.6 producer result."""

    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter = _adapter(runtime, (metadata,))
    handoff = _CountingDeterministicHandoff()
    composition = _PostP06IdentityCorruptingComposition(field)
    session = ControlledCompositionSession.create(
        ControlledCompositionSessionCreationInput(
            "identity-corruption", runtime, adapter, handoff, composition
        )
    )

    with pytest.raises(ControlledCompositionSessionFailureError) as failure:
        session.run_cycle(
            _cycle(_feasible(f"corrupted-{field}"), metadata),
            session.initial_continuation,
        )

    assert failure.value.failure_kind == "ValueError"
    # Corruption occurs after standard P0.6 compose, so this is consumer
    # containment rather than a claim that P0.6 tick was prevented.
    assert composition.calls == handoff.calls == 1
    assert (adapter.acquire_calls, adapter.transmit_calls) == (1, 1)
    assert (adapter.acknowledgement_calls, adapter.actual_calls) == (1, 1)
    assert session.is_terminal
    with pytest.raises(ControlledCompositionSessionTerminatedError):
        _ = session.initial_continuation


def test_post_p06_caller_command_corruption_is_terminal_for_the_p07_consumer() -> None:
    """P0.7 consumes a post-producer P0.5-to-P0.3 lineage corruption."""

    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    adapter = _adapter(runtime, (metadata,))
    handoff = _CountingDeterministicHandoff()
    composition = _PostP06IdentityCorruptingComposition("caller_command")
    session = ControlledCompositionSession.create(
        ControlledCompositionSessionCreationInput(
            "caller-command-corruption", runtime, adapter, handoff, composition
        )
    )

    with pytest.raises(ControlledCompositionSessionFailureError) as failure:
        session.run_cycle(
            _cycle(_feasible("corrupted-caller-command"), metadata),
            session.initial_continuation,
        )

    assert failure.value.failure_kind == "ValueError"
    caller_command_was_replaced = (
        composition.original_caller_command is not composition.corrupted_caller_command
    )
    assert caller_command_was_replaced
    assert composition.original_caller_command == composition.corrupted_caller_command
    assert composition.admitted_command is composition.original_caller_command
    # P0.6 already ticked and audited before this post-producer corruption.
    assert composition.calls == handoff.calls == 1
    assert (adapter.acquire_calls, adapter.transmit_calls) == (1, 1)
    assert (adapter.acknowledgement_calls, adapter.actual_calls) == (1, 1)
    assert session.is_terminal
    with pytest.raises(ControlledCompositionSessionTerminatedError):
        _ = session.initial_continuation


def test_cross_session_or_replaced_continuation_fails_without_execution() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    first, _, _, _ = _session(runtime, (metadata,), session_id="first")
    second, composition, adapter, _ = _session(
        _ready_runtime(), (metadata,), session_id="second"
    )

    with pytest.raises(ControlledCompositionSessionFailureError):
        second.run_cycle(
            _cycle(_feasible("cross"), metadata), first.initial_continuation
        )

    assert composition.calls == 0
    assert (adapter.acquire_calls, adapter.transmit_calls) == (0, 0)
    assert second.is_terminal
    with pytest.raises(ControlledCompositionSessionFailureError):
        first.terminate(replace(first.initial_continuation))


def test_session_receipt_and_continuation_reject_copy_pickle_and_replay() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    session, _, _, _ = _session(runtime, (metadata,))
    receipt = session.run_cycle(
        _cycle(_feasible("serialization"), metadata),
        session.initial_continuation,
    )

    for value in (session, receipt, receipt.continuation):
        for operation in (copy.copy, copy.deepcopy, pickle.dumps):
            with pytest.raises(TypeError, match="cannot be copied or serialized"):
                operation(value)
    with pytest.raises(ControlledCompositionSessionFailureError):
        session.run_cycle(
            _cycle(_feasible("replay"), metadata), session.initial_continuation
        )


def test_terminate_and_non_admission_consume_the_session() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    session, composition, adapter, _ = _session(runtime, (metadata,))
    termination = session.terminate(session.initial_continuation)

    assert termination.final_ordinal == 0
    assert composition.calls == 0
    assert (adapter.acquire_calls, adapter.transmit_calls) == (0, 0)
    with pytest.raises(ControlledCompositionSessionTerminatedError):
        session.terminate(session.initial_continuation)

    starting_runtime = ControlledEdgeRuntime.start(_ready_runtime().simulator)
    non_admission_metadata = _metadata(starting_runtime.simulator.clock.now, 2)
    failed, failed_composition, failed_adapter, _ = _session(
        starting_runtime, (non_admission_metadata,)
    )
    with pytest.raises(ControlledCompositionSessionFailureError) as failure:
        failed.run_cycle(
            _cycle(_feasible("non-admission"), non_admission_metadata),
            failed.initial_continuation,
        )
    assert failure.value.failure_kind == "ValueError"
    assert failed_composition.calls == 1
    assert failed_adapter.transmit_calls == 0
    assert failed.is_terminal


def test_unavailable_adapter_fact_is_terminal_and_fresh_session_can_recover() -> None:
    runtime = _ready_runtime()
    metadata = _metadata(runtime.simulator.clock.now, 1)
    failure = DeviceAdapterFailure(
        AdapterFailureCode.CHANNEL_UNAVAILABLE,
        runtime.simulator.clock.now,
        "unavailable for test",
    )
    unavailable_adapter = _CountingAdapter(
        observations=(
            DeviceObservation(
                runtime.simulator.clock.now,
                AdapterFactAvailability.UNAVAILABLE,
                None,
                None,
                None,
                None,
                failure,
            ),
        ),
        transmission_outcomes=(
            ScriptedTransmissionOutcome(
                runtime.simulator.clock.now,
                TransmissionStatus.FAILED,
                failure,
            ),
        ),
        acknowledgements=(
            DeviceAckObservation(
                runtime.simulator.clock.now,
                AdapterFactAvailability.UNAVAILABLE,
                None,
                failure,
            ),
        ),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                runtime.simulator.clock.now,
                AdapterFactAvailability.UNAVAILABLE,
                None,
                failure,
            ),
        ),
    )
    handoff = _CountingDeterministicHandoff()
    composition = _CountingComposition()
    failed = ControlledCompositionSession.create(
        ControlledCompositionSessionCreationInput(
            "failed-session", runtime, unavailable_adapter, handoff, composition
        )
    )

    with pytest.raises(ControlledCompositionSessionFailureError):
        failed.run_cycle(
            _cycle(_feasible("unavailable"), metadata),
            failed.initial_continuation,
        )
    assert composition.calls == handoff.calls == 1
    assert failed.is_terminal

    def read_initial_continuation() -> None:
        _ = failed.initial_continuation

    with pytest.raises(ControlledCompositionSessionTerminatedError):
        read_initial_continuation()

    fresh_runtime = _ready_runtime()
    fresh_metadata = _metadata(fresh_runtime.simulator.clock.now, 2)
    recovered, _, _, _ = _session(
        fresh_runtime,
        (fresh_metadata,),
        session_id="fresh-session",
    )
    receipt = recovered.run_cycle(
        _cycle(_feasible("fresh-recovery"), fresh_metadata),
        recovered.initial_continuation,
    )
    assert receipt.session_id == "fresh-session"
    assert not recovered.is_terminal


def test_public_exports_and_p06_frozen_source_paths_are_unchanged() -> None:
    import edge_runtime.controlled_composition_session as session_api

    assert set(session_api.__all__) == {
        "ControlledCompositionSession",
        "ControlledCompositionSessionCreationInput",
        "ControlledCompositionSessionContinuation",
        "ControlledCompositionSessionCycleInput",
        "ControlledCompositionSessionCycleReceipt",
        "ControlledCompositionSessionFailureError",
        "ControlledCompositionSessionTerminationReceipt",
        "ControlledCompositionSessionTerminatedError",
    }
    package = Path(inspect.getfile(session_api)).parent
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
