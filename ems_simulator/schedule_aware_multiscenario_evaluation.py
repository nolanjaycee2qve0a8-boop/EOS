"""Deterministic observational matrix for existing three-path headroom flows.

TASK-154 builds caller-owned finite scenario facts and reuses TASK-153's
frozen full/rolling/schedule-aware execution composition.  It never invokes
headroom, reservation, candidate, physical-revision, or MPC boundaries itself.
"""

import argparse
import csv
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path

from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import DailySimulationScenarioInput
from ems_simulator.multi_opportunity_headroom_demo import create_demo_input
from ems_simulator.schedule_aware_headroom_comparison_demo import (
    ComparisonMetrics,
    PVAbsorptionMetrics,
    ScheduleAwareHeadroomComparisonExecutionResult,
    run_comparison,
)
from forecast import ForecastHorizon, ForecastPoint

_HOURS_PER_DAY = 24
_HORIZON_POINTS = 24
_FLOAT_TOLERANCE = 1e-9
_LOW_PRICE_CNY_PER_KWH = 0.20


@dataclass(frozen=True, slots=True)
class ScheduleAwareEvaluationScenario:
    """Caller-owned facts for one deterministic diagnostic scenario."""

    scenario_id: str
    description: str
    pv_profile_kw: tuple[float, ...]
    load_profile_kw: tuple[float, ...]
    tariff_profile_cny_per_kwh: tuple[float, ...]
    initial_soc: float
    gap_tolerance_points: int
    expected_opportunity_count: int

    def __post_init__(self) -> None:
        if not self.scenario_id or not self.description:
            raise ValueError("scenario_id and description must be non-empty")
        for field_name, profile in (
            ("pv_profile_kw", self.pv_profile_kw),
            ("load_profile_kw", self.load_profile_kw),
            ("tariff_profile_cny_per_kwh", self.tariff_profile_cny_per_kwh),
        ):
            if not isinstance(profile, tuple) or len(profile) != _HOURS_PER_DAY:
                raise ValueError(f"{field_name} must contain exactly 24 values")
        if not 0.0 <= self.initial_soc <= 1.0:
            raise ValueError("initial_soc must be in [0, 1]")
        if self.gap_tolerance_points < 0 or self.expected_opportunity_count < 0:
            raise ValueError("scenario metadata counts must be non-negative")


@dataclass(frozen=True, slots=True)
class EarlyPathEvidence:
    required_headroom_kwh: float | None
    target_soc: float | None
    requested_grid_charge_kw: float | None
    allowed_grid_charge_kw: float | None


@dataclass(frozen=True, slots=True)
class EarlyScheduleEvidence:
    opportunity_count: int
    standalone_headroom_kwh: float | None
    adjusted_headroom_kwh: float | None
    target_soc: float | None
    gap_load_energy_kwh: float | None
    stored_depletion_potential_kwh: float | None
    requested_grid_charge_kw: float | None
    allowed_grid_charge_kw: float | None


@dataclass(frozen=True, slots=True)
class ScheduleScenarioEvidence:
    maximum_opportunity_entries: int
    no_opportunity_cycle_count: int
    minimum_first_standalone_headroom_kwh: float | None
    maximum_first_standalone_headroom_kwh: float | None
    minimum_first_adjusted_headroom_kwh: float | None
    maximum_first_adjusted_headroom_kwh: float | None
    minimum_target_soc: float | None
    maximum_target_soc: float | None
    maximum_gap_load_energy_kwh: float
    maximum_stored_depletion_potential_kwh: float
    adjusted_greater_than_standalone_count: int
    adjusted_equal_to_standalone_count: int


@dataclass(frozen=True, slots=True)
class PairwiseDelta:
    grid_import_kwh: float
    grid_export_kwh: float
    absorbed_pv_surplus_kwh: float
    battery_throughput_kwh: float
    final_soc: float


@dataclass(frozen=True, slots=True)
class ScheduleAwareEvaluationScenarioResult:
    """One scenario's exact three-path execution and observed read model."""

    scenario: ScheduleAwareEvaluationScenario
    execution: ScheduleAwareHeadroomComparisonExecutionResult
    full_early: EarlyPathEvidence
    rolling_early: EarlyPathEvidence
    schedule_early: EarlyScheduleEvidence
    schedule_evidence: ScheduleScenarioEvidence
    target_classification: str
    allowance_classification: str
    control_classification: str
    rolling_minus_full: PairwiseDelta
    schedule_minus_full: PairwiseDelta
    schedule_minus_rolling: PairwiseDelta


@dataclass(frozen=True, slots=True)
class ScheduleAwareMultiScenarioEvaluationResult:
    """Ordered, deterministic multi-scenario evaluation artifacts."""

    scenario_results: tuple[ScheduleAwareEvaluationScenarioResult, ...]
    scenario_summary_path: Path
    evaluation_summary_path: Path
    early_target_svg_path: Path
    early_allowance_svg_path: Path
    grid_import_svg_path: Path
    pv_absorption_svg_path: Path


def scenario_matrix() -> tuple[ScheduleAwareEvaluationScenario, ...]:
    """Return the stable TASK-154 diagnostic matrix in caller order."""

    baseline = create_demo_input(Path("."))
    daily = baseline.integration_input.daily_input
    pv = daily.pv_power_curve_kw
    load = daily.load_power_curve_kw
    tariff = daily.tariff_curve_cny_per_kwh

    return (
        ScheduleAwareEvaluationScenario(
            "S0",
            "TASK-153 / TASK-146 finite two-opportunity baseline.",
            pv,
            load,
            tariff,
            0.50,
            1,
            2,
        ),
        ScheduleAwareEvaluationScenario(
            "S1",
            "Large inter-opportunity deficit with preserved separation.",
            pv,
            _replace_values(load, (11, 12, 13), (3.0, 3.0, 3.0)),
            tariff,
            0.50,
            1,
            2,
        ),
        ScheduleAwareEvaluationScenario(
            "S2",
            "Small inter-opportunity deficit with preserved separation.",
            pv,
            _replace_values(load, (11, 12, 13), (0.5, 0.5, 0.5)),
            tariff,
            0.50,
            1,
            2,
        ),
        ScheduleAwareEvaluationScenario(
            "S3",
            "Extended cheap tariff through late morning.",
            pv,
            load,
            _replace_values(tariff, tuple(range(6, 12)), (0.2,) * 6),
            0.50,
            1,
            2,
        ),
        ScheduleAwareEvaluationScenario(
            "S4",
            "Reduced second PV-surplus opportunity.",
            _replace_values(pv, (14, 15, 16, 17), (1.8, 2.0, 1.8, 1.5)),
            load,
            tariff,
            0.50,
            1,
            2,
        ),
        ScheduleAwareEvaluationScenario(
            "S5",
            "Expanded second PV-surplus opportunity.",
            _replace_values(pv, (14, 15, 16, 17), (4.5, 6.0, 5.5, 4.5)),
            load,
            tariff,
            0.50,
            1,
            2,
        ),
        ScheduleAwareEvaluationScenario(
            "S6",
            "Baseline facts with low initial SOC.",
            pv,
            load,
            tariff,
            0.20,
            1,
            2,
        ),
        ScheduleAwareEvaluationScenario(
            "S7",
            "Baseline facts with high initial SOC.",
            pv,
            load,
            tariff,
            0.80,
            1,
            2,
        ),
    )


def run_evaluation(
    output_directory: Path,
) -> ScheduleAwareMultiScenarioEvaluationResult:
    """Run every matrix scenario using TASK-153's unchanged three-path engine."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    results = tuple(
        _run_scenario(scenario, output_directory / scenario.scenario_id)
        for scenario in scenario_matrix()
    )
    scenario_summary_path = output_directory / "scenario_summary.csv"
    scenario_summary_path.write_text(
        _scenario_summary_csv(results), encoding="utf-8", newline=""
    )
    evaluation_summary_path = output_directory / "evaluation_summary.txt"
    evaluation_summary_path.write_text(
        _evaluation_summary(results), encoding="utf-8", newline=""
    )
    early_target_svg_path = output_directory / "early_target_soc_by_scenario.svg"
    early_allowance_svg_path = (
        output_directory / "early_allowed_grid_charge_by_scenario.svg"
    )
    grid_import_svg_path = output_directory / "grid_import_by_scenario.svg"
    pv_absorption_svg_path = output_directory / "pv_absorption_by_scenario.svg"
    early_target_svg_path.write_text(
        _bar_svg("Early target SOC", results, _early_target_values), encoding="utf-8"
    )
    early_allowance_svg_path.write_text(
        _bar_svg("Early allowed grid charge (kW)", results, _early_allowance_values),
        encoding="utf-8",
    )
    grid_import_svg_path.write_text(
        _bar_svg("Grid import (kWh)", results, _grid_import_values), encoding="utf-8"
    )
    pv_absorption_svg_path.write_text(
        _bar_svg("Estimated absorbed PV surplus (kWh)", results, _pv_absorption_values),
        encoding="utf-8",
    )
    return ScheduleAwareMultiScenarioEvaluationResult(
        results,
        scenario_summary_path,
        evaluation_summary_path,
        early_target_svg_path,
        early_allowance_svg_path,
        grid_import_svg_path,
        pv_absorption_svg_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS schedule-aware headroom multi-scenario evaluation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task154_multiscenario"),
    )
    arguments = parser.parse_args(argv)
    result = run_evaluation(arguments.output_dir)
    for path in (
        result.scenario_summary_path,
        result.evaluation_summary_path,
        result.early_target_svg_path,
        result.early_allowance_svg_path,
        result.grid_import_svg_path,
        result.pv_absorption_svg_path,
    ):
        print(path)
    return 0


def _run_scenario(
    scenario: ScheduleAwareEvaluationScenario,
    output_directory: Path,
) -> ScheduleAwareEvaluationScenarioResult:
    output_directory.mkdir(parents=True, exist_ok=True)
    source = _scenario_input(scenario, output_directory)
    execution = run_comparison(source, output_directory)
    full_early = _full_early_evidence(execution)
    rolling_early = _rolling_early_evidence(execution)
    schedule_early = _schedule_early_evidence(execution)
    schedule_evidence = _schedule_evidence(execution)
    return ScheduleAwareEvaluationScenarioResult(
        scenario,
        execution,
        full_early,
        rolling_early,
        schedule_early,
        schedule_evidence,
        _classify_scalar(
            full_early.target_soc,
            rolling_early.target_soc,
            schedule_early.target_soc,
        ),
        _classify_scalar(
            full_early.allowed_grid_charge_kw,
            rolling_early.allowed_grid_charge_kw,
            schedule_early.allowed_grid_charge_kw,
        ),
        _classify_control(execution),
        _delta(
            execution.rolling_metrics,
            execution.full_metrics,
            execution.rolling_pv_absorption,
            execution.full_pv_absorption,
        ),
        _delta(
            execution.schedule_metrics,
            execution.full_metrics,
            execution.schedule_pv_absorption,
            execution.full_pv_absorption,
        ),
        _delta(
            execution.schedule_metrics,
            execution.rolling_metrics,
            execution.schedule_pv_absorption,
            execution.rolling_pv_absorption,
        ),
    )


def _scenario_input(
    scenario: ScheduleAwareEvaluationScenario,
    output_directory: Path,
) -> ExplainableMPCDailySimulationInput:
    """Create only caller facts; execution remains in TASK-153 composition."""

    template = create_demo_input(output_directory)
    template_daily = template.integration_input.daily_input
    daily = DailySimulationScenarioInput(
        template_daily.step_identities,
        scenario.pv_profile_kw,
        scenario.load_profile_kw,
        scenario.tariff_profile_cny_per_kwh,
        template_daily.battery_parameters,
        scenario.initial_soc,
    )
    integration_template = template.integration_input
    integration = EMSIntegrationScenarioInput(
        daily,
        integration_template.objective_composition,
        integration_template.capability,
        integration_template.battery_power_limit_kw,
        integration_template.export_limit_kw,
        integration_template.initial_grid_power_kw,
    )
    return ExplainableMPCDailySimulationInput(
        integration,
        _finite_horizons(daily),
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        template.battery_optimization_model,
        template.explanation_locale,
        output_directory / "full_mpc_decisions.csv",
    )


def _finite_horizons(
    daily: DailySimulationScenarioInput,
) -> tuple[ForecastHorizon, ...]:
    """Create finite no-wrap caller facts with explicit zero-surplus tails."""

    horizons: list[ForecastHorizon] = []
    for hour, identity in enumerate(daily.step_identities):
        timestamp = identity.timestamp
        if timestamp is None:
            raise ValueError("scenario steps require explicit timestamps")
        points = tuple(
            _forecast_point(daily, hour + offset, timestamp + timedelta(hours=offset))
            for offset in range(_HORIZON_POINTS)
        )
        horizons.append(ForecastHorizon(points))
    return tuple(horizons)


def _forecast_point(
    daily: DailySimulationScenarioInput,
    index: int,
    timestamp: datetime,
) -> ForecastPoint:
    if index < _HOURS_PER_DAY:
        return ForecastPoint(
            timestamp,
            daily.pv_power_curve_kw[index],
            daily.load_power_curve_kw[index],
            daily.tariff_curve_cny_per_kwh[index],
        )
    return ForecastPoint(timestamp, 0.0, 0.0, 0.50)


def _full_early_evidence(
    execution: ScheduleAwareHeadroomComparisonExecutionResult,
) -> EarlyPathEvidence:
    output = execution.full_result.step_traces[
        0
    ].headroom_mpc_cycle_result.headroom_optimization_output
    reservation = output.candidate_planning_result.grid_charge_reservation
    return EarlyPathEvidence(
        output.headroom_requirement.required_headroom_energy_kwh,
        output.headroom_requirement.recommended_pre_pv_max_soc_fraction,
        None if reservation is None else reservation.requested_grid_charge_power_kw,
        None if reservation is None else reservation.allowed_grid_charge_power_kw,
    )


def _rolling_early_evidence(
    execution: ScheduleAwareHeadroomComparisonExecutionResult,
) -> EarlyPathEvidence:
    output = execution.rolling_result.step_traces[
        0
    ].rolling_headroom_mpc_cycle_result.rolling_headroom_optimization_output
    requirement = output.rolling_headroom_requirement.headroom_requirement
    reservation = output.candidate_planning_result.grid_charge_reservation
    return EarlyPathEvidence(
        requirement.required_headroom_energy_kwh,
        requirement.recommended_pre_pv_max_soc_fraction,
        None if reservation is None else reservation.requested_grid_charge_power_kw,
        None if reservation is None else reservation.allowed_grid_charge_power_kw,
    )


def _schedule_early_evidence(
    execution: ScheduleAwareHeadroomComparisonExecutionResult,
) -> EarlyScheduleEvidence:
    output = execution.schedule_result.step_traces[
        0
    ].multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output
    entry = (
        output.headroom_schedule.entries[0]
        if output.headroom_schedule.entries
        else None
    )
    reservation = output.candidate_planning_result.reservation_result
    return EarlyScheduleEvidence(
        len(output.headroom_schedule.entries),
        None
        if entry is None
        else entry.headroom_requirement.required_headroom_energy_kwh,
        None if entry is None else entry.required_pre_opportunity_headroom_kwh,
        None if entry is None else entry.recommended_pre_opportunity_max_soc_fraction,
        None if entry is None else entry.gap_net_deficit_load_energy_kwh,
        None if entry is None else entry.battery_stored_energy_depletion_potential_kwh,
        None if reservation is None else reservation.requested_grid_charge_power_kw,
        None if reservation is None else reservation.allowed_grid_charge_power_kw,
    )


def _schedule_evidence(
    execution: ScheduleAwareHeadroomComparisonExecutionResult,
) -> ScheduleScenarioEvidence:
    schedules = tuple(
        trace.multi_opportunity_mpc_cycle_result.multi_opportunity_optimization_output.headroom_schedule
        for trace in execution.schedule_result.step_traces
    )
    entries = tuple(schedule.entries[0] for schedule in schedules if schedule.entries)
    standalone = tuple(
        entry.headroom_requirement.required_headroom_energy_kwh for entry in entries
    )
    adjusted = tuple(entry.required_pre_opportunity_headroom_kwh for entry in entries)
    targets = tuple(
        entry.recommended_pre_opportunity_max_soc_fraction for entry in entries
    )
    gap_load = tuple(entry.gap_net_deficit_load_energy_kwh for entry in entries)
    depletion = tuple(
        entry.battery_stored_energy_depletion_potential_kwh for entry in entries
    )
    return ScheduleScenarioEvidence(
        max((len(schedule.entries) for schedule in schedules), default=0),
        sum(not schedule.entries for schedule in schedules),
        min(standalone) if standalone else None,
        max(standalone) if standalone else None,
        min(adjusted) if adjusted else None,
        max(adjusted) if adjusted else None,
        min(targets) if targets else None,
        max(targets) if targets else None,
        max(gap_load, default=0.0),
        max(depletion, default=0.0),
        sum(
            value > base + _FLOAT_TOLERANCE
            for value, base in zip(adjusted, standalone, strict=True)
        ),
        sum(
            abs(value - base) <= _FLOAT_TOLERANCE
            for value, base in zip(adjusted, standalone, strict=True)
        ),
    )


def _delta(
    observed: ComparisonMetrics,
    reference: ComparisonMetrics,
    observed_pv: PVAbsorptionMetrics,
    reference_pv: PVAbsorptionMetrics,
) -> PairwiseDelta:
    return PairwiseDelta(
        observed.grid_import_energy_kwh - reference.grid_import_energy_kwh,
        observed.grid_export_energy_kwh - reference.grid_export_energy_kwh,
        observed_pv.estimated_absorbed_pv_surplus_energy_kwh
        - reference_pv.estimated_absorbed_pv_surplus_energy_kwh,
        observed.battery_throughput_kwh - reference.battery_throughput_kwh,
        observed.final_soc - reference.final_soc,
    )


def _classify_scalar(
    full: float | None,
    rolling: float | None,
    schedule: float | None,
) -> str:
    if full is None or rolling is None or schedule is None:
        return "DISTINCT"
    if _close(schedule, full):
        return "FULL_LIKE"
    if _close(schedule, rolling):
        return "ROLLING_LIKE"
    if min(full, rolling) < schedule < max(full, rolling):
        return "INTERMEDIATE"
    return "DISTINCT"


def _classify_control(
    execution: ScheduleAwareHeadroomComparisonExecutionResult,
) -> str:
    full = _control_vector(execution.full_metrics, execution.full_pv_absorption)
    rolling = _control_vector(
        execution.rolling_metrics,
        execution.rolling_pv_absorption,
    )
    schedule = _control_vector(
        execution.schedule_metrics,
        execution.schedule_pv_absorption,
    )
    if _vectors_close(schedule, full):
        return "FULL_LIKE"
    if _vectors_close(schedule, rolling):
        return "ROLLING_LIKE"
    if all(
        min(full_value, rolling_value)
        <= schedule_value
        <= max(full_value, rolling_value)
        for full_value, rolling_value, schedule_value in zip(
            full, rolling, schedule, strict=True
        )
    ):
        return "INTERMEDIATE"
    return "DISTINCT"


def _control_vector(
    metrics: ComparisonMetrics,
    pv: PVAbsorptionMetrics,
) -> tuple[float, float, float, float, float]:
    return (
        metrics.grid_import_energy_kwh,
        metrics.grid_export_energy_kwh,
        pv.estimated_absorbed_pv_surplus_energy_kwh,
        metrics.battery_throughput_kwh,
        metrics.final_soc,
    )


def _vectors_close(left: tuple[float, ...], right: tuple[float, ...]) -> bool:
    return all(
        _close(left_value, right_value)
        for left_value, right_value in zip(left, right, strict=True)
    )


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= _FLOAT_TOLERANCE


def _scenario_summary_csv(
    results: tuple[ScheduleAwareEvaluationScenarioResult, ...],
) -> str:
    columns = (
        "scenario_id",
        "description",
        "initial_soc",
        "full_early_headroom_kwh",
        "rolling_early_headroom_kwh",
        "schedule_early_standalone_headroom_kwh",
        "schedule_early_adjusted_headroom_kwh",
        "full_early_target_soc",
        "rolling_early_target_soc",
        "schedule_early_target_soc",
        "full_early_allowed_grid_charge_kw",
        "rolling_early_allowed_grid_charge_kw",
        "schedule_early_allowed_grid_charge_kw",
        "schedule_gap_load_energy_kwh",
        "schedule_stored_depletion_potential_kwh",
        "full_grid_import_kwh",
        "rolling_grid_import_kwh",
        "schedule_grid_import_kwh",
        "full_grid_export_kwh",
        "rolling_grid_export_kwh",
        "schedule_grid_export_kwh",
        "full_absorbed_pv_surplus_kwh",
        "rolling_absorbed_pv_surplus_kwh",
        "schedule_absorbed_pv_surplus_kwh",
        "full_final_soc",
        "rolling_final_soc",
        "schedule_final_soc",
        "schedule_target_class",
        "schedule_allowance_class",
        "schedule_control_class",
    )
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(columns)
    for result in results:
        full = result.execution.full_metrics
        rolling = result.execution.rolling_metrics
        schedule = result.execution.schedule_metrics
        writer.writerow(
            (
                result.scenario.scenario_id,
                result.scenario.description,
                _number(result.scenario.initial_soc),
                _optional_number(result.full_early.required_headroom_kwh),
                _optional_number(result.rolling_early.required_headroom_kwh),
                _optional_number(result.schedule_early.standalone_headroom_kwh),
                _optional_number(result.schedule_early.adjusted_headroom_kwh),
                _optional_number(result.full_early.target_soc),
                _optional_number(result.rolling_early.target_soc),
                _optional_number(result.schedule_early.target_soc),
                _optional_number(result.full_early.allowed_grid_charge_kw),
                _optional_number(result.rolling_early.allowed_grid_charge_kw),
                _optional_number(result.schedule_early.allowed_grid_charge_kw),
                _optional_number(result.schedule_early.gap_load_energy_kwh),
                _optional_number(result.schedule_early.stored_depletion_potential_kwh),
                _number(full.grid_import_energy_kwh),
                _number(rolling.grid_import_energy_kwh),
                _number(schedule.grid_import_energy_kwh),
                _number(full.grid_export_energy_kwh),
                _number(rolling.grid_export_energy_kwh),
                _number(schedule.grid_export_energy_kwh),
                _number(
                    result.execution.full_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh
                ),
                _number(
                    result.execution.rolling_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh
                ),
                _number(
                    result.execution.schedule_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh
                ),
                _number(full.final_soc),
                _number(rolling.final_soc),
                _number(schedule.final_soc),
                result.target_classification,
                result.allowance_classification,
                result.control_classification,
            )
        )
    return stream.getvalue()


def _evaluation_summary(
    results: tuple[ScheduleAwareEvaluationScenarioResult, ...],
) -> str:
    blocks = [
        "EOS Schedule-Aware Multi-Scenario Behavioral Evaluation\n",
        "These are deterministic diagnostic scenarios, not a statistical claim "
        "about household populations.\n",
        "S8 medium initial-SOC grouping is represented by S0; it is not "
        "executed twice.\n",
    ]
    for result in results:
        blocks.append(_scenario_text(result))
    blocks.append("cross_scenario_observations\n")
    blocks.append(_cross_scenario_text(results))
    return "".join(blocks)


def _scenario_text(result: ScheduleAwareEvaluationScenarioResult) -> str:
    full = result.execution.full_metrics
    rolling = result.execution.rolling_metrics
    schedule = result.execution.schedule_metrics
    early = result.schedule_early
    full_absorbed = (
        result.execution.full_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh
    )
    rolling_absorbed = (
        result.execution.rolling_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh
    )
    schedule_absorbed = (
        result.execution.schedule_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh
    )
    return (
        f"[{result.scenario.scenario_id}] {result.scenario.description}\n"
        f"initial_soc={result.scenario.initial_soc:.6f}\n"
        "early_headroom_kwh="
        f"full:{_optional_number(result.full_early.required_headroom_kwh)} "
        f"rolling:{_optional_number(result.rolling_early.required_headroom_kwh)} "
        f"schedule_standalone:{_optional_number(early.standalone_headroom_kwh)} "
        f"schedule_adjusted:{_optional_number(early.adjusted_headroom_kwh)}\n"
        "early_target_soc="
        f"full:{_optional_number(result.full_early.target_soc)} "
        f"rolling:{_optional_number(result.rolling_early.target_soc)} "
        f"schedule:{_optional_number(early.target_soc)}\n"
        "early_allowed_grid_charge_kw="
        f"full:{_optional_number(result.full_early.allowed_grid_charge_kw)} "
        f"rolling:{_optional_number(result.rolling_early.allowed_grid_charge_kw)} "
        f"schedule:{_optional_number(early.allowed_grid_charge_kw)}\n"
        "daily_grid_import_kwh="
        f"full:{full.grid_import_energy_kwh:.6f} "
        f"rolling:{rolling.grid_import_energy_kwh:.6f} "
        f"schedule:{schedule.grid_import_energy_kwh:.6f}\n"
        "daily_grid_export_kwh="
        f"full:{full.grid_export_energy_kwh:.6f} "
        f"rolling:{rolling.grid_export_energy_kwh:.6f} "
        f"schedule:{schedule.grid_export_energy_kwh:.6f}\n"
        "absorbed_pv_surplus_kwh="
        f"full:{full_absorbed:.6f} "
        f"rolling:{rolling_absorbed:.6f} "
        f"schedule:{schedule_absorbed:.6f}\n"
        "classifications="
        f"target:{result.target_classification} "
        f"allowance:{result.allowance_classification} "
        f"control:{result.control_classification}\n"
        "schedule_evidence="
        f"opportunities:{early.opportunity_count} "
        f"gap_load:{_optional_number(early.gap_load_energy_kwh)} "
        f"stored_depletion:{_optional_number(early.stored_depletion_potential_kwh)} "
        f"adjusted_gt_standalone:{result.schedule_evidence.adjusted_greater_than_standalone_count}\n"
    )


def _cross_scenario_text(
    results: tuple[ScheduleAwareEvaluationScenarioResult, ...],
) -> str:
    by_id = {result.scenario.scenario_id: result for result in results}
    s1 = by_id["S1"].schedule_early
    s2 = by_id["S2"].schedule_early
    s3 = by_id["S3"]
    s4 = by_id["S4"].schedule_early
    s5 = by_id["S5"].schedule_early
    s6 = by_id["S6"]
    s0 = by_id["S0"]
    s7 = by_id["S7"]
    s3_divergence = _s3_tariff_interaction(s3)
    intermediate = tuple(
        result.scenario.scenario_id
        for result in results
        if "INTERMEDIATE"
        in (
            result.target_classification,
            result.allowance_classification,
            result.control_classification,
        )
    )
    return (
        "S1_vs_S2_depletion_sensitivity\n"
        f"S1_stored_depletion={_optional_number(s1.stored_depletion_potential_kwh)}\n"
        f"S2_stored_depletion={_optional_number(s2.stored_depletion_potential_kwh)}\n"
        f"S1_adjusted_headroom={_optional_number(s1.adjusted_headroom_kwh)}\n"
        f"S2_adjusted_headroom={_optional_number(s2.adjusted_headroom_kwh)}\n"
        "S4_vs_S5_second_opportunity_sensitivity\n"
        f"S4_adjusted_headroom={_optional_number(s4.adjusted_headroom_kwh)}\n"
        f"S5_adjusted_headroom={_optional_number(s5.adjusted_headroom_kwh)}\n"
        "S3_extended_tariff_interaction\n" + s3_divergence + "initial_soc_interaction\n"
        f"S6_control={s6.control_classification}; "
        f"S0_control={s0.control_classification}; "
        f"S7_control={s7.control_classification}\n"
        f"intermediate_classification_scenarios={'|'.join(intermediate)}\n"
        "Recommendation: extend deterministic scenario coverage before changing "
        "optimization; observed classifications identify where an explicit new "
        "policy objective would be justified.\n"
    )


def _s3_tariff_interaction(result: ScheduleAwareEvaluationScenarioResult) -> str:
    full_traces = result.execution.full_result.step_traces
    schedule_traces = result.execution.schedule_result.step_traces
    for index, (full_trace, schedule_trace) in enumerate(
        zip(full_traces, schedule_traces, strict=True)
    ):
        full_output = full_trace.headroom_mpc_cycle_result.headroom_optimization_output
        full_target = (
            full_output.headroom_requirement.recommended_pre_pv_max_soc_fraction
        )
        schedule_cycle = schedule_trace.multi_opportunity_mpc_cycle_result
        output = schedule_cycle.multi_opportunity_optimization_output
        entry = (
            output.headroom_schedule.entries[0]
            if output.headroom_schedule.entries
            else None
        )
        if entry is None or _close(
            full_target, entry.recommended_pre_opportunity_max_soc_fraction
        ):
            continue
        point = schedule_trace.forecast_horizon.points[0]
        reservation = output.candidate_planning_result.reservation_result
        timestamp = point.timestamp.isoformat()
        requested = (
            ""
            if reservation is None
            else _number(reservation.requested_grid_charge_power_kw)
        )
        allowed = (
            ""
            if reservation is None
            else _number(reservation.allowed_grid_charge_power_kw)
        )
        price = point.electricity_price_cny_per_kwh
        price_text = "" if price is None else _number(price)
        cheap = "" if price is None else str(price <= _LOW_PRICE_CNY_PER_KWH).lower()
        return (
            f"first_target_divergence_index={index}\n"
            f"first_target_divergence_timestamp={timestamp}\n"
            f"price_cny_per_kwh={price_text}\n"
            f"cheap_tariff_active={cheap}\n"
            f"reservation_requested_kw={requested}\n"
            f"reservation_allowed_kw={allowed}\n"
        )
    return "first_target_divergence_index=\n"


def _bar_svg(
    title: str,
    results: tuple[ScheduleAwareEvaluationScenarioResult, ...],
    value_getter: Callable[
        [ScheduleAwareEvaluationScenarioResult],
        tuple[float | None, float | None, float | None],
    ],
) -> str:
    values = tuple(value_getter(result) for result in results)
    width, height = 1024, 360
    left, right, top, bottom = 65.0, 990.0, 45.0, 275.0
    numeric = tuple(value for group in values for value in group if value is not None)
    maximum = max(1.0, *numeric)
    colors = ("#2563eb", "#dc2626", "#059669")
    labels = ("Full", "Rolling", "Schedule")
    group_width = (right - left) / len(results)
    bar_width = min(22.0, group_width / 4.0)
    bars: list[str] = []
    for index, group in enumerate(values):
        for series_index, value in enumerate(group):
            if value is None:
                continue
            x = left + index * group_width + series_index * bar_width
            bar_height = value / maximum * (bottom - top)
            bars.append(
                f'<rect x="{x:.2f}" y="{bottom - bar_height:.2f}" '
                f'width="{bar_width:.2f}" height="{bar_height:.2f}" '
                f'fill="{colors[series_index]}"/>'
            )
    scenario_labels = "".join(
        f'<text x="{left + index * group_width:.2f}" y="300" '
        f'font-family="sans-serif" font-size="12">{result.scenario.scenario_id}</text>'
        for index, result in enumerate(results)
    )
    legend = "".join(
        f'<text x="{65 + index * 120}" y="335" font-family="sans-serif" '
        f'font-size="12" fill="{colors[index]}">{label}</text>'
        for index, label in enumerate(labels)
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">'
        '<rect width="100%" height="100%" fill="white"/>'
        f'<text x="65" y="24" font-family="sans-serif" font-size="16">{title}</text>'
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" '
        'stroke="#64748b" stroke-width="1"/>'
        f"{''.join(bars)}{scenario_labels}{legend}</svg>\n"
    )


def _early_target_values(
    result: ScheduleAwareEvaluationScenarioResult,
) -> tuple[float | None, float | None, float | None]:
    return (
        result.full_early.target_soc,
        result.rolling_early.target_soc,
        result.schedule_early.target_soc,
    )


def _early_allowance_values(
    result: ScheduleAwareEvaluationScenarioResult,
) -> tuple[float | None, float | None, float | None]:
    return (
        result.full_early.allowed_grid_charge_kw,
        result.rolling_early.allowed_grid_charge_kw,
        result.schedule_early.allowed_grid_charge_kw,
    )


def _grid_import_values(
    result: ScheduleAwareEvaluationScenarioResult,
) -> tuple[float, float, float]:
    return (
        result.execution.full_metrics.grid_import_energy_kwh,
        result.execution.rolling_metrics.grid_import_energy_kwh,
        result.execution.schedule_metrics.grid_import_energy_kwh,
    )


def _pv_absorption_values(
    result: ScheduleAwareEvaluationScenarioResult,
) -> tuple[float, float, float]:
    return (
        result.execution.full_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh,
        result.execution.rolling_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh,
        result.execution.schedule_pv_absorption.estimated_absorbed_pv_surplus_energy_kwh,
    )


def _replace_values(
    values: tuple[float, ...],
    indexes: tuple[int, ...],
    replacements: tuple[float, ...],
) -> tuple[float, ...]:
    if len(indexes) != len(replacements):
        raise ValueError("indexes and replacements must have matching lengths")
    changed = list(values)
    for index, replacement in zip(indexes, replacements, strict=True):
        changed[index] = replacement
    return tuple(changed)


def _number(value: float) -> str:
    return f"{value:.6f}"


def _optional_number(value: float | None) -> str:
    return "" if value is None else _number(value)


if __name__ == "__main__":
    raise SystemExit(main())
