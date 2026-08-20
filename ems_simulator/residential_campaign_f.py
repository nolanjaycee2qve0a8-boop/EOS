"""Campaign F: correlated and tail multi-day residential robustness evidence.

This post-freeze module is deliberately an orchestration and evidence layer.
It creates caller-owned forecast facts, supplies them to the frozen daily
runner, and aggregates only completed Simulator and ledger evidence.
"""

# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from statistics import fmean, pstdev
from xml.etree import ElementTree
from xml.sax.saxutils import escape

from ems_simulator.economic_comparison_explanation import (
    DeterministicEconomicComparisonExplainer,
    EconomicComparisonExplanation,
    EconomicComparisonInput,
)
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner,
    _schedule_runner,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
    MultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.multi_opportunity_headroom_demo import (
    _GAP_TOLERANCE_POINTS,
    create_demo_input,
)
from ems_simulator.residential_acceptance import (
    NUMERIC_TOLERANCE,
    DeterministicResidentialAcceptanceEvaluator,
    ResidentialAcceptanceSeverity,
    ResidentialAcceptanceStatus,
)
from ems_simulator.residential_campaign_a import _ledger
from ems_simulator.residential_campaign_d import (
    ResidentialCampaignDCase,
    ResidentialCampaignDDayPathResult,
    ResidentialCampaignDPathSummary,
    ResidentialCampaignDScenarioDay,
    _aggregate_reconciled,
    _daily_comparison,
    _day_path,
    _path_summary,
    campaign_d_cases,
    campaign_d_scenario_days,
)
from forecast import ForecastHorizon, ForecastPoint
from optimization import PVOpportunityWindowConfiguration
from simulator import SimulationStepIdentity

_SEED = 20260818
_DAYS = 7
_HOURS = 24
_CORE_PER_REGIME = 16
_TAIL_PER_REGIME = 4
_CORE_RHO = 0.70
_TIMING_RHO = 0.65
_FORECAST_FALLBACK_TARIFF = 0.50
_SCALES = (0.18, 0.15, 0.12)
_LOWER = (-0.40, -0.35, -0.30)
_UPPER = (0.40, 0.35, 0.30)
_CORRELATION = ((1.0, -0.45, 0.35), (-0.45, 1.0, -0.25), (0.35, -0.25, 1.0))
_CHOLESKY = (
    (1.0, 0.0, 0.0),
    (-0.45, 0.8930285549745876, 0.0),
    (0.35, -0.10358011452683305, 0.9310054564150567),
)
_REGIME_CASE_IDS = (
    ("REFERENCE", "D01_7D_REFERENCE_REPEAT"),
    ("HIGH_PV", "D03_7D_HIGH_PV_REPEAT"),
    ("HIGH_EVENING_LOAD", "D02_7D_EVENING_REPEAT"),
)
_ANCHOR_SIGNATURE_TOLERANCE = 1e-6
# Reporting-only argmax membership tolerance. It never affects sampling,
# control, accounting, regret or comparison calculations.
_MAXIMUM_FLOAT_TIE_ABSOLUTE_TOLERANCE = NUMERIC_TOLERANCE
_MAXIMUM_FLOAT_TIE_RELATIVE_TOLERANCE = 0.0
# Frozen Campaign-D seven-day evidence, independently recorded from D01/D03/D02.
# Order: source case, import, export, degradation, final SOC, terminal value,
# adjusted cost, total physical revisions.
_D_ANCHOR_SIGNATURES = {
    "REFERENCE": (
        "D01_7D_REFERENCE_REPEAT",
        110.804432,
        18.614958,
        5.449474,
        0.200000,
        0.000000,
        41.737368,
        35,
    ),
    "HIGH_PV": (
        "D03_7D_HIGH_PV_REPEAT",
        82.250000,
        40.110526,
        5.449474,
        0.200000,
        0.000000,
        30.992368,
        36,
    ),
    "HIGH_EVENING_LOAD": (
        "D02_7D_EVENING_REPEAT",
        161.204432,
        18.614958,
        5.449474,
        0.200000,
        0.000000,
        87.097368,
        56,
    ),
}
_STRATEGIES = ("Schedule", "Economic")
_NESTED_MPC_DECISION_HEADER = (
    "timestamp",
    "strategy_name",
    "strategy_version",
    "candidate_action",
    "candidate_requested_power_kw",
    "final_action",
    "final_requested_power_kw",
    "revision_applied",
    "revision_reasons",
    "candidate_soc_violation_kinds",
    "candidate_power_violation_kinds",
    "candidate_battery_horizon_feasible",
    "final_soc_feasible",
    "final_power_feasible",
    "final_battery_horizon_feasible",
    "candidate_starting_soc_fraction",
    "candidate_ending_soc_fraction",
    "final_starting_soc_fraction",
    "final_ending_soc_fraction",
    "min_soc_fraction",
    "max_soc_fraction",
    "max_charge_power_kw",
    "max_discharge_power_kw",
    "formatted_text",
)
_NESTED_ACTION_VALUES = frozenset({"charge", "discharge", "idle"})
_NESTED_REQUIRED_TEXT_COLUMNS = frozenset(
    {
        "timestamp",
        "strategy_name",
        "strategy_version",
        "candidate_action",
        "final_action",
        "formatted_text",
    }
)
_NESTED_BOOLEAN_COLUMNS = frozenset(
    {
        "revision_applied",
        "candidate_battery_horizon_feasible",
        "final_soc_feasible",
        "final_power_feasible",
        "final_battery_horizon_feasible",
    }
)
_NESTED_NUMERIC_COLUMNS = frozenset(
    {
        "candidate_requested_power_kw",
        "final_requested_power_kw",
        "candidate_starting_soc_fraction",
        "candidate_ending_soc_fraction",
        "final_starting_soc_fraction",
        "final_ending_soc_fraction",
        "min_soc_fraction",
        "max_soc_fraction",
        "max_charge_power_kw",
        "max_discharge_power_kw",
    }
)
_SUMMARY_TITLE = "Campaign F: correlated and tail multi-day residential robustness"
_SUMMARY_KEYS = (
    "campaign_id",
    "summary_schema_version",
    "seed",
    "regimes",
    "core_scenarios",
    "tail_scenarios",
    "total_scenarios",
    "sampled_tail_paths",
    "perfect_anchor_paths",
    "total_paths",
    "sampled_tail_daily_executions",
    "anchor_daily_executions",
    "total_daily_executions",
    "schedule_daily_executions",
    "economic_daily_executions",
    "scenario_days",
    "sampled_tail_hours",
    "anchor_hours",
    "total_hours",
    "soc_boundaries",
    "continuity_failures",
    "clip_evidence",
    "regret_evidence",
    "strategy_comparisons",
    "maximum_adjusted_cost_regret",
    "maximum_adjusted_cost_regret_reference_count",
    "maximum_adjusted_cost_regret_references",
    "maximum_actual_power_difference_kw",
    "maximum_actual_power_difference_reference_count",
    "maximum_actual_power_difference_references",
    "maximum_physical_revisions",
    "maximum_physical_revisions_reference_count",
    "maximum_physical_revisions_references",
    "d_anchor_reproduction_status",
    "runner_input_boundary_status",
    "crn_pairing_status",
    "core_tail_isolation_status",
    "output_contract_status",
    "root_files",
    "nested_daily_mpc_decision_files",
    "expected_recursive_files",
    "findings",
    "publication_status",
    "hard_status",
    "failure_stage",
    "failure_message",
)


@dataclass(frozen=True, slots=True)
class CampaignFRegime:
    """One exact seven-day Campaign-D-derived physical source sequence."""

    regime_id: str
    source_case: ResidentialCampaignDCase
    source_days: tuple[ResidentialCampaignDScenarioDay, ...]


@dataclass(frozen=True, slots=True)
class CampaignFScenarioDay:
    """Immutable forecast and realized facts for one path day before execution."""

    regime_id: str
    scenario_id: str
    scenario_class: str
    core_sample_index: int | None
    tail_case_id: str | None
    day_index: int
    source_day: ResidentialCampaignDScenarioDay
    independent_innovation: tuple[float, float, float]
    correlated_innovation: tuple[float, float, float]
    prior_latent: tuple[float, float, float]
    latent: tuple[float, float, float]
    unclipped_error: tuple[float, float, float]
    clipped_error: tuple[float, float, float]
    clip_flags: tuple[bool, bool, bool]
    timing_prior_latent: float
    timing_latent: float
    pv_shift_hours: int
    load_shift_hours: int
    tariff_shift_hours: int
    forecast_pv_profile_kw: tuple[float, ...]
    forecast_load_profile_kw: tuple[float, ...]
    forecast_tariff_profile_per_kwh: tuple[float, ...]

    @property
    def realized_source_scenario_id(self) -> str:
        return self.source_day.source_scenario.scenario_id

    @property
    def forecast_fingerprint(self) -> str:
        return _combined_fingerprint(
            self.forecast_pv_profile_kw,
            self.forecast_load_profile_kw,
            self.forecast_tariff_profile_per_kwh,
        )

    @property
    def realized_fingerprint(self) -> str:
        source = self.source_day.source_scenario
        return _combined_fingerprint(
            source.pv_profile_kw,
            source.load_profile_kw,
            source.import_tariff_profile_per_kwh,
        )


@dataclass(frozen=True, slots=True)
class CampaignFScenarioDefinition:
    scenario_id: str
    regime: CampaignFRegime
    scenario_class: str
    core_sample_index: int | None
    tail_case_id: str | None
    days: tuple[CampaignFScenarioDay, ...]


@dataclass(frozen=True, slots=True)
class CampaignFPathResult:
    scenario: CampaignFScenarioDefinition
    strategy: str
    summary: ResidentialCampaignDPathSummary
    comparison: EconomicComparisonExplanation

    @property
    def actual_powers_kw(self) -> tuple[float, ...]:
        return tuple(
            trace.simulation_trace.state.battery_result.actual_power_kw
            for day in self.summary.days
            for trace in day.trajectory.step_traces
        )


@dataclass(frozen=True, slots=True)
class CampaignFAnchorResult:
    regime: CampaignFRegime
    strategy: str
    path: CampaignFPathResult


@dataclass(frozen=True, slots=True)
class CampaignFRegretEvidence:
    path: CampaignFPathResult
    anchor: CampaignFAnchorResult
    adjusted_cost_regret: float
    actual_power_divergence_hours: int
    maximum_actual_power_difference_kw: float
    total_absolute_actual_power_difference_kwh: float


@dataclass(frozen=True, slots=True)
class _CampaignFMaximumEvidence:
    """One maximum value and every deterministic, tied source path."""

    value: float | int
    references: tuple[CampaignFPathResult, ...]


@dataclass(frozen=True, slots=True)
class CampaignFStrategyComparison:
    scenario: CampaignFScenarioDefinition
    explanation: EconomicComparisonExplanation


@dataclass(frozen=True, slots=True)
class CampaignFDistributionStatistic:
    regime_id: str
    strategy: str
    count: int
    mean: float
    population_standard_deviation: float
    minimum: float
    p05: float
    p50: float
    p90: float
    p95: float
    maximum: float
    positive_count: int
    zero_count: int
    negative_count: int


@dataclass(frozen=True, slots=True)
class CampaignFAcceptanceFinding:
    severity: str
    code: str
    regime_id: str
    scenario_id: str
    strategy: str
    day_index: int | None
    message: str
    evidence_reference: str


@dataclass(frozen=True, slots=True)
class CampaignFResult:
    regimes: tuple[CampaignFRegime, ...]
    scenarios: tuple[CampaignFScenarioDefinition, ...]
    paths: tuple[CampaignFPathResult, ...]
    anchors: tuple[CampaignFAnchorResult, ...]
    regrets: tuple[CampaignFRegretEvidence, ...]
    comparisons: tuple[CampaignFStrategyComparison, ...]
    distributions: tuple[CampaignFDistributionStatistic, ...]
    findings: tuple[CampaignFAcceptanceFinding, ...]
    hard_passed: bool
    output_paths: tuple[Path, ...]


def campaign_f_regimes() -> tuple[CampaignFRegime, ...]:
    """Select exactly three existing seven-day Campaign D cases; no fallback."""

    cases = {case.case_id: case for case in campaign_d_cases()}
    days = campaign_d_scenario_days()
    values: list[CampaignFRegime] = []
    for regime_id, case_id in _REGIME_CASE_IDS:
        if case_id not in cases:
            raise ValueError(f"Campaign F requires existing Campaign D case {case_id}")
        case = cases[case_id]
        selected = tuple(day for day in days if day.case.case_id == case_id)
        if (
            len(selected) != _DAYS
            or tuple(day.source_scenario.scenario_id for day in selected)
            != case.source_scenario_ids
        ):
            raise AssertionError(
                f"Campaign D sequence missing or changed for {case_id}"
            )
        values.append(CampaignFRegime(regime_id, case, selected))
    if len(values) != 3 or len({item.source_case.case_id for item in values}) != 3:
        raise AssertionError("Campaign F requires three distinct Campaign D regimes")
    return tuple(values)


def campaign_f_scenarios(
    regimes: tuple[CampaignFRegime, ...] | None = None,
) -> tuple[CampaignFScenarioDefinition, ...]:
    """Return 48 correlated core and 12 deterministic tail seven-day scenarios."""

    values: list[CampaignFScenarioDefinition] = []
    for regime in campaign_f_regimes() if regimes is None else regimes:
        values.extend(
            _core_scenario(regime, index) for index in range(_CORE_PER_REGIME)
        )
        values.extend(_tail_scenario(regime, tail) for tail in range(1, 5))
    if (
        len(values) != 60
        or sum(item.scenario_class == "core" for item in values) != 48
        or sum(item.scenario_class == "tail" for item in values) != 12
        or sum(len(item.days) for item in values) != 420
    ):
        raise AssertionError("Campaign F matrix must remain 48 core + 12 tail")
    return tuple(values)


def _core_scenario(regime: CampaignFRegime, sample: int) -> CampaignFScenarioDefinition:
    scenario_id = f"F-{regime.regime_id}-CORE-{sample:02d}"
    previous = _correlated_initial(regime.regime_id, sample)
    prior_timing = _normal(_key(regime.regime_id, sample, "initial", "timing", 0))
    days: list[CampaignFScenarioDay] = []
    for day_index, source_day in enumerate(regime.source_days):
        independent = (
            _normal(_key(regime.regime_id, sample, day_index, "pv", 0)),
            _normal(_key(regime.regime_id, sample, day_index, "load", 0)),
            _normal(_key(regime.regime_id, sample, day_index, "tariff", 0)),
        )
        correlated = _apply_cholesky(independent)
        current = (
            _CORE_RHO * previous[0] + math.sqrt(1.0 - _CORE_RHO**2) * correlated[0],
            _CORE_RHO * previous[1] + math.sqrt(1.0 - _CORE_RHO**2) * correlated[1],
            _CORE_RHO * previous[2] + math.sqrt(1.0 - _CORE_RHO**2) * correlated[2],
        )
        timing_innovation = _normal(
            _key(regime.regime_id, sample, day_index, "timing", 0)
        )
        timing = (
            _TIMING_RHO * prior_timing
            + math.sqrt(1.0 - _TIMING_RHO**2) * timing_innovation
        )
        unclipped = (
            _SCALES[0] * current[0],
            _SCALES[1] * current[1],
            _SCALES[2] * current[2],
        )
        clipped = (
            min(max(unclipped[0], _LOWER[0]), _UPPER[0]),
            min(max(unclipped[1], _LOWER[1]), _UPPER[1]),
            min(max(unclipped[2], _LOWER[2]), _UPPER[2]),
        )
        days.append(
            _scenario_day(
                regime,
                scenario_id,
                "core",
                sample,
                None,
                day_index,
                source_day,
                independent,
                correlated,
                previous,
                current,
                unclipped,
                clipped,
                (
                    not math.isclose(
                        unclipped[0], clipped[0], abs_tol=NUMERIC_TOLERANCE
                    ),
                    not math.isclose(
                        unclipped[1], clipped[1], abs_tol=NUMERIC_TOLERANCE
                    ),
                    not math.isclose(
                        unclipped[2], clipped[2], abs_tol=NUMERIC_TOLERANCE
                    ),
                ),
                prior_timing,
                timing,
                _shift(timing),
                _shift(timing),
                _shift(timing, tariff=True),
            )
        )
        previous = current
        prior_timing = timing
    return CampaignFScenarioDefinition(
        scenario_id, regime, "core", sample, None, tuple(days)
    )


def _tail_scenario(regime: CampaignFRegime, tail: int) -> CampaignFScenarioDefinition:
    tail_id = f"F-TAIL-{tail:02d}"
    scenario_id = f"F-{regime.regime_id}-{tail_id}"
    days: list[CampaignFScenarioDay] = []
    for day_index, source_day in enumerate(regime.source_days):
        pv, load, tariff, pv_shift, load_shift, tariff_shift = _tail_values(
            tail, day_index
        )
        values = (pv, load, tariff)
        days.append(
            _scenario_day(
                regime,
                scenario_id,
                "tail",
                None,
                tail_id,
                day_index,
                source_day,
                values,
                values,
                (0.0, 0.0, 0.0),
                values,
                values,
                values,
                (False, False, False),
                0.0,
                0.0,
                pv_shift,
                load_shift,
                tariff_shift,
            )
        )
    return CampaignFScenarioDefinition(
        scenario_id, regime, "tail", None, tail_id, tuple(days)
    )


def _tail_values(
    tail: int, day_index: int
) -> tuple[float, float, float, int, int, int]:
    if tail == 1:
        return (0.45, -0.35, -0.30, 0, 0, 0)
    if tail == 2:
        return (-0.45, 0.35, 0.30, 0, 0, 0)
    if tail == 3:
        return (0.0, 0.0, 0.0, -4, 4, 3)
    if tail == 4:
        return (
            (0.45, -0.35, -0.30, -2, 2, 1)
            if day_index < 3
            else (-0.45, 0.35, 0.30, 2, -2, -1)
        )
    raise ValueError("Campaign F tail must be in 1..4")


def _scenario_day(
    regime: CampaignFRegime,
    scenario_id: str,
    scenario_class: str,
    core_sample_index: int | None,
    tail_case_id: str | None,
    day_index: int,
    source_day: ResidentialCampaignDScenarioDay,
    independent: tuple[float, float, float],
    correlated: tuple[float, float, float],
    prior: tuple[float, float, float],
    latent: tuple[float, float, float],
    unclipped: tuple[float, float, float],
    clipped: tuple[float, float, float],
    flags: tuple[bool, bool, bool],
    prior_timing: float,
    timing: float,
    pv_shift: int,
    load_shift: int,
    tariff_shift: int,
) -> CampaignFScenarioDay:
    source = source_day.source_scenario
    pv = _shift_profile(_scale(source.pv_profile_kw, clipped[0]), pv_shift)
    load = _shift_profile(_scale(source.load_profile_kw, clipped[1]), load_shift)
    tariff = _shift_profile(
        _scale(source.import_tariff_profile_per_kwh, clipped[2]), tariff_shift
    )
    return CampaignFScenarioDay(
        regime.regime_id,
        scenario_id,
        scenario_class,
        core_sample_index,
        tail_case_id,
        day_index,
        source_day,
        independent,
        correlated,
        prior,
        latent,
        unclipped,
        clipped,
        flags,
        prior_timing,
        timing,
        pv_shift,
        load_shift,
        tariff_shift,
        pv,
        load,
        tariff,
    )


def run_residential_campaign_f(output_directory: Path) -> CampaignFResult:
    """Execute the frozen daily runner 882 times with auditable F facts."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    regimes = campaign_f_regimes()
    scenarios = campaign_f_scenarios(regimes)
    template = create_demo_input(output_directory)
    evaluator = DeterministicResidentialAcceptanceEvaluator()
    anchors = tuple(
        CampaignFAnchorResult(
            regime,
            strategy,
            _execute_path(
                _perfect_anchor(regime), strategy, template, evaluator, output_directory
            ),
        )
        for regime in regimes
        for strategy in _STRATEGIES
    )
    paths = tuple(
        _execute_path(scenario, strategy, template, evaluator, output_directory)
        for scenario in scenarios
        for strategy in _STRATEGIES
    )
    anchor_index = {(item.regime.regime_id, item.strategy): item for item in anchors}
    regrets = tuple(
        _regret(path, anchor_index[(path.scenario.regime.regime_id, path.strategy)])
        for path in paths
    )
    comparisons = tuple(
        CampaignFStrategyComparison(scenario, _comparison_for_scenario(scenario, paths))
        for scenario in scenarios
    )
    distributions = _distributions(regrets)
    semantic_findings = _findings(paths, anchors, regrets, comparisons, distributions)
    provisional = CampaignFResult(
        regimes,
        scenarios,
        paths,
        anchors,
        regrets,
        comparisons,
        distributions,
        semantic_findings,
        _hard_passed(semantic_findings),
        (),
    )
    outputs = _write_outputs(output_directory, provisional, final_status=False)
    output_findings = _output_contract_findings(
        output_directory, provisional, final_artifacts=False
    )
    findings = semantic_findings + output_findings
    hard_passed = _hard_passed(findings)
    result = CampaignFResult(
        regimes,
        scenarios,
        paths,
        anchors,
        regrets,
        comparisons,
        distributions,
        findings,
        hard_passed,
        outputs,
    )
    _write_final_status(output_directory, result)
    final_findings = _output_contract_findings(
        output_directory, result, final_artifacts=True
    )
    if not final_findings:
        return result

    diagnostic_findings = result.findings + final_findings
    diagnostic = CampaignFResult(
        result.regimes,
        result.scenarios,
        result.paths,
        result.anchors,
        result.regrets,
        result.comparisons,
        result.distributions,
        diagnostic_findings,
        False,
        result.output_paths,
    )
    _write_final_status(output_directory, diagnostic)
    diagnostic_failures = _failure_diagnostic_contract_failures(
        output_directory, diagnostic
    )
    if diagnostic_failures:
        raise RuntimeError(
            "Campaign F cannot write a diagnostic publication failure: "
            + "; ".join(diagnostic_failures)
        )
    return diagnostic


def _perfect_anchor(regime: CampaignFRegime) -> CampaignFScenarioDefinition:
    scenario_id = f"F-{regime.regime_id}-PERFECT-ANCHOR"
    days = tuple(
        _scenario_day(
            regime,
            scenario_id,
            "anchor",
            None,
            None,
            index,
            source_day,
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (False, False, False),
            0.0,
            0.0,
            0,
            0,
            0,
        )
        for index, source_day in enumerate(regime.source_days)
    )
    return CampaignFScenarioDefinition(scenario_id, regime, "anchor", None, None, days)


def _execute_path(
    scenario: CampaignFScenarioDefinition,
    strategy: str,
    template: ExplainableMPCDailySimulationInput,
    evaluator: DeterministicResidentialAcceptanceEvaluator,
    output_directory: Path,
) -> CampaignFPathResult:
    case = ResidentialCampaignDCase(
        scenario.scenario_id,
        "seven_day",
        tuple(day.realized_source_scenario_id for day in scenario.days),
        f"Campaign F {scenario.scenario_class} derived from {scenario.regime.source_case.case_id}",
        scenario.regime.source_case.initial_soc_fraction,
    )
    soc = case.initial_soc_fraction
    results: list[ResidentialCampaignDDayPathResult] = []
    for definition in scenario.days:
        source_day = definition.source_day
        day = ResidentialCampaignDScenarioDay(
            case,
            definition.day_index + 1,
            source_day.source_scenario,
            source_day.global_start_timestamp,
            source_day.global_end_timestamp,
            f"{scenario.scenario_id} day {definition.day_index}",
        )
        directory = (
            output_directory
            / "executions"
            / scenario.regime.regime_id
            / scenario.scenario_id
            / f"day_{definition.day_index:02d}"
            / strategy.lower()
        )
        input_value = _daily_input(day, definition, soc, template, directory)
        trajectory = (
            _schedule_runner(day.source_scenario.candidate_configuration).run(
                input_value
            )
            if strategy == "Schedule"
            else _economic_runner(day.source_scenario.candidate_configuration).run(
                input_value
            )
        )
        ledger = _ledger(trajectory, day.source_scenario)
        comparison = _daily_comparison(day, ledger, ledger)
        result = _day_path(
            day, strategy, soc, trajectory, ledger, comparison, evaluator
        )
        results.append(result)
        soc = result.final_actual_soc_fraction
    summary = _path_summary(case, strategy, tuple(results))
    comparison = DeterministicEconomicComparisonExplainer().explain(
        EconomicComparisonInput(
            strategy,
            strategy,
            summary.aggregate_outcome,
            summary.aggregate_outcome,
            scenario.scenario_id,
            "Campaign F completed path evidence.",
        )
    )
    return CampaignFPathResult(scenario, strategy, summary, comparison)


def _daily_input(
    day: ResidentialCampaignDScenarioDay,
    definition: CampaignFScenarioDay,
    initial_soc: float,
    template: ExplainableMPCDailySimulationInput,
    directory: Path,
) -> MultiOpportunityExplainableMPCDailySimulationInput:
    """Use forecast facts only in horizons and frozen source facts only in Simulator input."""

    directory.mkdir(parents=True, exist_ok=True)
    source = day.source_scenario
    model = source.battery_model
    identities = tuple(
        SimulationStepIdentity(
            index, 3600.0, day.global_start_timestamp + timedelta(hours=index)
        )
        for index in range(_HOURS)
    )
    realized = DailySimulationScenarioInput(
        identities,
        source.pv_profile_kw,
        source.load_profile_kw,
        source.import_tariff_profile_per_kwh,
        BatteryParameters(
            model.usable_capacity_kwh,
            model.max_charge_power_kw,
            model.max_discharge_power_kw,
            model.charge_efficiency,
            model.discharge_efficiency,
            model.min_soc_fraction,
        ),
        initial_soc,
    )
    integration_template = template.integration_input
    integration = EMSIntegrationScenarioInput(
        realized,
        integration_template.objective_composition,
        integration_template.capability,
        max(model.max_charge_power_kw, model.max_discharge_power_kw),
        integration_template.export_limit_kw,
        integration_template.initial_grid_power_kw,
    )
    horizons = _forecast_horizons(
        realized, definition, template.mpc_configuration.forecast_horizon_points
    )
    daily = ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        model,
        template.explanation_locale,
        directory / "mpc_decisions.csv",
    )
    return MultiOpportunityExplainableMPCDailySimulationInput(
        daily,
        source.candidate_configuration,
        PVOpportunityWindowConfiguration(_GAP_TOLERANCE_POINTS),
    )


def _forecast_horizons(
    realized: DailySimulationScenarioInput,
    definition: CampaignFScenarioDay,
    point_count: int,
) -> tuple[ForecastHorizon, ...]:
    values: list[ForecastHorizon] = []
    for hour, identity in enumerate(realized.step_identities):
        if identity.timestamp is None:
            raise ValueError("Campaign F requires explicit timestamps")
        points = tuple(
            ForecastPoint(
                identity.timestamp + timedelta(hours=offset),
                definition.forecast_pv_profile_kw[hour + offset]
                if hour + offset < _HOURS
                else 0.0,
                definition.forecast_load_profile_kw[hour + offset]
                if hour + offset < _HOURS
                else 0.0,
                definition.forecast_tariff_profile_per_kwh[hour + offset]
                if hour + offset < _HOURS
                else _FORECAST_FALLBACK_TARIFF,
            )
            for offset in range(point_count)
        )
        values.append(ForecastHorizon(points))
    return tuple(values)


def _comparison_for_scenario(
    scenario: CampaignFScenarioDefinition,
    paths: tuple[CampaignFPathResult, ...],
) -> EconomicComparisonExplanation:
    items = {path.strategy: path for path in paths if path.scenario is scenario}
    if set(items) != {"Schedule", "Economic"}:
        raise AssertionError("Campaign F strategy comparison requires two real paths")
    return DeterministicEconomicComparisonExplainer().explain(
        EconomicComparisonInput(
            "Schedule",
            "Economic",
            items["Schedule"].summary.aggregate_outcome,
            items["Economic"].summary.aggregate_outcome,
            scenario.scenario_id,
            "Campaign F multi-day completed outcomes; candidate minus reference.",
        )
    )


def _regret(
    path: CampaignFPathResult, anchor: CampaignFAnchorResult
) -> CampaignFRegretEvidence:
    if path.strategy != anchor.strategy or path.scenario.regime is not anchor.regime:
        raise ValueError("regret requires same-regime same-strategy anchor")
    actual = path.actual_powers_kw
    baseline = anchor.path.actual_powers_kw
    if len(actual) != 168 or len(baseline) != 168:
        raise AssertionError("Campaign F paths must contain exactly 168 actual hours")
    differences = tuple(
        abs(left - right) for left, right in zip(actual, baseline, strict=True)
    )
    return CampaignFRegretEvidence(
        path,
        anchor,
        path.summary.aggregate_outcome.adjusted_net_economic_cost
        - anchor.path.summary.aggregate_outcome.adjusted_net_economic_cost,
        sum(value > NUMERIC_TOLERANCE for value in differences),
        max(differences),
        sum(differences),
    )


def _distributions(
    regrets: tuple[CampaignFRegretEvidence, ...],
) -> tuple[CampaignFDistributionStatistic, ...]:
    values: list[CampaignFDistributionStatistic] = []
    grouped: dict[tuple[str, str], list[float]] = defaultdict(list)
    for regret in regrets:
        if regret.path.scenario.scenario_class == "core":
            grouped[
                (regret.path.scenario.regime.regime_id, regret.path.strategy)
            ].append(regret.adjusted_cost_regret)
    for (regime_id, strategy), points in sorted(grouped.items()):
        ordered = tuple(sorted(points))
        if len(ordered) != 16:
            raise AssertionError(
                "each core distribution must contain exactly 16 points"
            )
        values.append(
            CampaignFDistributionStatistic(
                regime_id,
                strategy,
                len(ordered),
                fmean(ordered),
                pstdev(ordered),
                ordered[0],
                _nearest(ordered, 0.05),
                _nearest(ordered, 0.50),
                _nearest(ordered, 0.90),
                _nearest(ordered, 0.95),
                ordered[-1],
                sum(value > NUMERIC_TOLERANCE for value in ordered),
                sum(abs(value) <= NUMERIC_TOLERANCE for value in ordered),
                sum(value < -NUMERIC_TOLERANCE for value in ordered),
            )
        )
    return tuple(values)


def _findings(
    paths: tuple[CampaignFPathResult, ...],
    anchors: tuple[CampaignFAnchorResult, ...],
    regrets: tuple[CampaignFRegretEvidence, ...],
    comparisons: tuple[CampaignFStrategyComparison, ...],
    distributions: tuple[CampaignFDistributionStatistic, ...],
) -> tuple[CampaignFAcceptanceFinding, ...]:
    values: list[CampaignFAcceptanceFinding] = []
    for path in paths + tuple(anchor.path for anchor in anchors):
        for day in path.summary.days:
            if not _daily_passed(day):
                values.append(
                    _finding(
                        "MAJOR",
                        "DAILY_ACCEPTANCE",
                        path,
                        day.scenario_day.day_index - 1,
                        "Frozen daily acceptance failed.",
                    )
                )
        if path.summary.timestamp_discontinuity_count:
            values.append(
                _finding(
                    "BLOCKER",
                    "TIMESTAMP_CONTINUITY",
                    path,
                    None,
                    "Multi-day timestamps are discontinuous.",
                )
            )
        if not _aggregate_reconciled(path.summary):
            values.append(
                _finding(
                    "BLOCKER",
                    "ACCOUNTING_RECONCILIATION",
                    path,
                    None,
                    "Aggregate accounting does not reconcile.",
                )
            )
        if any(not item.passed for item in path.summary.continuity):
            values.append(
                _finding(
                    "BLOCKER",
                    "SOC_CONTINUITY",
                    path,
                    None,
                    "Actual Simulator SOC carry failed.",
                )
            )
    for anchor in anchors:
        if any(
            day.forecast_fingerprint != day.realized_fingerprint
            for day in anchor.path.scenario.days
        ):
            values.append(
                _finding(
                    "BLOCKER",
                    "ANCHOR_FORECAST",
                    anchor.path,
                    None,
                    "Perfect anchor forecast differs from realized facts.",
                )
            )
    if len(regrets) != 120 or len(comparisons) != 60 or len(distributions) != 6:
        values.append(
            CampaignFAcceptanceFinding(
                "BLOCKER",
                "MATRIX",
                "",
                "",
                "",
                None,
                "Campaign F result matrix is incomplete.",
                "matrix",
            )
        )
    values.extend(_anchor_reproduction_findings(anchors))
    values.extend(_runner_input_boundary_findings(paths, anchors))
    values.extend(_crn_pairing_findings(paths))
    values.extend(
        _core_tail_statistics_findings(paths, anchors, regrets, distributions)
    )
    return tuple(values)


def _runner_input_boundary_findings(
    paths: tuple[CampaignFPathResult, ...],
    anchors: tuple[CampaignFAnchorResult, ...],
) -> tuple[CampaignFAcceptanceFinding, ...]:
    """Prove every retained runner input still matches its immutable scenario facts."""

    values: list[CampaignFAcceptanceFinding] = []
    for path in paths + tuple(anchor.path for anchor in anchors):
        if len(path.summary.days) != _DAYS:
            values.append(
                _gate_finding(
                    "RUNNER_INPUT_BOUNDARY_FAILURE",
                    f"path={path.scenario.scenario_id};strategy={path.strategy}",
                    "Campaign F retained path does not contain the frozen seven-day input boundary.",
                )
            )
            continue
        for definition, day in zip(path.scenario.days, path.summary.days, strict=True):
            if _runner_input_matches_definition(definition, day):
                continue
            values.append(
                _gate_finding(
                    "RUNNER_INPUT_BOUNDARY_FAILURE",
                    "path="
                    + path.scenario.scenario_id
                    + ";strategy="
                    + path.strategy
                    + ";day="
                    + str(definition.day_index),
                    "Campaign F retained runner input differs from its immutable forecast or realized scenario facts.",
                )
            )
    return tuple(values)


def _runner_input_matches_definition(
    definition: CampaignFScenarioDay,
    day: ResidentialCampaignDDayPathResult,
) -> bool:
    daily_mpc = day.trajectory.source_input.daily_mpc_input
    realized = daily_mpc.integration_input.daily_input
    source = definition.source_day.source_scenario
    expected_timestamps = tuple(
        definition.source_day.global_start_timestamp + timedelta(hours=index)
        for index in range(_HOURS)
    )
    if (
        realized.pv_power_curve_kw is not source.pv_profile_kw
        or realized.load_power_curve_kw is not source.load_profile_kw
        or realized.tariff_curve_cny_per_kwh is not source.import_tariff_profile_per_kwh
        or tuple(identity.timestamp for identity in realized.step_identities)
        != expected_timestamps
        or len(daily_mpc.forecast_horizons) != _HOURS
    ):
        return False
    for hour, horizon in enumerate(daily_mpc.forecast_horizons):
        for offset, point in enumerate(horizon.points):
            profile_index = hour + offset
            expected = (
                expected_timestamps[hour] + timedelta(hours=offset),
                definition.forecast_pv_profile_kw[profile_index]
                if profile_index < _HOURS
                else 0.0,
                definition.forecast_load_profile_kw[profile_index]
                if profile_index < _HOURS
                else 0.0,
                definition.forecast_tariff_profile_per_kwh[profile_index]
                if profile_index < _HOURS
                else _FORECAST_FALLBACK_TARIFF,
            )
            if (
                point.timestamp,
                point.pv_power_kw,
                point.load_power_kw,
                point.electricity_price_cny_per_kwh,
            ) != expected:
                return False
    return True


def _hard_passed(findings: tuple[CampaignFAcceptanceFinding, ...]) -> bool:
    return not any(item.severity in {"BLOCKER", "MAJOR"} for item in findings)


def _scenario_key(
    scenario: CampaignFScenarioDefinition,
) -> tuple[str, str]:
    return (scenario.regime.regime_id, scenario.scenario_id)


def _sampled_path_key(path: CampaignFPathResult) -> tuple[str, str, str]:
    return (*_scenario_key(path.scenario), path.strategy)


def _expected_scenario_keys() -> frozenset[tuple[str, str]]:
    return frozenset(
        (regime_id, f"F-{regime_id}-CORE-{index:02d}")
        for regime_id, _ in _REGIME_CASE_IDS
        for index in range(_CORE_PER_REGIME)
    ) | frozenset(
        (regime_id, f"F-{regime_id}-F-TAIL-{tail:02d}")
        for regime_id, _ in _REGIME_CASE_IDS
        for tail in range(1, _TAIL_PER_REGIME + 1)
    )


def _expected_core_path_keys() -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (regime_id, f"F-{regime_id}-CORE-{index:02d}", strategy)
        for regime_id, _ in _REGIME_CASE_IDS
        for index in range(_CORE_PER_REGIME)
        for strategy in _STRATEGIES
    )


def _expected_tail_path_keys() -> frozenset[tuple[str, str, str]]:
    return frozenset(
        (regime_id, f"F-{regime_id}-F-TAIL-{tail:02d}", strategy)
        for regime_id, _ in _REGIME_CASE_IDS
        for tail in range(1, _TAIL_PER_REGIME + 1)
        for strategy in _STRATEGIES
    )


def _expected_sampled_path_keys() -> frozenset[tuple[str, str, str]]:
    return _expected_core_path_keys() | _expected_tail_path_keys()


def _anchor_reproduction_findings(
    anchors: tuple[CampaignFAnchorResult, ...],
) -> tuple[CampaignFAcceptanceFinding, ...]:
    values: list[CampaignFAcceptanceFinding] = []
    expected_keys = {
        (regime_id, strategy)
        for regime_id in _D_ANCHOR_SIGNATURES
        for strategy in ("Schedule", "Economic")
    }
    actual_keys = {(item.regime.regime_id, item.strategy) for item in anchors}
    if actual_keys != expected_keys:
        values.append(
            _gate_finding(
                "D_ANCHOR_REPRODUCTION_FAILURE",
                "anchor matrix",
                "Campaign F anchors must contain each D01/D03/D02 regime and strategy.",
            )
        )
    for anchor in anchors:
        expected = _D_ANCHOR_SIGNATURES.get(anchor.regime.regime_id)
        path = anchor.path
        if expected is None:
            values.append(
                _gate_finding(
                    "D_ANCHOR_REPRODUCTION_FAILURE",
                    f"anchor={path.scenario.scenario_id}",
                    "Anchor regime is not a frozen Campaign D signature.",
                )
            )
            continue
        (
            case_id,
            grid_import,
            grid_export,
            degradation,
            final_soc,
            terminal_value,
            adjusted_cost,
            revisions,
        ) = expected
        outcome = path.summary.aggregate_outcome
        actual = (
            path.scenario.regime.source_case.case_id == case_id
            and tuple(day.realized_source_scenario_id for day in path.scenario.days)
            == anchor.regime.source_case.source_scenario_ids
            and tuple(
                day.source_day.global_start_timestamp for day in path.scenario.days
            )
            == tuple(day.global_start_timestamp for day in anchor.regime.source_days)
            and all(
                day.forecast_fingerprint == day.realized_fingerprint
                for day in path.scenario.days
            )
            and math.isclose(
                sum(
                    day.ledger.total_grid_import_energy_kwh for day in path.summary.days
                ),
                grid_import,
                rel_tol=0.0,
                abs_tol=_ANCHOR_SIGNATURE_TOLERANCE,
            )
            and math.isclose(
                sum(
                    day.ledger.total_grid_export_energy_kwh for day in path.summary.days
                ),
                grid_export,
                rel_tol=0.0,
                abs_tol=_ANCHOR_SIGNATURE_TOLERANCE,
            )
            and math.isclose(
                outcome.battery_degradation_cost,
                degradation,
                rel_tol=0.0,
                abs_tol=_ANCHOR_SIGNATURE_TOLERANCE,
            )
            and math.isclose(
                path.summary.final_actual_soc_fraction,
                final_soc,
                rel_tol=0.0,
                abs_tol=_ANCHOR_SIGNATURE_TOLERANCE,
            )
            and math.isclose(
                path.summary.final_terminal_evidence.terminal_energy_value,
                terminal_value,
                rel_tol=0.0,
                abs_tol=_ANCHOR_SIGNATURE_TOLERANCE,
            )
            and math.isclose(
                outcome.adjusted_net_economic_cost,
                adjusted_cost,
                rel_tol=0.0,
                abs_tol=_ANCHOR_SIGNATURE_TOLERANCE,
            )
            and path.summary.total_physical_revisions == revisions
        )
        if not actual:
            values.append(
                _gate_finding(
                    "D_ANCHOR_REPRODUCTION_FAILURE",
                    f"anchor={path.scenario.scenario_id};strategy={path.strategy}",
                    "Campaign F perfect anchor differs from its frozen Campaign D signature.",
                )
            )
    return tuple(values)


def _crn_pairing_findings(
    paths: tuple[CampaignFPathResult, ...],
) -> tuple[CampaignFAcceptanceFinding, ...]:
    values: list[CampaignFAcceptanceFinding] = []
    expected_paths = _expected_sampled_path_keys()
    actual_paths = Counter(_sampled_path_key(path) for path in paths)
    if actual_paths != Counter({key: 1 for key in expected_paths}):
        missing = sorted(key for key in expected_paths if actual_paths[key] == 0)
        extra = sorted(key for key in actual_paths if key not in expected_paths)
        duplicate = sorted(key for key, count in actual_paths.items() if count != 1)
        values.append(
            _gate_finding(
                "CRN_PAIRING_FAILURE",
                "missing="
                + repr(missing)
                + "; extra="
                + repr(extra)
                + "; duplicate="
                + repr(duplicate),
                "Campaign F requires exactly one path for every expected scenario/strategy key.",
            )
        )
    by_scenario: dict[tuple[str, str], list[CampaignFPathResult]] = defaultdict(list)
    for path in paths:
        by_scenario[_scenario_key(path.scenario)].append(path)
    for scenario_key in sorted(_expected_scenario_keys()):
        paired = by_scenario.get(scenario_key, [])
        strategies = Counter(path.strategy for path in paired)
        if strategies != Counter({strategy: 1 for strategy in _STRATEGIES}):
            values.append(
                _gate_finding(
                    "CRN_PAIRING_FAILURE",
                    f"scenario={scenario_key}; strategies={dict(strategies)}",
                    "Campaign F comparison requires exactly one Schedule and one Economic path.",
                )
            )
            continue
        schedule = next(path for path in paired if path.strategy == "Schedule")
        economic = next(path for path in paired if path.strategy == "Economic")
        if not _crn_pair_isolated_and_equal(schedule, economic):
            values.append(
                _gate_finding(
                    "CRN_PAIRING_FAILURE",
                    f"scenario={scenario_key}",
                    "Schedule/Economic paths do not retain equal exogenous facts and independent execution objects.",
                )
            )
    return tuple(values)


def _crn_pair_isolated_and_equal(
    schedule: CampaignFPathResult, economic: CampaignFPathResult
) -> bool:
    if len(schedule.summary.days) != _DAYS or len(economic.summary.days) != _DAYS:
        return False
    for schedule_definition, economic_definition, schedule_day, economic_day in zip(
        schedule.scenario.days,
        economic.scenario.days,
        schedule.summary.days,
        economic.summary.days,
        strict=True,
    ):
        schedule_input = schedule_day.trajectory.source_input.daily_mpc_input
        economic_input = economic_day.trajectory.source_input.daily_mpc_input
        schedule_realized = schedule_input.integration_input.daily_input
        economic_realized = economic_input.integration_input.daily_input
        if (
            schedule_definition.day_index != economic_definition.day_index
            or schedule_definition.realized_source_scenario_id
            != economic_definition.realized_source_scenario_id
            or schedule_definition.forecast_fingerprint
            != economic_definition.forecast_fingerprint
            or schedule_definition.realized_fingerprint
            != economic_definition.realized_fingerprint
            or _forecast_payload(schedule_input.forecast_horizons)
            != _forecast_payload(economic_input.forecast_horizons)
            or schedule_realized.pv_power_curve_kw
            != economic_realized.pv_power_curve_kw
            or schedule_realized.load_power_curve_kw
            != economic_realized.load_power_curve_kw
            or schedule_realized.tariff_curve_cny_per_kwh
            != economic_realized.tariff_curve_cny_per_kwh
            or tuple(item.timestamp for item in schedule_realized.step_identities)
            != tuple(item.timestamp for item in economic_realized.step_identities)
            or schedule_day.trajectory is economic_day.trajectory
            or schedule_day.trajectory.source_input
            is economic_day.trajectory.source_input
            or schedule_day.trajectory.step_traces
            is economic_day.trajectory.step_traces
            or schedule_day is economic_day
            or schedule_day.trajectory.journal_records
            is economic_day.trajectory.journal_records
        ):
            return False
        for schedule_trace, economic_trace in zip(
            _day_traces(schedule_day), _day_traces(economic_day), strict=True
        ):
            if (
                schedule_trace is economic_trace
                or schedule_trace.simulation_trace is economic_trace.simulation_trace
                or schedule_trace.simulation_trace.state
                is economic_trace.simulation_trace.state
                or schedule_trace.journal_record is economic_trace.journal_record
            ):
                return False
    return True


def _forecast_payload(
    horizons: tuple[ForecastHorizon, ...],
) -> tuple[tuple[tuple[object, ...], ...], ...]:
    return tuple(
        tuple(
            (
                point.timestamp,
                point.pv_power_kw,
                point.load_power_kw,
                point.electricity_price_cny_per_kwh,
            )
            for point in horizon.points
        )
        for horizon in horizons
    )


def _core_tail_statistics_findings(
    paths: tuple[CampaignFPathResult, ...],
    anchors: tuple[CampaignFAnchorResult, ...],
    regrets: tuple[CampaignFRegretEvidence, ...],
    distributions: tuple[CampaignFDistributionStatistic, ...],
) -> tuple[CampaignFAcceptanceFinding, ...]:
    core_paths = tuple(path for path in paths if path.scenario.scenario_class == "core")
    tail_paths = tuple(path for path in paths if path.scenario.scenario_class == "tail")
    core_regrets = tuple(
        item for item in regrets if item.path.scenario.scenario_class == "core"
    )
    groups: dict[tuple[str, str], list[tuple[str, str, str]]] = defaultdict(list)
    for regret in core_regrets:
        groups[(regret.path.scenario.regime.regime_id, regret.path.strategy)].append(
            _sampled_path_key(regret.path)
        )
    expected_core_paths = _expected_core_path_keys()
    expected_tail_paths = _expected_tail_path_keys()
    actual_core_paths = Counter(_sampled_path_key(path) for path in core_paths)
    actual_tail_paths = Counter(_sampled_path_key(path) for path in tail_paths)
    expected_groups = {
        (regime_id, strategy): {
            key
            for key in expected_core_paths
            if key[0] == regime_id and key[2] == strategy
        }
        for regime_id, _ in _REGIME_CASE_IDS
        for strategy in _STRATEGIES
    }
    valid = (
        actual_core_paths == Counter({key: 1 for key in expected_core_paths})
        and actual_tail_paths == Counter({key: 1 for key in expected_tail_paths})
        and len(regrets) == len(paths)
        and {id(item.path) for item in regrets} == {id(path) for path in paths}
        and Counter(_sampled_path_key(item.path) for item in core_regrets)
        == Counter({key: 1 for key in expected_core_paths})
        and all(
            item.path not in tuple(anchor.path for anchor in anchors)
            for item in regrets
        )
        and {key: set(items) for key, items in groups.items()} == expected_groups
        and all(len(items) == 16 and len(set(items)) == 16 for items in groups.values())
        and len(distributions) == 6
        and {(item.regime_id, item.strategy, item.count) for item in distributions}
        == {(regime, strategy, 16) for regime, strategy in groups}
    )
    if valid:
        return ()
    return (
        _gate_finding(
            "CORE_TAIL_STATISTICS_CONTAMINATION",
            "core distributions",
            "Core distributions must contain exactly 16 unique core regrets per regime and strategy only.",
        ),
    )


def _gate_finding(
    code: str, evidence_reference: str, message: str
) -> CampaignFAcceptanceFinding:
    return CampaignFAcceptanceFinding(
        "BLOCKER", code, "", "", "", None, message, evidence_reference
    )


def _finding(
    severity: str,
    code: str,
    path: CampaignFPathResult,
    day_index: int | None,
    message: str,
) -> CampaignFAcceptanceFinding:
    return CampaignFAcceptanceFinding(
        severity,
        code,
        path.scenario.regime.regime_id,
        path.scenario.scenario_id,
        path.strategy,
        day_index,
        message,
        path.scenario.scenario_id,
    )


def _daily_passed(day: ResidentialCampaignDDayPathResult) -> bool:
    return not any(
        finding.status is ResidentialAcceptanceStatus.FAIL
        and finding.severity
        in {ResidentialAcceptanceSeverity.BLOCKER, ResidentialAcceptanceSeverity.MAJOR}
        for finding in day.acceptance.findings
    )


def _key(regime: str, sample: int, day: int | str, component: str, pair: int) -> str:
    return f"{_SEED}|{regime}|{sample}|{day}|{component}|{pair}"


def _uniform(key: str) -> float:
    """Return a SHA-256-derived value in the open interval (0, 1)."""

    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return (int.from_bytes(digest[:16], "big") + 1) / (2**128 + 1)


def _normal(key: str) -> float:
    return math.sqrt(-2.0 * math.log(_uniform(f"{key}|u1"))) * math.cos(
        2.0 * math.pi * _uniform(f"{key}|u2")
    )


def _correlated_initial(regime: str, sample: int) -> tuple[float, float, float]:
    return _apply_cholesky(
        (
            _normal(_key(regime, sample, "initial", "pv", 0)),
            _normal(_key(regime, sample, "initial", "load", 0)),
            _normal(_key(regime, sample, "initial", "tariff", 0)),
        )
    )


def _correlated(key: str) -> tuple[float, float, float]:
    """Compatibility helper used by tests; key ordering remains deterministic."""

    return _apply_cholesky(
        (_normal(f"{key}|pv"), _normal(f"{key}|load"), _normal(f"{key}|tariff"))
    )


def _apply_cholesky(values: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        _CHOLESKY[0][0] * values[0],
        _CHOLESKY[1][0] * values[0] + _CHOLESKY[1][1] * values[1],
        _CHOLESKY[2][0] * values[0]
        + _CHOLESKY[2][1] * values[1]
        + _CHOLESKY[2][2] * values[2],
    )


def _shift(value: float, tariff: bool = False) -> int:
    if tariff:
        return -1 if value <= -0.75 else 1 if value >= 0.75 else 0
    if value <= -1.0:
        return -2
    if value <= -0.35:
        return -1
    if value < 0.35:
        return 0
    if value < 1.0:
        return 1
    return 2


def _scale(values: tuple[float, ...], error: float) -> tuple[float, ...]:
    return tuple(max(0.0, value * (1.0 + error)) for value in values)


def _shift_profile(values: tuple[float, ...], shift: int) -> tuple[float, ...]:
    if shift == 0:
        return values
    distance = abs(shift) % len(values)
    return (
        values[distance:] + values[:distance]
        if shift < 0
        else values[-distance:] + values[:-distance]
    )


def _nearest(values: tuple[float, ...], percentile: float) -> float:
    return values[max(0, math.ceil(percentile * len(values)) - 1)]


def _combined_fingerprint(
    pv: tuple[float, ...], load: tuple[float, ...], tariff: tuple[float, ...]
) -> str:
    return hashlib.sha256(
        "|".join(
            f"{value:.12f}" for values in (pv, load, tariff) for value in values
        ).encode("ascii")
    ).hexdigest()


def _csv(rows: Iterable[Iterable[object]]) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue()


def _number(value: float) -> str:
    """Render evidence values without feeding display rounding back into accounting."""

    return f"{value:.12f}"


def _write_outputs(
    directory: Path, result: CampaignFResult, *, final_status: bool
) -> tuple[Path, ...]:
    files: dict[str, str] = {
        "campaign_f_summary.txt": _summary(result, final_status=final_status),
        "campaign_f_regime_manifest.csv": _regime_csv(result.regimes),
        "campaign_f_scenario_manifest.csv": _scenario_csv(result.scenarios),
        "campaign_f_scenario_day_manifest.csv": _scenario_day_csv(result.scenarios),
        "campaign_f_anchor_path_results.csv": _path_csv(
            tuple(anchor.path for anchor in result.anchors), "anchor"
        ),
        "campaign_f_anchor_daily_results.csv": _daily_csv(
            tuple(anchor.path for anchor in result.anchors)
        ),
        "campaign_f_path_results.csv": _path_csv(result.paths, "sampled_or_tail"),
        "campaign_f_daily_results.csv": _daily_csv(result.paths),
        "campaign_f_regret_evidence.csv": _regret_csv(result.regrets),
        "campaign_f_strategy_comparisons.csv": _comparison_csv(result.comparisons),
        "campaign_f_core_distribution_summary.csv": _distribution_csv(
            result.distributions
        ),
        "campaign_f_tail_results.csv": _tail_csv(result.paths, result.regrets),
        "campaign_f_soc_continuity.csv": _continuity_csv(result.paths, result.anchors),
        "campaign_f_hourly_trace.csv": _hourly_csv(result.paths),
        "campaign_f_anchor_hourly_trace.csv": _hourly_csv(
            tuple(anchor.path for anchor in result.anchors)
        ),
        "campaign_f_acceptance_findings.csv": _findings_csv(result.findings),
    }
    files.update(_charts(result))
    paths: list[Path] = []
    for name, content in files.items():
        path = directory / name
        path.write_text(content, encoding="utf-8", newline="")
        paths.append(path)
    return tuple(paths)


def _write_final_status(directory: Path, result: CampaignFResult) -> None:
    (directory / "campaign_f_summary.txt").write_text(
        _summary(result, final_status=True, directory=directory),
        encoding="utf-8",
        newline="",
    )
    (directory / "campaign_f_acceptance_findings.csv").write_text(
        _findings_csv(result.findings), encoding="utf-8", newline=""
    )


def _summary(
    result: CampaignFResult, *, final_status: bool, directory: Path | None = None
) -> str:
    return "\n".join(
        (
            _SUMMARY_TITLE,
            *(
                f"{key}={value}"
                for key, value in _summary_values(
                    result, final_status=final_status, directory=directory
                )
            ),
            "",
        )
    )


def _summary_values(
    result: CampaignFResult, *, final_status: bool, directory: Path | None
) -> tuple[tuple[str, str], ...]:
    paths = result.paths + tuple(anchor.path for anchor in result.anchors)
    root_files, nested_files, recursive_files = _artifact_counts(directory)
    finding_codes = {item.code for item in result.findings}
    publication_status = (
        "PASS"
        if final_status and result.hard_passed
        else "PENDING"
        if not final_status
        else "FAIL"
    )
    failure_stage, failure_message = _publication_failure_context(
        result, final_status=final_status
    )
    maximum_regret = _maximum_adjusted_cost_regret_evidence(result)
    maximum_power = _maximum_actual_power_evidence(result)
    maximum_revisions = _maximum_physical_revision_evidence(paths)
    values = (
        ("campaign_id", "Campaign F"),
        ("summary_schema_version", "2"),
        ("seed", str(_SEED)),
        ("regimes", str(len(result.regimes))),
        (
            "core_scenarios",
            str(sum(item.scenario_class == "core" for item in result.scenarios)),
        ),
        (
            "tail_scenarios",
            str(sum(item.scenario_class == "tail" for item in result.scenarios)),
        ),
        ("total_scenarios", str(len(result.scenarios))),
        ("sampled_tail_paths", str(len(result.paths))),
        ("perfect_anchor_paths", str(len(result.anchors))),
        ("total_paths", str(len(paths))),
        (
            "sampled_tail_daily_executions",
            str(sum(len(path.summary.days) for path in result.paths)),
        ),
        (
            "anchor_daily_executions",
            str(sum(len(anchor.path.summary.days) for anchor in result.anchors)),
        ),
        ("total_daily_executions", str(sum(len(path.summary.days) for path in paths))),
        (
            "schedule_daily_executions",
            str(
                sum(
                    len(path.summary.days)
                    for path in paths
                    if path.strategy == "Schedule"
                )
            ),
        ),
        (
            "economic_daily_executions",
            str(
                sum(
                    len(path.summary.days)
                    for path in paths
                    if path.strategy == "Economic"
                )
            ),
        ),
        ("scenario_days", str(sum(len(item.days) for item in result.scenarios))),
        (
            "sampled_tail_hours",
            str(sum(len(path.actual_powers_kw) for path in result.paths)),
        ),
        (
            "anchor_hours",
            str(sum(len(anchor.path.actual_powers_kw) for anchor in result.anchors)),
        ),
        ("total_hours", str(sum(len(path.actual_powers_kw) for path in paths))),
        ("soc_boundaries", str(sum(len(path.summary.continuity) for path in paths))),
        (
            "continuity_failures",
            str(
                sum(
                    not item.passed
                    for path in paths
                    for item in path.summary.continuity
                )
            ),
        ),
        (
            "clip_evidence",
            str(
                sum(
                    any(day.clip_flags)
                    for scenario in result.scenarios
                    for day in scenario.days
                )
            ),
        ),
        ("regret_evidence", str(len(result.regrets))),
        ("strategy_comparisons", str(len(result.comparisons))),
        (
            "maximum_adjusted_cost_regret",
            repr(maximum_regret.value),
        ),
        (
            "maximum_adjusted_cost_regret_reference_count",
            str(len(maximum_regret.references)),
        ),
        (
            "maximum_adjusted_cost_regret_references",
            _maximum_references_json(maximum_regret),
        ),
        (
            "maximum_actual_power_difference_kw",
            repr(maximum_power.value),
        ),
        (
            "maximum_actual_power_difference_reference_count",
            str(len(maximum_power.references)),
        ),
        (
            "maximum_actual_power_difference_references",
            _maximum_references_json(maximum_power),
        ),
        (
            "maximum_physical_revisions",
            str(maximum_revisions.value),
        ),
        (
            "maximum_physical_revisions_reference_count",
            str(len(maximum_revisions.references)),
        ),
        (
            "maximum_physical_revisions_references",
            _maximum_references_json(maximum_revisions),
        ),
        (
            "d_anchor_reproduction_status",
            "FAIL" if "D_ANCHOR_REPRODUCTION_FAILURE" in finding_codes else "PASS",
        ),
        (
            "runner_input_boundary_status",
            "FAIL" if "RUNNER_INPUT_BOUNDARY_FAILURE" in finding_codes else "PASS",
        ),
        (
            "crn_pairing_status",
            "FAIL" if "CRN_PAIRING_FAILURE" in finding_codes else "PASS",
        ),
        (
            "core_tail_isolation_status",
            "FAIL" if "CORE_TAIL_STATISTICS_CONTAMINATION" in finding_codes else "PASS",
        ),
        (
            "output_contract_status",
            "FAIL" if "OUTPUT_CONTRACT_FAILURE" in finding_codes else "PASS",
        ),
        ("root_files", str(root_files)),
        ("nested_daily_mpc_decision_files", str(nested_files)),
        ("expected_recursive_files", str(recursive_files)),
        ("findings", str(len(result.findings))),
        ("publication_status", publication_status),
        ("hard_status", "PASS" if final_status and result.hard_passed else "FAIL"),
        ("failure_stage", failure_stage),
        ("failure_message", failure_message),
    )
    if tuple(key for key, _ in values) != _SUMMARY_KEYS:
        raise AssertionError("Campaign F summary schema changed without validation")
    return values


def _artifact_counts(directory: Path | None) -> tuple[int, int, int]:
    if directory is None:
        return (26, 882, 908)
    files = tuple(path for path in directory.rglob("*") if path.is_file())
    return (
        sum(path.parent == directory for path in files),
        sum(path.name == "mpc_decisions.csv" for path in files),
        len(files),
    )


def _path_reference(path: CampaignFPathResult) -> str:
    return f"{path.scenario.scenario_id}/{path.strategy}"


def _maximum_adjusted_cost_regret_evidence(
    result: CampaignFResult,
) -> _CampaignFMaximumEvidence:
    return _maximum_float_evidence(
        tuple((item.adjusted_cost_regret, item.path) for item in result.regrets)
    )


def _maximum_actual_power_evidence(
    result: CampaignFResult,
) -> _CampaignFMaximumEvidence:
    return _maximum_float_evidence(
        tuple(
            (item.maximum_actual_power_difference_kw, item.path)
            for item in result.regrets
        )
    )


def _maximum_physical_revision_evidence(
    paths: tuple[CampaignFPathResult, ...],
) -> _CampaignFMaximumEvidence:
    if not paths:
        return _CampaignFMaximumEvidence(0, ())
    maximum = max(item.summary.total_physical_revisions for item in paths)
    return _CampaignFMaximumEvidence(
        maximum,
        _ordered_references(
            item for item in paths if item.summary.total_physical_revisions == maximum
        ),
    )


def _maximum_float_evidence(
    values: tuple[tuple[float, CampaignFPathResult], ...],
) -> _CampaignFMaximumEvidence:
    if not values:
        return _CampaignFMaximumEvidence(0.0, ())
    maximum = max(value for value, _ in values)
    return _CampaignFMaximumEvidence(
        maximum,
        _ordered_references(
            path
            for value, path in values
            if math.isclose(
                value,
                maximum,
                rel_tol=_MAXIMUM_FLOAT_TIE_RELATIVE_TOLERANCE,
                abs_tol=_MAXIMUM_FLOAT_TIE_ABSOLUTE_TOLERANCE,
            )
        ),
    )


def _ordered_references(
    paths: Iterable[CampaignFPathResult],
) -> tuple[CampaignFPathResult, ...]:
    strategy_order = {strategy: index for index, strategy in enumerate(_STRATEGIES)}
    return tuple(
        sorted(
            paths,
            key=lambda item: (
                item.scenario.scenario_id,
                strategy_order[item.strategy],
            ),
        )
    )


def _maximum_references_json(evidence: _CampaignFMaximumEvidence) -> str:
    return json.dumps(
        [
            {
                "scenario_id": path.scenario.scenario_id,
                "strategy": path.strategy,
                "value": evidence.value,
            }
            for path in evidence.references
        ],
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _publication_failure_context(
    result: CampaignFResult, *, final_status: bool
) -> tuple[str, str]:
    if not final_status:
        return ("not_finalized", "none")
    if not result.findings:
        return ("none", "none")
    finding = result.findings[0]
    stage = (
        "publication_validation"
        if finding.code == "OUTPUT_CONTRACT_FAILURE"
        else "semantic_validation"
    )
    message = f"{finding.code}:{finding.evidence_reference}".replace("\n", " ")
    return (stage, message or "unspecified")


def _output_contract_findings(
    directory: Path, result: CampaignFResult, *, final_artifacts: bool = True
) -> tuple[CampaignFAcceptanceFinding, ...]:
    """Validate emitted evidence before, and again after, publication finalization."""

    headers = _output_csv_headers()
    expected_root = {
        "campaign_f_summary.txt",
        *headers,
        "campaign_f_core_regret_ecdf_reference.svg",
        "campaign_f_core_regret_ecdf_high_pv.svg",
        "campaign_f_core_regret_ecdf_high_evening_load.svg",
        "campaign_f_tail_regret_reference.svg",
        "campaign_f_tail_regret_high_pv.svg",
        "campaign_f_tail_regret_high_evening_load.svg",
        "campaign_f_core_actual_power_divergence.svg",
        "campaign_f_physical_revisions.svg",
        "campaign_f_soc_continuity.svg",
        "campaign_f_core_tail_ranking_summary.svg",
    }
    expected_rows = {
        "campaign_f_regime_manifest.csv": 3,
        "campaign_f_scenario_manifest.csv": 60,
        "campaign_f_scenario_day_manifest.csv": 420,
        "campaign_f_anchor_path_results.csv": 6,
        "campaign_f_anchor_daily_results.csv": 42,
        "campaign_f_path_results.csv": 120,
        "campaign_f_daily_results.csv": 840,
        "campaign_f_regret_evidence.csv": 120,
        "campaign_f_strategy_comparisons.csv": 60,
        "campaign_f_core_distribution_summary.csv": 6,
        "campaign_f_tail_results.csv": 24,
        "campaign_f_soc_continuity.csv": 756,
        "campaign_f_hourly_trace.csv": 20160,
        "campaign_f_anchor_hourly_trace.csv": 1008,
        "campaign_f_acceptance_findings.csv": len(result.findings),
    }
    failures: list[str] = []
    actual_root = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_root != expected_root:
        failures.append("root relative-path set")
    for name, expected_header in headers.items():
        path = directory / name
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                rows = tuple(csv.reader(handle))
        except (OSError, UnicodeError, csv.Error) as error:
            failures.append(f"{name}: unreadable ({error})")
            continue
        if not rows or tuple(rows[0]) != expected_header:
            failures.append(f"{name}: schema")
            continue
        if len(rows) - 1 != expected_rows[name]:
            failures.append(f"{name}: row cardinality")
    failures.extend(_output_traceability_failures(directory, result))
    failures.extend(_output_svg_failures(directory))
    if final_artifacts:
        failures.extend(_final_artifact_failures(directory, result))
    if not failures:
        return ()
    return (
        _gate_finding(
            "OUTPUT_CONTRACT_FAILURE",
            "; ".join(failures),
            "Campaign F emitted evidence does not satisfy the publication output contract.",
        ),
    )


def _final_artifact_failures(
    directory: Path, result: CampaignFResult, *, diagnostic: bool = False
) -> list[str]:
    failures: list[str] = []
    summary_path = directory / "campaign_f_summary.txt"
    try:
        title, summary = _summary_fields(summary_path)
    except (OSError, UnicodeError, ValueError) as error:
        failures.append(f"campaign_f_summary.txt: final schema ({error})")
    else:
        expected = _summary_values(result, final_status=True, directory=directory)
        if title != _SUMMARY_TITLE:
            failures.append("campaign_f_summary.txt: title")
        if summary != expected:
            failures.append("campaign_f_summary.txt: complete final content")
        failures.extend(_maximum_evidence_contract_failures(summary, result))
        if any(value == "PENDING" for _, value in summary):
            failures.append("campaign_f_summary.txt: pending publication state")
        if not diagnostic and _artifact_counts(directory) != (26, 882, 908):
            failures.append("campaign_f_summary.txt: normal artifact cardinality")
    findings_path = directory / "campaign_f_acceptance_findings.csv"
    try:
        with findings_path.open(encoding="utf-8", newline="") as handle:
            actual_findings = tuple(csv.reader(handle))
    except (OSError, UnicodeError, csv.Error) as error:
        failures.append(f"campaign_f_acceptance_findings.csv: unreadable ({error})")
    else:
        expected_findings = tuple(csv.reader(StringIO(_findings_csv(result.findings))))
        if actual_findings != expected_findings:
            failures.append("campaign_f_acceptance_findings.csv: final content")
    return failures


def _maximum_evidence_contract_failures(
    summary: tuple[tuple[str, str], ...], result: CampaignFResult
) -> list[str]:
    """Independently parse and reconcile summary argmax sets to retained evidence.

    This validator deliberately does not call the summary generator's maximum,
    tie-collection, ordering or JSON helpers.  Shared constants express the
    public contract; separate calculations prevent common-mode self-validation.
    """

    values = dict(summary)
    strategy_rank = {"Schedule": 0, "Economic": 1}
    paths = result.paths + tuple(anchor.path for anchor in result.anchors)

    regret_candidates = [
        (item.path.scenario.scenario_id, item.path.strategy, item.adjusted_cost_regret)
        for item in result.regrets
    ]
    power_candidates = [
        (
            item.path.scenario.scenario_id,
            item.path.strategy,
            item.maximum_actual_power_difference_kw,
        )
        for item in result.regrets
    ]
    revision_candidates = [
        (
            item.scenario.scenario_id,
            item.strategy,
            item.summary.total_physical_revisions,
        )
        for item in paths
    ]
    expected_items = (
        (
            "maximum_adjusted_cost_regret",
            "maximum_adjusted_cost_regret",
            regret_candidates,
            True,
        ),
        (
            "maximum_actual_power_difference_kw",
            "maximum_actual_power_difference",
            power_candidates,
            True,
        ),
        (
            "maximum_physical_revisions",
            "maximum_physical_revisions",
            revision_candidates,
            False,
        ),
    )
    failures: list[str] = []
    for value_key, reference_prefix, candidates, floating in expected_items:
        count_key = f"{reference_prefix}_reference_count"
        references_key = f"{reference_prefix}_references"
        if not candidates or any(
            isinstance(candidate[2], bool)
            or not isinstance(candidate[2], int | float)
            or not math.isfinite(candidate[2])
            for candidate in candidates
        ):
            failures.append(f"campaign_f_summary.txt: {references_key} raw evidence")
            continue
        maximum = candidates[0][2]
        for _, _, candidate_value in candidates[1:]:
            if candidate_value > maximum:
                maximum = candidate_value
        expected_references = []
        for scenario_id, strategy, candidate_value in candidates:
            tied = (
                math.isclose(
                    candidate_value,
                    maximum,
                    rel_tol=_MAXIMUM_FLOAT_TIE_RELATIVE_TOLERANCE,
                    abs_tol=_MAXIMUM_FLOAT_TIE_ABSOLUTE_TOLERANCE,
                )
                if floating
                else candidate_value == maximum
            )
            if tied:
                expected_references.append((scenario_id, strategy, candidate_value))
        expected_references.sort(key=lambda item: (item[0], strategy_rank[item[1]]))
        try:
            count = int(values[count_key])
        except (KeyError, ValueError):
            failures.append(f"campaign_f_summary.txt: {count_key}")
            continue
        if count != len(expected_references):
            failures.append(f"campaign_f_summary.txt: {count_key} mismatch")
        try:
            summary_maximum = float(values[value_key])
        except (KeyError, ValueError):
            failures.append(f"campaign_f_summary.txt: {value_key} value")
        else:
            matches_maximum = (
                math.isclose(
                    summary_maximum,
                    maximum,
                    rel_tol=_MAXIMUM_FLOAT_TIE_RELATIVE_TOLERANCE,
                    abs_tol=_MAXIMUM_FLOAT_TIE_ABSOLUTE_TOLERANCE,
                )
                if floating
                else summary_maximum == maximum
            )
            if not matches_maximum:
                failures.append(f"campaign_f_summary.txt: {value_key} value")
        try:
            parsed = json.loads(values[references_key])
        except (KeyError, json.JSONDecodeError):
            failures.append(f"campaign_f_summary.txt: {references_key} encoding")
            continue
        if not isinstance(parsed, list) or any(
            not isinstance(item, dict)
            or set(item) != {"scenario_id", "strategy", "value"}
            or not isinstance(item["scenario_id"], str)
            or not item["scenario_id"]
            or not isinstance(item["strategy"], str)
            or item["strategy"] not in _STRATEGIES
            or isinstance(item["value"], bool)
            or not isinstance(item["value"], int | float)
            or not math.isfinite(item["value"])
            for item in parsed
        ):
            failures.append(f"campaign_f_summary.txt: {references_key} structure")
            continue
        actual_references = [
            (item["scenario_id"], item["strategy"], item["value"]) for item in parsed
        ]
        if len(
            {(scenario_id, strategy) for scenario_id, strategy, _ in actual_references}
        ) != len(actual_references):
            failures.append(f"campaign_f_summary.txt: {references_key} duplicate")
        if actual_references != expected_references:
            failures.append(
                f"campaign_f_summary.txt: {references_key} retained argmax set"
            )
    return failures


def _failure_diagnostic_contract_failures(
    directory: Path, result: CampaignFResult
) -> list[str]:
    failures = _final_artifact_failures(directory, result, diagnostic=True)
    if result.hard_passed:
        failures.append("diagnostic result must be hard FAIL")
    if not any(item.code == "OUTPUT_CONTRACT_FAILURE" for item in result.findings):
        failures.append("diagnostic findings lack OUTPUT_CONTRACT_FAILURE")
    return failures


def _summary_fields(path: Path) -> tuple[str, tuple[tuple[str, str], ...]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0]:
        raise ValueError("missing title")
    fields: list[tuple[str, str]] = []
    seen: set[str] = set()
    for line in lines[1:]:
        if "=" not in line:
            raise ValueError("malformed field")
        key, value = line.split("=", 1)
        if not key or not value or key in seen:
            raise ValueError("duplicate or empty field")
        seen.add(key)
        fields.append((key, value))
    if tuple(key for key, _ in fields) != _SUMMARY_KEYS:
        raise ValueError("unexpected field schema or order")
    return (lines[0], tuple(fields))


def _output_csv_headers() -> dict[str, tuple[str, ...]]:
    return {
        "campaign_f_regime_manifest.csv": (
            "regime_id",
            "campaign_d_case_id",
            "initial_soc_fraction",
            "start_timestamp",
            "source_scenario_ids",
        ),
        "campaign_f_scenario_manifest.csv": (
            "scenario_id",
            "regime_id",
            "scenario_class",
            "core_sample_index",
            "tail_case_id",
            "day_count",
        ),
        "campaign_f_scenario_day_manifest.csv": (
            "scenario_id",
            "regime_id",
            "scenario_class",
            "day_index",
            "source_scenario_id",
            "timestamp",
            "independent_pv",
            "independent_load",
            "independent_tariff",
            "correlated_pv",
            "correlated_load",
            "correlated_tariff",
            "prior_pv",
            "prior_load",
            "prior_tariff",
            "latent_pv",
            "latent_load",
            "latent_tariff",
            "unclipped_pv_error",
            "unclipped_load_error",
            "unclipped_tariff_error",
            "clipped_pv_error",
            "clipped_load_error",
            "clipped_tariff_error",
            "pv_clipped",
            "load_clipped",
            "tariff_clipped",
            "timing_prior",
            "timing_latent",
            "pv_shift_hours",
            "load_shift_hours",
            "tariff_shift_hours",
            "forecast_fingerprint",
            "realized_fingerprint",
        ),
        "campaign_f_anchor_path_results.csv": _path_header(),
        "campaign_f_path_results.csv": _path_header(),
        "campaign_f_anchor_daily_results.csv": _daily_header(),
        "campaign_f_daily_results.csv": _daily_header(),
        "campaign_f_regret_evidence.csv": (
            "scenario_id",
            "regime_id",
            "scenario_class",
            "strategy",
            "anchor_id",
            "adjusted_cost_regret",
            "actual_power_divergence_hours",
            "maximum_actual_power_difference_kw",
            "total_absolute_actual_power_difference_kwh",
        ),
        "campaign_f_strategy_comparisons.csv": (
            "scenario_id",
            "regime_id",
            "scenario_class",
            "ranking",
            "delta_adjusted_cost",
            "dominant_components",
        ),
        "campaign_f_core_distribution_summary.csv": (
            "regime_id",
            "strategy",
            "count",
            "mean_regret",
            "population_stddev",
            "minimum",
            "p05",
            "p50",
            "p90",
            "p95",
            "maximum",
            "positive_count",
            "zero_count",
            "negative_count",
        ),
        "campaign_f_tail_results.csv": (
            "scenario_id",
            "regime_id",
            "tail_case_id",
            "strategy",
            "adjusted_cost_regret",
            "actual_power_divergence_hours",
        ),
        "campaign_f_soc_continuity.csv": (
            "path_id",
            "strategy",
            "day_index",
            "prior_final_actual_soc_fraction",
            "current_initial_soc_fraction",
            "carry_delta",
            "timestamp_gap_hours",
            "passed",
        ),
        "campaign_f_hourly_trace.csv": _hourly_header(),
        "campaign_f_anchor_hourly_trace.csv": _hourly_header(),
        "campaign_f_acceptance_findings.csv": (
            "severity",
            "code",
            "regime_id",
            "scenario_id",
            "strategy",
            "day_index",
            "message",
            "evidence_reference",
        ),
    }


def _path_header() -> tuple[str, ...]:
    return (
        "path_id",
        "execution_scope",
        "regime_id",
        "scenario_class",
        "strategy",
        "adjusted_net_economic_cost",
        "operating_cost",
        "terminal_value",
        "grid_import_kwh",
        "grid_export_kwh",
        "battery_throughput_kwh",
        "final_actual_soc_fraction",
        "physical_revisions",
        "timestamp_discontinuities",
        "forecast_fingerprint",
    )


def _daily_header() -> tuple[str, ...]:
    return (
        "path_id",
        "regime_id",
        "scenario_class",
        "strategy",
        "day_index",
        "source_scenario_id",
        "initial_actual_soc_fraction",
        "final_actual_soc_fraction",
        "import_cost",
        "export_revenue",
        "degradation_cost",
        "terminal_value_diagnostic",
        "physical_revisions",
        "forecast_fingerprint",
        "realized_fingerprint",
        "daily_acceptance_passed",
    )


def _hourly_header() -> tuple[str, ...]:
    return (
        "path_id",
        "regime_id",
        "scenario_class",
        "strategy",
        "day_index",
        "hour_index",
        "timestamp",
        "forecast_fingerprint",
        "realized_fingerprint",
        "actual_battery_power_kw",
        "actual_soc_fraction",
        "actual_grid_power_kw",
        "realized_pv_kw",
        "realized_load_kw",
        "realized_import_tariff_per_kwh",
    )


def _output_traceability_failures(
    directory: Path, result: CampaignFResult
) -> list[str]:
    nested = tuple(directory.rglob("mpc_decisions.csv"))
    expected_nested = _expected_nested_contents(result)
    actual_nested = {path.relative_to(directory) for path in nested}
    if actual_nested != set(expected_nested):
        return ["nested mpc_decisions.csv relative-path set"]
    with ThreadPoolExecutor(max_workers=16) as executor:
        failures = tuple(
            executor.map(
                lambda relative: _nested_csv_failure(
                    directory, relative, expected_nested[relative]
                ),
                sorted(expected_nested),
            )
        )
    if any(failures):
        return [next(failure for failure in failures if failure is not None)]
    for name, scope in (
        ("campaign_f_path_results.csv", "sampled_or_tail"),
        ("campaign_f_anchor_path_results.csv", "anchor"),
    ):
        with (directory / name).open(encoding="utf-8", newline="") as handle:
            rows = tuple(csv.DictReader(handle))
        if any(
            row["execution_scope"] != scope
            or not row["path_id"]
            or not row["regime_id"]
            or not row["strategy"]
            for row in rows
        ):
            return [f"{name}: execution scope or traceability"]
    return []


def _nested_csv_failure(
    directory: Path, relative: Path, expected_content: str
) -> str | None:
    try:
        with (directory / relative).open(encoding="utf-8", newline="") as handle:
            actual_rows = tuple(csv.reader(handle))
        expected_rows = tuple(csv.reader(StringIO(expected_content)))
    except (OSError, UnicodeError, csv.Error) as error:
        return f"nested {relative}: unreadable ({error})"
    if (
        len(expected_rows) != _HOURS + 1
        or not expected_rows
        or tuple(expected_rows[0]) != _NESTED_MPC_DECISION_HEADER
    ):
        raise AssertionError("Campaign F retained nested CSV contract is incomplete")
    if not actual_rows or tuple(actual_rows[0]) != _NESTED_MPC_DECISION_HEADER:
        return f"nested {relative}: schema"
    if len(actual_rows) != _HOURS + 1:
        return f"nested {relative}: row cardinality"
    header_indexes = {
        value: index for index, value in enumerate(_NESTED_MPC_DECISION_HEADER)
    }
    previous_timestamp: datetime | None = None
    for row_index, (actual, expected) in enumerate(
        zip(actual_rows[1:], expected_rows[1:], strict=True)
    ):
        if len(actual) != len(_NESTED_MPC_DECISION_HEADER):
            return f"nested {relative}: row {row_index} structure"
        if actual != expected:
            return f"nested {relative}: row {row_index} retained-content mismatch"
        for name in _NESTED_REQUIRED_TEXT_COLUMNS:
            if not actual[header_indexes[name]]:
                return f"nested {relative}: row {row_index} missing {name}"
        for name in _NESTED_BOOLEAN_COLUMNS:
            if actual[header_indexes[name]] not in {"true", "false"}:
                return f"nested {relative}: row {row_index} invalid {name}"
        for name in _NESTED_NUMERIC_COLUMNS:
            try:
                value = float(actual[header_indexes[name]])
            except ValueError:
                return f"nested {relative}: row {row_index} nonnumeric {name}"
            if not math.isfinite(value):
                return f"nested {relative}: row {row_index} nonfinite {name}"
        if any(
            float(actual[header_indexes[name]]) < 0.0
            for name in ("candidate_requested_power_kw", "final_requested_power_kw")
        ):
            return f"nested {relative}: row {row_index} negative requested power"
        if any(
            actual[header_indexes[name]] not in _NESTED_ACTION_VALUES
            for name in ("candidate_action", "final_action")
        ):
            return f"nested {relative}: row {row_index} invalid action"
        try:
            timestamp = datetime.fromisoformat(actual[header_indexes["timestamp"]])
        except ValueError:
            return f"nested {relative}: row {row_index} invalid timestamp"
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return f"nested {relative}: row {row_index} naive timestamp"
        if (
            previous_timestamp is not None
            and timestamp - previous_timestamp != timedelta(hours=1)
        ):
            return f"nested {relative}: row {row_index} timestamp sequence"
        previous_timestamp = timestamp
    return None


def _expected_nested_contents(result: CampaignFResult) -> dict[Path, str]:
    paths = result.paths + tuple(anchor.path for anchor in result.anchors)
    values: dict[Path, str] = {}
    for path in paths:
        for definition, day in zip(path.scenario.days, path.summary.days, strict=True):
            relative = _nested_relative_path(path, definition)
            if relative in values:
                raise AssertionError("Campaign F nested CSV relative path is ambiguous")
            values[relative] = day.trajectory.csv_content
    return values


def _nested_relative_path(
    path: CampaignFPathResult, definition: CampaignFScenarioDay
) -> Path:
    return (
        Path("executions")
        / path.scenario.regime.regime_id
        / path.scenario.scenario_id
        / f"day_{definition.day_index:02d}"
        / path.strategy.lower()
        / "mpc_decisions.csv"
    )


def _output_svg_failures(directory: Path) -> list[str]:
    failures: list[str] = []
    for path in directory.glob("campaign_f_*.svg"):
        try:
            root = ElementTree.parse(path).getroot()
        except (ElementTree.ParseError, OSError) as error:
            failures.append(f"{path.name}: XML ({error})")
            continue
        visible = " ".join(
            element.text or ""
            for element in root.iter()
            if element.tag.endswith("text")
        )
        required = (
            "unit=",
            "R=REFERENCE",
            "HP=HIGH_PV",
            "HEL=HIGH_EVENING_LOAD",
            "S=Schedule",
            "E=Economic",
            "mapping=",
        )
        if any(value not in visible for value in required):
            failures.append(f"{path.name}: visible traceability")
    return failures


def _regime_csv(regimes: tuple[CampaignFRegime, ...]) -> str:
    return _csv(
        [
            (
                "regime_id",
                "campaign_d_case_id",
                "initial_soc_fraction",
                "start_timestamp",
                "source_scenario_ids",
            )
        ]
        + [
            (
                item.regime_id,
                item.source_case.case_id,
                _number(item.source_case.initial_soc_fraction),
                item.source_days[0].global_start_timestamp.isoformat(),
                "|".join(item.source_case.source_scenario_ids),
            )
            for item in regimes
        ]
    )


def _scenario_csv(scenarios: tuple[CampaignFScenarioDefinition, ...]) -> str:
    return _csv(
        [
            (
                "scenario_id",
                "regime_id",
                "scenario_class",
                "core_sample_index",
                "tail_case_id",
                "day_count",
            )
        ]
        + [
            (
                item.scenario_id,
                item.regime.regime_id,
                item.scenario_class,
                item.core_sample_index or "",
                item.tail_case_id or "",
                len(item.days),
            )
            for item in scenarios
        ]
    )


def _scenario_day_csv(scenarios: tuple[CampaignFScenarioDefinition, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "scenario_id",
            "regime_id",
            "scenario_class",
            "day_index",
            "source_scenario_id",
            "timestamp",
            "independent_pv",
            "independent_load",
            "independent_tariff",
            "correlated_pv",
            "correlated_load",
            "correlated_tariff",
            "prior_pv",
            "prior_load",
            "prior_tariff",
            "latent_pv",
            "latent_load",
            "latent_tariff",
            "unclipped_pv_error",
            "unclipped_load_error",
            "unclipped_tariff_error",
            "clipped_pv_error",
            "clipped_load_error",
            "clipped_tariff_error",
            "pv_clipped",
            "load_clipped",
            "tariff_clipped",
            "timing_prior",
            "timing_latent",
            "pv_shift_hours",
            "load_shift_hours",
            "tariff_shift_hours",
            "forecast_fingerprint",
            "realized_fingerprint",
        )
    ]
    for item in scenarios:
        for day in item.days:
            rows.append(
                (
                    item.scenario_id,
                    item.regime.regime_id,
                    item.scenario_class,
                    day.day_index,
                    day.realized_source_scenario_id,
                    day.source_day.global_start_timestamp.isoformat(),
                    *map(_number, day.independent_innovation),
                    *map(_number, day.correlated_innovation),
                    *map(_number, day.prior_latent),
                    *map(_number, day.latent),
                    *map(_number, day.unclipped_error),
                    *map(_number, day.clipped_error),
                    *[str(value).lower() for value in day.clip_flags],
                    _number(day.timing_prior_latent),
                    _number(day.timing_latent),
                    day.pv_shift_hours,
                    day.load_shift_hours,
                    day.tariff_shift_hours,
                    day.forecast_fingerprint,
                    day.realized_fingerprint,
                )
            )
    return _csv(rows)


def _path_csv(paths: tuple[CampaignFPathResult, ...], scope: str) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "path_id",
            "execution_scope",
            "regime_id",
            "scenario_class",
            "strategy",
            "adjusted_net_economic_cost",
            "operating_cost",
            "terminal_value",
            "grid_import_kwh",
            "grid_export_kwh",
            "battery_throughput_kwh",
            "final_actual_soc_fraction",
            "physical_revisions",
            "timestamp_discontinuities",
            "forecast_fingerprint",
        )
    ]
    for path in paths:
        outcome = path.summary.aggregate_outcome
        rows.append(
            (
                path.scenario.scenario_id,
                scope,
                path.scenario.regime.regime_id,
                path.scenario.scenario_class,
                path.strategy,
                _number(outcome.adjusted_net_economic_cost),
                _number(
                    outcome.realized_import_cost
                    - outcome.realized_export_revenue
                    + outcome.battery_degradation_cost
                ),
                _number(path.summary.final_terminal_evidence.terminal_energy_value),
                _number(
                    sum(
                        day.ledger.total_grid_import_energy_kwh
                        for day in path.summary.days
                    )
                ),
                _number(
                    sum(
                        day.ledger.total_grid_export_energy_kwh
                        for day in path.summary.days
                    )
                ),
                _number(
                    sum(
                        day.ledger.total_battery_throughput_kwh
                        for day in path.summary.days
                    )
                ),
                _number(path.summary.final_actual_soc_fraction),
                sum(day.kpi.physical_revision_count for day in path.summary.days),
                path.summary.timestamp_discontinuity_count,
                path.scenario.days[0].forecast_fingerprint,
            )
        )
    return _csv(rows)


def _daily_csv(paths: tuple[CampaignFPathResult, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "path_id",
            "regime_id",
            "scenario_class",
            "strategy",
            "day_index",
            "source_scenario_id",
            "initial_actual_soc_fraction",
            "final_actual_soc_fraction",
            "import_cost",
            "export_revenue",
            "degradation_cost",
            "terminal_value_diagnostic",
            "physical_revisions",
            "forecast_fingerprint",
            "realized_fingerprint",
            "daily_acceptance_passed",
        )
    ]
    for path in paths:
        for definition, day in zip(path.scenario.days, path.summary.days, strict=True):
            rows.append(
                (
                    path.scenario.scenario_id,
                    path.scenario.regime.regime_id,
                    path.scenario.scenario_class,
                    path.strategy,
                    definition.day_index,
                    definition.realized_source_scenario_id,
                    _number(day.initial_soc_fraction),
                    _number(day.final_actual_soc_fraction),
                    _number(day.ledger.total_realized_import_cost),
                    _number(day.ledger.total_realized_export_revenue),
                    _number(day.ledger.total_battery_degradation_cost),
                    _number(day.ledger.terminal_energy_value),
                    day.kpi.physical_revision_count,
                    definition.forecast_fingerprint,
                    definition.realized_fingerprint,
                    str(_daily_passed(day)).lower(),
                )
            )
    return _csv(rows)


def _regret_csv(regrets: tuple[CampaignFRegretEvidence, ...]) -> str:
    return _csv(
        [
            (
                "scenario_id",
                "regime_id",
                "scenario_class",
                "strategy",
                "anchor_id",
                "adjusted_cost_regret",
                "actual_power_divergence_hours",
                "maximum_actual_power_difference_kw",
                "total_absolute_actual_power_difference_kwh",
            )
        ]
        + [
            (
                item.path.scenario.scenario_id,
                item.path.scenario.regime.regime_id,
                item.path.scenario.scenario_class,
                item.path.strategy,
                item.anchor.path.scenario.scenario_id,
                _number(item.adjusted_cost_regret),
                item.actual_power_divergence_hours,
                _number(item.maximum_actual_power_difference_kw),
                _number(item.total_absolute_actual_power_difference_kwh),
            )
            for item in regrets
        ]
    )


def _comparison_csv(comparisons: tuple[CampaignFStrategyComparison, ...]) -> str:
    return _csv(
        [
            (
                "scenario_id",
                "regime_id",
                "scenario_class",
                "ranking",
                "delta_adjusted_cost",
                "dominant_components",
            )
        ]
        + [
            (
                item.scenario.scenario_id,
                item.scenario.regime.regime_id,
                item.scenario.scenario_class,
                item.explanation.ranking.value,
                _number(item.explanation.delta_adjusted_cost),
                "|".join(
                    component.value
                    for component in item.explanation.dominant_components
                ),
            )
            for item in comparisons
        ]
    )


def _distribution_csv(values: tuple[CampaignFDistributionStatistic, ...]) -> str:
    return _csv(
        [
            (
                "regime_id",
                "strategy",
                "count",
                "mean_regret",
                "population_stddev",
                "minimum",
                "p05",
                "p50",
                "p90",
                "p95",
                "maximum",
                "positive_count",
                "zero_count",
                "negative_count",
            )
        ]
        + [
            (
                item.regime_id,
                item.strategy,
                item.count,
                _number(item.mean),
                _number(item.population_standard_deviation),
                _number(item.minimum),
                _number(item.p05),
                _number(item.p50),
                _number(item.p90),
                _number(item.p95),
                _number(item.maximum),
                item.positive_count,
                item.zero_count,
                item.negative_count,
            )
            for item in values
        ]
    )


def _tail_csv(
    paths: tuple[CampaignFPathResult, ...], regrets: tuple[CampaignFRegretEvidence, ...]
) -> str:
    indexed = {id(item.path): item for item in regrets}
    return _csv(
        [
            (
                "scenario_id",
                "regime_id",
                "tail_case_id",
                "strategy",
                "adjusted_cost_regret",
                "actual_power_divergence_hours",
            )
        ]
        + [
            (
                path.scenario.scenario_id,
                path.scenario.regime.regime_id,
                path.scenario.tail_case_id,
                path.strategy,
                _number(indexed[id(path)].adjusted_cost_regret),
                indexed[id(path)].actual_power_divergence_hours,
            )
            for path in paths
            if path.scenario.scenario_class == "tail"
        ]
    )


def _continuity_csv(
    paths: tuple[CampaignFPathResult, ...], anchors: tuple[CampaignFAnchorResult, ...]
) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "path_id",
            "strategy",
            "day_index",
            "prior_final_actual_soc_fraction",
            "current_initial_soc_fraction",
            "carry_delta",
            "timestamp_gap_hours",
            "passed",
        )
    ]
    for path in paths + tuple(anchor.path for anchor in anchors):
        for evidence in path.summary.continuity:
            rows.append(
                (
                    path.scenario.scenario_id,
                    path.strategy,
                    evidence.day_index - 1,
                    _number(evidence.prior_final_actual_soc_fraction),
                    _number(evidence.current_initial_soc_fraction),
                    _number(evidence.carry_delta),
                    _number(evidence.timestamp_gap_hours),
                    str(evidence.passed).lower(),
                )
            )
    return _csv(rows)


def _hourly_csv(paths: tuple[CampaignFPathResult, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "path_id",
            "regime_id",
            "scenario_class",
            "strategy",
            "day_index",
            "hour_index",
            "timestamp",
            "forecast_fingerprint",
            "realized_fingerprint",
            "actual_battery_power_kw",
            "actual_soc_fraction",
            "actual_grid_power_kw",
            "realized_pv_kw",
            "realized_load_kw",
            "realized_import_tariff_per_kwh",
        )
    ]
    for path in paths:
        for definition, day in zip(path.scenario.days, path.summary.days, strict=True):
            for hour, trace in enumerate(_day_traces(day)):
                state = trace.simulation_trace.state
                rows.append(
                    (
                        path.scenario.scenario_id,
                        path.scenario.regime.regime_id,
                        path.scenario.scenario_class,
                        path.strategy,
                        definition.day_index,
                        hour,
                        trace.context.source_context.timestamp.isoformat(),
                        definition.forecast_fingerprint,
                        definition.realized_fingerprint,
                        _number(state.battery_result.actual_power_kw),
                        _number(state.battery_result.next_state.soc),
                        _number(state.grid_result.actual_grid_power_kw),
                        _number(state.pv_result.actual_power_kw),
                        _number(state.load_result.actual_power_kw),
                        _number(state.tariff_result.import_price_cny_per_kwh),
                    )
                )
    return _csv(rows)


def _day_traces(
    day: ResidentialCampaignDDayPathResult,
) -> tuple[
    MultiOpportunityExplainableMPCDailySimulationStepTrace
    | EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
    ...,
]:
    trajectory = day.trajectory
    if isinstance(
        trajectory, EconomicMultiOpportunityExplainableMPCDailySimulationResult
    ):
        return trajectory.step_traces
    if isinstance(trajectory, MultiOpportunityExplainableMPCDailySimulationResult):
        return trajectory.step_traces
    raise TypeError("Campaign F requires a completed frozen multi-opportunity trace")


def _findings_csv(findings: tuple[CampaignFAcceptanceFinding, ...]) -> str:
    return _csv(
        [
            (
                "severity",
                "code",
                "regime_id",
                "scenario_id",
                "strategy",
                "day_index",
                "message",
                "evidence_reference",
            )
        ]
        + [
            (
                item.severity,
                item.code,
                item.regime_id,
                item.scenario_id,
                item.strategy,
                item.day_index if item.day_index is not None else "",
                item.message,
                item.evidence_reference,
            )
            for item in findings
        ]
    )


def _charts(result: CampaignFResult) -> dict[str, str]:
    charts: dict[str, str] = {}
    for regime in result.regimes:
        core = tuple(
            item
            for item in result.regrets
            if item.path.scenario.regime is regime
            and item.path.scenario.scenario_class == "core"
        )
        tail = tuple(
            item
            for item in result.regrets
            if item.path.scenario.regime is regime
            and item.path.scenario.scenario_class == "tail"
        )
        charts[f"campaign_f_core_regret_ecdf_{regime.regime_id.lower()}.svg"] = (
            _ecdf_svg(f"{regime.regime_id} core adjusted-cost regret", core)
        )
        charts[f"campaign_f_tail_regret_{regime.regime_id.lower()}.svg"] = _bar_svg(
            f"{regime.regime_id} deterministic tail regret",
            "currency",
            tuple(
                (
                    _trace_label(item.path.scenario, item.path.strategy),
                    item.adjusted_cost_regret,
                )
                for item in tail
            ),
        )
    core = tuple(
        item for item in result.regrets if item.path.scenario.scenario_class == "core"
    )
    charts["campaign_f_core_actual_power_divergence.svg"] = _bar_svg(
        "Core actual Simulator battery-power divergence",
        "hours",
        tuple(
            (
                _trace_label(item.path.scenario, item.path.strategy),
                float(item.actual_power_divergence_hours),
            )
            for item in core
        ),
    )
    charts["campaign_f_physical_revisions.svg"] = _bar_svg(
        "Completed-path physical revisions",
        "count",
        tuple(
            (
                _trace_label(path.scenario, path.strategy),
                float(
                    sum(day.kpi.physical_revision_count for day in path.summary.days)
                ),
            )
            for path in result.paths
        ),
    )
    charts["campaign_f_soc_continuity.svg"] = _bar_svg(
        "Final actual SOC by completed path",
        "SOC fraction",
        tuple(
            (
                _trace_label(path.scenario, path.strategy),
                path.summary.final_actual_soc_fraction,
            )
            for path in result.paths
        ),
    )
    charts["campaign_f_core_tail_ranking_summary.svg"] = _bar_svg(
        "Core and tail adjusted-cost regret summary",
        "currency",
        tuple(
            (
                _regime_short(item.regime_id)
                + "-"
                + _strategy_short(item.strategy)
                + "-MEAN",
                item.mean,
            )
            for item in result.distributions
        ),
    )
    if len(charts) != 10:
        raise AssertionError("Campaign F requires exactly ten SVG reports")
    return charts


def _ecdf_svg(title: str, regrets: tuple[CampaignFRegretEvidence, ...]) -> str:
    groups: dict[str, list[CampaignFRegretEvidence]] = defaultdict(list)
    for item in regrets:
        groups[item.path.strategy].append(item)
    values = tuple(
        item.adjusted_cost_regret for points in groups.values() for item in points
    ) or (0.0,)
    lower, upper = _bounds(values)
    lines = [
        f'<text x="20" y="24">{escape(title)}</text>',
        '<line x1="55" y1="250" x2="775" y2="250" stroke="#555"/>',
    ]
    mapping_lines: list[str] = []
    for index, (strategy, points) in enumerate(sorted(groups.items())):
        ordered = tuple(
            sorted(
                points,
                key=lambda item: (
                    item.adjusted_cost_regret,
                    item.path.scenario.scenario_id,
                    item.path.strategy,
                ),
            )
        )
        color = ("#2474b5", "#d05a35")[index]
        path = " ".join(
            f"{_x(item.adjusted_cost_regret, lower, upper):.2f},{250 - 180 * (rank + 1) / len(ordered):.2f}"
            for rank, item in enumerate(ordered)
        )
        lines.append(
            f'<polyline fill="none" stroke="{color}" points="{path}"/><text x="{80 + index * 130}" y="280" fill="{color}">{escape(strategy)} n={len(ordered)}</text>'
        )
        mapping_lines.extend(_ecdf_mapping_lines(strategy, ordered))
    lines.append(
        f'<text x="55" y="315">zero={_x(0.0, lower, upper):.2f}; unit=currency; core only</text>'
    )
    lines.extend(_svg_legend(330))
    for index, mapping in enumerate(mapping_lines):
        lines.append(f'<text x="55" y="{365 + index * 14}">{escape(mapping)}</text>')
    return _svg(lines, height=380 + len(mapping_lines) * 14)


def _ecdf_mapping_lines(
    strategy: str, ordered: tuple[CampaignFRegretEvidence, ...]
) -> tuple[str, ...]:
    short = _strategy_short(strategy)
    entries = tuple(
        f"{rank:02d}={_trace_label(item.path.scenario, strategy)}:{item.adjusted_cost_regret:.6f}"
        for rank, item in enumerate(ordered, start=1)
    )
    return tuple(
        "mapping=" + short + " rank " + " | ".join(entries[index : index + 4])
        for index in range(0, len(entries), 4)
    )


def _bar_svg(title: str, unit: str, values: tuple[tuple[str, float], ...]) -> str:
    minimum, maximum = _bounds(tuple(value for _, value in values) or (0.0,))
    baseline = 250 - 180 * (0.0 - minimum) / (maximum - minimum)
    width = 720 / max(1, len(values))
    lines = [
        f'<text x="20" y="24">{escape(title)}</text>',
        f'<line x1="55" y1="{baseline:.2f}" x2="775" y2="{baseline:.2f}" stroke="#555"/>',
    ]
    for index, (label, value) in enumerate(values):
        y = 250 - 180 * (value - minimum) / (maximum - minimum)
        top, height = (y, baseline - y) if value >= 0.0 else (baseline, y - baseline)
        x = 55 + index * width + width * 0.1
        lines.append(
            f'<rect x="{x:.2f}" y="{top:.2f}" width="{width * 0.8:.2f}" height="{height:.2f}" fill="#2474b5"/><title>{escape(label)}={value:.6f} {escape(unit)}</title>'
        )
    lines.append(
        f'<text x="55" y="315">unit={escape(unit)}; zero baseline={baseline:.2f}</text>'
    )
    mapping_lines = _mapping_lines(values)
    lines.extend(_svg_legend(335))
    for index, mapping in enumerate(mapping_lines):
        lines.append(
            f'<text x="55" y="{390 + index * 14}">mapping={escape(mapping)}</text>'
        )
    return _svg(lines, height=405 + len(mapping_lines) * 14)


def _trace_label(scenario: CampaignFScenarioDefinition, strategy: str) -> str:
    prefix = _regime_short(scenario.regime.regime_id)
    strategy_label = _strategy_short(strategy)
    if scenario.scenario_class == "core":
        return f"{prefix}-C{scenario.core_sample_index:02d}-{strategy_label}"
    if scenario.scenario_class == "tail":
        if scenario.tail_case_id is None:
            raise AssertionError("Campaign F tail requires a deterministic tail ID")
        return f"{prefix}-T{scenario.tail_case_id[-2:]}-{strategy_label}"
    return f"{prefix}-A-{strategy_label}"


def _regime_short(regime_id: str) -> str:
    return {"REFERENCE": "R", "HIGH_PV": "HP", "HIGH_EVENING_LOAD": "HEL"}[regime_id]


def _strategy_short(strategy: str) -> str:
    return {"Schedule": "S", "Economic": "E"}[strategy]


def _svg_legend(y: int) -> tuple[str, ...]:
    return (
        f'<text x="55" y="{y}">R=REFERENCE; HP=HIGH_PV; HEL=HIGH_EVENING_LOAD; C=CORE; T=TAIL</text>',
        f'<text x="55" y="{y + 15}">S=Schedule; E=Economic; labels are deterministic caller-order trace keys</text>',
    )


def _mapping_lines(values: tuple[tuple[str, float], ...]) -> tuple[str, ...]:
    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for index, (label, _) in enumerate(values, start=1):
        item = f"{index}:{label}"
        if current and current_length + len(item) + 3 > 120:
            chunks.append(" | ".join(current))
            current = []
            current_length = 0
        current.append(item)
        current_length += len(item) + 3
    if current:
        chunks.append(" | ".join(current))
    return tuple(chunks) or ("none",)


def _bounds(values: tuple[float, ...]) -> tuple[float, float]:
    minimum, maximum = min(values), max(values)
    lower, upper = min(minimum, 0.0), max(maximum, 0.0)
    if math.isclose(lower, upper, abs_tol=NUMERIC_TOLERANCE):
        return lower - 1.0, upper + 1.0
    padding = (upper - lower) * 0.08
    return lower - padding, upper + padding


def _x(value: float, lower: float, upper: float) -> float:
    return 55 + 720 * (value - lower) / (upper - lower)


def _svg(body: list[str], *, height: int = 340) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="{height}" viewBox="0 0 800 {height}">'
        + "".join(body)
        + "</svg>\n"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        result = run_residential_campaign_f(arguments.output_dir)
    except Exception:
        print("FAIL")
        return 1
    print("PASS" if result.hard_passed else "FAIL")
    return 0 if result.hard_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
