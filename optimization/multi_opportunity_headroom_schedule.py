"""Pure multi-opportunity PV headroom planning evidence.

This module deliberately separates three questions: which PV-surplus
opportunities are visible, how much room one opportunity needs (TASK-132),
and how much room should exist before each opportunity after expected
inter-opportunity *potential* depletion.  It does not decide, reserve,
optimize, or execute battery power.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from forecast import ForecastHorizon, ForecastPoint
from optimization.battery_planning import BatteryOptimizationModel
from optimization.pv_headroom import (
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
)
from optimization.pv_opportunity_window import (
    PVOpportunityWindowConfiguration,
    PVOpportunityWindowStep,
)


def _require_positive_finite_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("control_step_duration_seconds must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(
            "control_step_duration_seconds must be finite and greater than 0"
        )
    return normalized


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _pv_surplus_power_kw(point: ForecastPoint) -> float:
    return max(point.pv_power_kw - point.load_power_kw, 0.0)


@dataclass(frozen=True, slots=True)
class PVOpportunitySequenceInput:
    """Compose exact caller-owned forecast facts and segmentation configuration."""

    forecast_horizon: ForecastHorizon
    opportunity_configuration: PVOpportunityWindowConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(
            self.opportunity_configuration,
            PVOpportunityWindowConfiguration,
        ):
            raise TypeError(
                "opportunity_configuration must be a PVOpportunityWindowConfiguration"
            )


@dataclass(frozen=True, slots=True)
class PVOpportunitySequenceEntry:
    """Preserve one distinct, confirmed PV-surplus opportunity and its points."""

    source_index_start: int
    source_index_end: int
    steps: tuple[PVOpportunityWindowStep, ...]
    selected_forecast_horizon: ForecastHorizon
    opportunity_start_timestamp: datetime
    opportunity_end_timestamp: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_index_start",
            _require_non_negative_int(self.source_index_start, "source_index_start"),
        )
        object.__setattr__(
            self,
            "source_index_end",
            _require_non_negative_int(self.source_index_end, "source_index_end"),
        )
        if self.source_index_end < self.source_index_start:
            raise ValueError("source_index_end must not precede source_index_start")
        if not isinstance(self.steps, tuple) or not self.steps:
            raise ValueError("steps must be a non-empty tuple")
        if not isinstance(self.selected_forecast_horizon, ForecastHorizon):
            raise TypeError("selected_forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.opportunity_start_timestamp, datetime):
            raise TypeError("opportunity_start_timestamp must be a datetime")
        if not isinstance(self.opportunity_end_timestamp, datetime):
            raise TypeError("opportunity_end_timestamp must be a datetime")
        if self.opportunity_end_timestamp < self.opportunity_start_timestamp:
            raise ValueError("opportunity_end_timestamp must not precede start")
        if len(self.steps) != len(self.selected_forecast_horizon.points):
            raise ValueError("selected_forecast_horizon must preserve every step")
        expected_indexes = tuple(
            range(self.source_index_start, self.source_index_end + 1)
        )
        if tuple(step.source_index for step in self.steps) != expected_indexes:
            raise ValueError("steps must preserve a contiguous source-index interval")
        for step, point in zip(
            self.steps, self.selected_forecast_horizon.points, strict=True
        ):
            if not isinstance(step, PVOpportunityWindowStep):
                raise TypeError("steps must contain PVOpportunityWindowStep objects")
            if point is not step.forecast_point:
                raise ValueError(
                    "selected horizon must preserve exact ForecastPoint identity"
                )
        if self.opportunity_start_timestamp != self.steps[0].forecast_point.timestamp:
            raise ValueError("opportunity_start_timestamp must match the first point")
        if self.opportunity_end_timestamp != self.steps[-1].forecast_point.timestamp:
            raise ValueError("opportunity_end_timestamp must match the last point")
        if not any(step.active for step in self.steps):
            raise ValueError("an opportunity must contain an active PV-surplus point")


@dataclass(frozen=True, slots=True)
class PVOpportunitySequence:
    """Retain every distinct opportunity visible in one caller-owned horizon."""

    source_input: PVOpportunitySequenceInput
    entries: tuple[PVOpportunitySequenceEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, PVOpportunitySequenceInput):
            raise TypeError("source_input must be a PVOpportunitySequenceInput")
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")
        expected_ranges = _opportunity_ranges(self.source_input)
        if len(self.entries) != len(expected_ranges):
            raise ValueError("entries must preserve every distinct opportunity")
        points = self.source_input.forecast_horizon.points
        for entry, expected_range in zip(self.entries, expected_ranges, strict=True):
            if not isinstance(entry, PVOpportunitySequenceEntry):
                raise TypeError(
                    "entries must contain PVOpportunitySequenceEntry objects"
                )
            start, end = expected_range
            if (entry.source_index_start, entry.source_index_end) != (start, end):
                raise ValueError("entries must preserve exact segmented indexes")
            for step in entry.steps:
                if step.forecast_point is not points[step.source_index]:
                    raise ValueError(
                        "entries must preserve exact ForecastPoint identity"
                    )


class PVOpportunitySequenceBoundary(ABC):
    """Define stateless all-opportunity segmentation without energy accounting."""

    __slots__ = ()

    @abstractmethod
    def decompose(
        self, sequence_input: PVOpportunitySequenceInput
    ) -> PVOpportunitySequence:
        """Return all distinct confirmed opportunities in caller order."""
        raise NotImplementedError


class DeterministicPVOpportunitySequenceCalculator(PVOpportunitySequenceBoundary):
    """Segment every confirmed opportunity using TASK-140-compatible gap semantics."""

    __slots__ = ()

    def decompose(
        self, sequence_input: PVOpportunitySequenceInput
    ) -> PVOpportunitySequence:
        if not isinstance(sequence_input, PVOpportunitySequenceInput):
            raise TypeError("sequence_input must be a PVOpportunitySequenceInput")
        points = sequence_input.forecast_horizon.points
        entries = tuple(
            self._entry(points, start, end)
            for start, end in _opportunity_ranges(sequence_input)
        )
        return PVOpportunitySequence(sequence_input, entries)

    @staticmethod
    def _entry(
        points: tuple[ForecastPoint, ...],
        start: int,
        end: int,
    ) -> PVOpportunitySequenceEntry:
        steps = tuple(
            PVOpportunityWindowStep(
                points[index],
                index,
                _pv_surplus_power_kw(points[index]),
                _pv_surplus_power_kw(points[index]) > 0,
            )
            for index in range(start, end + 1)
        )
        selected_horizon = ForecastHorizon(tuple(step.forecast_point for step in steps))
        return PVOpportunitySequenceEntry(
            start,
            end,
            steps,
            selected_horizon,
            steps[0].forecast_point.timestamp,
            steps[-1].forecast_point.timestamp,
        )


def _opportunity_ranges(
    sequence_input: PVOpportunitySequenceInput,
) -> tuple[tuple[int, int], ...]:
    """Return confirmed active ranges, retaining only confirmed short cloud gaps."""

    tolerance = sequence_input.opportunity_configuration.max_inactive_gap_points
    ranges: list[tuple[int, int]] = []
    current_start: int | None = None
    current_end: int | None = None
    pending_inactive: list[int] = []
    for index, point in enumerate(sequence_input.forecast_horizon.points):
        if _pv_surplus_power_kw(point) > 0:
            if current_start is None:
                current_start = index
            elif len(pending_inactive) > tolerance:
                assert current_end is not None
                ranges.append((current_start, current_end))
                current_start = index
            current_end = index
            pending_inactive.clear()
        elif current_start is not None:
            pending_inactive.append(index)
    if current_start is not None:
        assert current_end is not None
        ranges.append((current_start, current_end))
    return tuple(ranges)


@dataclass(frozen=True, slots=True)
class MultiOpportunityHeadroomScheduleInput:
    """Compose exact future facts needed for pure multi-opportunity planning."""

    forecast_horizon: ForecastHorizon
    battery_model: BatteryOptimizationModel
    control_step_duration_seconds: float
    opportunity_configuration: PVOpportunityWindowConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.battery_model, BatteryOptimizationModel):
            raise TypeError("battery_model must be a BatteryOptimizationModel")
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_finite_seconds(self.control_step_duration_seconds),
        )
        if not isinstance(
            self.opportunity_configuration,
            PVOpportunityWindowConfiguration,
        ):
            raise TypeError(
                "opportunity_configuration must be a PVOpportunityWindowConfiguration"
            )


@dataclass(frozen=True, slots=True)
class MultiOpportunityHeadroomScheduleEntry:
    """Read-only evidence and schedule target for one distinct PV opportunity.

    ``gap_net_deficit_load_energy_kwh`` is load-side energy.  The associated
    battery-stored depletion potential is that energy divided by discharge
    efficiency: it is the potential decrease in stored battery energy if the
    deficit were served by the battery, not an executed discharge decision.
    """

    opportunity: PVOpportunitySequenceEntry
    headroom_requirement: PVHeadroomRequirement
    gap_start_source_index: int | None
    gap_end_source_index: int | None
    gap_net_deficit_load_energy_kwh: float
    battery_stored_energy_depletion_potential_kwh: float
    required_pre_opportunity_headroom_kwh: float
    recommended_pre_opportunity_max_soc_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity, PVOpportunitySequenceEntry):
            raise TypeError("opportunity must be a PVOpportunitySequenceEntry")
        if not isinstance(self.headroom_requirement, PVHeadroomRequirement):
            raise TypeError("headroom_requirement must be a PVHeadroomRequirement")
        for field_name in (
            "gap_net_deficit_load_energy_kwh",
            "battery_stored_energy_depletion_potential_kwh",
            "required_pre_opportunity_headroom_kwh",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_non_negative_finite(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "recommended_pre_opportunity_max_soc_fraction",
            _require_non_negative_finite(
                self.recommended_pre_opportunity_max_soc_fraction,
                "recommended_pre_opportunity_max_soc_fraction",
            ),
        )
        if (self.gap_start_source_index is None) is not (
            self.gap_end_source_index is None
        ):
            raise ValueError("gap indexes must both be set or both be None")
        if self.gap_start_source_index is not None:
            gap_start = _require_non_negative_int(
                self.gap_start_source_index,
                "gap_start_source_index",
            )
            gap_end = _require_non_negative_int(
                self.gap_end_source_index,
                "gap_end_source_index",
            )
            object.__setattr__(
                self,
                "gap_start_source_index",
                gap_start,
            )
            object.__setattr__(
                self,
                "gap_end_source_index",
                gap_end,
            )
            if gap_end < gap_start:
                raise ValueError("gap_end_source_index must not precede gap start")


@dataclass(frozen=True, slots=True)
class MultiOpportunityHeadroomSchedule:
    """Retain complete opportunity, per-opportunity, gap, and target evidence."""

    source_input: MultiOpportunityHeadroomScheduleInput
    opportunity_sequence: PVOpportunitySequence
    entries: tuple[MultiOpportunityHeadroomScheduleEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, MultiOpportunityHeadroomScheduleInput):
            raise TypeError(
                "source_input must be a MultiOpportunityHeadroomScheduleInput"
            )
        if not isinstance(self.opportunity_sequence, PVOpportunitySequence):
            raise TypeError("opportunity_sequence must be a PVOpportunitySequence")
        if not isinstance(self.entries, tuple):
            raise TypeError("entries must be a tuple")
        sequence_input = self.opportunity_sequence.source_input
        if sequence_input.forecast_horizon is not self.source_input.forecast_horizon:
            raise ValueError("sequence must preserve exact source forecast identity")
        if (
            sequence_input.opportunity_configuration
            is not self.source_input.opportunity_configuration
        ):
            raise ValueError("sequence must preserve exact opportunity configuration")
        if len(self.entries) != len(self.opportunity_sequence.entries):
            raise ValueError("entries must preserve every opportunity")
        self._validate_entries()

    def _validate_entries(self) -> None:
        model = self.source_input.battery_model
        usable_range = model.usable_capacity_kwh * (
            model.max_soc_fraction - model.min_soc_fraction
        )
        next_required = 0.0
        entries = self.entries
        for reverse_index in range(len(entries) - 1, -1, -1):
            entry = entries[reverse_index]
            if not isinstance(entry, MultiOpportunityHeadroomScheduleEntry):
                raise TypeError(
                    "entries must contain MultiOpportunityHeadroomScheduleEntry"
                )
            sequence_entry = self.opportunity_sequence.entries[reverse_index]
            if entry.opportunity is not sequence_entry:
                raise ValueError("entries must preserve exact opportunity identity")
            requirement_input = entry.headroom_requirement.source_input
            if (
                requirement_input.forecast_horizon
                is not sequence_entry.selected_forecast_horizon
            ):
                raise ValueError("headroom requirement must use exact selected horizon")
            if requirement_input.battery_model is not model:
                raise ValueError(
                    "headroom requirement must preserve exact battery model"
                )
            if (
                requirement_input.control_step_duration_seconds
                != self.source_input.control_step_duration_seconds
            ):
                raise ValueError("headroom requirement must preserve exact duration")
            if reverse_index == len(entries) - 1:
                if (
                    entry.gap_start_source_index is not None
                    or entry.gap_end_source_index is not None
                ):
                    raise ValueError("last opportunity must not have a future gap")
                if (
                    entry.gap_net_deficit_load_energy_kwh != 0.0
                    or entry.battery_stored_energy_depletion_potential_kwh != 0.0
                ):
                    raise ValueError("last opportunity must have zero future depletion")
            else:
                next_opportunity = self.opportunity_sequence.entries[reverse_index + 1]
                expected_start = sequence_entry.source_index_end + 1
                expected_end = next_opportunity.source_index_start - 1
                if (
                    entry.gap_start_source_index,
                    entry.gap_end_source_index,
                ) != (expected_start, expected_end):
                    raise ValueError("gap indexes must preserve source interval")
                expected_load, expected_stored = _gap_depletion(
                    self.source_input,
                    expected_start,
                    expected_end,
                )
                if (
                    entry.gap_net_deficit_load_energy_kwh,
                    entry.battery_stored_energy_depletion_potential_kwh,
                ) != (expected_load, expected_stored):
                    raise ValueError(
                        "gap depletion evidence must preserve exact formula"
                    )
            expected_required = min(
                usable_range,
                entry.headroom_requirement.required_headroom_energy_kwh
                + max(
                    next_required - entry.battery_stored_energy_depletion_potential_kwh,
                    0.0,
                ),
            )
            expected_target = max(
                model.min_soc_fraction,
                min(
                    model.max_soc_fraction,
                    model.max_soc_fraction
                    - expected_required / model.usable_capacity_kwh,
                ),
            )
            if entry.required_pre_opportunity_headroom_kwh != expected_required:
                raise ValueError("schedule headroom must preserve backward recurrence")
            if entry.recommended_pre_opportunity_max_soc_fraction != expected_target:
                raise ValueError("schedule target must preserve bounded headroom")
            next_required = expected_required


class MultiOpportunityHeadroomScheduleBoundary(ABC):
    """Define stateless evidence-only multi-opportunity headroom planning."""

    __slots__ = ()

    @abstractmethod
    def calculate(
        self,
        schedule_input: MultiOpportunityHeadroomScheduleInput,
    ) -> MultiOpportunityHeadroomSchedule:
        """Produce a schedule without deciding, reserving, or executing power."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class DeterministicMultiOpportunityHeadroomScheduleCalculator(
    MultiOpportunityHeadroomScheduleBoundary
):
    """Compose segmentation and unchanged TASK-132 evidence exactly once each."""

    opportunity_sequence_calculator: PVOpportunitySequenceBoundary
    headroom_calculator: PVHeadroomRequirementBoundary

    def __post_init__(self) -> None:
        if not isinstance(
            self.opportunity_sequence_calculator,
            PVOpportunitySequenceBoundary,
        ):
            raise TypeError(
                "opportunity_sequence_calculator must be a "
                "PVOpportunitySequenceBoundary"
            )
        if not isinstance(self.headroom_calculator, PVHeadroomRequirementBoundary):
            raise TypeError(
                "headroom_calculator must be a PVHeadroomRequirementBoundary"
            )

    def calculate(
        self,
        schedule_input: MultiOpportunityHeadroomScheduleInput,
    ) -> MultiOpportunityHeadroomSchedule:
        if not isinstance(schedule_input, MultiOpportunityHeadroomScheduleInput):
            raise TypeError(
                "schedule_input must be a MultiOpportunityHeadroomScheduleInput"
            )
        sequence = self.opportunity_sequence_calculator.decompose(
            PVOpportunitySequenceInput(
                schedule_input.forecast_horizon,
                schedule_input.opportunity_configuration,
            )
        )
        requirements = tuple(
            self.headroom_calculator.calculate(
                PVHeadroomRequirementInput(
                    opportunity.selected_forecast_horizon,
                    schedule_input.battery_model,
                    schedule_input.control_step_duration_seconds,
                )
            )
            for opportunity in sequence.entries
        )
        entries = self._entries(schedule_input, sequence, requirements)
        return MultiOpportunityHeadroomSchedule(schedule_input, sequence, entries)

    @staticmethod
    def _entries(
        schedule_input: MultiOpportunityHeadroomScheduleInput,
        sequence: PVOpportunitySequence,
        requirements: tuple[PVHeadroomRequirement, ...],
    ) -> tuple[MultiOpportunityHeadroomScheduleEntry, ...]:
        model = schedule_input.battery_model
        usable_range = model.usable_capacity_kwh * (
            model.max_soc_fraction - model.min_soc_fraction
        )
        planned: list[MultiOpportunityHeadroomScheduleEntry] = []
        next_required = 0.0
        for index in range(len(sequence.entries) - 1, -1, -1):
            opportunity = sequence.entries[index]
            requirement = requirements[index]
            if index == len(sequence.entries) - 1:
                gap_start = None
                gap_end = None
                gap_load = 0.0
                depletion = 0.0
            else:
                next_opportunity = sequence.entries[index + 1]
                gap_start = opportunity.source_index_end + 1
                gap_end = next_opportunity.source_index_start - 1
                gap_load, depletion = _gap_depletion(
                    schedule_input,
                    gap_start,
                    gap_end,
                )
            required = min(
                usable_range,
                requirement.required_headroom_energy_kwh
                + max(next_required - depletion, 0.0),
            )
            target = max(
                model.min_soc_fraction,
                min(
                    model.max_soc_fraction,
                    model.max_soc_fraction - required / model.usable_capacity_kwh,
                ),
            )
            planned.append(
                MultiOpportunityHeadroomScheduleEntry(
                    opportunity,
                    requirement,
                    gap_start,
                    gap_end,
                    gap_load,
                    depletion,
                    required,
                    target,
                )
            )
            next_required = required
        return tuple(reversed(planned))


def _gap_depletion(
    schedule_input: MultiOpportunityHeadroomScheduleInput,
    start_index: int,
    end_index: int,
) -> tuple[float, float]:
    """Return load-side deficit energy and battery-stored depletion potential.

    A load-side deficit of ``E`` kWh would require a battery stored-energy
    decrease of ``E / discharge_efficiency`` kWh to serve it.  This is only
    natural headroom recreation potential; it never commands a discharge.
    """

    duration_hours = schedule_input.control_step_duration_seconds / 3600.0
    gap_load = sum(
        max(point.load_power_kw - point.pv_power_kw, 0.0) * duration_hours
        for point in schedule_input.forecast_horizon.points[start_index : end_index + 1]
    )
    gap_load = _require_non_negative_finite(
        gap_load,
        "gap_net_deficit_load_energy_kwh",
    )
    stored = _require_non_negative_finite(
        gap_load / schedule_input.battery_model.discharge_efficiency,
        "battery_stored_energy_depletion_potential_kwh",
    )
    return gap_load, stored
