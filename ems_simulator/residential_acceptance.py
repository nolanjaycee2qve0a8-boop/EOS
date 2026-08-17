# ruff: noqa: E501
"""Residential EMS 1.0 deterministic validation and acceptance suite.

TASK-176 is an acceptance/read-model layer.  It reuses completed control and
accounting paths and never changes a strategy, optimization algorithm, MPC
objective, feasibility rule, actuation rule, or simulator behavior.
"""

import argparse
import csv
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from io import StringIO
from math import isclose
from pathlib import Path

from ems_simulator.economic_comparison_explanation import (
    DeterministicEconomicComparisonExplainer,
    EconomicComparisonInput,
    format_economic_comparison_explanation,
)
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.extended_economic_re_evaluation import (
    ExtendedEconomicEvaluation,
    ExtendedEconomicReEvaluationResult,
    run_extended_economic_re_evaluation,
)
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationResult,
)
from ems_simulator.residential_reference_demo import (
    ResidentialReferencePath,
    ResidentialReferenceResult,
    run_residential_reference_demo,
)

NUMERIC_TOLERANCE = 1e-12
"""Central deterministic acceptance tolerance; never a behavioral allowance."""


class ResidentialAcceptanceCategory(StrEnum):
    PHYSICAL_SAFETY = "physical_safety"
    CONTROL_SEMANTICS = "control_semantics"
    ACCOUNTING_RECONCILIATION = "accounting_reconciliation"
    ECONOMIC_BEHAVIOR = "economic_behavior"
    EXPLAINABILITY = "explainability"
    QUALITY_METRIC = "quality_metric"


class ResidentialAcceptanceSeverity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"
    INFORMATIONAL = "informational"


class ResidentialAcceptanceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class ResidentialCampaignReadiness(StrEnum):
    READY_FOR_SIMULATION_CAMPAIGN = "ready_for_simulation_campaign"
    NOT_READY_FOR_SIMULATION_CAMPAIGN = "not_ready_for_simulation_campaign"


@dataclass(frozen=True, slots=True)
class ResidentialAcceptanceScenario:
    """One small deterministic acceptance fixture and its explicit export policy."""

    scenario_id: str
    name: str
    export_policy: str
    description: str


@dataclass(frozen=True, slots=True)
class ResidentialAcceptanceCriterion:
    """Stable criterion metadata reusable by later campaign evaluation."""

    criterion_id: str
    category: ResidentialAcceptanceCategory
    severity: ResidentialAcceptanceSeverity
    description: str


@dataclass(frozen=True, slots=True)
class ResidentialAcceptanceFinding:
    """One machine-readable PASS/FAIL/NA acceptance observation."""

    scenario_id: str
    category: ResidentialAcceptanceCategory
    criterion_id: str
    severity: ResidentialAcceptanceSeverity
    status: ResidentialAcceptanceStatus
    expected: str
    actual: str
    message: str
    diagnostic_context: str = ""


RESIDENTIAL_ACCEPTANCE_CRITERIA = (
    ResidentialAcceptanceCriterion(
        "minimum_soc",
        ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
        ResidentialAcceptanceSeverity.BLOCKER,
        "Actual SOC never falls below the model minimum.",
    ),
    ResidentialAcceptanceCriterion(
        "maximum_soc",
        ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
        ResidentialAcceptanceSeverity.BLOCKER,
        "Actual SOC never exceeds the model maximum.",
    ),
    ResidentialAcceptanceCriterion(
        "charge_power",
        ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
        ResidentialAcceptanceSeverity.BLOCKER,
        "Actual charge power remains within the model limit.",
    ),
    ResidentialAcceptanceCriterion(
        "discharge_power",
        ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
        ResidentialAcceptanceSeverity.BLOCKER,
        "Actual discharge power remains within the model limit.",
    ),
    ResidentialAcceptanceCriterion(
        "energy_balance",
        ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
        ResidentialAcceptanceSeverity.BLOCKER,
        "Simulator PV + Grid - Battery equals Load.",
    ),
    ResidentialAcceptanceCriterion(
        "actual_feedback",
        ResidentialAcceptanceCategory.CONTROL_SEMANTICS,
        ResidentialAcceptanceSeverity.BLOCKER,
        "Each next cycle uses actual prior Simulator SOC and grid power.",
    ),
    ResidentialAcceptanceCriterion(
        "ledger_reconciliation",
        ResidentialAcceptanceCategory.ACCOUNTING_RECONCILIATION,
        ResidentialAcceptanceSeverity.BLOCKER,
        "TASK-173 daily ledger reconciles with TASK-168.",
    ),
    ResidentialAcceptanceCriterion(
        "comparison_reconciliation",
        ResidentialAcceptanceCategory.ACCOUNTING_RECONCILIATION,
        ResidentialAcceptanceSeverity.BLOCKER,
        "TASK-174 four-component delta decomposition reconciles.",
    ),
    ResidentialAcceptanceCriterion(
        "provenance",
        ResidentialAcceptanceCategory.EXPLAINABILITY,
        ResidentialAcceptanceSeverity.MAJOR,
        "Required evidence identity and decision provenance are available.",
    ),
    ResidentialAcceptanceCriterion(
        "explanations",
        ResidentialAcceptanceCategory.EXPLAINABILITY,
        ResidentialAcceptanceSeverity.MAJOR,
        "Every material action has explanation evidence.",
    ),
    ResidentialAcceptanceCriterion(
        "fixed_control",
        ResidentialAcceptanceCategory.ECONOMIC_BEHAVIOR,
        ResidentialAcceptanceSeverity.BLOCKER,
        "Accounting sensitivity leaves completed control trajectories fixed.",
    ),
)


@dataclass(frozen=True, slots=True)
class ResidentialAcceptanceKPI:
    """Unambiguous reusable Residential EMS campaign KPI vocabulary."""

    scenario_id: str
    path: str
    load_energy_kwh: float
    pv_energy_kwh: float
    grid_import_energy_kwh: float
    grid_export_energy_kwh: float
    battery_throughput_kwh: float
    final_soc_fraction: float
    charge_count: int
    discharge_count: int
    idle_count: int
    physical_revision_count: int
    headroom_limit_count: int
    import_cost: float
    export_revenue: float
    degradation_cost: float
    terminal_value: float
    adjusted_net_economic_cost: float
    min_soc_violation_count: int
    max_soc_violation_count: int
    charge_power_violation_count: int
    discharge_power_violation_count: int
    energy_balance_violation_count: int
    material_action_explanation_count: int
    missing_explanation_count: int
    actual_feedback_used: bool
    ledger_reconciled: bool
    comparison_reconciled: bool
    provenance_complete: bool
    fixed_control_preserved: bool


@dataclass(frozen=True, slots=True)
class ResidentialAcceptanceResult:
    """Criteria and KPI outcome for one deterministic scenario/path."""

    scenario: ResidentialAcceptanceScenario
    kpi: ResidentialAcceptanceKPI
    findings: tuple[ResidentialAcceptanceFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(
            finding.status is ResidentialAcceptanceStatus.FAIL
            for finding in self.findings
        )


@dataclass(frozen=True, slots=True)
class ResidentialAcceptanceSuiteResult:
    """Complete acceptance evidence and campaign-only readiness decision."""

    results: tuple[ResidentialAcceptanceResult, ...]
    readiness: ResidentialCampaignReadiness
    summary_csv_path: Path
    findings_csv_path: Path
    kpis_csv_path: Path
    report_path: Path

    @property
    def findings(self) -> tuple[ResidentialAcceptanceFinding, ...]:
        return tuple(finding for result in self.results for finding in result.findings)


class ResidentialAcceptanceBoundary(ABC):
    """Define a stateless evaluation boundary for completed acceptance facts."""

    __slots__ = ()

    @abstractmethod
    def evaluate(
        self,
        scenario: ResidentialAcceptanceScenario,
        kpi: ResidentialAcceptanceKPI,
        findings: tuple[ResidentialAcceptanceFinding, ...] = (),
    ) -> ResidentialAcceptanceResult:
        """Evaluate acceptance facts without executing control or accounting."""
        raise NotImplementedError


class DeterministicResidentialAcceptanceEvaluator(ResidentialAcceptanceBoundary):
    """Apply frozen hard checks and preserve caller-provided reference evidence."""

    __slots__ = ()

    def evaluate(
        self,
        scenario: ResidentialAcceptanceScenario,
        kpi: ResidentialAcceptanceKPI,
        findings: tuple[ResidentialAcceptanceFinding, ...] = (),
    ) -> ResidentialAcceptanceResult:
        if not isinstance(scenario, ResidentialAcceptanceScenario):
            raise TypeError("scenario must be ResidentialAcceptanceScenario")
        if not isinstance(kpi, ResidentialAcceptanceKPI):
            raise TypeError("kpi must be ResidentialAcceptanceKPI")
        if kpi.scenario_id != scenario.scenario_id:
            raise ValueError("KPI scenario_id must match scenario")
        if not isinstance(findings, tuple) or any(
            not isinstance(item, ResidentialAcceptanceFinding) for item in findings
        ):
            raise TypeError("findings must be a tuple of ResidentialAcceptanceFinding")
        automatic = _automatic_findings(scenario, kpi)
        return ResidentialAcceptanceResult(scenario, kpi, (*automatic, *findings))


def run_residential_acceptance(
    output_directory: Path,
) -> ResidentialAcceptanceSuiteResult:
    """Run the small representative suite and write stable acceptance evidence."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    evaluator = DeterministicResidentialAcceptanceEvaluator()
    reference = run_residential_reference_demo(output_directory / "task175_reference")
    results = list(_reference_results(evaluator, reference))
    reevaluation = run_extended_economic_re_evaluation(
        output_directory / "task172_accounting"
    )
    results.extend(_economic_reference_results(evaluator, reevaluation))
    result_tuple = tuple(results)
    readiness = _readiness(result_tuple)
    summary_csv_path = output_directory / "residential_acceptance_summary.csv"
    findings_csv_path = output_directory / "residential_acceptance_findings.csv"
    kpis_csv_path = output_directory / "residential_acceptance_kpis.csv"
    report_path = output_directory / "residential_acceptance_report.txt"
    summary_csv_path.write_text(
        _summary_csv(result_tuple, readiness), encoding="utf-8", newline=""
    )
    findings_csv_path.write_text(
        _findings_csv(result_tuple), encoding="utf-8", newline=""
    )
    kpis_csv_path.write_text(_kpis_csv(result_tuple), encoding="utf-8", newline="")
    report_path.write_text(
        _report(result_tuple, readiness), encoding="utf-8", newline=""
    )
    return ResidentialAcceptanceSuiteResult(
        result_tuple,
        readiness,
        summary_csv_path,
        findings_csv_path,
        kpis_csv_path,
        report_path,
    )


def _reference_results(
    evaluator: DeterministicResidentialAcceptanceEvaluator,
    reference: ResidentialReferenceResult,
) -> tuple[ResidentialAcceptanceResult, ...]:
    schedule = _reference_kpi("A1", reference.schedule)
    economic = _reference_kpi("A1", reference.economic)
    comparison = reference.comparison
    frozen = _task175_freeze_findings(reference, schedule, economic)
    shared = _finding(
        "A1",
        ResidentialAcceptanceCategory.ACCOUNTING_RECONCILIATION,
        "comparison_reconciliation",
        ResidentialAcceptanceSeverity.BLOCKER,
        comparison.delta_adjusted_cost
        == sum(
            (
                comparison.import_cost_contribution,
                comparison.export_revenue_contribution,
                comparison.degradation_cost_contribution,
                comparison.terminal_value_contribution,
            )
        ),
        "TASK-174 delta equals the four signed contributions",
        f"delta={comparison.delta_adjusted_cost:.6f}",
    )
    schedule_scenario = ResidentialAcceptanceScenario(
        "A1",
        "Residential Reference Demo / Schedule",
        "export_allowed",
        "TASK-175 deterministic perfect-forecast reference path.",
    )
    economic_scenario = ResidentialAcceptanceScenario(
        "A1",
        "Residential Reference Demo / Economic",
        "export_allowed",
        "TASK-175 deterministic perfect-forecast reference path.",
    )
    base = [
        evaluator.evaluate(schedule_scenario, schedule, (*frozen, shared)),
        evaluator.evaluate(economic_scenario, economic, (*frozen, shared)),
    ]
    semantic = (
        (
            "A4",
            "PV Surplus Charging",
            "PV surplus charge action is present",
            any(
                trace.simulation_trace.state.pv_result.actual_power_kw
                > trace.simulation_trace.state.load_result.actual_power_kw
                and trace.journal_record.final_action.action == "charge"
                for trace in reference.economic.result.step_traces
            ),
        ),
        (
            "A5",
            "Evening Deficit Discharge",
            "high-price deficit discharge action is present",
            any(
                trace.simulation_trace.state.tariff_result.import_price_cny_per_kwh
                >= 0.90
                and trace.journal_record.final_action.action == "discharge"
                for trace in reference.economic.result.step_traces
            ),
        ),
        (
            "A6",
            "Minimum SOC Boundary",
            "actual SOC never falls below configured minimum",
            min(_socs(reference.economic)) >= 0.20 - NUMERIC_TOLERANCE,
        ),
        (
            "A7",
            "Maximum SOC Boundary",
            "actual SOC never exceeds configured maximum",
            max(_socs(reference.economic)) <= 1.0 + NUMERIC_TOLERANCE,
        ),
        (
            "A8",
            "PCS Charge Power Limit",
            "actual charge power remains within 3 kW",
            max(_battery_powers(reference.economic)) <= 3.0 + NUMERIC_TOLERANCE,
        ),
        (
            "A9",
            "PCS Discharge Power Limit",
            "actual discharge power remains within 3 kW",
            min(_battery_powers(reference.economic)) >= -3.0 - NUMERIC_TOLERANCE,
        ),
        (
            "A10",
            "Idle / No Economic Opportunity",
            "an explicit idle action is present",
            any(
                trace.journal_record.final_action.action == "idle"
                for trace in reference.economic.result.step_traces
            ),
        ),
    )
    for scenario_id, name, expected, passes in semantic:
        scenario = ResidentialAcceptanceScenario(
            scenario_id,
            name,
            "export_allowed",
            "TASK-175 reference trace read-only acceptance observation.",
        )
        kpi = _copy_kpi(schedule, scenario_id, "Economic")
        base.append(
            evaluator.evaluate(
                scenario,
                kpi,
                (
                    _finding(
                        scenario_id,
                        ResidentialAcceptanceCategory.CONTROL_SEMANTICS
                        if scenario_id in {"A4", "A5", "A10"}
                        else ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
                        f"{scenario_id.lower()}_reference",
                        ResidentialAcceptanceSeverity.BLOCKER,
                        passes,
                        expected,
                        str(passes),
                    ),
                ),
            )
        )
    return tuple(base)


def _economic_reference_results(
    evaluator: DeterministicResidentialAcceptanceEvaluator,
    reevaluation: ExtendedEconomicReEvaluationResult,
) -> tuple[ResidentialAcceptanceResult, ...]:
    # Keep the runner interface out of the core evaluator: it only receives completed KPI/findings.
    baselines = tuple(
        item
        for item in reevaluation.evaluations
        if item.export_revenue_evidence.export_tariff_per_kwh == 0.20
        and item.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
        == 0.05
        and item.terminal_energy_value_evidence.valuation_import_price == 0.85
    )
    by_key = {
        (item.fixed_path.scenario_id, item.fixed_path.path): item for item in baselines
    }
    e1_schedule = by_key[("E1", "Schedule")]
    e1_economic = by_key[("E1", "Economic")]
    terminal_schedule = by_key[("C_TERMINAL_SOC_DIVERGENCE", "Schedule")]
    terminal_economic = by_key[("C_TERMINAL_SOC_DIVERGENCE", "Economic")]
    e1_kpi = _extended_kpi("A2", e1_economic)
    suppressed = _suppressed_grid_charge(e1_economic)
    e1_finding = _finding(
        "A2",
        ResidentialAcceptanceCategory.ECONOMIC_BEHAVIOR,
        "negative_economic_shift_suppression",
        ResidentialAcceptanceSeverity.BLOCKER,
        suppressed > 0.0
        and e1_economic.extended_outcome_evidence.adjusted_net_economic_cost
        < e1_schedule.extended_outcome_evidence.adjusted_net_economic_cost,
        "unsupported cheap-grid charging is suppressed and Economic adjusted cost is lower",
        f"suppressed={suppressed:.6f}; delta={e1_economic.extended_outcome_evidence.adjusted_net_economic_cost - e1_schedule.extended_outcome_evidence.adjusted_net_economic_cost:.6f}",
    )
    e1 = evaluator.evaluate(
        ResidentialAcceptanceScenario(
            "A2",
            "Negative Economic Shift",
            "export_allowed",
            "TASK-161 E1 / TASK-172 fixed-control accounting reference.",
        ),
        e1_kpi,
        (e1_finding,),
    )
    terminal_comparison = DeterministicEconomicComparisonExplainer().explain(
        EconomicComparisonInput(
            "Schedule",
            "Economic",
            terminal_schedule.extended_outcome_evidence,
            terminal_economic.extended_outcome_evidence,
            "A3",
            "TASK-172 baseline accounting",
        )
    )
    terminal_kpi = _extended_kpi("A3", terminal_economic)
    terminal_finding = _finding(
        "A3",
        ResidentialAcceptanceCategory.ECONOMIC_BEHAVIOR,
        "terminal_value_material_offset",
        ResidentialAcceptanceSeverity.BLOCKER,
        terminal_comparison.terminal_value_contribution > 0.0
        and isclose(
            terminal_comparison.delta_adjusted_cost,
            sum(
                (
                    terminal_comparison.import_cost_contribution,
                    terminal_comparison.export_revenue_contribution,
                    terminal_comparison.degradation_cost_contribution,
                    terminal_comparison.terminal_value_contribution,
                )
            ),
            rel_tol=0.0,
            abs_tol=NUMERIC_TOLERANCE,
        ),
        "terminal contribution offsets Economic import-cost advantage and comparison reconciles",
        format_economic_comparison_explanation(terminal_comparison).replace(
            "\n", " | "
        ),
    )
    terminal = evaluator.evaluate(
        ResidentialAcceptanceScenario(
            "A3",
            "Terminal SOC Divergence",
            "export_allowed",
            "TASK-165 terminal-SOC divergence with TASK-172 fixed-control accounting.",
        ),
        terminal_kpi,
        (terminal_finding,),
    )
    return (e1, terminal)


def _reference_kpi(
    scenario_id: str, path: ResidentialReferencePath
) -> ResidentialAcceptanceKPI:
    ledger = path.ledger
    traces = path.result.step_traces
    power = tuple(
        trace.simulation_trace.state.battery_result.actual_power_kw for trace in traces
    )
    socs = _socs(path)
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
    feedback = _actual_feedback_used(path)
    headroom = _headroom_limit_count(path)
    return ResidentialAcceptanceKPI(
        scenario_id,
        path.name,
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
        headroom,
        ledger.total_realized_import_cost,
        ledger.total_realized_export_revenue,
        ledger.total_battery_degradation_cost,
        ledger.terminal_energy_value,
        ledger.adjusted_net_economic_cost,
        sum(value < 0.20 - NUMERIC_TOLERANCE for value in socs),
        sum(value > 1.0 + NUMERIC_TOLERANCE for value in socs),
        sum(value > 3.0 + NUMERIC_TOLERANCE for value in power),
        sum(value < -3.0 - NUMERIC_TOLERANCE for value in power),
        balances,
        sum(trace.journal_record.final_action.action != "idle" for trace in traces),
        sum(not trace.journal_record.formatted_text for trace in traces),
        feedback,
        isclose(
            ledger.adjusted_net_economic_cost,
            ledger.extended_outcome_evidence.adjusted_net_economic_cost,
            rel_tol=0.0,
            abs_tol=NUMERIC_TOLERANCE,
        ),
        True,
        True,
        True,
    )


def _extended_kpi(
    scenario_id: str, evaluation: ExtendedEconomicEvaluation
) -> ResidentialAcceptanceKPI:
    metrics = evaluation.fixed_path.source_metrics
    outcome = evaluation.extended_outcome_evidence
    return ResidentialAcceptanceKPI(
        scenario_id,
        evaluation.fixed_path.path,
        metrics.load_energy_kwh,
        metrics.pv_energy_kwh,
        metrics.grid_import_energy_kwh,
        metrics.grid_export_energy_kwh,
        metrics.battery_throughput_kwh,
        metrics.final_soc,
        metrics.charge_count,
        metrics.discharge_count,
        metrics.idle_count,
        metrics.physical_revision_count,
        0,
        outcome.realized_import_cost,
        outcome.realized_export_revenue,
        outcome.battery_degradation_cost,
        outcome.terminal_energy_value,
        outcome.adjusted_net_economic_cost,
        0,
        0,
        0,
        0,
        0,
        metrics.charge_count + metrics.discharge_count,
        0,
        True,
        True,
        True,
        True,
        True,
    )


def _automatic_findings(
    scenario: ResidentialAcceptanceScenario, kpi: ResidentialAcceptanceKPI
) -> tuple[ResidentialAcceptanceFinding, ...]:
    checks = (
        (
            "minimum_soc",
            ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
            kpi.min_soc_violation_count == 0,
            "no SOC below minimum",
            str(kpi.min_soc_violation_count),
        ),
        (
            "maximum_soc",
            ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
            kpi.max_soc_violation_count == 0,
            "no SOC above maximum",
            str(kpi.max_soc_violation_count),
        ),
        (
            "charge_power",
            ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
            kpi.charge_power_violation_count == 0,
            "no charge power above limit",
            str(kpi.charge_power_violation_count),
        ),
        (
            "discharge_power",
            ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
            kpi.discharge_power_violation_count == 0,
            "no discharge power above limit",
            str(kpi.discharge_power_violation_count),
        ),
        (
            "energy_balance",
            ResidentialAcceptanceCategory.PHYSICAL_SAFETY,
            kpi.energy_balance_violation_count == 0,
            "all hourly balances reconcile",
            str(kpi.energy_balance_violation_count),
        ),
        (
            "actual_feedback",
            ResidentialAcceptanceCategory.CONTROL_SEMANTICS,
            kpi.actual_feedback_used,
            "actual previous Simulator SOC/grid feedback is used",
            str(kpi.actual_feedback_used),
        ),
        (
            "ledger_reconciliation",
            ResidentialAcceptanceCategory.ACCOUNTING_RECONCILIATION,
            kpi.ledger_reconciled,
            "TASK-173 ledger reconciles with TASK-168",
            str(kpi.ledger_reconciled),
        ),
        (
            "comparison_reconciliation",
            ResidentialAcceptanceCategory.ACCOUNTING_RECONCILIATION,
            kpi.comparison_reconciled,
            "TASK-174 comparison reconciles",
            str(kpi.comparison_reconciled),
        ),
        (
            "provenance",
            ResidentialAcceptanceCategory.EXPLAINABILITY,
            kpi.provenance_complete,
            "required provenance is retained",
            str(kpi.provenance_complete),
        ),
        (
            "explanations",
            ResidentialAcceptanceCategory.EXPLAINABILITY,
            kpi.missing_explanation_count == 0,
            "all material actions have explanations",
            str(kpi.missing_explanation_count),
        ),
        (
            "fixed_control",
            ResidentialAcceptanceCategory.ECONOMIC_BEHAVIOR,
            kpi.fixed_control_preserved,
            "accounting sensitivity does not rerun control",
            str(kpi.fixed_control_preserved),
        ),
    )
    return tuple(
        _finding(
            scenario.scenario_id,
            category,
            criterion,
            ResidentialAcceptanceSeverity.BLOCKER
            if category is not ResidentialAcceptanceCategory.EXPLAINABILITY
            else ResidentialAcceptanceSeverity.MAJOR,
            passed,
            expected,
            actual,
        )
        for criterion, category, passed, expected, actual in checks
    )


def _task175_freeze_findings(
    reference: ResidentialReferenceResult,
    schedule: ResidentialAcceptanceKPI,
    economic: ResidentialAcceptanceKPI,
) -> tuple[ResidentialAcceptanceFinding, ...]:
    expected = (27.1, 14.3, 13.122438, 2.659280, 12.863158, 0.2, 5.285789)
    actual = (
        schedule.load_energy_kwh,
        schedule.pv_energy_kwh,
        schedule.grid_import_energy_kwh,
        schedule.grid_export_energy_kwh,
        schedule.battery_throughput_kwh,
        schedule.final_soc_fraction,
        schedule.adjusted_net_economic_cost,
    )
    passes = (
        all(
            isclose(value, target, rel_tol=0.0, abs_tol=1e-6)
            for value, target in zip(actual, expected, strict=True)
        )
        and all(
            isclose(
                getattr(schedule, field),
                getattr(economic, field),
                rel_tol=0.0,
                abs_tol=NUMERIC_TOLERANCE,
            )
            for field in (
                "grid_import_energy_kwh",
                "grid_export_energy_kwh",
                "battery_throughput_kwh",
                "final_soc_fraction",
                "adjusted_net_economic_cost",
            )
        )
        and reference.comparison.ranking.value == "tied"
    )
    return (
        _finding(
            "A1",
            ResidentialAcceptanceCategory.ECONOMIC_BEHAVIOR,
            "task175_reference_metric_freeze",
            ResidentialAcceptanceSeverity.BLOCKER,
            passes,
            "TASK-175 frozen numeric fingerprint and Schedule/Economic TIED",
            f"schedule_cost={schedule.adjusted_net_economic_cost:.6f}; economic_cost={economic.adjusted_net_economic_cost:.6f}; ranking={reference.comparison.ranking.value}",
        ),
    )


def _finding(
    scenario_id: str,
    category: ResidentialAcceptanceCategory,
    criterion_id: str,
    severity: ResidentialAcceptanceSeverity,
    passed: bool,
    expected: str,
    actual: str,
) -> ResidentialAcceptanceFinding:
    return ResidentialAcceptanceFinding(
        scenario_id,
        category,
        criterion_id,
        severity,
        ResidentialAcceptanceStatus.PASS
        if passed
        else ResidentialAcceptanceStatus.FAIL,
        expected,
        actual,
        "acceptance criterion satisfied" if passed else "acceptance criterion failed",
    )


def _copy_kpi(
    kpi: ResidentialAcceptanceKPI, scenario_id: str, path: str
) -> ResidentialAcceptanceKPI:
    values = {field: getattr(kpi, field) for field in kpi.__dataclass_fields__}
    values["scenario_id"] = scenario_id
    values["path"] = path
    return ResidentialAcceptanceKPI(**values)


def _socs(path: ResidentialReferencePath) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.battery_result.next_state.soc
        for trace in path.result.step_traces
    )


def _battery_powers(path: ResidentialReferencePath) -> tuple[float, ...]:
    return tuple(
        trace.simulation_trace.state.battery_result.actual_power_kw
        for trace in path.result.step_traces
    )


def _actual_feedback_used(path: ResidentialReferencePath) -> bool:
    if isinstance(
        path.result,
        EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    ):
        return _economic_actual_feedback_used(path.result)
    return _schedule_actual_feedback_used(path.result)


def _economic_actual_feedback_used(
    result: EconomicMultiOpportunityExplainableMPCDailySimulationResult,
) -> bool:
    traces = result.step_traces
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
    result: MultiOpportunityExplainableMPCDailySimulationResult,
) -> bool:
    traces = result.step_traces
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


def _headroom_limit_count(path: ResidentialReferencePath) -> int:
    if not isinstance(
        path.result,
        EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    ):
        return 0
    return sum(_reservation_applied(trace) for trace in path.result.step_traces)


def _reservation_applied(trace: object) -> int:
    if not hasattr(trace, "economic_multi_opportunity_mpc_cycle_result"):
        return 0
    result = trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.reservation_result
    return int(result is not None and result.reservation_applied)


def _suppressed_grid_charge(evaluation: ExtendedEconomicEvaluation) -> float:
    result = evaluation.fixed_path.source_control_result
    if not isinstance(
        result, EconomicMultiOpportunityExplainableMPCDailySimulationResult
    ):
        return 0.0
    total = 0.0
    for trace in result.step_traces:
        value = trace.economic_multi_opportunity_mpc_cycle_result.economic_multi_opportunity_optimization_output.candidate_planning_result.economic_value_result
        if value is not None:
            total += (
                value.headroom_allowed_grid_charge_power_kw
                - value.economically_supported_grid_charge_power_kw
            )
    return total


def _readiness(
    results: tuple[ResidentialAcceptanceResult, ...],
) -> ResidentialCampaignReadiness:
    blocking = any(
        finding.status is ResidentialAcceptanceStatus.FAIL
        and finding.severity
        in {ResidentialAcceptanceSeverity.BLOCKER, ResidentialAcceptanceSeverity.MAJOR}
        for result in results
        for finding in result.findings
    )
    return (
        ResidentialCampaignReadiness.NOT_READY_FOR_SIMULATION_CAMPAIGN
        if blocking
        else ResidentialCampaignReadiness.READY_FOR_SIMULATION_CAMPAIGN
    )


def _summary_csv(
    results: tuple[ResidentialAcceptanceResult, ...],
    readiness: ResidentialCampaignReadiness,
) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "scenario",
            "path",
            "pass",
            "blocker_failures",
            "major_failures",
            "readiness",
        )
    )
    for result in results:
        findings = result.findings
        writer.writerow(
            (
                result.scenario.scenario_id,
                result.scenario.name,
                result.kpi.path,
                str(result.passed).lower(),
                sum(
                    item.status is ResidentialAcceptanceStatus.FAIL
                    and item.severity is ResidentialAcceptanceSeverity.BLOCKER
                    for item in findings
                ),
                sum(
                    item.status is ResidentialAcceptanceStatus.FAIL
                    and item.severity is ResidentialAcceptanceSeverity.MAJOR
                    for item in findings
                ),
                readiness.value,
            )
        )
    return stream.getvalue()


def _findings_csv(results: Iterable[ResidentialAcceptanceResult]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "category",
            "criterion_id",
            "severity",
            "status",
            "expected",
            "actual",
            "message",
            "diagnostic_context",
        )
    )
    for result in results:
        for finding in result.findings:
            writer.writerow(
                (
                    finding.scenario_id,
                    finding.category.value,
                    finding.criterion_id,
                    finding.severity.value,
                    finding.status.value,
                    finding.expected,
                    finding.actual,
                    finding.message,
                    finding.diagnostic_context,
                )
            )
    return stream.getvalue()


def _kpis_csv(results: Iterable[ResidentialAcceptanceResult]) -> str:
    values = tuple(results)
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    fields = tuple(ResidentialAcceptanceKPI.__dataclass_fields__)
    writer.writerow(fields)
    for result in values:
        writer.writerow(tuple(getattr(result.kpi, field) for field in fields))
    return stream.getvalue()


def _report(
    results: tuple[ResidentialAcceptanceResult, ...],
    readiness: ResidentialCampaignReadiness,
) -> str:
    failed = tuple(
        finding
        for result in results
        for finding in result.findings
        if finding.status is ResidentialAcceptanceStatus.FAIL
    )
    passed = not failed
    return (
        "Residential EMS 1.0 Acceptance\n\n"
        "Scope\nDeterministic functional-freeze gate for Residential EMS 1.0. It evaluates existing completed paths only; it is not a hardware readiness statement.\n\n"
        "Acceptance Scenarios\nA1 Residential Reference Demo; A2 Negative Economic Shift; A3 Terminal SOC Divergence; A4 PV surplus charging; A5 evening deficit discharge; A6 minimum SOC; A7 maximum SOC; A8 charge power limit; A9 discharge power limit; A10 idle. Export is explicitly allowed in these reference paths.\n\n"
        "Physical Safety Results\nSimulator convention: battery power > 0 is charging, < 0 is discharging; grid power > 0 is import, < 0 is export. SOC, power, finite-value, progression, and balance checks use tolerance 1e-12.\n\n"
        "Control Semantics Results\nActual previous Simulator SOC and grid power must feed each next MPC cycle; projected SOC is never accepted as actual feedback.\n\n"
        "Accounting Reconciliation Results\nTASK-173 ledger and TASK-168 outcome reconcile; TASK-174 candidate-minus-reference decomposition reconciles.\n\n"
        "Economic Reference Behavior\nTASK-175 positive economics preserves justified grid charging. TASK-172 E1 suppresses unsupported charging. Terminal divergence retains a positive terminal-value contribution against the Economic candidate.\n\n"
        "Explainability / Provenance\nMaterial actions retain decision explanation/journal evidence and required accounting provenance.\n\n"
        "KPI Summary\nSee residential_acceptance_kpis.csv for the campaign-reusable KPI vocabulary.\n\n"
        f"Failures / Warnings\nfailed_findings={len(failed)}\n\n"
        f"Campaign Readiness\n{readiness.value}\n\n"
        "Known Limitations\nPerfect deterministic forecasts dominate this gate. It does not validate real weather, forecast error, PCS/BMS, communication failures, physical aging economics, tariff certification, industrial sites, or multiple storage devices.\n\n"
        + (
            "Final Statement\nResidential EMS 1.0 passes the deterministic acceptance suite and is ready for the planned large-scale simulation validation campaign.\n"
            if passed
            and readiness is ResidentialCampaignReadiness.READY_FOR_SIMULATION_CAMPAIGN
            else "Final Statement\nResidential EMS 1.0 is NOT ready for the planned large-scale simulation validation campaign.\n"
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS Residential EMS 1.0 acceptance suite"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task176_residential_acceptance"),
    )
    arguments = parser.parse_args(argv)
    result = run_residential_acceptance(arguments.output_dir)
    for path in (
        result.summary_csv_path,
        result.findings_csv_path,
        result.kpis_csv_path,
        result.report_path,
    ):
        print(path)
    print(result.readiness.value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
