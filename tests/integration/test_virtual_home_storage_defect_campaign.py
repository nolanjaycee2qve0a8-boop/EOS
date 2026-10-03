"""Acceptance tests for the bounded simulated defect-finding campaign."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timedelta
from math import isclose
from pathlib import Path
from xml.etree import ElementTree

import pytest

from ems_simulator.economic_ledger import (
    DeterministicEconomicLedgerBuilder,
    EconomicLedgerInput,
)
from ems_simulator.economic_schedule_aware_comparison_demo import _schedule_runner
from examples.virtual_home_storage_defect_campaign.campaign import (
    CONFIGURATION,
    DEGRADATION_RATE,
    EXPORT_TARIFF,
    HOURS,
    TERMINAL_VALUE,
    CampaignResult,
    ScenarioSpec,
    _inputs,
    executable_scenarios,
    run_campaign,
)


@pytest.fixture(scope="module")
def campaign(tmp_path_factory: pytest.TempPathFactory) -> CampaignResult:
    return run_campaign(tmp_path_factory.mktemp("defect_campaign"))


def _spec(scenario_id: str) -> ScenarioSpec:
    return next(
        item for item in executable_scenarios() if item.scenario_id == scenario_id
    )


def _schedule(spec: ScenarioSpec, output_directory: Path):  # type: ignore[no-untyped-def]
    source, _ = _inputs(spec, output_directory)
    return _schedule_runner(CONFIGURATION).run(source)


def _output(campaign: CampaignResult, filename: str) -> Path:
    return next(path for path in campaign.output_paths if path.name == filename)


def test_matrix_has_18_unique_targeted_scenarios_and_machine_readable_contract(
    campaign: CampaignResult,
) -> None:
    with _output(campaign, "simulated_scenario_matrix.csv").open(
        encoding="utf-8", newline=""
    ) as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 18
    assert len({row["scenario_id"] for row in rows}) == 18
    assert {row["scenario_id"] for row in rows} == {
        *(
            f"S{index:02d}_{suffix}"
            for index, suffix in (
                (1, "MIN_SOC_LOAD"),
                (2, "MAX_SOC_PV"),
                (3, "EXACT_MAX_FILL"),
                (4, "EXACT_MIN_DRAIN"),
                (5, "PV_STEP_UP"),
                (6, "LOAD_STEP_UP"),
                (7, "CHARGE_LIMIT"),
                (8, "DISCHARGE_LIMIT"),
                (9, "ZERO_EXPORT_FULL"),
                (10, "NEGATIVE_PRICE"),
                (11, "PRICE_SPIKE_IDLE"),
                (12, "FALSE_PV_FORECAST"),
                (13, "MISSED_LOAD_SPIKE"),
                (14, "CROSS_MIDNIGHT"),
                (15, "LOW_EFFICIENCY"),
                (16, "23_POINT_CURVE"),
                (17, "NAN_PV"),
                (18, "HALF_HOUR_STEP"),
            )
        )
    }
    assert all(row["goal"] and row["explicit_input"] for row in rows)
    assert all(row["expected"] and row["existing_coverage"] for row in rows)
    json_rows = json.loads(
        _output(campaign, "simulated_scenario_matrix.json").read_text(encoding="utf-8")
    )
    assert json_rows == rows

    explicit = {
        row["scenario_id"]: json.loads(row["explicit_input"])
        for row in rows
        if row["scenario_id"]
        not in {
            "S16_23_POINT_CURVE",
            "S17_NAN_PV",
            "S18_HALF_HOUR_STEP",
        }
    }
    assert explicit["S12_FALSE_PV_FORECAST"]["realized_pv_kw"][12] == 0.0
    assert explicit["S12_FALSE_PV_FORECAST"]["forecast_pv_kw"][12] == 5.0
    assert explicit["S13_MISSED_LOAD_SPIKE"]["realized_load_kw"][18] == 6.0
    assert explicit["S13_MISSED_LOAD_SPIKE"]["forecast_load_kw"][18] == 0.0
    assert (
        explicit["S10_NEGATIVE_PRICE"]["realized_tariff_cny_per_kwh"][:6] == [-0.2] * 6
    )


def test_manual_threshold_limit_and_efficiency_results_use_fixed_external_values(
    tmp_path: Path,
) -> None:
    cases = {
        "S03_EXACT_MAX_FILL": (0, 0.5263157894736842, 0.0, 1.0),
        "S04_EXACT_MIN_DRAIN": (0, -0.475, 0.0, 0.2),
        "S07_CHARGE_LIMIT": (0, 3.0, -7.0, 0.785),
        "S08_DISCHARGE_LIMIT": (0, -3.0, 7.0, 0.6842105263157895),
    }
    for scenario_id, (hour, battery, grid, soc) in cases.items():
        result = _schedule(_spec(scenario_id), tmp_path / scenario_id)
        trace = result.step_traces[hour]
        state = trace.simulation_trace.state
        assert isclose(state.battery_result.actual_power_kw, battery, abs_tol=1e-12)
        assert isclose(state.grid_result.actual_grid_power_kw, grid, abs_tol=1e-12)
        assert isclose(state.battery_result.next_state.soc, soc, abs_tol=1e-12)
        assert (
            trace.feasible_decision.source_decision
            is trace.decision_provenance.decision
        )
        assert trace.handoff.source_feasible_decision is trace.feasible_decision
        assert (
            trace.simulation_trace.simulation_input.battery_input.actuation
            is trace.handoff.actuation
        )

    low_efficiency = _schedule(_spec("S15_LOW_EFFICIENCY"), tmp_path / "low_eff")
    assert (
        low_efficiency.step_traces[
            8
        ].simulation_trace.state.battery_result.actual_power_kw
        == 2.0
    )
    assert (
        low_efficiency.step_traces[
            18
        ].simulation_trace.state.battery_result.actual_power_kw
        == -1.0
    )
    # Independent: 0.50 + 2*0.8/10 - 1/0.8/10 = 0.535.
    assert isclose(
        low_efficiency.step_traces[
            -1
        ].simulation_trace.state.battery_result.next_state.soc,
        0.535,
        abs_tol=1e-12,
    )


def test_findings_distinguish_contract_defects_strategy_limits_and_input_rejection(
    campaign: CampaignResult,
) -> None:
    counts = Counter(item.status for item in campaign.path_results)
    assert counts == {
        "PASS": 16,
        "LIMITATION": 8,
        "FAIL": 8,
        "REJECTED_AS_EXPECTED": 3,
    }
    codes = {item.finding_code for item in campaign.path_results if item.finding_code}
    assert {
        "NEGATIVE_REALIZED_NET_COST_REJECTED",
        "NEGATIVE_TARIFF_LEDGER_REJECTED",
        "ZERO_EXPORT_NOT_ENFORCED_NO_CURTAILMENT",
        "NO_PRICE_ONLY_ARBITRAGE",
        "FALSE_PV_FORECAST_CAUSES_GRID_CHARGE",
        "MISSED_LOAD_SPIKE_NO_DISCHARGE",
        "INVALID_INPUT_FAIL_CLOSED",
    } == codes

    zero_export = next(
        item
        for item in campaign.path_results
        if item.scenario_id == "S09_ZERO_EXPORT_FULL" and item.strategy == "Schedule"
    )
    assert zero_export.status == "LIMITATION"
    assert zero_export.total_export_kwh == 10.0
    assert zero_export.independent_export_revenue_cny == 2.0
    assert zero_export.independent_degradation_cost_cny == 0.0
    assert zero_export.independent_net_cost_cny == -2.0

    independent_net_costs = {
        scenario_id: next(
            item
            for item in campaign.path_results
            if item.scenario_id == scenario_id and item.strategy == "Schedule"
        ).independent_net_cost_cny
        for scenario_id in (
            "S02_MAX_SOC_PV",
            "S05_PV_STEP_UP",
            "S07_CHARGE_LIMIT",
        )
    }
    assert independent_net_costs["S02_MAX_SOC_PV"] == -0.4
    assert independent_net_costs["S05_PV_STEP_UP"] == pytest.approx(-0.05)
    assert independent_net_costs["S07_CHARGE_LIMIT"] == -1.25

    false_pv = next(
        item
        for item in campaign.path_results
        if item.scenario_id == "S12_FALSE_PV_FORECAST" and item.strategy == "Schedule"
    )
    assert false_pv.total_import_kwh == 5.0
    assert false_pv.total_battery_throughput_kwh == 3.0

    missed_load = next(
        item
        for item in campaign.path_results
        if item.scenario_id == "S13_MISSED_LOAD_SPIKE" and item.strategy == "Schedule"
    )
    assert missed_load.total_import_kwh == 6.0
    assert missed_load.total_battery_throughput_kwh == 0.0


def test_negative_tariff_and_negative_net_cost_are_minimal_core_reproductions(
    tmp_path: Path,
) -> None:
    negative_price = _spec("S10_NEGATIVE_PRICE")
    trajectory = _schedule(negative_price, tmp_path / "negative_price")
    actual_import_cost = 0.0
    for trace in trajectory.step_traces:
        state = trace.simulation_trace.state
        grid = max(state.grid_result.actual_grid_power_kw, 0.0)
        actual_import_cost += grid * state.tariff_result.import_price_cny_per_kwh
    assert isclose(actual_import_cost, -1.0526315789473686, abs_tol=1e-12)
    with pytest.raises(
        ValueError, match="import_tariff_per_kwh must be finite and non-negative"
    ):
        DeterministicEconomicLedgerBuilder().build(
            EconomicLedgerInput(
                trajectory,
                (EXPORT_TARIFF,) * HOURS,
                (DEGRADATION_RATE,) * HOURS,
                TERMINAL_VALUE,
                negative_price.battery_model,
            )
        )

    export_only = _spec("S02_MAX_SOC_PV")
    export_trajectory = _schedule(export_only, tmp_path / "export_only")
    with pytest.raises(
        ValueError, match="total_realized_net_cost must be finite and non-negative"
    ):
        DeterministicEconomicLedgerBuilder().build(
            EconomicLedgerInput(
                export_trajectory,
                (EXPORT_TARIFF,) * HOURS,
                (DEGRADATION_RATE,) * HOURS,
                TERMINAL_VALUE,
                export_only.battery_model,
            )
        )


def test_cross_midnight_carries_actual_soc_and_keeps_strategy_chains_separate(
    campaign: CampaignResult,
) -> None:
    rows = [
        item
        for item in campaign.path_results
        if item.scenario_id == "S14_CROSS_MIDNIGHT"
    ]
    assert [(row.strategy, row.day_index) for row in rows] == [
        ("Schedule", 1),
        ("Schedule", 2),
        ("Economic", 1),
        ("Economic", 2),
    ]
    for strategy in ("Schedule", "Economic"):
        day1, day2 = (row for row in rows if row.strategy == strategy)
        assert day1.final_soc is not None
        assert isclose(day1.final_soc, 0.69, abs_tol=1e-12)
        assert day2.initial_soc == day1.final_soc
        day2_start = datetime.fromisoformat(day2.first_timestamp_utc)
        day1_end = datetime.fromisoformat(day1.last_timestamp_utc)
        assert day2_start == day1_end + timedelta(hours=1)
        assert day1.last_timestamp_utc == "2026-03-01T23:00:00+00:00"
        assert day2.first_timestamp_utc == "2026-03-02T00:00:00+00:00"
        assert day2.status == "PASS"


def test_outputs_are_deterministic_labeled_parseable_and_report_scope(
    tmp_path: Path,
    campaign: CampaignResult,
) -> None:
    repeated = run_campaign(tmp_path / "repeated")
    first = {path.name: path for path in campaign.output_paths}
    second = {path.name: path for path in repeated.output_paths}
    assert first.keys() == second.keys()
    assert {name: path.read_bytes() for name, path in first.items()} == {
        name: path.read_bytes() for name, path in second.items()
    }

    root = ElementTree.parse(first["simulated_defect_findings.svg"]).getroot()
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    svg = first["simulated_defect_findings.svg"].read_text(encoding="utf-8")
    assert "SIMULATED" in svg and "非真实设备采集" in svg

    report = first["simulated_defect_report_zh.md"].read_text(encoding="utf-8")
    for heading in (
        "跨合同与 ledger 缺陷",
        "策略与产品能力局限",
        "输入合同拒绝",
        "Simulator 与测试缺口",
        "建议的下一修复顺序",
    ):
        assert heading in report
    assert "不是 PCS/BMS、HIL" in report
