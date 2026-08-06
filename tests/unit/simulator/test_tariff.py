"""Tests for Phase 6 tariff simulation contracts."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from simulator import (
    SimulationStepIdentity,
    TariffSimulationInput,
    TariffSimulationModelBoundary,
    TariffSimulationResult,
)
from simulator import tariff as tariff_module


class RecordingTariffModel(TariffSimulationModelBoundary):
    """Test-only model returning caller-configured price observations."""

    __slots__ = ("export_price", "import_price", "received")

    def __init__(self, import_price: float, export_price: float) -> None:
        self.import_price = import_price
        self.export_price = export_price
        self.received: TariffSimulationInput | None = None

    def simulate(
        self,
        simulation_input: TariffSimulationInput,
    ) -> TariffSimulationResult:
        self.received = simulation_input
        return TariffSimulationResult(
            simulation_input,
            self.import_price,
            self.export_price,
        )


def make_step() -> SimulationStepIdentity:
    return SimulationStepIdentity(
        sequence=0,
        duration_seconds=60.0,
        timestamp=datetime(2026, 8, 5, 12, 0, tzinfo=UTC),
    )


def test_tariff_input_preserves_exact_step_and_explicit_prices() -> None:
    step = make_step()

    simulation_input = TariffSimulationInput(step, 0.8, 0.3)

    assert simulation_input.step_identity is step
    assert simulation_input.import_price_cny_per_kwh == 0.8
    assert simulation_input.export_price_cny_per_kwh == 0.3


def test_tariff_input_accepts_signed_finite_prices() -> None:
    simulation_input = TariffSimulationInput(make_step(), -0.1, -0.2)

    assert simulation_input.import_price_cny_per_kwh == -0.1
    assert simulation_input.export_price_cny_per_kwh == -0.2


def test_tariff_input_requires_step_timestamp() -> None:
    step = SimulationStepIdentity(0, 60.0, None)

    with pytest.raises(ValueError, match="timestamp"):
        TariffSimulationInput(step, 0.8, 0.3)


def test_tariff_input_rejects_invalid_step_type() -> None:
    with pytest.raises(TypeError, match="step_identity"):
        TariffSimulationInput(cast(Any, object()), 0.8, 0.3)


@pytest.mark.parametrize("field_name", ["import_price", "export_price"])
@pytest.mark.parametrize("value", [True, "1", None, object()])
def test_tariff_input_rejects_invalid_price_type(
    field_name: str,
    value: object,
) -> None:
    values = {
        "import_price": (value, 0.3),
        "export_price": (0.8, value),
    }

    with pytest.raises(TypeError, match="price_cny_per_kwh"):
        TariffSimulationInput(make_step(), *cast(Any, values[field_name]))


@pytest.mark.parametrize("field_name", ["import_price", "export_price"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_tariff_input_rejects_non_finite_price(
    field_name: str,
    value: float,
) -> None:
    values = {
        "import_price": (value, 0.3),
        "export_price": (0.8, value),
    }

    with pytest.raises(ValueError, match="price_cny_per_kwh"):
        TariffSimulationInput(make_step(), *values[field_name])


def test_tariff_result_preserves_exact_input_identity() -> None:
    simulation_input = TariffSimulationInput(make_step(), 0.8, 0.3)

    result = TariffSimulationResult(simulation_input, 0.9, 0.4)

    assert result.simulation_input is simulation_input
    assert result.import_price_cny_per_kwh == 0.9
    assert result.export_price_cny_per_kwh == 0.4


@pytest.mark.parametrize("value", [True, "1", None, float("nan"), float("inf")])
def test_tariff_result_rejects_invalid_import_price(value: object) -> None:
    simulation_input = TariffSimulationInput(make_step(), 0.8, 0.3)
    exception_type = TypeError if not isinstance(value, float) else ValueError

    with pytest.raises(exception_type, match="import_price_cny_per_kwh"):
        TariffSimulationResult(simulation_input, cast(Any, value), 0.3)


def test_tariff_result_rejects_invalid_input() -> None:
    with pytest.raises(TypeError, match="simulation_input"):
        TariffSimulationResult(cast(Any, object()), 0.8, 0.3)


@pytest.mark.parametrize(
    ("model_type", "expected_slots", "expected_fields"),
    [
        (
            TariffSimulationInput,
            (
                "step_identity",
                "import_price_cny_per_kwh",
                "export_price_cny_per_kwh",
            ),
            [
                "step_identity",
                "import_price_cny_per_kwh",
                "export_price_cny_per_kwh",
            ],
        ),
        (
            TariffSimulationResult,
            (
                "simulation_input",
                "import_price_cny_per_kwh",
                "export_price_cny_per_kwh",
            ),
            [
                "simulation_input",
                "import_price_cny_per_kwh",
                "export_price_cny_per_kwh",
            ],
        ),
    ],
)
def test_tariff_artifacts_are_frozen_slotted_and_field_complete(
    model_type: type[object],
    expected_slots: tuple[str, ...],
    expected_fields: list[str],
) -> None:
    assert is_dataclass(model_type)
    assert cast(Any, model_type).__dataclass_params__.frozen
    assert cast(Any, model_type).__slots__ == expected_slots
    assert [field.name for field in fields(model_type)] == expected_fields


def test_tariff_artifacts_have_no_instance_dictionary() -> None:
    simulation_input = TariffSimulationInput(make_step(), 0.8, 0.3)
    result = TariffSimulationResult(simulation_input, 0.8, 0.3)

    assert not hasattr(simulation_input, "__dict__")
    assert not hasattr(result, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).import_price_cny_per_kwh = 1.0


def test_tariff_boundary_is_abstract_stateless_and_empty_slotted() -> None:
    assert inspect.isabstract(TariffSimulationModelBoundary)
    assert TariffSimulationModelBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, TariffSimulationModelBoundary)()


def test_test_only_tariff_model_receives_exact_input() -> None:
    simulation_input = TariffSimulationInput(make_step(), 0.8, 0.3)
    model = RecordingTariffModel(0.9, 0.4)

    result = model.simulate(simulation_input)

    assert model.received is simulation_input
    assert result.simulation_input is simulation_input


def test_tariff_boundary_signature_is_contract_only() -> None:
    signature = inspect.signature(TariffSimulationModelBoundary.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is TariffSimulationResult
    assert getattr(
        TariffSimulationModelBoundary.simulate,
        "__isabstractmethod__",
        False,
    )


def test_tariff_contract_has_no_strategy_runtime_or_external_state() -> None:
    simulation_input = TariffSimulationInput(make_step(), 0.8, 0.3)
    result = TariffSimulationResult(simulation_input, 0.8, 0.3)

    for artifact in (simulation_input, result):
        for forbidden in (
            "tou",
            "strategy",
            "forecast",
            "api",
            "runtime",
            "command",
            "device",
            "schedule",
            "cache",
            "history",
        ):
            assert not hasattr(artifact, forbidden)


def test_tariff_module_dependencies_are_core_and_standard_library_only() -> None:
    tree = ast.parse(inspect.getsource(tariff_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "simulator.core",
        "simulator.validation",
    }


def test_no_concrete_tariff_model_is_exported() -> None:
    concrete_models = [
        member
        for _, member in inspect.getmembers(tariff_module, inspect.isclass)
        if issubclass(member, TariffSimulationModelBoundary)
        and member is not TariffSimulationModelBoundary
    ]

    assert concrete_models == []
