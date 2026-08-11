"""MPC strategy extension contracts without an optimization implementation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite

from ems_strategy.context import EMSContext
from ems_strategy.decision import EMSDecision
from forecast import ForecastHorizon


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be greater than 0")
    return value


def _require_positive_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("control_step_duration_seconds must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(
            "control_step_duration_seconds must be finite and greater than 0"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class MPCConfiguration:
    """Describe caller-supplied planning shape without an objective algorithm.

    ``forecast_horizon_points`` is the required count of future points and
    ``control_step_duration_seconds`` is an explicit, positive raw-second
    planning parameter. This configuration neither computes controls nor owns
    objective weights, state prediction, history, or a solver.
    """

    forecast_horizon_points: int
    control_step_duration_seconds: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "forecast_horizon_points",
            _require_positive_int(
                self.forecast_horizon_points,
                "forecast_horizon_points",
            ),
        )
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_seconds(self.control_step_duration_seconds),
        )


@dataclass(frozen=True, slots=True)
class MPCStrategyInput:
    """Preserve exact current facts, future facts, and planning configuration.

    The input is only an immutable provenance carrier. It retains the exact
    caller-supplied references and does not merge forecast facts into
    ``EMSContext`` or reconstruct any artifact.
    """

    context: EMSContext
    forecast_horizon: ForecastHorizon
    configuration: MPCConfiguration

    def __post_init__(self) -> None:
        if not isinstance(self.context, EMSContext):
            raise TypeError("context must be an EMSContext")
        if not isinstance(self.forecast_horizon, ForecastHorizon):
            raise TypeError("forecast_horizon must be a ForecastHorizon")
        if not isinstance(self.configuration, MPCConfiguration):
            raise TypeError("configuration must be an MPCConfiguration")
        if (
            len(self.forecast_horizon.points)
            != self.configuration.forecast_horizon_points
        ):
            raise ValueError(
                "forecast_horizon point count must equal forecast_horizon_points"
            )


class MPCStrategyBoundary(ABC):
    """Define an MPC extension seam from explicit planning input to EMSDecision.

    This boundary keeps the existing Strategy output and provenance contracts:
    implementations return an ``EMSDecision`` whose ``source_context`` is the
    exact ``MPCStrategyInput.context``. It intentionally defines no solver,
    objective weighting, feasibility evaluation, actuation, or simulation.
    """

    __slots__ = ()

    @abstractmethod
    def evaluate(self, strategy_input: MPCStrategyInput) -> EMSDecision:
        """Return one decision preserving the input context identity."""
        raise NotImplementedError
