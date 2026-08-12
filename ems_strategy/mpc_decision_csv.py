"""Deterministic in-memory CSV representation of MPC decision journal records."""

import csv
import io
from abc import ABC, abstractmethod
from dataclasses import dataclass

from ems_strategy.mpc_decision_journal import ExplainableMPCDecisionJournalRecord

EXPLAINABLE_MPC_DECISION_CSV_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "strategy_name",
    "strategy_version",
    "candidate_action",
    "candidate_requested_power_kw",
    "final_action",
    "final_requested_power_kw",
    "revision_applied",
    "revision_reasons",
    "candidate_soc_violation_kinds",
    "candidate_power_violation_kinds",
    "candidate_battery_horizon_feasible",
    "final_soc_feasible",
    "final_power_feasible",
    "final_battery_horizon_feasible",
    "candidate_starting_soc_fraction",
    "candidate_ending_soc_fraction",
    "final_starting_soc_fraction",
    "final_ending_soc_fraction",
    "min_soc_fraction",
    "max_soc_fraction",
    "max_charge_power_kw",
    "max_discharge_power_kw",
    "formatted_text",
)


@dataclass(frozen=True, slots=True)
class ExplainableMPCDecisionCSVRow:
    """Keep one CSV-schema row as primitive values only."""

    timestamp: str
    strategy_name: str
    strategy_version: str
    candidate_action: str
    candidate_requested_power_kw: float
    final_action: str
    final_requested_power_kw: float
    revision_applied: bool
    revision_reasons: str
    candidate_soc_violation_kinds: str
    candidate_power_violation_kinds: str
    candidate_battery_horizon_feasible: bool
    final_soc_feasible: bool
    final_power_feasible: bool
    final_battery_horizon_feasible: bool
    candidate_starting_soc_fraction: float
    candidate_ending_soc_fraction: float
    final_starting_soc_fraction: float
    final_ending_soc_fraction: float
    min_soc_fraction: float
    max_soc_fraction: float
    max_charge_power_kw: float
    max_discharge_power_kw: float
    formatted_text: str


@dataclass(frozen=True, slots=True)
class ExplainableMPCDecisionCSVRowMappingInput:
    """Retain one exact journal record for read-only CSV mapping."""

    record: ExplainableMPCDecisionJournalRecord

    def __post_init__(self) -> None:
        if not isinstance(self.record, ExplainableMPCDecisionJournalRecord):
            raise TypeError("record must be an ExplainableMPCDecisionJournalRecord")


class ExplainableMPCDecisionCSVRowMappingBoundary(ABC):
    """Define stateless mapping of one existing journal record to a CSV row."""

    __slots__ = ()

    @abstractmethod
    def map(
        self,
        mapping_input: ExplainableMPCDecisionCSVRowMappingInput,
    ) -> ExplainableMPCDecisionCSVRow:
        """Map supplied record values only; do not re-evaluate them."""
        raise NotImplementedError


class DeterministicExplainableMPCDecisionCSVRowMapper(
    ExplainableMPCDecisionCSVRowMappingBoundary
):
    """Map one supplied record into the explicit stable CSV schema."""

    __slots__ = ()

    def map(
        self,
        mapping_input: ExplainableMPCDecisionCSVRowMappingInput,
    ) -> ExplainableMPCDecisionCSVRow:
        if not isinstance(mapping_input, ExplainableMPCDecisionCSVRowMappingInput):
            raise TypeError(
                "mapping_input must be an ExplainableMPCDecisionCSVRowMappingInput"
            )
        record = mapping_input.record
        return ExplainableMPCDecisionCSVRow(
            record.timestamp.isoformat(),
            record.strategy.name,
            record.strategy.version,
            record.candidate_action.action,
            record.candidate_requested_power_kw,
            record.final_action.action,
            record.final_requested_power_kw,
            record.revision_applied,
            "|".join(record.revision_reasons),
            "|".join(record.candidate_soc_violation_kinds),
            "|".join(record.candidate_power_violation_kinds),
            record.candidate_battery_horizon_feasible,
            record.final_soc_feasible,
            record.final_power_feasible,
            record.final_battery_horizon_feasible,
            record.candidate_starting_soc_fraction,
            record.candidate_ending_soc_fraction,
            record.final_starting_soc_fraction,
            record.final_ending_soc_fraction,
            record.min_soc_fraction,
            record.max_soc_fraction,
            record.max_charge_power_kw,
            record.max_discharge_power_kw,
            record.formatted_text,
        )


class ExplainableMPCDecisionCSVSerializerBoundary(ABC):
    """Define stateless in-memory serialization of caller-ordered CSV rows."""

    __slots__ = ()

    @abstractmethod
    def serialize(self, rows: tuple[ExplainableMPCDecisionCSVRow, ...]) -> str:
        """Return header-inclusive CSV text without filesystem effects."""
        raise NotImplementedError


class DeterministicExplainableMPCDecisionCSVSerializer(
    ExplainableMPCDecisionCSVSerializerBoundary
):
    """Serialize rows in exact caller order with stdlib CSV escaping."""

    __slots__ = ()

    def serialize(self, rows: tuple[ExplainableMPCDecisionCSVRow, ...]) -> str:
        if not isinstance(rows, tuple):
            raise TypeError("rows must be a tuple")
        if any(not isinstance(row, ExplainableMPCDecisionCSVRow) for row in rows):
            raise TypeError("rows must contain ExplainableMPCDecisionCSVRow objects")
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(EXPLAINABLE_MPC_DECISION_CSV_COLUMNS)
        for row in rows:
            writer.writerow(
                tuple(
                    "true" if value is True else "false" if value is False else value
                    for value in (
                        row.timestamp,
                        row.strategy_name,
                        row.strategy_version,
                        row.candidate_action,
                        row.candidate_requested_power_kw,
                        row.final_action,
                        row.final_requested_power_kw,
                        row.revision_applied,
                        row.revision_reasons,
                        row.candidate_soc_violation_kinds,
                        row.candidate_power_violation_kinds,
                        row.candidate_battery_horizon_feasible,
                        row.final_soc_feasible,
                        row.final_power_feasible,
                        row.final_battery_horizon_feasible,
                        row.candidate_starting_soc_fraction,
                        row.candidate_ending_soc_fraction,
                        row.final_starting_soc_fraction,
                        row.final_ending_soc_fraction,
                        row.min_soc_fraction,
                        row.max_soc_fraction,
                        row.max_charge_power_kw,
                        row.max_discharge_power_kw,
                        row.formatted_text,
                    )
                )
            )
        return output.getvalue()
