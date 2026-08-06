"""Tests for the Phase 6 battery simulation model contracts."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from typing import Any, cast

import pytest

from kernel.decision import DecisionIntent, FeasibleDecisionIntent
from simulator import (
    BatterySimulationActuation,
    BatterySimulationInput,
    BatterySimulationModelBoundary,
    BatterySimulationResult,
    BatterySimulationState,
    SimulationStepIdentity,
)
from simulator import battery as battery_module


class RecordingBatteryModel(BatterySimulationModelBoundary):
    """Test-only model returning caller-configured immutable observations."""

    __slots__ = ("actual_power_kw", "next_state", "received")

    def __init__(
        self,
        next_state: BatterySimulationState,
        actual_power_kw: float,
    ) -> None:
        self.next_state = next_state
        self.actual_power_kw = actual_power_kw
        self.received: BatterySimulationInput | None = None

    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        self.received = simulation_input
        return BatterySimulationResult(
            simulation_input,
            self.next_state,
            self.actual_power_kw,
        )


def make_actuation(power_kw: float = 1.0) -> BatterySimulationActuation:
    feasible_decision = FeasibleDecisionIntent(DecisionIntent(power_kw))
    return BatterySimulationActuation(feasible_decision, power_kw)


def make_input() -> BatterySimulationInput:
    return BatterySimulationInput(
        SimulationStepIdentity(0, 60.0, None),
        BatterySimulationState(0.5),
        make_actuation(),
    )


@pytest.mark.parametrize("soc", [0.0, 0.5, 1.0])
def test_battery_state_accepts_raw_fraction_boundaries(soc: float) -> None:
    state = BatterySimulationState(soc)

    assert state.soc == soc


@pytest.mark.parametrize("value", [True, "0.5", None, object()])
def test_battery_state_rejects_invalid_soc_type(value: object) -> None:
    with pytest.raises(TypeError, match="soc"):
        BatterySimulationState(cast(Any, value))


@pytest.mark.parametrize(
    "value",
    [-0.01, 1.01, float("nan"), float("inf"), float("-inf")],
)
def test_battery_state_rejects_invalid_soc_value(value: float) -> None:
    with pytest.raises(ValueError, match="soc"):
        BatterySimulationState(value)


def test_battery_input_preserves_exact_component_identities() -> None:
    step = SimulationStepIdentity(2, 300.0, None)
    source_state = BatterySimulationState(0.4)
    actuation = make_actuation(-2.0)

    simulation_input = BatterySimulationInput(step, source_state, actuation)

    assert simulation_input.step_identity is step
    assert simulation_input.source_state is source_state
    assert simulation_input.actuation is actuation


@pytest.mark.parametrize(
    ("field_name", "values"),
    [
        ("step_identity", (object(), BatterySimulationState(0.5), make_actuation())),
        (
            "source_state",
            (SimulationStepIdentity(0, 1.0, None), object(), make_actuation()),
        ),
        (
            "actuation",
            (
                SimulationStepIdentity(0, 1.0, None),
                BatterySimulationState(0.5),
                object(),
            ),
        ),
    ],
)
def test_battery_input_rejects_invalid_component_type(
    field_name: str,
    values: tuple[object, object, object],
) -> None:
    with pytest.raises(TypeError, match=field_name):
        BatterySimulationInput(*cast(Any, values))


def test_battery_result_preserves_exact_input_and_next_state_identities() -> None:
    simulation_input = make_input()
    next_state = BatterySimulationState(0.6)

    result = BatterySimulationResult(simulation_input, next_state, 1.0)

    assert result.simulation_input is simulation_input
    assert result.next_state is next_state
    assert result.actual_power_kw == 1.0


def test_battery_result_allows_unchanged_state_identity() -> None:
    simulation_input = make_input()

    result = BatterySimulationResult(
        simulation_input,
        simulation_input.source_state,
        0.0,
    )

    assert result.next_state is simulation_input.source_state


@pytest.mark.parametrize(
    ("power_kw", "meaning"),
    [(2.0, "charging"), (-2.0, "discharging"), (0.0, "idle")],
)
def test_battery_result_uses_actuation_power_sign_contract(
    power_kw: float,
    meaning: str,
) -> None:
    result = BatterySimulationResult(
        make_input(),
        BatterySimulationState(0.5),
        power_kw,
    )

    assert result.actual_power_kw == power_kw
    assert meaning in (BatterySimulationResult.__doc__ or "")


@pytest.mark.parametrize("value", [True, "1", None, object()])
def test_battery_result_rejects_invalid_power_type(value: object) -> None:
    with pytest.raises(TypeError, match="actual_power_kw"):
        BatterySimulationResult(
            make_input(),
            BatterySimulationState(0.5),
            cast(Any, value),
        )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_battery_result_rejects_non_finite_power(value: float) -> None:
    with pytest.raises(ValueError, match="actual_power_kw"):
        BatterySimulationResult(make_input(), BatterySimulationState(0.5), value)


def test_battery_result_rejects_invalid_references() -> None:
    with pytest.raises(TypeError, match="simulation_input"):
        BatterySimulationResult(cast(Any, object()), BatterySimulationState(0.5), 0.0)
    with pytest.raises(TypeError, match="next_state"):
        BatterySimulationResult(make_input(), cast(Any, object()), 0.0)


@pytest.mark.parametrize(
    ("model_type", "expected_slots", "expected_fields"),
    [
        (BatterySimulationState, ("soc",), ["soc"]),
        (
            BatterySimulationInput,
            ("step_identity", "source_state", "actuation"),
            ["step_identity", "source_state", "actuation"],
        ),
        (
            BatterySimulationResult,
            ("simulation_input", "next_state", "actual_power_kw"),
            ["simulation_input", "next_state", "actual_power_kw"],
        ),
    ],
)
def test_battery_model_artifacts_are_frozen_slotted_and_field_complete(
    model_type: type[object],
    expected_slots: tuple[str, ...],
    expected_fields: list[str],
) -> None:
    assert is_dataclass(model_type)
    assert cast(Any, model_type).__dataclass_params__.frozen
    assert cast(Any, model_type).__slots__ == expected_slots
    assert [field.name for field in fields(model_type)] == expected_fields


def test_battery_model_artifacts_have_no_instance_dictionary() -> None:
    simulation_input = make_input()
    result = BatterySimulationResult(
        simulation_input,
        BatterySimulationState(0.6),
        1.0,
    )

    for artifact in (
        simulation_input.source_state,
        simulation_input,
        result,
    ):
        assert not hasattr(artifact, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).next_state = BatterySimulationState(0.7)


def test_battery_boundary_is_abstract_stateless_and_empty_slotted() -> None:
    assert inspect.isabstract(BatterySimulationModelBoundary)
    assert BatterySimulationModelBoundary.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, BatterySimulationModelBoundary)()


def test_test_only_battery_model_receives_exact_input_once() -> None:
    simulation_input = make_input()
    next_state = BatterySimulationState(0.6)
    model = RecordingBatteryModel(next_state, 1.0)

    result = model.simulate(simulation_input)

    assert model.received is simulation_input
    assert result.simulation_input is simulation_input
    assert result.next_state is next_state


def test_battery_boundary_signature_is_contract_only() -> None:
    signature = inspect.signature(BatterySimulationModelBoundary.simulate)

    assert list(signature.parameters) == ["self", "simulation_input"]
    assert signature.return_annotation is BatterySimulationResult
    assert getattr(
        BatterySimulationModelBoundary.simulate,
        "__isabstractmethod__",
        False,
    )


def test_battery_contract_does_not_calculate_or_execute() -> None:
    simulation_input = make_input()
    result = BatterySimulationResult(
        simulation_input,
        BatterySimulationState(0.5),
        0.0,
    )

    assert simulation_input.source_state.soc == 0.5
    for artifact in (simulation_input.source_state, simulation_input, result):
        for forbidden in (
            "calculate_soc",
            "efficiency",
            "degradation",
            "temperature",
            "runtime",
            "command",
            "device",
            "cache",
            "history",
        ):
            assert not hasattr(artifact, forbidden)


def test_battery_module_dependencies_are_contract_only() -> None:
    tree = ast.parse(inspect.getsource(battery_module))
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "dataclasses",
        "kernel.decision.constraint",
        "simulator.core",
        "simulator.validation",
    }


def test_no_concrete_battery_model_is_exported() -> None:
    concrete_models = [
        member
        for _, member in inspect.getmembers(battery_module, inspect.isclass)
        if issubclass(member, BatterySimulationModelBoundary)
        and member is not BatterySimulationModelBoundary
    ]

    assert concrete_models == []
