"""Contract tests for the post-freeze Residential EMS Campaign B tooling."""

from collections import Counter
from pathlib import Path

from ems_simulator.residential_campaign_b import (
    _bar_svg,
    campaign_b_scenarios,
    run_residential_campaign_b,
)


def test_campaign_b_defines_exact_72_cell_boundary_matrix() -> None:
    scenarios = campaign_b_scenarios()

    assert len(scenarios) == 72
    assert len({scenario.scenario_id for scenario in scenarios}) == 72
    assert Counter(scenario.matrix_group for scenario in scenarios) == {
        "B1_PCS": 18,
        "B2_SOC": 12,
        "B3_TARIFF": 18,
        "B4_ACCOUNTING": 24,
    }
    assert all(
        scenario.campaign_scenario.forecast_semantics
        == "perfect_caller_supplied_forecast_equals_realized"
        for scenario in scenarios
    )
    assert sum(scenario.accounting_only for scenario in scenarios) == 24


def test_campaign_b_runs_144_logical_paths_with_fixed_control_for_b4(
    tmp_path: Path,
) -> None:
    campaign = run_residential_campaign_b(tmp_path)
    paths = tuple(
        path
        for result in campaign.scenario_results
        for path in (result.schedule, result.economic)
    )

    assert len(campaign.scenario_results) == 72
    assert len(paths) == 144
    assert campaign.unique_control_execution_count == 102
    assert campaign.hard_passed
    assert all(path.acceptance.passed for path in paths)
    assert all(path.kpi.ledger_reconciled for path in paths)
    assert all(path.kpi.comparison_reconciled for path in paths)
    assert all(path.kpi.provenance_complete for path in paths)

    b4 = tuple(
        result
        for result in campaign.scenario_results
        if result.scenario.matrix_group == "B4_ACCOUNTING"
    )
    assert len(b4) == 24
    assert all(result.control_reused for result in b4)
    # Every B4 case references one of three already-completed fixed trajectory pairs.
    assert len({id(result.schedule.trajectory) for result in b4}) == 3
    assert len({id(result.economic.trajectory) for result in b4}) == 3
    assert all(
        result.schedule.trajectory is not result.economic.trajectory for result in b4
    )


def test_campaign_b_output_is_repeatable_and_contains_required_evidence(
    tmp_path: Path,
) -> None:
    first = run_residential_campaign_b(tmp_path / "first")
    second = run_residential_campaign_b(tmp_path / "second")

    assert first.hard_passed == second.hard_passed
    assert first.anomaly_shortlist == second.anomaly_shortlist
    first_files = {path.name: path for path in first.output_paths}
    second_files = {path.name: path for path in second.output_paths}
    assert first_files.keys() == second_files.keys()
    for name in first_files:
        assert first_files[name].read_text(encoding="utf-8") == second_files[
            name
        ].read_text(encoding="utf-8")
    assert {
        "campaign_b_scenarios.csv",
        "campaign_b_results.csv",
        "campaign_b_comparisons.csv",
        "campaign_b_findings.csv",
        "campaign_b_summary.txt",
        "campaign_b_pcs_sweep.csv",
        "campaign_b_soc_sweep.csv",
        "campaign_b_tariff_sweep.csv",
        "campaign_b_accounting_sensitivity.csv",
    }.issubset(first_files)
    assert (
        "adjusted_net_economic_cost"
        in first_files["campaign_b_results.csv"]
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert (
        "delta_adjusted_cost"
        in first_files["campaign_b_comparisons.csv"]
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )


def test_campaign_b_svg_zero_axis_uses_the_computed_data_zero_baseline() -> None:
    svg = _bar_svg("mixed values", (("negative", -1.0), ("positive", 1.0)))

    assert 'id="zero-axis" x1="40" y1="155.00" x2="990" y2="155.00"' in svg
    assert 'id="zero-axis" x1="40" y1="250.00"' not in svg


def test_campaign_b_svg_reporting_labels_swept_dimensions_and_b4_provenance(
    tmp_path: Path,
) -> None:
    campaign = run_residential_campaign_b(tmp_path)
    outputs = {
        path.name: path.read_text(encoding="utf-8") for path in campaign.output_paths
    }

    assert "PCS=0.50kW | reference" in outputs["pcs_power_vs_physical_revisions.svg"]
    assert "SOC=0.20 | reference" in outputs["initial_soc_vs_grid_import.svg"]
    assert (
        "TOU=0.50/0.50/0.50 | reference"
        in outputs["tariff_spread_vs_strategy_delta.svg"]
    )

    export = outputs["export_tariff_vs_strategy_delta.svg"]
    degradation = outputs["degradation_vs_strategy_delta.svg"]
    terminal = outputs["terminal_value_vs_strategy_delta.svg"]
    for chart in (export, degradation, terminal):
        assert "B4_01_E1_NEGATIVE_SHIFT | E1_NEGATIVE_SHIFT |" in chart
    assert "export_tariff=" in export
    assert "degradation_rate=" in degradation
    assert "terminal_value=" in terminal
    assert export != degradation
    assert degradation != terminal


def test_campaign_b_svg_escapes_data_derived_text() -> None:
    svg = _bar_svg('title <& "', (('label <& "', -1.0),))

    assert 'title &lt;&amp; "' in svg
    assert 'label &lt;&amp; "' in svg
    assert 'data-label="label &lt;&amp; &quot;"' in svg
