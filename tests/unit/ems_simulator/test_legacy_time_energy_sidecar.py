"""Regression checks for fixed-request legacy/new physical accounting."""

import pytest

from tools.compare_legacy_time_energy import ABS_LIMIT, compare_scenario, scenarios


@pytest.mark.parametrize("name", tuple(scenarios()))
def test_24_hour_fixed_request_physical_accounting(name: str) -> None:
    rows, requests = compare_scenario(scenarios()[name])

    assert len(requests) == 24
    assert len(rows) == 24 * 6
    assert {row["hour"] for row in rows} == set(range(24))
    assert all(row["within_limit"] for row in rows)
    assert max(abs(float(row["delta"])) for row in rows) <= ABS_LIMIT


@pytest.mark.parametrize("name", ("upper_bound", "lower_bound"))
def test_clipped_request_is_replayed_not_legacy_actual(name: str) -> None:
    rows, requests = compare_scenario(scenarios()[name])
    first = rows[0]

    assert requests[0] == first["request_kw"]
    assert requests[0] != first["legacy_actual_kw"]
    assert int(first["sidecar_slices"]) > 1


def test_hour_boundary_event_is_not_duplicated() -> None:
    rows, requests = compare_scenario(scenarios()["hour_boundary"])

    assert requests[:2] == (-3.0, 2.0)
    assert rows[0]["measure"] == "soc_end"
    assert rows[0]["sidecar"] == pytest.approx(0.2, abs=ABS_LIMIT)
    assert all(row["sidecar_slices"] == 1 for row in rows[:12])
    assert all(row["within_limit"] for row in rows)
