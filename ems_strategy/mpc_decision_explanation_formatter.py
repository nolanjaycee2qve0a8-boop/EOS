"""Deterministic plain-text presentation of one MPC decision explanation."""

# ruff: noqa: E501, I001, RUF001

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal

from ems_strategy.mpc_decision_explanation import MPCDecisionExplanation


MPCDecisionExplanationLocale = Literal["zh-CN", "en-US"]


@dataclass(frozen=True, slots=True)
class MPCDecisionExplanationFormatInput:
    """Preserve one exact machine explanation and its explicit presentation locale."""

    explanation: MPCDecisionExplanation
    locale: MPCDecisionExplanationLocale

    def __post_init__(self) -> None:
        if not isinstance(self.explanation, MPCDecisionExplanation):
            raise TypeError("explanation must be an MPCDecisionExplanation")
        if self.locale not in ("zh-CN", "en-US"):
            raise ValueError("locale must be 'zh-CN' or 'en-US'")


@dataclass(frozen=True, slots=True)
class FormattedMPCDecisionExplanation:
    """Retain one exact formatter input and its non-empty stable plain text."""

    source_input: MPCDecisionExplanationFormatInput
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, MPCDecisionExplanationFormatInput):
            raise TypeError("source_input must be an MPCDecisionExplanationFormatInput")
        if not isinstance(self.text, str):
            raise TypeError("text must be a str")
        if not self.text.strip():
            raise ValueError("text must be non-empty")


class MPCDecisionExplanationFormatterBoundary(ABC):
    """Define stateless presentation of existing MPC explanation evidence."""

    __slots__ = ()

    @abstractmethod
    def format(
        self,
        format_input: MPCDecisionExplanationFormatInput,
    ) -> FormattedMPCDecisionExplanation:
        """Render supplied read-model facts without deriving or executing them."""
        raise NotImplementedError


class DeterministicMPCDecisionExplanationFormatter(
    MPCDecisionExplanationFormatterBoundary
):
    """Render fixed localized templates from one supplied explanation only."""

    __slots__ = ()

    def format(
        self,
        format_input: MPCDecisionExplanationFormatInput,
    ) -> FormattedMPCDecisionExplanation:
        if not isinstance(format_input, MPCDecisionExplanationFormatInput):
            raise TypeError("format_input must be an MPCDecisionExplanationFormatInput")
        explanation = format_input.explanation
        text = (
            self._format_zh_cn(explanation)
            if format_input.locale == "zh-CN"
            else self._format_en_us(explanation)
        )
        return FormattedMPCDecisionExplanation(format_input, text)

    @classmethod
    def _format_zh_cn(cls, explanation: MPCDecisionExplanation) -> str:
        physical = explanation.physical_explanation
        return "\n".join(
            (
                f"最终决策：{cls._action_zh(explanation.final_action.action)} "
                f"{cls._power(explanation.final_requested_power_kw)}",
                f"原始候选：{cls._action_zh(explanation.candidate_action.action)} "
                f"{cls._power(explanation.candidate_requested_power_kw)}",
                f"是否发生物理修订：{'是' if explanation.revision_applied else '否'}",
                "",
                "修订原因：",
                *cls._bullets(
                    (
                        cls._revision_reason_zh(reason)
                        for reason in physical.revision_reasons
                    ),
                    "无",
                ),
                "",
                "候选物理证据：",
                f"* 功率约束：{cls._joined_or_none(physical.candidate_power_violation_kinds, cls._power_kind_zh, '无')}",
                f"* SOC约束：{cls._joined_or_none(physical.candidate_soc_violation_kinds, cls._soc_kind_zh, '无')}",
                f"* 候选电池规划范围：{'通过' if physical.candidate_battery_horizon_feasible else '不通过'}",
                "",
                "SOC轨迹：",
                f"* 候选：{cls._soc(physical.candidate_starting_soc_fraction)} -> {cls._soc(physical.candidate_ending_soc_fraction)}",
                f"* 最终：{cls._soc(physical.final_starting_soc_fraction)} -> {cls._soc(physical.final_ending_soc_fraction)}",
                f"* 规划范围：{cls._soc(physical.min_soc_fraction)} ~ {cls._soc(physical.max_soc_fraction)}",
                "",
                "电池功率上限：",
                f"* 最大充电功率：{cls._power(physical.max_charge_power_kw)}",
                f"* 最大放电功率：{cls._power(physical.max_discharge_power_kw)}",
                "",
                "最终物理校验：",
                f"* SOC：{'通过' if physical.final_soc_feasible else '不通过'}",
                f"* Power：{'通过' if physical.final_power_feasible else '不通过'}",
                f"* Battery Horizon：{'通过' if physical.final_battery_horizon_feasible else '不通过'}",
            )
        )

    @classmethod
    def _format_en_us(cls, explanation: MPCDecisionExplanation) -> str:
        physical = explanation.physical_explanation
        return "\n".join(
            (
                f"Final decision: {cls._action_en(explanation.final_action.action)} "
                f"{cls._power(explanation.final_requested_power_kw)}",
                f"Original candidate: {cls._action_en(explanation.candidate_action.action)} "
                f"{cls._power(explanation.candidate_requested_power_kw)}",
                f"Physical revision: {'Yes' if explanation.revision_applied else 'No'}",
                "",
                "Revision reasons:",
                *cls._bullets(
                    (
                        cls._revision_reason_en(reason)
                        for reason in physical.revision_reasons
                    ),
                    "None",
                ),
                "",
                "Candidate physical evidence:",
                f"* Power constraint: {cls._joined_or_none(physical.candidate_power_violation_kinds, cls._power_kind_en, 'None')}",
                f"* SOC constraint: {cls._joined_or_none(physical.candidate_soc_violation_kinds, cls._soc_kind_en, 'None')}",
                f"* Candidate battery horizon: {'Pass' if physical.candidate_battery_horizon_feasible else 'Fail'}",
                "",
                "SOC trajectory:",
                f"* Candidate: {cls._soc(physical.candidate_starting_soc_fraction)} -> {cls._soc(physical.candidate_ending_soc_fraction)}",
                f"* Final: {cls._soc(physical.final_starting_soc_fraction)} -> {cls._soc(physical.final_ending_soc_fraction)}",
                f"* Planning range: {cls._soc(physical.min_soc_fraction)} ~ {cls._soc(physical.max_soc_fraction)}",
                "",
                "Battery power limits:",
                f"* Maximum charge power: {cls._power(physical.max_charge_power_kw)}",
                f"* Maximum discharge power: {cls._power(physical.max_discharge_power_kw)}",
                "",
                "Final physical verification:",
                f"* SOC: {'Pass' if physical.final_soc_feasible else 'Fail'}",
                f"* Power: {'Pass' if physical.final_power_feasible else 'Fail'}",
                f"* Battery horizon: {'Pass' if physical.final_battery_horizon_feasible else 'Fail'}",
            )
        )

    @staticmethod
    def _bullets(values: Iterable[str], none: str) -> tuple[str, ...]:
        rendered = tuple(f"* {value}" for value in values)
        return rendered or (f"* {none}",)

    @staticmethod
    def _joined_or_none(
        values: tuple[str, ...],
        localizer: Callable[[str], str],
        none: str,
    ) -> str:
        if not values:
            return none
        return "; ".join(localizer(value) for value in values)

    @staticmethod
    def _power(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".") + " kW"

    @staticmethod
    def _soc(value: float) -> str:
        return f"{value * 100:.2f}%"

    @staticmethod
    def _action_zh(action: str) -> str:
        return {"charge": "充电", "discharge": "放电", "idle": "待机"}[action]

    @staticmethod
    def _action_en(action: str) -> str:
        return {"charge": "Charge", "discharge": "Discharge", "idle": "Idle"}[action]

    @staticmethod
    def _revision_reason_zh(reason: str) -> str:
        return {
            "charge_power_limit": "充电请求功率超过电池规划上限",
            "discharge_power_limit": "放电请求功率超过电池规划上限",
            "max_soc_limit": "充电将导致SOC超过规划上限",
            "min_soc_limit": "放电将导致SOC低于规划下限",
        }[reason]

    @staticmethod
    def _revision_reason_en(reason: str) -> str:
        return {
            "charge_power_limit": "Requested charge power exceeds the battery planning limit",
            "discharge_power_limit": "Requested discharge power exceeds the battery planning limit",
            "max_soc_limit": "Charging would exceed the planned maximum SOC",
            "min_soc_limit": "Discharging would fall below the planned minimum SOC",
        }[reason]

    @staticmethod
    def _soc_kind_zh(kind: str) -> str:
        return {
            "below_min_soc": "SOC低于规划下限",
            "above_max_soc": "SOC超过规划上限",
        }[kind]

    @staticmethod
    def _soc_kind_en(kind: str) -> str:
        return {
            "below_min_soc": "SOC below planned minimum",
            "above_max_soc": "SOC above planned maximum",
        }[kind]

    @staticmethod
    def _power_kind_zh(kind: str) -> str:
        return {
            "charge_power_above_max": "充电功率超过最大允许值",
            "discharge_power_above_max": "放电功率超过最大允许值",
        }[kind]

    @staticmethod
    def _power_kind_en(kind: str) -> str:
        return {
            "charge_power_above_max": "Charge power exceeds maximum allowed",
            "discharge_power_above_max": "Discharge power exceeds maximum allowed",
        }[kind]
