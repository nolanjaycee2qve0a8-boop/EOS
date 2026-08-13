"""Filesystem persistence boundary for already serialized explainable MPC CSV."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ExplainableMPCDecisionCSVFileExportInput:
    """Retain exact complete CSV text and a caller-owned CSV target path."""

    csv_content: str
    output_path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.csv_content, str):
            raise TypeError("csv_content must be a str")
        if not isinstance(self.output_path, Path):
            raise TypeError("output_path must be a pathlib.Path")
        if self.output_path.suffix.lower() != ".csv":
            raise ValueError("output_path must have a .csv extension")
        if not self.output_path.parent.is_dir():
            raise ValueError("output_path parent directory must already exist")
        if self.output_path.exists() and self.output_path.is_dir():
            raise ValueError("output_path must not be a directory")


@dataclass(frozen=True, slots=True)
class ExplainableMPCDecisionCSVFileExportResult:
    """Preserve one exact completed file-export request and its byte count."""

    source_input: ExplainableMPCDecisionCSVFileExportInput
    output_path: Path
    bytes_written: int

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, ExplainableMPCDecisionCSVFileExportInput):
            raise TypeError(
                "source_input must be an ExplainableMPCDecisionCSVFileExportInput"
            )
        if self.output_path is not self.source_input.output_path:
            raise ValueError("output_path must preserve exact source input identity")
        if isinstance(self.bytes_written, bool) or not isinstance(
            self.bytes_written, int
        ):
            raise TypeError("bytes_written must be an integer")
        if self.bytes_written < 0:
            raise ValueError("bytes_written must be greater than or equal to 0")
        if self.bytes_written != len(self.source_input.csv_content.encode("utf-8")):
            raise ValueError("bytes_written must equal exact UTF-8 content byte length")


class ExplainableMPCDecisionCSVFileExporterBoundary(ABC):
    """Define stateless persistence of exact pre-serialized CSV text."""

    __slots__ = ()

    @abstractmethod
    def export(
        self,
        export_input: ExplainableMPCDecisionCSVFileExportInput,
    ) -> ExplainableMPCDecisionCSVFileExportResult:
        """Write one complete CSV document without mapping or serialization."""
        raise NotImplementedError


class DeterministicExplainableMPCDecisionCSVFileExporter(
    ExplainableMPCDecisionCSVFileExporterBoundary
):
    """Overwrite one caller-supplied regular CSV file with exact UTF-8 content."""

    __slots__ = ()

    def export(
        self,
        export_input: ExplainableMPCDecisionCSVFileExportInput,
    ) -> ExplainableMPCDecisionCSVFileExportResult:
        if not isinstance(export_input, ExplainableMPCDecisionCSVFileExportInput):
            raise TypeError(
                "export_input must be an ExplainableMPCDecisionCSVFileExportInput"
            )
        export_input.output_path.write_text(
            export_input.csv_content,
            encoding="utf-8",
            newline="",
        )
        return ExplainableMPCDecisionCSVFileExportResult(
            export_input,
            export_input.output_path,
            len(export_input.csv_content.encode("utf-8")),
        )
