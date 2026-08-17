# ruff: noqa: E501
"""Deterministic Residential EMS 1.0 Simulation Validation Campaign Phase A.

This campaign is a functional-freeze validation/read-model.  It composes the
existing Schedule-aware and Economic Schedule-aware daily runners with
caller-owned deterministic facts.  It does not change or repair strategy,
MPC, headroom, economic-planning, physical-revision, feasibility, handoff, or
Simulator behaviour.
"""

import argparse
import csv
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from io import StringIO
from math import isclose
from pathlib import Path

from ems_simulator.economic_comparison_explanation import (
    DeterministicEconomicComparisonExplainer,
    EconomicComparisonExplanation,
    EconomicComparisonInput,
    EconomicComparisonRanking,
)
from ems_simulator.economic_ledger import (
    DailyEconomicLedger,
    DeterministicEconomicLedgerBuilder,
    EconomicLedgerInput,
)
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner,
    _finite_horizons,
    _schedule_runner,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.multi_opportunity_headroom_demo import (
    _GAP_TOLERANCE_POINTS,
    create_demo_input,
)
from ems_simulator.residential_acceptance import (
    NUMERIC_TOLERANCE,
    DeterministicResidentialAcceptanceEvaluator,
    ResidentialAcceptanceCategory,
    ResidentialAcceptanceFinding,
    ResidentialAcceptanceKPI,
    ResidentialAcceptanceResult,
    ResidentialAcceptanceScenario,
    ResidentialAcceptanceSeverity,
    ResidentialAcceptanceStatus,
)
from optimization import (
    BatteryOptimizationModel,
    NetLoadAwareBaselineOptimizationConfiguration,
    PVOpportunityWindowConfiguration,
)

_HOURS_PER_DAY = 24
_REFERENCE_IMPORT_TARIFF = (0.20,) * 6 + (0.50,) * 12 + (0.90,) * 4 + (0.50,) * 2
_NEGATIVE_IMPORT_TARIFF = (0.80,) * 6 + (0.85,) * 18
_REFERENCE_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(
    0.30, 0.80, 3.0
)
_NEGATIVE_CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.80, 1.00, 3.0)
_REFERENCE_MODEL = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)
_EXPORT_ALLOWED = "export_allowed_settled"
_PERFECT_FORECAST = "perfect_caller_supplied_forecast_equals_realized"
_MEANINGFUL_COST_LOSS = 0.25
_LARGE_COST_DIVERGENCE = 0.50


@dataclass(frozen=True, slots=True)
class ResidentialCampaignScenario:
    """Complete, caller-owned deterministic facts for one Phase-A day."""

    scenario_id: str
    description: str
    load_profile_kw: tuple[float, ...]
    pv_profile_kw: tuple[float, ...]
    import_tariff_profile_per_kwh: tuple[float, ...]
    export_tariff_per_kwh: float
    initial_soc_fraction: float
    battery_model: BatteryOptimizationModel
    candidate_configuration: NetLoadAwareBaselineOptimizationConfiguration
    degradation_cost_per_throughput_kwh: float
    terminal_valuation_per_kwh: float
    export_policy: str
    forecast_semantics: str


@dataclass(frozen=True, slots=True)
class ResidentialCampaignPathResult:
    """One exact completed daily trajectory and its post-control evidence."""

    scenario: ResidentialCampaignScenario
    strategy: str
    trajectory: (
        MultiOpportunityExplainableMPCDailySimulationResult
        | EconomicMultiOpportunityExplainableMPCDailySimulationResult
    )
    ledger: DailyEconomicLedger
    kpi: ResidentialAcceptanceKPI
    acceptance: ResidentialAcceptanceResult


@dataclass(frozen=True, slots=True)
class ResidentialCampaignScenarioResult:
    """The two primary strategies and their TASK-174 comparison for one day."""

    scenario: ResidentialCampaignScenario
    schedule: ResidentialCampaignPathResult
    economic: ResidentialCampaignPathResult
    comparison: EconomicComparisonExplanation


@dataclass(frozen=True, slots=True)
class ResidentialCampaignAResult:
    """Stable Phase-A results, summary status, and generated output locations."""

    scenarios: tuple[ResidentialCampaignScenario, ...]
    scenario_results: tuple[ResidentialCampaignScenarioResult, ...]
    hard_passed: bool
    anomaly_shortlist: tuple[str, ...]
    scenarios_csv_path: Path
    results_csv_path: Path
    comparisons_csv_path: Path
    findings_csv_path: Path
    summary_path: Path
    adjusted_cost_svg_path: Path
    grid_import_svg_path: Path
    throughput_svg_path: Path
    final_soc_svg_path: Path
    cost_delta_svg_path: Path


def campaign_scenarios() -> tuple[ResidentialCampaignScenario, ...]:
    """Return exactly 24 stable Phase-A scenarios in campaign order."""

    template = create_demo_input(Path("."))
    daily = template.integration_input.daily_input
    reference_pv = _replace(
        daily.pv_power_curve_kw, (14, 15, 16, 17), (1.8, 2.0, 1.8, 1.5)
    )
    reference_load = daily.load_power_curve_kw
    low_pcs_model = BatteryOptimizationModel(10.0, 0.20, 1.0, 1.5, 1.5, 0.95, 0.95)
    midday_cloud = _replace(
        reference_pv, (12, 13, 14, 15, 16), (0.05, 0.10, 0.45, 0.50, 0.40)
    )
    double_hump = _replace(
        reference_pv,
        (8, 9, 10, 11, 12, 13, 14, 15, 16, 17),
        (2.4, 3.0, 2.2, 0.0, 0.0, 0.0, 2.0, 2.8, 2.2, 1.6),
    )
    morning_peak = _add(reference_load, range(6, 10), 1.50)
    evening_peak = _add(reference_load, range(18, 22), 1.80)
    daytime_load = _add(reference_load, range(8, 18), 1.20)
    weak_tou = (0.45,) * 6 + (0.50,) * 12 + (0.55,) * 4 + (0.50,) * 2
    strong_tou = (0.10,) * 6 + (0.50,) * 12 + (1.20,) * 4 + (0.50,) * 2

    def scenario(
        scenario_id: str,
        description: str,
        *,
        load: tuple[float, ...] = reference_load,
        pv: tuple[float, ...] = reference_pv,
        tariff: tuple[float, ...] = _REFERENCE_IMPORT_TARIFF,
        export_tariff: float = 0.20,
        initial_soc: float = 0.50,
        model: BatteryOptimizationModel = _REFERENCE_MODEL,
        configuration: NetLoadAwareBaselineOptimizationConfiguration = _REFERENCE_CONFIGURATION,
        degradation: float = 0.05,
        terminal: float = 0.85,
    ) -> ResidentialCampaignScenario:
        return ResidentialCampaignScenario(
            scenario_id,
            description,
            load,
            pv,
            tariff,
            export_tariff,
            initial_soc,
            model,
            configuration,
            degradation,
            terminal,
            _EXPORT_ALLOWED,
            _PERFECT_FORECAST,
        )

    scenarios = (
        scenario(
            "A01_REFERENCE_TASK175",
            "TASK-175 frozen Residential EMS 1.0 reference semantics.",
        ),
        scenario(
            "A02_NEGATIVE_ECONOMIC_SHIFT",
            "TASK-172 E1 negative economic-shift semantics.",
            tariff=_NEGATIVE_IMPORT_TARIFF,
            configuration=_NEGATIVE_CONFIGURATION,
        ),
        scenario(
            "A03_TERMINAL_SOC_DIVERGENCE",
            "TASK-165 terminal-SOC-divergence semantics: PV capped below load.",
            pv=tuple(min(value, 0.60) for value in reference_pv),
            tariff=_NEGATIVE_IMPORT_TARIFF,
            configuration=_NEGATIVE_CONFIGURATION,
        ),
        scenario(
            "A04_INITIAL_SOC_20",
            "Reference profiles with initial SOC 20%.",
            initial_soc=0.20,
        ),
        scenario(
            "A05_INITIAL_SOC_35",
            "Reference profiles with initial SOC 35%.",
            initial_soc=0.35,
        ),
        scenario(
            "A06_INITIAL_SOC_70",
            "Reference profiles with initial SOC 70%.",
            initial_soc=0.70,
        ),
        scenario(
            "A07_INITIAL_SOC_90",
            "Reference profiles with initial SOC 90%.",
            initial_soc=0.90,
        ),
        scenario(
            "A08_NO_PV",
            "Reference profiles with PV fixed to 0 kW.",
            pv=(0.0,) * _HOURS_PER_DAY,
        ),
        scenario(
            "A09_LOW_PV",
            "Reference PV multiplied by 0.50.",
            pv=_scale(reference_pv, 0.50),
        ),
        scenario(
            "A10_HIGH_PV",
            "Reference PV multiplied by 1.50.",
            pv=_scale(reference_pv, 1.50),
        ),
        scenario(
            "A11_MIDDAY_CLOUD_DIP",
            "Reference PV with a deterministic 12:00-16:00 cloud dip.",
            pv=midday_cloud,
        ),
        scenario(
            "A12_DOUBLE_HUMP_PV",
            "Deterministic morning and afternoon PV humps separated by a zero-PV gap.",
            pv=double_hump,
        ),
        scenario(
            "A13_LOW_LOAD",
            "Reference load multiplied by 0.70.",
            load=_scale(reference_load, 0.70),
        ),
        scenario(
            "A14_HIGH_LOAD",
            "Reference load multiplied by 1.30.",
            load=_scale(reference_load, 1.30),
        ),
        scenario(
            "A15_MORNING_PEAK",
            "Reference load plus 1.50 kW at 06:00-09:00.",
            load=morning_peak,
        ),
        scenario(
            "A16_EVENING_PEAK",
            "Reference load plus 1.80 kW at 18:00-21:00.",
            load=evening_peak,
        ),
        scenario(
            "A17_HIGH_DAYTIME_LOAD",
            "Reference load plus 1.20 kW at 08:00-17:00.",
            load=daytime_load,
        ),
        scenario(
            "A18_FLAT_IMPORT_TARIFF",
            "Flat 0.50 currency/kWh import tariff.",
            tariff=(0.50,) * _HOURS_PER_DAY,
        ),
        scenario(
            "A19_WEAK_TOU_SPREAD",
            "Weak 0.45/0.50/0.55 import tariff spread.",
            tariff=weak_tou,
        ),
        scenario(
            "A20_STRONG_TOU_SPREAD",
            "Strong 0.10/0.50/1.20 import tariff spread.",
            tariff=strong_tou,
        ),
        scenario(
            "A21_HIGH_EXPORT_TARIFF",
            "Reference control facts with export tariff 0.60 currency/kWh.",
            export_tariff=0.60,
        ),
        scenario(
            "A22_ZERO_EXPORT_REVENUE",
            "Reference control facts with export tariff 0.00 currency/kWh.",
            export_tariff=0.00,
        ),
        scenario(
            "A23_LOW_PCS_POWER",
            "Reference profiles with 1.50 kW charge/discharge PCS limit.",
            model=low_pcs_model,
        ),
        scenario(
            "A24_HIGH_DEGRADATION_COST",
            "Reference control facts with degradation rate 0.15 currency/kWh throughput.",
            degradation=0.15,
        ),
    )
    if len(scenarios) != 24 or len({item.scenario_id for item in scenarios}) != 24:
        raise AssertionError("Phase A must contain exactly 24 unique scenarios")
    return scenarios


def run_residential_campaign_a(output_directory: Path) -> ResidentialCampaignAResult:
    """Run 24 deterministic scenarios x two frozen strategies exactly once."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    evaluator = DeterministicResidentialAcceptanceEvaluator()
    results = tuple(
        _run_scenario(scenario, output_directory / scenario.scenario_id, evaluator)
        for scenario in campaign_scenarios()
    )
    paths = tuple(
        path for result in results for path in (result.schedule, result.economic)
    )
    if len(paths) != 48:
        raise AssertionError("Phase A must complete exactly 48 daily trajectories")
    hard_passed = _hard_passed(paths)
    shortlist = _anomaly_shortlist(results)
    scenarios_csv_path = output_directory / "campaign_scenarios.csv"
    results_csv_path = output_directory / "campaign_results.csv"
    comparisons_csv_path = output_directory / "campaign_comparisons.csv"
    findings_csv_path = output_directory / "campaign_findings.csv"
    summary_path = output_directory / "campaign_summary.txt"
    adjusted_cost_svg_path = output_directory / "adjusted_cost_by_scenario.svg"
    grid_import_svg_path = output_directory / "grid_import_by_scenario.svg"
    throughput_svg_path = output_directory / "battery_throughput_by_scenario.svg"
    final_soc_svg_path = output_directory / "final_soc_by_scenario.svg"
    cost_delta_svg_path = output_directory / "economic_minus_schedule_cost_delta.svg"
    scenarios_csv_path.write_text(
        _scenarios_csv(campaign_scenarios()), encoding="utf-8", newline=""
    )
    results_csv_path.write_text(_results_csv(paths), encoding="utf-8", newline="")
    comparisons_csv_path.write_text(
        _comparisons_csv(results), encoding="utf-8", newline=""
    )
    findings_csv_path.write_text(_findings_csv(paths), encoding="utf-8", newline="")
    summary_path.write_text(
        _summary(results, shortlist, hard_passed), encoding="utf-8", newline=""
    )
    adjusted_cost_svg_path.write_text(
        _paired_svg(
            "Adjusted net economic cost",
            results,
            lambda item: (
                item.schedule.kpi.adjusted_net_economic_cost,
                item.economic.kpi.adjusted_net_economic_cost,
            ),
        ),
        encoding="utf-8",
        newline="",
    )
    grid_import_svg_path.write_text(
        _paired_svg(
            "Grid import energy (kWh)",
            results,
            lambda item: (
                item.schedule.kpi.grid_import_energy_kwh,
                item.economic.kpi.grid_import_energy_kwh,
            ),
        ),
        encoding="utf-8",
        newline="",
    )
    throughput_svg_path.write_text(
        _paired_svg(
            "Battery throughput (kWh)",
            results,
            lambda item: (
                item.schedule.kpi.battery_throughput_kwh,
                item.economic.kpi.battery_throughput_kwh,
            ),
        ),
        encoding="utf-8",
        newline="",
    )
    final_soc_svg_path.write_text(
        _paired_svg(
            "Final actual SOC",
            results,
            lambda item: (
                item.schedule.kpi.final_soc_fraction,
                item.economic.kpi.final_soc_fraction,
            ),
        ),
        encoding="utf-8",
        newline="",
    )
    cost_delta_svg_path.write_text(
        _single_svg(
            "Economic minus Schedule adjusted cost",
            results,
            lambda item: item.comparison.delta_adjusted_cost,
        ),
        encoding="utf-8",
        newline="",
    )
    return ResidentialCampaignAResult(
        campaign_scenarios(),
        results,
        hard_passed,
        shortlist,
        scenarios_csv_path,
        results_csv_path,
        comparisons_csv_path,
        findings_csv_path,
        summary_path,
        adjusted_cost_svg_path,
        grid_import_svg_path,
        throughput_svg_path,
        final_soc_svg_path,
        cost_delta_svg_path,
    )


def _run_scenario(
    scenario: ResidentialCampaignScenario,
    output_directory: Path,
    evaluator: DeterministicResidentialAcceptanceEvaluator,
) -> ResidentialCampaignScenarioResult:
    output_directory.mkdir(parents=True, exist_ok=True)
    schedule_input, economic_input = _inputs(scenario, output_directory)
    schedule_trajectory = _schedule_runner(scenario.candidate_configuration).run(
        schedule_input
    )
    economic_trajectory = _economic_runner(scenario.candidate_configuration).run(
        economic_input
    )
    schedule_ledger = _ledger(schedule_trajectory, scenario)
    economic_ledger = _ledger(economic_trajectory, scenario)
    comparison = DeterministicEconomicComparisonExplainer().explain(
        EconomicComparisonInput(
            "Schedule",
            "Economic",
            schedule_ledger.extended_outcome_evidence,
            economic_ledger.extended_outcome_evidence,
            scenario.scenario_id,
            "TASK-173 ledger outcomes; candidate minus reference.",
        )
    )
    reconciled = isclose(
        comparison.delta_adjusted_cost,
        sum(
            (
                comparison.import_cost_contribution,
                comparison.export_revenue_contribution,
                comparison.degradation_cost_contribution,
                comparison.terminal_value_contribution,
            )
        ),
        rel_tol=0.0,
        abs_tol=NUMERIC_TOLERANCE,
    )
    schedule_kpi = _kpi(
        scenario, "Schedule", schedule_trajectory, schedule_ledger, reconciled
    )
    economic_kpi = _kpi(
        scenario, "Economic", economic_trajectory, economic_ledger, reconciled
    )
    acceptance_scenario = ResidentialAcceptanceScenario(
        scenario.scenario_id,
        scenario.scenario_id,
        scenario.export_policy,
        scenario.description,
    )
    schedule = ResidentialCampaignPathResult(
        scenario,
        "Schedule",
        schedule_trajectory,
        schedule_ledger,
        schedule_kpi,
        evaluator.evaluate(
            acceptance_scenario,
            schedule_kpi,
            _anchor_findings(
                scenario,
                "Schedule",
                schedule_kpi,
                economic_kpi,
                comparison,
                economic_trajectory,
            ),
        ),
    )
    economic = ResidentialCampaignPathResult(
        scenario,
        "Economic",
        economic_trajectory,
        economic_ledger,
        economic_kpi,
        evaluator.evaluate(
            acceptance_scenario,
            economic_kpi,
            _anchor_findings(
                scenario,
                "Economic",
                schedule_kpi,
                economic_kpi,
                comparison,
                economic_trajectory,
            ),
        ),
    )
    return ResidentialCampaignScenarioResult(scenario, schedule, economic, comparison)


def _inputs(
    scenario: ResidentialCampaignScenario, output_directory: Path
) -> tuple[
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationInput,
]:
    """Compose the same exact exogenous facts for both frozen primary paths."""

    template = create_demo_input(output_directory)
    model = scenario.battery_model
    daily = DailySimulationScenarioInput(
        template.integration_input.daily_input.step_identities,
        scenario.pv_profile_kw,
        scenario.load_profile_kw,
        scenario.import_tariff_profile_per_kwh,
        BatteryParameters(
            model.usable_capacity_kwh,
            model.max_charge_power_kw,
            model.max_discharge_power_kw,
            model.charge_efficiency,
            model.discharge_efficiency,
            model.min_soc_fraction,
        ),
        scenario.initial_soc_fraction,
    )
    integration_template = template.integration_input
    integration = EMSIntegrationScenarioInput(
        daily,
        integration_template.objective_composition,
        integration_template.capability,
        max(model.max_charge_power_kw, model.max_discharge_power_kw),
        integration_template.export_limit_kw,
        integration_template.initial_grid_power_kw,
    )
    horizons = _finite_horizons(daily)
    schedule_daily = ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        model,
        template.explanation_locale,
        output_directory / "schedule_mpc_decisions.csv",
    )
    economic_daily = ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        model,
        template.explanation_locale,
        output_directory / "economic_mpc_decisions.csv",
    )
    opportunity = PVOpportunityWindowConfiguration(_GAP_TOLERANCE_POINTS)
    return (
        MultiOpportunityExplainableMPCDailySimulationInput(
            schedule_daily, scenario.candidate_configuration, opportunity
        ),
        MultiOpportunityExplainableMPCDailySimulationInput(
            economic_daily, scenario.candidate_configuration, opportunity
        ),
    )


def _ledger(
    trajectory: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    scenario: ResidentialCampaignScenario,
) -> DailyEconomicLedger:
    return DeterministicEconomicLedgerBuilder().build(
        EconomicLedgerInput(
            trajectory,
            (scenario.export_tariff_per_kwh,) * _HOURS_PER_DAY,
            (scenario.degradation_cost_per_throughput_kwh,) * _HOURS_PER_DAY,
            scenario.terminal_valuation_per_kwh,
            scenario.battery_model,
        )
    )


def _kpi(
    scenario: ResidentialCampaignScenario,
    strategy: str,
    trajectory: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    ledger: DailyEconomicLedger,
    comparison_reconciled: bool,
) -> ResidentialAcceptanceKPI:
    traces = trajectory.step_traces
    model = scenario.battery_model
    powers = tuple(
        trace.simulation_trace.state.battery_result.actual_power_kw for trace in traces
    )
    balances = sum(
        not isclose(
            trace.simulation_trace.state.pv_result.actual_power_kw
            + trace.simulation_trace.state.grid_result.actual_grid_power_kw
            - trace.simulation_trace.state.battery_result.actual_power_kw,
            trace.simulation_trace.state.load_result.actual_power_kw,
            rel_tol=0.0,
            abs_tol=NUMERIC_TOLERANCE,
        )
        for trace in traces
    )
    return ResidentialAcceptanceKPI(
        scenario.scenario_id,
        strategy,
        ledger.total_load_energy_kwh,
        ledger.total_pv_energy_kwh,
        ledger.total_grid_import_energy_kwh,
        ledger.total_grid_export_energy_kwh,
        ledger.total_battery_throughput_kwh,
        ledger.final_soc_fraction,
        sum(trace.journal_record.final_action.action == "charge" for trace in traces),
        sum(
            trace.journal_record.final_action.action == "discharge" for trace in traces
        ),
        sum(trace.journal_record.final_action.action == "idle" for trace in traces),
        sum(trace.journal_record.revision_applied for trace in traces),
        _headroom_limit_count(trajectory),
        ledger.total_realized_import_cost,
        ledger.total_realized_export_revenue,
        ledger.total_battery_degradation_cost,
        ledger.terminal_energy_value,
        ledger.adjusted_net_economic_cost,
        sum(
            interval.soc_after_fraction < model.min_soc_fraction - NUMERIC_TOLERANCE
            for interval in ledger.intervals
        ),
        sum(
            interval.soc_after_fraction > model.max_soc_fraction + NUMERIC_TOLERANCE
            for interval in ledger.intervals
        ),
        sum(power > model.max_charge_power_kw + NUMERIC_TOLERANCE for power in powers),
        sum(
            power < -model.max_discharge_power_kw - NUMERIC_TOLERANCE
            for power in powers
        ),
        balances,
        sum(trace.journal_record.final_action.action != "idle" for trace in traces),
        sum(not trace.journal_record.formatted_text for trace in traces),
        _actual_feedback_used(trajectory),
        isclose(
            ledger.adjusted_net_economic_cost,
            ledger.extended_outcome_evidence.adjusted_net_economic_cost,
            rel_tol=0.0,
            abs_tol=NUMERIC_TOLERANCE,
        ),
        comparison_reconciled,
        all(
            trace.decision_provenance.decision
            is trace.feasible_decision.source_decision
            and trace.feasible_decision.source_provenance is trace.decision_provenance
            and trace.handoff.source_feasible_decision is trace.feasible_decision
            for trace in traces
        ),
        True,
    )


def _actual_feedback_used(
    trajectory: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> bool:
    if isinstance(
        trajectory,
        EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    ):
        return _economic_actual_feedback_used(trajectory)
    return _schedule_actual_feedback_used(trajectory)


def _economic_actual_feedback_used(
    trajectory: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> bool:
    traces = trajectory.step_traces
    return all(
        index == 0
        or (
            trace.context.source_context.soc
            == traces[index - 1].simulation_trace.state.battery_result.next_state.soc
            and trace.context.source_context.grid_power_kw
            == traces[index - 1].simulation_trace.state.grid_result.actual_grid_power_kw
        )
        for index, trace in enumerate(traces)
    )


def _schedule_actual_feedback_used(
    trajectory: MultiOpportunityExplainableMPCDailySimulationResult,
) -> bool:
    traces = trajectory.step_traces
    return all(
        index == 0
        or (
            trace.context.source_context.soc
            == traces[index - 1].simulation_trace.state.battery_result.next_state.soc
            and trace.context.source_context.grid_power_kw
            == traces[index - 1].simulation_trace.state.grid_result.actual_grid_power_kw
        )
        for index, trace in enumerate(traces)
    )


def _headroom_limit_count(
    trajectory: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> int:
    if not isinstance(
        trajectory, EconomicMultiOpportunityExplainableMPCDailySimulationResult
    ):
        return 0
    return sum(
        trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.reservation_result
        is not None
        and trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.reservation_result.reservation_applied
        for trace in trajectory.step_traces
    )


def _anchor_findings(
    scenario: ResidentialCampaignScenario,
    strategy: str,
    schedule: ResidentialAcceptanceKPI,
    economic: ResidentialAcceptanceKPI,
    comparison: EconomicComparisonExplanation,
    economic_trajectory: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> tuple[ResidentialAcceptanceFinding, ...]:
    passed = True
    expected = ""
    actual = ""
    if scenario.scenario_id == "A01_REFERENCE_TASK175":
        expected = "TASK-175 fingerprint and Schedule/Economic tie"
        passed = (
            all(
                isclose(value, target, rel_tol=0.0, abs_tol=1e-6)
                for value, target in zip(
                    (
                        schedule.load_energy_kwh,
                        schedule.pv_energy_kwh,
                        schedule.grid_import_energy_kwh,
                        schedule.grid_export_energy_kwh,
                        schedule.battery_throughput_kwh,
                        schedule.final_soc_fraction,
                        schedule.adjusted_net_economic_cost,
                    ),
                    (27.1, 14.3, 13.122438, 2.659280, 12.863158, 0.2, 5.285789),
                    strict=True,
                )
            )
            and comparison.ranking is EconomicComparisonRanking.TIED
        )
        actual = f"schedule_cost={schedule.adjusted_net_economic_cost:.6f}; ranking={comparison.ranking.value}"
    elif scenario.scenario_id == "A02_NEGATIVE_ECONOMIC_SHIFT":
        suppressed = _suppressed_grid_charge(economic_trajectory)
        expected = (
            "negative economics suppresses cheap-grid charge without acceptance failure"
        )
        passed = (
            suppressed > 0.0
            and comparison.ranking is EconomicComparisonRanking.CANDIDATE_BETTER
        )
        actual = f"suppressed_grid_charge_kwh={suppressed:.6f}; ranking={comparison.ranking.value}"
    elif scenario.scenario_id == "A03_TERMINAL_SOC_DIVERGENCE":
        expected = "TASK-165 terminal SOC divergence remains observable"
        passed = (
            schedule.final_soc_fraction
            > economic.final_soc_fraction + NUMERIC_TOLERANCE
            and comparison.terminal_value_contribution > 0.0
        )
        actual = f"schedule_soc={schedule.final_soc_fraction:.6f}; economic_soc={economic.final_soc_fraction:.6f}; terminal_contribution={comparison.terminal_value_contribution:.6f}"
    else:
        return ()
    return (
        ResidentialAcceptanceFinding(
            scenario.scenario_id,
            ResidentialAcceptanceCategory.QUALITY_METRIC,
            "anchor_reference",
            ResidentialAcceptanceSeverity.BLOCKER,
            ResidentialAcceptanceStatus.PASS
            if passed
            else ResidentialAcceptanceStatus.FAIL,
            expected,
            actual,
            "campaign anchor preserved" if passed else "campaign anchor drifted",
        ),
    )


def _suppressed_grid_charge(
    trajectory: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> float:
    return sum(
        max(
            value.headroom_allowed_grid_charge_power_kw
            - value.economically_supported_grid_charge_power_kw,
            0.0,
        )
        * trace.simulation_trace.simulation_input.step_identity.duration_seconds
        / 3600.0
        for trace in trajectory.step_traces
        if (
            value
            := trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.economic_value_result
        )
        is not None
    )


def _hard_passed(paths: Iterable[ResidentialCampaignPathResult]) -> bool:
    return not any(
        finding.status is ResidentialAcceptanceStatus.FAIL
        and finding.severity
        in {ResidentialAcceptanceSeverity.BLOCKER, ResidentialAcceptanceSeverity.MAJOR}
        for path in paths
        for finding in path.acceptance.findings
    )


def _anomaly_shortlist(
    results: tuple[ResidentialCampaignScenarioResult, ...],
) -> tuple[str, ...]:
    all_paths = tuple(
        path for result in results for path in (result.schedule, result.economic)
    )
    throughput_median = _median(
        tuple(path.kpi.battery_throughput_kwh for path in all_paths)
    )
    revision_median = _median(
        tuple(float(path.kpi.physical_revision_count) for path in all_paths)
    )
    shortlisted: list[str] = []
    for result in results:
        failures = tuple(
            finding
            for path in (result.schedule, result.economic)
            for finding in path.acceptance.findings
            if finding.status is ResidentialAcceptanceStatus.FAIL
            and finding.severity
            in {
                ResidentialAcceptanceSeverity.BLOCKER,
                ResidentialAcceptanceSeverity.MAJOR,
            }
        )
        reasons: list[str] = []
        if failures:
            reasons.append("hard_acceptance_failure")
        if result.comparison.delta_adjusted_cost > _MEANINGFUL_COST_LOSS:
            reasons.append("economic_meaningful_loss")
        if abs(result.comparison.delta_adjusted_cost) > _LARGE_COST_DIVERGENCE:
            reasons.append("large_cost_divergence")
        if (
            max(
                result.schedule.kpi.battery_throughput_kwh,
                result.economic.kpi.battery_throughput_kwh,
            )
            > 1.5 * throughput_median
        ):
            reasons.append("high_throughput_vs_campaign_median")
        if (
            max(
                result.schedule.kpi.physical_revision_count,
                result.economic.kpi.physical_revision_count,
            )
            > revision_median + 2.0
        ):
            reasons.append("high_physical_revisions_vs_campaign_median")
        if result.scenario.scenario_id == "A01_REFERENCE_TASK175" and failures:
            reasons.append("reference_metric_drift")
        if reasons:
            shortlisted.append(f"{result.scenario.scenario_id}: {','.join(reasons)}")
    return tuple(shortlisted)


def _scenarios_csv(scenarios: Iterable[ResidentialCampaignScenario]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "description",
            "load_profile_kw",
            "pv_profile_kw",
            "import_tariff_profile_per_kwh",
            "export_tariff_per_kwh",
            "initial_soc_fraction",
            "battery_capacity_kwh",
            "min_soc_fraction",
            "max_soc_fraction",
            "max_charge_power_kw",
            "max_discharge_power_kw",
            "charge_efficiency",
            "discharge_efficiency",
            "candidate_low_price_threshold",
            "candidate_high_price_threshold",
            "candidate_grid_charge_power_kw",
            "degradation_cost_per_throughput_kwh",
            "terminal_valuation_per_kwh",
            "export_policy",
            "forecast_semantics",
        )
    )
    for item in scenarios:
        model = item.battery_model
        configuration = item.candidate_configuration
        writer.writerow(
            (
                item.scenario_id,
                item.description,
                _profile(item.load_profile_kw),
                _profile(item.pv_profile_kw),
                _profile(item.import_tariff_profile_per_kwh),
                _number(item.export_tariff_per_kwh),
                _number(item.initial_soc_fraction),
                _number(model.usable_capacity_kwh),
                _number(model.min_soc_fraction),
                _number(model.max_soc_fraction),
                _number(model.max_charge_power_kw),
                _number(model.max_discharge_power_kw),
                _number(model.charge_efficiency),
                _number(model.discharge_efficiency),
                _number(configuration.low_price_threshold_cny_per_kwh),
                _number(configuration.high_price_threshold_cny_per_kwh),
                _number(configuration.requested_grid_charge_power_kw),
                _number(item.degradation_cost_per_throughput_kwh),
                _number(item.terminal_valuation_per_kwh),
                item.export_policy,
                item.forecast_semantics,
            )
        )
    return stream.getvalue()


def _results_csv(paths: Iterable[ResidentialCampaignPathResult]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "strategy",
            "initial_soc_fraction",
            "battery_capacity_kwh",
            "max_charge_power_kw",
            "max_discharge_power_kw",
            "load_energy_kwh",
            "pv_energy_kwh",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
            "battery_throughput_kwh",
            "final_soc_fraction",
            "realized_import_cost",
            "realized_export_revenue",
            "battery_degradation_cost",
            "terminal_energy_value",
            "adjusted_net_economic_cost",
            "charge_count",
            "discharge_count",
            "idle_count",
            "physical_revision_count",
            "headroom_limit_count",
            "min_soc_violation_count",
            "max_soc_violation_count",
            "charge_power_violation_count",
            "discharge_power_violation_count",
            "energy_balance_violation_count",
            "blocker_count",
            "major_count",
            "minor_count",
            "informational_count",
            "acceptance_status",
        )
    )
    for path in paths:
        kpi = path.kpi
        counts = _severity_counts(path.acceptance.findings)
        writer.writerow(
            (
                path.scenario.scenario_id,
                path.strategy,
                _number(path.scenario.initial_soc_fraction),
                _number(path.scenario.battery_model.usable_capacity_kwh),
                _number(path.scenario.battery_model.max_charge_power_kw),
                _number(path.scenario.battery_model.max_discharge_power_kw),
                *(
                    _number(value)
                    for value in (
                        kpi.load_energy_kwh,
                        kpi.pv_energy_kwh,
                        kpi.grid_import_energy_kwh,
                        kpi.grid_export_energy_kwh,
                        kpi.battery_throughput_kwh,
                        kpi.final_soc_fraction,
                        kpi.import_cost,
                        kpi.export_revenue,
                        kpi.degradation_cost,
                        kpi.terminal_value,
                        kpi.adjusted_net_economic_cost,
                    )
                ),
                kpi.charge_count,
                kpi.discharge_count,
                kpi.idle_count,
                kpi.physical_revision_count,
                kpi.headroom_limit_count,
                kpi.min_soc_violation_count,
                kpi.max_soc_violation_count,
                kpi.charge_power_violation_count,
                kpi.discharge_power_violation_count,
                kpi.energy_balance_violation_count,
                counts[ResidentialAcceptanceSeverity.BLOCKER],
                counts[ResidentialAcceptanceSeverity.MAJOR],
                counts[ResidentialAcceptanceSeverity.MINOR],
                counts[ResidentialAcceptanceSeverity.INFORMATIONAL],
                "pass" if _path_hard_passed(path) else "fail",
            )
        )
    return stream.getvalue()


def _comparisons_csv(results: Iterable[ResidentialCampaignScenarioResult]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "ranking",
            "schedule_adjusted_cost",
            "economic_adjusted_cost",
            "delta_adjusted_cost",
            "delta_import_cost",
            "delta_export_revenue",
            "delta_degradation_cost",
            "delta_terminal_value",
            "import_contribution",
            "export_contribution",
            "degradation_contribution",
            "terminal_contribution",
            "dominant_components",
        )
    )
    for result in results:
        item = result.comparison
        writer.writerow(
            (
                result.scenario.scenario_id,
                item.ranking.value,
                _number(item.reference_adjusted_net_economic_cost),
                _number(item.candidate_adjusted_net_economic_cost),
                _number(item.delta_adjusted_cost),
                _number(item.delta_import_cost),
                _number(item.delta_export_revenue),
                _number(item.delta_degradation_cost),
                _number(item.delta_terminal_value),
                _number(item.import_cost_contribution),
                _number(item.export_revenue_contribution),
                _number(item.degradation_cost_contribution),
                _number(item.terminal_value_contribution),
                "|".join(component.value for component in item.dominant_components),
            )
        )
    return stream.getvalue()


def _findings_csv(paths: Iterable[ResidentialCampaignPathResult]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "strategy",
            "category",
            "criterion_id",
            "severity",
            "status",
            "expected",
            "actual",
            "message",
        )
    )
    for path in paths:
        for finding in path.acceptance.findings:
            writer.writerow(
                (
                    path.scenario.scenario_id,
                    path.strategy,
                    finding.category.value,
                    finding.criterion_id,
                    finding.severity.value,
                    finding.status.value,
                    finding.expected,
                    finding.actual,
                    finding.message,
                )
            )
    return stream.getvalue()


def _summary(
    results: tuple[ResidentialCampaignScenarioResult, ...],
    shortlist: tuple[str, ...],
    hard_passed: bool,
) -> str:
    paths = tuple(
        path for result in results for path in (result.schedule, result.economic)
    )
    counts = Counter(
        finding.severity
        for path in paths
        for finding in path.acceptance.findings
        if finding.status is ResidentialAcceptanceStatus.FAIL
    )
    rankings = Counter(result.comparison.ranking for result in results)
    best = min(results, key=lambda item: item.comparison.delta_adjusted_cost)
    worst = max(results, key=lambda item: item.comparison.delta_adjusted_cost)
    divergence = max(results, key=lambda item: abs(item.comparison.delta_adjusted_cost))
    highest_throughput = max(paths, key=lambda item: item.kpi.battery_throughput_kwh)
    highest_import = max(paths, key=lambda item: item.kpi.grid_import_energy_kwh)
    highest_export = max(paths, key=lambda item: item.kpi.grid_export_energy_kwh)
    lowest_soc = min(paths, key=lambda item: item.kpi.final_soc_fraction)
    highest_revision = max(paths, key=lambda item: item.kpi.physical_revision_count)
    return "\n".join(
        (
            "EOS Residential EMS 1.0 Campaign A — Deterministic Baseline Matrix",
            "forecast_semantics=perfect caller-supplied forecast equals realized exogenous trajectory; no forecast-error validation is implied.",
            "export_policy=export allowed and settled at each scenario's explicit export tariff; zero-export is not active.",
            "hard_acceptance=PASS only when zero BLOCKER and zero MAJOR findings; a strategy losing economically is an experimental observation, not an acceptance failure.",
            f"campaign_hard_status={'PASS' if hard_passed else 'FAIL'}",
            f"scenario_count={len(results)} completed_trajectory_count={len(paths)} accepted_trajectory_count={sum(_path_hard_passed(path) for path in paths)}",
            f"blocker_count={counts[ResidentialAcceptanceSeverity.BLOCKER]} major_count={counts[ResidentialAcceptanceSeverity.MAJOR]} minor_count={counts[ResidentialAcceptanceSeverity.MINOR]} informational_count={counts[ResidentialAcceptanceSeverity.INFORMATIONAL]}",
            f"economic_wins={rankings[EconomicComparisonRanking.CANDIDATE_BETTER]} schedule_wins={rankings[EconomicComparisonRanking.REFERENCE_BETTER]} ties={rankings[EconomicComparisonRanking.TIED]}",
            f"largest_economic_accounting_advantage={best.scenario.scenario_id}:{_number(best.comparison.delta_adjusted_cost)}",
            f"largest_economic_accounting_disadvantage={worst.scenario.scenario_id}:{_number(worst.comparison.delta_adjusted_cost)}",
            f"largest_absolute_strategy_divergence={divergence.scenario.scenario_id}:{_number(divergence.comparison.delta_adjusted_cost)}",
            f"highest_throughput={highest_throughput.scenario.scenario_id}/{highest_throughput.strategy}:{_number(highest_throughput.kpi.battery_throughput_kwh)}",
            f"highest_grid_import={highest_import.scenario.scenario_id}/{highest_import.strategy}:{_number(highest_import.kpi.grid_import_energy_kwh)}",
            f"highest_grid_export={highest_export.scenario.scenario_id}/{highest_export.strategy}:{_number(highest_export.kpi.grid_export_energy_kwh)}",
            f"lowest_final_soc={lowest_soc.scenario.scenario_id}/{lowest_soc.strategy}:{_number(lowest_soc.kpi.final_soc_fraction)}",
            f"highest_physical_revision_count={highest_revision.scenario.scenario_id}/{highest_revision.strategy}:{highest_revision.kpi.physical_revision_count}",
            "anomaly_thresholds=Economic loss > 0.25; absolute strategy cost divergence > 0.50; throughput > 1.5x campaign median; physical revisions > campaign median + 2; any blocker/major failure.",
            "anomaly_shortlist=" + ("; ".join(shortlist) if shortlist else "none"),
            "functional_freeze=Campaign A adds validation tooling only. It is not proof of PCS control, field safety, real-weather robustness, or hardware/customer deployment readiness.",
            "",
        )
    )


def _paired_svg(
    title: str,
    results: Iterable[ResidentialCampaignScenarioResult],
    getter: Callable[[ResidentialCampaignScenarioResult], tuple[float, float]],
) -> str:
    values = tuple(getter(item) for item in results)
    maximum = max(1.0, *(value for pair in values for value in pair))
    bars = "".join(
        f'<rect x="{55 + index * 38 + side * 12}" y="{250 - value / maximum * 190:.2f}" width="9" height="{value / maximum * 190:.2f}" fill="{("#2563eb", "#059669")[side]}"/>'
        for index, pair in enumerate(values)
        for side, value in enumerate(pair)
    )
    labels = "".join(
        f'<text x="{55 + index * 38}" y="274" font-size="7">{index + 1:02d}</text>'
        for index in range(len(values))
    )
    return _svg(
        title,
        bars,
        labels
        + '<text x="55" y="310" fill="#2563eb">Schedule</text><text x="130" y="310" fill="#059669">Economic</text>',
    )


def _single_svg(
    title: str,
    results: Iterable[ResidentialCampaignScenarioResult],
    getter: Callable[[ResidentialCampaignScenarioResult], float],
) -> str:
    values = tuple(getter(item) for item in results)
    maximum, minimum = max(1.0, *values), min(0.0, *values)
    scale = max(maximum - minimum, 1.0)
    baseline = 250 - (0.0 - minimum) / scale * 190
    bars = "".join(
        f'<rect x="{55 + index * 38}" y="{min(baseline, 250 - (value - minimum) / scale * 190):.2f}" width="12" height="{abs(baseline - (250 - (value - minimum) / scale * 190)):.2f}" fill="{"#059669" if value <= 0.0 else "#dc2626"}"/>'
        for index, value in enumerate(values)
    )
    labels = "".join(
        f'<text x="{55 + index * 38}" y="274" font-size="7">{index + 1:02d}</text>'
        for index in range(len(values))
    )
    return _svg(
        title,
        bars,
        labels
        + '<text x="55" y="310">green=Economic advantage; red=Schedule advantage</text>',
    )


def _svg(title: str, content: str, footer: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="340" viewBox="0 0 1024 340"><rect width="100%" height="100%" fill="white"/><text x="40" y="28" font-family="sans-serif" font-size="16">{title}</text><line x1="40" y1="250" x2="990" y2="250" stroke="#64748b"/>{content}{footer}</svg>\n'


def _path_hard_passed(path: ResidentialCampaignPathResult) -> bool:
    return not any(
        finding.status is ResidentialAcceptanceStatus.FAIL
        and finding.severity
        in {ResidentialAcceptanceSeverity.BLOCKER, ResidentialAcceptanceSeverity.MAJOR}
        for finding in path.acceptance.findings
    )


def _severity_counts(
    findings: Iterable[ResidentialAcceptanceFinding],
) -> Counter[ResidentialAcceptanceSeverity]:
    return Counter(
        finding.severity
        for finding in findings
        if finding.status is ResidentialAcceptanceStatus.FAIL
    )


def _median(values: tuple[float, ...]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return (
        (ordered[middle - 1] + ordered[middle]) / 2.0
        if len(ordered) % 2 == 0
        else ordered[middle]
    )


def _replace(
    values: tuple[float, ...], indexes: tuple[int, ...], replacements: tuple[float, ...]
) -> tuple[float, ...]:
    changed = list(values)
    for index, replacement in zip(indexes, replacements, strict=True):
        changed[index] = replacement
    return tuple(changed)


def _scale(values: tuple[float, ...], factor: float) -> tuple[float, ...]:
    return tuple(value * factor for value in values)


def _add(
    values: tuple[float, ...], indexes: range, addition: float
) -> tuple[float, ...]:
    changed = list(values)
    for index in indexes:
        changed[index] += addition
    return tuple(changed)


def _profile(values: tuple[float, ...]) -> str:
    return "|".join(_number(value) for value in values)


def _number(value: float) -> str:
    return f"{value:.6f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS Residential EMS deterministic Campaign A"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("simulation_output_campaign_a")
    )
    arguments = parser.parse_args(argv)
    result = run_residential_campaign_a(arguments.output_dir)
    for path in (
        result.scenarios_csv_path,
        result.results_csv_path,
        result.comparisons_csv_path,
        result.findings_csv_path,
        result.summary_path,
        result.adjusted_cost_svg_path,
        result.grid_import_svg_path,
        result.throughput_svg_path,
        result.final_soc_svg_path,
        result.cost_delta_svg_path,
    ):
        print(path)
    print("PASS" if result.hard_passed else "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
