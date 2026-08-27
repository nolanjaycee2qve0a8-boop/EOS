"""Abstract P0.4 device port and deterministic scripted contract adapter."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import NoReturn, SupportsIndex

from edge_runtime.device_adapter.contracts import (
    DeviceAckObservation,
    DeviceActualTelemetryObservation,
    DeviceAdapterFailure,
    DeviceObservation,
    DeviceTransmissionEvidence,
    DeviceTransmissionRequest,
    TransmissionStatus,
)
from edge_runtime.validation import require_aware_datetime


class ResidentialDeviceAdapterBoundary(ABC):
    """Transport-neutral fact port.  It owns neither a controller nor a clock."""

    @abstractmethod
    def acquire_observation(self) -> DeviceObservation: ...

    @abstractmethod
    def transmit(
        self, request: DeviceTransmissionRequest
    ) -> DeviceTransmissionEvidence: ...

    @abstractmethod
    def observe_acknowledgement(self) -> DeviceAckObservation: ...

    @abstractmethod
    def observe_actual_telemetry(self) -> DeviceActualTelemetryObservation: ...


@dataclass(frozen=True, slots=True)
class ScriptedTransmissionOutcome:
    """One explicit test-script response to one transmission invocation."""

    attempted_at: datetime
    status: TransmissionStatus
    failure: DeviceAdapterFailure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attempted_at",
            require_aware_datetime(self.attempted_at, "attempted_at"),
        )
        if not isinstance(self.status, TransmissionStatus):
            raise TypeError("status must be TransmissionStatus")
        if self.failure is not None and not isinstance(
            self.failure, DeviceAdapterFailure
        ):
            raise TypeError("failure must be DeviceAdapterFailure or None")
        if (self.status is TransmissionStatus.TRANSMITTED) != (self.failure is None):
            raise ValueError("scripted status/failure mismatch")


class ScriptedResidentialDeviceAdapter(ResidentialDeviceAdapterBoundary):
    """No-network/no-thread test double with no retained command/request cache."""

    def __init__(
        self,
        *,
        observations: tuple[DeviceObservation, ...],
        transmission_outcomes: tuple[ScriptedTransmissionOutcome, ...],
        acknowledgements: tuple[DeviceAckObservation, ...],
        actual_telemetry: tuple[DeviceActualTelemetryObservation, ...],
    ) -> None:
        expected = (
            ("observations", observations, DeviceObservation),
            (
                "transmission_outcomes",
                transmission_outcomes,
                ScriptedTransmissionOutcome,
            ),
            ("acknowledgements", acknowledgements, DeviceAckObservation),
            ("actual_telemetry", actual_telemetry, DeviceActualTelemetryObservation),
        )
        for name, values, item_type in expected:
            if not isinstance(values, tuple) or any(
                not isinstance(item, item_type) for item in values
            ):
                raise TypeError(f"{name} must be tuple of {item_type.__name__}")
        self._observations = observations
        self._outcomes = transmission_outcomes
        self._acknowledgements = acknowledgements
        self._actual = actual_telemetry
        self._observation_index = 0
        self._outcome_index = 0
        self._ack_index = 0
        self._actual_index = 0
        self._transmission_attempt_count = 0

    @property
    def transmission_attempt_count(self) -> int:
        return self._transmission_attempt_count

    @staticmethod
    def _next(values: tuple[object, ...], index: int, operation: str) -> object:
        if index >= len(values):
            raise LookupError(f"script exhausted for {operation}")
        return values[index]

    def acquire_observation(self) -> DeviceObservation:
        item = self._next(self._observations, self._observation_index, "observation")
        self._observation_index += 1
        assert isinstance(item, DeviceObservation)
        return item

    def transmit(
        self, request: DeviceTransmissionRequest
    ) -> DeviceTransmissionEvidence:
        if not isinstance(request, DeviceTransmissionRequest):
            raise TypeError("adapter transmit requires DeviceTransmissionRequest")
        if request._used:
            raise ValueError("DeviceTransmissionRequest is already consumed")
        item = self._next(self._outcomes, self._outcome_index, "transmission")
        assert isinstance(item, ScriptedTransmissionOutcome)
        request._consume_once()
        self._outcome_index += 1
        self._transmission_attempt_count += 1
        return DeviceTransmissionEvidence.from_request(
            request,
            attempted_at=item.attempted_at,
            status=item.status,
            failure=item.failure,
        )

    def observe_acknowledgement(self) -> DeviceAckObservation:
        item = self._next(self._acknowledgements, self._ack_index, "acknowledgement")
        self._ack_index += 1
        assert isinstance(item, DeviceAckObservation)
        return item

    def observe_actual_telemetry(self) -> DeviceActualTelemetryObservation:
        item = self._next(self._actual, self._actual_index, "actual telemetry")
        self._actual_index += 1
        assert isinstance(item, DeviceActualTelemetryObservation)
        return item

    def __copy__(self) -> NoReturn:
        raise TypeError("ScriptedResidentialDeviceAdapter cannot be copied")

    def __deepcopy__(self, memo: object) -> NoReturn:
        raise TypeError("ScriptedResidentialDeviceAdapter cannot be copied")

    def __reduce__(self) -> NoReturn:
        raise TypeError("ScriptedResidentialDeviceAdapter cannot be serialized")

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        raise TypeError("ScriptedResidentialDeviceAdapter cannot be serialized")
