"""Fairness, physical bookkeeping, tariff boundaries and inventory accounting."""

from pathlib import Path

import pytest

from tools.dynamic_constraint_probe import Case, FactSegment
from tools.joint_execution_contract import DAY_ENERGY_TOL, SOC_TOL
from tools.joint_strategy_adapter import BASIC, JOINT
from tools.joint_strategy_comparison import (
    compare_metrics,
    comparison_cases,
    metric_tolerance,
    metrics,
    positive_linear_mean,
    price_piece,
    run_comparison,
    run_strategy,
)


@pytest.mark.parametrize("case_name", ["original", "reserve"])
@pytest.mark.parametrize("mode", ["ideal", "dynamic"])
@pytest.mark.parametrize("identifier", [JOINT, BASIC])
def test_three_steps_same_control_conservation(
    case_name: str, mode: str, identifier: str
) -> None:
    case = comparison_cases()[case_name]
    results = [
        run_strategy(case, identifier, mode=mode, step_s=s) for s in (3600, 60, 15)
    ]
    ref = metrics(results[0])
    for result in results:
        assert result.passed
        actual = metrics(result)
        for key, delta in compare_metrics(ref, actual).items():
            assert abs(delta) <= metric_tolerance(key), (key, delta)
        assert abs(actual["available_pv_kwh"] - 39.6) <= DAY_ENERGY_TOL
        assert abs(actual["load_kwh"] - 29.4) <= DAY_ENERGY_TOL
        assert result.execution.case is case
        assert result.execution.settings.pv_ac_max_kw == 6
        for a, b in zip(
            result.execution.ledger[:-1], result.execution.ledger[1:], strict=True
        ):
            assert a.end_s == b.start_s and a.soc_after == b.soc_before


def test_terminal_difference_and_zero_difference() -> None:
    case = comparison_cases()["reserve"]
    a = metrics(run_strategy(case, JOINT, mode="dynamic", step_s=60))
    b = metrics(run_strategy(case, BASIC, mode="dynamic", step_s=60))
    assert abs(a["final_soc"] - b["final_soc"]) > SOC_TOL
    assert all(x == 0 for x in compare_metrics(a, a).values())
    for values in (a, b):
        for price in (0.3, 0.55, 0.9):
            expected = (values["final_soc"] - 0.2) * 10 * 0.95 * price
            assert (
                abs(values[f"terminal_value_cny_at_{price}"] - expected)
                < DAY_ENERGY_TOL
            )
            assert (
                values[f"inventory_adjusted_cost_cny_at_{price}"]
                == values["net_cost_cny"] - values[f"terminal_value_cny_at_{price}"]
            )


def test_tariff_boundary_and_local_sub_ulp_duration() -> None:
    prices = (1.0, 2.0) + (0.0,) * 22
    cost, revenue = price_piece(3500, 0, 200, 3, prices)
    assert cost == pytest.approx(3 * 100 / 3600 * 3, abs=1e-12)
    assert revenue == 0
    assert price_piece(3500, 0, 200, -3, prices) == (0, 0)
    # A positive local duration survives even when absolute endpoints coincide.
    cost, _ = price_piece(41136.896491228035, 0, 1.4e-12, 3)
    assert cost > 0


def test_bidirectional_flows_not_netted() -> None:
    case = Case(
        "reversal",
        0.2,
        (
            FactSegment(0, 1800, 2, 0, False, False, 0.2),
            FactSegment(1800, 3600, 0, 2, False, False, 0.2),
            FactSegment(3600, 86400, 0, 0, False, False, 0.2),
        ),
    )
    result = run_strategy(case, BASIC, mode="ideal", step_s=3600)
    value = metrics(result)
    assert value["import_kwh"] == pytest.approx(1, abs=DAY_ENERGY_TOL)
    assert value["export_kwh"] == pytest.approx(1, abs=DAY_ENERGY_TOL)
    assert value["net_cost_cny"] == pytest.approx(0.3, abs=DAY_ENERGY_TOL)


def test_soft_gap_crossing_integral() -> None:
    assert positive_linear_mean(-1, 1) == 0.25
    assert positive_linear_mean(1, -1) == 0.25
    assert positive_linear_mean(-1, -2) == 0
    assert positive_linear_mean(1, 2) == 1.5


def test_output_refuses_overwrite(tmp_path: Path) -> None:
    with pytest.raises(FileExistsError):
        run_comparison(tmp_path)
    assert not (tmp_path / "COMPLETE").exists()
