"""Read-only requests adapting two existing policies, never execution logic."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from math import isfinite

from ems_simulator.input import BatteryParameters
from tools.closed_loop_time_energy_probe import _request as demo_request
from tools.dynamic_constraint_probe import FactSegment
from tools.dynamic_constraint_probe import _request as joint_request

JOINT = "joint_reserve_v1"
BASIC = "demo_self_consumption_v1"
STRATEGIES = (JOINT, BASIC)


@dataclass(frozen=True, slots=True)
class StrategyInput:
    """Detached immutable snapshot; no executor, ledger or mutable state handle."""

    at_s: int
    soc: float
    fact: FactSegment
    battery: BatteryParameters

    @classmethod
    def snapshot(
        cls, at_s: int, soc: float, fact: FactSegment, battery: BatteryParameters
    ) -> "StrategyInput":
        return cls(at_s, soc, replace(fact), replace(battery))


@dataclass(frozen=True, slots=True)
class RequestStrategy:
    """Trusted offline callback, not a sandbox for hostile Python code."""

    identifier: str
    request: Callable[[StrategyInput], float]

    def __post_init__(self) -> None:
        if self.identifier not in STRATEGIES:
            raise ValueError("unknown strategy identifier")
        if not callable(self.request):
            raise TypeError("strategy must be callable")

    def evaluate(self, facts: StrategyInput) -> float:
        value = self.request(facts)
        if type(value) not in (int, float) or not isfinite(value):
            raise ValueError("strategy must return a finite numeric request")
        return float(value)


def _joint(facts: StrategyInput) -> float:
    return joint_request(facts.fact, facts.soc, facts.battery)


def _basic(facts: StrategyInput) -> float:
    return demo_request(
        facts.fact.load_kw, facts.fact.pv_kw, facts.soc, facts.fact.reserve_target_soc
    )


def strategy_by_id(identifier: str) -> RequestStrategy:
    if identifier == JOINT:
        return RequestStrategy(identifier, _joint)
    if identifier == BASIC:
        return RequestStrategy(identifier, _basic)
    raise ValueError("unknown strategy identifier")
