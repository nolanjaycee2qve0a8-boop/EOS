"""Runnable longer-horizon headroom-aware 24-hour MPC comparison demo.

The 24-point perfect forecast is caller-owned deterministic demo data.  Its
repeating-day wrap only makes the full day visible to each finite planning
cycle; it is neither a forecast provider nor runtime scheduling behavior.
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
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
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.headroom_aware_explainable_mpc_daily import (
    HeadroomAwareExplainableMPCDailySimulationResult,
    HeadroomAwareExplainableMPCDailySimulationRunner,
)
from ems_simulator.input import DailySimulationScenarioInput
from ems_simulator.net_load_mpc_demo import (
    _daily_input,
    _DemoMPCDecisionTranslator,
    _DemoPassThroughFeasibility,
    _DemoSimulationHandoff,
)
from ems_simulator.output import (
    DailyEnergySummary,
    DailySimulationExport,
    SimulationExportPaths,
    SimulationResultExporter,
)
from ems_strategy import (
    DeterministicExplainableMPCDecisionCSVFileExporter,
    DeterministicExplainableMPCDecisionCSVRowMapper,
    DeterministicExplainableMPCDecisionCSVSerializer,
    DeterministicExplainableMPCDecisionJournalRecordBuilder,
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    EMSStrategyDescriptor,
    FirstStepMPCCurrentActionExtractor,
    HeadroomAwareSingleMPCCycleOrchestrator,
    MPCConfiguration,
)
from forecast import ForecastHorizon, ForecastPoint
from objective import ObjectiveCapabilityActivationComposition, ObjectiveDescriptor
from optimization import (
    BatteryOptimizationModel,
    DeterministicBatteryHorizonConstraintAggregator,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonConstraintEvaluator,
    DeterministicBatterySOCHorizonProjector,
    DeterministicExplicitCandidatePhysicalReviser,
    DeterministicHeadroomAwareCandidatePlanner,
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    DeterministicHeadroomAwarePhysicalOptimizer,
    DeterministicPVHeadroomRequirementCalculator,
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationSolutionControlPlanBuilder,
)

_HOURS_PER_DAY = 24
_HORIZON_POINTS = 24


@dataclass(frozen=True, slots=True)
class HeadroomAwareMPCDemoExecutionResult:
    """Retain completed demo evidence and caller-targeted output paths."""

    source_input: ExplainableMPCDailySimulationInput
    daily_result: HeadroomAwareExplainableMPCDailySimulationResult
    simulation_export: DailySimulationExport
    simulation_paths: SimulationExportPaths
    decision_csv_path: Path
    summary_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ExplainableMPCDailySimulationInput):
            raise TypeError(
                "source_input must be an ExplainableMPCDailySimulationInput"
            )
        if not isinstance(
            self.daily_result,
            HeadroomAwareExplainableMPCDailySimulationResult,
        ):
            raise TypeError(
                "daily_result must be a "
                "HeadroomAwareExplainableMPCDailySimulationResult"
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
            raise ValueError("daily_result must preserve exact source input")
        if (
            self.simulation_export.source_result
            is not self.daily_result.simulation_result
        ):
            raise ValueError("simulation export must preserve exact simulation result")
        if self.decision_csv_path is not self.source_input.decision_csv_output_path:
            raise ValueError("decision CSV path must preserve exact source path")


def create_demo_input(output_directory: Path) -> ExplainableMPCDailySimulationInput:
    """Create one explicit longer-horizon headroom-aware daily input."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    daily_input = _daily_input()
    capability = CapabilityDescriptor(
        "headroom-aware-net-load-mpc",
        "Headroom-aware physically-revised net-load MPC.",
    )
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
    return ExplainableMPCDailySimulationInput(
        integration_input,
        _forecast_horizons(daily_input),
        MPCConfiguration(_HORIZON_POINTS, 3600.0),
        OptimizationObjectiveCollection(
            (OptimizationObjective("energy_cost", "minimize"),)
        ),
        EMSStrategyDescriptor("headroom-aware-net-load-mpc", "1.0"),
        BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95),
        "zh-CN",
        output_directory / "mpc_decisions.csv",
    )


def run_demo(output_directory: Path) -> HeadroomAwareMPCDemoExecutionResult:
    """Execute the finite comparison day and write its five output files."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    source_input = create_demo_input(output_directory)
    daily_result = _runner().run(source_input)
    simulation_export = SimulationResultExporter.export(daily_result.simulation_result)
    simulation_paths = SimulationResultExporter.write_files(
        simulation_export,
        output_directory,
    )
    summary_path = output_directory / "daily_summary.txt"
    summary_path.write_text(
        _summary_text(daily_result, simulation_export.summary),
        encoding="utf-8",
    )
    return HeadroomAwareMPCDemoExecutionResult(
        source_input,
        daily_result,
        simulation_export,
        simulation_paths,
        source_input.decision_csv_output_path,
        summary_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the deterministic longer-horizon headroom-aware comparison CLI."""

    parser = argparse.ArgumentParser(
        description="EOS longer-horizon headroom-aware MPC daily demo"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_headroom_mpc"),
        help="directory for deterministic headroom-aware demo outputs",
    )
    arguments = parser.parse_args(argv)
    execution = run_demo(arguments.output_dir)
    print(f"Headroom-aware MPC decisions: {execution.decision_csv_path}")
    print(f"Simulation CSV: {execution.simulation_paths.csv_path}")
    print(f"Power curve: {execution.simulation_paths.power_curve_path}")
    print(f"SOC curve: {execution.simulation_paths.soc_curve_path}")
    print(f"Daily summary: {execution.summary_path}")
    return 0


def _forecast_horizons(
    daily_input: DailySimulationScenarioInput,
) -> tuple[ForecastHorizon, ...]:
    """Create 24 caller-owned repeating-day perfect forecast horizons."""

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


def _runner() -> HeadroomAwareExplainableMPCDailySimulationRunner:
    """Compose the existing TASK-132 to TASK-138 components exactly once."""

    headroom_optimizer = DeterministicHeadroomAwarePhysicalOptimizer(
        DeterministicPVHeadroomRequirementCalculator(),
        DeterministicHeadroomAwareCandidatePlanner(
            NetLoadAwareBaselineOptimizer(
                NetLoadAwareBaselineOptimizationConfiguration(0.30, 0.90, 3.0)
            ),
            DeterministicHeadroomAwareGridChargeReservationCalculator(),
        ),
        DeterministicExplicitCandidatePhysicalReviser(
            DeterministicBatterySOCHorizonProjector(),
            DeterministicBatterySOCHorizonConstraintEvaluator(),
            DeterministicBatteryPowerHorizonConstraintEvaluator(),
            DeterministicBatteryHorizonConstraintAggregator(),
        ),
    )
    mpc_cycle = HeadroomAwareSingleMPCCycleOrchestrator(
        headroom_optimizer,
        OptimizationSolutionControlPlanBuilder(),
        FirstStepMPCCurrentActionExtractor(),
        _DemoMPCDecisionTranslator(),
    )
    return HeadroomAwareExplainableMPCDailySimulationRunner(
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
    result: HeadroomAwareExplainableMPCDailySimulationResult,
    summary: DailyEnergySummary,
) -> str:
    """Render standard metrics plus deterministic headroom planning evidence."""

    records = result.journal_records
    reasons = tuple(reason for record in records for reason in record.revision_reasons)
    traces = result.step_traces
    reservations = tuple(
        planning_result.grid_charge_reservation
        for planning_result in (
            trace.headroom_mpc_cycle_result.headroom_optimization_output.candidate_planning_result
            for trace in traces
        )
        if planning_result.grid_charge_reservation is not None
    )
    requirements = tuple(
        trace.headroom_mpc_cycle_result.headroom_optimization_output.headroom_requirement
        for trace in traces
    )
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
    reduced_reservation_count = sum(
        reservation.reservation_applied for reservation in reservations
    )
    zero_reservation_count = sum(
        reservation.allowed_grid_charge_power_kw == 0 for reservation in reservations
    )
    minimum_recommended_soc = min(
        requirement.recommended_pre_pv_max_soc_fraction for requirement in requirements
    )
    maximum_required_headroom = max(
        requirement.required_headroom_energy_kwh for requirement in requirements
    )
    return (
        "EOS Longer-Horizon Headroom-Aware MPC Daily Demo Summary\n"
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
        f"headroom_grid_charge_reservations={len(reservations)}\n"
        "headroom_reduced_grid_charge_reservations="
        f"{reduced_reservation_count}\n"
        "headroom_zero_grid_charge_reservations="
        f"{zero_reservation_count}\n"
        "minimum_recommended_pre_pv_max_soc_fraction="
        f"{minimum_recommended_soc:.6f}\n"
        "maximum_required_headroom_energy_kwh="
        f"{maximum_required_headroom:.6f}\n"
    )


if __name__ == "__main__":
    raise SystemExit(main())
