"""Regression tests for frozen Residential EMS Campaign D reporting tooling."""

import csv
from collections import Counter
from dataclasses import dataclass, replace
from itertools import pairwise
from math import isclose
from pathlib import Path
from xml.etree import ElementTree

import pytest

import ems_simulator.residential_campaign_d as campaign_d_module
from ems_simulator.multi_opportunity_headroom_demo import create_demo_input
from ems_simulator.residential_acceptance import (
    NUMERIC_TOLERANCE,
    DeterministicResidentialAcceptanceEvaluator,
)
from ems_simulator.residential_campaign_d import (
    ResidentialCampaignDResult,
    ResidentialCampaignDScenarioDay,
    _bar_svg,
    campaign_d_cases,
    campaign_d_scenario_days,
    run_residential_campaign_d,
)


@pytest.fixture(scope="module")
def campaign_d(tmp_path_factory: pytest.TempPathFactory) -> ResidentialCampaignDResult:
    """Run the fixed Campaign D matrix once for all report-contract assertions."""

    return run_residential_campaign_d(tmp_path_factory.mktemp("campaign_d"))


@dataclass(frozen=True, slots=True)
class _ArtificialChainDay:
    """Test-only final-SOC evidence for mutation-sensitive carry orchestration."""

    initial_soc_fraction: float
    final_actual_soc_fraction: float


@dataclass(frozen=True, slots=True)
class _ArtificialPathSummary:
    """Test-only aggregate placeholder; the carry loop is the unit under test."""

    days: tuple[_ArtificialChainDay, ...]
    aggregate_outcome: object


class _ArtificialRunner:
    """Return a strategy marker without invoking frozen production control."""

    def __init__(self, strategy: str) -> None:
        self.strategy = strategy

    def run(self, _daily_input: object) -> str:
        return self.strategy


class _ArtificialComparisonExplainer:
    """Avoid constructing accounting evidence while exercising `_run_case`."""

    def explain(self, _source_input: object) -> object:
        return object()


def _csv_rows(campaign: ResidentialCampaignDResult) -> dict[str, list[dict[str, str]]]:
    """Read Campaign D CSV evidence by its stable generated filename."""

    rows: dict[str, list[dict[str, str]]] = {}
    for path in campaign.output_paths:
        if path.suffix != ".csv":
            continue
        with path.open(encoding="utf-8", newline="") as stream:
            rows[path.name] = list(csv.DictReader(stream))
    return rows


def _output_path(campaign: ResidentialCampaignDResult, name: str) -> Path:
    return next(path for path in campaign.output_paths if path.name == name)


def _csv_header(campaign: ResidentialCampaignDResult, name: str) -> list[str]:
    with _output_path(campaign, name).open(encoding="utf-8", newline="") as stream:
        return next(csv.reader(stream))


def _svg_root(campaign: ResidentialCampaignDResult, name: str) -> ElementTree.Element:
    """Parse one already-generated Campaign D SVG without text-order assumptions."""

    return ElementTree.parse(_output_path(campaign, name)).getroot()


def _svg_elements(root: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    return root.findall(f"{{http://www.w3.org/2000/svg}}{name}")


def test_campaign_d_defines_the_exact_six_case_matrix() -> None:
    cases = campaign_d_cases()
    days = campaign_d_scenario_days()

    assert len(cases) == 6
    assert [len(case.source_scenario_ids) for case in cases] == [7, 7, 7, 7, 30, 30]
    assert cases[3].source_scenario_ids == (
        "A01_REFERENCE_TASK175",
        "A01_REFERENCE_TASK175",
        "A10_HIGH_PV",
        "A01_REFERENCE_TASK175",
        "A16_EVENING_PEAK",
        "A16_EVENING_PEAK",
        "A10_HIGH_PV",
    )
    assert cases[4].source_scenario_ids == cases[3].source_scenario_ids * 4 + (
        "A01_REFERENCE_TASK175",
        "A01_REFERENCE_TASK175",
    )
    assert cases[5].source_scenario_ids == (
        ("A10_HIGH_PV",) * 10
        + ("A16_EVENING_PEAK",) * 10
        + ("A01_REFERENCE_TASK175",) * 10
    )
    assert len(days) == 88
    assert len({day.scenario_day_id for day in days}) == 88


def test_campaign_d_orchestration_keeps_artificial_strategy_soc_chains_isolated(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Make carry isolation mutation-sensitive without running production control.

    The real deterministic matrix intentionally produces equal Schedule/Economic
    outcomes. These test-only final SOC values differ so a swapped/shared/reset
    carry variable inside the existing `_run_case` loop cannot pass silently.
    """

    source_case = campaign_d_cases()[0]
    scenario_days = tuple(
        day
        for day in campaign_d_scenario_days()
        if day.case.case_id == source_case.case_id
    )[:3]
    case = replace(
        source_case,
        source_scenario_ids=tuple(
            day.source_scenario.scenario_id for day in scenario_days
        ),
    )
    supplied_initial_soc: dict[str, list[float]] = {"Schedule": [], "Economic": []}
    final_soc = {
        "Schedule": (0.31, 0.42, 0.53),
        "Economic": (0.71, 0.62, 0.73),
    }

    def fake_daily_input(
        _day: ResidentialCampaignDScenarioDay,
        initial_soc: float,
        _template: object,
        directory: Path,
    ) -> str:
        strategy = directory.name.capitalize()
        supplied_initial_soc[strategy].append(initial_soc)
        return strategy

    def fake_day_path(
        day: ResidentialCampaignDScenarioDay,
        strategy: str,
        initial_soc: float,
        _trajectory: object,
        _ledger: object,
        _comparison: object,
        _evaluator: object,
    ) -> _ArtificialChainDay:
        return _ArtificialChainDay(
            initial_soc,
            final_soc[strategy][day.day_index - 1],
        )

    def fake_path_summary(
        _case: object,
        _strategy: str,
        days: tuple[_ArtificialChainDay, ...],
    ) -> _ArtificialPathSummary:
        return _ArtificialPathSummary(days, object())

    def fake_comparison_input(*_arguments: object) -> object:
        return object()

    monkeypatch.setattr(campaign_d_module, "_daily_input", fake_daily_input)
    monkeypatch.setattr(
        campaign_d_module,
        "_schedule_runner",
        lambda _configuration: _ArtificialRunner("Schedule"),
    )
    monkeypatch.setattr(
        campaign_d_module,
        "_economic_runner",
        lambda _configuration: _ArtificialRunner("Economic"),
    )
    monkeypatch.setattr(campaign_d_module, "_ledger", lambda *_arguments: object())
    monkeypatch.setattr(
        campaign_d_module, "_daily_comparison", lambda *_arguments: object()
    )
    monkeypatch.setattr(campaign_d_module, "_day_path", fake_day_path)
    monkeypatch.setattr(campaign_d_module, "_path_summary", fake_path_summary)
    monkeypatch.setattr(
        campaign_d_module, "EconomicComparisonInput", fake_comparison_input
    )
    monkeypatch.setattr(
        campaign_d_module,
        "DeterministicEconomicComparisonExplainer",
        _ArtificialComparisonExplainer,
    )

    result = campaign_d_module._run_case(
        case,
        scenario_days,
        create_demo_input(tmp_path),
        DeterministicResidentialAcceptanceEvaluator(),
        tmp_path,
    )

    assert supplied_initial_soc == {
        "Schedule": [case.initial_soc_fraction, 0.31, 0.42],
        "Economic": [case.initial_soc_fraction, 0.71, 0.62],
    }
    assert supplied_initial_soc["Schedule"][1:] != supplied_initial_soc["Economic"][1:]
    assert all(
        initial_soc != case.initial_soc_fraction
        for chain in supplied_initial_soc.values()
        for initial_soc in chain[1:]
    )
    assert [day.final_actual_soc_fraction for day in result.schedule.days] == [
        0.31,
        0.42,
        0.53,
    ]
    assert [day.final_actual_soc_fraction for day in result.economic.days] == [
        0.71,
        0.62,
        0.73,
    ]


def test_campaign_d_executes_fresh_daily_paths_with_actual_state_carry(
    campaign_d: ResidentialCampaignDResult,
) -> None:
    results = campaign_d.case_results
    paths = tuple(
        summary for result in results for summary in (result.schedule, result.economic)
    )
    day_paths = tuple(day for summary in paths for day in summary.days)

    assert len(results) == 6
    assert len(paths) == 12
    assert len(day_paths) == 176
    assert len({id(day.trajectory) for day in day_paths}) == 176
    assert all(len(day.trajectory.step_traces) == 24 for day in day_paths)
    assert campaign_d.hard_passed

    for summary in paths:
        timestamps = tuple(
            trace.simulation_trace.simulation_input.step_identity.timestamp
            for day in summary.days
            for trace in day.trajectory.step_traces
        )
        assert all(timestamp is not None for timestamp in timestamps)
        concrete_timestamps = tuple(
            timestamp for timestamp in timestamps if timestamp is not None
        )
        assert len(concrete_timestamps) == summary.total_hours
        assert all(
            following - prior == concrete_timestamps[1] - concrete_timestamps[0]
            for prior, following in pairwise(concrete_timestamps)
        )
        assert all(item.passed for item in summary.continuity)
        assert all(
            isclose(item.carry_delta, 0.0, abs_tol=NUMERIC_TOLERANCE)
            for item in summary.continuity
        )
        for prior_day, current_day in pairwise(summary.days):
            prior_trace = prior_day.trajectory.step_traces[-1]
            current_trace = current_day.trajectory.step_traces[0]
            prior_timestamp = (
                prior_trace.simulation_trace.simulation_input.step_identity.timestamp
            )
            current_timestamp = (
                current_trace.simulation_trace.simulation_input.step_identity.timestamp
            )
            assert isclose(
                current_day.initial_soc_fraction,
                prior_day.final_actual_soc_fraction,
                abs_tol=NUMERIC_TOLERANCE,
            )
            assert current_timestamp is not None
            assert prior_timestamp is not None
            assert (current_timestamp - prior_timestamp).total_seconds() == 3600.0
            assert (
                current_day.scenario_day.source_scenario.battery_model
                is prior_day.scenario_day.source_scenario.battery_model
            )
            assert (
                current_day.trajectory.source_input.daily_mpc_input.source_strategy
                is prior_day.trajectory.source_input.daily_mpc_input.source_strategy
            )
            assert (
                current_day.scenario_day.source_scenario.export_policy
                == prior_day.scenario_day.source_scenario.export_policy
            )
        assert summary.timestamp_discontinuity_count == 0


def test_campaign_d_aggregate_uses_actual_final_soc_and_terminal_value_once(
    campaign_d: ResidentialCampaignDResult,
) -> None:
    for result in campaign_d.case_results:
        for summary in (result.schedule, result.economic):
            final_day = summary.days[-1]
            model = final_day.scenario_day.source_scenario.battery_model
            valuation = (
                final_day.scenario_day.source_scenario.terminal_valuation_per_kwh
            )
            final_soc = final_day.final_actual_soc_fraction
            expected_terminal = (
                max(final_soc - model.min_soc_fraction, 0.0)
                * model.usable_capacity_kwh
                * model.discharge_efficiency
                * valuation
            )
            outcome = summary.aggregate_outcome
            assert isclose(
                summary.final_terminal_evidence.terminal_energy_value,
                expected_terminal,
                abs_tol=NUMERIC_TOLERANCE,
            )
            assert summary.final_terminal_evidence.source_input.battery_model is model
            assert isclose(
                outcome.adjusted_net_economic_cost,
                outcome.realized_import_cost
                - outcome.realized_export_revenue
                + outcome.battery_degradation_cost
                - summary.final_terminal_evidence.terminal_energy_value,
                abs_tol=NUMERIC_TOLERANCE,
            )


def test_campaign_d_outputs_are_complete_and_byte_deterministic(
    campaign_d: ResidentialCampaignDResult, tmp_path: Path
) -> None:
    expected_names = {
        "campaign_d_cases.csv",
        "campaign_d_scenario_days.csv",
        "campaign_d_day_results.csv",
        "campaign_d_continuity.csv",
        "campaign_d_path_summaries.csv",
        "campaign_d_comparisons.csv",
        "campaign_d_findings.csv",
        "campaign_d_summary.txt",
        "soc_7d_mixed_week.svg",
        "soc_30d_representative.svg",
        "soc_30d_block_stress.svg",
        "carry_continuity.svg",
        "cumulative_operating_cost.svg",
        "daily_grid_import_export.svg",
        "cumulative_physical_revisions.svg",
        "aggregate_adjusted_cost_comparison.svg",
    }
    first = {path.name: path.read_bytes() for path in campaign_d.output_paths}
    repeat = run_residential_campaign_d(tmp_path / "repeat")
    second = {path.name: path.read_bytes() for path in repeat.output_paths}

    assert set(first) == expected_names
    assert set(second) == expected_names
    assert first == second


def test_campaign_d_output_schema_and_summary_remain_auditable(
    campaign_d: ResidentialCampaignDResult,
) -> None:
    """Assert stable evidence schema, counts, provenance and summary semantics."""

    expected_headers = {
        "campaign_d_cases.csv": [
            "case_id",
            "duration_class",
            "day_count",
            "initial_soc_fraction",
            "source_sequence",
            "description",
        ],
        "campaign_d_scenario_days.csv": [
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
        ],
        "campaign_d_day_results.csv": [
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
        ],
        "campaign_d_continuity.csv": [
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
        ],
        "campaign_d_path_summaries.csv": [
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
        ],
        "campaign_d_comparisons.csv": [
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
        ],
        "campaign_d_findings.csv": [
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
        ],
    }
    expected_rows = {
        "campaign_d_cases.csv": 6,
        "campaign_d_scenario_days.csv": 88,
        "campaign_d_day_results.csv": 176,
        "campaign_d_continuity.csv": 164,
        "campaign_d_path_summaries.csv": 12,
        "campaign_d_comparisons.csv": 6,
    }
    rows = _csv_rows(campaign_d)

    assert set(rows) == set(expected_headers)
    assert {
        name: _csv_header(campaign_d, name) for name in expected_headers
    } == expected_headers
    assert {name: len(rows[name]) for name in expected_rows} == expected_rows
    assert len(rows["campaign_d_findings.csv"]) == len(campaign_d.findings)
    assert Counter(
        (
            row["case_id"],
            row["strategy"],
            row["day_index"],
            row["category"],
            row["criterion_id"],
            row["severity"],
            row["status"],
            row["expected"],
            row["actual"],
            row["message"],
        )
        for row in rows["campaign_d_findings.csv"]
    ) == Counter(
        (
            finding.case_id,
            finding.strategy,
            "" if finding.day_index is None else str(finding.day_index),
            finding.category,
            finding.criterion_id,
            finding.severity,
            finding.status,
            finding.expected,
            finding.actual,
            finding.message,
        )
        for finding in campaign_d.findings
    )
    assert {
        (row["case_id"], row["strategy"]) for row in rows["campaign_d_day_results.csv"]
    } == {
        (result.case.case_id, strategy)
        for result in campaign_d.case_results
        for strategy in ("Schedule", "Economic")
    }
    assert all(
        row["source_scenario_id"] and row["first_timestamp"] and row["last_timestamp"]
        for row in rows["campaign_d_day_results.csv"]
    )
    assert all(
        row["prior_final_actual_soc"] == row["current_initial_soc"]
        and row["passed"] == "true"
        for row in rows["campaign_d_continuity.csv"]
    )

    summary_text = _output_path(campaign_d, "campaign_d_summary.txt").read_text(
        encoding="utf-8"
    )
    for required_text in (
        "functional_freeze=",
        "matrix=6 cases; 4 seven-day; 2 thirty-day; 88 scenario-days; "
        "12 logical paths; 176 actual frozen daily executions",
        "campaign_hard_status=PASS",
        "blocker_count=0 major_count=0 minor_count=0 informational_count=0",
        "continuity_status=PASS",
        "terminal_value_once=PASS",
        "economic_wins=0 schedule_wins=0 ties=6",
        "largest_schedule_economic_difference=",
        "interpretation=",
    ):
        assert required_text in summary_text


def test_campaign_d_svg_uses_its_computed_zero_baseline_and_escaped_labels() -> None:
    svg = _bar_svg(
        "cost <&>",
        "CNY",
        (("negative <&>", -2.0), ('positive "&', 6.0)),
        "trace <&>",
    )

    assert 'id="zero-axis" x1="40" y1="202.50" x2="990" y2="202.50"' in svg
    assert 'data-label="negative &lt;&amp;&gt;"' in svg
    assert 'data-label="positive &quot;&amp;"' in svg
    assert "cost &lt;&amp;&gt;" in svg


def test_campaign_d_generated_svgs_preserve_evidence_points_and_traceability(
    campaign_d: ResidentialCampaignDResult,
) -> None:
    """Parse each generated SVG and reconcile its visible semantic data count."""

    summaries = {
        f"{result.case.case_id}|{summary.strategy}": summary
        for result in campaign_d.case_results
        for summary in (result.schedule, result.economic)
    }
    expected_soc = {
        "soc_7d_mixed_week.svg": "D04_7D_MIXED_WEEK",
        "soc_30d_representative.svg": "D05_30D_REPRESENTATIVE",
        "soc_30d_block_stress.svg": "D06_30D_BLOCK_STRESS",
    }
    for name, case_id in expected_soc.items():
        root = _svg_root(campaign_d, name)
        polylines = _svg_elements(root, "polyline")
        labels = [line.attrib["data-label"] for line in polylines]
        assert labels == [f"{case_id}|Schedule", f"{case_id}|Economic"]
        assert [len(line.attrib["points"].split()) for line in polylines] == [
            summaries[labels[0]].total_hours,
            summaries[labels[1]].total_hours,
        ]
        svg_text = "".join(root.itertext())
        assert "SOC fraction" in svg_text
        assert "hourly actual Simulator next-state SOC" in svg_text

    for name, unit in (
        ("cumulative_operating_cost.svg", "CNY"),
        ("cumulative_physical_revisions.svg", "count"),
    ):
        root = _svg_root(campaign_d, name)
        polylines = _svg_elements(root, "polyline")
        labels = [line.attrib["data-label"] for line in polylines]
        assert set(labels) == set(summaries)
        assert {
            label: len(line.attrib["points"].split())
            for label, line in zip(labels, polylines, strict=True)
        } == {label: len(summary.days) for label, summary in summaries.items()}
        assert unit in "".join(root.itertext())
        assert "x-axis cadence=1 day" in "".join(root.itertext())

    carry_root = _svg_root(campaign_d, "carry_continuity.svg")
    carry_bars = [
        element
        for element in _svg_elements(carry_root, "rect")
        if "data-label" in element.attrib
    ]
    expected_carry_labels = {
        f"{item.case_id}|{item.strategy}|day={item.day_index}"
        for result in campaign_d.case_results
        for summary in (result.schedule, result.economic)
        for item in summary.continuity
    }
    assert {bar.attrib["data-label"] for bar in carry_bars} == expected_carry_labels
    assert len(carry_bars) == 164
    carry_axis = carry_root.find("{http://www.w3.org/2000/svg}line")
    assert carry_axis is not None
    assert carry_axis.attrib["y1"] == "250.00"

    grid_root = _svg_root(campaign_d, "daily_grid_import_export.svg")
    grid_bars = [
        element
        for element in _svg_elements(grid_root, "rect")
        if "data-label" in element.attrib
    ]
    expected_grid_labels = {
        f"{result.case.case_id}|{summary.strategy}|day={day.scenario_day.day_index}|{flow}"
        for result in campaign_d.case_results
        for summary in (result.schedule, result.economic)
        for day in summary.days
        for flow in ("import", "export")
    }
    grid_values = tuple(
        value
        for result in campaign_d.case_results
        for summary in (result.schedule, result.economic)
        for day in summary.days
        for value in (day.kpi.grid_import_energy_kwh, -day.kpi.grid_export_energy_kwh)
    )
    lower, upper = min(0.0, min(grid_values)), max(1.0, max(grid_values))
    expected_baseline = 250 - (0.0 - lower) / max(upper - lower, 1.0) * 190
    grid_axis = grid_root.find("{http://www.w3.org/2000/svg}line")
    assert {bar.attrib["data-label"] for bar in grid_bars} == expected_grid_labels
    assert len(grid_bars) == 352
    assert grid_axis is not None
    assert isclose(float(grid_axis.attrib["y1"]), expected_baseline, abs_tol=0.01)
    assert float(grid_axis.attrib["y1"]) != 250.0
    assert "kWh" in "".join(grid_root.itertext())

    cost_root = _svg_root(campaign_d, "aggregate_adjusted_cost_comparison.svg")
    cost_bars = [
        element
        for element in _svg_elements(cost_root, "rect")
        if "data-label" in element.attrib
    ]
    assert {bar.attrib["data-label"] for bar in cost_bars} == set(summaries)
    assert len(cost_bars) == 12
    assert "CNY" in "".join(cost_root.itertext())
