"""Acceptance tests for the 24-hour simulated household teaching wrapper."""

import csv
import json
from math import isclose
from pathlib import Path
from xml.etree import ElementTree

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
)
from examples.virtual_home_storage_day.demo import (
    DayTeachingResult,
    run_day_teaching_demo,
)


def _run(tmp_path: Path) -> DayTeachingResult:
    return run_day_teaching_demo(tmp_path / "day")


def test_day_uses_existing_economic_result_and_preserves_identity_chain(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path)
    completed = result.source_result.economic.result
    assert isinstance(
        completed, EconomicMultiOpportunityExplainableMPCDailySimulationResult
    )
    assert completed.source_input is result.source_result.economic_input
    assert len(completed.step_traces) == 24

    for trace in completed.step_traces:
        decision = trace.decision_provenance.decision
        feasible = trace.feasible_decision
        handoff = trace.handoff
        battery_input = trace.simulation_trace.simulation_input.battery_input
        battery_result = trace.simulation_trace.state.battery_result
        assert decision.source_context is trace.context
        assert trace.decision_provenance.source_context is trace.context
        assert feasible.source_decision is decision
        assert feasible.source_provenance is trace.decision_provenance
        assert handoff.source_feasible_decision is feasible
        assert battery_input.actuation is handoff.actuation
        assert battery_result.simulation_input is battery_input


def test_hourly_output_covers_one_day_and_reconciles_power_energy_soc_and_cost(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path)
    rows = json.loads(result.hourly_json_path.read_text(encoding="utf-8"))
    assert len(rows) == 24
    assert [row["hour"] for row in rows] == list(range(24))
    timestamps = [row["timestamp"] for row in rows]
    assert timestamps[0] == "2026-02-01T00:00:00+00:00"
    assert timestamps[-1] == "2026-02-01T23:00:00+00:00"
    assert all(row["duration_hours"] == 1.0 for row in rows)

    previous_soc = 0.50
    total_import_cost = 0.0
    total_export_revenue = 0.0
    total_degradation_cost = 0.0
    for row in rows:
        pv = row["pv_kw"]
        load = row["load_kw"]
        battery = row["actual_battery_kw_signed"]
        grid = row["actual_grid_kw_signed"]
        assert isclose(pv + grid - battery, load, rel_tol=0.0, abs_tol=1e-12)
        assert row["grid_import_kw"] == max(grid, 0.0)
        assert row["grid_export_kw"] == max(-grid, 0.0)
        assert row["grid_import_kwh"] == row["grid_import_kw"]
        assert row["grid_export_kwh"] == row["grid_export_kw"]

        # Independent one-hour hand calculation from the documented battery model.
        expected_soc = previous_soc + (
            battery * 0.95 / 10.0 if battery >= 0.0 else battery / 0.95 / 10.0
        )
        assert isclose(row["soc_before_fraction"], previous_soc, abs_tol=1e-12)
        assert isclose(row["soc_after_fraction"], expected_soc, abs_tol=1e-12)
        assert 0.20 <= row["soc_after_fraction"] <= 1.0
        assert -3.0 <= battery <= 3.0
        previous_soc = row["soc_after_fraction"]

        expected_import_cost = row["grid_import_kwh"] * row["import_tariff_cny_per_kwh"]
        expected_export_revenue = row["grid_export_kwh"] * 0.20
        expected_degradation = abs(battery) * 0.05
        assert isclose(
            row["realized_import_cost_cny"], expected_import_cost, abs_tol=1e-12
        )
        assert isclose(
            row["realized_export_revenue_cny"],
            expected_export_revenue,
            abs_tol=1e-12,
        )
        assert isclose(
            row["battery_degradation_cost_cny"],
            expected_degradation,
            abs_tol=1e-12,
        )
        total_import_cost += expected_import_cost
        total_export_revenue += expected_export_revenue
        total_degradation_cost += expected_degradation

    ledger = result.source_result.economic.ledger
    assert isclose(previous_soc, 0.20, abs_tol=1e-12)
    assert isclose(total_import_cost, 5.17448753462604, abs_tol=1e-12)
    assert isclose(total_export_revenue, 0.5318559556786707, abs_tol=1e-12)
    assert isclose(total_degradation_cost, 0.6431578947368422, abs_tol=1e-12)
    assert isclose(total_import_cost, ledger.total_realized_import_cost, abs_tol=1e-12)
    assert isclose(
        total_export_revenue, ledger.total_realized_export_revenue, abs_tol=1e-12
    )
    assert isclose(
        total_degradation_cost,
        ledger.total_battery_degradation_cost,
        abs_tol=1e-12,
    )


def test_key_hours_show_price_gate_pv_charge_discharge_and_soc_revision(
    tmp_path: Path,
) -> None:
    result = _run(tmp_path)
    rows = json.loads(result.hourly_json_path.read_text(encoding="utf-8"))
    overnight, pv_charge, discharge, revised = (rows[index] for index in (0, 8, 18, 21))

    assert overnight["decision_action"] == "charge"
    assert overnight["economic_supported_grid_charge_kw"] == 1.0224376731301954
    assert "价格参与" in overnight["price_decision_role"]
    assert overnight["actual_grid_kw_signed"] == 1.8224376731301954

    assert pv_charge["pv_kw"] == 2.0 and pv_charge["load_kw"] == 0.8
    assert pv_charge["decision_action"] == "charge"
    assert pv_charge["economic_supported_grid_charge_kw"] is None
    assert "绕过" in pv_charge["price_decision_role"]
    assert pv_charge["actual_battery_kw_signed"] == 1.2

    assert discharge["import_tariff_cny_per_kwh"] == 0.9
    assert discharge["decision_action"] == "discharge"
    assert discharge["actual_battery_kw_signed"] == -2.0
    assert discharge["actual_grid_kw_signed"] == 0.0

    assert revised["candidate_request_kw_magnitude"] == 1.8
    assert isclose(revised["decision_request_kw_magnitude"], 0.9, abs_tol=1e-12)
    assert revised["revision_reasons"] == ["min_soc_limit"]
    assert revised["soc_after_fraction"] == 0.2
    expected_explanation = "最终决策" + chr(0xFF1A) + "放电 0.9 kW"
    assert expected_explanation in revised["decision_explanation_zh"]


def test_exports_are_labeled_parseable_aligned_and_deterministic(
    tmp_path: Path,
) -> None:
    first = _run(tmp_path / "first")
    second = _run(tmp_path / "second")
    first_paths = (
        first.hourly_csv_path,
        first.hourly_json_path,
        first.key_events_path,
        first.summary_path,
        first.linked_curve_path,
    )
    second_paths = (
        second.hourly_csv_path,
        second.hourly_json_path,
        second.key_events_path,
        second.summary_path,
        second.linked_curve_path,
    )
    assert [path.read_bytes() for path in first_paths] == [
        path.read_bytes() for path in second_paths
    ]
    with first.hourly_csv_path.open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    json_rows = json.loads(first.hourly_json_path.read_text(encoding="utf-8"))
    assert len(csv_rows) == len(json_rows) == 24
    assert all("SIMULATED" in row["label"] for row in json_rows)

    root = ElementTree.parse(first.linked_curve_path).getroot()
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    polylines = root.findall("svg:polyline", namespace)
    assert len(polylines) == 6
    assert all(len(item.attrib["points"].split()) == 24 for item in polylines)
    soc_y_coordinates = [
        float(point.split(",")[1]) for point in polylines[-1].attrib["points"].split()
    ]
    assert min(soc_y_coordinates) == 390.0  # 100% SOC upper boundary.
    assert max(soc_y_coordinates) == 520.0  # 20% SOC lower boundary.
    svg_text = first.linked_curve_path.read_text(encoding="utf-8")
    for label in ("SIMULATED", "PV", "家庭负载", "电池", "购电", "售电", "SOC"):
        assert label in svg_text

    summary = first.summary_path.read_text(encoding="utf-8")
    events = first.key_events_path.read_text(encoding="utf-8")
    for required in (
        "仅模拟",
        "perfect forecast",
        "不是设备命令",
        "不代表真实合同或优化收益",
    ):
        assert required in summary
    assert "现有中文约束解释" in events
    assert "min_soc_limit" in events
