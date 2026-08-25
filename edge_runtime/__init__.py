"""Transport-neutral Residential Edge Runtime safety contracts.

P0.1 defines immutable facts, validation and deterministic safety/lifecycle
semantics only.  It owns no device adapter, socket, thread, scheduler or
control loop.
"""

from edge_runtime.contracts import (
    AcknowledgementStatus,
    CommandAcknowledgement,
    DeviceCapability,
    DeviceCapabilitySource,
    EffectiveDeviceCapability,
    FaultEvent,
    FaultSeverity,
    FaultSource,
    OperatingMode,
    PowerCommand,
    RuntimeHealth,
    RuntimeState,
    SafetyConstraint,
    SafetyDecision,
    SafetyOutcome,
    SafetyPrecedence,
    TelemetryQualityStatus,
    TelemetrySnapshot,
    TimingPolicy,
)
from edge_runtime.lifecycle import (
    CommandLifecycleBook,
    CommandLifecycleRecord,
    CommandLifecycleState,
    CommandSubmissionResult,
    ExecutionCompletionEvidence,
    RecoveryReadiness,
)
from edge_runtime.safety import (
    DeterministicEdgeSafetyEvaluator,
    EdgeSafetyEvaluationInput,
    FreshnessEvaluation,
    RecoveryReadinessInput,
    evaluate_freshness,
    evaluate_recovery_readiness,
    merge_device_capabilities,
)

__all__ = [
    "AcknowledgementStatus",
    "CommandAcknowledgement",
    "CommandLifecycleBook",
    "CommandLifecycleRecord",
    "CommandLifecycleState",
    "CommandSubmissionResult",
    "DeterministicEdgeSafetyEvaluator",
    "DeviceCapability",
    "DeviceCapabilitySource",
    "EdgeSafetyEvaluationInput",
    "EffectiveDeviceCapability",
    "ExecutionCompletionEvidence",
    "FaultEvent",
    "FaultSeverity",
    "FaultSource",
    "FreshnessEvaluation",
    "OperatingMode",
    "PowerCommand",
    "RecoveryReadiness",
    "RecoveryReadinessInput",
    "RuntimeHealth",
    "RuntimeState",
    "SafetyConstraint",
    "SafetyDecision",
    "SafetyOutcome",
    "SafetyPrecedence",
    "TelemetryQualityStatus",
    "TelemetrySnapshot",
    "TimingPolicy",
    "evaluate_freshness",
    "evaluate_recovery_readiness",
    "merge_device_capabilities",
]
