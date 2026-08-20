from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path
from xml.etree import ElementTree

import pytest

from ems_simulator import residential_campaign_f as campaign_f
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner as source_economic_runner,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _schedule_runner as source_schedule_runner,
)
from ems_simulator.residential_acceptance import NUMERIC_TOLERANCE
from ems_simulator.residential_campaign_d import campaign_d_cases
from ems_simulator.residential_campaign_f import (
    _CHOLESKY,
    _CORRELATION,
    CampaignFPathResult,
    CampaignFResult,
    campaign_f_regimes,
    campaign_f_scenarios,
    run_residential_campaign_f,
)
from optimization import NetLoadAwareBaselineOptimizationConfiguration


@dataclass(frozen=True, slots=True)
class _CampaignFExecutionAudit:
    result: CampaignFResult
    schedule_factory_calls: int
    economic_factory_calls: int


def test_campaign_f_regimes_preserve_exact_campaign_d_sequences() -> None:
    cases = {item.case_id: item for item in campaign_d_cases()}
    regimes = campaign_f_regimes()

    assert [(item.regime_id, item.source_case.case_id) for item in regimes] == [
        ("REFERENCE", "D01_7D_REFERENCE_REPEAT"),
        ("HIGH_PV", "D03_7D_HIGH_PV_REPEAT"),
        ("HIGH_EVENING_LOAD", "D02_7D_EVENING_REPEAT"),
    ]
    for regime in regimes:
        assert (
            regime.source_case.source_scenario_ids
            == cases[regime.source_case.case_id].source_scenario_ids
        )
        assert tuple(day.source_scenario.scenario_id for day in regime.source_days) == (
            regime.source_case.source_scenario_ids
        )


def test_campaign_f_builds_420_real_scenario_days_with_core_and_tail_rules() -> None:
    scenarios = campaign_f_scenarios()
    core = tuple(item for item in scenarios if item.scenario_class == "core")
    tail = tuple(item for item in scenarios if item.scenario_class == "tail")

    assert len(scenarios) == 60
    assert len(core) == 48
    assert len(tail) == 12
    assert sum(len(item.days) for item in scenarios) == 420
    assert all(
        tuple(day.day_index for day in item.days) == tuple(range(7))
        for item in scenarios
    )
    assert all(
        day.forecast_fingerprint != day.realized_fingerprint
        for item in core
        for day in item.days
        if any(abs(value) > NUMERIC_TOLERANCE for value in day.clipped_error)
        or day.pv_shift_hours
        or day.load_shift_hours
        or day.tariff_shift_hours
    )

    reversal = next(item for item in tail if item.tail_case_id == "F-TAIL-04")
    assert all(day.clipped_error == (0.45, -0.35, -0.30) for day in reversal.days[:3])
    assert all(day.clipped_error == (-0.45, 0.35, 0.30) for day in reversal.days[3:])
    assert all(day.pv_shift_hours == -2 for day in reversal.days[:3])
    assert all(day.pv_shift_hours == 2 for day in reversal.days[3:])
    assert all(not any(day.clip_flags) for item in tail for day in item.days)


def test_campaign_f_cholesky_and_ar1_evidence_match_the_declared_model() -> None:
    correlation = ((1.0, -0.45, 0.35), (-0.45, 1.0, -0.25), (0.35, -0.25, 1.0))
    cholesky = (
        (1.0, 0.0, 0.0),
        (-0.45, 0.8930285549745876, 0.0),
        (0.35, -0.10358011452683305, 0.9310054564150567),
    )
    for expected_row, actual_row in zip(cholesky, _CHOLESKY, strict=True):
        assert pytest.approx(expected_row) == actual_row
    for expected_row, actual_row in zip(correlation, _CORRELATION, strict=True):
        assert pytest.approx(expected_row) == actual_row
    for row in range(3):
        for column in range(3):
            reconstructed = sum(
                cholesky[row][index] * cholesky[column][index]
                for index in range(min(row, column) + 1)
            )
            assert reconstructed == pytest.approx(correlation[row][column])

    def keyed_normal(key: str) -> float:
        def uniform(suffix: str) -> float:
            digest = hashlib.sha256((key + suffix).encode("utf-8")).digest()
            return (int.from_bytes(digest[:16], "big") + 1) / (2**128 + 1)

        return math.sqrt(-2.0 * math.log(uniform("|u1"))) * math.cos(
            2.0 * math.pi * uniform("|u2")
        )

    def sample_key(day: int | str, component: str) -> str:
        return f"20260818|REFERENCE|0|{day}|{component}|0"

    initial_independent = tuple(
        keyed_normal(sample_key("initial", component))
        for component in ("pv", "load", "tariff")
    )
    initial = (
        initial_independent[0],
        -0.45 * initial_independent[0] + 0.8930285549745876 * initial_independent[1],
        0.35 * initial_independent[0]
        - 0.10358011452683305 * initial_independent[1]
        + 0.9310054564150567 * initial_independent[2],
    )
    prior_timing = keyed_normal(sample_key("initial", "timing"))

    sample = next(
        item
        for item in campaign_f_scenarios()
        if item.scenario_id == "F-REFERENCE-CORE-00"
    )
    prior = initial
    for current in sample.days:
        independent = tuple(
            keyed_normal(sample_key(current.day_index, component))
            for component in ("pv", "load", "tariff")
        )
        correlated = (
            independent[0],
            -0.45 * independent[0] + 0.8930285549745876 * independent[1],
            0.35 * independent[0]
            - 0.10358011452683305 * independent[1]
            + 0.9310054564150567 * independent[2],
        )
        expected: tuple[float, float, float] = (
            0.70 * prior[0] + math.sqrt(1.0 - 0.70**2) * correlated[0],
            0.70 * prior[1] + math.sqrt(1.0 - 0.70**2) * correlated[1],
            0.70 * prior[2] + math.sqrt(1.0 - 0.70**2) * correlated[2],
        )
        timing = 0.65 * prior_timing + math.sqrt(1.0 - 0.65**2) * keyed_normal(
            sample_key(current.day_index, "timing")
        )
        unclipped = tuple(
            scale * latent
            for scale, latent in zip((0.18, 0.15, 0.12), expected, strict=True)
        )
        clipped = (
            min(max(unclipped[0], -0.40), 0.40),
            min(max(unclipped[1], -0.35), 0.35),
            min(max(unclipped[2], -0.30), 0.30),
        )
        assert current.independent_innovation == pytest.approx(independent)
        assert current.correlated_innovation == pytest.approx(correlated)
        assert current.prior_latent == pytest.approx(prior)
        assert current.latent == pytest.approx(expected)
        assert current.unclipped_error == pytest.approx(unclipped)
        assert current.clipped_error == pytest.approx(clipped)
        assert current.timing_prior_latent == pytest.approx(prior_timing)
        assert current.timing_latent == pytest.approx(timing)
        prior = expected
        prior_timing = timing


@pytest.fixture(scope="module")
def campaign_f_execution_audit(
    tmp_path_factory: pytest.TempPathFactory,
) -> _CampaignFExecutionAudit:
    schedule_calls = 0
    economic_calls = 0

    def schedule_factory(
        configuration: NetLoadAwareBaselineOptimizationConfiguration,
    ) -> object:
        nonlocal schedule_calls
        schedule_calls += 1
        return source_schedule_runner(configuration)

    def economic_factory(
        configuration: NetLoadAwareBaselineOptimizationConfiguration,
    ) -> object:
        nonlocal economic_calls
        economic_calls += 1
        return source_economic_runner(configuration)

    patch = pytest.MonkeyPatch()
    patch.setattr(campaign_f, "_schedule_runner", schedule_factory)
    patch.setattr(campaign_f, "_economic_runner", economic_factory)
    try:
        result = run_residential_campaign_f(tmp_path_factory.mktemp("campaign-f"))
    finally:
        patch.undo()
    return _CampaignFExecutionAudit(result, schedule_calls, economic_calls)


@pytest.fixture(scope="module")
def campaign_f_result(
    campaign_f_execution_audit: _CampaignFExecutionAudit,
) -> CampaignFResult:
    return campaign_f_execution_audit.result


def test_campaign_f_executes_the_complete_real_matrix(
    campaign_f_result: CampaignFResult,
    campaign_f_execution_audit: _CampaignFExecutionAudit,
) -> None:
    assert campaign_f_result.hard_passed
    assert len(campaign_f_result.paths) == 120
    assert len(campaign_f_result.anchors) == 6
    assert len(campaign_f_result.regrets) == 120
    assert len(campaign_f_result.comparisons) == 60
    assert len(campaign_f_result.distributions) == 6
    assert not campaign_f_result.findings

    all_paths = campaign_f_result.paths + tuple(
        anchor.path for anchor in campaign_f_result.anchors
    )
    all_days = tuple(day for path in all_paths for day in path.summary.days)
    assert len(all_days) == 882
    assert len({id(day.trajectory) for day in all_days}) == 882
    assert sum(len(path.summary.continuity) for path in all_paths) == 756
    assert campaign_f_execution_audit.schedule_factory_calls == 441
    assert campaign_f_execution_audit.economic_factory_calls == 441


def test_campaign_f_retained_execution_uses_forecast_and_realized_facts_separately(
    campaign_f_result: CampaignFResult,
) -> None:
    schedule = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.scenario_id == "F-REFERENCE-CORE-00"
        and path.strategy == "Schedule"
    )
    economic = next(
        path
        for path in campaign_f_result.paths
        if path.scenario is schedule.scenario and path.strategy == "Economic"
    )
    for definition, schedule_day, economic_day in zip(
        schedule.scenario.days,
        schedule.summary.days,
        economic.summary.days,
        strict=True,
    ):
        schedule_input = schedule_day.trajectory.source_input.daily_mpc_input
        economic_input = economic_day.trajectory.source_input.daily_mpc_input
        source = definition.source_day.source_scenario

        for hour, (schedule_horizon, economic_horizon) in enumerate(
            zip(
                schedule_input.forecast_horizons,
                economic_input.forecast_horizons,
                strict=True,
            )
        ):
            for offset, (schedule_point, economic_point) in enumerate(
                zip(schedule_horizon.points, economic_horizon.points, strict=True)
            ):
                profile_index = hour + offset
                assert schedule_point == economic_point
                assert schedule_point.pv_power_kw == (
                    definition.forecast_pv_profile_kw[profile_index]
                    if profile_index < 24
                    else 0.0
                )
                assert schedule_point.load_power_kw == (
                    definition.forecast_load_profile_kw[profile_index]
                    if profile_index < 24
                    else 0.0
                )
                assert schedule_point.electricity_price_cny_per_kwh == (
                    definition.forecast_tariff_profile_per_kwh[profile_index]
                    if profile_index < 24
                    else 0.50
                )
        assert (
            schedule_input.integration_input.daily_input.pv_power_curve_kw
            is source.pv_profile_kw
        )
        assert (
            schedule_input.integration_input.daily_input.load_power_curve_kw
            is source.load_profile_kw
        )
        assert (
            schedule_input.integration_input.daily_input.tariff_curve_cny_per_kwh
            is source.import_tariff_profile_per_kwh
        )


def test_campaign_f_accounting_regret_and_actual_power_are_derived_from_traces(
    campaign_f_result: CampaignFResult,
) -> None:
    regret = next(
        item
        for item in campaign_f_result.regrets
        if item.path.scenario.scenario_id == "F-HIGH_PV-F-TAIL-03"
        and item.path.strategy == "Schedule"
    )
    summary = regret.path.summary
    operating_cost = sum(
        day.ledger.total_realized_import_cost
        - day.ledger.total_realized_export_revenue
        + day.ledger.total_battery_degradation_cost
        for day in summary.days
    )
    assert summary.aggregate_outcome.adjusted_net_economic_cost == pytest.approx(
        operating_cost - summary.final_terminal_evidence.terminal_energy_value
    )
    powers = regret.path.actual_powers_kw
    anchor_powers = regret.anchor.path.actual_powers_kw
    differences = tuple(
        abs(left - right) for left, right in zip(powers, anchor_powers, strict=True)
    )
    assert regret.adjusted_cost_regret == pytest.approx(
        summary.aggregate_outcome.adjusted_net_economic_cost
        - regret.anchor.path.summary.aggregate_outcome.adjusted_net_economic_cost
    )
    assert regret.actual_power_divergence_hours == sum(
        value > NUMERIC_TOLERANCE for value in differences
    )
    assert regret.maximum_actual_power_difference_kw == max(differences)
    assert regret.total_absolute_actual_power_difference_kwh == pytest.approx(
        sum(differences)
    )
    maximum_power = max(
        item.maximum_actual_power_difference_kw for item in campaign_f_result.regrets
    )
    assert maximum_power == pytest.approx(4.9)
    assert {
        item.path.strategy
        for item in campaign_f_result.regrets
        if item.maximum_actual_power_difference_kw == maximum_power
    } == {"Schedule", "Economic"}


def test_campaign_f_summary_retains_complete_tied_argmax_evidence(
    campaign_f_result: CampaignFResult,
) -> None:
    directory = campaign_f_result.output_paths[0].parent
    _, fields = campaign_f._summary_fields(directory / "campaign_f_summary.txt")
    summary = dict(fields)

    path_values = (
        (
            "maximum_adjusted_cost_regret",
            "maximum_adjusted_cost_regret",
            tuple(
                (
                    item.path.scenario.scenario_id,
                    item.path.strategy,
                    item.adjusted_cost_regret,
                )
                for item in campaign_f_result.regrets
            ),
            True,
        ),
        (
            "maximum_actual_power_difference_kw",
            "maximum_actual_power_difference",
            tuple(
                (
                    item.path.scenario.scenario_id,
                    item.path.strategy,
                    item.maximum_actual_power_difference_kw,
                )
                for item in campaign_f_result.regrets
            ),
            True,
        ),
        (
            "maximum_physical_revisions",
            "maximum_physical_revisions",
            tuple(
                (
                    path.scenario.scenario_id,
                    path.strategy,
                    path.summary.total_physical_revisions,
                )
                for path in campaign_f_result.paths
                + tuple(anchor.path for anchor in campaign_f_result.anchors)
            ),
            False,
        ),
    )
    for value_key, reference_prefix, candidates, floating in path_values:
        value = candidates[0][2]
        for _, _, candidate in candidates[1:]:
            if candidate > value:
                value = candidate
        expected = [
            candidate
            for candidate in candidates
            if (
                math.isclose(candidate[2], value, abs_tol=NUMERIC_TOLERANCE)
                if floating
                else candidate[2] == value
            )
        ]
        expected.sort(key=lambda item: (item[0], 0 if item[1] == "Schedule" else 1))
        assert summary[f"{reference_prefix}_reference_count"] == "2"
        references = json.loads(summary[f"{reference_prefix}_references"])
        assert [
            (reference["scenario_id"], reference["strategy"])
            for reference in references
        ] == [(scenario_id, strategy) for scenario_id, strategy, _ in expected]
        assert [reference["value"] for reference in references] == [
            value for _, _, value in expected
        ]
        assert f"{value_key}_reference" not in summary


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    (
        ("omit_economic", "retained argmax set"),
        ("omit_schedule", "retained argmax set"),
        ("reverse_order", "retained argmax set"),
        ("wrong_scenario", "retained argmax set"),
        ("extra_nonmaximum", "retained argmax set"),
        ("wrong_count", "reference_count mismatch"),
        ("malformed_json", "encoding"),
    ),
)
def test_campaign_f_generator_common_mode_mutations_fail_targeted_independent_validator(
    campaign_f_result: CampaignFResult,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_failure: str,
) -> None:
    """Fast validator regressions do not stand in for publication propagation."""

    directory = campaign_f_result.output_paths[0].parent
    restore = _install_generator_argmax_mutation(monkeypatch, mutation)
    generated = campaign_f._summary_values(
        campaign_f_result, final_status=True, directory=directory
    )
    nested_calls: list[Path] = []
    original_nested_validator = campaign_f._nested_csv_failure

    def count_nested(
        output_directory: Path, relative: Path, expected_content: str
    ) -> str | None:
        nested_calls.append(relative)
        return original_nested_validator(output_directory, relative, expected_content)

    monkeypatch.setattr(campaign_f, "_nested_csv_failure", count_nested)
    failures = campaign_f._maximum_evidence_contract_failures(
        generated, campaign_f_result
    )
    restore()

    assert failures
    assert any(expected_failure in item for item in failures)
    assert nested_calls == []


def _install_generator_argmax_mutation(
    monkeypatch: pytest.MonkeyPatch, mutation: str
) -> Callable[[], None]:
    """Install one generator-only fault and return its immediate restoration."""

    if mutation in {"omit_economic", "omit_schedule"}:
        original_regret = campaign_f._maximum_adjusted_cost_regret_evidence

        def one_strategy_only(source: CampaignFResult) -> object:
            evidence = original_regret(source)
            references = (
                evidence.references[:1]
                if mutation == "omit_economic"
                else evidence.references[1:]
            )
            return replace(evidence, references=references)

        monkeypatch.setattr(
            campaign_f, "_maximum_adjusted_cost_regret_evidence", one_strategy_only
        )
        return lambda: monkeypatch.setattr(
            campaign_f, "_maximum_adjusted_cost_regret_evidence", original_regret
        )
    if mutation == "reverse_order":
        original_serializer = campaign_f._maximum_references_json
        monkeypatch.setattr(
            campaign_f,
            "_maximum_references_json",
            lambda evidence: original_serializer(
                replace(evidence, references=tuple(reversed(evidence.references)))
            ),
        )
        return lambda: monkeypatch.setattr(
            campaign_f, "_maximum_references_json", original_serializer
        )
    if mutation == "wrong_scenario":
        original_power = campaign_f._maximum_actual_power_evidence

        def wrong_scenario(source: CampaignFResult) -> object:
            evidence = original_power(source)
            reference = evidence.references[0]
            forged = replace(
                reference,
                scenario=replace(reference.scenario, scenario_id="F-REFERENCE-CORE-01"),
            )
            return replace(evidence, references=(forged, *evidence.references[1:]))

        monkeypatch.setattr(
            campaign_f, "_maximum_actual_power_evidence", wrong_scenario
        )
        return lambda: monkeypatch.setattr(
            campaign_f, "_maximum_actual_power_evidence", original_power
        )
    if mutation == "extra_nonmaximum":
        original_revisions = campaign_f._maximum_physical_revision_evidence

        def extra_nonmaximum(paths: tuple[CampaignFPathResult, ...]) -> object:
            evidence = original_revisions(paths)
            extra = next(
                path
                for path in paths
                if all(path is not reference for reference in evidence.references)
            )
            return replace(evidence, references=(*evidence.references, extra))

        monkeypatch.setattr(
            campaign_f, "_maximum_physical_revision_evidence", extra_nonmaximum
        )
        return lambda: monkeypatch.setattr(
            campaign_f, "_maximum_physical_revision_evidence", original_revisions
        )
    if mutation == "wrong_count":
        original_summary_values = campaign_f._summary_values

        def wrong_count(
            source: CampaignFResult,
            *,
            final_status: bool,
            directory: Path | None,
        ) -> tuple[tuple[str, str], ...]:
            values = original_summary_values(
                source, final_status=final_status, directory=directory
            )
            return tuple(
                (key, "1")
                if key == "maximum_adjusted_cost_regret_reference_count"
                else (key, value)
                for key, value in values
            )

        monkeypatch.setattr(campaign_f, "_summary_values", wrong_count)
        return lambda: monkeypatch.setattr(
            campaign_f, "_summary_values", original_summary_values
        )
    if mutation == "malformed_json":
        original_serializer = campaign_f._maximum_references_json
        monkeypatch.setattr(campaign_f, "_maximum_references_json", lambda _: "{")
        return lambda: monkeypatch.setattr(
            campaign_f, "_maximum_references_json", original_serializer
        )
    raise AssertionError(f"unknown generator mutation: {mutation}")


def test_campaign_f_argmax_evidence_preserves_unique_ties_and_tolerance(
    campaign_f_result: CampaignFResult,
) -> None:
    paths = tuple(item.path for item in campaign_f_result.regrets[:3])

    unique = campaign_f._maximum_float_evidence(((9.0, paths[0]), (8.0, paths[1])))
    assert unique.value == 9.0
    assert unique.references == (paths[0],)

    tied = campaign_f._maximum_float_evidence(
        ((9.0, paths[0]), (9.0, paths[1]), (8.0, paths[2]))
    )
    assert tied.references == campaign_f._ordered_references((paths[0], paths[1]))

    three_way = campaign_f._maximum_float_evidence(
        ((9.0, paths[2]), (9.0, paths[0]), (9.0, paths[1]))
    )
    assert three_way.references == campaign_f._ordered_references(paths)

    within_tolerance = campaign_f._maximum_float_evidence(
        (
            (9.0, paths[0]),
            (9.0 - NUMERIC_TOLERANCE / 2.0, paths[1]),
        )
    )
    outside_tolerance = campaign_f._maximum_float_evidence(
        (
            (9.0, paths[0]),
            (9.0 - 2.0 * NUMERIC_TOLERANCE, paths[1]),
        )
    )
    assert within_tolerance.references == campaign_f._ordered_references(paths[:2])
    assert outside_tolerance.references == (paths[0],)

    revision_paths = tuple(
        replace(
            path,
            summary=replace(
                path.summary,
                days=tuple(
                    replace(
                        day,
                        kpi=replace(
                            day.kpi,
                            physical_revision_count=value if index == 0 else 0,
                        ),
                    )
                    for index, day in enumerate(path.summary.days)
                ),
            ),
        )
        for path, value in zip(paths, (10, 10, 9), strict=True)
    )
    revisions = campaign_f._maximum_physical_revision_evidence(revision_paths)
    assert revisions.value == 10
    assert revisions.references == campaign_f._ordered_references(revision_paths[:2])


def test_campaign_f_output_contract_is_complete_and_traceable(
    campaign_f_result: CampaignFResult,
) -> None:
    directory = campaign_f_result.output_paths[0].parent
    paths = tuple(
        sorted(
            item.relative_to(directory)
            for item in directory.rglob("*")
            if item.is_file()
        )
    )

    assert len(campaign_f_result.output_paths) == 26
    assert len(paths) == 908
    assert sum("mpc_decisions.csv" in str(item) for item in paths) == 882
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
        "campaign_f_soc_continuity.csv": 756,
        "campaign_f_hourly_trace.csv": 20160,
        "campaign_f_anchor_hourly_trace.csv": 1008,
    }
    for name, expected in expected_rows.items():
        with (directory / name).open(encoding="utf-8", newline="") as handle:
            assert len(tuple(csv.reader(handle))) - 1 == expected
    assert len(tuple(directory.glob("campaign_f_*.svg"))) == 10


def test_campaign_f_anchor_crn_and_statistics_gates_fail_under_mutation(
    campaign_f_result: CampaignFResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_signature = campaign_f._D_ANCHOR_SIGNATURES["REFERENCE"]
    monkeypatch.setitem(
        campaign_f._D_ANCHOR_SIGNATURES,
        "REFERENCE",
        (original_signature[0], 0.0, *original_signature[2:]),
    )
    anchor_findings = campaign_f._findings(
        campaign_f_result.paths,
        campaign_f_result.anchors,
        campaign_f_result.regrets,
        campaign_f_result.comparisons,
        campaign_f_result.distributions,
    )
    assert any(item.code == "D_ANCHOR_REPRODUCTION_FAILURE" for item in anchor_findings)
    assert not campaign_f._hard_passed(anchor_findings)

    economic = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.scenario_id == "F-REFERENCE-CORE-00"
        and path.strategy == "Economic"
    )
    changed_day = replace(
        economic.scenario.days[0],
        forecast_pv_profile_kw=(
            999.0,
            *economic.scenario.days[0].forecast_pv_profile_kw[1:],
        ),
    )
    changed_scenario = replace(
        economic.scenario,
        days=(changed_day, *economic.scenario.days[1:]),
    )
    changed_path = replace(economic, scenario=changed_scenario)
    crn_paths = tuple(
        changed_path if path is economic else path for path in campaign_f_result.paths
    )
    crn_findings = campaign_f._findings(
        crn_paths,
        campaign_f_result.anchors,
        campaign_f_result.regrets,
        campaign_f_result.comparisons,
        campaign_f_result.distributions,
    )
    assert any(item.code == "CRN_PAIRING_FAILURE" for item in crn_findings)
    assert not campaign_f._hard_passed(crn_findings)

    tail_regret = next(
        item
        for item in campaign_f_result.regrets
        if item.path.scenario.scenario_class == "tail"
    )
    contaminated = campaign_f._findings(
        campaign_f_result.paths,
        campaign_f_result.anchors,
        (*campaign_f_result.regrets, tail_regret),
        campaign_f_result.comparisons,
        campaign_f_result.distributions,
    )
    assert any(
        item.code == "CORE_TAIL_STATISTICS_CONTAMINATION" for item in contaminated
    )
    assert not campaign_f._hard_passed(contaminated)


def test_campaign_f_exact_identity_gates_reject_balanced_mutations(
    campaign_f_result: CampaignFResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    anchor = campaign_f_result.anchors[0]
    original_terminal = anchor.path.summary.final_terminal_evidence
    changed_terminal = type(
        "TerminalEvidence",
        (),
        {"terminal_energy_value": original_terminal.terminal_energy_value + 1.0},
    )()
    object.__setattr__(anchor.path.summary, "final_terminal_evidence", changed_terminal)
    try:
        anchor_findings = campaign_f._anchor_reproduction_findings(
            campaign_f_result.anchors
        )
    finally:
        object.__setattr__(
            anchor.path.summary, "final_terminal_evidence", original_terminal
        )
    assert any(item.code == "D_ANCHOR_REPRODUCTION_FAILURE" for item in anchor_findings)
    assert not campaign_f._hard_passed(anchor_findings)

    original_signature = campaign_f._D_ANCHOR_SIGNATURES["REFERENCE"]
    monkeypatch.setitem(
        campaign_f._D_ANCHOR_SIGNATURES,
        "REFERENCE",
        (*original_signature[:5], 1.0, *original_signature[6:]),
    )
    expected_findings = campaign_f._anchor_reproduction_findings(
        campaign_f_result.anchors
    )
    assert any(
        item.code == "D_ANCHOR_REPRODUCTION_FAILURE" for item in expected_findings
    )
    assert not campaign_f._hard_passed(expected_findings)

    first_schedule = next(
        item for item in campaign_f_result.paths if item.strategy == "Schedule"
    )
    second_schedule = next(
        item
        for item in campaign_f_result.paths
        if item.strategy == "Schedule" and item is not first_schedule
    )
    duplicate_schedule_paths = tuple(
        first_schedule if item is second_schedule else item
        for item in campaign_f_result.paths
    )
    crn_findings = campaign_f._crn_pairing_findings(duplicate_schedule_paths)
    assert any(item.code == "CRN_PAIRING_FAILURE" for item in crn_findings)
    assert not campaign_f._hard_passed(crn_findings)

    second_scenario = next(
        item.scenario
        for item in campaign_f_result.paths
        if item.scenario is not first_schedule.scenario
    )
    duplicate_scenario_paths = tuple(
        replace(item, scenario=first_schedule.scenario)
        if item.scenario is second_scenario
        else item
        for item in campaign_f_result.paths
    )
    scenario_findings = campaign_f._crn_pairing_findings(duplicate_scenario_paths)
    assert any(item.code == "CRN_PAIRING_FAILURE" for item in scenario_findings)
    assert not campaign_f._hard_passed(scenario_findings)

    core = next(
        item
        for item in campaign_f_result.paths
        if item.scenario.scenario_class == "core" and item.strategy == "Schedule"
    )
    fake_scenario = replace(core.scenario, scenario_id="F-REFERENCE-CORE-99")
    fake_core = replace(core, scenario=fake_scenario)
    replaced_paths = tuple(
        fake_core if item is core else item for item in campaign_f_result.paths
    )
    replaced_regrets = tuple(
        replace(item, path=fake_core) if item.path is core else item
        for item in campaign_f_result.regrets
    )
    core_findings = campaign_f._core_tail_statistics_findings(
        replaced_paths,
        campaign_f_result.anchors,
        replaced_regrets,
        campaign_f_result.distributions,
    )
    assert any(
        item.code == "CORE_TAIL_STATISTICS_CONTAMINATION" for item in core_findings
    )
    assert not campaign_f._hard_passed(core_findings)

    another_core = next(
        item
        for item in campaign_f_result.paths
        if item.scenario.scenario_class == "core"
        and item.strategy == "Schedule"
        and item is not core
    )
    duplicate_core_paths = tuple(
        core if item is another_core else item for item in campaign_f_result.paths
    )
    duplicate_core_regrets = tuple(
        replace(item, path=core) if item.path is another_core else item
        for item in campaign_f_result.regrets
    )
    duplicate_core_findings = campaign_f._core_tail_statistics_findings(
        duplicate_core_paths,
        campaign_f_result.anchors,
        duplicate_core_regrets,
        campaign_f_result.distributions,
    )
    assert any(
        item.code == "CORE_TAIL_STATISTICS_CONTAMINATION"
        for item in duplicate_core_findings
    )
    assert not campaign_f._hard_passed(duplicate_core_findings)


def test_campaign_f_source_selection_and_regret_mapping_reject_mutations(
    campaign_f_result: CampaignFResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_cases = campaign_d_cases
    monkeypatch.setattr(
        campaign_f,
        "campaign_d_cases",
        lambda: tuple(
            item for item in original_cases() if item.case_id != "D02_7D_EVENING_REPEAT"
        ),
    )
    with pytest.raises(ValueError, match="D02_7D_EVENING_REPEAT"):
        campaign_f.campaign_f_regimes()
    monkeypatch.undo()

    schedule_regret = next(
        item for item in campaign_f_result.regrets if item.path.strategy == "Schedule"
    )
    foreign_anchor = replace(
        schedule_regret.anchor,
        regime=next(
            regime
            for regime in campaign_f_result.regimes
            if regime is not schedule_regret.path.scenario.regime
        ),
    )
    with pytest.raises(ValueError, match="same-regime"):
        campaign_f._regret(schedule_regret.path, foreign_anchor)


def test_campaign_f_output_contract_rejects_corrupt_temp_artifacts(
    campaign_f_result: CampaignFResult,
    tmp_path: Path,
) -> None:
    source = campaign_f_result.output_paths[0].parent
    corrupted = tmp_path / "corrupted-output"
    shutil.copytree(source, corrupted)
    (corrupted / "campaign_f_regret_evidence.csv").unlink()
    findings = campaign_f._output_contract_findings(corrupted, campaign_f_result)
    assert len(findings) == 1
    assert findings[0].code == "OUTPUT_CONTRACT_FAILURE"
    assert not campaign_f._hard_passed(findings)


def test_campaign_f_output_contract_validates_final_and_nested_artifacts(
    campaign_f_result: CampaignFResult,
    tmp_path: Path,
) -> None:
    source = campaign_f_result.output_paths[0].parent
    corrupted = tmp_path / "corrupted-final-output"
    shutil.copytree(source, corrupted)

    summary = corrupted / "campaign_f_summary.txt"
    nested = next(corrupted.rglob("mpc_decisions.csv"))
    nested_other = next(
        path
        for path in corrupted.rglob("mpc_decisions.csv")
        if path.read_bytes() != nested.read_bytes()
    )
    originals = {
        summary: summary.read_bytes(),
        nested: nested.read_bytes(),
        nested_other: nested_other.read_bytes(),
    }
    nested_rows = _csv_rows(originals[nested])
    indexes = {name: index for index, name in enumerate(nested_rows[0])}
    summary_fields = dict(campaign_f._summary_fields(summary)[1])

    def summary_with(line: str) -> bytes:
        return _summary_text((*originals[summary].decode("utf-8").splitlines(), line))

    def summary_replacing(key: str, value: str) -> bytes:
        return originals[summary].replace(
            f"{key}={summary_fields[key]}".encode(),
            f"{key}={value}".encode(),
        )

    def mutated_nested(mutate: Callable[[list[list[str]]], object]) -> bytes:
        rows = [list(row) for row in nested_rows]
        mutate(rows)
        return _csv_text(rows)

    nested_mutations: tuple[Callable[[list[list[str]]], object], ...] = (
        lambda rows: rows.pop(1),
        lambda rows: rows.pop(12),
        lambda rows: rows.pop(),
        lambda rows: rows.insert(2, rows[1].copy()),
        lambda rows: rows.append(rows[12].copy()),
        lambda rows: rows.append(rows[-1].copy()),
        lambda rows: rows.__setitem__(slice(1, 3), (rows[2], rows[1])),
        lambda rows: rows[1].__setitem__(indexes["strategy_name"], "forged"),
        lambda rows: rows[12].__setitem__(indexes["strategy_name"], "forged"),
        lambda rows: rows[-1].__setitem__(indexes["strategy_name"], "forged"),
        lambda rows: rows[12].__setitem__(
            indexes["candidate_requested_power_kw"], "1.25"
        ),
        lambda rows: rows[-1].__setitem__(
            indexes["candidate_requested_power_kw"], "1.25"
        ),
        lambda rows: rows[12].__setitem__(
            indexes["timestamp"], rows[11][indexes["timestamp"]]
        ),
        lambda rows: rows[12].__setitem__(
            indexes["timestamp"], rows[13][indexes["timestamp"]]
        ),
        lambda rows: rows[-1].__setitem__(
            indexes["timestamp"], rows[-2][indexes["timestamp"]]
        ),
        lambda rows: rows[1].__setitem__(
            indexes["candidate_requested_power_kw"], "nan"
        ),
        lambda rows: rows[12].__setitem__(
            indexes["candidate_requested_power_kw"], "inf"
        ),
        lambda rows: rows[-1].__setitem__(
            indexes["candidate_requested_power_kw"], "-inf"
        ),
        lambda rows: rows[0].pop(),
        lambda rows: rows[0].append("unknown"),
        lambda rows: rows[0].__setitem__(0, "bad_timestamp"),
        lambda rows: rows[0].__setitem__(slice(0, 2), (rows[0][1], rows[0][0])),
        lambda rows: rows[0].__setitem__(1, rows[0][0]),
    )
    regret_references = json.loads(
        summary_fields["maximum_adjusted_cost_regret_references"]
    )
    summary_mutations = (
        summary_replacing("maximum_adjusted_cost_regret_reference_count", "1"),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(regret_references[:1], separators=(",", ":")),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(regret_references[1:], separators=(",", ":")),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(
                [
                    *regret_references,
                    {
                        "scenario_id": "F-REFERENCE-CORE-00",
                        "strategy": "Schedule",
                        "value": 999.0,
                    },
                ],
                separators=(",", ":"),
            ),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(
                [*regret_references, regret_references[0]], separators=(",", ":")
            ),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(
                [{**regret_references[0], "value": 0.0}, regret_references[1]],
                separators=(",", ":"),
            ),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(
                [{**regret_references[0], "strategy": "forged"}, regret_references[1]],
                separators=(",", ":"),
            ),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(
                [
                    {**regret_references[0], "scenario_id": "forged"},
                    regret_references[1],
                ],
                separators=(",", ":"),
            ),
        ),
        summary_replacing("maximum_adjusted_cost_regret_references", "{"),
        summary_replacing("maximum_adjusted_cost_regret_references", "{}"),
        summary_replacing("maximum_adjusted_cost_regret_references", '["forged"]'),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(
                [{"scenario_id": regret_references[0]["scenario_id"]}],
                separators=(",", ":"),
            ),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(
                [{**regret_references[0], "extra": "forged"}, regret_references[1]],
                separators=(",", ":"),
            ),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            json.dumps(list(reversed(regret_references)), separators=(",", ":")),
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            '[{"scenario_id":"F-HIGH_EVENING_LOAD-F-TAIL-03",'
            '"strategy":"Schedule","value":NaN}]',
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            '[{"scenario_id":"F-HIGH_EVENING_LOAD-F-TAIL-03",'
            '"strategy":"Schedule","value":Infinity}]',
        ),
        summary_replacing(
            "maximum_adjusted_cost_regret_references",
            '[{"scenario_id":"F-HIGH_EVENING_LOAD-F-TAIL-03",'
            '"strategy":"Schedule","value":-Infinity}]',
        ),
    )

    for mutation in nested_mutations:
        nested.write_bytes(mutated_nested(mutation))
        assert campaign_f._nested_csv_failure(
            corrupted, nested.relative_to(corrupted), originals[nested].decode("utf-8")
        )
        nested.write_bytes(originals[nested])

    for content in summary_mutations:
        summary.write_bytes(content)
        _, fields = campaign_f._summary_fields(summary)
        assert campaign_f._maximum_evidence_contract_failures(fields, campaign_f_result)
    summary.write_bytes(summary_with("maximum_adjusted_cost_regret_reference=forged"))
    with pytest.raises(ValueError, match="unexpected field schema"):
        campaign_f._summary_fields(summary)

    for original_path, original in originals.items():
        original_path.write_bytes(original)
    nested.write_bytes(originals[nested_other])
    nested_other.write_bytes(originals[nested])
    assert campaign_f._nested_csv_failure(
        corrupted, nested.relative_to(corrupted), originals[nested].decode("utf-8")
    )


def _csv_rows(content: bytes) -> list[list[str]]:
    return list(csv.reader(StringIO(content.decode("utf-8"))))


def _csv_text(rows: list[list[str]]) -> bytes:
    output = StringIO(newline="")
    csv.writer(output, lineterminator="\n").writerows(rows)
    return output.getvalue().encode("utf-8")


def _summary_text(lines: Iterable[str]) -> bytes:
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_campaign_f_finalization_nested_middle_row_corruption_returns_cli_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    original = campaign_f._write_final_status
    corrupted = False

    def corrupt_once(directory: Path, result: CampaignFResult) -> None:
        nonlocal corrupted
        original(directory, result)
        if result.hard_passed and not corrupted:
            nested = sorted(directory.rglob("mpc_decisions.csv"))[0]
            rows = _csv_rows(nested.read_bytes())
            rows[12][rows[0].index("strategy_name")] = "forged"
            nested.write_bytes(_csv_text(rows))
            corrupted = True

    monkeypatch.setattr(campaign_f, "_write_final_status", corrupt_once)
    assert (
        campaign_f.main(["--output-dir", str(tmp_path / "finalization-corrupt")]) == 1
    )
    assert capsys.readouterr().out.strip() == "FAIL"
    summary = (tmp_path / "finalization-corrupt" / "campaign_f_summary.txt").read_text(
        encoding="utf-8"
    )
    findings = (
        tmp_path / "finalization-corrupt" / "campaign_f_acceptance_findings.csv"
    ).read_text(encoding="utf-8")
    assert "publication_status=FAIL" in summary
    assert "hard_status=FAIL" in summary
    assert "OUTPUT_CONTRACT_FAILURE" in findings


@pytest.mark.parametrize(
    ("mutation", "expected_contract_failure"),
    (
        (
            "omit_schedule",
            "maximum_adjusted_cost_regret_references retained argmax set",
        ),
        (
            "wrong_scenario",
            "maximum_actual_power_difference_references retained argmax set",
        ),
        (
            "extra_nonmaximum",
            "maximum_physical_revisions_references retained argmax set",
        ),
        (
            "wrong_count",
            "maximum_adjusted_cost_regret_reference_count mismatch",
        ),
        ("malformed_json", "maximum_actual_power_difference_references encoding"),
    ),
)
def test_campaign_f_generator_mutations_reach_full_publication_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutation: str,
    expected_contract_failure: str,
) -> None:
    """Generator faults must traverse the actual final publication orchestration."""

    original_write_final_status = campaign_f._write_final_status
    original_output_validator = campaign_f._output_contract_findings
    original_nested_validator = campaign_f._nested_csv_failure
    final_gate_nested_counts: list[int] = []
    nested_calls: list[Path] = []
    writes = 0

    def count_nested(
        directory: Path, relative: Path, expected_content: str
    ) -> str | None:
        nested_calls.append(relative)
        return original_nested_validator(directory, relative, expected_content)

    def count_final_gate(
        directory: Path, result: CampaignFResult, *, final_artifacts: bool = True
    ) -> tuple[campaign_f.CampaignFAcceptanceFinding, ...]:
        if final_artifacts:
            nested_calls.clear()
        findings = original_output_validator(
            directory, result, final_artifacts=final_artifacts
        )
        if final_artifacts:
            final_gate_nested_counts.append(len(nested_calls))
        return findings

    def write_mutated_once(directory: Path, result: CampaignFResult) -> None:
        nonlocal writes
        writes += 1
        if writes != 1:
            original_write_final_status(directory, result)
            return
        restore = _install_generator_argmax_mutation(monkeypatch, mutation)
        try:
            original_write_final_status(directory, result)
        finally:
            restore()

    monkeypatch.setattr(campaign_f, "_nested_csv_failure", count_nested)
    monkeypatch.setattr(campaign_f, "_output_contract_findings", count_final_gate)
    monkeypatch.setattr(campaign_f, "_write_final_status", write_mutated_once)

    directory = tmp_path / f"generator-{mutation}"
    assert campaign_f.main(["--output-dir", str(directory)]) == 1
    captured = capsys.readouterr().out
    assert captured.strip() == "FAIL"
    assert "PASS" not in captured
    assert final_gate_nested_counts == [882]
    assert writes == 2

    _, fields = campaign_f._summary_fields(directory / "campaign_f_summary.txt")
    summary = dict(fields)
    with (directory / "campaign_f_acceptance_findings.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        findings = tuple(csv.DictReader(handle))
    assert summary["hard_status"] == "FAIL"
    assert summary["publication_status"] == "FAIL"
    assert "PENDING" not in summary.values()
    assert findings
    output_contract_findings = tuple(
        item for item in findings if item["code"] == "OUTPUT_CONTRACT_FAILURE"
    )
    assert output_contract_findings
    assert any(
        expected_contract_failure in item["evidence_reference"]
        for item in output_contract_findings
    )


def test_campaign_f_normal_cli_remains_clean_after_generator_failure_regressions(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A normal production run remains independent of generator-fault tests."""

    directory = tmp_path / "normal-after-generator-failures"
    assert campaign_f.main(["--output-dir", str(directory)]) == 0
    assert capsys.readouterr().out.strip() == "PASS"

    _, fields = campaign_f._summary_fields(directory / "campaign_f_summary.txt")
    summary = dict(fields)
    with (directory / "campaign_f_acceptance_findings.csv").open(
        encoding="utf-8", newline=""
    ) as handle:
        findings = tuple(csv.DictReader(handle))
    assert summary["hard_status"] == "PASS"
    assert summary["publication_status"] == "PASS"
    assert summary["findings"] == "0"
    assert summary["maximum_adjusted_cost_regret_reference_count"] == "2"
    assert summary["maximum_actual_power_difference_reference_count"] == "2"
    assert summary["maximum_physical_revisions_reference_count"] == "2"
    assert findings == ()


def test_campaign_f_csv_reconciliation_and_visible_svg_traceability(
    campaign_f_result: CampaignFResult,
) -> None:
    directory = campaign_f_result.output_paths[0].parent
    all_paths = {}
    for name in (
        "campaign_f_path_results.csv",
        "campaign_f_anchor_path_results.csv",
    ):
        with (directory / name).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                all_paths[(row["path_id"], row["strategy"])] = row
    daily: dict[tuple[str, str], list[dict[str, str]]] = {}
    for name in (
        "campaign_f_daily_results.csv",
        "campaign_f_anchor_daily_results.csv",
    ):
        with (directory / name).open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                daily.setdefault((row["path_id"], row["strategy"]), []).append(row)
    assert len(all_paths) == 126
    for key, path_row in all_paths.items():
        operating = sum(
            (
                float(row["import_cost"])
                - float(row["export_revenue"])
                + float(row["degradation_cost"])
                for row in daily[key]
            ),
            0.0,
        )
        assert float(path_row["adjusted_net_economic_cost"]) == pytest.approx(
            operating - float(path_row["terminal_value"]), abs=1e-9
        )
    for svg_path in directory.glob("campaign_f_*.svg"):
        root = ElementTree.parse(svg_path).getroot()
        visible = " ".join(
            element.text or ""
            for element in root.iter()
            if element.tag.endswith("text")
        )
        assert "unit=" in visible
        assert "R=REFERENCE" in visible
        assert "HP=HIGH_PV" in visible
        assert "HEL=HIGH_EVENING_LOAD" in visible
        assert "S=Schedule" in visible
        assert "E=Economic" in visible
        assert "mapping=" in visible
    negative_svg = campaign_f._bar_svg("A & B", "kW", (("A < B", -1.0), ("C", 1.0)))
    assert "A &amp; B" in negative_svg
    assert "A &lt; B" in negative_svg
    assert 'y1="250.00"' not in negative_svg


def test_campaign_f_crn_gate_reads_retained_runner_forecast_input(
    campaign_f_result: CampaignFResult,
) -> None:
    economic = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.scenario_id == "F-REFERENCE-CORE-00"
        and path.strategy == "Economic"
    )
    day = economic.summary.days[0]
    trajectory = day.trajectory
    daily_mpc = trajectory.source_input.daily_mpc_input
    horizon = daily_mpc.forecast_horizons[0]
    changed_point = replace(horizon.points[0], pv_power_kw=999.0)
    changed_horizon = replace(horizon, points=(changed_point, *horizon.points[1:]))
    changed_daily_mpc = replace(
        daily_mpc,
        forecast_horizons=(changed_horizon, *daily_mpc.forecast_horizons[1:]),
    )
    changed_trajectory = replace(
        trajectory,
        source_input=replace(
            trajectory.source_input, daily_mpc_input=changed_daily_mpc
        ),
    )
    changed_day = replace(day, trajectory=changed_trajectory)
    changed_path = replace(
        economic,
        summary=replace(
            economic.summary, days=(changed_day, *economic.summary.days[1:])
        ),
    )
    changed_paths = tuple(
        changed_path if path is economic else path for path in campaign_f_result.paths
    )
    findings = campaign_f._crn_pairing_findings(changed_paths)
    assert any(item.code == "CRN_PAIRING_FAILURE" for item in findings)
    assert not campaign_f._hard_passed(findings)


def test_campaign_f_runner_input_boundary_covers_core_tail_reversal_and_anchor(
    campaign_f_result: CampaignFResult,
) -> None:
    reference_core = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.scenario_id == "F-REFERENCE-CORE-00"
        and path.strategy == "Economic"
    )
    clipped_core = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.scenario_class == "core"
        and path.strategy == "Schedule"
        and any(any(day.clip_flags) for day in path.scenario.days)
    )
    amplitude_tail = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.tail_case_id == "F-TAIL-01" and path.strategy == "Schedule"
    )
    timing_tail = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.tail_case_id == "F-TAIL-03" and path.strategy == "Economic"
    )
    reversal_tail = next(
        path
        for path in campaign_f_result.paths
        if path.scenario.tail_case_id == "F-TAIL-04" and path.strategy == "Schedule"
    )
    selected = (
        reference_core,
        clipped_core,
        amplitude_tail,
        timing_tail,
        reversal_tail,
    )
    assert not campaign_f._runner_input_boundary_findings(selected, ())
    assert not campaign_f._runner_input_boundary_findings(
        (), tuple(campaign_f_result.anchors)
    )

    for path in selected:
        day_index = 2 if path is reversal_tail else 0
        day = path.summary.days[day_index]
        daily_mpc = day.trajectory.source_input.daily_mpc_input
        horizon = daily_mpc.forecast_horizons[0]
        changed_point = replace(horizon.points[0], pv_power_kw=999.0)
        changed_trajectory = replace(
            day.trajectory,
            source_input=replace(
                day.trajectory.source_input,
                daily_mpc_input=replace(
                    daily_mpc,
                    forecast_horizons=(
                        replace(
                            horizon,
                            points=(changed_point, *horizon.points[1:]),
                        ),
                        *daily_mpc.forecast_horizons[1:],
                    ),
                ),
            ),
        )
        changed_path = replace(
            path,
            summary=replace(
                path.summary,
                days=(
                    *path.summary.days[:day_index],
                    replace(day, trajectory=changed_trajectory),
                    *path.summary.days[day_index + 1 :],
                ),
            ),
        )
        findings = campaign_f._runner_input_boundary_findings((changed_path,), ())
        assert any(item.code == "RUNNER_INPUT_BOUNDARY_FAILURE" for item in findings)
        assert not campaign_f._hard_passed(findings)


def test_campaign_f_writer_exception_returns_cli_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    def writer_failure(_: Path, __: CampaignFResult) -> None:
        raise OSError("injected final writer failure")

    monkeypatch.setattr(campaign_f, "_write_final_status", writer_failure)
    assert campaign_f.main(["--output-dir", str(tmp_path / "writer-failure")]) == 1
    assert capsys.readouterr().out.strip() == "FAIL"


def test_campaign_f_ecdf_visible_rank_mapping_matches_independent_sort(
    campaign_f_result: CampaignFResult,
) -> None:
    regrets = tuple(
        item
        for item in campaign_f_result.regrets
        if item.path.scenario.regime.regime_id == "REFERENCE"
        and item.path.scenario.scenario_class == "core"
    )
    svg = campaign_f._ecdf_svg("reference", regrets)
    root = ElementTree.fromstring(svg)
    visible = "\n".join(
        element.text or "" for element in root.iter() if element.tag.endswith("text")
    )
    for strategy, short in (("Schedule", "S"), ("Economic", "E")):
        ordered = sorted(
            (item for item in regrets if item.path.strategy == strategy),
            key=lambda item: (
                item.adjusted_cost_regret,
                item.path.scenario.scenario_id,
                item.path.strategy,
            ),
        )
        assert len(ordered) == 16
        for rank, item in enumerate(ordered, start=1):
            expected = (
                f"{rank:02d}=R-C{item.path.scenario.core_sample_index:02d}-{short}:"
                f"{item.adjusted_cost_regret:.6f}"
            )
            assert expected in visible
