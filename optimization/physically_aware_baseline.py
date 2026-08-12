"""One-pass physical revision of the deterministic price-only candidate."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import isfinite, nextafter
from typing import Literal

from decision_formation import DecisionIntent
from optimization.battery_horizon_constraint import (
    BatteryHorizonConstraintAggregateBoundary,
    BatteryHorizonConstraintEvaluation,
    BatteryHorizonConstraintInput,
)
from optimization.battery_planning import BatteryOptimizationInput
from optimization.battery_power_constraint import (
    BatteryPowerHorizonConstraintBoundary,
    BatteryPowerHorizonConstraintEvaluation,
    BatteryPowerHorizonConstraintInput,
)
from optimization.battery_soc_constraint import (
    BatterySOCHorizonConstraintBoundary,
    BatterySOCHorizonConstraintEvaluation,
    BatterySOCHorizonConstraintInput,
)
from optimization.battery_soc_projection import (
    BatterySOCHorizonProjection,
    BatterySOCHorizonProjectionBoundary,
    BatterySOCHorizonProjectionInput,
)
from optimization.model import OptimizationResult
from optimization.price_aware_baseline import PriceAwareBaselineOptimizer
from optimization.solution import OptimizationSolution, OptimizationSolutionStep
from optimization.solution_boundary import OptimizationSolveOutput

BatterySolutionRevisionReason = Literal[
    "charge_power_limit",
    "discharge_power_limit",
    "max_soc_limit",
    "min_soc_limit",
]

_CHARGE_REASONS: tuple[BatterySolutionRevisionReason, ...] = (
    "charge_power_limit",
    "max_soc_limit",
)
_DISCHARGE_REASONS: tuple[BatterySolutionRevisionReason, ...] = (
    "discharge_power_limit",
    "min_soc_limit",
)


def _require_positive_seconds(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("control_step_duration_seconds must be a number")
    normalized = float(value)
    if not isfinite(normalized) or normalized <= 0:
        raise ValueError(
            "control_step_duration_seconds must be finite and greater than 0"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class PhysicallyAwareBaselineOptimizationInput:
    """Compose one exact battery planning request and explicit step duration."""

    battery_input: BatteryOptimizationInput
    control_step_duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.battery_input, BatteryOptimizationInput):
            raise TypeError("battery_input must be a BatteryOptimizationInput")
        object.__setattr__(
            self,
            "control_step_duration_seconds",
            _require_positive_seconds(self.control_step_duration_seconds),
        )


@dataclass(frozen=True, slots=True)
class BatterySolutionRevisionStep:
    """Explain one exact candidate-to-revised planning-step replacement."""

    source_candidate_step: OptimizationSolutionStep
    revised_step: OptimizationSolutionStep
    step_index: int
    reasons: tuple[BatterySolutionRevisionReason, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_candidate_step, OptimizationSolutionStep):
            raise TypeError("source_candidate_step must be an OptimizationSolutionStep")
        if not isinstance(self.revised_step, OptimizationSolutionStep):
            raise TypeError("revised_step must be an OptimizationSolutionStep")
        if self.revised_step is self.source_candidate_step:
            raise ValueError("revised_step must be a new explicit solution step")
        if isinstance(self.step_index, bool) or not isinstance(self.step_index, int):
            raise TypeError("step_index must be an integer")
        if self.step_index < 0:
            raise ValueError("step_index must be greater than or equal to 0")
        if not isinstance(self.reasons, tuple):
            raise TypeError("reasons must be a tuple")
        allowed_reasons = (
            "charge_power_limit",
            "discharge_power_limit",
            "max_soc_limit",
            "min_soc_limit",
        )
        if any(reason not in allowed_reasons for reason in self.reasons):
            raise ValueError(
                "reasons must contain BatterySolutionRevisionReason values"
            )
        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("reasons must not contain duplicates")
        expected_order = (
            _CHARGE_REASONS
            if self.source_candidate_step.intent.action == "charge"
            else _DISCHARGE_REASONS
            if self.source_candidate_step.intent.action == "discharge"
            else ()
        )
        if (
            tuple(reason for reason in expected_order if reason in self.reasons)
            != self.reasons
        ):
            raise ValueError(
                "reasons must preserve deterministic action-specific order"
            )
        if self.revised_step.timestamp is not self.source_candidate_step.timestamp:
            raise ValueError("revised_step must preserve exact timestamp identity")
        if self.source_candidate_step.intent.action == "idle":
            if (
                self.revised_step.intent.action != "idle"
                or self.revised_step.requested_power_kw != 0
                or self.reasons
            ):
                raise ValueError(
                    "idle candidate steps must remain idle without reasons"
                )
        elif self.revised_step.intent.action not in (
            self.source_candidate_step.intent.action,
            "idle",
        ):
            raise ValueError("revision must not reverse a candidate action direction")
        elif (
            self.revised_step.requested_power_kw
            > self.source_candidate_step.requested_power_kw
        ):
            raise ValueError("revision must not increase candidate requested power")


@dataclass(frozen=True, slots=True)
class BatterySolutionRevision:
    """Retain complete exact candidate and final planning-step provenance."""

    source_candidate_solution: OptimizationSolution
    revised_solution: OptimizationSolution
    steps: tuple[BatterySolutionRevisionStep, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_candidate_solution, OptimizationSolution):
            raise TypeError("source_candidate_solution must be an OptimizationSolution")
        if not isinstance(self.revised_solution, OptimizationSolution):
            raise TypeError("revised_solution must be an OptimizationSolution")
        if (
            self.revised_solution.source_result
            is self.source_candidate_solution.source_result
        ):
            raise ValueError("revised_solution must preserve a distinct final result")
        if (
            self.revised_solution.source_result.source_problem
            is not self.source_candidate_solution.source_result.source_problem
        ):
            raise ValueError(
                "revised solution must preserve exact source problem identity"
            )
        if not isinstance(self.steps, tuple):
            raise TypeError("steps must be a tuple")
        candidate_steps = self.source_candidate_solution.steps
        revised_steps = self.revised_solution.steps
        if len(self.steps) != len(candidate_steps) or len(self.steps) != len(
            revised_steps
        ):
            raise ValueError(
                "revision steps must cover candidate and revised steps exactly"
            )
        for index, (evidence, candidate, revised) in enumerate(
            zip(self.steps, candidate_steps, revised_steps, strict=True)
        ):
            if not isinstance(evidence, BatterySolutionRevisionStep):
                raise TypeError(
                    "steps must contain BatterySolutionRevisionStep objects"
                )
            if evidence.step_index != index:
                raise ValueError("revision steps must preserve exact candidate order")
            if evidence.source_candidate_step is not candidate:
                raise ValueError("revision must preserve exact candidate step identity")
            if evidence.revised_step is not revised:
                raise ValueError("revision must preserve exact revised step identity")


@dataclass(frozen=True, slots=True)
class PhysicallyAwareOptimizationSolveOutput:
    """Retain candidate, revision, and final physical evidence without loss."""

    source_input: PhysicallyAwareBaselineOptimizationInput
    candidate_output: OptimizationSolveOutput
    candidate_projection: BatterySOCHorizonProjection
    candidate_soc_evaluation: BatterySOCHorizonConstraintEvaluation
    candidate_power_evaluation: BatteryPowerHorizonConstraintEvaluation
    candidate_constraint_evaluation: BatteryHorizonConstraintEvaluation
    revision: BatterySolutionRevision
    final_output: OptimizationSolveOutput
    final_projection: BatterySOCHorizonProjection
    final_soc_evaluation: BatterySOCHorizonConstraintEvaluation
    final_power_evaluation: BatteryPowerHorizonConstraintEvaluation
    final_constraint_evaluation: BatteryHorizonConstraintEvaluation

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, PhysicallyAwareBaselineOptimizationInput):
            raise TypeError(
                "source_input must be a PhysicallyAwareBaselineOptimizationInput"
            )
        if not isinstance(self.candidate_output, OptimizationSolveOutput):
            raise TypeError("candidate_output must be an OptimizationSolveOutput")
        if not isinstance(self.final_output, OptimizationSolveOutput):
            raise TypeError("final_output must be an OptimizationSolveOutput")
        problem = self.source_input.battery_input.problem
        if self.candidate_output.result.source_problem is not problem:
            raise ValueError(
                "candidate output must preserve exact input problem identity"
            )
        if self.final_output.result.source_problem is not problem:
            raise ValueError("final output must preserve exact input problem identity")
        self._validate_evidence(
            self.candidate_output.solution,
            self.candidate_projection,
            self.candidate_soc_evaluation,
            self.candidate_power_evaluation,
            self.candidate_constraint_evaluation,
            "candidate",
        )
        if not isinstance(self.revision, BatterySolutionRevision):
            raise TypeError("revision must be a BatterySolutionRevision")
        if (
            self.revision.source_candidate_solution
            is not self.candidate_output.solution
        ):
            raise ValueError("revision must preserve exact candidate solution identity")
        if self.revision.revised_solution is not self.final_output.solution:
            raise ValueError("revision must preserve exact final solution identity")
        self._validate_evidence(
            self.final_output.solution,
            self.final_projection,
            self.final_soc_evaluation,
            self.final_power_evaluation,
            self.final_constraint_evaluation,
            "final",
        )
        if self.final_output.result.outcome != self.candidate_output.result.outcome:
            raise ValueError(
                "final output must preserve the candidate optimization outcome"
            )
        if self.candidate_output.result.outcome == "unavailable":
            if self.final_output.solution.steps:
                raise ValueError(
                    "unavailable output must not invent final solution steps"
                )
        elif not self.final_constraint_evaluation.feasible:
            raise ValueError(
                "final output must satisfy known battery horizon constraints"
            )

    def _validate_evidence(
        self,
        solution: OptimizationSolution,
        projection: BatterySOCHorizonProjection,
        soc_evaluation: BatterySOCHorizonConstraintEvaluation,
        power_evaluation: BatteryPowerHorizonConstraintEvaluation,
        aggregate: BatteryHorizonConstraintEvaluation,
        stage: str,
    ) -> None:
        if not isinstance(projection, BatterySOCHorizonProjection):
            raise TypeError(f"{stage}_projection must be a BatterySOCHorizonProjection")
        if projection.source_input.battery_input is not self.source_input.battery_input:
            raise ValueError(
                f"{stage} projection must preserve exact battery input identity"
            )
        if projection.source_input.solution is not solution:
            raise ValueError(
                f"{stage} projection must preserve exact solution identity"
            )
        if (
            projection.source_input.control_step_duration_seconds
            != self.source_input.control_step_duration_seconds
        ):
            raise ValueError(f"{stage} projection must preserve exact duration value")
        if not isinstance(soc_evaluation, BatterySOCHorizonConstraintEvaluation):
            raise TypeError(
                f"{stage}_soc_evaluation must be a "
                "BatterySOCHorizonConstraintEvaluation"
            )
        if soc_evaluation.source_input.projection is not projection:
            raise ValueError(
                f"{stage} SOC evaluation must preserve exact projection identity"
            )
        model = self.source_input.battery_input.battery_model
        if soc_evaluation.source_input.battery_model is not model:
            raise ValueError(
                f"{stage} SOC evaluation must preserve exact model identity"
            )
        if not isinstance(power_evaluation, BatteryPowerHorizonConstraintEvaluation):
            raise TypeError(
                f"{stage}_power_evaluation must be a "
                "BatteryPowerHorizonConstraintEvaluation"
            )
        if power_evaluation.source_input.solution is not solution:
            raise ValueError(
                f"{stage} power evaluation must preserve exact solution identity"
            )
        if power_evaluation.source_input.battery_model is not model:
            raise ValueError(
                f"{stage} power evaluation must preserve exact model identity"
            )
        if not isinstance(aggregate, BatteryHorizonConstraintEvaluation):
            raise TypeError(
                f"{stage}_constraint_evaluation must be a "
                "BatteryHorizonConstraintEvaluation"
            )
        if aggregate.source_input.soc_evaluation is not soc_evaluation:
            raise ValueError(f"{stage} aggregate must preserve exact SOC evaluation")
        if aggregate.source_input.power_evaluation is not power_evaluation:
            raise ValueError(f"{stage} aggregate must preserve exact power evaluation")


class PhysicallyAwareOptimizationBoundary(ABC):
    """Define one explicit candidate-evidence-revision-final horizon flow."""

    __slots__ = ()

    @abstractmethod
    def solve_physically(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> PhysicallyAwareOptimizationSolveOutput:
        """Return one fully evidenced physical revision without retries or execution."""
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class PhysicallyAwarePriceBaselineOptimizer(PhysicallyAwareOptimizationBoundary):
    """Perform exactly one deterministic physical revision of a price candidate."""

    price_optimizer: PriceAwareBaselineOptimizer
    soc_projector: BatterySOCHorizonProjectionBoundary
    soc_evaluator: BatterySOCHorizonConstraintBoundary
    power_evaluator: BatteryPowerHorizonConstraintBoundary
    constraint_aggregator: BatteryHorizonConstraintAggregateBoundary

    def __post_init__(self) -> None:
        if not isinstance(self.price_optimizer, PriceAwareBaselineOptimizer):
            raise TypeError("price_optimizer must be a PriceAwareBaselineOptimizer")
        if not isinstance(self.soc_projector, BatterySOCHorizonProjectionBoundary):
            raise TypeError(
                "soc_projector must be a BatterySOCHorizonProjectionBoundary"
            )
        if not isinstance(self.soc_evaluator, BatterySOCHorizonConstraintBoundary):
            raise TypeError(
                "soc_evaluator must be a BatterySOCHorizonConstraintBoundary"
            )
        if not isinstance(self.power_evaluator, BatteryPowerHorizonConstraintBoundary):
            raise TypeError(
                "power_evaluator must be a BatteryPowerHorizonConstraintBoundary"
            )
        if not isinstance(
            self.constraint_aggregator,
            BatteryHorizonConstraintAggregateBoundary,
        ):
            raise TypeError(
                "constraint_aggregator must be a "
                "BatteryHorizonConstraintAggregateBoundary"
            )

    def solve_physically(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> PhysicallyAwareOptimizationSolveOutput:
        if not isinstance(
            optimization_input,
            PhysicallyAwareBaselineOptimizationInput,
        ):
            raise TypeError(
                "optimization_input must be a PhysicallyAwareBaselineOptimizationInput"
            )
        candidate_output = self.price_optimizer.solve_with_solution(
            optimization_input.battery_input.problem
        )
        (
            candidate_projection,
            candidate_soc_evaluation,
            candidate_power_evaluation,
            candidate_constraint_evaluation,
        ) = self._evaluate_solution(optimization_input, candidate_output.solution)

        final_result = OptimizationResult(
            optimization_input.battery_input.problem,
            candidate_output.result.outcome,
        )
        revised_steps, revision_steps = self._revise_steps(
            optimization_input,
            candidate_output.solution,
        )
        final_solution = OptimizationSolution(final_result, revised_steps)
        revision = BatterySolutionRevision(
            candidate_output.solution,
            final_solution,
            revision_steps,
        )
        final_output = OptimizationSolveOutput(final_result, final_solution)
        (
            final_projection,
            final_soc_evaluation,
            final_power_evaluation,
            final_constraint_evaluation,
        ) = self._evaluate_solution(optimization_input, final_solution)
        return PhysicallyAwareOptimizationSolveOutput(
            optimization_input,
            candidate_output,
            candidate_projection,
            candidate_soc_evaluation,
            candidate_power_evaluation,
            candidate_constraint_evaluation,
            revision,
            final_output,
            final_projection,
            final_soc_evaluation,
            final_power_evaluation,
            final_constraint_evaluation,
        )

    def _evaluate_solution(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
        solution: OptimizationSolution,
    ) -> tuple[
        BatterySOCHorizonProjection,
        BatterySOCHorizonConstraintEvaluation,
        BatteryPowerHorizonConstraintEvaluation,
        BatteryHorizonConstraintEvaluation,
    ]:
        battery_input = optimization_input.battery_input
        projection = self.soc_projector.project(
            BatterySOCHorizonProjectionInput(
                battery_input,
                solution,
                optimization_input.control_step_duration_seconds,
            )
        )
        soc_evaluation = self.soc_evaluator.evaluate(
            BatterySOCHorizonConstraintInput(projection, battery_input.battery_model)
        )
        power_evaluation = self.power_evaluator.evaluate(
            BatteryPowerHorizonConstraintInput(solution, battery_input.battery_model)
        )
        aggregate = self.constraint_aggregator.aggregate(
            BatteryHorizonConstraintInput(soc_evaluation, power_evaluation)
        )
        return projection, soc_evaluation, power_evaluation, aggregate

    def _revise_steps(
        self,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
        candidate_solution: OptimizationSolution,
    ) -> tuple[
        tuple[OptimizationSolutionStep, ...],
        tuple[BatterySolutionRevisionStep, ...],
    ]:
        duration_hours = optimization_input.control_step_duration_seconds / 3600.0
        current_soc = optimization_input.battery_input.battery_state.soc_fraction
        revised_steps: list[OptimizationSolutionStep] = []
        evidence: list[BatterySolutionRevisionStep] = []
        for index, candidate_step in enumerate(candidate_solution.steps):
            revised_intent, allowed_power, reasons = self._revise_step(
                candidate_step,
                current_soc,
                duration_hours,
                optimization_input,
            )
            revised_step = OptimizationSolutionStep(
                candidate_step.timestamp,
                DecisionIntent(revised_intent),
                allowed_power,
            )
            revised_steps.append(revised_step)
            evidence.append(
                BatterySolutionRevisionStep(
                    candidate_step,
                    revised_step,
                    index,
                    reasons,
                )
            )
            current_soc = self._next_soc(
                current_soc,
                revised_step,
                duration_hours,
                optimization_input,
            )
        return tuple(revised_steps), tuple(evidence)

    @staticmethod
    def _revise_step(
        candidate_step: OptimizationSolutionStep,
        current_soc: float,
        duration_hours: float,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> tuple[
        Literal["charge", "discharge", "idle"],
        float,
        tuple[BatterySolutionRevisionReason, ...],
    ]:
        model = optimization_input.battery_input.battery_model
        requested = candidate_step.requested_power_kw
        if candidate_step.intent.action == "idle":
            return "idle", 0.0, ()
        if candidate_step.intent.action == "charge":
            soc_limit = (
                (model.max_soc_fraction - current_soc)
                * model.usable_capacity_kwh
                / (duration_hours * model.charge_efficiency)
            )
            power_limit = model.max_charge_power_kw
            reason_order = _CHARGE_REASONS
        else:
            soc_limit = (
                (current_soc - model.min_soc_fraction)
                * model.usable_capacity_kwh
                * model.discharge_efficiency
                / duration_hours
            )
            power_limit = model.max_discharge_power_kw
            reason_order = _DISCHARGE_REASONS
        allowed_power = max(0.0, min(requested, power_limit, soc_limit))
        # A one-ULP inward adjustment is only used when the SOC bound actually
        # constrained this step, so strict TASK-118 comparisons stay reliable.
        if soc_limit < requested and allowed_power == soc_limit and allowed_power > 0:
            allowed_power = nextafter(allowed_power, 0.0)
        reasons: list[BatterySolutionRevisionReason] = []
        if requested > power_limit:
            reasons.append(reason_order[0])
        if soc_limit < requested:
            reasons.append(reason_order[1])
        action = candidate_step.intent.action if allowed_power > 0 else "idle"
        return action, allowed_power, tuple(reasons)

    @staticmethod
    def _next_soc(
        current_soc: float,
        revised_step: OptimizationSolutionStep,
        duration_hours: float,
        optimization_input: PhysicallyAwareBaselineOptimizationInput,
    ) -> float:
        model = optimization_input.battery_input.battery_model
        if revised_step.intent.action == "charge":
            energy_delta = (
                revised_step.requested_power_kw
                * duration_hours
                * model.charge_efficiency
            )
        elif revised_step.intent.action == "discharge":
            energy_delta = -(
                revised_step.requested_power_kw
                * duration_hours
                / model.discharge_efficiency
            )
        else:
            energy_delta = 0.0
        return current_soc + energy_delta / model.usable_capacity_kwh
