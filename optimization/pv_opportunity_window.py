"""Select one rolling PV-surplus opportunity from caller-owned forecast facts.

This module selects ordered evidence only.  It does not calculate energy,
inspect battery facts, construct a new horizon, or alter existing headroom
formulas.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from forecast import ForecastHorizon, ForecastPoint


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be greater than or equal to 0")
    return value


def _require_non_negative_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized < 0:
        raise ValueError(f"{field_name} must be finite and non-negative")
    return normalized


@dataclass(frozen=True, slots=True)
class PVOpportunityWindowConfiguration:
    """Declare tolerated consecutive inactive forecast points within one window."""

    max_inactive_gap_points: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_inactive_gap_points",
            _require_non_negative_int(
                self.max_inactive_gap_points,
                "max_inactive_gap_points",
            ),
        )


@dataclass(frozen=True, slots=True)
class PVOpportunityWindowSelectionInput:
    """Retain exact caller-owned forecast and point-count gap configuration."""

    forecast_horizon: ForecastHorizon
    configuration: PVOpportunityWindowConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.configuration, PVOpportunityWindowConfiguration):
            raise TypeError("configuration must be a PVOpportunityWindowConfiguration")


@dataclass(frozen=True, slots=True)
class PVOpportunityWindowStep:
    """Preserve one selected source point and its net-PV surplus evidence."""

    forecast_point: ForecastPoint
    source_index: int
    pv_surplus_power_kw: float
    active: bool

    def __post_init__(self) -> None:
        if not isinstance(self.forecast_point, ForecastPoint):
            raise TypeError("forecast_point must be a ForecastPoint")
        object.__setattr__(
            self,
            "source_index",
            _require_non_negative_int(self.source_index, "source_index"),
        )
        object.__setattr__(
            self,
            "pv_surplus_power_kw",
            _require_non_negative_finite(
                self.pv_surplus_power_kw,
                "pv_surplus_power_kw",
            ),
        )
        if not isinstance(self.active, bool):
            raise TypeError("active must be a bool")
        expected_surplus = _pv_surplus_power_kw(self.forecast_point)
        if self.pv_surplus_power_kw != expected_surplus:
            raise ValueError("pv_surplus_power_kw must match forecast PV minus load")
        if self.active is not (expected_surplus > 0):
            raise ValueError("active must match positive PV-surplus semantics")


@dataclass(frozen=True, slots=True)
class PVOpportunityWindow:
    """Retain one confirmed next/current contiguous PV-surplus opportunity."""

    source_input: PVOpportunityWindowSelectionInput
    steps: tuple[PVOpportunityWindowStep, ...]
    start_index: int | None
    end_index_exclusive: int | None
    active_surplus_point_count: int
    inactive_gap_point_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, PVOpportunityWindowSelectionInput):
            raise TypeError("source_input must be a PVOpportunityWindowSelectionInput")
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        for step in self.steps:
            if not isinstance(step, PVOpportunityWindowStep):
                raise TypeError("steps must contain PVOpportunityWindowStep objects")
        self._validate_indexes_and_counts()
        self._validate_exact_selection()

    def _validate_indexes_and_counts(self) -> None:
        if isinstance(self.start_index, bool) or (
            self.start_index is not None and not isinstance(self.start_index, int)
        ):
            raise TypeError("start_index must be an int or None")
        if isinstance(self.end_index_exclusive, bool) or (
            self.end_index_exclusive is not None
            and not isinstance(self.end_index_exclusive, int)
        ):
            raise TypeError("end_index_exclusive must be an int or None")
        active_count = _require_non_negative_int(
            self.active_surplus_point_count,
            "active_surplus_point_count",
        )
        inactive_count = _require_non_negative_int(
            self.inactive_gap_point_count,
            "inactive_gap_point_count",
        )
        object.__setattr__(self, "active_surplus_point_count", active_count)
        object.__setattr__(self, "inactive_gap_point_count", inactive_count)

        if not self.steps:
            if (
                self.start_index is not None
                or self.end_index_exclusive is not None
                or active_count != 0
                or inactive_count != 0
            ):
                raise ValueError("an empty opportunity must use empty metadata")
            return

        if self.start_index is None or self.end_index_exclusive is None:
            raise ValueError("a non-empty opportunity requires start and end indexes")
        if self.start_index < 0 or self.end_index_exclusive <= self.start_index:
            raise ValueError("opportunity indexes must describe a positive interval")
        if self.end_index_exclusive > len(self.source_input.forecast_horizon.points):
            raise ValueError("opportunity indexes must be within the source horizon")
        if active_count != sum(step.active for step in self.steps):
            raise ValueError("active_surplus_point_count must match selected evidence")
        if inactive_count != sum(not step.active for step in self.steps):
            raise ValueError("inactive_gap_point_count must match selected evidence")

    def _validate_exact_selection(self) -> None:
        expected_indexes = _selected_indexes(self.source_input)
        actual_indexes = tuple(step.source_index for step in self.steps)
        if actual_indexes != expected_indexes:
            raise ValueError("steps must preserve the exact selected source indexes")
        if not expected_indexes:
            return
        horizon_points = self.source_input.forecast_horizon.points
        for step in self.steps:
            if step.forecast_point is not horizon_points[step.source_index]:
                raise ValueError("steps must preserve exact ForecastPoint identity")
        if self.start_index != expected_indexes[0]:
            raise ValueError("start_index must preserve the first selected index")
        if self.end_index_exclusive != expected_indexes[-1] + 1:
            raise ValueError("end_index_exclusive must follow the selected window")


class PVOpportunityWindowSelectionBoundary(ABC):
    """Define deterministic selection of one next/current PV opportunity."""

    __slots__ = ()

    @abstractmethod
    def select(
        self,
        selection_input: PVOpportunityWindowSelectionInput,
    ) -> PVOpportunityWindow:
        """Select one confirmed opportunity without energy or battery behavior."""
        raise NotImplementedError


class DeterministicPVOpportunityWindowSelector(PVOpportunityWindowSelectionBoundary):
    """Select the first confirmed active window in caller-defined forecast order."""

    __slots__ = ()

    def select(
        self,
        selection_input: PVOpportunityWindowSelectionInput,
    ) -> PVOpportunityWindow:
        if not isinstance(selection_input, PVOpportunityWindowSelectionInput):
            raise TypeError(
                "selection_input must be a PVOpportunityWindowSelectionInput"
            )
        indexes = _selected_indexes(selection_input)
        steps = tuple(
            _window_step(selection_input.forecast_horizon.points[index], index)
            for index in indexes
        )
        if not steps:
            return PVOpportunityWindow(selection_input, (), None, None, 0, 0)
        return PVOpportunityWindow(
            selection_input,
            steps,
            indexes[0],
            indexes[-1] + 1,
            sum(step.active for step in steps),
            sum(not step.active for step in steps),
        )


def _selected_indexes(
    selection_input: PVOpportunityWindowSelectionInput,
) -> tuple[int, ...]:
    """Select the first confirmed active window; discard unconfirmed tail gaps."""

    points = selection_input.forecast_horizon.points
    start_index = next(
        (
            index
            for index, point in enumerate(points)
            if _pv_surplus_power_kw(point) > 0
        ),
        None,
    )
    if start_index is None:
        return ()

    selected = [start_index]
    pending_inactive: list[int] = []
    tolerance = selection_input.configuration.max_inactive_gap_points
    for index in range(start_index + 1, len(points)):
        if _pv_surplus_power_kw(points[index]) > 0:
            selected.extend(pending_inactive)
            pending_inactive.clear()
            selected.append(index)
            continue
        pending_inactive.append(index)
        if len(pending_inactive) > tolerance:
            break
    return tuple(selected)


def _window_step(point: ForecastPoint, source_index: int) -> PVOpportunityWindowStep:
    surplus = _pv_surplus_power_kw(point)
    return PVOpportunityWindowStep(point, source_index, surplus, surplus > 0)


def _pv_surplus_power_kw(point: ForecastPoint) -> float:
    return max(point.pv_power_kw - point.load_power_kw, 0.0)
