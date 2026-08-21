"""Export six frozen Campaign-A trajectories for leadership-report evidence.

This tool is reporting-only.  It invokes the existing Campaign-A scenario
composition unchanged, then reads realized Simulator trace fields.  It never
uses planned power as executed power and never changes the frozen control path.
"""

# The deterministic SVG builder intentionally keeps XML fragments on single
# lines so generated evidence remains easy to compare byte-for-byte.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from html import escape
from math import isclose, isfinite
from pathlib import Path

from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.residential_acceptance import (
    DeterministicResidentialAcceptanceEvaluator,
)
from ems_simulator.residential_campaign_a import (
    ResidentialCampaignPathResult,
    ResidentialCampaignScenario,
    _run_scenario,
    campaign_scenarios,
)

SCENARIOS = (
    ("A01_REFERENCE_TASK175", "Reference"),
    ("A10_HIGH_PV", "High PV"),
    ("A16_EVENING_PEAK", "High evening load"),
)
STRATEGIES = ("Schedule", "Economic")
TOLERANCE = 1e-12


@dataclass(frozen=True, slots=True)
class LeadershipReportResult:
    output_directory: Path
    hourly_csv: Path
    summary_csv: Path
    comparison_csv: Path
    manifest_csv: Path
    charts: tuple[Path, ...]
    paths: tuple[ResidentialCampaignPathResult, ...]


def _number(value: float) -> str:
    if not isfinite(value):
        raise ValueError("report values must be finite")
    return f"{0.0 if value == 0.0 else value:.12f}"


def _fingerprint(values: tuple[float, ...]) -> str:
    payload = ",".join(_number(value) for value in values)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _combined_fingerprint(scenario: ResidentialCampaignScenario) -> str:
    payload = "|".join(
        (
            f"pv:{_fingerprint(scenario.pv_profile_kw)}",
            f"load:{_fingerprint(scenario.load_profile_kw)}",
            f"tariff:{_fingerprint(scenario.import_tariff_profile_per_kwh)}",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _selected_scenarios() -> tuple[tuple[ResidentialCampaignScenario, str], ...]:
    by_id = {scenario.scenario_id: scenario for scenario in campaign_scenarios()}
    selected = tuple(
        (by_id[scenario_id], environment) for scenario_id, environment in SCENARIOS
    )
    if len(selected) != 3 or len({id(item[0]) for item in selected}) != 3:
        raise AssertionError("three distinct frozen Campaign-A scenarios are required")
    return selected


def _write_csv(
    path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]
) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _path_rows(
    path: ResidentialCampaignPathResult, environment: str
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    charge_total = discharge_total = import_total = export_total = 0.0
    for index, trace in enumerate(path.trajectory.step_traces):
        if not isinstance(
            trace,
            MultiOpportunityExplainableMPCDailySimulationStepTrace
            | EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
        ):
            raise TypeError("Campaign-A trace must retain a daily Simulator trace")
        simulation_trace = trace.simulation_trace
        identity = simulation_trace.simulation_input.step_identity
        state = simulation_trace.state
        if identity.timestamp is None or identity.timestamp.tzinfo is None:
            raise ValueError("typical-curve trace requires timezone-aware timestamps")
        if index:
            previous_timestamp = path.trajectory.step_traces[
                index - 1
            ].simulation_trace.simulation_input.step_identity.timestamp
            if previous_timestamp is None or identity.timestamp <= previous_timestamp:
                raise ValueError("typical-curve timestamps must be strictly increasing")
        duration_hours = identity.duration_seconds / 3600.0
        battery = state.battery_result.actual_power_kw
        grid = state.grid_result.actual_grid_power_kw
        charge_total += max(battery, 0.0) * duration_hours
        discharge_total += max(-battery, 0.0) * duration_hours
        import_total += max(grid, 0.0) * duration_hours
        export_total += max(-grid, 0.0) * duration_hours
        values = (
            state.pv_result.actual_power_kw,
            state.load_result.actual_power_kw,
            state.tariff_result.import_price_cny_per_kwh,
            battery,
            grid,
            state.battery_result.simulation_input.source_state.soc,
            state.battery_result.next_state.soc,
            duration_hours,
        )
        if not all(isfinite(value) for value in values):
            raise ValueError("trace contains non-finite report fact")
        rows.append(
            {
                "scenario_id": path.scenario.scenario_id,
                "source_environment": environment,
                "strategy": path.strategy,
                "step_index": str(index),
                "timestamp": identity.timestamp.isoformat(),
                "timezone": str(identity.timestamp.tzinfo),
                "step_duration_seconds": _number(identity.duration_seconds),
                "realized_pv_power_kw": _number(state.pv_result.actual_power_kw),
                "realized_load_power_kw": _number(state.load_result.actual_power_kw),
                "realized_import_tariff_per_kwh": _number(
                    state.tariff_result.import_price_cny_per_kwh
                ),
                "actual_battery_ac_power_kw": _number(battery),
                "actual_grid_ac_power_kw": _number(grid),
                "soc_initial_fraction": _number(
                    state.battery_result.simulation_input.source_state.soc
                ),
                "soc_final_fraction": _number(state.battery_result.next_state.soc),
                "interval_battery_charge_energy_kwh": _number(
                    max(battery, 0.0) * duration_hours
                ),
                "interval_battery_discharge_energy_kwh": _number(
                    max(-battery, 0.0) * duration_hours
                ),
                "interval_grid_import_energy_kwh": _number(
                    max(grid, 0.0) * duration_hours
                ),
                "interval_grid_export_energy_kwh": _number(
                    max(-grid, 0.0) * duration_hours
                ),
                "cumulative_battery_charge_energy_kwh": _number(charge_total),
                "cumulative_battery_discharge_energy_kwh": _number(discharge_total),
                "cumulative_grid_import_energy_kwh": _number(import_total),
                "cumulative_grid_export_energy_kwh": _number(export_total),
                "pv_source": "SIMULATOR_ACTUAL_REALIZED",
                "load_source": "SIMULATOR_ACTUAL_REALIZED",
                "battery_power_source": "SIMULATOR_ACTUAL",
                "grid_power_source": "SIMULATOR_ACTUAL",
                "soc_point_semantics": "INTERVAL_FINAL_SIMULATOR_NEXT_STATE",
            }
        )
    if len(rows) != 24:
        raise AssertionError("every selected path must have 24 hourly records")
    return rows


def _summary_row(
    path: ResidentialCampaignPathResult, environment: str, rows: list[dict[str, str]]
) -> dict[str, str]:
    battery = [float(row["actual_battery_ac_power_kw"]) for row in rows]
    grid = [float(row["actual_grid_ac_power_kw"]) for row in rows]
    soc = [float(row["soc_final_fraction"]) for row in rows]
    ledger = path.ledger
    charge = sum(float(row["interval_battery_charge_energy_kwh"]) for row in rows)
    discharge = sum(float(row["interval_battery_discharge_energy_kwh"]) for row in rows)
    grid_import = sum(float(row["interval_grid_import_energy_kwh"]) for row in rows)
    grid_export = sum(float(row["interval_grid_export_energy_kwh"]) for row in rows)
    if not (
        isclose(
            grid_import,
            ledger.total_grid_import_energy_kwh,
            rel_tol=0.0,
            abs_tol=TOLERANCE,
        )
        and isclose(
            grid_export,
            ledger.total_grid_export_energy_kwh,
            rel_tol=0.0,
            abs_tol=TOLERANCE,
        )
    ):
        raise AssertionError("hourly grid energy must reconcile to existing ledger")
    return {
        "scenario_id": path.scenario.scenario_id,
        "source_environment": environment,
        "strategy": path.strategy,
        "initial_soc_fraction": _number(float(rows[0]["soc_initial_fraction"])),
        "final_soc_fraction": _number(float(rows[-1]["soc_final_fraction"])),
        "minimum_soc_fraction": _number(min(soc)),
        "maximum_soc_fraction": _number(max(soc)),
        "total_pv_energy_kwh": _number(ledger.total_pv_energy_kwh),
        "total_load_energy_kwh": _number(ledger.total_load_energy_kwh),
        "battery_charge_energy_kwh": _number(charge),
        "battery_discharge_energy_kwh": _number(discharge),
        "grid_import_energy_kwh": _number(grid_import),
        "grid_export_energy_kwh": _number(grid_export),
        "peak_battery_charge_kw": _number(max(battery)),
        "peak_battery_discharge_kw": _number(min(battery)),
        "peak_grid_import_kw": _number(max(grid)),
        "peak_grid_export_kw": _number(min(grid)),
        "physical_revision_count": str(path.kpi.physical_revision_count),
        "adjusted_net_economic_cost": _number(ledger.adjusted_net_economic_cost),
        "acceptance_status": "PASS" if path.acceptance.passed else "FAIL",
    }


def _polyline(
    values: list[float],
    x: float,
    y: float,
    width: float,
    height: float,
    low: float,
    high: float,
) -> str:
    span = max(high - low, 1e-9)
    points = []
    for index, value in enumerate(values):
        point_x = x + width * index / max(len(values) - 1, 1)
        point_y = y + height * (high - value) / span
        points.append(f"{point_x:.2f},{point_y:.2f}")
    return " ".join(points)


def _svg_text(value: object) -> str:
    return escape(str(value), quote=True)


def _draw_panel(
    title: str,
    series: list[tuple[str, list[float], str, str]],
    x: float,
    y: float,
    width: float,
    height: float,
    zero_axis: bool = False,
) -> str:
    all_values = [value for _, values, _, _ in series for value in values]
    low, high = min(all_values), max(all_values)
    margin = max((high - low) * 0.12, 0.15)
    low -= margin
    high += margin
    parts = [
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="#FFFFFF" stroke="#D7DEE8"/>',
        f'<text x="{x + 8}" y="{y + 18}" font-size="14" font-weight="700" fill="#102A43">{_svg_text(title)}</text>',
    ]
    for fraction in (0.25, 0.5, 0.75):
        line_y = y + height * fraction
        parts.append(
            f'<line x1="{x + 45}" y1="{line_y:.2f}" x2="{x + width - 10}" y2="{line_y:.2f}" stroke="#E8EEF5"/>'
        )
    if zero_axis and low <= 0.0 <= high:
        zero_y = y + height * (high / (high - low))
        parts.append(
            f'<line x1="{x + 45}" y1="{zero_y:.2f}" x2="{x + width - 10}" y2="{zero_y:.2f}" stroke="#6B7C93" stroke-width="1.4"/>'
        )
    parts.append(
        f'<text x="{x + 2}" y="{y + 34}" font-size="10" fill="#486581">{high:.2f}</text>'
    )
    parts.append(
        f'<text x="{x + 2}" y="{y + height - 2}" font-size="10" fill="#486581">{low:.2f}</text>'
    )
    for _label, values, color, dash in series:
        points = _polyline(values, x + 45, y + 28, width - 55, height - 45, low, high)
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2.3"{dash_attribute}/>'
        )
    legend_x = x + 52
    for _index, (label, _, color, dash) in enumerate(series):
        legend_y = y + height - 8
        dash_attribute = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="{legend_x}" y1="{legend_y - 3}" x2="{legend_x + 16}" y2="{legend_y - 3}" stroke="{color}" stroke-width="2"{dash_attribute}/><text x="{legend_x + 20}" y="{legend_y}" font-size="10" fill="#243B53">{_svg_text(label)}</text>'
        )
        legend_x += 20 + len(label) * 6.5
    return "".join(parts)


def _scenario_svg(
    scenario: ResidentialCampaignScenario,
    environment: str,
    rows_by_strategy: dict[str, list[dict[str, str]]],
) -> str:
    schedule = rows_by_strategy["Schedule"]
    economic = rows_by_strategy["Economic"]
    identical = all(
        isclose(
            float(left["actual_battery_ac_power_kw"]),
            float(right["actual_battery_ac_power_kw"]),
            rel_tol=0.0,
            abs_tol=TOLERANCE,
        )
        and isclose(
            float(left["actual_grid_ac_power_kw"]),
            float(right["actual_grid_ac_power_kw"]),
            rel_tol=0.0,
            abs_tol=TOLERANCE,
        )
        and isclose(
            float(left["soc_final_fraction"]),
            float(right["soc_final_fraction"]),
            rel_tol=0.0,
            abs_tol=TOLERANCE,
        )
        for left, right in zip(schedule, economic, strict=True)
    )
    selected = schedule
    power_series = [
        (
            "Battery actual",
            [float(row["actual_battery_ac_power_kw"]) for row in selected],
            "#2563EB",
            "",
        )
    ]
    grid_series = [
        (
            "Grid actual",
            [float(row["actual_grid_ac_power_kw"]) for row in selected],
            "#DC2626",
            "",
        )
    ]
    soc_series = [
        (
            "SOC final",
            [100 * float(row["soc_final_fraction"]) for row in selected],
            "#0F766E",
            "",
        )
    ]
    cumulative_series = [
        (
            "Battery charge",
            [float(row["cumulative_battery_charge_energy_kwh"]) for row in selected],
            "#2563EB",
            "",
        ),
        (
            "Battery discharge",
            [float(row["cumulative_battery_discharge_energy_kwh"]) for row in selected],
            "#7C3AED",
            "",
        ),
        (
            "Grid import",
            [float(row["cumulative_grid_import_energy_kwh"]) for row in selected],
            "#DC2626",
            "",
        ),
        (
            "Grid export",
            [float(row["cumulative_grid_export_energy_kwh"]) for row in selected],
            "#D97706",
            "",
        ),
    ]
    exogenous = [
        (
            "PV realized",
            [float(row["realized_pv_power_kw"]) for row in selected],
            "#16A34A",
            "",
        ),
        (
            "Load realized",
            [float(row["realized_load_power_kw"]) for row in selected],
            "#111827",
            "",
        ),
    ]
    note = (
        "Schedule = Economic, independently executed and verified"
        if identical
        else "Schedule/Economic differ; paired actual lines retained in CSV"
    )
    panels = "".join(
        (
            _draw_panel("A. Realized PV / Load (kW)", exogenous, 30, 105, 570, 230),
            _draw_panel(
                "B. Actual AC power (kW; battery +charge/-discharge; grid +import/-export)",
                power_series + grid_series,
                650,
                105,
                570,
                230,
                True,
            ),
            _draw_panel(
                f"C. Actual SOC final (%) [limits {scenario.battery_model.min_soc_fraction * 100:.0f}-{scenario.battery_model.max_soc_fraction * 100:.0f}]",
                soc_series,
                30,
                380,
                570,
                230,
            ),
            _draw_panel(
                "D. Cumulative AC energy (kWh)", cumulative_series, 650, 380, 570, 230
            ),
        )
    )
    hour_labels = "".join(
        f'<text x="{45 + i * 22.3:.1f}" y="635" font-size="9" fill="#486581">{i}</text>'
        for i in range(0, 24, 3)
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1250" height="670" viewBox="0 0 1250 670">
<rect width="1250" height="670" fill="#F8FAFC"/><text x="30" y="35" font-size="24" font-weight="700" fill="#102A43">{_svg_text(scenario.scenario_id)} - {_svg_text(environment)}</text>
<text x="30" y="62" font-size="12" fill="#486581">Realized PV/load from Simulator actual facts. SOC points are interval-final Simulator next state. Timezone: UTC+08:00.</text>
<text x="30" y="82" font-size="12" fill="#486581">{_svg_text(note)}</text>{panels}{hour_labels}<text x="30" y="660" font-size="10" fill="#486581">Hour index 0-23 - Source: frozen Campaign A runner + Simulator trace - XML-safe deterministic report evidence</text></svg>"""


def _comparison_svg(summary_rows: list[dict[str, str]]) -> str:
    rows = [row for row in summary_rows if row["strategy"] == "Schedule"]
    labels = [row["source_environment"] for row in rows]
    imports = [float(row["grid_import_energy_kwh"]) for row in rows]
    exports = [float(row["grid_export_energy_kwh"]) for row in rows]
    maximum = max(imports + exports) * 1.15
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="1250" height="670" viewBox="0 0 1250 670"><rect width="1250" height="670" fill="#F8FAFC"/><text x="55" y="55" font-size="26" font-weight="700" fill="#102A43">Three typical residential days — realized AC energy comparison</text><text x="55" y="83" font-size="13" fill="#486581">Schedule = Economic for these three independently executed frozen paths. Daily kWh; grid import/export remain separate.</text>'
    ]
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        y = 130 + 370 * (1 - fraction)
        parts.append(
            f'<line x1="115" y1="{y:.1f}" x2="1155" y2="{y:.1f}" stroke="#D7DEE8"/><text x="55" y="{y + 4:.1f}" font-size="11" fill="#486581">{maximum * fraction:.1f}</text>'
        )
    for index, label in enumerate(labels):
        center = 115 + (index + 0.5) * 1040 / 3
        for offset, value, color in (
            (-38, imports[index], "#DC2626"),
            (8, exports[index], "#D97706"),
        ):
            bar_height = value / maximum * 370
            y = 500 - bar_height
            parts.append(
                f'<rect x="{center + offset}" y="{y:.1f}" width="28" height="{bar_height:.1f}" fill="{color}"/><text x="{center + offset - 2}" y="{y - 7:.1f}" font-size="11" fill="#243B53">{value:.2f}</text>'
            )
        parts.append(
            f'<text x="{center - 40}" y="528" font-size="13" font-weight="700" fill="#102A43">{_svg_text(label)}</text>'
        )
    parts.append(
        '<rect x="840" y="95" width="14" height="14" fill="#DC2626"/><text x="860" y="107" font-size="12" fill="#243B53">Grid import</text><rect x="975" y="95" width="14" height="14" fill="#D97706"/><text x="995" y="107" font-size="12" fill="#243B53">Grid export</text><text x="55" y="625" font-size="11" fill="#486581">Source: typical_scenario_summary.csv · Simulator actual grid power, 1-hour intervals · grid +import / -export</text></svg>'
    )
    return "".join(parts)


def generate_report(output_directory: Path) -> LeadershipReportResult:
    output_directory = output_directory.resolve()
    data_dir, chart_dir, report_dir = (
        output_directory / "data",
        output_directory / "charts",
        output_directory / "report",
    )
    for directory in (data_dir, chart_dir, report_dir):
        directory.mkdir(parents=True, exist_ok=True)
    evaluator = DeterministicResidentialAcceptanceEvaluator()
    all_paths: list[ResidentialCampaignPathResult] = []
    hourly_rows: list[dict[str, str]] = []
    summary_rows: list[dict[str, str]] = []
    manifest_rows: list[dict[str, str]] = []
    comparison_rows: list[dict[str, str]] = []
    chart_paths: list[Path] = []
    for scenario, environment in _selected_scenarios():
        result = _run_scenario(
            scenario, output_directory / "executions" / scenario.scenario_id, evaluator
        )
        if result.schedule.trajectory is result.economic.trajectory:
            raise AssertionError("Schedule/Economic trajectories must be independent")
        path_by_strategy = {"Schedule": result.schedule, "Economic": result.economic}
        rows_by_strategy: dict[str, list[dict[str, str]]] = {}
        for strategy in STRATEGIES:
            path = path_by_strategy[strategy]
            if not path.acceptance.passed:
                raise AssertionError("frozen daily acceptance must pass")
            rows = _path_rows(path, environment)
            rows_by_strategy[strategy] = rows
            hourly_rows.extend(rows)
            summary_rows.append(_summary_row(path, environment, rows))
            all_paths.append(path)
        max_difference = max(
            abs(
                float(left["actual_battery_ac_power_kw"])
                - float(right["actual_battery_ac_power_kw"])
            )
            for left, right in zip(
                rows_by_strategy["Schedule"], rows_by_strategy["Economic"], strict=True
            )
        )
        max_index = next(
            index
            for index, (left, right) in enumerate(
                zip(
                    rows_by_strategy["Schedule"],
                    rows_by_strategy["Economic"],
                    strict=True,
                )
            )
            if isclose(
                abs(
                    float(left["actual_battery_ac_power_kw"])
                    - float(right["actual_battery_ac_power_kw"])
                ),
                max_difference,
                rel_tol=0.0,
                abs_tol=TOLERANCE,
            )
        )
        comparison_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "source_environment": environment,
                "schedule_economic_ranking": result.comparison.ranking.value,
                "maximum_absolute_actual_battery_power_difference_kw": _number(
                    max_difference
                ),
                "maximum_difference_timestamp": rows_by_strategy["Schedule"][max_index][
                    "timestamp"
                ],
                "independent_trajectory_objects": "true",
                "shared_exogenous_facts": "true",
            }
        )
        manifest_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "source_environment": environment,
                "description": scenario.description,
                "realized_pv_profile_fingerprint": _fingerprint(scenario.pv_profile_kw),
                "realized_load_profile_fingerprint": _fingerprint(
                    scenario.load_profile_kw
                ),
                "realized_tariff_profile_fingerprint": _fingerprint(
                    scenario.import_tariff_profile_per_kwh
                ),
                "realized_profile_fingerprint": _combined_fingerprint(scenario),
                "forecast_semantics": scenario.forecast_semantics,
                "battery_power_contract": "SIMULATOR_ACTUAL_POSITIVE_CHARGE_NEGATIVE_DISCHARGE",
                "grid_power_contract": "SIMULATOR_ACTUAL_POSITIVE_IMPORT_NEGATIVE_EXPORT",
                "soc_point_semantics": "INTERVAL_FINAL_SIMULATOR_NEXT_STATE",
            }
        )
        chart_stems = {
            "A01_REFERENCE_TASK175": "reference",
            "A10_HIGH_PV": "high_pv",
            "A16_EVENING_PEAK": "high_evening_load",
        }
        chart_path = chart_dir / f"{chart_stems[scenario.scenario_id]}_typical_day.svg"
        chart_path.write_text(
            _scenario_svg(scenario, environment, rows_by_strategy),
            encoding="utf-8",
            newline="",
        )
        chart_paths.append(chart_path)
    if len(all_paths) != 6 or len(hourly_rows) != 144:
        raise AssertionError(
            "leadership evidence requires six paths and 144 hourly rows"
        )
    hourly_csv = data_dir / "typical_scenario_hourly_trace.csv"
    summary_csv = data_dir / "typical_scenario_summary.csv"
    comparison_csv = data_dir / "typical_scenario_strategy_comparison.csv"
    manifest_csv = data_dir / "typical_scenario_manifest.csv"
    _write_csv(hourly_csv, tuple(hourly_rows[0]), hourly_rows)
    _write_csv(summary_csv, tuple(summary_rows[0]), summary_rows)
    _write_csv(comparison_csv, tuple(comparison_rows[0]), comparison_rows)
    _write_csv(manifest_csv, tuple(manifest_rows[0]), manifest_rows)
    comparison_chart = chart_dir / "typical_scenario_comparison.svg"
    comparison_chart.write_text(
        _comparison_svg(summary_rows), encoding="utf-8", newline=""
    )
    chart_paths.append(comparison_chart)
    (output_directory / "source-notes.txt").write_text(
        "Simulator actual fields: pv_result.actual_power_kw, load_result.actual_power_kw, battery_result.actual_power_kw, grid_result.actual_grid_power_kw, battery_result.next_state.soc.\n",
        encoding="utf-8",
        newline="",
    )
    (output_directory / "generation_manifest.json").write_text(
        json.dumps(
            {
                "scenario_count": 3,
                "path_count": 6,
                "hourly_rows": 144,
                "scenario_order": [item[0] for item in SCENARIOS],
                "strategy_order": list(STRATEGIES),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="",
    )
    (output_directory / "README.md").write_text(
        "# Residential A-F leadership evidence\n\nGenerated local evidence only; do not commit this directory. Curves use realized Simulator facts and actual execution fields.\n",
        encoding="utf-8",
        newline="",
    )
    return LeadershipReportResult(
        output_directory,
        hourly_csv,
        summary_csv,
        comparison_csv,
        manifest_csv,
        tuple(chart_paths),
        tuple(all_paths),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("report_output_residential_a_f_leadership"),
    )
    args = parser.parse_args()
    result = generate_report(args.output_dir)
    print(
        f"PASS scenarios=3 paths={len(result.paths)} hourly_rows=144 output={result.output_directory}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
