"""Deterministic P0.2 virtual PCS/BMS and fault-injection contracts.

This package is a caller-stepped software plant simulator.  It owns neither a
transport adapter nor a runtime loop, and it deliberately reuses P0.1 public
contracts for every command, safety, telemetry and lifecycle fact.
"""

from edge_runtime.device_simulator.contracts import (
    DeviceSimulatorConfiguration,
    DeviceSimulatorStep,
    FaultSchedule,
    FaultSpecification,
    FaultTarget,
    FaultType,
    VirtualClock,
)
from edge_runtime.device_simulator.simulator import (
    DeterministicDeviceScenarioHarness,
    DeterministicDeviceSimulator,
    DeviceScenarioTrace,
)

__all__ = [
    "DeterministicDeviceScenarioHarness",
    "DeterministicDeviceSimulator",
    "DeviceScenarioTrace",
    "DeviceSimulatorConfiguration",
    "DeviceSimulatorStep",
    "FaultSchedule",
    "FaultSpecification",
    "FaultTarget",
    "FaultType",
    "VirtualClock",
]
