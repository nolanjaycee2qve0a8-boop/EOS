"""Focused input and reporting guards for the one-event cutoff experiment."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from tools.grid_charge_cutoff_experiment import (
    CANDIDATE_CUTOFF_S,
    EXPECTED_CANDIDATE_EVENTS,
    EXPECTED_PERMISSION_EVENTS,
    ORIGINAL_CUTOFF_S,
    build_pair,
    compare_outcomes,
    permission_events,
    run_experiment,
    validate_pair,
)
from tools.joint_strategy_comparison import comparison_cases


def _source_bytes() -> bytes:
    return json.dumps(
        {name: asdict(case) for name, case in comparison_cases().items()},
        sort_keys=True,
    ).encode()


def test_frozen_B_schedule_and_exactly_one_moved_permission_event() -> None:
    source = _source_bytes()
    assert hashlib.sha256(source).hexdigest() == (
        "3b37c192d720b4f9608693240ee87643b1ed9f7dabc55653baa3d3a1c32cc10a"
    )
    baseline, candidate = build_pair(source)
    assert permission_events(baseline) == EXPECTED_PERMISSION_EVENTS
    assert permission_events(candidate) == EXPECTED_CANDIDATE_EVENTS
    assert baseline.initial_soc == candidate.initial_soc == 0.5
    assert len(baseline.segments) == len(candidate.segments) == 25
    assert [
        (left.start, left.end, left.grid_charge_allowed, right.grid_charge_allowed)
        for left, right in zip(baseline.segments, candidate.segments, strict=True)
        if left != right
    ] == [(CANDIDATE_CUTOFF_S, ORIGINAL_CUTOFF_S, True, False)]
    assert all(
        replace(right, grid_charge_allowed=left.grid_charge_allowed) == left
        for left, right in zip(baseline.segments, candidate.segments, strict=True)
    )


def test_source_digest_change_fails_before_any_execution() -> None:
    with pytest.raises(ValueError, match="SHA-256 differs"):
        build_pair(_source_bytes() + b" ")


def test_other_fact_or_extra_permission_change_is_rejected() -> None:
    baseline, candidate = build_pair(_source_bytes())
    altered = list(candidate.segments)
    altered[0] = replace(altered[0], load_kw=altered[0].load_kw + 0.1)
    with pytest.raises(ValueError, match="non-permission fact"):
        validate_pair(baseline, replace(candidate, segments=tuple(altered)))
    altered = list(candidate.segments)
    altered[0] = replace(altered[0], grid_charge_allowed=False)
    with pytest.raises(ValueError, match="sole input difference"):
        validate_pair(baseline, replace(candidate, segments=tuple(altered)))


def test_same_time_load_fact_and_hourly_decisions_are_retained() -> None:
    baseline, candidate = build_pair(_source_bytes())
    previous = next(f for f in baseline.segments if f.start == 14400)
    changed = next(f for f in candidate.segments if f.start == 18000)
    following = next(f for f in candidate.segments if f.start == 21600)
    assert (previous.load_kw, changed.load_kw, following.load_kw) == (0.7, 0.9, 1.4)
    assert (previous.pv_kw, changed.pv_kw, following.pv_kw) == (0.0, 0.0, 0.2)
    assert CANDIDATE_CUTOFF_S % 3600 == ORIGINAL_CUTOFF_S % 3600 == 0


def test_tradeoff_does_not_call_a_cost_saving_a_guarded_improvement() -> None:
    baseline: dict[str, object] = {
        "assessment": "PASS",
        "common_B_target_gap": {
            "terminal_kwh": 0.0,
            "peak_kwh": 3.0,
            "integral_kwh_h": 3.25,
        },
        "metrics": {
            "net_cost_cny": 14.0,
            "curtailed_pv_kwh": 26.0,
            "prohibited_grid_charge_kwh": 0.05,
        },
    }
    candidate: dict[str, object] = {
        **baseline,
        "common_B_target_gap": {
            "terminal_kwh": 0.0,
            "peak_kwh": 3.0,
            "integral_kwh_h": 3.26,
        },
        "metrics": {
            "net_cost_cny": 13.0,
            "curtailed_pv_kwh": 25.0,
            "prohibited_grid_charge_kwh": 0.05,
        },
    }
    comparison = compare_outcomes(baseline, candidate)
    assert comparison["common_gap_worsened"] == {
        "terminal_kwh": False,
        "peak_kwh": False,
        "integral_kwh_h": True,
    }
    assert comparison["non_worsening_guarded_improvement"] is False


def test_existing_output_is_rejected_without_rerunning(tmp_path: Path) -> None:
    source = tmp_path / "inputs.json"
    source.write_bytes(_source_bytes())
    output = tmp_path / "existing"
    output.mkdir()
    with pytest.raises(FileExistsError):
        run_experiment(source, output)
