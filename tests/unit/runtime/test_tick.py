"""Tests for immutable TickResult values."""

from dataclasses import FrozenInstanceError
from typing import Any, cast

import pytest

from kernel.decision import DecisionResult
from kernel.event import EventJournal
from kernel.runtime import TickResult


def test_tick_result_accepts_valid_values() -> None:
    decision_result = DecisionResult.empty()
    journal = EventJournal()
    result = TickResult(decision_result, journal)
    assert result.decision_result is decision_result
    assert result.journal is journal


def test_tick_result_rejects_invalid_decision_result() -> None:
    with pytest.raises(TypeError, match="decision_result"):
        TickResult(cast(DecisionResult, object()), EventJournal())


def test_tick_result_rejects_invalid_journal() -> None:
    with pytest.raises(TypeError, match="journal"):
        TickResult(DecisionResult.empty(), cast(EventJournal, object()))


def test_tick_result_is_frozen() -> None:
    result = TickResult(DecisionResult.empty(), EventJournal())
    with pytest.raises(FrozenInstanceError):
        cast(Any, result).journal = EventJournal()


def test_tick_result_uses_slots() -> None:
    assert not hasattr(
        TickResult(DecisionResult.empty(), EventJournal()),
        "__dict__",
    )
