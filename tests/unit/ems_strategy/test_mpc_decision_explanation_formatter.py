"""Tests for deterministic presentation of TASK-123 MPC explanation evidence."""

# ruff: noqa: RUF001

import ast
import inspect
from abc import ABC
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

import ems_strategy
from ems_strategy import (
    DeterministicMPCDecisionExplanationBuilder,
    DeterministicMPCDecisionExplanationFormatter,
    FormattedMPCDecisionExplanation,
    MPCDecisionExplanationFormatInput,
    MPCDecisionExplanationFormatterBoundary,
)
from ems_strategy.mpc_decision_explanation import MPCDecisionExplanation
from optimization import BatteryOptimizationModel
from tests.unit.ems_strategy.test_physically_aware_mpc_cycle import (
    make_orchestrator,
    make_physical_input,
    make_real_physical_optimizer,
)


def _explanation(*, soc: float = 0.8, power: float = 6.0) -> MPCDecisionExplanation:
    result = (
        make_orchestrator().run_cycle(make_physical_input(soc=soc))
        if power == 6.0
        else make_orchestrator(make_real_physical_optimizer(power)).run_cycle(
            make_physical_input(soc=soc)
        )
    )
    return DeterministicMPCDecisionExplanationBuilder().explain(
        ems_strategy.MPCDecisionExplanationInput(result)
    )


def test_format_contracts_are_immutable_slotted_and_preserve_exact_identity() -> None:
    explanation = _explanation()
    format_input = MPCDecisionExplanationFormatInput(explanation, "en-US")
    formatted = DeterministicMPCDecisionExplanationFormatter().format(format_input)

    assert [field.name for field in fields(MPCDecisionExplanationFormatInput)] == [
        "explanation",
        "locale",
    ]
    assert [field.name for field in fields(FormattedMPCDecisionExplanation)] == [
        "source_input",
        "text",
    ]
    assert formatted.source_input is format_input
    assert formatted.source_input.explanation is explanation
    assert not hasattr(format_input, "__dict__")
    assert not hasattr(formatted, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, formatted).text = "changed"


@pytest.mark.parametrize("locale", ["", "fr-FR", None])
def test_format_input_rejects_unsupported_locale(locale: object) -> None:
    with pytest.raises(ValueError, match="locale"):
        MPCDecisionExplanationFormatInput(_explanation(), cast(Any, locale))


def test_formatted_result_rejects_empty_text() -> None:
    format_input = MPCDecisionExplanationFormatInput(_explanation(), "en-US")
    with pytest.raises(ValueError, match="non-empty"):
        FormattedMPCDecisionExplanation(format_input, "   ")


def test_zh_cn_power_revision_renders_existing_evidence_without_recalculation() -> None:
    text = (
        DeterministicMPCDecisionExplanationFormatter()
        .format(MPCDecisionExplanationFormatInput(_explanation(), "zh-CN"))
        .text
    )

    assert "最终决策：放电 4 kW" in text
    assert "原始候选：放电 6 kW" in text
    assert "是否发生物理修订：是" in text
    assert "放电请求功率超过电池规划上限" in text
    assert "放电功率超过最大允许值" in text
    assert "SOC约束：无" in text
    assert "候选电池规划范围：不通过" in text
    assert "* SOC：通过" in text
    assert "* Power：通过" in text
    assert "* Battery Horizon：通过" in text


def test_en_us_soc_revision_renders_projection_values_and_final_pass() -> None:
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        ems_strategy.MPCDecisionExplanationInput(
            make_orchestrator().run_cycle(
                make_physical_input(
                    soc=0.2,
                    model=BatteryOptimizationModel(
                        10.0, 0.1, 0.9, 10.0, 10.0, 1.0, 0.9
                    ),
                )
            )
        )
    )
    text = (
        DeterministicMPCDecisionExplanationFormatter()
        .format(MPCDecisionExplanationFormatInput(explanation, "en-US"))
        .text
    )

    assert "Discharging would fall below the planned minimum SOC" in text
    assert "SOC below planned minimum" in text
    assert "* Candidate: 20.00% ->" in text
    assert "* Final: 20.00% ->" in text
    assert "* SOC: Pass" in text


def test_no_revision_idle_and_numeric_rendering_keep_all_sections() -> None:
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        ems_strategy.MPCDecisionExplanationInput(
            make_orchestrator(make_real_physical_optimizer(2.3456)).run_cycle(
                make_physical_input(
                    prices=(0.5,),
                    model=BatteryOptimizationModel(10.0, 0.1, 0.9, 5.0, 5.0, 1.0, 1.0),
                )
            )
        )
    )
    text = (
        DeterministicMPCDecisionExplanationFormatter()
        .format(MPCDecisionExplanationFormatInput(explanation, "zh-CN"))
        .text
    )

    assert "最终决策：待机 0 kW" in text
    assert "原始候选：待机 0 kW" in text
    assert "是否发生物理修订：否" in text
    assert "* 无" in text
    assert "候选物理证据：" in text
    assert "最终物理校验：" in text


def test_candidate_horizon_boolean_is_not_derived_from_selected_step_evidence() -> None:
    explanation = DeterministicMPCDecisionExplanationBuilder().explain(
        ems_strategy.MPCDecisionExplanationInput(
            make_orchestrator().run_cycle(
                make_physical_input(
                    prices=(0.9, 0.9),
                    soc=0.8,
                    model=BatteryOptimizationModel(
                        10.0, 0.1, 0.9, 10.0, 10.0, 1.0, 1.0
                    ),
                )
            )
        )
    )
    text = (
        DeterministicMPCDecisionExplanationFormatter()
        .format(MPCDecisionExplanationFormatInput(explanation, "en-US"))
        .text
    )

    assert explanation.physical_explanation.candidate_soc_violation_kinds == ()
    assert explanation.physical_explanation.candidate_power_violation_kinds == ()
    assert explanation.physical_explanation.candidate_battery_horizon_feasible is False
    assert "* SOC constraint: None" in text
    assert "* Power constraint: None" in text
    assert "* Candidate battery horizon: Fail" in text


def test_formatter_boundary_is_abstract_stateless_and_has_no_execution_dependency() -> (
    None
):
    signature = inspect.signature(MPCDecisionExplanationFormatterBoundary.format)
    hints = get_type_hints(MPCDecisionExplanationFormatterBoundary.format)
    module_path = (
        Path(ems_strategy.__file__).parent / "mpc_decision_explanation_formatter.py"
    )
    source = module_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }

    assert issubclass(MPCDecisionExplanationFormatterBoundary, ABC)
    assert inspect.isabstract(MPCDecisionExplanationFormatterBoundary)
    assert MPCDecisionExplanationFormatterBoundary.__slots__ == ()
    assert list(signature.parameters) == ["self", "format_input"]
    assert hints["format_input"] is MPCDecisionExplanationFormatInput
    assert hints["return"] is FormattedMPCDecisionExplanation
    with pytest.raises(TypeError):
        MPCDecisionExplanationFormatterBoundary()  # type: ignore[abstract]
    assert not hasattr(DeterministicMPCDecisionExplanationFormatter(), "__dict__")
    for forbidden in (
        "optimization",
        "ems_simulator",
        "runtime",
        "device",
        "execution",
    ):
        assert forbidden not in imported_modules


def test_public_api_exports_formatter_contracts() -> None:
    for name in (
        "MPCDecisionExplanationLocale",
        "MPCDecisionExplanationFormatInput",
        "FormattedMPCDecisionExplanation",
        "MPCDecisionExplanationFormatterBoundary",
        "DeterministicMPCDecisionExplanationFormatter",
    ):
        assert name in ems_strategy.__all__
