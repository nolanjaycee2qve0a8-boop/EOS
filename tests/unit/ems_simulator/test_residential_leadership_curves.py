from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest

from tools.generate_residential_leadership_curves import generate_report
from tools.verify_residential_a_f_leadership_snapshots import (
    _SNAPSHOTS,
    SnapshotContractError,
    _pdf_page_text,
    _pptx_slide_text,
    _sha256,
    validate_and_export,
)


def _snapshot_directory() -> Path:
    return Path(__file__).resolve().parents[3] / "docs" / "reports" / "residential_a_f"


def _rewrite_zip_member(path: Path, member: str, replacement: bytes | None) -> None:
    rewritten = path.with_suffix(".rewritten.pptx")
    with zipfile.ZipFile(path) as source, zipfile.ZipFile(rewritten, "w") as target:
        for info in source.infolist():
            if info.filename == member and replacement is None:
                continue
            if info.filename == member:
                assert replacement is not None
                target.writestr(info, replacement)
            else:
                target.writestr(info, source.read(info.filename))
    rewritten.replace(path)


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


def test_snapshot_validator_exports_byte_identical_tracked_release_files(
    tmp_path: Path,
) -> None:
    source = _snapshot_directory()
    exported = tmp_path / "export"

    validate_and_export(source, exported)

    for name, _ in _SNAPSHOTS:
        assert _sha256(exported / name) == _sha256(source / name)


def test_snapshot_validator_fails_when_a_required_snapshot_is_missing(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "snapshots"
    shutil.copytree(_snapshot_directory(), copied)
    (copied / _SNAPSHOTS[-1][0]).unlink()

    with pytest.raises(FileNotFoundError):
        validate_and_export(copied, tmp_path / "export")


def test_snapshot_validator_fails_when_technical_pptx_page_count_is_wrong(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "snapshots"
    shutil.copytree(_snapshot_directory(), copied)
    _rewrite_zip_member(
        copied / _SNAPSHOTS[0][0],
        "ppt/slides/slide21.xml",
        None,
    )

    with pytest.raises(SnapshotContractError, match="expected 21 pages, got 20"):
        validate_and_export(copied, tmp_path / "export")


def test_snapshot_validator_fails_when_slide20_count_contract_is_missing(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "snapshots"
    shutil.copytree(_snapshot_directory(), copied)
    technical_pptx = copied / _SNAPSHOTS[0][0]
    with zipfile.ZipFile(technical_pptx) as archive:
        slide20 = archive.read("ppt/slides/slide20.xml")
    _rewrite_zip_member(
        technical_pptx,
        "ppt/slides/slide20.xml",
        slide20.replace(b"164 SOC boundaries", b"164 SOC boundary-missing"),
    )

    with pytest.raises(
        SnapshotContractError,
        match="technical PPTX slide 20: missing 164 SOC boundaries",
    ):
        validate_and_export(copied, tmp_path / "export")


def test_tracked_technical_pdf_page20_exposes_all_fine_grained_counts() -> None:
    technical_pdf = _snapshot_directory() / _SNAPSHOTS[1][0]
    page20_text = _pdf_page_text(technical_pdf, 20)

    for count in (
        "164 SOC boundaries",
        "192 comparisons",
        "384 regrets",
        "21,168 hourly records",
        "756 SOC boundaries",
        "908 artifacts",
    ):
        assert count in page20_text


def test_tracked_technical_pptx_slide20_exposes_full_a_to_f_count_contract() -> None:
    technical_pptx = _snapshot_directory() / _SNAPSHOTS[0][0]
    slide20_text = _pptx_slide_text(technical_pptx, 20)

    for count in (
        "24 scenarios",
        "144 logical paths",
        "78 independent executions",
        "176 daily executions",
        "390 executions",
        "882 daily executions",
        "164 SOC boundaries",
        "192 comparisons",
        "384 regrets",
        "21,168 hourly records",
        "756 SOC boundaries",
        "908 artifacts",
    ):
        assert count in slide20_text
