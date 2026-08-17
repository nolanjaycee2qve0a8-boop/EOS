# ruff: noqa: E501
"""Residential EMS 1.0 Campaign C: deterministic forecast-error characterization.

This post-freeze campaign composes existing daily runners with separate,
caller-owned forecast facts and realized Simulator facts.  It changes no
residential control capability, contract, ledger, comparison, or execution
behavior.
"""

import argparse
import csv
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from io import StringIO
from math import isclose
from pathlib import Path
from xml.sax.saxutils import escape

from ems_simulator.economic_comparison_explanation import (
    DeterministicEconomicComparisonExplainer,
    EconomicComparisonExplanation,
    EconomicComparisonInput,
    EconomicComparisonRanking,
)
from ems_simulator.economic_ledger import DailyEconomicLedger
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner,
    _schedule_runner,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import (
    HOURS_PER_DAY,
    BatteryParameters,
    DailySimulationScenarioInput,
)
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
    ResidentialAcceptanceKPI,
    ResidentialAcceptanceResult,
    ResidentialAcceptanceScenario,
    ResidentialAcceptanceSeverity,
)
from ems_simulator.residential_campaign_a import (
    ResidentialCampaignScenario,
    _kpi,
    _ledger,
    campaign_scenarios,
)
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationModel,
    NetLoadAwareBaselineOptimizationConfiguration,
    PVOpportunityWindowConfiguration,
)

_FORECAST_FALLBACK_TARIFF = 0.50
_ENVIRONMENT_SOURCES = (
    ("REFERENCE", "A01_REFERENCE_TASK175"),
    ("HIGH_EVENING_LOAD", "A16_EVENING_PEAK"),
    ("HIGH_PV", "A10_HIGH_PV"),
)

# Frozen Campaign A fingerprints.  Campaign C executes each perfect path once
# (as part of its own 78-path matrix) and compares that resulting evidence to
# the established source-environment values; it never executes a second
# perfect trajectory merely to create this comparison.
_PERFECT_ANCHOR_FINGERPRINTS: dict[tuple[str, str], tuple[float, ...]] = {
    ("C_REFERENCE_PERFECT", "Schedule"): (
        13.122438,
        2.659280,
        12.863158,
        0.2,
        5.0,
        0.0,
        5.174488,
        0.531856,
        0.643158,
        0.0,
        5.285789,
    ),
    ("C_REFERENCE_PERFECT", "Economic"): (
        13.122438,
        2.659280,
        12.863158,
        0.2,
        5.0,
        6.0,
        5.174488,
        0.531856,
        0.643158,
        0.0,
        5.285789,
    ),
    ("C_HIGH_EVENING_LOAD_PERFECT", "Schedule"): (
        20.322438,
        2.659280,
        12.863158,
        0.2,
        8.0,
        0.0,
        11.654488,
        0.531856,
        0.643158,
        0.0,
        11.765789,
    ),
    ("C_HIGH_EVENING_LOAD_PERFECT", "Economic"): (
        20.322438,
        2.659280,
        12.863158,
        0.2,
        8.0,
        6.0,
        11.654488,
        0.531856,
        0.643158,
        0.0,
        11.765789,
    ),
    ("C_HIGH_PV_PERFECT", "Schedule"): (
        11.750000,
        8.436842,
        12.863158,
        0.2,
        6.0,
        0.0,
        4.795000,
        1.687368,
        0.643158,
        0.0,
        3.750789,
    ),
    ("C_HIGH_PV_PERFECT", "Economic"): (
        11.750000,
        8.436842,
        12.863158,
        0.2,
        6.0,
        6.0,
        4.795000,
        1.687368,
        0.643158,
        0.0,
        3.750789,
    ),
}


@dataclass(frozen=True, slots=True)
class ResidentialCampaignCScenario:
    """Immutable validation facts with intentionally separate forecast/actual data."""

    scenario_id: str
    environment: str
    forecast_error_case_id: str
    description: str
    realized_pv_profile_kw: tuple[float, ...]
    forecast_pv_profile_kw: tuple[float, ...]
    realized_load_profile_kw: tuple[float, ...]
    forecast_load_profile_kw: tuple[float, ...]
    realized_tariff_profile_cny_per_kwh: tuple[float, ...]
    forecast_tariff_profile_cny_per_kwh: tuple[float, ...]
    export_tariff_per_kwh: float
    initial_soc_fraction: float
    battery_model: BatteryOptimizationModel
    candidate_configuration: NetLoadAwareBaselineOptimizationConfiguration
    degradation_cost_per_throughput_kwh: float
    terminal_valuation_per_kwh: float
    export_policy: str
    forecast_semantics: str
    realized_source_scenario_id: str
    perfect_anchor_id: str
    transformation_metadata: str


@dataclass(frozen=True, slots=True)
class ForecastErrorEvidence:
    """Deterministic forecast-minus-realized error metrics for one scenario."""

    scenario: ResidentialCampaignCScenario
    pv_signed_daily_energy_bias_kwh: float
    pv_mean_absolute_error_kw: float
    pv_maximum_absolute_error_kw: float
    load_signed_daily_energy_bias_kwh: float
    load_mean_absolute_error_kw: float
    load_maximum_absolute_error_kw: float
    tariff_signed_mean_bias_cny_per_kwh: float
    tariff_mean_absolute_error_cny_per_kwh: float
    tariff_maximum_absolute_error_cny_per_kwh: float


@dataclass(frozen=True, slots=True)
class ResidentialCampaignCPathResult:
    """One freshly executed frozen primary path and its post-control evidence."""

    scenario: ResidentialCampaignCScenario
    strategy: str
    trajectory: (
        MultiOpportunityExplainableMPCDailySimulationResult
        | EconomicMultiOpportunityExplainableMPCDailySimulationResult
    )
    ledger: DailyEconomicLedger
    kpi: ResidentialAcceptanceKPI
    acceptance: ResidentialAcceptanceResult


@dataclass(frozen=True, slots=True)
class AnchorRegretEvidence:
    """Compare one authoritative executed path with its same-environment anchor."""

    path: ResidentialCampaignCPathResult
    perfect_anchor_scenario_id: str
    adjusted_cost_regret: float
    grid_import_delta_kwh: float
    grid_export_delta_kwh: float
    battery_throughput_delta_kwh: float
    final_soc_delta: float
    physical_revision_count_delta: int
    headroom_limit_count_delta: int
    actual_executed_battery_power_divergence_count: int
    maximum_absolute_actual_executed_battery_power_difference_kw: float


@dataclass(frozen=True, slots=True)
class ResidentialCampaignCScenarioResult:
    scenario: ResidentialCampaignCScenario
    forecast_error: ForecastErrorEvidence
    schedule: ResidentialCampaignCPathResult
    economic: ResidentialCampaignCPathResult
    comparison: EconomicComparisonExplanation


@dataclass(frozen=True, slots=True)
class ResidentialCampaignCResult:
    scenarios: tuple[ResidentialCampaignCScenario, ...]
    scenario_results: tuple[ResidentialCampaignCScenarioResult, ...]
    anchor_regrets: tuple[AnchorRegretEvidence, ...]
    hard_passed: bool
    perfect_anchor_reproduced: bool
    output_paths: tuple[Path, ...]


def campaign_c_scenarios() -> tuple[ResidentialCampaignCScenario, ...]:
    """Return exactly three realized environments times thirteen forecast cases."""

    sources = {item.scenario_id: item for item in campaign_scenarios()}
    scenarios: list[ResidentialCampaignCScenario] = []
    for environment, source_id in _ENVIRONMENT_SOURCES:
        source = sources[source_id]
        for case_id, pv, load, tariff, metadata in _forecast_cases(source):
            scenario_id = f"C_{environment}_{case_id}"
            scenarios.append(
                ResidentialCampaignCScenario(
                    scenario_id,
                    environment,
                    case_id,
                    f"Campaign C {environment} with {case_id} caller-supplied forecast facts.",
                    source.pv_profile_kw,
                    pv,
                    source.load_profile_kw,
                    load,
                    source.import_tariff_profile_per_kwh,
                    tariff,
                    source.export_tariff_per_kwh,
                    source.initial_soc_fraction,
                    source.battery_model,
                    source.candidate_configuration,
                    source.degradation_cost_per_throughput_kwh,
                    source.terminal_valuation_per_kwh,
                    source.export_policy,
                    "caller_supplied_forecast_may_differ_from_realized_execution_facts",
                    source_id,
                    f"C_{environment}_PERFECT",
                    metadata,
                )
            )
    result = tuple(scenarios)
    counts = Counter(item.environment for item in result)
    if (
        len(result) != 39
        or len({item.scenario_id for item in result}) != 39
        or set(counts.values()) != {13}
    ):
        raise AssertionError(
            "Campaign C must contain exactly 3 environments x 13 cases"
        )
    return result


def run_residential_campaign_c(output_directory: Path) -> ResidentialCampaignCResult:
    """Freshly execute all 78 paths; no Campaign C trajectory is reused."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    evaluator = DeterministicResidentialAcceptanceEvaluator()
    scenarios = campaign_c_scenarios()
    results = tuple(
        _run_scenario(scenario, output_directory / scenario.scenario_id, evaluator)
        for scenario in scenarios
    )
    paths = _paths(results)
    if len(paths) != 78 or len({id(path.trajectory) for path in paths}) != 78:
        raise AssertionError("Campaign C must freshly execute exactly 78 unique paths")
    regrets = _anchor_regrets(results)
    hard_passed = _hard_passed(paths)
    perfect_anchor_reproduced = _perfect_anchor_reproduced(results)
    output_paths = _write_outputs(
        output_directory,
        scenarios,
        results,
        regrets,
        hard_passed,
        perfect_anchor_reproduced,
    )
    return ResidentialCampaignCResult(
        scenarios,
        results,
        regrets,
        hard_passed,
        perfect_anchor_reproduced,
        output_paths,
    )


def _forecast_cases(
    source: ResidentialCampaignScenario,
) -> tuple[
    tuple[str, tuple[float, ...], tuple[float, ...], tuple[float, ...], str], ...
]:
    pv, load, tariff = (
        source.pv_profile_kw,
        source.load_profile_kw,
        source.import_tariff_profile_per_kwh,
    )
    return (
        ("PERFECT", pv, load, tariff, "forecast equals realized facts exactly"),
        (
            "PV_OVER_25",
            _scale(pv, 1.25),
            load,
            tariff,
            "forecast PV = realized PV * 1.25",
        ),
        (
            "PV_UNDER_25",
            _scale(pv, 0.75),
            load,
            tariff,
            "forecast PV = realized PV * 0.75",
        ),
        (
            "LOAD_OVER_25",
            pv,
            _scale(load, 1.25),
            tariff,
            "forecast load = realized load * 1.25",
        ),
        (
            "LOAD_UNDER_25",
            pv,
            _scale(load, 0.75),
            tariff,
            "forecast load = realized load * 0.75",
        ),
        (
            "PV_EARLY_2H",
            _shift_earlier(pv, 2),
            load,
            tariff,
            "24-hour circular timing displacement: PV earlier by 2h",
        ),
        (
            "PV_LATE_2H",
            _shift_later(pv, 2),
            load,
            tariff,
            "24-hour circular timing displacement: PV later by 2h",
        ),
        (
            "LOAD_EARLY_2H",
            pv,
            _shift_earlier(load, 2),
            tariff,
            "24-hour circular timing displacement: load earlier by 2h",
        ),
        (
            "LOAD_LATE_2H",
            pv,
            _shift_later(load, 2),
            tariff,
            "24-hour circular timing displacement: load later by 2h",
        ),
        (
            "TARIFF_EARLY_2H",
            pv,
            load,
            _shift_earlier(tariff, 2),
            "24-hour circular timing displacement: tariff earlier by 2h",
        ),
        (
            "TARIFF_LATE_2H",
            pv,
            load,
            _shift_later(tariff, 2),
            "24-hour circular timing displacement: tariff later by 2h",
        ),
        (
            "OPTIMISTIC_COMBINED",
            _scale(pv, 1.25),
            _scale(load, 0.75),
            tariff,
            "forecast PV * 1.25 and load * 0.75",
        ),
        (
            "PESSIMISTIC_COMBINED",
            _scale(pv, 0.75),
            _scale(load, 1.25),
            tariff,
            "forecast PV * 0.75 and load * 1.25",
        ),
    )


def _scale(values: tuple[float, ...], factor: float) -> tuple[float, ...]:
    return tuple(value * factor for value in values)


def _shift_earlier(values: tuple[float, ...], hours: int) -> tuple[float, ...]:
    """Move a value at t+hours to t; circularly preserve all 24 values."""
    return values[hours:] + values[:hours]


def _shift_later(values: tuple[float, ...], hours: int) -> tuple[float, ...]:
    """Move a value at t-hours to t; circularly preserve all 24 values."""
    return values[-hours:] + values[:-hours]


def _run_scenario(
    scenario: ResidentialCampaignCScenario,
    output_directory: Path,
    evaluator: DeterministicResidentialAcceptanceEvaluator,
) -> ResidentialCampaignCScenarioResult:
    output_directory.mkdir(parents=True, exist_ok=True)
    execution = _execution_scenario(scenario)
    schedule_input, economic_input = _inputs(scenario, output_directory)
    schedule_trajectory = _schedule_runner(scenario.candidate_configuration).run(
        schedule_input
    )
    economic_trajectory = _economic_runner(scenario.candidate_configuration).run(
        economic_input
    )
    schedule_ledger = _ledger(schedule_trajectory, execution)
    economic_ledger = _ledger(economic_trajectory, execution)
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
    acceptance_scenario = ResidentialAcceptanceScenario(
        scenario.scenario_id,
        scenario.scenario_id,
        scenario.export_policy,
        scenario.description,
    )
    schedule_kpi = replace(
        _kpi(execution, "Schedule", schedule_trajectory, schedule_ledger, reconciled),
        scenario_id=scenario.scenario_id,
    )
    economic_kpi = replace(
        _kpi(execution, "Economic", economic_trajectory, economic_ledger, reconciled),
        scenario_id=scenario.scenario_id,
    )
    schedule = ResidentialCampaignCPathResult(
        scenario,
        "Schedule",
        schedule_trajectory,
        schedule_ledger,
        schedule_kpi,
        evaluator.evaluate(acceptance_scenario, schedule_kpi),
    )
    economic = ResidentialCampaignCPathResult(
        scenario,
        "Economic",
        economic_trajectory,
        economic_ledger,
        economic_kpi,
        evaluator.evaluate(acceptance_scenario, economic_kpi),
    )
    return ResidentialCampaignCScenarioResult(
        scenario, _error_evidence(scenario), schedule, economic, comparison
    )


def _execution_scenario(
    scenario: ResidentialCampaignCScenario,
) -> ResidentialCampaignScenario:
    return ResidentialCampaignScenario(
        scenario.scenario_id,
        scenario.description,
        scenario.realized_load_profile_kw,
        scenario.realized_pv_profile_kw,
        scenario.realized_tariff_profile_cny_per_kwh,
        scenario.export_tariff_per_kwh,
        scenario.initial_soc_fraction,
        scenario.battery_model,
        scenario.candidate_configuration,
        scenario.degradation_cost_per_throughput_kwh,
        scenario.terminal_valuation_per_kwh,
        scenario.export_policy,
        scenario.forecast_semantics,
    )


def _inputs(
    scenario: ResidentialCampaignCScenario, output_directory: Path
) -> tuple[
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationInput,
]:
    template = create_demo_input(output_directory)
    model = scenario.battery_model
    daily = DailySimulationScenarioInput(
        template.integration_input.daily_input.step_identities,
        scenario.realized_pv_profile_kw,
        scenario.realized_load_profile_kw,
        scenario.realized_tariff_profile_cny_per_kwh,
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
    horizons = _forecast_horizons(
        daily,
        scenario,
        template.mpc_configuration.forecast_horizon_points,
    )
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


def _forecast_horizons(
    daily: DailySimulationScenarioInput,
    scenario: ResidentialCampaignCScenario,
    point_count: int,
) -> tuple[ForecastHorizon, ...]:
    horizons: list[ForecastHorizon] = []
    for hour, identity in enumerate(daily.step_identities):
        timestamp = identity.timestamp
        if timestamp is None:
            raise ValueError("Campaign C requires explicit step timestamps")
        points = tuple(
            _forecast_point(
                scenario, hour + offset, timestamp + timedelta(hours=offset)
            )
            for offset in range(point_count)
        )
        horizons.append(ForecastHorizon(points))
    return tuple(horizons)


def _forecast_point(
    scenario: ResidentialCampaignCScenario, index: int, timestamp: datetime
) -> ForecastPoint:
    if index < HOURS_PER_DAY:
        return ForecastPoint(
            timestamp,
            scenario.forecast_pv_profile_kw[index],
            scenario.forecast_load_profile_kw[index],
            scenario.forecast_tariff_profile_cny_per_kwh[index],
        )
    return ForecastPoint(timestamp, 0.0, 0.0, _FORECAST_FALLBACK_TARIFF)


def _error_evidence(scenario: ResidentialCampaignCScenario) -> ForecastErrorEvidence:
    pv = _curve_error(scenario.forecast_pv_profile_kw, scenario.realized_pv_profile_kw)
    load = _curve_error(
        scenario.forecast_load_profile_kw, scenario.realized_load_profile_kw
    )
    tariff = _curve_error(
        scenario.forecast_tariff_profile_cny_per_kwh,
        scenario.realized_tariff_profile_cny_per_kwh,
    )
    return ForecastErrorEvidence(
        scenario, *pv, *load, tariff[0] / HOURS_PER_DAY, tariff[1], tariff[2]
    )


def _curve_error(
    forecast: tuple[float, ...], realized: tuple[float, ...]
) -> tuple[float, float, float]:
    errors = tuple(left - right for left, right in zip(forecast, realized, strict=True))
    return (
        sum(errors),
        sum(abs(value) for value in errors) / HOURS_PER_DAY,
        max(abs(value) for value in errors),
    )


def _paths(
    results: Iterable[ResidentialCampaignCScenarioResult],
) -> tuple[ResidentialCampaignCPathResult, ...]:
    return tuple(
        path for result in results for path in (result.schedule, result.economic)
    )


def _anchor_regrets(
    results: tuple[ResidentialCampaignCScenarioResult, ...],
) -> tuple[AnchorRegretEvidence, ...]:
    anchors = {
        (result.scenario.environment, path.strategy): path
        for result in results
        if result.scenario.forecast_error_case_id == "PERFECT"
        for path in (result.schedule, result.economic)
    }
    if len(anchors) != 6:
        raise AssertionError(
            "Campaign C requires one perfect anchor per environment/strategy"
        )
    evidence: list[AnchorRegretEvidence] = []
    for path in _paths(results):
        anchor = anchors[(path.scenario.environment, path.strategy)]
        actual = _actual_powers(path)
        anchor_actual = _actual_powers(anchor)
        differences = tuple(
            abs(left - right) for left, right in zip(actual, anchor_actual, strict=True)
        )
        evidence.append(
            AnchorRegretEvidence(
                path,
                anchor.scenario.scenario_id,
                path.kpi.adjusted_net_economic_cost
                - anchor.kpi.adjusted_net_economic_cost,
                path.kpi.grid_import_energy_kwh - anchor.kpi.grid_import_energy_kwh,
                path.kpi.grid_export_energy_kwh - anchor.kpi.grid_export_energy_kwh,
                path.kpi.battery_throughput_kwh - anchor.kpi.battery_throughput_kwh,
                path.kpi.final_soc_fraction - anchor.kpi.final_soc_fraction,
                path.kpi.physical_revision_count - anchor.kpi.physical_revision_count,
                path.kpi.headroom_limit_count - anchor.kpi.headroom_limit_count,
                sum(value > NUMERIC_TOLERANCE for value in differences),
                max(differences),
            )
        )
    return tuple(evidence)


def _actual_powers(path: ResidentialCampaignCPathResult) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.battery_result.actual_power_kw
        for trace in path.trajectory.step_traces
    )


def _hard_passed(paths: Iterable[ResidentialCampaignCPathResult]) -> bool:
    return not any(
        finding.status.value == "fail"
        and finding.severity
        in {ResidentialAcceptanceSeverity.BLOCKER, ResidentialAcceptanceSeverity.MAJOR}
        for path in paths
        for finding in path.acceptance.findings
    )


def _perfect_anchor_reproduced(
    results: tuple[ResidentialCampaignCScenarioResult, ...],
) -> bool:
    """Verify each fresh perfect C path against its frozen Campaign A evidence."""
    perfect_results = tuple(
        result
        for result in results
        if result.scenario.forecast_error_case_id == "PERFECT"
    )
    observed = {
        (path.scenario.scenario_id, path.strategy)
        for result in perfect_results
        for path in (result.schedule, result.economic)
    }
    if observed != set(_PERFECT_ANCHOR_FINGERPRINTS):
        return False
    return all(
        result.forecast_error.pv_maximum_absolute_error_kw == 0.0
        and result.forecast_error.load_maximum_absolute_error_kw == 0.0
        and result.forecast_error.tariff_maximum_absolute_error_cny_per_kwh == 0.0
        and result.comparison.ranking is EconomicComparisonRanking.TIED
        and all(
            path.acceptance.passed
            and path.kpi.ledger_reconciled
            and path.kpi.comparison_reconciled
            and _matches_perfect_anchor_fingerprint(path)
            for path in (result.schedule, result.economic)
        )
        for result in perfect_results
    )


def _matches_perfect_anchor_fingerprint(path: ResidentialCampaignCPathResult) -> bool:
    expected = _PERFECT_ANCHOR_FINGERPRINTS[(path.scenario.scenario_id, path.strategy)]
    observed = (
        path.kpi.grid_import_energy_kwh,
        path.kpi.grid_export_energy_kwh,
        path.kpi.battery_throughput_kwh,
        path.kpi.final_soc_fraction,
        float(path.kpi.physical_revision_count),
        float(path.kpi.headroom_limit_count),
        path.ledger.total_realized_import_cost,
        path.ledger.total_realized_export_revenue,
        path.ledger.total_battery_degradation_cost,
        path.ledger.terminal_energy_value,
        path.ledger.adjusted_net_economic_cost,
    )
    return all(
        isclose(value, reference, abs_tol=1e-6)
        for value, reference in zip(observed, expected, strict=True)
    )


def _write_outputs(
    output_directory: Path,
    scenarios: tuple[ResidentialCampaignCScenario, ...],
    results: tuple[ResidentialCampaignCScenarioResult, ...],
    regrets: tuple[AnchorRegretEvidence, ...],
    hard_passed: bool,
    anchors_reproduced: bool,
) -> tuple[Path, ...]:
    contents = {
        "campaign_c_scenarios.csv": _scenarios_csv(scenarios),
        "campaign_c_results.csv": _results_csv(_paths(results)),
        "campaign_c_forecast_errors.csv": _errors_csv(results),
        "campaign_c_anchor_regret.csv": _regrets_csv(regrets),
        "campaign_c_comparisons.csv": _comparisons_csv(results),
        "campaign_c_findings.csv": _findings_csv(_paths(results)),
        "campaign_c_summary.txt": _summary(
            results, regrets, hard_passed, anchors_reproduced
        ),
    }
    output_paths: list[Path] = []
    for name, content in contents.items():
        path = output_directory / name
        path.write_text(content, encoding="utf-8", newline="")
        output_paths.append(path)
    charts = (
        (
            "forecast_pv_mae_kw.svg",
            "Forecast PV MAE",
            "kW",
            tuple(
                (
                    _label(result.scenario),
                    result.forecast_error.pv_mean_absolute_error_kw,
                )
                for result in results
            ),
            "PV forecast MAE",
            "#2563eb",
        ),
        (
            "adjusted_cost_regret_cny.svg",
            "Adjusted-cost regret",
            "CNY",
            tuple(
                (
                    _label(item.path.scenario, item.path.strategy),
                    item.adjusted_cost_regret,
                )
                for item in regrets
            ),
            "imperfect minus perfect",
            "#059669",
        ),
        (
            "executed_battery_power_divergence.svg",
            "Actual executed battery-power divergence",
            "kW",
            tuple(
                (
                    _label(item.path.scenario, item.path.strategy),
                    item.maximum_absolute_actual_executed_battery_power_difference_kw,
                )
                for item in regrets
            ),
            "max actual-power difference",
            "#7c3aed",
        ),
        (
            "final_soc_delta.svg",
            "Final actual SOC delta",
            "fraction",
            tuple(
                (_label(item.path.scenario, item.path.strategy), item.final_soc_delta)
                for item in regrets
            ),
            "imperfect minus perfect",
            "#0891b2",
        ),
        (
            "physical_revision_delta.svg",
            "Physical revision-count delta",
            "count",
            tuple(
                (
                    _label(item.path.scenario, item.path.strategy),
                    float(item.physical_revision_count_delta),
                )
                for item in regrets
            ),
            "imperfect minus perfect",
            "#d97706",
        ),
        (
            "schedule_economic_adjusted_cost_delta_cny.svg",
            "Economic minus Schedule adjusted cost",
            "CNY",
            tuple(
                (_label(item.scenario), item.comparison.delta_adjusted_cost)
                for item in results
            ),
            "Economic minus Schedule",
            "#dc2626",
        ),
    )
    for name, title, unit, points, legend, color in charts:
        path = output_directory / name
        path.write_text(
            _svg_bar_chart(title, unit, points, legend, color),
            encoding="utf-8",
            newline="",
        )
        output_paths.append(path)
    return tuple(output_paths)


def _label(scenario: ResidentialCampaignCScenario, strategy: str = "") -> str:
    suffix = f" | {strategy}" if strategy else ""
    return f"{scenario.scenario_id} | {scenario.environment} | {scenario.forecast_error_case_id}{suffix}"


def _scenarios_csv(scenarios: Iterable[ResidentialCampaignCScenario]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "environment",
            "forecast_error_case_id",
            "realized_source_scenario_id",
            "perfect_anchor_id",
            "transformation_metadata",
            "realized_pv_profile_kw",
            "forecast_pv_profile_kw",
            "realized_load_profile_kw",
            "forecast_load_profile_kw",
            "realized_tariff_profile_cny_per_kwh",
            "forecast_tariff_profile_cny_per_kwh",
            "forecast_semantics",
        )
    )
    for item in scenarios:
        writer.writerow(
            (
                item.scenario_id,
                item.environment,
                item.forecast_error_case_id,
                item.realized_source_scenario_id,
                item.perfect_anchor_id,
                item.transformation_metadata,
                _profile(item.realized_pv_profile_kw),
                _profile(item.forecast_pv_profile_kw),
                _profile(item.realized_load_profile_kw),
                _profile(item.forecast_load_profile_kw),
                _profile(item.realized_tariff_profile_cny_per_kwh),
                _profile(item.forecast_tariff_profile_cny_per_kwh),
                item.forecast_semantics,
            )
        )
    return stream.getvalue()


def _results_csv(paths: Iterable[ResidentialCampaignCPathResult]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "environment",
            "forecast_error_case_id",
            "strategy",
            "grid_import_kwh",
            "grid_export_kwh",
            "battery_throughput_kwh",
            "final_actual_soc",
            "physical_revision_count",
            "headroom_limit_count",
            "realized_import_cost",
            "export_revenue",
            "degradation_cost",
            "terminal_value",
            "adjusted_net_economic_cost",
            "acceptance_status",
        )
    )
    for path in paths:
        kpi = path.kpi
        writer.writerow(
            (
                path.scenario.scenario_id,
                path.scenario.environment,
                path.scenario.forecast_error_case_id,
                path.strategy,
                *(
                    _number(value)
                    for value in (
                        kpi.grid_import_energy_kwh,
                        kpi.grid_export_energy_kwh,
                        kpi.battery_throughput_kwh,
                        kpi.final_soc_fraction,
                    )
                ),
                kpi.physical_revision_count,
                kpi.headroom_limit_count,
                *(
                    _number(value)
                    for value in (
                        kpi.import_cost,
                        kpi.export_revenue,
                        kpi.degradation_cost,
                        kpi.terminal_value,
                        kpi.adjusted_net_economic_cost,
                    )
                ),
                "pass" if path.acceptance.passed else "fail",
            )
        )
    return stream.getvalue()


def _errors_csv(results: Iterable[ResidentialCampaignCScenarioResult]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "environment",
            "forecast_error_case_id",
            "pv_signed_daily_energy_bias_kwh",
            "pv_mae_kw",
            "pv_max_abs_kw",
            "load_signed_daily_energy_bias_kwh",
            "load_mae_kw",
            "load_max_abs_kw",
            "tariff_signed_mean_bias_cny_per_kwh",
            "tariff_mae_cny_per_kwh",
            "tariff_max_abs_cny_per_kwh",
        )
    )
    for result in results:
        item = result.forecast_error
        writer.writerow(
            (
                result.scenario.scenario_id,
                result.scenario.environment,
                result.scenario.forecast_error_case_id,
                *(
                    _number(value)
                    for value in (
                        item.pv_signed_daily_energy_bias_kwh,
                        item.pv_mean_absolute_error_kw,
                        item.pv_maximum_absolute_error_kw,
                        item.load_signed_daily_energy_bias_kwh,
                        item.load_mean_absolute_error_kw,
                        item.load_maximum_absolute_error_kw,
                        item.tariff_signed_mean_bias_cny_per_kwh,
                        item.tariff_mean_absolute_error_cny_per_kwh,
                        item.tariff_maximum_absolute_error_cny_per_kwh,
                    )
                ),
            )
        )
    return stream.getvalue()


def _regrets_csv(regrets: Iterable[AnchorRegretEvidence]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "environment",
            "forecast_error_case_id",
            "strategy",
            "perfect_anchor_scenario_id",
            "adjusted_cost_regret",
            "grid_import_delta_kwh",
            "grid_export_delta_kwh",
            "battery_throughput_delta_kwh",
            "final_soc_delta",
            "physical_revision_count_delta",
            "headroom_limit_count_delta",
            "actual_executed_battery_power_divergence_count",
            "max_abs_actual_executed_battery_power_difference_kw",
        )
    )
    for item in regrets:
        path = item.path
        writer.writerow(
            (
                path.scenario.scenario_id,
                path.scenario.environment,
                path.scenario.forecast_error_case_id,
                path.strategy,
                item.perfect_anchor_scenario_id,
                *(
                    _number(value)
                    for value in (
                        item.adjusted_cost_regret,
                        item.grid_import_delta_kwh,
                        item.grid_export_delta_kwh,
                        item.battery_throughput_delta_kwh,
                        item.final_soc_delta,
                    )
                ),
                item.physical_revision_count_delta,
                item.headroom_limit_count_delta,
                item.actual_executed_battery_power_divergence_count,
                _number(
                    item.maximum_absolute_actual_executed_battery_power_difference_kw
                ),
            )
        )
    return stream.getvalue()


def _comparisons_csv(results: Iterable[ResidentialCampaignCScenarioResult]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "environment",
            "forecast_error_case_id",
            "ranking",
            "schedule_adjusted_cost",
            "economic_adjusted_cost",
            "economic_minus_schedule_adjusted_cost",
            "import_cost_contribution",
            "export_revenue_contribution",
            "degradation_cost_contribution",
            "terminal_value_contribution",
            "dominant_components",
            "reconciled",
        )
    )
    for result in results:
        value = result.comparison
        writer.writerow(
            (
                result.scenario.scenario_id,
                result.scenario.environment,
                result.scenario.forecast_error_case_id,
                value.ranking.value,
                _number(value.reference_adjusted_net_economic_cost),
                _number(value.candidate_adjusted_net_economic_cost),
                _number(value.delta_adjusted_cost),
                _number(value.import_cost_contribution),
                _number(value.export_revenue_contribution),
                _number(value.degradation_cost_contribution),
                _number(value.terminal_value_contribution),
                "|".join(component.value for component in value.dominant_components),
                str(result.schedule.kpi.comparison_reconciled).lower(),
            )
        )
    return stream.getvalue()


def _findings_csv(paths: Iterable[ResidentialCampaignCPathResult]) -> str:
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
    results: tuple[ResidentialCampaignCScenarioResult, ...],
    regrets: tuple[AnchorRegretEvidence, ...],
    hard_passed: bool,
    anchors_reproduced: bool,
) -> str:
    paths = _paths(results)
    failures = Counter(
        finding.severity
        for path in paths
        for finding in path.acceptance.findings
        if finding.status.value == "fail"
    )
    rankings = Counter(item.comparison.ranking for item in results)
    highest_divergence = max(
        regrets, key=lambda item: item.actual_executed_battery_power_divergence_count
    )
    highest_revision = max(paths, key=lambda item: item.kpi.physical_revision_count)
    positive = max(regrets, key=lambda item: item.adjusted_cost_regret)
    negative = min(regrets, key=lambda item: item.adjusted_cost_regret)
    shortlist = _shortlist(results, regrets)
    return "\n".join(
        (
            "EOS Residential EMS 1.0 Campaign C - Deterministic Forecast Error and Robustness Characterization",
            "functional_freeze=validation/reporting tooling only; no control capability changed.",
            "forecast_vs_realized=forecast horizons drive planning; realized DailySimulationScenarioInput drives authoritative Simulator execution and feedback.",
            "matrix=3 environments x 13 explicit forecast cases = 39 scenarios; logical_paths=78; actual_control_executions=78; no accounting-only reuse.",
            f"campaign_hard_status={'PASS' if hard_passed else 'FAIL'}",
            f"perfect_anchor_reproduction={'PASS' if anchors_reproduced else 'FAIL'}",
            f"blocker_count={failures[ResidentialAcceptanceSeverity.BLOCKER]} major_count={failures[ResidentialAcceptanceSeverity.MAJOR]} minor_count={failures[ResidentialAcceptanceSeverity.MINOR]} informational_count={failures[ResidentialAcceptanceSeverity.INFORMATIONAL]}",
            f"economic_wins={rankings[EconomicComparisonRanking.CANDIDATE_BETTER]} schedule_wins={rankings[EconomicComparisonRanking.REFERENCE_BETTER]} ties={rankings[EconomicComparisonRanking.TIED]}",
            f"largest_positive_adjusted_cost_regret={positive.path.scenario.scenario_id}/{positive.path.strategy}:{_number(positive.adjusted_cost_regret)}",
            f"largest_negative_adjusted_cost_regret={negative.path.scenario.scenario_id}/{negative.path.strategy}:{_number(negative.adjusted_cost_regret)}",
            f"highest_actual_power_divergence={highest_divergence.path.scenario.scenario_id}/{highest_divergence.path.strategy}:count={highest_divergence.actual_executed_battery_power_divergence_count};max_kw={_number(highest_divergence.maximum_absolute_actual_executed_battery_power_difference_kw)}",
            f"highest_physical_revisions={highest_revision.scenario.scenario_id}/{highest_revision.strategy}:{highest_revision.kpi.physical_revision_count}",
            "interpretation=deterministic characterization only; not stochastic probability, hardware robustness, PCS certification, field/customer readiness, controller tuning, or proof of optimality.",
            "human_review_shortlist=" + ("; ".join(shortlist) if shortlist else "none"),
            "future_handoff=any probabilistic or multi-day campaign requires separately approved scope.",
            "",
        )
    )


def _shortlist(
    results: tuple[ResidentialCampaignCScenarioResult, ...],
    regrets: tuple[AnchorRegretEvidence, ...],
) -> tuple[str, ...]:
    selected: dict[str, set[str]] = defaultdict(set)
    for item, reason in (
        (
            max(regrets, key=lambda value: value.adjusted_cost_regret),
            "largest_positive_regret",
        ),
        (
            min(regrets, key=lambda value: value.adjusted_cost_regret),
            "largest_negative_regret",
        ),
        (
            max(
                regrets,
                key=lambda value: value.actual_executed_battery_power_divergence_count,
            ),
            "highest_actual_power_divergence",
        ),
    ):
        selected[item.path.scenario.scenario_id].add(reason)
    for result in results:
        if result.comparison.ranking is not EconomicComparisonRanking.TIED:
            selected[result.scenario.scenario_id].add(
                f"ranking_{result.comparison.ranking.value}"
            )
    for path in _paths(results):
        model = path.scenario.battery_model
        if path.kpi.final_soc_fraction in {
            model.min_soc_fraction,
            model.max_soc_fraction,
        }:
            selected[path.scenario.scenario_id].add("final_soc_boundary")
    return tuple(
        f"{key}: {','.join(sorted(value))}" for key, value in sorted(selected.items())
    )


def _profile(values: tuple[float, ...]) -> str:
    return "|".join(_number(value) for value in values)


def _number(value: float) -> str:
    return f"{value:.6f}"


def _svg_bar_chart(
    title: str,
    unit: str,
    points: tuple[tuple[str, float], ...],
    legend: str,
    color: str,
) -> str:
    visible = points or (("no data", 0.0),)
    values = tuple(value for _, value in visible)
    maximum, minimum = max(1.0, *values), min(0.0, *values)
    scale = max(maximum - minimum, 1.0)
    baseline = 250 - (0.0 - minimum) / scale * 190
    width = min(18.0, 900.0 / len(visible))
    bars = "".join(
        f'<rect data-label="{escape(label, {'"': "&quot;"})}" x="{55 + index * width:.2f}" y="{min(baseline, 250 - (value - minimum) / scale * 190):.2f}" width="{max(width - 2, 1):.2f}" height="{abs(baseline - (250 - (value - minimum) / scale * 190)):.2f}" fill="{color}"/>'
        for index, (label, value) in enumerate(visible)
    )
    labels = "".join(
        f'<text x="{55 + index * width + width / 2:.2f}" y="280" font-family="sans-serif" font-size="6" text-anchor="end" transform="rotate(-55 {55 + index * width + width / 2:.2f} 280)">{escape(label)}</text>'
        for index, (label, _) in enumerate(visible)
    )
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="420" viewBox="0 0 1024 420"><rect width="100%" height="100%" fill="white"/><text x="40" y="28" font-family="sans-serif" font-size="16">{escape(title)} ({escape(unit)})</text><line id="zero-axis" x1="40" y1="{baseline:.2f}" x2="990" y2="{baseline:.2f}" stroke="#64748b"/>{bars}{labels}<rect x="40" y="360" width="12" height="12" fill="{color}"/><text x="58" y="370" font-family="sans-serif" font-size="11">{escape(legend)}; unit={escape(unit)}</text></svg>\n'


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS Residential EMS deterministic Campaign C"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("simulation_output_campaign_c")
    )
    arguments = parser.parse_args(argv)
    result = run_residential_campaign_c(arguments.output_dir)
    for path in result.output_paths:
        print(path)
    print("PASS" if result.hard_passed else "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
