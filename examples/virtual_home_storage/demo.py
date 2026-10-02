"""Five fixed teaching fixtures over the real strategy and frozen Edge chain."""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

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
    PowerCommand,
    TimingPolicy,
)
from edge_runtime.controlled_composition import DeterministicControlledEdgeComposition
from edge_runtime.controlled_composition_session import (
    ControlledCompositionSession,
    ControlledCompositionSessionCreationInput,
    ControlledCompositionSessionCycleInput,
    ControlledCompositionSessionFailureError,
)
from edge_runtime.controlled_runtime import ControlledEdgeRuntime, RuntimeLoopStep
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
    FaultSpecification,
    FaultTarget,
    FaultType,
    VirtualClock,
)
from ems_strategy import (
    DecisionProvenance,
    DeterministicEdgeCommandHandoff,
    EdgeCommandHandoffResult,
    EdgeCommandMetadata,
    EMSContext,
    EMSDecision,
    FeasibleDecision,
    SelfConsumptionStrategy,
)
from kernel.decision import DecisionContext
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor

START = datetime(2032, 1, 1, tzinfo=UTC)
AT = START + timedelta(seconds=1)
DURATION = timedelta(seconds=60)
LABEL = "simulated / 固定教学 fixture; 非真实采集、非生产自动审批"
NAMES = ("charge", "discharge", "power_limit", "expired", "ack_mismatch")


@dataclass(frozen=True)
class ApprovalFixture:
    """Caller approval for exactly these facts/request, never a generic evaluator."""

    fixture_id: str
    context: DecisionContext
    requested_action: str
    requested_kw: float
    approved_action: Literal["charge", "discharge", "idle"]
    approved_kw: float

    def bind(
        self, decision: EMSDecision, provenance: DecisionProvenance
    ) -> FeasibleDecision:
        if (
            decision.source_context.source_context != self.context
            or decision.source_strategy is not SelfConsumptionStrategy.descriptor
            or decision.intent.action != self.requested_action
            or decision.requested_power_kw != self.requested_kw
        ):
            raise ValueError("strategy request is outside explicit teaching approval")
        return FeasibleDecision(
            decision, provenance, DecisionIntent(self.approved_action), self.approved_kw
        )


def context_facts(pv: float, load: float) -> DecisionContext:
    return DecisionContext(
        timestamp=AT,
        soc=0.5,
        battery_power_limit_kw=3.0,
        battery_energy_capacity_kwh=10.0,
        pv_power_kw=pv,
        load_power_kw=load,
        grid_power_kw=0.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=5.0,
    )


# Explicit caller approvals. These values are not derived from strategy output.
APPROVALS = {
    "charge": ApprovalFixture(
        "charge-approval", context_facts(4, 1), "charge", 3, "charge", 3
    ),
    "discharge": ApprovalFixture(
        "discharge-approval", context_facts(1, 4), "discharge", 3, "discharge", 3
    ),
    "power_limit": ApprovalFixture(
        "limit-approval", context_facts(7, 1), "charge", 6, "charge", 6
    ),
    "expired": ApprovalFixture(
        "expired-approval", context_facts(4, 1), "charge", 3, "charge", 3
    ),
    "ack_mismatch": ApprovalFixture(
        "ack-approval", context_facts(4, 1), "charge", 3, "charge", 3
    ),
}


@dataclass(frozen=True)
class Scenario:
    name: str
    context: DecisionContext
    approval: ApprovalFixture
    configuration: DeviceSimulatorConfiguration
    metadata: EdgeCommandMetadata
    adapter_ack_id: str
    adapter_ack_power_kw: float


def scenario(name: str) -> Scenario:
    if name not in NAMES:
        raise ValueError(f"unknown fixed scenario: {name}")
    pv, load = {"discharge": (1.0, 4.0), "power_limit": (7.0, 1.0)}.get(
        name, (4.0, 1.0)
    )
    faults: tuple[FaultSpecification, ...] = ()
    if name == "power_limit":
        faults = (
            FaultSpecification(
                "teaching-bms-limit",
                FaultType.CHARGE_DERATE,
                FaultTarget.BMS,
                START,
                None,
                (("factor", 0.5),),
                "simulated BMS charge limit 1.5 kW",
            ),
        )
    configuration = DeviceSimulatorConfiguration(
        10,
        0.5,
        0.2,
        0.9,
        3,
        3,
        0.9,
        0.9,
        TimingPolicy(
            timedelta(seconds=30),
            timedelta(seconds=30),
            timedelta(minutes=5),
            timedelta(seconds=2),
            timedelta(seconds=5),
            timedelta(seconds=120),
        ),
        FaultSchedule(faults),
    )
    issued = START - timedelta(seconds=60) if name == "expired" else AT
    expires = START if name == "expired" else AT + timedelta(seconds=120)
    metadata = EdgeCommandMetadata(
        f"{name}-command-1",
        1,
        f"{name}-decision-1",
        issued,
        issued,
        expires,
        "explicit-teaching-fixture",
        "virtual-home-storage",
        f"{name}-correlation-1",
    )
    return Scenario(
        name,
        context_facts(pv, load),
        APPROVALS[name],
        configuration,
        metadata,
        "different-command" if name == "ack_mismatch" else metadata.command_id,
        {"discharge": -3.0, "power_limit": 1.5, "expired": 0.0}.get(name, 3.0),
    )


def strategy_context(facts: DecisionContext) -> EMSContext:
    capability = CapabilityDescriptor("self-consumption", "Use local virtual PV")
    matches = CapabilityMatchCollection(
        RequiredCapabilityCollection((capability,)),
        AvailableCapabilityCollection((capability,)),
        (CapabilityMatch(capability, capability),),
        (),
    )
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("self-consumption", "Virtual home teaching fixture"),
        ActiveCapabilityCollection(matches, (capability,), ()),
    )
    return EMSContext(facts, composition, capability)


def evaluate_fixture(
    spec: Scenario,
) -> tuple[EMSDecision, DecisionProvenance, FeasibleDecision]:
    context = strategy_context(spec.context)
    decision = SelfConsumptionStrategy().evaluate(context)
    provenance = DecisionProvenance(context, decision.source_strategy, decision)
    return decision, provenance, spec.approval.bind(decision, provenance)


@dataclass
class CallNotes:
    """Audit references only: never retain a runtime or continuation on failure."""

    steps: list[RuntimeLoopStep] = field(default_factory=list)
    handoffs: list[EdgeCommandHandoffResult] = field(default_factory=list)
    observations: list[DeviceObservation] = field(default_factory=list)
    transmissions: list[DeviceTransmissionEvidence] = field(default_factory=list)
    acknowledgements: list[DeviceAckObservation] = field(default_factory=list)
    actuals: list[DeviceActualTelemetryObservation] = field(default_factory=list)


@dataclass(frozen=True)
class ObservedRuntime(ControlledEdgeRuntime):
    """Call frozen P0.3 once; retain only its completed immutable tick evidence."""

    notes: CallNotes = field(default_factory=CallNotes, compare=False)

    def tick(
        self,
        command: PowerCommand | None,
        *,
        duration: timedelta,
        tolerance_kw: float = 0.01,
    ) -> ControlledEdgeRuntime:
        result = super().tick(command, duration=duration, tolerance_kw=tolerance_kw)
        self.notes.steps.append(result.trace.steps[-1])
        return result


class ObservedHandoff(DeterministicEdgeCommandHandoff):
    def __init__(self, notes: CallNotes) -> None:
        self.notes = notes

    def _handoff(
        self, feasible_decision: FeasibleDecision, *, metadata: EdgeCommandMetadata
    ) -> EdgeCommandHandoffResult:
        result = super()._handoff(feasible_decision, metadata=metadata)
        self.notes.handoffs.append(result)
        return result


class ObservedAdapter(ScriptedResidentialDeviceAdapter):
    """Record the exact facts returned by the frozen scripted adapter."""

    notes: CallNotes

    def acquire_observation(self) -> DeviceObservation:
        result = super().acquire_observation()
        self.notes.observations.append(result)
        return result

    def transmit(
        self, request: DeviceTransmissionRequest
    ) -> DeviceTransmissionEvidence:
        result = super().transmit(request)
        self.notes.transmissions.append(result)
        return result

    def observe_acknowledgement(self) -> DeviceAckObservation:
        result = super().observe_acknowledgement()
        self.notes.acknowledgements.append(result)
        return result

    def observe_actual_telemetry(self) -> DeviceActualTelemetryObservation:
        result = super().observe_actual_telemetry()
        self.notes.actuals.append(result)
        return result


def create_session(spec: Scenario, notes: CallNotes) -> ControlledCompositionSession:
    ready = ControlledEdgeRuntime.start(
        DeterministicDeviceSimulator.start(spec.configuration, at=VirtualClock(START))
    ).tick(None, duration=timedelta(seconds=1))
    runtime = ObservedRuntime(
        ready.simulator, ready.lifecycle_book, ready.state, ready.trace, notes
    )
    # An explicit, independent start snapshot: NOT the post-tick actual result.
    probe = ready.simulator.prepare_step()
    adapter = ObservedAdapter(
        observations=(
            DeviceObservation(
                AT,
                AdapterFactAvailability.AVAILABLE,
                probe.raw_telemetry,
                probe.bms_capability,
                probe.pcs_capability,
                probe.runtime_health,
                None,
            ),
        ),
        transmission_outcomes=(
            ScriptedTransmissionOutcome(AT, TransmissionStatus.TRANSMITTED),
        ),
        acknowledgements=(
            DeviceAckObservation(
                AT,
                AdapterFactAvailability.AVAILABLE,
                CommandAcknowledgement(
                    spec.adapter_ack_id,
                    spec.metadata.sequence,
                    AcknowledgementStatus.ACCEPTED,
                    AT,
                    AT,
                    spec.adapter_ack_power_kw,
                    None,
                    "scripted simulated ACK",
                    spec.metadata.correlation_id,
                ),
                None,
            ),
        ),
        actual_telemetry=(
            DeviceActualTelemetryObservation(
                AT,
                AdapterFactAvailability.AVAILABLE,
                probe.raw_telemetry,
                None,
            ),
        ),
    )
    adapter.notes = notes
    return ControlledCompositionSession.create(
        ControlledCompositionSessionCreationInput(
            f"{spec.name}-session",
            runtime,
            adapter,
            ObservedHandoff(notes),
            DeterministicControlledEdgeComposition(),
        )
    )


EXPLANATIONS = {
    "charge": "PV 4 > 负载 1: 策略请求充电 3 kW; 显式 fixture 批准; 安全层允许。",
    "discharge": "负载 4 > PV 1 且 SOC 高于储备: 请求放电 3 kW; 命令映射为 -3 kW。",
    "power_limit": (
        "PV 盈余 6 kW; fixture 批准 6; BMS 1.5 与 PCS 3 取小, "
        "安全限到 +1.5 kW; lifecycle_incomplete 不等于完成。"
    ),
    "expired": "命令在本次 tick 开始前已过期; 批准不延长有效期, 虚拟执行功率为零。",
    "ack_mismatch": (
        "P0.3 已虚拟充电; 随后 P0.4 ACK ID 失配, "
        "session 终止, 无下一 continuation; 不撤销执行。"
    ),
}


def run_scenario(name: str) -> dict[str, object]:
    spec = scenario(name)
    decision, provenance, feasible = evaluate_fixture(spec)
    notes = CallNotes()
    session = create_session(spec, notes)
    continuation = session.initial_continuation
    failure: str | None = None
    receipt_returned = False
    try:
        receipt = session.run_cycle(
            ControlledCompositionSessionCycleInput(feasible, spec.metadata, DURATION),
            continuation,
        )
    except ControlledCompositionSessionFailureError as exc:
        failure = str(exc.__cause__)
    else:
        receipt_returned = True
        session.terminate(receipt.continuation)
    # Read recorded facts even if the later adapter audit failed. No re-execution.
    step = notes.steps[0]
    device = step.device_step
    safety = device.safety_decision
    command = notes.handoffs[0].command
    ack = device.acknowledgement
    p04_ack = notes.acknowledgements[0].acknowledgement
    observation = notes.observations[0]
    p04_actual = notes.actuals[0].telemetry if notes.actuals else None
    row: dict[str, object] = {
        "label": LABEL,
        "scenario": name,
        "cycle": 1,
        "input": asdict(spec),
        "duration_seconds": 60,
        "tick_index": step.tick_index,
        "tick_start": step.started_at,
        "tick_end": step.ended_at,
        "runtime_state_before": step.state_before.value,
        "runtime_state_after": step.state_after.value,
        "runtime_transition_reasons": step.transition_reasons,
        "admitted": step.admitted_command is not None,
        "strategy": decision.source_strategy.name,
        "decision_id": spec.metadata.provenance_id,
        "strategy_action": decision.intent.action,
        "strategy_request_kw_magnitude": decision.requested_power_kw,
        "approval_fixture": spec.approval.fixture_id,
        "approval_kind": "explicit scenario fixture; not production feasibility",
        "approved_action": feasible.approved_intent.action,
        "approved_kw_magnitude": feasible.approved_power_kw,
        "command": asdict(command),
        "command_kw_signed": command.requested_battery_power_kw,
        "bms_charge_limit_kw": device.bms_capability.max_charge_power_kw,
        "pcs_charge_limit_kw": device.pcs_capability.max_charge_power_kw,
        "bms_discharge_limit_kw": device.bms_capability.max_discharge_power_kw,
        "pcs_discharge_limit_kw": device.pcs_capability.max_discharge_power_kw,
        "safety_final_kw_signed": safety.final_requested_battery_power_kw
        if safety
        else None,
        "safety_reasons": [x.reason_code for x in safety.applied_constraints]
        if safety
        else [],
        "virtual_actual_kw_signed": device.actual_power_kw,
        "soc_before": device.starting_soc_fraction,
        "soc_after": device.ending_soc_fraction,
        "p02_ack": ack.to_dict() if ack else None,
        "p02_application_authorized": device.command_application_authorized,
        "p03_reconciliation": step.reconciliation.to_dict(),
        "p04_observation": observation.to_dict(),
        "p04_transmission": notes.transmissions[0].to_dict()
        if notes.transmissions
        else None,
        "p04_ack": p04_ack.to_dict() if p04_ack else None,
        "p04_actual": p04_actual.to_dict() if p04_actual else None,
        "p04_actual_read": bool(notes.actuals),
        "p04_source": "independent scripted pre-execution snapshot; simulated",
        "receipt_returned": receipt_returned,
        "session_terminal": session.is_terminal,
        "stop_reason": failure
        or ("bounded single cycle finished; " + step.reconciliation.primary_reason),
        "explanation_zh": EXPLANATIONS[name],
    }
    # provenance is created for this actual evaluation, never taken from a prior row.
    assert provenance.decision is decision
    return row


def export(directory: Path, rows: list[dict[str, object]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    normalized = json.loads(json.dumps(rows, ensure_ascii=False, default=_json_value))
    (directory / "steps.json").write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (directory / "steps.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, dict | list)
                else value
                for key, value in row.items()
            }
            for row in normalized
        )


def _json_value(value: object) -> str | float:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    raise TypeError(f"unsupported output value {type(value).__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=LABEL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [run_scenario(name) for name in NAMES]
    export(args.output, rows)
    print(LABEL)
    for row in rows:
        print(f"{row['scenario']}: {row['explanation_zh']}")
        print(
            f"  request={row['strategy_request_kw_magnitude']} "
            f"approval={row['approved_kw_magnitude']} "
            f"command={row['command_kw_signed']} "
            f"safety={row['safety_final_kw_signed']} "
            f"virtual_actual={row['virtual_actual_kw_signed']} kW "
            f"SOC={row['soc_after']}; {row['stop_reason']}"
        )
    print("P0.4 是独立脚本观察, 不回写 P0.3 reconciliation; ACK 不证明物理完成。")
    print("P0.2 ACK 缺失即不施加是模拟政策; 真实设备可能在 ACK 丢失时已执行。")


if __name__ == "__main__":
    main()
