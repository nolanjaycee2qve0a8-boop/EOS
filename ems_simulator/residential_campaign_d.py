"""Residential EMS Campaign D: deterministic multi-day continuity validation.

This post-freeze module orchestrates completed frozen 24-hour runners.  It is
not a persistent controller, does not alter a daily runner, and retains each
completed daily trajectory as the only source of actual state and accounting
evidence.
"""

import argparse
import csv
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from io import StringIO
from itertools import pairwise
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
    ResidentialAcceptanceKPI,
    ResidentialAcceptanceResult,
    ResidentialAcceptanceScenario,
    ResidentialAcceptanceSeverity,
    ResidentialAcceptanceStatus,
)
from ems_simulator.residential_campaign_a import (
    ResidentialCampaignScenario,
    _kpi,
    _ledger,
    campaign_scenarios,
)
from optimization import (
    DeterministicExtendedEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    ExtendedEconomicOutcomeEvidence,
    ExtendedEconomicOutcomeInput,
    PVOpportunityWindowConfiguration,
    TerminalEnergyValueEvidence,
    TerminalEnergyValueInput,
)
from simulator import SimulationStepIdentity

_HOURS_PER_DAY = 24
_START = datetime(2026, 1, 1, tzinfo=UTC)
_SOURCE_IDS = (
    "A01_REFERENCE_TASK175",
    "A16_EVENING_PEAK",
    "A10_HIGH_PV",
)
_D04 = (
    "A01_REFERENCE_TASK175",
    "A01_REFERENCE_TASK175",
    "A10_HIGH_PV",
    "A01_REFERENCE_TASK175",
    "A16_EVENING_PEAK",
    "A16_EVENING_PEAK",
    "A10_HIGH_PV",
)


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDCase:
    """One explicit immutable multi-day validation sequence."""

    case_id: str
    duration_class: str
    source_scenario_ids: tuple[str, ...]
    description: str
    initial_soc_fraction: float


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDScenarioDay:
    """Caller-owned source facts and global time identity for one frozen day."""

    case: ResidentialCampaignDCase
    day_index: int
    source_scenario: ResidentialCampaignScenario
    global_start_timestamp: datetime
    global_end_timestamp: datetime
    day_local_description: str

    @property
    def scenario_day_id(self) -> str:
        return f"{self.case.case_id}:D{self.day_index:02d}"


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDDayPathResult:
    """One new frozen daily execution, retained without trajectory reuse."""

    scenario_day: ResidentialCampaignDScenarioDay
    strategy: str
    initial_soc_fraction: float
    trajectory: (
        MultiOpportunityExplainableMPCDailySimulationResult
        | EconomicMultiOpportunityExplainableMPCDailySimulationResult
    )
    ledger: DailyEconomicLedger
    kpi: ResidentialAcceptanceKPI
    acceptance: ResidentialAcceptanceResult

    @property
    def final_actual_soc_fraction(self) -> float:
        return self.trajectory.step_traces[
            -1
        ].simulation_trace.state.battery_result.next_state.soc


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDContinuityEvidence:
    """One exact within-path boundary, based solely on completed Simulator facts."""

    case_id: str
    strategy: str
    day_index: int
    prior_final_actual_soc_fraction: float
    current_initial_soc_fraction: float
    carry_delta: float
    prior_last_timestamp: datetime
    current_first_timestamp: datetime
    timestamp_gap_hours: float
    battery_model_continuous: bool
    strategy_continuous: bool
    export_policy_continuous: bool

    @property
    def passed(self) -> bool:
        return (
            abs(self.carry_delta) <= NUMERIC_TOLERANCE
            and self.timestamp_gap_hours == 1.0
            and self.battery_model_continuous
            and self.strategy_continuous
            and self.export_policy_continuous
        )


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDPathSummary:
    """Campaign-local multi-day aggregate of completed daily facts only."""

    case: ResidentialCampaignDCase
    strategy: str
    days: tuple[ResidentialCampaignDDayPathResult, ...]
    continuity: tuple[ResidentialCampaignDContinuityEvidence, ...]
    final_terminal_evidence: TerminalEnergyValueEvidence
    aggregate_outcome: ExtendedEconomicOutcomeEvidence
    daily_terminal_value_diagnostic_sum: float
    minimum_actual_soc_fraction: float
    maximum_actual_soc_fraction: float
    timestamp_discontinuity_count: int

    @property
    def initial_soc_fraction(self) -> float:
        return self.days[0].initial_soc_fraction

    @property
    def final_actual_soc_fraction(self) -> float:
        return self.days[-1].final_actual_soc_fraction

    @property
    def total_hours(self) -> int:
        return len(self.days) * _HOURS_PER_DAY

    @property
    def total_grid_import_energy_kwh(self) -> float:
        return sum(day.kpi.grid_import_energy_kwh for day in self.days)

    @property
    def total_grid_export_energy_kwh(self) -> float:
        return sum(day.kpi.grid_export_energy_kwh for day in self.days)

    @property
    def total_battery_throughput_kwh(self) -> float:
        return sum(day.kpi.battery_throughput_kwh for day in self.days)

    @property
    def total_physical_revisions(self) -> int:
        return sum(day.kpi.physical_revision_count for day in self.days)

    @property
    def total_headroom_limits(self) -> int:
        return sum(day.kpi.headroom_limit_count for day in self.days)

    @property
    def aggregate_operating_cost(self) -> float:
        outcome = self.aggregate_outcome
        return (
            outcome.realized_import_cost
            - outcome.realized_export_revenue
            + outcome.battery_degradation_cost
        )

    @property
    def hard_passed(self) -> bool:
        return (
            all(_daily_hard_passed(day.acceptance) for day in self.days)
            and all(item.passed for item in self.continuity)
            and self.timestamp_discontinuity_count == 0
            and _aggregate_reconciled(self)
        )


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDCaseResult:
    case: ResidentialCampaignDCase
    schedule: ResidentialCampaignDPathSummary
    economic: ResidentialCampaignDPathSummary
    comparison: EconomicComparisonExplanation


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDFinding:
    """Campaign-local, visible validation observation; it never changes TASK-176."""

    case_id: str
    strategy: str
    day_index: int | None
    category: str
    criterion_id: str
    severity: str
    status: str
    expected: str
    actual: str
    message: str


@dataclass(frozen=True, slots=True)
class ResidentialCampaignDResult:
    cases: tuple[ResidentialCampaignDCase, ...]
    scenario_days: tuple[ResidentialCampaignDScenarioDay, ...]
    case_results: tuple[ResidentialCampaignDCaseResult, ...]
    findings: tuple[ResidentialCampaignDFinding, ...]
    hard_passed: bool
    output_paths: tuple[Path, ...]


def campaign_d_cases() -> tuple[ResidentialCampaignDCase, ...]:
    """Return the exact six caller-owned Campaign D sequences."""

    sources = {item.scenario_id: item for item in campaign_scenarios()}
    initial_soc = sources["A01_REFERENCE_TASK175"].initial_soc_fraction
    d05 = _D04 * 4 + ("A01_REFERENCE_TASK175", "A01_REFERENCE_TASK175")
    cases = (
        ResidentialCampaignDCase(
            "D01_7D_REFERENCE_REPEAT",
            "seven_day",
            ("A01_REFERENCE_TASK175",) * 7,
            "Seven consecutive A01 reference days.",
            initial_soc,
        ),
        ResidentialCampaignDCase(
            "D02_7D_EVENING_REPEAT",
            "seven_day",
            ("A16_EVENING_PEAK",) * 7,
            "Seven consecutive A16 evening-load days.",
            initial_soc,
        ),
        ResidentialCampaignDCase(
            "D03_7D_HIGH_PV_REPEAT",
            "seven_day",
            ("A10_HIGH_PV",) * 7,
            "Seven consecutive A10 high-PV days.",
            initial_soc,
        ),
        ResidentialCampaignDCase(
            "D04_7D_MIXED_WEEK",
            "seven_day",
            _D04,
            "Exact mixed-week source sequence.",
            initial_soc,
        ),
        ResidentialCampaignDCase(
            "D05_30D_REPRESENTATIVE",
            "thirty_day",
            d05,
            "D04 repeated four times plus A01/A01.",
            initial_soc,
        ),
        ResidentialCampaignDCase(
            "D06_30D_BLOCK_STRESS",
            "thirty_day",
            ("A10_HIGH_PV",) * 10
            + ("A16_EVENING_PEAK",) * 10
            + ("A01_REFERENCE_TASK175",) * 10,
            "Ten high-PV, ten evening-load, then ten reference days.",
            initial_soc,
        ),
    )
    if (
        len(cases) != 6
        or sum(len(case.source_scenario_ids) for case in cases) != 88
        or sum(case.duration_class == "seven_day" for case in cases) != 4
        or sum(case.duration_class == "thirty_day" for case in cases) != 2
        or any(
            item not in sources for case in cases for item in case.source_scenario_ids
        )
    ):
        raise AssertionError("Campaign D matrix must remain exactly 4x7 + 2x30")
    return cases


def campaign_d_scenario_days() -> tuple[ResidentialCampaignDScenarioDay, ...]:
    """Expand the exact case sequence without mutating any Campaign A fact."""

    sources = {item.scenario_id: item for item in campaign_scenarios()}
    days: list[ResidentialCampaignDScenarioDay] = []
    global_day = 0
    for case in campaign_d_cases():
        for local_index, source_id in enumerate(case.source_scenario_ids, start=1):
            start = _START + timedelta(days=global_day)
            days.append(
                ResidentialCampaignDScenarioDay(
                    case,
                    local_index,
                    sources[source_id],
                    start,
                    start + timedelta(hours=23),
                    (
                        f"{case.case_id} day {local_index}: "
                        f"{sources[source_id].description}"
                    ),
                )
            )
            global_day += 1
    if len(days) != 88 or len({item.scenario_day_id for item in days}) != 88:
        raise AssertionError(
            "Campaign D must contain exactly 88 explicit scenario-days"
        )
    return tuple(days)


def run_residential_campaign_d(output_directory: Path) -> ResidentialCampaignDResult:
    """Execute the frozen daily runners and report multi-day continuity."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    template = create_demo_input(Path("."))
    evaluator = DeterministicResidentialAcceptanceEvaluator()
    days_by_case: dict[str, list[ResidentialCampaignDScenarioDay]] = defaultdict(list)
    scenario_days = campaign_d_scenario_days()
    for day in scenario_days:
        days_by_case[day.case.case_id].append(day)
    results = tuple(
        _run_case(
            case,
            tuple(days_by_case[case.case_id]),
            template,
            evaluator,
            output_directory,
        )
        for case in campaign_d_cases()
    )
    paths = tuple(
        path
        for result in results
        for summary in (result.schedule, result.economic)
        for path in summary.days
    )
    if len(paths) != 176 or len({id(path.trajectory) for path in paths}) != 176:
        raise AssertionError(
            "Campaign D must execute exactly 176 unique frozen daily paths"
        )
    findings = _findings(results)
    hard_passed = all(
        result.schedule.hard_passed
        and result.economic.hard_passed
        and _comparison_reconciled(result.comparison)
        for result in results
    )
    output_paths = _write_outputs(
        output_directory,
        campaign_d_cases(),
        scenario_days,
        results,
        findings,
        hard_passed,
    )
    return ResidentialCampaignDResult(
        campaign_d_cases(), scenario_days, results, findings, hard_passed, output_paths
    )


def _run_case(
    case: ResidentialCampaignDCase,
    scenario_days: tuple[ResidentialCampaignDScenarioDay, ...],
    template: ExplainableMPCDailySimulationInput,
    evaluator: DeterministicResidentialAcceptanceEvaluator,
    output_directory: Path,
) -> ResidentialCampaignDCaseResult:
    if tuple(day.source_scenario.scenario_id for day in scenario_days) != (
        case.source_scenario_ids
    ):
        raise AssertionError("scenario-day order must preserve the exact case sequence")
    schedule_soc = economic_soc = case.initial_soc_fraction
    schedule_days: list[ResidentialCampaignDDayPathResult] = []
    economic_days: list[ResidentialCampaignDDayPathResult] = []
    for day in scenario_days:
        schedule_input = _daily_input(
            day,
            schedule_soc,
            template,
            output_directory
            / day.case.case_id
            / f"day_{day.day_index:02d}"
            / "schedule",
        )
        economic_input = _daily_input(
            day,
            economic_soc,
            template,
            output_directory
            / day.case.case_id
            / f"day_{day.day_index:02d}"
            / "economic",
        )
        schedule_trajectory = _schedule_runner(
            day.source_scenario.candidate_configuration
        ).run(schedule_input)
        economic_trajectory = _economic_runner(
            day.source_scenario.candidate_configuration
        ).run(economic_input)
        schedule_ledger = _ledger(schedule_trajectory, day.source_scenario)
        economic_ledger = _ledger(economic_trajectory, day.source_scenario)
        comparison = _daily_comparison(day, schedule_ledger, economic_ledger)
        schedule_days.append(
            _day_path(
                day,
                "Schedule",
                schedule_soc,
                schedule_trajectory,
                schedule_ledger,
                comparison,
                evaluator,
            )
        )
        economic_days.append(
            _day_path(
                day,
                "Economic",
                economic_soc,
                economic_trajectory,
                economic_ledger,
                comparison,
                evaluator,
            )
        )
        schedule_soc = schedule_days[-1].final_actual_soc_fraction
        economic_soc = economic_days[-1].final_actual_soc_fraction
    schedule_summary = _path_summary(case, "Schedule", tuple(schedule_days))
    economic_summary = _path_summary(case, "Economic", tuple(economic_days))
    comparison = DeterministicEconomicComparisonExplainer().explain(
        EconomicComparisonInput(
            "Schedule",
            "Economic",
            schedule_summary.aggregate_outcome,
            economic_summary.aggregate_outcome,
            case.case_id,
            (
                "Campaign D aggregate: daily realized components plus final "
                "terminal value once."
            ),
        )
    )
    return ResidentialCampaignDCaseResult(
        case, schedule_summary, economic_summary, comparison
    )


def _daily_input(
    day: ResidentialCampaignDScenarioDay,
    initial_soc: float,
    template: ExplainableMPCDailySimulationInput,
    directory: Path,
) -> MultiOpportunityExplainableMPCDailySimulationInput:
    """Construct one local frozen daily input with caller-owned global timestamps."""

    directory.mkdir(parents=True, exist_ok=True)
    source = day.source_scenario
    integration_template = template.integration_input
    model = source.battery_model
    identities = tuple(
        SimulationStepIdentity(
            index, 3600.0, day.global_start_timestamp + timedelta(hours=index)
        )
        for index in range(_HOURS_PER_DAY)
    )
    daily = DailySimulationScenarioInput(
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
    integration = EMSIntegrationScenarioInput(
        daily,
        integration_template.objective_composition,
        integration_template.capability,
        max(model.max_charge_power_kw, model.max_discharge_power_kw),
        integration_template.export_limit_kw,
        integration_template.initial_grid_power_kw,
    )
    daily_mpc = ExplainableMPCDailySimulationInput(
        integration,
        _finite_horizons(daily),
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        model,
        template.explanation_locale,
        directory / "mpc_decisions.csv",
    )
    return MultiOpportunityExplainableMPCDailySimulationInput(
        daily_mpc,
        source.candidate_configuration,
        PVOpportunityWindowConfiguration(_GAP_TOLERANCE_POINTS),
    )


def _daily_comparison(
    day: ResidentialCampaignDScenarioDay,
    schedule_ledger: DailyEconomicLedger,
    economic_ledger: DailyEconomicLedger,
) -> EconomicComparisonExplanation:
    return DeterministicEconomicComparisonExplainer().explain(
        EconomicComparisonInput(
            "Schedule",
            "Economic",
            schedule_ledger.extended_outcome_evidence,
            economic_ledger.extended_outcome_evidence,
            day.scenario_day_id,
            "Completed daily evidence only.",
        )
    )


def _day_path(
    day: ResidentialCampaignDScenarioDay,
    strategy: str,
    initial_soc: float,
    trajectory: MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    ledger: DailyEconomicLedger,
    comparison: EconomicComparisonExplanation,
    evaluator: DeterministicResidentialAcceptanceEvaluator,
) -> ResidentialCampaignDDayPathResult:
    reconciled = _comparison_reconciled(comparison)
    source_kpi = _kpi(day.source_scenario, strategy, trajectory, ledger, reconciled)
    kpi = replace(source_kpi, scenario_id=day.scenario_day_id)
    acceptance = evaluator.evaluate(
        ResidentialAcceptanceScenario(
            day.scenario_day_id,
            f"{day.scenario_day_id} / {strategy}",
            day.source_scenario.export_policy,
            day.day_local_description,
        ),
        kpi,
    )
    if len(trajectory.step_traces) != _HOURS_PER_DAY:
        raise AssertionError(
            "each Campaign D frozen run must contain exactly 24 traces"
        )
    return ResidentialCampaignDDayPathResult(
        day, strategy, initial_soc, trajectory, ledger, kpi, acceptance
    )


def _path_summary(
    case: ResidentialCampaignDCase,
    strategy: str,
    days: tuple[ResidentialCampaignDDayPathResult, ...],
) -> ResidentialCampaignDPathSummary:
    continuity = _continuity(case, strategy, days)
    final_day = days[-1]
    terminal = DeterministicTerminalEnergyValueCalculator().calculate(
        TerminalEnergyValueInput(
            final_day.final_actual_soc_fraction,
            final_day.scenario_day.source_scenario.battery_model,
            final_day.scenario_day.source_scenario.terminal_valuation_per_kwh,
        )
    )
    import_cost = sum(day.ledger.total_realized_import_cost for day in days)
    export_revenue = sum(day.ledger.total_realized_export_revenue for day in days)
    degradation = sum(day.ledger.total_battery_degradation_cost for day in days)
    outcome = DeterministicExtendedEconomicOutcomeCalculator().calculate(
        ExtendedEconomicOutcomeInput(import_cost, export_revenue, degradation, terminal)
    )
    actual_socs = tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for day in days
        for trace in day.trajectory.step_traces
    )
    timestamps = tuple(
        trace.simulation_trace.simulation_input.step_identity.timestamp
        for day in days
        for trace in day.trajectory.step_traces
    )
    if any(timestamp is None for timestamp in timestamps):
        raise AssertionError("Campaign D requires timezone-aware Simulator timestamps")
    typed_timestamps = tuple(
        timestamp for timestamp in timestamps if timestamp is not None
    )
    discontinuities = sum(
        following != prior + timedelta(hours=1)
        for prior, following in pairwise(typed_timestamps)
    )
    return ResidentialCampaignDPathSummary(
        case,
        strategy,
        days,
        continuity,
        terminal,
        outcome,
        sum(day.ledger.terminal_energy_value for day in days),
        min(actual_socs),
        max(actual_socs),
        discontinuities,
    )


def _continuity(
    case: ResidentialCampaignDCase,
    strategy: str,
    days: tuple[ResidentialCampaignDDayPathResult, ...],
) -> tuple[ResidentialCampaignDContinuityEvidence, ...]:
    evidence: list[ResidentialCampaignDContinuityEvidence] = []
    for prior, current in pairwise(days):
        prior_trace = prior.trajectory.step_traces[-1]
        current_trace = current.trajectory.step_traces[0]
        prior_timestamp = (
            prior_trace.simulation_trace.simulation_input.step_identity.timestamp
        )
        current_timestamp = (
            current_trace.simulation_trace.simulation_input.step_identity.timestamp
        )
        if prior_timestamp is None or current_timestamp is None:
            raise AssertionError("Campaign D timestamps must be explicit")
        evidence.append(
            ResidentialCampaignDContinuityEvidence(
                case.case_id,
                strategy,
                current.scenario_day.day_index,
                prior.final_actual_soc_fraction,
                current.initial_soc_fraction,
                current.initial_soc_fraction - prior.final_actual_soc_fraction,
                prior_timestamp,
                current_timestamp,
                (current_timestamp - prior_timestamp).total_seconds() / 3600.0,
                current.scenario_day.source_scenario.battery_model
                is prior.scenario_day.source_scenario.battery_model,
                current.trajectory.source_input.daily_mpc_input.source_strategy
                is prior.trajectory.source_input.daily_mpc_input.source_strategy,
                current.scenario_day.source_scenario.export_policy
                == prior.scenario_day.source_scenario.export_policy,
            )
        )
    return tuple(evidence)


def _aggregate_reconciled(summary: ResidentialCampaignDPathSummary) -> bool:
    outcome = summary.aggregate_outcome
    return isclose(
        outcome.adjusted_net_economic_cost,
        outcome.realized_import_cost
        - outcome.realized_export_revenue
        + outcome.battery_degradation_cost
        - summary.final_terminal_evidence.terminal_energy_value,
        rel_tol=0.0,
        abs_tol=NUMERIC_TOLERANCE,
    )


def _comparison_reconciled(comparison: EconomicComparisonExplanation) -> bool:
    return isclose(
        comparison.delta_adjusted_cost,
        comparison.import_cost_contribution
        + comparison.export_revenue_contribution
        + comparison.degradation_cost_contribution
        + comparison.terminal_value_contribution,
        rel_tol=0.0,
        abs_tol=NUMERIC_TOLERANCE,
    )


def _daily_hard_passed(acceptance: ResidentialAcceptanceResult) -> bool:
    return not any(
        item.status is ResidentialAcceptanceStatus.FAIL
        and item.severity
        in {ResidentialAcceptanceSeverity.BLOCKER, ResidentialAcceptanceSeverity.MAJOR}
        for item in acceptance.findings
    )


def _findings(
    results: tuple[ResidentialCampaignDCaseResult, ...],
) -> tuple[ResidentialCampaignDFinding, ...]:
    values: list[ResidentialCampaignDFinding] = []
    for result in results:
        for summary in (result.schedule, result.economic):
            for day in summary.days:
                values.extend(_frozen_findings(day))
            for item in summary.continuity:
                values.append(
                    _campaign_finding(
                        result.case.case_id,
                        summary.strategy,
                        item.day_index,
                        "continuity",
                        "soc_carry_and_timestamp",
                        item.passed,
                        "carry delta 0; timestamp gap 1h; stable model/strategy/policy",
                        (
                            f"carry_delta={item.carry_delta:.12f}; "
                            f"gap_hours={item.timestamp_gap_hours:.6f}"
                        ),
                    )
                )
            values.append(
                _campaign_finding(
                    result.case.case_id,
                    summary.strategy,
                    None,
                    "accounting",
                    "aggregate_terminal_once",
                    _aggregate_reconciled(summary),
                    "aggregate import - export + degradation - final terminal",
                    (
                        "daily_terminal_diagnostic_sum="
                        f"{summary.daily_terminal_value_diagnostic_sum:.6f}; "
                        "final_terminal="
                        f"{summary.final_terminal_evidence.terminal_energy_value:.6f}"
                    ),
                )
            )
        values.append(
            _campaign_finding(
                result.case.case_id,
                "Comparison",
                None,
                "accounting",
                "aggregate_comparison_reconciliation",
                _comparison_reconciled(result.comparison),
                "delta equals signed components",
                f"delta={result.comparison.delta_adjusted_cost:.12f}",
            )
        )
    return tuple(values)


def _frozen_findings(
    day: ResidentialCampaignDDayPathResult,
) -> tuple[ResidentialCampaignDFinding, ...]:
    return tuple(
        ResidentialCampaignDFinding(
            day.scenario_day.case.case_id,
            day.strategy,
            day.scenario_day.day_index,
            finding.category.value,
            finding.criterion_id,
            finding.severity.value,
            finding.status.value,
            finding.expected,
            finding.actual,
            finding.message,
        )
        for finding in day.acceptance.findings
    )


def _campaign_finding(
    case_id: str,
    strategy: str,
    day_index: int | None,
    category: str,
    criterion: str,
    passed: bool,
    expected: str,
    actual: str,
) -> ResidentialCampaignDFinding:
    return ResidentialCampaignDFinding(
        case_id,
        strategy,
        day_index,
        category,
        criterion,
        "blocker",
        "pass" if passed else "fail",
        expected,
        actual,
        "Campaign D local validation; frozen TASK-176 semantics are unchanged.",
    )


def _write_outputs(
    output: Path,
    cases: tuple[ResidentialCampaignDCase, ...],
    days: tuple[ResidentialCampaignDScenarioDay, ...],
    results: tuple[ResidentialCampaignDCaseResult, ...],
    findings: tuple[ResidentialCampaignDFinding, ...],
    hard_passed: bool,
) -> tuple[Path, ...]:
    contents = {
        "campaign_d_cases.csv": _cases_csv(cases),
        "campaign_d_scenario_days.csv": _scenario_days_csv(days),
        "campaign_d_day_results.csv": _day_results_csv(results),
        "campaign_d_continuity.csv": _continuity_csv(results),
        "campaign_d_path_summaries.csv": _summaries_csv(results),
        "campaign_d_comparisons.csv": _comparisons_csv(results),
        "campaign_d_findings.csv": _findings_csv(findings),
        "campaign_d_summary.txt": _summary(results, findings, hard_passed),
    }
    paths: list[Path] = []
    for name, text in contents.items():
        path = output / name
        path.write_text(text, encoding="utf-8", newline="")
        paths.append(path)
    charts = _charts(results)
    for name, text in charts.items():
        path = output / name
        path.write_text(text, encoding="utf-8", newline="")
        paths.append(path)
    return tuple(paths)


def _csv(rows: Iterable[Iterable[object]]) -> str:
    stream = StringIO(newline="")
    csv.writer(stream, lineterminator="\n").writerows(rows)
    return stream.getvalue()


def _cases_csv(cases: Iterable[ResidentialCampaignDCase]) -> str:
    return _csv(
        (
            (
                "case_id",
                "duration_class",
                "day_count",
                "initial_soc_fraction",
                "source_sequence",
                "description",
            ),
            *(
                (
                    case.case_id,
                    case.duration_class,
                    len(case.source_scenario_ids),
                    _number(case.initial_soc_fraction),
                    "|".join(case.source_scenario_ids),
                    case.description,
                )
                for case in cases
            ),
        )
    )


def _scenario_days_csv(days: Iterable[ResidentialCampaignDScenarioDay]) -> str:
    header = (
        "case_id",
        "duration_class",
        "day_index",
        "source_scenario_id",
        "day_local_description",
        "global_start_timestamp",
        "global_end_timestamp",
        "realized_pv_profile_kw",
        "realized_load_profile_kw",
        "realized_tariff_profile",
        "forecast_semantics",
        "export_tariff",
        "battery_model",
        "optimization_configuration",
        "degradation_cost",
        "terminal_valuation",
        "export_policy",
    )
    return _csv(
        (
            header,
            *(
                (
                    day.case.case_id,
                    day.case.duration_class,
                    day.day_index,
                    day.source_scenario.scenario_id,
                    day.day_local_description,
                    day.global_start_timestamp.isoformat(),
                    day.global_end_timestamp.isoformat(),
                    _profile(day.source_scenario.pv_profile_kw),
                    _profile(day.source_scenario.load_profile_kw),
                    _profile(day.source_scenario.import_tariff_profile_per_kwh),
                    day.source_scenario.forecast_semantics,
                    _number(day.source_scenario.export_tariff_per_kwh),
                    str(day.source_scenario.battery_model),
                    str(day.source_scenario.candidate_configuration),
                    _number(day.source_scenario.degradation_cost_per_throughput_kwh),
                    _number(day.source_scenario.terminal_valuation_per_kwh),
                    day.source_scenario.export_policy,
                )
                for day in days
            ),
        )
    )


def _day_results_csv(results: Iterable[ResidentialCampaignDCaseResult]) -> str:
    header = (
        "case_id",
        "strategy",
        "day_index",
        "source_scenario_id",
        "initial_soc",
        "final_actual_soc",
        "carry_delta",
        "first_timestamp",
        "last_timestamp",
        "grid_import_kwh",
        "grid_export_kwh",
        "battery_throughput_kwh",
        "import_cost",
        "export_revenue",
        "degradation_cost",
        "daily_terminal_value",
        "daily_adjusted_cost",
        "physical_revisions",
        "headroom_limits",
        "min_soc_violations",
        "max_soc_violations",
        "charge_power_violations",
        "discharge_power_violations",
        "energy_balance_violations",
        "ledger_reconciled",
        "comparison_reconciled",
        "provenance_complete",
        "explanation_complete",
        "acceptance_status",
    )
    rows: list[tuple[object, ...]] = [header]
    for result in results:
        for summary in (result.schedule, result.economic):
            prior = None
            for day in summary.days:
                trace = day.trajectory.step_traces
                first_timestamp = trace[
                    0
                ].simulation_trace.simulation_input.step_identity.timestamp
                last_timestamp = trace[
                    -1
                ].simulation_trace.simulation_input.step_identity.timestamp
                if first_timestamp is None or last_timestamp is None:
                    raise AssertionError("Campaign D requires explicit timestamps")
                carry = (
                    0.0
                    if prior is None
                    else day.initial_soc_fraction - prior.final_actual_soc_fraction
                )
                kpi = day.kpi
                rows.append(
                    (
                        result.case.case_id,
                        summary.strategy,
                        day.scenario_day.day_index,
                        day.scenario_day.source_scenario.scenario_id,
                        _number(day.initial_soc_fraction),
                        _number(day.final_actual_soc_fraction),
                        _number(carry),
                        first_timestamp.isoformat(),
                        last_timestamp.isoformat(),
                        _number(kpi.grid_import_energy_kwh),
                        _number(kpi.grid_export_energy_kwh),
                        _number(kpi.battery_throughput_kwh),
                        _number(kpi.import_cost),
                        _number(kpi.export_revenue),
                        _number(kpi.degradation_cost),
                        _number(kpi.terminal_value),
                        _number(kpi.adjusted_net_economic_cost),
                        kpi.physical_revision_count,
                        kpi.headroom_limit_count,
                        kpi.min_soc_violation_count,
                        kpi.max_soc_violation_count,
                        kpi.charge_power_violation_count,
                        kpi.discharge_power_violation_count,
                        kpi.energy_balance_violation_count,
                        str(kpi.ledger_reconciled).lower(),
                        str(kpi.comparison_reconciled).lower(),
                        str(kpi.provenance_complete).lower(),
                        str(kpi.missing_explanation_count == 0).lower(),
                        "pass" if day.acceptance.passed else "fail",
                    )
                )
                prior = day
    return _csv(rows)


def _continuity_csv(results: Iterable[ResidentialCampaignDCaseResult]) -> str:
    header = (
        "case_id",
        "strategy",
        "day_index",
        "prior_final_actual_soc",
        "current_initial_soc",
        "carry_delta",
        "prior_last_timestamp",
        "current_first_timestamp",
        "timestamp_gap_hours",
        "battery_model_continuous",
        "strategy_continuous",
        "export_policy_continuous",
        "passed",
    )
    return _csv(
        (
            header,
            *(
                (
                    item.case_id,
                    item.strategy,
                    item.day_index,
                    _number(item.prior_final_actual_soc_fraction),
                    _number(item.current_initial_soc_fraction),
                    _number(item.carry_delta),
                    item.prior_last_timestamp.isoformat(),
                    item.current_first_timestamp.isoformat(),
                    _number(item.timestamp_gap_hours),
                    str(item.battery_model_continuous).lower(),
                    str(item.strategy_continuous).lower(),
                    str(item.export_policy_continuous).lower(),
                    str(item.passed).lower(),
                )
                for result in results
                for summary in (result.schedule, result.economic)
                for item in summary.continuity
            ),
        )
    )


def _summaries_csv(results: Iterable[ResidentialCampaignDCaseResult]) -> str:
    header = (
        "case_id",
        "strategy",
        "days",
        "total_hours",
        "initial_soc",
        "final_actual_soc",
        "minimum_actual_soc",
        "maximum_actual_soc",
        "day_boundaries",
        "max_abs_carry_delta",
        "timestamp_discontinuities",
        "grid_import_kwh",
        "grid_export_kwh",
        "battery_throughput_kwh",
        "physical_revisions",
        "headroom_limits",
        "days_ending_min_soc",
        "days_ending_max_soc",
        "aggregate_import_cost",
        "aggregate_export_revenue",
        "aggregate_degradation_cost",
        "aggregate_operating_cost",
        "final_terminal_value",
        "daily_terminal_diagnostic_sum",
        "aggregate_adjusted_cost",
        "hard_status",
    )
    rows: list[tuple[object, ...]] = [header]
    for result in results:
        for summary in (result.schedule, result.economic):
            model = summary.days[-1].scenario_day.source_scenario.battery_model
            outcome = summary.aggregate_outcome
            rows.append(
                (
                    result.case.case_id,
                    summary.strategy,
                    len(summary.days),
                    summary.total_hours,
                    _number(summary.initial_soc_fraction),
                    _number(summary.final_actual_soc_fraction),
                    _number(summary.minimum_actual_soc_fraction),
                    _number(summary.maximum_actual_soc_fraction),
                    len(summary.continuity),
                    _number(
                        max(
                            (abs(item.carry_delta) for item in summary.continuity),
                            default=0.0,
                        )
                    ),
                    summary.timestamp_discontinuity_count,
                    _number(summary.total_grid_import_energy_kwh),
                    _number(summary.total_grid_export_energy_kwh),
                    _number(summary.total_battery_throughput_kwh),
                    summary.total_physical_revisions,
                    summary.total_headroom_limits,
                    sum(
                        isclose(
                            day.final_actual_soc_fraction,
                            model.min_soc_fraction,
                            abs_tol=NUMERIC_TOLERANCE,
                        )
                        for day in summary.days
                    ),
                    sum(
                        isclose(
                            day.final_actual_soc_fraction,
                            model.max_soc_fraction,
                            abs_tol=NUMERIC_TOLERANCE,
                        )
                        for day in summary.days
                    ),
                    _number(outcome.realized_import_cost),
                    _number(outcome.realized_export_revenue),
                    _number(outcome.battery_degradation_cost),
                    _number(summary.aggregate_operating_cost),
                    _number(summary.final_terminal_evidence.terminal_energy_value),
                    _number(summary.daily_terminal_value_diagnostic_sum),
                    _number(outcome.adjusted_net_economic_cost),
                    "pass" if summary.hard_passed else "fail",
                )
            )
    return _csv(rows)


def _comparisons_csv(results: Iterable[ResidentialCampaignDCaseResult]) -> str:
    header = (
        "case_id",
        "schedule_import_cost",
        "economic_import_cost",
        "import_cost_delta",
        "schedule_export_revenue",
        "economic_export_revenue",
        "export_revenue_contribution",
        "schedule_degradation_cost",
        "economic_degradation_cost",
        "degradation_contribution",
        "schedule_final_terminal_value",
        "economic_final_terminal_value",
        "terminal_value_contribution",
        "schedule_adjusted_cost",
        "economic_adjusted_cost",
        "economic_minus_schedule_adjusted_cost",
        "ranking",
        "dominant_components",
        "reconciled",
    )
    return _csv(
        (
            header,
            *(
                (
                    result.case.case_id,
                    _number(result.comparison.reference_realized_import_cost),
                    _number(result.comparison.candidate_realized_import_cost),
                    _number(result.comparison.delta_import_cost),
                    _number(result.comparison.reference_realized_export_revenue),
                    _number(result.comparison.candidate_realized_export_revenue),
                    _number(result.comparison.export_revenue_contribution),
                    _number(result.comparison.reference_battery_degradation_cost),
                    _number(result.comparison.candidate_battery_degradation_cost),
                    _number(result.comparison.degradation_cost_contribution),
                    _number(result.comparison.reference_terminal_energy_value),
                    _number(result.comparison.candidate_terminal_energy_value),
                    _number(result.comparison.terminal_value_contribution),
                    _number(result.comparison.reference_adjusted_net_economic_cost),
                    _number(result.comparison.candidate_adjusted_net_economic_cost),
                    _number(result.comparison.delta_adjusted_cost),
                    result.comparison.ranking.value,
                    "|".join(
                        item.value for item in result.comparison.dominant_components
                    ),
                    str(_comparison_reconciled(result.comparison)).lower(),
                )
                for result in results
            ),
        )
    )


def _findings_csv(findings: Iterable[ResidentialCampaignDFinding]) -> str:
    return _csv(
        (
            (
                "case_id",
                "strategy",
                "day_index",
                "category",
                "criterion_id",
                "severity",
                "status",
                "expected",
                "actual",
                "message",
            ),
            *(
                (
                    item.case_id,
                    item.strategy,
                    "" if item.day_index is None else item.day_index,
                    item.category,
                    item.criterion_id,
                    item.severity,
                    item.status,
                    item.expected,
                    item.actual,
                    item.message,
                )
                for item in findings
            ),
        )
    )


def _summary(
    results: tuple[ResidentialCampaignDCaseResult, ...],
    findings: tuple[ResidentialCampaignDFinding, ...],
    hard_passed: bool,
) -> str:
    summaries = tuple(
        summary for result in results for summary in (result.schedule, result.economic)
    )
    failures = Counter(item.severity for item in findings if item.status == "fail")
    rankings = Counter(result.comparison.ranking for result in results)
    largest_difference = max(
        results, key=lambda item: abs(item.comparison.delta_adjusted_cost)
    )
    highest_revisions = max(summaries, key=lambda item: item.total_physical_revisions)
    largest_range = max(
        summaries,
        key=lambda item: (
            item.maximum_actual_soc_fraction - item.minimum_actual_soc_fraction
        ),
    )
    boundaries = tuple(
        summary
        for summary in summaries
        if isclose(
            summary.final_actual_soc_fraction,
            summary.days[
                -1
            ].scenario_day.source_scenario.battery_model.min_soc_fraction,
            abs_tol=NUMERIC_TOLERANCE,
        )
        or isclose(
            summary.final_actual_soc_fraction,
            summary.days[
                -1
            ].scenario_day.source_scenario.battery_model.max_soc_fraction,
            abs_tol=NUMERIC_TOLERANCE,
        )
    )
    maximum_carry_delta = max(
        (abs(item.carry_delta) for summary in summaries for item in summary.continuity),
        default=0.0,
    )
    continuity_passed = all(
        item.passed for summary in summaries for item in summary.continuity
    )
    aggregate_reconciled = all(_aggregate_reconciled(summary) for summary in summaries)
    economic_wins = rankings[EconomicComparisonRanking.CANDIDATE_BETTER]
    schedule_wins = rankings[EconomicComparisonRanking.REFERENCE_BETTER]
    ties = rankings[EconomicComparisonRanking.TIED]
    largest_soc_range = (
        largest_range.maximum_actual_soc_fraction
        - largest_range.minimum_actual_soc_fraction
    )
    return "\n".join(
        (
            "EOS Residential EMS 1.0 Campaign D - Deterministic Multi-Day Continuity",
            (
                "functional_freeze=validation/reporting orchestration only; "
                "no production multi-day controller or frozen behavior changed."
            ),
            (
                "forecast_scope=perfect caller-supplied forecast equals realized "
                "daily facts; Campaign D does not test multi-day forecast uncertainty."
            ),
            (
                "matrix=6 cases; 4 seven-day; 2 thirty-day; 88 scenario-days; "
                "12 logical paths; 176 actual frozen daily executions; 0 reuse; "
                "0 accounting-only paths."
            ),
            f"campaign_hard_status={'PASS' if hard_passed else 'FAIL'}",
            (
                f"blocker_count={failures['blocker']} "
                f"major_count={failures['major']} minor_count={failures['minor']} "
                f"informational_count={failures['informational']}"
            ),
            (
                f"continuity_status={'PASS' if continuity_passed else 'FAIL'}; "
                "maximum_absolute_carry_delta="
                f"{_number(maximum_carry_delta)}"
            ),
            (f"aggregate_reconciliation={'PASS' if aggregate_reconciled else 'FAIL'}"),
            (
                "terminal_value_once="
                f"{'PASS' if aggregate_reconciled else 'FAIL'}; "
                "daily terminal values remain diagnostic; final actual SOC "
                "terminal value is applied once per multi-day path."
            ),
            (
                f"economic_wins={economic_wins} schedule_wins={schedule_wins} "
                f"ties={ties}"
            ),
            (
                "largest_schedule_economic_difference="
                f"{largest_difference.case.case_id}:"
                f"{_number(largest_difference.comparison.delta_adjusted_cost)}"
            ),
            (
                "highest_cumulative_physical_revisions="
                f"{highest_revisions.case.case_id}/{highest_revisions.strategy}:"
                f"{highest_revisions.total_physical_revisions}"
            ),
            (
                "largest_actual_soc_range="
                f"{largest_range.case.case_id}/{largest_range.strategy}:"
                f"{_number(largest_soc_range)}"
            ),
            "soc_boundary_endings="
            + (
                "|".join(f"{item.case.case_id}/{item.strategy}" for item in boundaries)
                if boundaries
                else "none"
            ),
            (
                "interpretation=deterministic perfect-forecast composition evidence "
                "only; not probability, hardware, PCS certification, field/customer "
                "readiness, restart recovery, real-time scheduling, or global "
                "multi-day optimality."
            ),
            (
                "future_handoff=combine multi-day continuity with forecast "
                "uncertainty only under separately approved scope."
            ),
            "",
        )
    )


def _charts(results: tuple[ResidentialCampaignDCaseResult, ...]) -> dict[str, str]:
    by_case = {item.case.case_id: item for item in results}
    return {
        "soc_7d_mixed_week.svg": _soc_svg(
            "D04 hourly actual SOC",
            (
                by_case["D04_7D_MIXED_WEEK"].schedule,
                by_case["D04_7D_MIXED_WEEK"].economic,
            ),
        ),
        "soc_30d_representative.svg": _soc_svg(
            "D05 hourly actual SOC",
            (
                by_case["D05_30D_REPRESENTATIVE"].schedule,
                by_case["D05_30D_REPRESENTATIVE"].economic,
            ),
        ),
        "soc_30d_block_stress.svg": _soc_svg(
            "D06 hourly actual SOC",
            (
                by_case["D06_30D_BLOCK_STRESS"].schedule,
                by_case["D06_30D_BLOCK_STRESS"].economic,
            ),
        ),
        "carry_continuity.svg": _bar_svg(
            "SOC carry delta",
            "SOC fraction",
            tuple(
                (
                    f"{item.case_id}|{item.strategy}|day={item.day_index}",
                    item.carry_delta,
                )
                for result in results
                for summary in (result.schedule, result.economic)
                for item in summary.continuity
            ),
            "actual day-start minus previous actual final",
        ),
        "cumulative_operating_cost.svg": _daily_series_svg(
            "Cumulative operating cost",
            "CNY",
            results,
            lambda day: (
                day.ledger.total_realized_import_cost
                - day.ledger.total_realized_export_revenue
                + day.ledger.total_battery_degradation_cost
            ),
            cumulative=True,
        ),
        "daily_grid_import_export.svg": _daily_grid_svg(results),
        "cumulative_physical_revisions.svg": _daily_series_svg(
            "Cumulative physical revisions",
            "count",
            results,
            lambda day: float(day.kpi.physical_revision_count),
            cumulative=True,
        ),
        "aggregate_adjusted_cost_comparison.svg": _bar_svg(
            "Schedule/Economic aggregate adjusted cost",
            "CNY",
            tuple(
                (
                    f"{result.case.case_id}|Schedule",
                    result.schedule.aggregate_outcome.adjusted_net_economic_cost,
                )
                for result in results
            )
            + tuple(
                (
                    f"{result.case.case_id}|Economic",
                    result.economic.aggregate_outcome.adjusted_net_economic_cost,
                )
                for result in results
            ),
            "daily operating components plus final terminal value once",
        ),
    }


def _soc_svg(
    title: str,
    summaries: tuple[ResidentialCampaignDPathSummary, ResidentialCampaignDPathSummary],
) -> str:
    series = tuple(
        (
            f"{summary.case.case_id}|{summary.strategy}",
            tuple(
                trace.simulation_trace.state.battery_result.next_state.soc
                for day in summary.days
                for trace in day.trajectory.step_traces
            ),
        )
        for summary in summaries
    )
    return _line_svg(
        title,
        "SOC fraction",
        series,
        (
            "hourly actual Simulator next-state SOC; all points retained; "
            "x-axis cadence=24 hours"
        ),
    )


def _daily_series_svg(
    title: str,
    unit: str,
    results: tuple[ResidentialCampaignDCaseResult, ...],
    value: Callable[[ResidentialCampaignDDayPathResult], float],
    *,
    cumulative: bool,
) -> str:
    series = []
    for result in results:
        for summary in (result.schedule, result.economic):
            total = 0.0
            values = []
            for day in summary.days:
                daily_value = value(day)
                total += daily_value
                values.append(total if cumulative else daily_value)
            series.append((f"{result.case.case_id}|{summary.strategy}", tuple(values)))
    return _line_svg(
        title, unit, tuple(series), "all daily points retained; x-axis cadence=1 day"
    )


def _daily_grid_svg(results: tuple[ResidentialCampaignDCaseResult, ...]) -> str:
    points = tuple(
        (
            f"{result.case.case_id}|{summary.strategy}|day={day.scenario_day.day_index}|import",
            day.kpi.grid_import_energy_kwh,
        )
        for result in results
        for summary in (result.schedule, result.economic)
        for day in summary.days
    ) + tuple(
        (
            f"{result.case.case_id}|{summary.strategy}|day={day.scenario_day.day_index}|export",
            -day.kpi.grid_export_energy_kwh,
        )
        for result in results
        for summary in (result.schedule, result.economic)
        for day in summary.days
    )
    return _bar_svg(
        "Daily grid import (+) / export (-)",
        "kWh",
        points,
        "all scenario-day grid values retained",
    )


def _line_svg(
    title: str, unit: str, series: tuple[tuple[str, tuple[float, ...]], ...], note: str
) -> str:
    values = tuple(value for _, points in series for value in points) or (0.0,)
    lower, upper = min(0.0, min(values)), max(1.0, max(values))
    scale = max(upper - lower, 1.0)
    baseline = 250 - (0.0 - lower) / scale * 190
    colors = ("#2563eb", "#dc2626", "#059669", "#7c3aed", "#d97706", "#0891b2")
    polylines: list[str] = []
    labels: list[str] = []
    for index, (label, points) in enumerate(series):
        width = max(len(points) - 1, 1)
        coordinates = " ".join(
            _coordinate(point_index, value, width, lower, scale)
            for point_index, value in enumerate(points)
        )
        color = colors[index % len(colors)]
        polylines.append(
            "<polyline "
            f'data-label="{_xml_attribute(label)}" points="{coordinates}" '
            f'fill="none" stroke="{color}" stroke-width="1.2"/>'
        )
        labels.append(
            "<text "
            f'x="{55 + (index % 3) * 300}" y="{300 + index // 3 * 15}" '
            'font-family="sans-serif" font-size="10" '
            f'fill="{color}">{escape(label)}</text>'
        )
    return "".join(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="420" ',
            'viewBox="0 0 1024 420">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<text x="40" y="25" font-family="sans-serif" font-size="16">',
            f"{escape(title)} ({escape(unit)})</text>",
            f'<line id="zero-axis" x1="40" y1="{baseline:.2f}" ',
            f'x2="990" y2="{baseline:.2f}" stroke="#64748b"/>',
            "".join(polylines),
            '<text x="40" y="285" font-family="sans-serif" font-size="10">',
            f"{escape(note)}; unit={escape(unit)}</text>",
            "".join(labels),
            "</svg>\n",
        )
    )


def _bar_svg(
    title: str, unit: str, points: tuple[tuple[str, float], ...], note: str
) -> str:
    visible = points or (("no data", 0.0),)
    values = tuple(value for _, value in visible)
    upper, lower = max(1.0, max(values)), min(0.0, min(values))
    scale = max(upper - lower, 1.0)
    baseline = 250 - (0.0 - lower) / scale * 190
    width = min(16.0, 920.0 / len(visible))
    bars = "".join(
        _bar_rect(label, value, index, width, lower, scale, baseline)
        for index, (label, value) in enumerate(visible)
    )
    labels = "".join(
        _bar_label(label, index, width) for index, (label, _) in enumerate(visible)
    )
    return "".join(
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="420" ',
            'viewBox="0 0 1024 420">',
            '<rect width="100%" height="100%" fill="white"/>',
            '<text x="40" y="25" font-family="sans-serif" font-size="16">',
            f"{escape(title)} ({escape(unit)})</text>",
            f'<line id="zero-axis" x1="40" y1="{baseline:.2f}" ',
            f'x2="990" y2="{baseline:.2f}" stroke="#64748b"/>',
            bars,
            labels,
            '<text x="40" y="365" font-family="sans-serif" font-size="10">',
            f"{escape(note)}; unit={escape(unit)}</text></svg>\n",
        )
    )


def _coordinate(
    point_index: int, value: float, width: int, lower: float, scale: float
) -> str:
    x = 50 + point_index * 920 / width
    y = 250 - (value - lower) / scale * 190
    return f"{x:.2f},{y:.2f}"


def _bar_rect(
    label: str,
    value: float,
    index: int,
    width: float,
    lower: float,
    scale: float,
    baseline: float,
) -> str:
    value_y = 250 - (value - lower) / scale * 190
    return "".join(
        (
            "<rect ",
            f'data-label="{_xml_attribute(label)}" ',
            f'x="{50 + index * width:.2f}" ',
            f'y="{min(baseline, value_y):.2f}" ',
            f'width="{max(width - 1, 1):.2f}" ',
            f'height="{abs(baseline - value_y):.2f}" fill="#2563eb"/>',
        )
    )


def _bar_label(label: str, index: int, width: float) -> str:
    x = 50 + index * width + width / 2
    return "".join(
        (
            "<text ",
            f'x="{x:.2f}" y="280" font-family="sans-serif" ',
            'font-size="5" text-anchor="end" ',
            f'transform="rotate(-55 {x:.2f} 280)">{escape(label)}</text>',
        )
    )


def _xml_attribute(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _profile(values: tuple[float, ...]) -> str:
    return "|".join(_number(value) for value in values)


def _number(value: float) -> str:
    return f"{value:.6f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EOS Residential EMS Campaign D")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("simulation_output_campaign_d")
    )
    arguments = parser.parse_args(argv)
    result = run_residential_campaign_d(arguments.output_dir)
    for path in result.output_paths:
        print(path)
    print("PASS" if result.hard_passed else "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
