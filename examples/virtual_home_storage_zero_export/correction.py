"""Explicit opt-in PV curtailment for one immutable simulation step."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Literal

from ems_simulator.battery import SimpleBatteryPhysicsModel
from ems_simulator.grid import GridEnergyBalanceSimulationModel
from ems_simulator.load import LoadProfileSimulationModel
from ems_strategy import (
    ActuationHandoffResult,
    DecisionProvenance,
    ZeroExportFeasibility,
)
from simulator import (
    BatterySimulationInput,
    BatterySimulationModelBoundary,
    BatterySimulationResult,
    GridSimulationInput,
    GridSimulationModelBoundary,
    GridSimulationResult,
    LoadSimulationInput,
    LoadSimulationModelBoundary,
    LoadSimulationResult,
    PVSimulationInput,
    PVSimulationModelBoundary,
    PVSimulationResult,
    SimulationExecutionTrace,
    SimulationModelBinding,
    SimulationModelBindingCollection,
    SimulationStepInput,
    SingleStepSimulationExecutor,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)
from simulator.validation import (
    require_non_negative_number,
    require_number,
    require_positive_number,
)

POWER_TOLERANCE_KW = 1e-9
ENERGY_TOLERANCE_KWH = 1e-9
SECONDS_PER_HOUR = 3600.0

Status = Literal["SATISFIED", "REJECTED"]
ReasonCode = Literal[
    "WITHIN_EXPORT_LIMIT",
    "PV_CURTAILED_TO_EXPORT_LIMIT",
    "CURTAILMENT_NOT_AUTHORIZED",
    "NON_PV_EXPORT_CANNOT_BE_CORRECTED",
]


@dataclass(frozen=True, slots=True)
class ZeroExportCurtailmentInput:
    """Relate exact preview facts without changing their source artifacts."""

    zero_export_feasibility: ZeroExportFeasibility
    expected_provenance: DecisionProvenance
    source_handoff: ActuationHandoffResult
    pv_input: PVSimulationInput
    load_result: LoadSimulationResult
    battery_result: BatterySimulationResult
    grid_input: GridSimulationInput
    export_limit_kw: float
    curtailment_allowed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.zero_export_feasibility, ZeroExportFeasibility):
            raise TypeError("zero_export_feasibility must be a ZeroExportFeasibility")
        if not isinstance(self.expected_provenance, DecisionProvenance):
            raise TypeError("expected_provenance must be a DecisionProvenance")
        if not isinstance(self.source_handoff, ActuationHandoffResult):
            raise TypeError("source_handoff must be an ActuationHandoffResult")
        if (
            self.zero_export_feasibility.source_provenance
            is not self.expected_provenance
        ):
            raise ValueError(
                "zero_export_feasibility must preserve exact expected provenance"
            )
        if (
            self.source_handoff.source_feasible_decision.source_provenance
            is not self.expected_provenance
        ):
            raise ValueError("source_handoff must preserve exact expected provenance")
        if not isinstance(self.pv_input, PVSimulationInput):
            raise TypeError("pv_input must be a PVSimulationInput")
        if not isinstance(self.load_result, LoadSimulationResult):
            raise TypeError("load_result must be a LoadSimulationResult")
        if not isinstance(self.battery_result, BatterySimulationResult):
            raise TypeError("battery_result must be a BatterySimulationResult")
        if not isinstance(self.grid_input, GridSimulationInput):
            raise TypeError("grid_input must be a GridSimulationInput")
        if not isinstance(self.curtailment_allowed, bool):
            raise TypeError("curtailment_allowed must be a bool")

        identity = self.pv_input.step_identity
        if (
            self.source_handoff.actuation
            is not self.battery_result.simulation_input.actuation
        ):
            raise ValueError("source_handoff must preserve exact battery actuation")
        for field_name, candidate in (
            ("load_result", self.load_result.simulation_input.step_identity),
            ("battery_result", self.battery_result.simulation_input.step_identity),
            ("grid_input", self.grid_input.step_identity),
        ):
            if candidate is not identity:
                raise ValueError(f"{field_name} must preserve exact step identity")
        decision_context = (
            self.zero_export_feasibility.source_decision.source_context.source_context
        )
        if (
            identity.timestamp is None
            or identity.timestamp != decision_context.timestamp
        ):
            raise ValueError("step timestamp must match exact decision context")
        export_limit = require_non_negative_number(
            self.export_limit_kw, "export_limit_kw"
        )
        if export_limit != decision_context.export_limit_kw:
            raise ValueError("export_limit_kw must match exact decision context")
        object.__setattr__(self, "export_limit_kw", export_limit)


@dataclass(frozen=True, slots=True)
class ZeroExportCurtailmentEvidence:
    """Record a correction verdict; rejected verdicts contain no claimed output."""

    source_input: ZeroExportCurtailmentInput
    status: Status
    reason_code: ReasonCode
    pv_available_kw: float
    load_served_kw: float
    battery_actual_power_kw: float
    export_limit_kw: float
    duration_hours: float
    pv_utilized_kw: float | None
    pv_curtailed_kw: float | None
    resulting_grid_power_kw: float | None
    pv_available_energy_kwh: float
    pv_utilized_energy_kwh: float | None
    pv_curtailed_energy_kwh: float | None
    load_served_energy_kwh: float
    battery_exchange_energy_kwh: float
    resulting_grid_energy_kwh: float | None

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ZeroExportCurtailmentInput):
            raise TypeError("source_input must be a ZeroExportCurtailmentInput")
        if self.status not in ("SATISFIED", "REJECTED"):
            raise ValueError("status must be SATISFIED or REJECTED")
        if self.reason_code not in (
            "WITHIN_EXPORT_LIMIT",
            "PV_CURTAILED_TO_EXPORT_LIMIT",
            "CURTAILMENT_NOT_AUTHORIZED",
            "NON_PV_EXPORT_CANNOT_BE_CORRECTED",
        ):
            raise ValueError("unsupported reason_code")
        for field_name in (
            "pv_available_kw",
            "load_served_kw",
            "export_limit_kw",
            "pv_available_energy_kwh",
            "load_served_energy_kwh",
        ):
            object.__setattr__(
                self,
                field_name,
                require_non_negative_number(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "battery_actual_power_kw",
            require_number(self.battery_actual_power_kw, "battery_actual_power_kw"),
        )
        object.__setattr__(
            self,
            "battery_exchange_energy_kwh",
            require_number(
                self.battery_exchange_energy_kwh,
                "battery_exchange_energy_kwh",
            ),
        )
        object.__setattr__(
            self,
            "duration_hours",
            require_positive_number(self.duration_hours, "duration_hours"),
        )

        expected_source = (
            self.source_input.pv_input.available_power_kw,
            self.source_input.load_result.actual_power_kw,
            self.source_input.battery_result.actual_power_kw,
            self.source_input.export_limit_kw,
            self.source_input.pv_input.step_identity.duration_seconds
            / SECONDS_PER_HOUR,
        )
        actual_source = (
            self.pv_available_kw,
            self.load_served_kw,
            self.battery_actual_power_kw,
            self.export_limit_kw,
            self.duration_hours,
        )
        if actual_source != expected_source:
            raise ValueError("evidence must preserve exact source facts")
        expected_available_energy = self.pv_available_kw * self.duration_hours
        if not isclose(
            self.pv_available_energy_kwh,
            expected_available_energy,
            rel_tol=0.0,
            abs_tol=ENERGY_TOLERANCE_KWH,
        ):
            raise ValueError("pv_available_energy_kwh must reconcile")
        if not isclose(
            self.load_served_energy_kwh,
            self.load_served_kw * self.duration_hours,
            rel_tol=0.0,
            abs_tol=ENERGY_TOLERANCE_KWH,
        ):
            raise ValueError("load_served_energy_kwh must reconcile")
        if not isclose(
            self.battery_exchange_energy_kwh,
            self.battery_actual_power_kw * self.duration_hours,
            rel_tol=0.0,
            abs_tol=ENERGY_TOLERANCE_KWH,
        ):
            raise ValueError("battery_exchange_energy_kwh must reconcile")

        outputs = (
            self.pv_utilized_kw,
            self.pv_curtailed_kw,
            self.resulting_grid_power_kw,
            self.pv_utilized_energy_kwh,
            self.pv_curtailed_energy_kwh,
            self.resulting_grid_energy_kwh,
        )
        if self.status == "REJECTED":
            if any(value is not None for value in outputs):
                raise ValueError("rejected evidence must not claim corrected outputs")
            if self.reason_code not in (
                "CURTAILMENT_NOT_AUTHORIZED",
                "NON_PV_EXPORT_CANNOT_BE_CORRECTED",
            ):
                raise ValueError("rejected evidence requires a rejection reason")
            return

        if any(value is None for value in outputs):
            raise ValueError("satisfied evidence requires complete corrected outputs")
        utilized = self.pv_utilized_kw
        curtailed = self.pv_curtailed_kw
        grid = self.resulting_grid_power_kw
        utilized_energy = self.pv_utilized_energy_kwh
        curtailed_energy = self.pv_curtailed_energy_kwh
        grid_energy = self.resulting_grid_energy_kwh
        assert utilized is not None
        assert curtailed is not None
        assert grid is not None
        assert utilized_energy is not None
        assert curtailed_energy is not None
        assert grid_energy is not None
        utilized = require_non_negative_number(utilized, "pv_utilized_kw")
        curtailed = require_non_negative_number(curtailed, "pv_curtailed_kw")
        grid = require_number(grid, "resulting_grid_power_kw")
        utilized_energy = require_non_negative_number(
            utilized_energy, "pv_utilized_energy_kwh"
        )
        curtailed_energy = require_non_negative_number(
            curtailed_energy, "pv_curtailed_energy_kwh"
        )
        grid_energy = require_number(grid_energy, "resulting_grid_energy_kwh")
        if utilized > self.pv_available_kw:
            raise ValueError("pv_utilized_kw must be within available PV")
        if not isclose(
            self.pv_available_kw,
            utilized + curtailed,
            rel_tol=0.0,
            abs_tol=POWER_TOLERANCE_KW,
        ):
            raise ValueError("PV available must equal utilized plus curtailed")
        expected_grid = self.load_served_kw + self.battery_actual_power_kw - utilized
        if not isclose(
            grid,
            expected_grid,
            rel_tol=0.0,
            abs_tol=POWER_TOLERANCE_KW,
        ):
            raise ValueError("resulting grid power must reconcile")
        if grid < -self.export_limit_kw - POWER_TOLERANCE_KW:
            raise ValueError("resulting grid power exceeds export limit")
        if not isclose(
            utilized_energy,
            utilized * self.duration_hours,
            rel_tol=0.0,
            abs_tol=ENERGY_TOLERANCE_KWH,
        ) or not isclose(
            curtailed_energy,
            curtailed * self.duration_hours,
            rel_tol=0.0,
            abs_tol=ENERGY_TOLERANCE_KWH,
        ):
            raise ValueError("PV energy evidence must reconcile")
        if not isclose(
            self.pv_available_energy_kwh,
            utilized_energy + curtailed_energy,
            rel_tol=0.0,
            abs_tol=ENERGY_TOLERANCE_KWH,
        ):
            raise ValueError("PV available energy must equal utilized plus curtailed")
        if not isclose(
            grid_energy,
            self.load_served_energy_kwh
            + self.battery_exchange_energy_kwh
            - utilized_energy,
            rel_tol=0.0,
            abs_tol=ENERGY_TOLERANCE_KWH,
        ):
            raise ValueError("resulting grid energy must reconcile")
        expected_reason = (
            "WITHIN_EXPORT_LIMIT"
            if curtailed == 0.0
            else "PV_CURTAILED_TO_EXPORT_LIMIT"
        )
        if self.reason_code != expected_reason:
            raise ValueError("reason_code must match curtailment result")


@dataclass(frozen=True, slots=True)
class ZeroExportCurtailmentResult:
    """Return corrected component results only for a satisfied verdict."""

    source_input: ZeroExportCurtailmentInput
    evidence: ZeroExportCurtailmentEvidence
    pv_result: PVSimulationResult | None
    grid_result: GridSimulationResult | None

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ZeroExportCurtailmentInput):
            raise TypeError("source_input must be a ZeroExportCurtailmentInput")
        if not isinstance(self.evidence, ZeroExportCurtailmentEvidence):
            raise TypeError("evidence must be ZeroExportCurtailmentEvidence")
        if self.evidence.source_input is not self.source_input:
            raise ValueError("evidence must preserve exact source input")
        if self.evidence.status == "REJECTED":
            if self.pv_result is not None or self.grid_result is not None:
                raise ValueError(
                    "rejected correction must not create component results"
                )
            return
        if not isinstance(self.pv_result, PVSimulationResult):
            raise TypeError("satisfied correction requires a PVSimulationResult")
        if not isinstance(self.grid_result, GridSimulationResult):
            raise TypeError("satisfied correction requires a GridSimulationResult")
        if self.pv_result.simulation_input is not self.source_input.pv_input:
            raise ValueError("PV result must preserve exact PV input")
        if self.grid_result.simulation_input is not self.source_input.grid_input:
            raise ValueError("Grid result must preserve exact Grid input")
        if self.pv_result.actual_power_kw != self.evidence.pv_utilized_kw:
            raise ValueError("PV result must equal evidenced utilized PV")
        if (
            self.grid_result.actual_grid_power_kw
            != self.evidence.resulting_grid_power_kw
        ):
            raise ValueError("Grid result must equal evidenced grid power")


class DeterministicZeroExportCurtailment:
    """Compute one opt-in, curtailment-only virtual correction without state."""

    __slots__ = ()

    @staticmethod
    def evaluate(
        source_input: ZeroExportCurtailmentInput,
    ) -> ZeroExportCurtailmentResult:
        if not isinstance(source_input, ZeroExportCurtailmentInput):
            raise TypeError("source_input must be a ZeroExportCurtailmentInput")
        available = source_input.pv_input.available_power_kw
        load = source_input.load_result.actual_power_kw
        battery = source_input.battery_result.actual_power_kw
        export_limit = source_input.export_limit_kw
        duration_hours = (
            source_input.pv_input.step_identity.duration_seconds / SECONDS_PER_HOUR
        )
        utilized_limit = load + battery + export_limit
        if utilized_limit < -POWER_TOLERANCE_KW:
            return _rejected(
                source_input,
                "NON_PV_EXPORT_CANNOT_BE_CORRECTED",
                available,
                load,
                battery,
                export_limit,
                duration_hours,
            )

        utilized = min(available, max(0.0, utilized_limit))
        curtailed = available - utilized
        if curtailed <= POWER_TOLERANCE_KW:
            utilized = available
            curtailed = 0.0
        if curtailed > 0.0 and not source_input.curtailment_allowed:
            return _rejected(
                source_input,
                "CURTAILMENT_NOT_AUTHORIZED",
                available,
                load,
                battery,
                export_limit,
                duration_hours,
            )

        grid = load + battery - utilized
        reason: ReasonCode = (
            "WITHIN_EXPORT_LIMIT"
            if curtailed == 0.0
            else "PV_CURTAILED_TO_EXPORT_LIMIT"
        )
        evidence = ZeroExportCurtailmentEvidence(
            source_input,
            "SATISFIED",
            reason,
            available,
            load,
            battery,
            export_limit,
            duration_hours,
            utilized,
            curtailed,
            grid,
            available * duration_hours,
            utilized * duration_hours,
            curtailed * duration_hours,
            load * duration_hours,
            battery * duration_hours,
            grid * duration_hours,
        )
        pv_result = PVSimulationResult(source_input.pv_input, utilized)
        grid_result = GridEnergyBalanceSimulationModel(
            pv_result,
            source_input.load_result,
            source_input.battery_result,
        ).simulate(source_input.grid_input)
        return ZeroExportCurtailmentResult(
            source_input, evidence, pv_result, grid_result
        )


def _rejected(
    source_input: ZeroExportCurtailmentInput,
    reason: ReasonCode,
    available: float,
    load: float,
    battery: float,
    export_limit: float,
    duration_hours: float,
) -> ZeroExportCurtailmentResult:
    evidence = ZeroExportCurtailmentEvidence(
        source_input,
        "REJECTED",
        reason,
        available,
        load,
        battery,
        export_limit,
        duration_hours,
        None,
        None,
        None,
        available * duration_hours,
        None,
        None,
        load * duration_hours,
        battery * duration_hours,
        None,
    )
    return ZeroExportCurtailmentResult(source_input, evidence, None, None)


@dataclass(frozen=True, slots=True)
class OptInZeroExportStepResult:
    """Atomic virtual step: rejected correction has no completed trace."""

    source_step: SimulationStepInput
    correction: ZeroExportCurtailmentResult
    simulation_trace: SimulationExecutionTrace | None

    def __post_init__(self) -> None:
        if not isinstance(self.source_step, SimulationStepInput):
            raise TypeError("source_step must be a SimulationStepInput")
        if not isinstance(self.correction, ZeroExportCurtailmentResult):
            raise TypeError("correction must be a ZeroExportCurtailmentResult")
        correction_input = self.correction.source_input
        if (
            correction_input.pv_input is not self.source_step.pv_input
            or correction_input.load_result.simulation_input
            is not self.source_step.load_input
            or correction_input.battery_result.simulation_input
            is not self.source_step.battery_input
            or correction_input.grid_input is not self.source_step.grid_input
        ):
            raise ValueError("correction must preserve all exact source step inputs")
        if self.correction.evidence.status == "REJECTED":
            if self.simulation_trace is not None:
                raise ValueError("rejected step must not have a completed trace")
            return
        if not isinstance(self.simulation_trace, SimulationExecutionTrace):
            raise TypeError("satisfied step requires a SimulationExecutionTrace")
        if self.simulation_trace.simulation_input is not self.source_step:
            raise ValueError("trace must preserve exact source step")
        if (
            self.simulation_trace.state.pv_result is not self.correction.pv_result
            or self.simulation_trace.state.grid_result
            is not self.correction.grid_result
            or self.simulation_trace.state.load_result
            is not correction_input.load_result
            or self.simulation_trace.state.battery_result
            is not correction_input.battery_result
        ):
            raise ValueError("trace must preserve exact preview and correction results")


class OptInZeroExportStepExecutor:
    """Preview battery/load, correct PV, then atomically form a virtual trace."""

    __slots__ = ()

    @staticmethod
    def execute(
        source_step: SimulationStepInput,
        *,
        zero_export_feasibility: ZeroExportFeasibility,
        expected_provenance: DecisionProvenance,
        source_handoff: ActuationHandoffResult,
        battery_model: SimpleBatteryPhysicsModel,
        export_limit_kw: float,
        curtailment_allowed: bool,
    ) -> OptInZeroExportStepResult:
        if not isinstance(source_step, SimulationStepInput):
            raise TypeError("source_step must be a SimulationStepInput")
        if not isinstance(battery_model, SimpleBatteryPhysicsModel):
            raise TypeError("battery_model must be a SimpleBatteryPhysicsModel")
        load_result = LoadProfileSimulationModel().simulate(source_step.load_input)
        battery_result = battery_model.simulate(source_step.battery_input)
        correction_input = ZeroExportCurtailmentInput(
            zero_export_feasibility,
            expected_provenance,
            source_handoff,
            source_step.pv_input,
            load_result,
            battery_result,
            source_step.grid_input,
            export_limit_kw,
            curtailment_allowed,
        )
        correction = DeterministicZeroExportCurtailment.evaluate(correction_input)
        if correction.evidence.status == "REJECTED":
            return OptInZeroExportStepResult(source_step, correction, None)

        assert correction.pv_result is not None
        assert correction.grid_result is not None
        tariff_result = TariffSimulationResult(
            source_step.tariff_input,
            source_step.tariff_input.import_price_cny_per_kwh,
            source_step.tariff_input.export_price_cny_per_kwh,
        )
        bindings = SimulationModelBindingCollection(
            (
                SimulationModelBinding(
                    PVSimulationModelBoundary,
                    _ExactPVResultModel(correction.pv_result),
                ),
                SimulationModelBinding(
                    LoadSimulationModelBoundary,
                    _ExactLoadResultModel(load_result),
                ),
                SimulationModelBinding(
                    TariffSimulationModelBoundary,
                    _ExactTariffResultModel(tariff_result),
                ),
                SimulationModelBinding(
                    BatterySimulationModelBoundary,
                    _ExactBatteryResultModel(battery_result),
                ),
                SimulationModelBinding(
                    GridSimulationModelBoundary,
                    _ExactGridResultModel(correction.grid_result),
                ),
            )
        )
        step_result = SingleStepSimulationExecutor.execute(source_step, bindings)
        trace = SimulationExecutionTrace.create(bindings, step_result)
        return OptInZeroExportStepResult(source_step, correction, trace)


@dataclass(frozen=True, slots=True)
class _ExactPVResultModel(PVSimulationModelBoundary):
    result: PVSimulationResult

    def simulate(self, simulation_input: PVSimulationInput) -> PVSimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be exact PV input")
        return self.result


@dataclass(frozen=True, slots=True)
class _ExactLoadResultModel(LoadSimulationModelBoundary):
    result: LoadSimulationResult

    def simulate(self, simulation_input: LoadSimulationInput) -> LoadSimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be exact Load input")
        return self.result


@dataclass(frozen=True, slots=True)
class _ExactTariffResultModel(TariffSimulationModelBoundary):
    result: TariffSimulationResult

    def simulate(
        self, simulation_input: TariffSimulationInput
    ) -> TariffSimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be exact Tariff input")
        return self.result


@dataclass(frozen=True, slots=True)
class _ExactBatteryResultModel(BatterySimulationModelBoundary):
    result: BatterySimulationResult

    def simulate(
        self, simulation_input: BatterySimulationInput
    ) -> BatterySimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be exact Battery input")
        return self.result


@dataclass(frozen=True, slots=True)
class _ExactGridResultModel(GridSimulationModelBoundary):
    result: GridSimulationResult

    def simulate(self, simulation_input: GridSimulationInput) -> GridSimulationResult:
        if simulation_input is not self.result.simulation_input:
            raise ValueError("simulation_input must be exact Grid input")
        return self.result
