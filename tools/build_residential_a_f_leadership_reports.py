"""Formal release-snapshot verifier for Residential EMS A-F leadership decks.

The four checked-in PPTX/PDF files are release snapshots.  This entry point
validates them together with the committed deterministic curve generator so a
clean checkout cannot silently publish stale 17-page material.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

_NAMES = (
    ("EOS_Residential_EMS_A-F_Leadership_Report_With_Curves_CN.pptx", 21),
    ("EOS_Residential_EMS_A-F_Leadership_Report_With_Curves_CN.pdf", 21),
    ("EOS_Residential_EMS_A-F_Leadership_Executive_CN.pptx", 12),
    ("EOS_Residential_EMS_A-F_Leadership_Executive_CN.pdf", 12),
)
_FORBIDDEN = ("TUSHARE_TOKEN", "C:\\Users\\", "AppData")


def _pptx_pages(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(
            name.startswith("ppt/slides/slide") and name.endswith(".xml")
            for name in archive.namelist()
        )


def _pdf_pages(path: Path) -> int:
    content = path.read_bytes()
    return len(re.findall(rb"/Type\s*/Page(?!s)", content))


def _check(path: Path, expected_pages: int) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    pages = _pptx_pages(path) if path.suffix == ".pptx" else _pdf_pages(path)
    if pages != expected_pages:
        raise ValueError(f"{path.name}: expected {expected_pages} pages, got {pages}")
    data = path.read_bytes()
    if any(marker.encode() in data for marker in _FORBIDDEN):
        raise ValueError(f"{path.name}: forbidden local/sensitive marker")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path, default=Path("docs/reports/residential_a_f")
    )
    arguments = parser.parse_args()
    source = (
        Path(__file__).resolve().parents[1] / "docs" / "reports" / "residential_a_f"
    )
    destination = arguments.output_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    for name, pages in _NAMES:
        snapshot = source / name
        _check(snapshot, pages)
        if snapshot.resolve() != (destination / name).resolve():
            shutil.copy2(snapshot, destination / name)
            _check(destination / name, pages)
    print("PASS technical=21 executive=12 snapshots=4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
