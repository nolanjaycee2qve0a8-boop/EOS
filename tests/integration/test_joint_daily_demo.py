"""Independent file-output contract; no legacy runner replacement."""

import csv
import json
from pathlib import Path

import pytest

from ems_simulator.demo import run_demo
from tools import joint_daily_demo
from tools.joint_daily_demo import run_daily


def test_day_writes_separate_report_and_does_not_overwrite(tmp_path: Path) -> None:
    output = tmp_path / "day"
    run_daily(output, mode="ideal")
    summary = json.loads((output / "joint_summary.json").read_text(encoding="utf-8"))
    assert summary["utc_start"] == "2026-01-01T00:00:00+00:00"
    assert len(summary["ems_decisions"]) == 24
    assert (output / "joint_power.svg").exists()
    assert (output / "ledger.csv").exists()
    assert json.loads((output / "manifest.json").read_text())["state"] == "completed"
    before = (output / "ledger.csv").read_bytes()
    with pytest.raises(FileExistsError):
        run_daily(output, mode="ideal")
    assert (output / "ledger.csv").read_bytes() == before


def test_replay_is_from_start_not_resume(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    run_daily(a, mode="ideal")
    run_daily(b, mode="ideal")
    for path in a.iterdir():
        assert path.read_bytes() == (b / path.name).read_bytes()


def test_output_failure_cannot_claim_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*args: object, **kwargs: object) -> dict[str, object]:
        raise OSError("test-only output failure")

    monkeypatch.setattr(joint_daily_demo, "write_daily_output", fail)
    with pytest.raises(OSError, match="test-only"):
        run_daily(tmp_path / "failure", mode="ideal")
    state = json.loads((tmp_path / "failure" / "manifest.json").read_text())
    assert state["state"] == "failed"


def test_legacy_demo_keeps_its_files(tmp_path: Path) -> None:
    result = run_demo(tmp_path / "legacy")
    assert len(result.simulation_result.traces) == 24
    assert (tmp_path / "legacy" / "simulation_result.csv").exists()
    assert not (tmp_path / "legacy" / "joint_summary.json").exists()


def test_hourly_csv_reaggregates_the_unique_ledger(tmp_path: Path) -> None:
    output = tmp_path / "reaggregate"
    run_daily(output, mode="dynamic")
    summary = json.loads((output / "joint_summary.json").read_text(encoding="utf-8"))
    with (output / "joint_hourly.csv").open(encoding="utf-8", newline="") as stream:
        hours = list(csv.DictReader(stream))
    from tools.joint_daily_output import ENERGIES

    assert len(hours) == 24
    for key in ENERGIES:
        assert (
            abs(sum(float(row[key]) for row in hours) - summary["totals"][key])
            <= 2.4e-8
        )
    assert abs(float(hours[-1]["soc_end"]) - summary["totals"]["soc_end"]) <= 1e-9
    assert summary["budgets"]["existing_excursion_s"] == 96
    assert summary["budgets"]["limited_full_response_envelope_s"] == 97
