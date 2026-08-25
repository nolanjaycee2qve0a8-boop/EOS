"""Immutable P0.2 input and evidence contracts for deterministic device steps."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import ClassVar

from edge_runtime import (
    CommandAcknowledgement,
    DeviceCapability,
    FaultEvent,
    PowerCommand,
    RuntimeHealth,
    SafetyDecision,
    TelemetrySnapshot,
    TimingPolicy,
)
from edge_runtime.validation import (
    SerializableContract,
    parse_utc_datetime,
    require_aware_datetime,
    require_exact_fields,
    require_fraction,
    require_non_empty_string,
    require_non_negative_number,
    require_number,
    require_optional_aware_datetime,
    require_positive_timedelta,
    utc_isoformat,
)


class FaultTarget(StrEnum):
    """The virtual authority whose facts or response a fault changes."""

    PCS = "pcs"
    BMS = "bms"
    COMMAND_CHANNEL = "command_channel"
    TELEMETRY = "telemetry"
    CAPABILITY = "capability"
    EDGE = "edge"


class FaultType(StrEnum):
    """P0.2 finite fault vocabulary; no protocol or hardware interpretation."""

    DISCONNECTED = "disconnected"
    UNAVAILABLE = "unavailable"
    TELEMETRY_FROZEN = "telemetry_frozen"
    CAPABILITY_STALE = "capability_stale"
    CHARGE_DERATE = "charge_derate"
    DISCHARGE_DERATE = "discharge_derate"
    CHARGE_PROHIBITED = "charge_prohibited"
    DISCHARGE_PROHIBITED = "discharge_prohibited"
    CRITICAL_FAULT = "critical_fault"
    WARNING_FAULT = "warning_fault"
    ESTOP = "estop"
    ACK_REJECTED = "ack_rejected"
    ACK_DROPPED = "ack_dropped"
    ACK_DELAYED = "ack_delayed"
    STUCK_AT_ZERO = "stuck_at_zero"
    STUCK_AT_PREVIOUS_POWER = "stuck_at_previous_power"
    ACTUAL_POWER_DEVIATION = "actual_power_deviation"
    SOC_UNKNOWN = "soc_unknown"


@dataclass(frozen=True, slots=True)
class _FaultCompatibility:
    """One auditable P0.2 fault whitelist entry."""

    targets: frozenset[FaultTarget]
    required_parameters: frozenset[str] = frozenset()
    optional_parameters: frozenset[str] = frozenset()


_DEVICE_TARGETS = frozenset({FaultTarget.BMS, FaultTarget.PCS})
_ACK_TARGETS = frozenset({FaultTarget.PCS, FaultTarget.COMMAND_CHANNEL})
_FAULT_COMPATIBILITY: dict[FaultType, _FaultCompatibility] = {
    FaultType.DISCONNECTED: _FaultCompatibility(
        frozenset({FaultTarget.BMS, FaultTarget.PCS, FaultTarget.COMMAND_CHANNEL})
    ),
    FaultType.UNAVAILABLE: _FaultCompatibility(
        frozenset({FaultTarget.BMS, FaultTarget.PCS, FaultTarget.COMMAND_CHANNEL})
    ),
    FaultType.TELEMETRY_FROZEN: _FaultCompatibility(frozenset({FaultTarget.TELEMETRY})),
    FaultType.CAPABILITY_STALE: _FaultCompatibility(
        frozenset({FaultTarget.BMS, FaultTarget.PCS, FaultTarget.CAPABILITY})
    ),
    FaultType.CHARGE_DERATE: _FaultCompatibility(
        _DEVICE_TARGETS, frozenset({"factor"})
    ),
    FaultType.DISCHARGE_DERATE: _FaultCompatibility(
        _DEVICE_TARGETS, frozenset({"factor"})
    ),
    FaultType.CHARGE_PROHIBITED: _FaultCompatibility(_DEVICE_TARGETS),
    FaultType.DISCHARGE_PROHIBITED: _FaultCompatibility(_DEVICE_TARGETS),
    FaultType.CRITICAL_FAULT: _FaultCompatibility(
        frozenset({FaultTarget.BMS, FaultTarget.PCS, FaultTarget.EDGE})
    ),
    FaultType.WARNING_FAULT: _FaultCompatibility(
        frozenset({FaultTarget.BMS, FaultTarget.PCS, FaultTarget.EDGE})
    ),
    FaultType.ESTOP: _FaultCompatibility(
        frozenset({FaultTarget.PCS, FaultTarget.EDGE})
    ),
    FaultType.ACK_REJECTED: _FaultCompatibility(_ACK_TARGETS),
    FaultType.ACK_DROPPED: _FaultCompatibility(_ACK_TARGETS),
    FaultType.ACK_DELAYED: _FaultCompatibility(_ACK_TARGETS, frozenset({"seconds"})),
    FaultType.STUCK_AT_ZERO: _FaultCompatibility(frozenset({FaultTarget.PCS})),
    FaultType.STUCK_AT_PREVIOUS_POWER: _FaultCompatibility(
        frozenset({FaultTarget.PCS})
    ),
    FaultType.ACTUAL_POWER_DEVIATION: _FaultCompatibility(
        frozenset({FaultTarget.PCS}), frozenset({"factor"})
    ),
    FaultType.SOC_UNKNOWN: _FaultCompatibility(
        frozenset({FaultTarget.BMS, FaultTarget.TELEMETRY})
    ),
}


def _validate_fault_compatibility(
    fault_type: FaultType,
    target: FaultTarget,
    parameters: tuple[tuple[str, float], ...],
) -> None:
    compatibility = _FAULT_COMPATIBILITY[fault_type]
    if target not in compatibility.targets:
        raise ValueError(f"{fault_type.value} is not valid for target {target.value}")
    names = frozenset(name for name, _ in parameters)
    allowed = compatibility.required_parameters | compatibility.optional_parameters
    if missing := compatibility.required_parameters - names:
        raise ValueError(f"{fault_type.value} is missing parameters: {sorted(missing)}")
    if extra := names - allowed:
        raise ValueError(
            f"{fault_type.value} has unsupported parameters: {sorted(extra)}"
        )
    values = dict(parameters)
    if "factor" in values and not 0 <= values["factor"] <= 1:
        raise ValueError("fault factor must be in [0, 1]")
    if "seconds" in values and values["seconds"] < 0:
        raise ValueError("fault delay seconds must be non-negative")


def _require_parameters(value: object) -> tuple[tuple[str, float], ...]:
    if not isinstance(value, tuple):
        raise TypeError("parameters must be a tuple")
    parsed: list[tuple[str, float]] = []
    for item in value:
        if not isinstance(item, tuple) or len(item) != 2:
            raise TypeError("parameters must contain (name, value) pairs")
        name, number = item
        parsed.append(
            (
                require_non_empty_string(name, "parameter name"),
                require_number(number, f"parameter {name}"),
            )
        )
    if len({name for name, _ in parsed}) != len(parsed):
        raise ValueError("parameters must have unique names")
    if tuple(sorted(parsed, key=lambda item: item[0])) != tuple(parsed):
        raise ValueError("parameters must be sorted by name")
    return tuple(parsed)


@dataclass(frozen=True, slots=True)
class FaultSpecification:
    """One immutable, caller-timed P0.2 fault without a mutable manifest."""

    fault_id: str
    fault_type: FaultType
    target: FaultTarget
    activation_at: datetime
    clear_at: datetime | None
    parameters: tuple[tuple[str, float], ...]
    description: str

    SCHEMA_VERSION: ClassVar[str] = "edge-device-fault-specification/v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fault_id", require_non_empty_string(self.fault_id, "fault_id")
        )
        if not isinstance(self.fault_type, FaultType):
            raise TypeError("fault_type must be a FaultType")
        if not isinstance(self.target, FaultTarget):
            raise TypeError("target must be a FaultTarget")
        object.__setattr__(
            self,
            "activation_at",
            require_aware_datetime(self.activation_at, "activation_at"),
        )
        object.__setattr__(
            self, "clear_at", require_optional_aware_datetime(self.clear_at, "clear_at")
        )
        if self.clear_at is not None and self.clear_at <= self.activation_at:
            raise ValueError("clear_at must be later than activation_at")
        object.__setattr__(self, "parameters", _require_parameters(self.parameters))
        _validate_fault_compatibility(self.fault_type, self.target, self.parameters)
        object.__setattr__(
            self,
            "description",
            require_non_empty_string(self.description, "description"),
        )

    def parameter(self, name: str, default: float) -> float:
        """Return one explicit numeric parameter without implicit coercion."""
        return dict(self.parameters).get(name, default)

    def active_at(self, at: datetime) -> bool:
        now = require_aware_datetime(at, "at")
        return self.activation_at <= now and (
            self.clear_at is None or now < self.clear_at
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "fault_id": self.fault_id,
            "fault_type": self.fault_type.value,
            "target": self.target.value,
            "activation_at": utc_isoformat(self.activation_at),
            "clear_at": None if self.clear_at is None else utc_isoformat(self.clear_at),
            "parameters": [
                {"name": name, "value": value} for name, value in self.parameters
            ],
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, value: object) -> "FaultSpecification":
        payload = require_exact_fields(
            value,
            "FaultSpecification",
            (
                "schema_version",
                "fault_id",
                "fault_type",
                "target",
                "activation_at",
                "clear_at",
                "parameters",
                "description",
            ),
        )
        if payload["schema_version"] != cls.SCHEMA_VERSION:
            raise ValueError("unsupported FaultSpecification schema_version")
        raw_parameters = payload["parameters"]
        if not isinstance(raw_parameters, list):
            raise TypeError("parameters must be a list")
        parameters: list[tuple[str, float]] = []
        for item in raw_parameters:
            parsed = require_exact_fields(item, "fault parameter", ("name", "value"))
            parameters.append(
                (
                    require_non_empty_string(parsed["name"], "parameter name"),
                    require_number(parsed["value"], "parameter value"),
                )
            )
        clear = payload["clear_at"]
        return cls(
            require_non_empty_string(payload["fault_id"], "fault_id"),
            FaultType(require_non_empty_string(payload["fault_type"], "fault_type")),
            FaultTarget(require_non_empty_string(payload["target"], "target")),
            parse_utc_datetime(payload["activation_at"], "activation_at"),
            None if clear is None else parse_utc_datetime(clear, "clear_at"),
            tuple(parameters),
            require_non_empty_string(payload["description"], "description"),
        )


@dataclass(frozen=True, slots=True)
class FaultSchedule:
    """Canonical immutable schedule with documented same-time event ordering."""

    specifications: tuple[FaultSpecification, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.specifications, tuple) or any(
            not isinstance(item, FaultSpecification) for item in self.specifications
        ):
            raise TypeError("specifications must be a tuple of FaultSpecification")
        ids = [item.fault_id for item in self.specifications]
        if len(ids) != len(set(ids)):
            raise ValueError("fault schedule must not contain duplicate fault_id")
        conflicts = [
            (item.target, item.fault_type, item.activation_at)
            for item in self.specifications
        ]
        if len(conflicts) != len(set(conflicts)):
            raise ValueError(
                "fault schedule has conflicting same-time target/type events"
            )
        object.__setattr__(
            self,
            "specifications",
            tuple(
                sorted(
                    self.specifications,
                    key=lambda item: (
                        item.activation_at,
                        item.target.value,
                        item.fault_type.value,
                        item.fault_id,
                    ),
                )
            ),
        )

    def active_at(self, at: datetime) -> tuple[FaultSpecification, ...]:
        """Sample independently at one step start; active interval is [start, clear)."""
        now = require_aware_datetime(at, "at")
        return tuple(item for item in self.specifications if item.active_at(now))


@dataclass(frozen=True, slots=True)
class VirtualClock:
    """Caller-controlled UTC-aware clock; advancing never sleeps or reverses."""

    now: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "now", require_aware_datetime(self.now, "now"))

    def advance(self, duration: timedelta) -> "VirtualClock":
        return VirtualClock(self.now + require_positive_timedelta(duration, "duration"))


@dataclass(frozen=True, slots=True)
class DeviceSimulatorConfiguration:
    """Caller-owned logical plant inputs, not a high-fidelity battery model."""

    capacity_kwh: float
    initial_soc_fraction: float
    min_soc_fraction: float
    max_soc_fraction: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    charge_efficiency: float
    discharge_efficiency: float
    timing_policy: TimingPolicy
    fault_schedule: FaultSchedule = field(default_factory=lambda: FaultSchedule(()))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "capacity_kwh",
            require_non_negative_number(self.capacity_kwh, "capacity_kwh"),
        )
        if self.capacity_kwh <= 0:
            raise ValueError("capacity_kwh must be greater than zero")
        for name in ("initial_soc_fraction", "min_soc_fraction", "max_soc_fraction"):
            object.__setattr__(self, name, require_fraction(getattr(self, name), name))
        if not self.min_soc_fraction < self.max_soc_fraction:
            raise ValueError("min_soc_fraction must be lower than max_soc_fraction")
        if (
            not self.min_soc_fraction
            <= self.initial_soc_fraction
            <= self.max_soc_fraction
        ):
            raise ValueError(
                "initial_soc_fraction must be inside configured SOC bounds"
            )
        for name in ("max_charge_power_kw", "max_discharge_power_kw"):
            object.__setattr__(
                self, name, require_non_negative_number(getattr(self, name), name)
            )
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than zero")
        for name in ("charge_efficiency", "discharge_efficiency"):
            object.__setattr__(self, name, require_number(getattr(self, name), name))
            if not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        if not isinstance(self.timing_policy, TimingPolicy):
            raise TypeError("timing_policy must be a TimingPolicy")
        if not isinstance(self.fault_schedule, FaultSchedule):
            raise TypeError("fault_schedule must be a FaultSchedule")


@dataclass(frozen=True, slots=True)
class DeviceSimulatorStep(SerializableContract):
    """Auditable facts from exactly one caller-driven P0.2 virtual interval."""

    started_at: datetime
    ended_at: datetime
    command: PowerCommand | None
    active_faults: tuple[FaultSpecification, ...]
    bms_capability: DeviceCapability
    pcs_capability: DeviceCapability
    runtime_health: RuntimeHealth
    raw_telemetry: TelemetrySnapshot
    safety_decision: SafetyDecision | None
    acknowledgement: CommandAcknowledgement | None
    command_application_authorized: bool
    actual_telemetry: TelemetrySnapshot
    actual_power_kw: float
    starting_soc_fraction: float
    ending_soc_fraction: float
    boundary_evidence: tuple[str, ...]
    fault_events: tuple[FaultEvent, ...]

    SCHEMA_VERSION: ClassVar[str] = "edge-device-simulator-step/v1"

    def __post_init__(self) -> None:
        for name in ("started_at", "ended_at"):
            object.__setattr__(
                self, name, require_aware_datetime(getattr(self, name), name)
            )
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be later than started_at")
        for name in ("actual_power_kw",):
            object.__setattr__(self, name, require_number(getattr(self, name), name))
        if not isinstance(self.command_application_authorized, bool):
            raise TypeError("command_application_authorized must be a bool")
        if self.command_application_authorized and (
            self.command is None or self.acknowledgement is None
        ):
            raise ValueError(
                "authorized application requires command and acknowledgement"
            )
        if not self.command_application_authorized and self.actual_power_kw != 0.0:
            raise ValueError("unauthorized application requires zero actual_power_kw")
        for name in ("starting_soc_fraction", "ending_soc_fraction"):
            object.__setattr__(self, name, require_fraction(getattr(self, name), name))
        if (
            not isinstance(self.active_faults, tuple)
            or not isinstance(self.boundary_evidence, tuple)
            or not isinstance(self.fault_events, tuple)
        ):
            raise TypeError("step evidence collections must be tuples")
