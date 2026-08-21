"""Validate and export the checked-in Residential EMS A-F report snapshots.

This is deliberately a snapshot validator/exporter. It does not regenerate
the report layout, rerun Campaign evidence generation, or create new PDFs.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import zipfile
import zlib
from pathlib import Path
from xml.etree import ElementTree

_SNAPSHOTS = (
    ("EOS_Residential_EMS_A-F_Leadership_Report_With_Curves_CN.pptx", 21),
    ("EOS_Residential_EMS_A-F_Leadership_Report_With_Curves_CN.pdf", 21),
    ("EOS_Residential_EMS_A-F_Leadership_Executive_CN.pptx", 12),
    ("EOS_Residential_EMS_A-F_Leadership_Executive_CN.pdf", 12),
)
_FORBIDDEN_MARKERS = ("TUSHARE_TOKEN", "C:\\Users\\", "AppData", "\\tmp\\")
_REPORT_TITLE = "Residential EMS 1.0"
_SLIDE20_TITLE = "A-F VALIDATION LADDER"
_SLIDE20_COUNTS = (
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
)
_DRAWING_TEXT = "{http://schemas.openxmlformats.org/drawingml/2006/main}t"


class SnapshotContractError(ValueError):
    """A checked-in release snapshot violates its published contract."""


def _snapshot_directory() -> Path:
    return Path(__file__).resolve().parents[1] / "docs" / "reports" / "residential_a_f"


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pptx_slide_names(path: Path) -> tuple[str, ...]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None:
                raise SnapshotContractError(f"{path.name}: corrupt PPTX member")
            return tuple(
                name
                for name in archive.namelist()
                if name.startswith("ppt/slides/slide") and name.endswith(".xml")
            )
    except zipfile.BadZipFile as error:
        raise SnapshotContractError(f"{path.name}: cannot parse PPTX") from error


def _pptx_slide_text(path: Path, slide_number: int) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            source = archive.read(f"ppt/slides/slide{slide_number}.xml")
    except (KeyError, zipfile.BadZipFile) as error:
        raise SnapshotContractError(
            f"{path.name}: cannot read slide {slide_number}"
        ) from error
    try:
        root = ElementTree.fromstring(source)
    except ElementTree.ParseError as error:
        raise SnapshotContractError(
            f"{path.name}: cannot parse slide {slide_number}"
        ) from error
    return "\n".join(node.text for node in root.iter(_DRAWING_TEXT) if node.text)


def _pdf_objects(path: Path) -> dict[int, bytes]:
    data = path.read_bytes()
    if not data.startswith(b"%PDF-"):
        raise SnapshotContractError(f"{path.name}: cannot parse PDF")
    objects = {
        int(match.group(1)): match.group(3)
        for match in re.finditer(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", data, re.DOTALL)
    }
    if not objects:
        raise SnapshotContractError(f"{path.name}: cannot parse PDF objects")
    return objects


def _pdf_page_objects(path: Path) -> tuple[dict[int, bytes], tuple[bytes, ...]]:
    objects = _pdf_objects(path)
    pages = tuple(
        body
        for body in objects.values()
        if re.search(rb"/Type\s*/Page(?!s)", body) is not None
    )
    if not pages:
        raise SnapshotContractError(f"{path.name}: no PDF pages")
    return objects, pages


def _pdf_unescape_literal(value: bytes) -> str:
    payload = re.sub(
        rb"\\\\([0-7]{1,3})",
        lambda match: bytes((int(match.group(1), 8),)),
        value,
    )
    payload = (
        payload.replace(b"\\\\(", b"(")
        .replace(b"\\\\)", b")")
        .replace(b"\\\\\\", b"\\")
    )
    return payload.decode("latin-1", errors="ignore")


def _pdf_page_text(path: Path, page_number: int) -> str:
    objects, pages = _pdf_page_objects(path)
    if not 1 <= page_number <= len(pages):
        raise SnapshotContractError(f"{path.name}: no page {page_number}")
    page = pages[page_number - 1]
    content_references = [
        int(value) for value in re.findall(rb"/Contents\s+(\d+)\s+\d+\s+R", page)
    ]
    if not content_references:
        arrays = re.findall(rb"/Contents\s*\[(.*?)\]", page, re.DOTALL)
        content_references = [
            int(value)
            for array in arrays
            for value in re.findall(rb"(\d+)\s+\d+\s+R", array)
        ]
    if not content_references:
        raise SnapshotContractError(f"{path.name}: page {page_number} has no content")
    streams: list[bytes] = []
    for reference in content_references:
        body = objects.get(reference)
        if body is None:
            raise SnapshotContractError(f"{path.name}: missing PDF content object")
        stream = re.search(rb"stream\r?\n(.*?)\r?\nendstream", body, re.DOTALL)
        if stream is None:
            raise SnapshotContractError(f"{path.name}: missing PDF content stream")
        content = stream.group(1)
        if b"/FlateDecode" in body[: stream.start()]:
            try:
                content = zlib.decompress(content)
            except zlib.error as error:
                raise SnapshotContractError(
                    f"{path.name}: cannot decompress PDF content"
                ) from error
        streams.append(content)
    literals = re.findall(rb"\((?:\\.|[^\\)])*\)", b"\n".join(streams))
    # PowerPoint places BDC language metadata such as ``(en-US)`` between
    # adjacent glyph runs. It is not visible page text and must not break a
    # required-title match after the literal strings are concatenated.
    return "".join(_pdf_unescape_literal(value[1:-1]) for value in literals).replace(
        "en-US", ""
    )


def _check_sensitive_markers(path: Path) -> None:
    data = path.read_bytes()
    if any(marker.encode("utf-8") in data for marker in _FORBIDDEN_MARKERS):
        raise SnapshotContractError(f"{path.name}: forbidden local/sensitive marker")


def _check_snapshot(path: Path, expected_pages: int) -> None:
    _require_file(path)
    pages = (
        len(_pptx_slide_names(path))
        if path.suffix == ".pptx"
        else len(_pdf_page_objects(path)[1])
    )
    if pages != expected_pages:
        raise SnapshotContractError(
            f"{path.name}: expected {expected_pages} pages, got {pages}"
        )
    _check_sensitive_markers(path)


def _check_technical_contract(snapshot_directory: Path) -> None:
    technical_pptx = snapshot_directory / _SNAPSHOTS[0][0]
    technical_pdf = snapshot_directory / _SNAPSHOTS[1][0]
    pptx_title = _pptx_slide_text(technical_pptx, 1)
    pdf_title = _pdf_page_text(technical_pdf, 1)
    if _REPORT_TITLE not in pptx_title or _REPORT_TITLE not in pdf_title:
        raise SnapshotContractError("technical report: missing Residential EMS title")
    pptx_text = _pptx_slide_text(technical_pptx, 20)
    pdf_text = _pdf_page_text(technical_pdf, 20)
    if _SLIDE20_TITLE not in pptx_text or _SLIDE20_TITLE not in pdf_text:
        raise SnapshotContractError(
            "technical slide 20: missing validation-ladder title"
        )
    for count in _SLIDE20_COUNTS:
        if count not in pptx_text:
            raise SnapshotContractError(f"technical PPTX slide 20: missing {count}")
        if count not in pdf_text:
            raise SnapshotContractError(f"technical PDF page 20: missing {count}")


def validate_and_export(snapshot_directory: Path, export_directory: Path) -> None:
    """Validate four tracked snapshots and copy their bytes to ``export_directory``."""
    for name, pages in _SNAPSHOTS:
        _check_snapshot(snapshot_directory / name, pages)
    _check_technical_contract(snapshot_directory)
    export_directory.mkdir(parents=True, exist_ok=True)
    for name, pages in _SNAPSHOTS:
        source = snapshot_directory / name
        destination = export_directory / name
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)
        _check_snapshot(destination, pages)
        if _sha256(source) != _sha256(destination):
            raise SnapshotContractError(f"{name}: export SHA-256 mismatch")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and export checked-in Residential EMS A-F report snapshots."
        )
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        required=True,
        help="Directory that receives byte-identical copies of the tracked snapshots.",
    )
    arguments = parser.parse_args()
    try:
        validate_and_export(_snapshot_directory(), arguments.export_dir.resolve())
    except (FileNotFoundError, SnapshotContractError) as error:
        print(f"FAIL snapshot_validation: {error}", file=sys.stderr)
        return 1
    print("PASS snapshot_validation technical=21 executive=12 exported=4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
