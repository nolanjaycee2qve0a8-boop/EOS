"""Tests for shared domain validation primitives."""

from collections.abc import Mapping, MutableMapping
from datetime import UTC, datetime, timedelta, tzinfo
from typing import cast

import pytest

from kernel.domain.validation import (
    freeze_mapping,
    require_non_empty_string,
    require_non_negative_integer,
    require_timezone_aware,
)

FIXED_TIME = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class UndefinedOffsetTimezone(tzinfo):
    """A tzinfo whose offset is undefined for awareness validation."""

    def utcoffset(self, dt: datetime | None) -> None:
        return None

    def dst(self, dt: datetime | None) -> None:
        return None

    def tzname(self, dt: datetime | None) -> str:
        return "undefined"


def test_require_non_empty_string_returns_value() -> None:
    assert require_non_empty_string(" value ", "field") == " value "


@pytest.mark.parametrize("value", ["", "  "])
def test_require_non_empty_string_rejects_empty_values(value: str) -> None:
    with pytest.raises(ValueError, match="field"):
        require_non_empty_string(value, "field")


def test_require_non_empty_string_rejects_non_string() -> None:
    with pytest.raises(ValueError, match="field"):
        require_non_empty_string(cast(str, 1), "field")


def test_require_timezone_aware_returns_aware_datetime() -> None:
    assert require_timezone_aware(FIXED_TIME, "observed_at") is FIXED_TIME


def test_require_timezone_aware_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="observed_at"):
        require_timezone_aware(datetime(2026, 1, 1, 12, 0), "observed_at")


def test_require_timezone_aware_rejects_undefined_offset() -> None:
    value = datetime(2026, 1, 1, 12, 0, tzinfo=UndefinedOffsetTimezone())
    with pytest.raises(ValueError, match="observed_at"):
        require_timezone_aware(value, "observed_at")


def test_require_non_negative_integer_returns_value() -> None:
    assert require_non_negative_integer(0, "priority") == 0


@pytest.mark.parametrize("value", [-1, True, False])
def test_require_non_negative_integer_rejects_invalid_values(value: int) -> None:
    with pytest.raises(ValueError, match="priority"):
        require_non_negative_integer(value, "priority")


def test_freeze_mapping_returns_equal_mapping() -> None:
    assert freeze_mapping({"limit_kw": 5}, "parameters") == {"limit_kw": 5}


def test_freeze_mapping_defensively_copies_first_level() -> None:
    source: dict[str, object] = {"limit_kw": 5}
    frozen = freeze_mapping(source, "parameters")
    source["limit_kw"] = 10
    assert frozen["limit_kw"] == 5


def test_freeze_mapping_rejects_non_mapping() -> None:
    value = cast(Mapping[str, object], ["not", "a", "mapping"])
    with pytest.raises(ValueError, match="parameters"):
        freeze_mapping(value, "parameters")


@pytest.mark.parametrize("key", ["", "  "])
def test_freeze_mapping_rejects_empty_keys(key: str) -> None:
    with pytest.raises(ValueError, match="parameters"):
        freeze_mapping({key: 1}, "parameters")


def test_freeze_mapping_result_is_read_only() -> None:
    frozen = cast(MutableMapping[str, object], freeze_mapping({}, "parameters"))
    with pytest.raises(TypeError):
        frozen["limit_kw"] = 5


def test_timezone_comparison_fixture_is_fixed() -> None:
    assert FIXED_TIME + timedelta(hours=1) > FIXED_TIME
