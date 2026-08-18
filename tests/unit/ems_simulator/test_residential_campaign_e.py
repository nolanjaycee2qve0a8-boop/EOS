"""Focused regression tests for post-freeze Residential Campaign E reporting."""

import csv
import hashlib
from collections import Counter
from math import ceil, isclose, sqrt
from pathlib import Path
from unittest.mock import Mock
from xml.etree import ElementTree

import pytest

import ems_simulator.residential_campaign_c as campaign_c
import ems_simulator.residential_campaign_e as campaign_e
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner as _economic_runner_factory,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _schedule_runner as _schedule_runner_factory,
)
from ems_simulator.residential_acceptance import NUMERIC_TOLERANCE
from ems_simulator.residential_campaign_c import (
    _run_scenario as _campaign_c_run_scenario,
)
from ems_simulator.residential_campaign_c import campaign_c_scenarios
from ems_simulator.residential_campaign_e import (
    _ENVIRONMENTS,
    _SEED,
    _bar_svg,
    _combined_forecast_fingerprint,
    _normalized_fingerprint_value,
    _profile_fingerprint,
    _sampled_scenario,
    _transform,
    campaign_e_samples,
    run_residential_campaign_e,
)


def _independent_profile_fingerprint(values: tuple[float, ...]) -> str:
    payload = ",".join(
        _independent_normalized_fingerprint_value(value) for value in values
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _independent_normalized_fingerprint_value(value: float) -> str:
    normalized = 0.0 if round(value, 6) == 0.0 else value
    return f"{normalized:.6f}"


def _independent_combined_fingerprint(
    pv_fingerprint: str, load_fingerprint: str, tariff_fingerprint: str
) -> str:
    payload = (
        f"pv:{pv_fingerprint}|load:{load_fingerprint}|tariff:{tariff_fingerprint}"
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _independent_nearest_rank(values: tuple[float, ...], percentile: float) -> float:
    ordered = tuple(sorted(values))
    index = min(max(ceil(percentile * len(ordered)), 1), len(ordered)) - 1
    return ordered[index]


def _csv_rows(path: Path) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames is not None
        return tuple(reader.fieldnames), list(reader)


def test_campaign_e_keyed_samples_are_deterministic_and_preserve_source_facts() -> None:
    first = campaign_e_samples()
    second = campaign_e_samples()

    assert first == second
    assert len(first) == 192
    assert Counter(item.environment for item in first) == {
        environment: 64 for environment in _ENVIRONMENTS
    }
    assert all(item.seed == _SEED for item in first)
    assert all(-0.30 <= item.pv_amplitude_error <= 0.30 for item in first)
    assert all(-0.25 <= item.load_amplitude_error <= 0.25 for item in first)
    assert all(-0.20 <= item.tariff_amplitude_error <= 0.20 for item in first)

    perfect = next(
        item
        for item in campaign_c_scenarios()
        if item.environment == "REFERENCE" and item.forecast_error_case_id == "PERFECT"
    )
    sampled = _sampled_scenario(perfect, first[0])
    assert sampled.realized_pv_profile_kw is perfect.realized_pv_profile_kw
    assert sampled.realized_load_profile_kw is perfect.realized_load_profile_kw
    assert (
        sampled.realized_tariff_profile_cny_per_kwh
        is perfect.realized_tariff_profile_cny_per_kwh
    )
    assert all(value >= 0.0 for value in sampled.forecast_pv_profile_kw)
    assert all(value >= 0.0 for value in sampled.forecast_load_profile_kw)
    assert all(value >= 0.0 for value in sampled.forecast_tariff_profile_cny_per_kwh)
    assert _transform((0.0, 2.0, 0.0), 0.30, 0) == (0.0, 2.6, 0.0)
    assert _transform((0.0, 2.0, 0.0), 0.0, 1) == (2.0, 0.0, 0.0)


def test_campaign_e_fingerprint_normalization_is_a_six_decimal_evidence_contract() -> (
    None
):
    collapsed_left = (1.0000001,)
    collapsed_right = (1.0000002,)
    visible_left = (1.000000,)
    visible_right = (1.000001,)

    assert _independent_normalized_fingerprint_value(collapsed_left[0]) == "1.000000"
    assert _independent_normalized_fingerprint_value(collapsed_right[0]) == "1.000000"
    assert _profile_fingerprint(collapsed_left) == _profile_fingerprint(collapsed_right)
    assert _independent_normalized_fingerprint_value(visible_left[0]) == "1.000000"
    assert _independent_normalized_fingerprint_value(visible_right[0]) == "1.000001"
    assert _profile_fingerprint(visible_left) != _profile_fingerprint(visible_right)

    for value in (-0.0, 0.0, -0.0000001):
        assert _normalized_fingerprint_value(value) == "0.000000"
        assert _independent_normalized_fingerprint_value(value) == "0.000000"
    assert _profile_fingerprint((-0.0,)) == _profile_fingerprint((0.0,))

    component = _independent_profile_fingerprint(visible_right)
    independent_combined = _independent_combined_fingerprint(
        component,
        _independent_profile_fingerprint((2.0,)),
        _independent_profile_fingerprint((0.2,)),
    )
    assert component == hashlib.sha256(b"1.000001").hexdigest()
    assert (
        _combined_forecast_fingerprint(
            component,
            _independent_profile_fingerprint((2.0,)),
            _independent_profile_fingerprint((0.2,)),
        )
        == independent_combined
    )


def test_campaign_e_executes_exact_matrix_with_full_crn_and_anchor_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    schedule_factory = Mock(wraps=_schedule_runner_factory)
    economic_factory = Mock(wraps=_economic_runner_factory)
    composition = Mock(wraps=_campaign_c_run_scenario)
    monkeypatch.setattr(campaign_c, "_schedule_runner", schedule_factory)
    monkeypatch.setattr(campaign_c, "_economic_runner", economic_factory)
    monkeypatch.setattr(campaign_e, "_run_scenario", composition)

    campaign = run_residential_campaign_e(tmp_path)

    assert composition.call_count == 195  # 3 anchors + 192 caller-owned samples
    assert schedule_factory.call_count == 195
    assert economic_factory.call_count == 195
    assert len(campaign.samples) == 192
    assert len(campaign.paths) == 384
    assert len(campaign.anchors) == 6
    assert campaign.sampled_execution_count == 384
    assert campaign.anchor_execution_count == 6
    assert campaign.hard_passed
    assert campaign.anchor_fingerprints_reproduced
    assert len(campaign.comparisons) == 192
    assert len(campaign.regrets) == 384

    expected_sample_keys = {
        (environment, sample_index)
        for environment in _ENVIRONMENTS
        for sample_index in range(64)
    }
    paired_paths = {
        key: tuple(
            item
            for item in campaign.paths
            if (item.sample.environment, item.sample.sample_index) == key
        )
        for key in expected_sample_keys
    }
    assert set(paired_paths) == expected_sample_keys
    assert all(len(pair) == 2 for pair in paired_paths.values())
    assert {
        (item.sample.environment, item.sample.sample_index, item.strategy)
        for item in campaign.paths
    } == {
        (environment, sample_index, strategy)
        for environment, sample_index in expected_sample_keys
        for strategy in ("Schedule", "Economic")
    }

    for pair in paired_paths.values():
        schedule, economic = sorted(pair, key=lambda item: item.strategy)
        assert (schedule.strategy, economic.strategy) == ("Economic", "Schedule")
        assert schedule.scenario is economic.scenario
        assert (
            schedule.scenario.forecast_pv_profile_kw
            is economic.scenario.forecast_pv_profile_kw
        )
        assert (
            schedule.scenario.forecast_load_profile_kw
            is economic.scenario.forecast_load_profile_kw
        )
        assert (
            schedule.scenario.forecast_tariff_profile_cny_per_kwh
            is economic.scenario.forecast_tariff_profile_cny_per_kwh
        )
        assert (
            schedule.scenario.realized_pv_profile_kw
            is economic.scenario.realized_pv_profile_kw
        )
        assert (
            schedule.scenario.realized_load_profile_kw
            is economic.scenario.realized_load_profile_kw
        )
        assert (
            schedule.scenario.realized_tariff_profile_cny_per_kwh
            is economic.scenario.realized_tariff_profile_cny_per_kwh
        )
        assert schedule.path.trajectory is not economic.path.trajectory

    anchor_by_key = {
        (anchor.environment, anchor.strategy): anchor for anchor in campaign.anchors
    }
    assert set(anchor_by_key) == {
        (environment, strategy)
        for environment in _ENVIRONMENTS
        for strategy in ("Schedule", "Economic")
    }
    assert all(
        regret.anchor
        is anchor_by_key[(regret.path.sample.environment, regret.path.strategy)]
        for regret in campaign.regrets
    )
    trajectories = tuple(
        item.path.trajectory for item in campaign.paths + campaign.anchors
    )
    assert len({id(trajectory) for trajectory in trajectories}) == 390

    for regret in campaign.regrets:
        actual_differences = tuple(
            abs(sampled - anchor)
            for sampled, anchor in zip(
                (
                    trace.simulation_trace.state.battery_result.actual_power_kw
                    for trace in regret.path.path.trajectory.step_traces
                ),
                (
                    trace.simulation_trace.state.battery_result.actual_power_kw
                    for trace in regret.anchor.path.trajectory.step_traces
                ),
                strict=True,
            )
        )
        assert regret.actual_power_divergence_hours == sum(
            difference > NUMERIC_TOLERANCE for difference in actual_differences
        )
        assert isclose(
            regret.maximum_actual_power_difference_kw,
            max(actual_differences),
            abs_tol=NUMERIC_TOLERANCE,
        )


def test_campaign_e_manifest_statistics_and_outputs_are_deterministic(
    tmp_path: Path,
) -> None:
    first = run_residential_campaign_e(tmp_path / "first")
    second = run_residential_campaign_e(tmp_path / "second")
    first_files = {path.name: path for path in first.output_paths}
    second_files = {path.name: path for path in second.output_paths}

    assert {
        "campaign_e_summary.txt",
        "campaign_e_sample_manifest.csv",
        "campaign_e_anchor_results.csv",
        "campaign_e_path_results.csv",
        "campaign_e_regret_evidence.csv",
        "campaign_e_strategy_comparisons.csv",
        "campaign_e_distribution_summary.csv",
        "campaign_e_hourly_trace.csv",
        "campaign_e_anchor_hourly_trace.csv",
        "campaign_e_acceptance_findings.csv",
        "campaign_e_regret_ecdf_reference.svg",
        "campaign_e_regret_ecdf_high_pv.svg",
        "campaign_e_regret_ecdf_high_evening_load.svg",
        "campaign_e_divergence_ecdf_reference.svg",
        "campaign_e_divergence_ecdf_high_pv.svg",
        "campaign_e_divergence_ecdf_high_evening_load.svg",
        "campaign_e_physical_revisions.svg",
        "campaign_e_ranking_summary.svg",
    } == set(first_files)
    assert first_files.keys() == second_files.keys()
    for name in first_files:
        assert first_files[name].read_bytes() == second_files[name].read_bytes()

    expected_headers = {
        "campaign_e_sample_manifest.csv": (
            "seed",
            "environment",
            "sample_index",
            "source_scenario_id",
            "realized_pv_fingerprint",
            "realized_load_fingerprint",
            "realized_tariff_fingerprint",
            "forecast_pv_fingerprint",
            "forecast_load_fingerprint",
            "forecast_tariff_fingerprint",
            "forecast_combined_fingerprint",
            "pv_amplitude_error",
            "load_amplitude_error",
            "tariff_amplitude_error",
            "pv_shift_hours",
            "load_shift_hours",
            "tariff_shift_hours",
        ),
        "campaign_e_anchor_results.csv": (
            "environment",
            "strategy",
            "scenario_id",
            "adjusted_net_economic_cost",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
            "battery_throughput_kwh",
            "final_actual_soc",
            "frozen_campaign_a_fingerprint_reproduced",
        ),
        "campaign_e_path_results.csv": (
            "environment",
            "sample_index",
            "strategy",
            "scenario_id",
            "adjusted_net_economic_cost",
            "physical_revisions",
            "final_actual_soc",
            "acceptance_passed",
            "ledger_reconciled",
            "comparison_reconciled",
        ),
        "campaign_e_regret_evidence.csv": (
            "environment",
            "sample_index",
            "strategy",
            "anchor_scenario_id",
            "adjusted_cost_regret_cny",
            "actual_power_divergence_hours",
            "maximum_actual_power_difference_kw",
            "actual_power_source",
        ),
        "campaign_e_strategy_comparisons.csv": (
            "environment",
            "sample_index",
            "ranking",
            "economic_minus_schedule_adjusted_cost_cny",
        ),
        "campaign_e_distribution_summary.csv": (
            "environment",
            "strategy",
            "metric",
            "count",
            "mean",
            "population_standard_deviation",
            "minimum",
            "p05_nearest_rank",
            "p50_nearest_rank",
            "p90_nearest_rank",
            "p95_nearest_rank",
            "maximum",
            "positive_count",
            "zero_count",
            "negative_count",
        ),
        "campaign_e_hourly_trace.csv": (
            "environment",
            "sample_index",
            "strategy",
            "execution_scope",
            "hour_index",
            "actual_battery_power_kw",
            "power_source",
        ),
        "campaign_e_anchor_hourly_trace.csv": (
            "environment",
            "strategy",
            "execution_scope",
            "hour_index",
            "timestamp",
            "realized_pv_power_kw",
            "realized_load_power_kw",
            "realized_import_tariff_cny_per_kwh",
            "actual_battery_power_kw",
            "actual_soc_fraction",
            "actual_grid_power_kw",
            "anchor_scenario_id",
            "frozen_campaign_a_fingerprint_reproduced",
        ),
        "campaign_e_acceptance_findings.csv": (
            "environment",
            "sample_index",
            "strategy",
            "criterion",
            "severity",
            "status",
            "message",
        ),
    }
    expected_rows = {
        "campaign_e_sample_manifest.csv": 192,
        "campaign_e_anchor_results.csv": 6,
        "campaign_e_path_results.csv": 384,
        "campaign_e_regret_evidence.csv": 384,
        "campaign_e_strategy_comparisons.csv": 192,
        "campaign_e_distribution_summary.csv": 30,
        "campaign_e_hourly_trace.csv": 384 * 24,
        "campaign_e_anchor_hourly_trace.csv": 6 * 24,
        "campaign_e_acceptance_findings.csv": sum(
            len(path.path.acceptance.findings) for path in first.paths
        ),
    }
    output_rows: dict[str, list[dict[str, str]]] = {}
    for name, expected_header in expected_headers.items():
        header, rows = _csv_rows(first_files[name])
        assert header == expected_header
        assert len(rows) == expected_rows[name]
        output_rows[name] = rows

    manifest_rows = output_rows["campaign_e_sample_manifest.csv"]
    assert len({row["forecast_combined_fingerprint"] for row in manifest_rows}) == 192
    source_by_environment = {
        item.environment: item
        for item in campaign_c_scenarios()
        if item.forecast_error_case_id == "PERFECT"
    }
    samples_by_key = {
        (sample.environment, sample.sample_index): sample for sample in first.samples
    }
    for row in manifest_rows:
        assert all(
            len(row[field]) == 64 and set(row[field]) <= set("0123456789abcdef")
            for field in (
                "forecast_pv_fingerprint",
                "forecast_load_fingerprint",
                "forecast_tariff_fingerprint",
                "forecast_combined_fingerprint",
            )
        )
        sampled = _sampled_scenario(
            source_by_environment[row["environment"]],
            samples_by_key[(row["environment"], int(row["sample_index"]))],
        )
        pv = _independent_profile_fingerprint(sampled.forecast_pv_profile_kw)
        load = _independent_profile_fingerprint(sampled.forecast_load_profile_kw)
        tariff = _independent_profile_fingerprint(
            sampled.forecast_tariff_profile_cny_per_kwh
        )
        assert (pv, load, tariff) == (
            row["forecast_pv_fingerprint"],
            row["forecast_load_fingerprint"],
            row["forecast_tariff_fingerprint"],
        )
        assert row[
            "forecast_combined_fingerprint"
        ] == _independent_combined_fingerprint(pv, load, tariff)

    first_sample = _sampled_scenario(
        source_by_environment["REFERENCE"], first.samples[0]
    )
    changed_pv = (
        *first_sample.forecast_pv_profile_kw[:-1],
        first_sample.forecast_pv_profile_kw[-1] + 0.001,
    )
    changed_pv_fingerprint = _independent_profile_fingerprint(changed_pv)
    assert changed_pv_fingerprint != _independent_profile_fingerprint(
        first_sample.forecast_pv_profile_kw
    )
    assert _independent_combined_fingerprint(
        changed_pv_fingerprint,
        _independent_profile_fingerprint(first_sample.forecast_load_profile_kw),
        _independent_profile_fingerprint(
            first_sample.forecast_tariff_profile_cny_per_kwh
        ),
    ) != _independent_combined_fingerprint(
        _independent_profile_fingerprint(first_sample.forecast_pv_profile_kw),
        _independent_profile_fingerprint(first_sample.forecast_load_profile_kw),
        _independent_profile_fingerprint(
            first_sample.forecast_tariff_profile_cny_per_kwh
        ),
    )

    scheduled_manifest = {
        (path.sample.environment, path.sample.sample_index): row
        for path in first.paths
        if path.strategy == "Schedule"
        for row in manifest_rows
        if (row["environment"], int(row["sample_index"]))
        == (path.sample.environment, path.sample.sample_index)
    }
    economic_manifest = {
        (path.sample.environment, path.sample.sample_index): row
        for path in first.paths
        if path.strategy == "Economic"
        for row in manifest_rows
        if (row["environment"], int(row["sample_index"]))
        == (path.sample.environment, path.sample.sample_index)
    }
    assert scheduled_manifest == economic_manifest

    sampled_rows = output_rows["campaign_e_hourly_trace.csv"]
    anchor_rows = output_rows["campaign_e_anchor_hourly_trace.csv"]
    assert {row["execution_scope"] for row in sampled_rows} == {"sampled"}
    assert {row["execution_scope"] for row in anchor_rows} == {"perfect_anchor"}
    assert len({(row["environment"], row["strategy"]) for row in anchor_rows}) == 6
    assert all(
        row["frozen_campaign_a_fingerprint_reproduced"] == "true" for row in anchor_rows
    )

    statistic = next(
        item
        for item in first.distributions
        if item.environment == "REFERENCE"
        and item.strategy == "Schedule"
        and item.metric == "adjusted_cost_regret_cny"
    )
    values = tuple(
        item.adjusted_cost_regret
        for item in first.regrets
        if item.path.sample.environment == statistic.environment
        and item.path.strategy == statistic.strategy
    )
    mean = sum(values) / len(values)
    assert statistic.count == 64
    assert isclose(statistic.mean, mean, abs_tol=NUMERIC_TOLERANCE)
    assert isclose(
        statistic.population_standard_deviation,
        sqrt(sum((value - mean) ** 2 for value in values) / len(values)),
        abs_tol=NUMERIC_TOLERANCE,
    )
    for percentile, actual in (
        (0.05, statistic.p05),
        (0.50, statistic.p50),
        (0.90, statistic.p90),
        (0.95, statistic.p95),
    ):
        assert actual == _independent_nearest_rank(values, percentile)

    probe = (-2.0, -1.0, 0.0, 1.0, 7.0)
    probe_mean = sum(probe) / len(probe)
    assert _independent_nearest_rank(probe, 0.05) == -2.0
    assert _independent_nearest_rank(probe, 0.50) == 0.0
    assert _independent_nearest_rank(probe, 0.90) == 7.0
    assert _independent_nearest_rank(probe, 0.95) == 7.0
    assert min(probe) == -2.0 and max(probe) == 7.0
    assert probe_mean == 1.0
    assert sqrt(sum((value - probe_mean) ** 2 for value in probe) / len(probe)) > 0.0
    assert (
        sum(value > 0 for value in probe),
        sum(value == 0 for value in probe),
        sum(value < 0 for value in probe),
    ) == (2, 1, 2)

    ecdf_paths = tuple(path for name, path in first_files.items() if "_ecdf_" in name)
    assert len(ecdf_paths) == 6
    for path in ecdf_paths:
        root = ElementTree.fromstring(path.read_text(encoding="utf-8"))
        polylines = root.findall("{http://www.w3.org/2000/svg}polyline")
        assert len(polylines) == 2
        assert {line.attrib["data-strategy"] for line in polylines} == {
            "Schedule",
            "Economic",
        }
        assert all(line.attrib["data-count"] == "64" for line in polylines)


def test_campaign_e_svg_escapes_labels_and_places_dynamic_zero_axis() -> None:
    svg = _bar_svg("<title>", "<unit>", (('negative<&"', -2.0), ("positive", 3.0)))

    assert 'id="zero-axis" x1="62.00" y1="230.80" x2="996.00" y2="230.80"' in svg
    assert "&lt;title&gt;" in svg
    assert 'data-label="negative&lt;&amp;&quot;"' in svg
    assert "&lt;unit&gt;" in svg
