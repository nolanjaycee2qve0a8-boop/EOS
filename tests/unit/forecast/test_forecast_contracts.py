"""Tests for immutable future-information contracts isolated from EMS context."""

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

import forecast
from ems_strategy import EMSContext
from forecast import ForecastHorizon, ForecastPoint


def make_point(
    *,
    hour: int = 1,
    price: float | None = 0.5,
) -> ForecastPoint:
    return ForecastPoint(
        datetime(2026, 1, 1, hour, tzinfo=UTC),
        pv_power_kw=2.0,
        load_power_kw=1.0,
        electricity_price_cny_per_kwh=price,
    )


def test_forecast_point_is_frozen_slotted_and_preserves_timestamp_identity() -> None:
    timestamp = datetime(2026, 1, 1, 1, tzinfo=UTC)
    point = ForecastPoint(timestamp, 2.0, 1.0, 0.5)

    assert [field.name for field in fields(ForecastPoint)] == [
        "timestamp",
        "pv_power_kw",
        "load_power_kw",
        "electricity_price_cny_per_kwh",
    ]
    assert point.timestamp is timestamp
    assert point.pv_power_kw == 2.0
    assert point.load_power_kw == 1.0
    assert point.electricity_price_cny_per_kwh == 0.5
    assert not hasattr(point, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, point).pv_power_kw = 3.0


def test_price_forecast_is_optional() -> None:
    point = make_point(price=None)

    assert point.electricity_price_cny_per_kwh is None


@pytest.mark.parametrize(
    ("kwargs", "exception"),
    [
        ({"pv_power_kw": -0.1}, ValueError),
        ({"load_power_kw": float("inf")}, ValueError),
        ({"electricity_price_cny_per_kwh": float("nan")}, ValueError),
        ({"pv_power_kw": cast(Any, True)}, TypeError),
    ],
)
def test_forecast_point_rejects_invalid_prediction_values(
    kwargs: dict[str, object],
    exception: type[Exception],
) -> None:
    values: dict[str, object] = {
        "timestamp": datetime(2026, 1, 1, 1, tzinfo=UTC),
        "pv_power_kw": 2.0,
        "load_power_kw": 1.0,
        "electricity_price_cny_per_kwh": 0.5,
    }
    values.update(kwargs)

    with pytest.raises(exception):
        ForecastPoint(**values)  # type: ignore[arg-type]


def test_horizon_preserves_exact_caller_tuple_and_point_order() -> None:
    first = make_point(hour=1)
    second = make_point(hour=2)
    points = (first, second)

    horizon = ForecastHorizon(points)

    assert [field.name for field in fields(ForecastHorizon)] == ["points"]
    assert horizon.points is points
    assert horizon.points[0] is first
    assert horizon.points[1] is second
    assert not hasattr(horizon, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, horizon).points = ()


def test_empty_horizon_is_a_valid_caller_supplied_collection() -> None:
    points: tuple[ForecastPoint, ...] = ()

    horizon = ForecastHorizon(points)

    assert horizon.points is points
    assert horizon.points == ()


def test_horizon_rejects_non_tuple_and_non_increasing_timestamps() -> None:
    first = make_point(hour=1)
    second = make_point(hour=2)

    with pytest.raises(TypeError, match="tuple"):
        ForecastHorizon(cast(Any, [first]))
    with pytest.raises(ValueError, match="increasing"):
        ForecastHorizon((second, first))
    with pytest.raises(ValueError, match="increasing"):
        ForecastHorizon(
            (
                first,
                ForecastPoint(
                    first.timestamp,
                    pv_power_kw=1.0,
                    load_power_kw=1.0,
                ),
            )
        )


def test_forecast_contract_has_no_ems_context_or_prediction_service_dependency() -> (
    None
):
    package_path = Path(forecast.__file__).parent
    for module_path in package_path.glob("*.py"):
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_modules = {
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        }
        assert all(
            module is None or not module.startswith("ems_strategy")
            for module in imported_modules
        )
        for forbidden_name in (
            "EMSContext",
            "Simulator",
            "Command",
            "Optimization",
            "MPC",
        ):
            assert forbidden_name not in source


def test_ems_context_has_no_future_forecast_field() -> None:
    assert "forecast" not in {field.name for field in fields(EMSContext)}
    assert tuple(field.name for field in fields(EMSContext)) == (
        "source_context",
        "objective_composition",
        "capability",
    )


def test_public_api_exports_forecast_contracts() -> None:
    assert forecast.__all__ == ["ForecastHorizon", "ForecastPoint"]
    assert forecast.ForecastPoint is ForecastPoint
    assert forecast.ForecastHorizon is ForecastHorizon
