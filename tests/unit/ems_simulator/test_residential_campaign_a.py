"""Contract tests for deterministic Residential EMS Campaign A tooling."""

from math import isclose
from pathlib import Path

from ems_simulator.residential_campaign_a import (
    _hard_passed,
    campaign_scenarios,
    run_residential_campaign_a,
)


def test_campaign_a_defines_exactly_24_unique_explicit_scenarios() -> None:
    scenarios = campaign_scenarios()

    assert len(scenarios) == 24
    assert len({scenario.scenario_id for scenario in scenarios}) == 24
    assert scenarios[0].scenario_id == "A01_REFERENCE_TASK175"
    assert scenarios[-1].scenario_id == "A24_HIGH_DEGRADATION_COST"
    assert all(
        scenario.forecast_semantics
        == "perfect_caller_supplied_forecast_equals_realized"
        for scenario in scenarios
    )
    assert all(
        scenario.export_policy == "export_allowed_settled" for scenario in scenarios
    )
    assert all(len(scenario.load_profile_kw) == 24 for scenario in scenarios)
    assert all(len(scenario.pv_profile_kw) == 24 for scenario in scenarios)
    assert all(
        len(scenario.import_tariff_profile_per_kwh) == 24 for scenario in scenarios
    )


def test_campaign_a_runs_48_completed_accepted_trajectories_and_anchor_cases(
    tmp_path: Path,
) -> None:
    campaign = run_residential_campaign_a(tmp_path)

    assert len(campaign.scenario_results) == 24
    paths = tuple(
        path
        for result in campaign.scenario_results
        for path in (result.schedule, result.economic)
    )
    assert len(paths) == 48
    assert campaign.hard_passed
    assert _hard_passed(paths)
    assert all(path.acceptance.passed for path in paths)
    assert all(path.kpi.comparison_reconciled for path in paths)
    assert all(path.kpi.ledger_reconciled for path in paths)
    assert all(
        result.schedule.trajectory.source_input.daily_mpc_input.integration_input
        is result.economic.trajectory.source_input.daily_mpc_input.integration_input
        and result.schedule.trajectory.source_input.daily_mpc_input.forecast_horizons
        is result.economic.trajectory.source_input.daily_mpc_input.forecast_horizons
        for result in campaign.scenario_results
    )

    by_id = {
        result.scenario.scenario_id: result for result in campaign.scenario_results
    }
    reference = by_id["A01_REFERENCE_TASK175"]
    assert reference.comparison.ranking.value == "tied"
    assert reference.schedule.kpi.load_energy_kwh == 27.1
    assert reference.schedule.kpi.pv_energy_kwh == 14.3
    assert isclose(
        reference.schedule.kpi.grid_import_energy_kwh,
        13.122438,
        abs_tol=1e-6,
    )
    assert isclose(reference.schedule.kpi.final_soc_fraction, 0.2, abs_tol=1e-12)

    negative = by_id["A02_NEGATIVE_ECONOMIC_SHIFT"]
    assert negative.comparison.ranking.value == "candidate_better"
    assert negative.comparison.delta_adjusted_cost < 0.0

    terminal = by_id["A03_TERMINAL_SOC_DIVERGENCE"]
    assert (
        terminal.schedule.kpi.final_soc_fraction
        > terminal.economic.kpi.final_soc_fraction
    )
    assert terminal.comparison.terminal_value_contribution > 0.0


def test_campaign_a_outputs_are_stable_across_repeated_runs(tmp_path: Path) -> None:
    first = run_residential_campaign_a(tmp_path / "first")
    second = run_residential_campaign_a(tmp_path / "second")

    assert first.hard_passed == second.hard_passed
    assert first.anomaly_shortlist == second.anomaly_shortlist
    for first_path, second_path in (
        (first.scenarios_csv_path, second.scenarios_csv_path),
        (first.results_csv_path, second.results_csv_path),
        (first.comparisons_csv_path, second.comparisons_csv_path),
        (first.findings_csv_path, second.findings_csv_path),
        (first.summary_path, second.summary_path),
    ):
        assert first_path.read_text(encoding="utf-8") == second_path.read_text(
            encoding="utf-8"
        )


def test_campaign_a_csv_outputs_include_required_evidence_columns(
    tmp_path: Path,
) -> None:
    campaign = run_residential_campaign_a(tmp_path)

    results_header = campaign.results_csv_path.read_text(encoding="utf-8").splitlines()[
        0
    ]
    comparisons_header = campaign.comparisons_csv_path.read_text(
        encoding="utf-8"
    ).splitlines()[0]
    findings_header = campaign.findings_csv_path.read_text(
        encoding="utf-8"
    ).splitlines()[0]
    assert "adjusted_net_economic_cost" in results_header
    assert "energy_balance_violation_count" in results_header
    assert "acceptance_status" in results_header
    assert "delta_adjusted_cost" in comparisons_header
    assert "dominant_components" in comparisons_header
    assert "severity" in findings_header
    assert "status" in findings_header


def test_campaign_loss_is_a_comparison_observation_not_an_acceptance_rule(
    tmp_path: Path,
) -> None:
    campaign = run_residential_campaign_a(tmp_path)

    # Campaign hard status is derived only from TASK-176 BLOCKER/MAJOR findings.
    # A comparison ranking is deliberately not read by _hard_passed.
    paths = tuple(
        path
        for result in campaign.scenario_results
        for path in (result.schedule, result.economic)
    )
    assert _hard_passed(paths)
    assert all(
        "ranking" not in finding.criterion_id
        for path in paths
        for finding in path.acceptance.findings
    )
