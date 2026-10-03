"""Independent numeric and boundary checks for the bounded teaching example."""

import csv
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from edge_runtime import AcknowledgementStatus, CommandAcknowledgement
from edge_runtime.controlled_composition import (
    ControlledEdgeCompositionEvidence,
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
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceObservation,
    ScriptedResidentialDeviceAdapter,
    ScriptedTransmissionOutcome,
    TransmissionStatus,
)
from edge_runtime.device_simulator import (
    DeterministicDeviceSimulator,
    FaultSchedule,
    FaultSpecification,
    FaultTarget,
    FaultType,
    VirtualClock,
)
from ems_strategy import DecisionProvenance, SelfConsumptionStrategy
from examples.virtual_home_storage.demo import (
    AT,
    DURATION,
    NAMES,
    START,
    CallNotes,
    ObservedHandoff,
    create_session,
    evaluate_fixture,
    export,
    run_scenario,
    scenario,
    strategy_context,
)


@pytest.mark.parametrize(
    ("name", "requested", "command", "actual", "soc"),
    [
        # Hand calculations: 3 kW for 1 minute is .05 kWh at the AC boundary.
        # Charge stores .045 kWh; discharge removes 1/18 kWh; capacity 10 kWh.
        ("charge", 3.0, 3.0, 3.0, 0.5045),
        ("discharge", 3.0, -3.0, -3.0, 0.49444444444444446),
        # BMS derate halves 3 to 1.5 kW: .025 kWh AC, .0225 kWh stored.
        ("power_limit", 6.0, 6.0, 1.5, 0.50225),
    ],
)
def test_hand_calculated_power_energy_soc(
    name: str, requested: float, command: float, actual: float, soc: float
) -> None:
    row = run_scenario(name)
    assert row["strategy_request_kw_magnitude"] == requested
    assert row["approved_kw_magnitude"] == requested
    assert row["command_kw_signed"] == command
    assert row["safety_final_kw_signed"] == actual
    assert row["virtual_actual_kw_signed"] == actual
    assert row["soc_after"] == pytest.approx(soc, abs=1e-12)
    assert row["receipt_returned"] is True
    assert row["session_terminal"] is True


def test_limit_does_not_claim_lifecycle_completion() -> None:
    row = run_scenario("power_limit")
    assert row["bms_charge_limit_kw"] == 1.5
    assert row["pcs_charge_limit_kw"] == 3
    reconciliation = row["p03_reconciliation"]
    assert isinstance(reconciliation, dict)
    assert reconciliation["status"] == "lifecycle_incomplete"
    assert row["safety_reasons"]


def test_exact_identity_and_one_real_call_per_layer() -> None:
    spec = scenario("charge")
    decision, provenance, feasible = evaluate_fixture(spec)
    notes = CallNotes()
    session = create_session(spec, notes)
    assert not notes.steps and not notes.handoffs
    receipt = session.run_cycle(
        ControlledCompositionSessionCycleInput(feasible, spec.metadata, DURATION),
        session.initial_continuation,
    )
    evidence = receipt.evidence
    assert decision.source_strategy is SelfConsumptionStrategy.descriptor
    assert decision.source_context.source_context is spec.context
    assert provenance.decision is decision
    assert provenance.source_context is decision.source_context
    assert feasible.source_decision is decision
    assert feasible.source_provenance is provenance
    assert len(notes.handoffs) == len(notes.steps) == 1
    assert len(notes.observations) == len(notes.transmissions) == 1
    assert len(notes.acknowledgements) == len(notes.actuals) == 1
    handoff = notes.handoffs[0]
    step = notes.steps[0]
    assert evidence.handoff_result is handoff
    assert handoff.source_feasible_decision is feasible
    assert handoff.metadata is spec.metadata
    assert evidence.runtime_step is step
    assert step.caller_command is handoff.command
    assert step.admitted_command is handoff.command
    assert step.device_step.command is handoff.command
    safety = step.device_step.safety_decision
    assert safety is not None
    assert safety.source_command is handoff.command
    assert safety.source_telemetry is step.device_step.raw_telemetry
    assert safety.source_capability.bms_capability is step.device_step.bms_capability
    assert safety.source_capability.pcs_capability is step.device_step.pcs_capability
    assert evidence.adapter_evidence.observation is notes.observations[0]
    assert evidence.adapter_evidence.transmission is notes.transmissions[0]
    assert evidence.adapter_evidence.acknowledgement is notes.acknowledgements[0]
    assert evidence.adapter_actual_telemetry is notes.actuals[0].telemetry
    for name in (
        "command_id",
        "sequence",
        "provenance_id",
        "issued_at",
        "not_before",
        "expires_at",
        "correlation_id",
    ):
        assert getattr(handoff.command, name) == getattr(spec.metadata, name)
        assert getattr(notes.transmissions[0], name) == getattr(spec.metadata, name)
    assert receipt.continuation.next_runtime.trace.steps[-1] is step
    assert step.tick_index == 1  # exactly one bootstrap tick before the command
    assert step.started_at == AT
    assert step.ended_at == AT + timedelta(seconds=60)
    session.terminate(receipt.continuation)


def test_independent_adapter_snapshot_never_rewrites_execution() -> None:
    row = run_scenario("charge")
    observation = row["p04_actual"]
    assert isinstance(observation, dict)
    assert observation["actual_battery_power_kw"] == 0
    assert observation["soc_fraction"] == 0.5
    assert row["virtual_actual_kw_signed"] == 3
    assert row["soc_after"] == 0.5045
    reconciliation = row["p03_reconciliation"]
    assert isinstance(reconciliation, dict)
    assert reconciliation["actual_power_kw"] == 3
    assert reconciliation["status"] == "completed"


def test_expired_command_is_real_non_admission_without_transmission() -> None:
    row = run_scenario("expired")
    assert row["receipt_returned"] is False
    assert row["session_terminal"] is True
    assert row["virtual_actual_kw_signed"] == 0
    assert row["soc_after"] == 0.5
    assert row["safety_final_kw_signed"] is None
    assert row["p02_ack"] is None
    assert row["p04_transmission"] is None
    assert row["p02_application_authorized"] is False
    assert "non-admission" in str(row["stop_reason"])
    reconciliation = row["p03_reconciliation"]
    assert isinstance(reconciliation, dict)
    assert reconciliation["status"] == "command_expired"


def test_ack_mismatch_preserves_preceding_execution_and_does_not_invent_actual() -> (
    None
):
    row = run_scenario("ack_mismatch")
    assert row["receipt_returned"] is False
    assert row["session_terminal"] is True
    assert row["virtual_actual_kw_signed"] == 3
    assert row["soc_after"] == 0.5045
    assert row["p02_application_authorized"] is True
    assert row["p04_transmission"] is not None
    assert row["p04_actual_read"] is False
    assert row["p04_actual"] is None
    assert "ACK does not correlate" in str(row["stop_reason"])
    ack = row["p04_ack"]
    assert isinstance(ack, dict)
    assert ack["command_id"] == "different-command"


class _EvidenceComposition(DeterministicControlledEdgeComposition):
    """Observe every returned P0.6 result; never replace its runtime or facts."""

    def __init__(self) -> None:
        self.evidence: list[ControlledEdgeCompositionEvidence] = []

    def _compose(
        self, composition_input: ControlledEdgeCompositionInput
    ) -> ControlledEdgeCompositionResult:
        result = super()._compose(composition_input)
        self.evidence.append(result.evidence)
        return result


@pytest.mark.parametrize(
    "reuse", ["metadata", "equal_metadata", "decision", "continuation"]
)
def test_no_reuse_or_implicit_second_cycle(reuse: str) -> None:
    spec = scenario("charge")
    _, _, feasible = evaluate_fixture(spec)
    notes = CallNotes()
    # Independent fresh plant and two explicit sets of scripted facts. Exhausting
    # a one-row script is NOT evidence that duplicate authority was rejected.
    runtime = ControlledEdgeRuntime.start(
        DeterministicDeviceSimulator.start(spec.configuration, at=VirtualClock(START))
    ).tick(None, duration=timedelta(seconds=1))
    probe = runtime.simulator.prepare_step()
    adapter = ScriptedResidentialDeviceAdapter(
        observations=tuple(
            DeviceObservation(
                AT,
                AdapterFactAvailability.AVAILABLE,
                probe.raw_telemetry,
                probe.bms_capability,
                probe.pcs_capability,
                probe.runtime_health,
                None,
            )
            for _ in range(2)
        ),
        transmission_outcomes=tuple(
            ScriptedTransmissionOutcome(AT, TransmissionStatus.TRANSMITTED)
            for _ in range(2)
        ),
        acknowledgements=tuple(
            DeviceAckObservation(
                AT,
                AdapterFactAvailability.AVAILABLE,
                CommandAcknowledgement(
                    spec.metadata.command_id,
                    1,
                    AcknowledgementStatus.ACCEPTED,
                    AT,
                    AT,
                    3.0,
                    None,
                    "explicit teaching ACK",
                    spec.metadata.correlation_id,
                ),
                None,
            )
            for _ in range(2)
        ),
        actual_telemetry=tuple(
            DeviceActualTelemetryObservation(
                AT,
                AdapterFactAvailability.AVAILABLE,
                probe.raw_telemetry,
                None,
            )
            for _ in range(2)
        ),
    )
    composition = _EvidenceComposition()
    session = ControlledCompositionSession.create(
        ControlledCompositionSessionCreationInput(
            "reuse-test",
            runtime,
            adapter,
            ObservedHandoff(notes),
            composition,
        )
    )
    first = session.initial_continuation
    receipt = session.run_cycle(
        ControlledCompositionSessionCycleInput(feasible, spec.metadata, DURATION), first
    )
    # Re-evaluate the strategy: no prior assessment is masquerading as new input.
    _, _, fresh = evaluate_fixture(spec)
    metadata = replace(
        spec.metadata,
        command_id="new-command",
        sequence=2,
        provenance_id="new-decision",
        issued_at=AT + DURATION,
        not_before=AT + DURATION,
        expires_at=AT + DURATION * 3,
    )
    if reuse == "metadata":
        metadata = spec.metadata
    elif reuse == "equal_metadata":
        metadata = replace(spec.metadata)
    cycle = ControlledCompositionSessionCycleInput(
        feasible if reuse == "decision" else fresh, metadata, DURATION
    )
    with pytest.raises(ControlledCompositionSessionFailureError) as caught:
        session.run_cycle(
            cycle, first if reuse == "continuation" else receipt.continuation
        )
    expected_cause = {
        "metadata": "metadata cannot be reused by a session cycle",
        "decision": "decision cannot be reused by a session cycle",
        "continuation": "continuation is not the exact active session continuation",
        "equal_metadata": "P0.3 non-admission is terminal for a session cycle",
    }[reuse]
    assert type(caught.value.__cause__) is ValueError
    assert str(caught.value.__cause__) == expected_cause
    assert session.is_terminal
    assert adapter.transmission_attempt_count == 1
    if reuse == "equal_metadata":
        # Equal values in a fresh object reach P0.3: a logical idle tick occurs,
        # but no second command is admitted/applied and no power is replayed.
        assert len(composition.evidence) == len(notes.handoffs) == 2
        second = composition.evidence[1].runtime_step
        assert second.tick_index == 2
        assert second.transition_reasons == ("duplicate_command_id",)
        assert second.admitted_command is None
        assert second.device_step.command is None
        assert second.device_step.command_application_authorized is False
        assert second.device_step.actual_power_kw == 0
        assert second.device_step.starting_soc_fraction == 0.5045
        assert second.device_step.ending_soc_fraction == 0.5045
        assert composition.evidence[1].adapter_evidence.transmission is None
    else:
        assert len(composition.evidence) == len(notes.handoffs) == 1
    with pytest.raises(ControlledCompositionSessionTerminatedError):
        session.run_cycle(cycle, receipt.continuation)


@pytest.mark.parametrize(
    "field,value",
    [("soc", 0.6), ("pv_power_kw", 5.0), ("battery_energy_capacity_kwh", 12.0)],
)
def test_changed_inputs_do_not_gain_fixture_approval(field: str, value: float) -> None:
    spec = scenario("charge")
    if field == "soc":
        facts = replace(spec.context, soc=value)
    elif field == "pv_power_kw":
        facts = replace(spec.context, pv_power_kw=value)
    else:
        facts = replace(spec.context, battery_energy_capacity_kwh=value)
    context = strategy_context(facts)
    decision = SelfConsumptionStrategy().evaluate(context)
    provenance = DecisionProvenance(context, decision.source_strategy, decision)
    with pytest.raises(ValueError, match="outside explicit teaching approval"):
        spec.approval.bind(decision, provenance)


def test_prior_provenance_cannot_approve_new_strategy_decision() -> None:
    spec = scenario("charge")
    _, old_provenance, _ = evaluate_fixture(spec)
    new_decision, _, _ = evaluate_fixture(spec)
    with pytest.raises(ValueError, match="exact source_decision identity"):
        spec.approval.bind(new_decision, old_provenance)


def test_missing_p02_ack_is_simulator_policy_not_p04_physical_claim() -> None:
    spec = scenario("charge")
    spec = replace(
        spec,
        configuration=replace(
            spec.configuration,
            fault_schedule=FaultSchedule(
                (
                    FaultSpecification(
                        "missing-ack",
                        FaultType.ACK_DROPPED,
                        FaultTarget.COMMAND_CHANNEL,
                        AT,
                        None,
                        (),
                        "simulated missing P0.2 ACK",
                    ),
                )
            ),
        ),
    )
    _, _, feasible = evaluate_fixture(spec)
    notes = CallNotes()
    session = create_session(spec, notes)
    receipt = session.run_cycle(
        ControlledCompositionSessionCycleInput(feasible, spec.metadata, DURATION),
        session.initial_continuation,
    )
    device = receipt.evidence.runtime_step.device_step
    assert device.acknowledgement is None
    assert device.command_application_authorized is False
    assert device.actual_power_kw == 0
    assert device.ending_soc_fraction == 0.5
    # P0.4's scripted accepted ACK cannot authorize a past P0.2 execution.
    assert receipt.evidence.correlated_acknowledgement is not None
    session.terminate(receipt.continuation)


def test_export_deterministic_machine_readable_and_labeled(tmp_path: Path) -> None:
    rows = [run_scenario(name) for name in NAMES]
    export(tmp_path, rows)
    json_bytes = (tmp_path / "steps.json").read_bytes()
    csv_bytes = (tmp_path / "steps.csv").read_bytes()
    data = json.loads(json_bytes)
    with (tmp_path / "steps.csv").open(newline="", encoding="utf-8") as stream:
        csv_data = list(csv.DictReader(stream))
    assert [x["scenario"] for x in data] == list(NAMES)
    assert len(csv_data) == 5
    assert all("simulated" in x["label"] for x in data)
    assert data[0]["input"]["configuration"]["capacity_kwh"] == 10
    assert data[0]["command"]["issued_at"] == "2032-01-01T00:00:01+00:00"
    assert json.loads(csv_data[0]["p04_actual"])["soc_fraction"] == 0.5
    export(tmp_path, [run_scenario(name) for name in NAMES])
    assert (tmp_path / "steps.json").read_bytes() == json_bytes
    assert (tmp_path / "steps.csv").read_bytes() == csv_bytes
