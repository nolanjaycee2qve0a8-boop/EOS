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
# Kept outside STRATEGIES: the existing two-policy comparison must not silently
# acquire a third policy without an explicit, timestamped forecast schedule.
MPC = "physically_aware_price_mpc_v1"
STRATEGIES = (JOINT, BASIC)


@dataclass(frozen=True, slots=True)
class StrategyInput:
    """Detached snapshot; MPC facts must carry a matured observation clock.

    The older JOINT/BASIC callbacks retain their original immediate fact
    contract. MPC alone receives the last delivered observation (or None),
    never the current scenario truth before that observation is available.
    """

    at_s: int
    soc: float
    fact: FactSegment | None
    battery: BatteryParameters
    observed_at_s: int | None = None
    available_at_s: int | None = None
    max_observation_age_s: int | None = None

    @classmethod
    def snapshot(
        cls,
        at_s: int,
        soc: float,
        fact: FactSegment | None,
        battery: BatteryParameters,
        *,
        observed_at_s: int | None = None,
        available_at_s: int | None = None,
        max_observation_age_s: int | None = None,
    ) -> "StrategyInput":
        return cls(
            at_s,
            soc,
            None if fact is None else replace(fact),
            replace(battery),
            observed_at_s,
            available_at_s,
            max_observation_age_s,
        )


@dataclass(frozen=True, slots=True)
class RequestStrategy:
    """Trusted offline callback, not a sandbox for hostile Python code."""

    identifier: str
    request: Callable[[StrategyInput], float]

    def __post_init__(self) -> None:
        if self.identifier == MPC:
            raise ValueError("MPC requires issued-forecast preflight")
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
    if facts.fact is None:
        raise ValueError("joint strategy requires a fact")
    return joint_request(facts.fact, facts.soc, facts.battery)


def _basic(facts: StrategyInput) -> float:
    if facts.fact is None:
        raise ValueError("basic strategy requires a fact")
    return demo_request(
        facts.fact.load_kw, facts.fact.pv_kw, facts.soc, facts.fact.reserve_target_soc
    )


def strategy_by_id(identifier: str) -> RequestStrategy:
    if identifier == JOINT:
        return RequestStrategy(identifier, _joint)
    if identifier == BASIC:
        return RequestStrategy(identifier, _basic)
    raise ValueError("unknown strategy identifier")
