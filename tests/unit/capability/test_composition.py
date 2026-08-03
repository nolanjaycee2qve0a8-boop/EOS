"""Tests for the EMS capability composition boundary."""

import ast
import inspect
from abc import ABC
from datetime import UTC, datetime
from typing import Any, cast, get_type_hints

import pytest

from capability import CapabilityCompositionBoundary, EMSCapabilityBoundary
from capability import composition as composition_module
from kernel.decision import DecisionContext, DecisionIntent


def make_context() -> DecisionContext:
    return DecisionContext(
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        soc=0.5,
        battery_power_limit_kw=50.0,
        battery_energy_capacity_kwh=100.0,
        pv_power_kw=25.0,
        load_power_kw=20.0,
        grid_power_kw=-5.0,
        electricity_price_cny_per_kwh=0.5,
        reserve_soc=0.2,
        export_limit_kw=10.0,
    )


class SequentialTestComposition(CapabilityCompositionBoundary):
    """Test-only conforming implementation without resolution behavior."""

    __slots__ = ()

    def evaluate(
        self,
        context: DecisionContext,
        capabilities: tuple[EMSCapabilityBoundary, ...],
    ) -> tuple[DecisionIntent, ...]:
        return tuple(capability.evaluate(context) for capability in capabilities)


def make_recording_capability(
    name: str,
    intent: DecisionIntent,
    calls: list[tuple[str, DecisionContext]],
) -> EMSCapabilityBoundary:
    class RecordingCapability(EMSCapabilityBoundary):
        __slots__ = ()

        def evaluate(self, context: DecisionContext) -> DecisionIntent:
            calls.append((name, context))
            return intent

    return RecordingCapability()


def test_composition_boundary_is_abstract() -> None:
    assert issubclass(CapabilityCompositionBoundary, ABC)
    assert inspect.isabstract(CapabilityCompositionBoundary)
    with pytest.raises(TypeError):
        CapabilityCompositionBoundary()  # type: ignore[abstract]


def test_evaluate_contract_is_explicit() -> None:
    parameters = list(
        inspect.signature(CapabilityCompositionBoundary.evaluate).parameters
    )
    hints = get_type_hints(CapabilityCompositionBoundary.evaluate)

    assert parameters == ["self", "context", "capabilities"]
    assert hints == {
        "context": DecisionContext,
        "capabilities": tuple[EMSCapabilityBoundary, ...],
        "return": tuple[DecisionIntent, ...],
    }


def test_conforming_composition_evaluates_each_position_exactly_once() -> None:
    context = make_context()
    calls: list[tuple[str, DecisionContext]] = []
    first_intent = DecisionIntent(3.0)
    second_intent = DecisionIntent(-2.0)
    capabilities = (
        make_recording_capability("first", first_intent, calls),
        make_recording_capability("second", second_intent, calls),
    )

    intents = SequentialTestComposition().evaluate(context, capabilities)

    assert calls == [("first", context), ("second", context)]
    assert calls[0][1] is context
    assert calls[1][1] is context
    assert intents[0] is first_intent
    assert intents[1] is second_intent


def test_caller_order_is_authoritative() -> None:
    context = make_context()
    calls: list[tuple[str, DecisionContext]] = []
    first = make_recording_capability("first", DecisionIntent(1.0), calls)
    second = make_recording_capability("second", DecisionIntent(2.0), calls)

    SequentialTestComposition().evaluate(context, (second, first))

    assert [name for name, _ in calls] == ["second", "first"]


def test_duplicate_capability_positions_are_not_deduplicated() -> None:
    context = make_context()
    calls: list[tuple[str, DecisionContext]] = []
    intent = DecisionIntent(1.0)
    capability = make_recording_capability("same", intent, calls)

    intents = SequentialTestComposition().evaluate(
        context,
        (capability, capability),
    )

    assert [name for name, _ in calls] == ["same", "same"]
    assert intents == (intent, intent)
    assert intents[0] is intent
    assert intents[1] is intent


def test_empty_composition_returns_empty_tuple() -> None:
    assert SequentialTestComposition().evaluate(make_context(), ()) == ()


def test_capability_exception_stops_later_evaluation_and_propagates() -> None:
    context = make_context()
    calls: list[tuple[str, DecisionContext]] = []
    failure = RuntimeError("capability failure")

    class FailingCapability(EMSCapabilityBoundary):
        __slots__ = ()

        def evaluate(self, context: DecisionContext) -> DecisionIntent:
            calls.append(("failing", context))
            raise failure

    later = make_recording_capability("later", DecisionIntent(1.0), calls)

    with pytest.raises(RuntimeError) as caught:
        SequentialTestComposition().evaluate(
            context,
            (FailingCapability(), later),
        )

    assert caught.value is failure
    assert [name for name, _ in calls] == ["failing"]


def test_boundary_has_no_instance_state() -> None:
    composition = SequentialTestComposition()

    assert CapabilityCompositionBoundary.__slots__ == ()
    assert not hasattr(composition, "__dict__")
    for forbidden in (
        "capabilities",
        "policy",
        "constraint",
        "runtime",
        "dispatcher",
        "device",
        "cache",
        "history",
    ):
        assert not hasattr(composition, forbidden)
    with pytest.raises(AttributeError):
        cast(Any, composition).cache = {}


def test_boundary_module_has_only_contract_dependencies() -> None:
    source = inspect.getsource(composition_module)
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert imported_modules == {
        "abc",
        "capability.base",
        "kernel.decision",
    }
    for forbidden in (
        "constraint",
        "runtime",
        "dispatch",
        "device",
        "persistence",
        "telemetry",
        "optimization",
        "forecast",
        "tou",
    ):
        assert all(
            forbidden not in module for module in imported_modules if module is not None
        )


def test_no_concrete_production_composition_is_introduced() -> None:
    production_classes = [
        value
        for value in vars(composition_module).values()
        if inspect.isclass(value) and value.__module__ == composition_module.__name__
    ]

    assert production_classes == [CapabilityCompositionBoundary]
    assert inspect.isabstract(production_classes[0])


def test_public_import() -> None:
    from capability import __all__ as public_names

    assert public_names == [
        "CapabilityCompositionBoundary",
        "CapabilityDescriptor",
        "DeterministicIntentResolutionImplementation",
        "DeterministicIntentResolutionParameters",
        "EMSCapabilityBoundary",
        "IntentResolutionBoundary",
        "SelfConsumptionCapability",
        "TOUCapabilityParameters",
        "TOUEnergyCapability",
    ]
