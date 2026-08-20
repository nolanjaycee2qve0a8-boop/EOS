from pathlib import Path

from tools.generate_residential_leadership_curves import generate_report


def test_leadership_curve_export_uses_six_independent_frozen_paths(
    tmp_path: Path,
) -> None:
    result = generate_report(tmp_path)

    assert len(result.paths) == 6
    assert len({id(path.trajectory) for path in result.paths}) == 6
    hourly_rows = result.hourly_csv.read_text(encoding="utf-8").splitlines()
    assert len(hourly_rows) == 145
    assert "SIMULATOR_ACTUAL" in hourly_rows[1]
    assert "INTERVAL_FINAL_SIMULATOR_NEXT_STATE" in hourly_rows[1]
    assert all(path.acceptance.passed for path in result.paths)
    assert all(path.exists() for path in result.charts)
