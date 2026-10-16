"""Focused contract tests for the isolated reserve-target comparison."""

import hashlib
import json
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from tools.joint_strategy_comparison import comparison_cases
from tools.reserve_target_isolation_experiment import (
    GapSlice,
    build_cases,
    common_target_gap,
    run_experiment,
)


def _source_bytes() -> bytes:
    return json.dumps(
        {name: asdict(case) for name, case in comparison_cases().items()},
        sort_keys=True,
    ).encode()


def test_exact_frozen_source_and_only_A_target_changes() -> None:
    source = _source_bytes()
    assert hashlib.sha256(source).hexdigest() == (
        "3b37c192d720b4f9608693240ee87643b1ed9f7dabc55653baa3d3a1c32cc10a"
    )
    a, b = build_cases(source)
    assert a.initial_soc == b.initial_soc == 0.5
    assert len(a.segments) == len(b.segments) == 25
    assert {fact.reserve_target_soc for fact in a.segments} == {0.2}
    assert [
        (fact.start, fact.reserve_target_soc)
        for i, fact in enumerate(b.segments)
        if i == 0 or fact.reserve_target_soc != b.segments[i - 1].reserve_target_soc
    ] == [(0, 0.8), (64800, 0.9)]
    assert all(
        replace(left, reserve_target_soc=right.reserve_target_soc) == right
        for left, right in zip(a.segments, b.segments, strict=True)
    )


def test_source_digest_or_schedule_change_fails_closed() -> None:
    source = _source_bytes()
    with pytest.raises(ValueError, match="SHA-256 differs"):
        build_cases(source + b" ")


def test_common_B_target_splits_at_64800_without_control_feedback() -> None:
    # A constant SOC of 50% has 3 kWh of B-target gap for 18 h,
    # then 4 kWh of B-target gap for 6 h. A 20% self-target has no gap.
    common = common_target_gap((GapSlice(0, 86400, 0.5, 0.5),), 0.5)
    assert common == {
        "terminal_kwh": pytest.approx(4.0),
        "peak_kwh": pytest.approx(4.0),
        "integral_kwh_h": pytest.approx(78.0),
    }
    assert (
        common_target_gap(
            (GapSlice(0, 64800, 0.5, 0.5), GapSlice(64800, 21600, 0.5, 0.5)),
            0.5,
        )
        == common
    )


def test_common_target_rejects_gaps_and_missing_terminal_coverage() -> None:
    with pytest.raises(ValueError, match="contiguous"):
        common_target_gap((GapSlice(1, 86399, 0.5, 0.5),), 0.5)
    with pytest.raises(ValueError, match="complete day"):
        common_target_gap((GapSlice(0, 64800, 0.5, 0.5),), 0.5)


def test_existing_output_is_rejected_before_simulation(tmp_path: Path) -> None:
    source = tmp_path / "inputs.json"
    source.write_bytes(_source_bytes())
    output = tmp_path / "already-exists"
    output.mkdir()
    with pytest.raises(FileExistsError, match="already exists"):
        run_experiment(source, output)
