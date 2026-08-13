"""Runnable deterministic explainable 24-hour physically-aware MPC demo.

The four-point repeating-day forecast is caller-owned demo data only. It is not
a forecast provider and is intentionally kept separate from the daily actual
PV, load, and tariff curves supplied to the simulator.
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from ems_simulator.demo import (
    LOAD_PROFILE_KW,
    PV_PROFILE_KW,
    TARIFF_PROFILE_CNY_PER_KWH,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import (
    ExplainableMPCDailySimulationInput,
    ExplainableMPCDailySimulationResult,
    ExplainableMPCDailySimulationRunner,
)
from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from ems_simulator.output import (
    DailySimulationExport,
    SimulationExportPaths,
    SimulationResultExporter,
)
from ems_strategy import (
    ActuationHandoffBoundary,
    ActuationHandoffResult,
    DecisionProvenance,
    DeterministicExplainableMPCDecisionCSVFileExporter,
    DeterministicExplainableMPCDecisionCSVRowMapper,
    DeterministicExplainableMPCDecisionCSVSerializer,
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    EMSDecision,
    EMSStrategyDescriptor,
    FeasibilityBoundary,
    FeasibleDecision,
    FirstStepMPCCurrentActionExtractor,
    MPCConfiguration,
    MPCDecisionTranslationBoundary,
    MPCDecisionTranslationInput,
    PhysicallyAwareSingleMPCCycleOrchestrator,
)
from forecast import ForecastHorizon, ForecastPoint
from kernel.decision import DecisionIntent as SimulatorDecisionIntent
from kernel.decision import FeasibleDecisionIntent
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationModel,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationSolutionControlPlanBuilder,
    PhysicallyAwarePriceBaselineOptimizer,
    PriceAwareBaselineOptimizationConfiguration,
    PriceAwareBaselineOptimizer,
)
from simulator import BatterySimulationActuation, SimulationStepIdentity

_HOURS_PER_DAY = 24
_HORIZON_POINTS = 4
_START = datetime(2026, 1, 1, tzinfo=UTC)


class _DemoMPCDecisionTranslator(MPCDecisionTranslationBoundary):
    """Translate the exact selected plan step without adding demo policy."""

    __slots__ = ()

    def translate(self, translation: MPCDecisionTranslationInput) -> EMSDecision:
        step = translation.current_action.selected_step
        context = (
            translation.current_action.source_plan.source_result.source_problem.context
        )
        return EMSDecision(
            context,
            translation.source_strategy,
            step.intent,
            step.requested_power_kw,
        )


class _DemoPassThroughFeasibility(FeasibilityBoundary):
    """Preserve the required downstream seam; planning revision is upstream."""

    __slots__ = ()

    def evaluate(
        self,
        decision: EMSDecision,
        *,
        provenance: DecisionProvenance,
    ) -> FeasibleDecision:
        return FeasibleDecision(
            decision,
            provenance,
            decision.intent,
            decision.requested_power_kw,
        )


class _DemoSimulationHandoff(ActuationHandoffBoundary):
    """Apply the frozen semantic-action to signed simulator-power mapping."""

    __slots__ = ()

    def _handoff(self, feasible_decision: FeasibleDecision) -> ActuationHandoffResult:
        magnitude = feasible_decision.approved_power_kw
        power_kw = (
            magnitude
            if feasible_decision.approved_intent.action == "charge"
            else -magnitude
            if feasible_decision.approved_intent.action == "discharge"
            else 0.0
        )
        return ActuationHandoffResult(
            feasible_decision,
            BatterySimulationActuation(
                FeasibleDecisionIntent(SimulatorDecisionIntent(power_kw)),
                power_kw,
            ),
        )


@dataclass(frozen=True, slots=True)
class ExplainableMPCDemoExecutionResult:
    """Preserve exact completed demo artifacts rather than only output paths."""

    source_input: ExplainableMPCDailySimulationInput
    daily_result: ExplainableMPCDailySimulationResult
    simulation_export: DailySimulationExport
    simulation_paths: SimulationExportPaths
    decision_csv_path: Path
    summary_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ExplainableMPCDailySimulationInput):
            raise TypeError(
                "source_input must be an ExplainableMPCDailySimulationInput"
            )
        if not isinstance(self.daily_result, ExplainableMPCDailySimulationResult):
            raise TypeError(
                "daily_result must be an ExplainableMPCDailySimulationResult"
            )
        if not isinstance(self.simulation_export, DailySimulationExport):
            raise TypeError("simulation_export must be a DailySimulationExport")
        if not isinstance(self.simulation_paths, SimulationExportPaths):
            raise TypeError("simulation_paths must be a SimulationExportPaths")
        if not isinstance(self.decision_csv_path, Path):
            raise TypeError("decision_csv_path must be a pathlib.Path")
        if not isinstance(self.summary_path, Path):
            raise TypeError("summary_path must be a pathlib.Path")
        if self.daily_result.source_input is not self.source_input:
            raise ValueError("daily_result must preserve exact source_input")
        if (
            self.simulation_export.source_result
            is not self.daily_result.simulation_result
        ):
            raise ValueError("simulation_export must preserve exact daily simulation")
        if self.decision_csv_path is not self.source_input.decision_csv_output_path:
            raise ValueError("decision_csv_path must preserve exact source path")


def create_demo_input(output_directory: Path) -> ExplainableMPCDailySimulationInput:
    """Create one deterministic demo-owned daily MPC input without execution."""
    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    daily_input = _daily_input()
    capability = CapabilityDescriptor("mpc", "Physically-aware price MPC.")
    match_collection = CapabilityMatchCollection(
        RequiredCapabilityCollection((capability,)),
        AvailableCapabilityCollection((capability,)),
        (CapabilityMatch(capability, capability),),
        (),
    )
    active = ActiveCapabilityCollection(match_collection, (capability,), ())
    integration_input = EMSIntegrationScenarioInput(
        daily_input,
        ObjectiveCapabilityActivationComposition(
            ObjectiveDescriptor("energy_cost", "Minimize imported energy cost."),
            active,
        ),
        capability,
        3.0,
        5.0,
        0.0,
    )
    configuration = MPCConfiguration(_HORIZON_POINTS, 3600.0)
    return ExplainableMPCDailySimulationInput(
        integration_input,
        _forecast_horizons(daily_input),
        configuration,
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
        EMSStrategyDescriptor("physically-aware-price-mpc", "1.0"),
        BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95),
        "zh-CN",
        output_directory / "mpc_decisions.csv",
    )


def run_demo(output_directory: Path) -> ExplainableMPCDemoExecutionResult:
    """Run one deterministic finite day and write all five demo outputs."""
    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    source_input = create_demo_input(output_directory)
    result = _runner().run(source_input)
    simulation_export = SimulationResultExporter.export(result.simulation_result)
    simulation_paths = SimulationResultExporter.write_files(
        simulation_export, output_directory
    )
    summary_path = output_directory / "daily_summary.txt"
    summary_path.write_text(_summary_text(result, simulation_export), encoding="utf-8")
    return ExplainableMPCDemoExecutionResult(
        source_input,
        result,
        simulation_export,
        simulation_paths,
        source_input.decision_csv_output_path,
        summary_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explainable daily MPC demo CLI."""
    parser = argparse.ArgumentParser(description="EOS explainable MPC daily demo")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output"),
        help="directory for deterministic demo outputs",
    )
    arguments = parser.parse_args(argv)
    execution = run_demo(arguments.output_dir)
    print(f"Explainable MPC decisions: {execution.decision_csv_path}")
    print(f"Simulation CSV: {execution.simulation_paths.csv_path}")
    print(f"Power curve: {execution.simulation_paths.power_curve_path}")
    print(f"SOC curve: {execution.simulation_paths.soc_curve_path}")
    print(f"Daily summary: {execution.summary_path}")
    return 0


def _daily_input() -> DailySimulationScenarioInput:
    step_identities = tuple(
        SimulationStepIdentity(hour, 3600.0, _START + timedelta(hours=hour))
        for hour in range(_HOURS_PER_DAY)
    )
    return DailySimulationScenarioInput(
        step_identities,
        PV_PROFILE_KW,
        LOAD_PROFILE_KW,
        TARIFF_PROFILE_CNY_PER_KWH,
        BatteryParameters(10.0, 3.0, 3.0, 0.95, 0.95, 0.20),
        0.50,
    )


def _forecast_horizons(
    daily_input: DailySimulationScenarioInput,
) -> tuple[ForecastHorizon, ...]:
    """Create the demo-only explicit four-point repeating-day perfect forecast."""
    horizons: list[ForecastHorizon] = []
    for hour, identity in enumerate(daily_input.step_identities):
        timestamp = identity.timestamp
        if timestamp is None:
            raise ValueError("demo step timestamps must be present")
        points = tuple(
            ForecastPoint(
                timestamp + timedelta(hours=offset),
                PV_PROFILE_KW[(hour + offset) % _HOURS_PER_DAY],
                LOAD_PROFILE_KW[(hour + offset) % _HOURS_PER_DAY],
                TARIFF_PROFILE_CNY_PER_KWH[(hour + offset) % _HOURS_PER_DAY],
            )
            for offset in range(_HORIZON_POINTS)
        )
        horizons.append(ForecastHorizon(points))
    return tuple(horizons)


def _runner() -> ExplainableMPCDailySimulationRunner:
    physical_optimizer = PhysicallyAwarePriceBaselineOptimizer(
        PriceAwareBaselineOptimizer(
            PriceAwareBaselineOptimizationConfiguration(0.30, 0.90, 3.0)
        ),
        DeterministicBatterySOCHorizonProjector(),
        DeterministicBatterySOCHorizonConstraintEvaluator(),
        DeterministicBatteryPowerHorizonConstraintEvaluator(),
        DeterministicBatteryHorizonConstraintAggregator(),
    )
    mpc_cycle = PhysicallyAwareSingleMPCCycleOrchestrator(
        physical_optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DemoMPCDecisionTranslator(),
    )
    return ExplainableMPCDailySimulationRunner(
        mpc_cycle,
        DeterministicMPCDecisionExplanationBuilder(),
        DeterministicMPCDecisionExplanationFormatter(),
        DeterministicExplainableMPCDecisionJournalRecordBuilder(),
        DeterministicExplainableMPCDecisionCSVRowMapper(),
        DeterministicExplainableMPCDecisionCSVSerializer(),
        DeterministicExplainableMPCDecisionCSVFileExporter(),
        _DemoPassThroughFeasibility(),
        _DemoSimulationHandoff(),
    )


def _summary_text(
    result: ExplainableMPCDailySimulationResult,
    simulation_export: DailySimulationExport,
) -> str:
    summary = simulation_export.summary
    records = result.journal_records
    reasons = tuple(reason for record in records for reason in record.revision_reasons)
    final_soc = result.simulation_result.traces[-1].state.battery_result.next_state.soc
    charge_count = sum(record.final_action.action == "charge" for record in records)
    discharge_count = sum(
        record.final_action.action == "discharge" for record in records
    )
    idle_count = sum(record.final_action.action == "idle" for record in records)
    revised_count = sum(record.revision_applied for record in records)
    soc_limited_count = sum(
        reason in ("min_soc_limit", "max_soc_limit") for reason in reasons
    )
    power_limited_count = sum(
        reason in ("charge_power_limit", "discharge_power_limit") for reason in reasons
    )
    return (
        "EOS Explainable MPC Daily Demo Summary\n"
        f"pv_energy_kwh={summary.pv_energy_kwh:.6f}\n"
        f"load_energy_kwh={summary.load_energy_kwh:.6f}\n"
        f"battery_throughput_kwh={summary.battery_throughput_kwh:.6f}\n"
        f"grid_import_energy_kwh={summary.grid_import_energy_kwh:.6f}\n"
        f"grid_export_energy_kwh={summary.grid_export_energy_kwh:.6f}\n"
        f"mpc_charge_decisions={charge_count}\n"
        f"mpc_discharge_decisions={discharge_count}\n"
        f"mpc_idle_decisions={idle_count}\n"
        f"mpc_revised_decisions={revised_count}\n"
        f"mpc_soc_limited_decisions={soc_limited_count}\n"
        f"mpc_power_limited_decisions={power_limited_count}\n"
        f"final_soc={final_soc:.6f}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
