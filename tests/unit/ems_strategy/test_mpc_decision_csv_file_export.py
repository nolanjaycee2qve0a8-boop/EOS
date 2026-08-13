"""Tests for caller-owned filesystem export of pre-serialized MPC CSV text."""

# ruff: noqa: RUF001

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import ems_strategy
from ems_strategy import (
    DeterministicExplainableMPCDecisionCSVFileExporter,
    ExplainableMPCDecisionCSVFileExporterBoundary,
    ExplainableMPCDecisionCSVFileExportInput,
    ExplainableMPCDecisionCSVFileExportResult,
)


def test_input_and_result_are_frozen_slotted_and_preserve_exact_path_identity(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "decision_log.CSV"
    export_input = ExplainableMPCDecisionCSVFileExportInput(
        "header\n",
        output_path,
    )
    result = DeterministicExplainableMPCDecisionCSVFileExporter().export(export_input)

    assert [
        field.name for field in fields(ExplainableMPCDecisionCSVFileExportInput)
    ] == [
        "csv_content",
        "output_path",
    ]
    assert [
        field.name for field in fields(ExplainableMPCDecisionCSVFileExportResult)
    ] == [
        "source_input",
        "output_path",
        "bytes_written",
    ]
    assert result.source_input is export_input
    assert result.output_path is output_path
    assert result.bytes_written == len(b"header\n")
    assert not hasattr(export_input, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).bytes_written = 0


@pytest.mark.parametrize("path_name", ["decision.txt", "decision", "decision.json"])
def test_input_requires_path_type_csv_extension_and_existing_parent(
    tmp_path: Path,
    path_name: str,
) -> None:
    with pytest.raises(ValueError, match=r"\.csv"):
        ExplainableMPCDecisionCSVFileExportInput("header\n", tmp_path / path_name)
    with pytest.raises(TypeError, match=r"pathlib\.Path"):
        ExplainableMPCDecisionCSVFileExportInput("header\n", cast(Any, "file.csv"))
    with pytest.raises(TypeError, match="csv_content"):
        ExplainableMPCDecisionCSVFileExportInput(cast(Any, None), tmp_path / "x.csv")
    with pytest.raises(ValueError, match="parent"):
        ExplainableMPCDecisionCSVFileExportInput(
            "header\n", tmp_path / "missing" / "x.csv"
        )
    target_directory = tmp_path / "target.csv"
    target_directory.mkdir()
    with pytest.raises(ValueError, match="directory"):
        ExplainableMPCDecisionCSVFileExportInput("header\n", target_directory)


def test_exporter_preserves_exact_utf8_newlines_multiline_quotes_and_overwrites(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "decisions.csv"
    content = 'header,text\nfirst,"中文，含有\n换行和""引号"""\n'
    exporter = DeterministicExplainableMPCDecisionCSVFileExporter()

    first = exporter.export(
        ExplainableMPCDecisionCSVFileExportInput(content, output_path)
    )
    output_path.write_text("old content", encoding="utf-8", newline="")
    second = exporter.export(
        ExplainableMPCDecisionCSVFileExportInput(content, output_path)
    )

    assert output_path.read_text(encoding="utf-8") == content
    assert first.bytes_written == len(content.encode("utf-8"))
    assert second.bytes_written == first.bytes_written
    assert output_path.read_bytes() == content.encode("utf-8")


def test_header_only_content_writes_a_valid_nonempty_document(tmp_path: Path) -> None:
    output_path = tmp_path / "header_only.csv"
    content = "timestamp,strategy_name\n"

    DeterministicExplainableMPCDecisionCSVFileExporter().export(
        ExplainableMPCDecisionCSVFileExportInput(content, output_path)
    )

    assert output_path.read_text(encoding="utf-8") == content


def test_result_rejects_noncanonical_identity_and_byte_count(tmp_path: Path) -> None:
    output_path = tmp_path / "decision.csv"
    export_input = ExplainableMPCDecisionCSVFileExportInput("中文\n", output_path)

    with pytest.raises(ValueError, match="identity"):
        ExplainableMPCDecisionCSVFileExportResult(
            export_input,
            Path(output_path),
            len(export_input.csv_content.encode("utf-8")),
        )
    with pytest.raises(ValueError, match="byte length"):
        ExplainableMPCDecisionCSVFileExportResult(export_input, output_path, 3)
    with pytest.raises(TypeError, match="integer"):
        ExplainableMPCDecisionCSVFileExportResult(
            export_input, output_path, cast(Any, True)
        )


def test_file_export_boundary_is_abstract_stateless_and_isolated() -> None:
    signature = inspect.signature(ExplainableMPCDecisionCSVFileExporterBoundary.export)
    hints = get_type_hints(ExplainableMPCDecisionCSVFileExporterBoundary.export)
    module_path = Path(ems_strategy.__file__).parent / "mpc_decision_csv_file_export.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert issubclass(ExplainableMPCDecisionCSVFileExporterBoundary, ABC)
    assert inspect.isabstract(ExplainableMPCDecisionCSVFileExporterBoundary)
    assert ExplainableMPCDecisionCSVFileExporterBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "export_input"]
    assert hints["return"] is ExplainableMPCDecisionCSVFileExportResult
    with pytest.raises(TypeError):
        ExplainableMPCDecisionCSVFileExporterBoundary()  # type: ignore[abstract]
    assert not hasattr(DeterministicExplainableMPCDecisionCSVFileExporter(), "__dict__")
    for forbidden in (
        "mpc_decision_csv",
        "optimization",
        "kernel.event",
        "runtime",
        "device",
    ):
        assert forbidden not in imported_modules


def test_public_api_exports_file_export_contracts() -> None:
    for name in (
        "ExplainableMPCDecisionCSVFileExportInput",
        "ExplainableMPCDecisionCSVFileExportResult",
        "ExplainableMPCDecisionCSVFileExporterBoundary",
        "DeterministicExplainableMPCDecisionCSVFileExporter",
    ):
        assert name in ems_strategy.__all__
