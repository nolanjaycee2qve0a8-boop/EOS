# ruff: noqa: E501
"""Explain differences between two completed TASK-168 economic outcomes.

The core explainer consumes final evidence only.  It never recalculates import
cost, export revenue, degradation, terminal value, or any control trajectory.
"""

import argparse
import csv
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from io import StringIO
from math import isclose, isfinite
from pathlib import Path

from optimization import ExtendedEconomicOutcomeEvidence

_RECONCILIATION_ABSOLUTE_TOLERANCE = 1e-12


class EconomicComparisonRanking(StrEnum):
    """Stable ranking of the candidate against the reference accounting path."""

    CANDIDATE_BETTER = "candidate_better"
    REFERENCE_BETTER = "reference_better"
    TIED = "tied"


class EconomicComparisonComponent(StrEnum):
    """One signed adjusted-cost contribution in a comparison decomposition."""

    IMPORT_COST = "import_cost"
    EXPORT_REVENUE = "export_revenue"
    DEGRADATION_COST = "degradation_cost"
    TERMINAL_VALUE = "terminal_value"
    NONE = "none"


_COMPONENT_ORDER = (
    EconomicComparisonComponent.IMPORT_COST,
    EconomicComparisonComponent.EXPORT_REVENUE,
    EconomicComparisonComponent.DEGRADATION_COST,
    EconomicComparisonComponent.TERMINAL_VALUE,
)


def _require_name(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")
    return value


def _require_optional_label(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_name(value, field_name)


def _require_finite(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError(f"{field_name} must be a number")
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{field_name} must be finite")
    return normalized


@dataclass(frozen=True, slots=True)
class EconomicComparisonInput:
    """Caller-owned pair of completed TASK-168 outcomes to compare."""

    reference_path_name: str
    candidate_path_name: str
    reference_outcome: ExtendedEconomicOutcomeEvidence
    candidate_outcome: ExtendedEconomicOutcomeEvidence
    scenario_id: str | None = None
    accounting_basis_label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reference_path_name",
            _require_name(self.reference_path_name, "reference_path_name"),
        )
        object.__setattr__(
            self,
            "candidate_path_name",
            _require_name(self.candidate_path_name, "candidate_path_name"),
        )
        if not isinstance(self.reference_outcome, ExtendedEconomicOutcomeEvidence):
            raise TypeError("reference_outcome must be ExtendedEconomicOutcomeEvidence")
        if not isinstance(self.candidate_outcome, ExtendedEconomicOutcomeEvidence):
            raise TypeError("candidate_outcome must be ExtendedEconomicOutcomeEvidence")
        object.__setattr__(
            self,
            "scenario_id",
            _require_optional_label(self.scenario_id, "scenario_id"),
        )
        object.__setattr__(
            self,
            "accounting_basis_label",
            _require_optional_label(
                self.accounting_basis_label,
                "accounting_basis_label",
            ),
        )


@dataclass(frozen=True, slots=True)
class EconomicComparisonExplanation:
    """Exact evidence pair, component deltas, contributions, and ranking."""

    source_input: EconomicComparisonInput
    reference_outcome: ExtendedEconomicOutcomeEvidence
    candidate_outcome: ExtendedEconomicOutcomeEvidence
    reference_realized_import_cost: float
    reference_realized_export_revenue: float
    reference_battery_degradation_cost: float
    reference_terminal_energy_value: float
    reference_adjusted_net_economic_cost: float
    candidate_realized_import_cost: float
    candidate_realized_export_revenue: float
    candidate_battery_degradation_cost: float
    candidate_terminal_energy_value: float
    candidate_adjusted_net_economic_cost: float
    delta_import_cost: float
    delta_export_revenue: float
    delta_degradation_cost: float
    delta_terminal_value: float
    delta_adjusted_cost: float
    import_cost_contribution: float
    export_revenue_contribution: float
    degradation_cost_contribution: float
    terminal_value_contribution: float
    ranking: EconomicComparisonRanking
    dominant_component: EconomicComparisonComponent
    dominant_components: tuple[EconomicComparisonComponent, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_input, EconomicComparisonInput):
            raise TypeError("source_input must be EconomicComparisonInput")
        if self.reference_outcome is not self.source_input.reference_outcome:
            raise ValueError("reference_outcome must preserve exact input identity")
        if self.candidate_outcome is not self.source_input.candidate_outcome:
            raise ValueError("candidate_outcome must preserve exact input identity")
        if not isinstance(self.ranking, EconomicComparisonRanking):
            raise TypeError("ranking must be EconomicComparisonRanking")
        if not isinstance(self.dominant_component, EconomicComparisonComponent):
            raise TypeError("dominant_component must be EconomicComparisonComponent")
        if not isinstance(self.dominant_components, tuple):
            raise TypeError("dominant_components must be a tuple")
        if any(
            not isinstance(component, EconomicComparisonComponent)
            for component in self.dominant_components
        ):
            raise TypeError(
                "dominant_components must contain EconomicComparisonComponent"
            )
        if EconomicComparisonComponent.NONE in self.dominant_components:
            raise ValueError("dominant_components must not contain NONE")
        for field_name in (
            "reference_realized_import_cost",
            "reference_realized_export_revenue",
            "reference_battery_degradation_cost",
            "reference_terminal_energy_value",
            "reference_adjusted_net_economic_cost",
            "candidate_realized_import_cost",
            "candidate_realized_export_revenue",
            "candidate_battery_degradation_cost",
            "candidate_terminal_energy_value",
            "candidate_adjusted_net_economic_cost",
            "delta_import_cost",
            "delta_export_revenue",
            "delta_degradation_cost",
            "delta_terminal_value",
            "delta_adjusted_cost",
            "import_cost_contribution",
            "export_revenue_contribution",
            "degradation_cost_contribution",
            "terminal_value_contribution",
        ):
            object.__setattr__(
                self,
                field_name,
                _require_finite(getattr(self, field_name), field_name),
            )
        _validate_outcome_values(self)
        _validate_decomposition(self)
        _validate_ranking(self)
        _validate_dominance(self)


class EconomicComparisonBoundary(ABC):
    """Define a stateless final-outcome comparison seam."""

    __slots__ = ()

    @abstractmethod
    def explain(
        self,
        comparison_input: EconomicComparisonInput,
    ) -> EconomicComparisonExplanation:
        """Compare supplied final evidence only."""
        raise NotImplementedError


class DeterministicEconomicComparisonExplainer(EconomicComparisonBoundary):
    """Deterministically decompose candidate minus reference adjusted cost."""

    __slots__ = ()

    def explain(
        self,
        comparison_input: EconomicComparisonInput,
    ) -> EconomicComparisonExplanation:
        if not isinstance(comparison_input, EconomicComparisonInput):
            raise TypeError("comparison_input must be EconomicComparisonInput")
        reference = comparison_input.reference_outcome
        candidate = comparison_input.candidate_outcome
        delta_import = _normalize_near_zero(
            candidate.realized_import_cost - reference.realized_import_cost
        )
        delta_export = _normalize_near_zero(
            candidate.realized_export_revenue - reference.realized_export_revenue
        )
        delta_degradation = _normalize_near_zero(
            candidate.battery_degradation_cost - reference.battery_degradation_cost
        )
        delta_terminal = _normalize_near_zero(
            candidate.terminal_energy_value - reference.terminal_energy_value
        )
        delta_adjusted = _normalize_near_zero(
            candidate.adjusted_net_economic_cost - reference.adjusted_net_economic_cost
        )
        import_contribution = delta_import
        export_contribution = _normalize_near_zero(-delta_export)
        degradation_contribution = delta_degradation
        terminal_contribution = _normalize_near_zero(-delta_terminal)
        contributions = {
            EconomicComparisonComponent.IMPORT_COST: import_contribution,
            EconomicComparisonComponent.EXPORT_REVENUE: export_contribution,
            EconomicComparisonComponent.DEGRADATION_COST: degradation_contribution,
            EconomicComparisonComponent.TERMINAL_VALUE: terminal_contribution,
        }
        dominant_components = _dominant_components(contributions)
        dominant_component = (
            dominant_components[0]
            if len(dominant_components) == 1
            else EconomicComparisonComponent.NONE
        )
        return EconomicComparisonExplanation(
            comparison_input,
            reference,
            candidate,
            reference.realized_import_cost,
            reference.realized_export_revenue,
            reference.battery_degradation_cost,
            reference.terminal_energy_value,
            reference.adjusted_net_economic_cost,
            candidate.realized_import_cost,
            candidate.realized_export_revenue,
            candidate.battery_degradation_cost,
            candidate.terminal_energy_value,
            candidate.adjusted_net_economic_cost,
            delta_import,
            delta_export,
            delta_degradation,
            delta_terminal,
            delta_adjusted,
            import_contribution,
            export_contribution,
            degradation_contribution,
            terminal_contribution,
            _ranking(delta_adjusted),
            dominant_component,
            dominant_components,
        )


def _validate_outcome_values(explanation: EconomicComparisonExplanation) -> None:
    reference = explanation.reference_outcome
    candidate = explanation.candidate_outcome
    expected = (
        explanation.reference_realized_import_cost,
        explanation.reference_realized_export_revenue,
        explanation.reference_battery_degradation_cost,
        explanation.reference_terminal_energy_value,
        explanation.reference_adjusted_net_economic_cost,
        explanation.candidate_realized_import_cost,
        explanation.candidate_realized_export_revenue,
        explanation.candidate_battery_degradation_cost,
        explanation.candidate_terminal_energy_value,
        explanation.candidate_adjusted_net_economic_cost,
    )
    actual = (
        reference.realized_import_cost,
        reference.realized_export_revenue,
        reference.battery_degradation_cost,
        reference.terminal_energy_value,
        reference.adjusted_net_economic_cost,
        candidate.realized_import_cost,
        candidate.realized_export_revenue,
        candidate.battery_degradation_cost,
        candidate.terminal_energy_value,
        candidate.adjusted_net_economic_cost,
    )
    if expected != actual:
        raise ValueError("component values must preserve exact outcome semantics")


def _validate_decomposition(explanation: EconomicComparisonExplanation) -> None:
    if not isclose(
        explanation.delta_adjusted_cost,
        explanation.candidate_adjusted_net_economic_cost
        - explanation.reference_adjusted_net_economic_cost,
        rel_tol=0.0,
        abs_tol=_RECONCILIATION_ABSOLUTE_TOLERANCE,
    ):
        raise ValueError("delta_adjusted_cost must preserve exact outcome difference")
    if explanation.import_cost_contribution != explanation.delta_import_cost:
        raise ValueError("import_cost_contribution must equal delta_import_cost")
    if explanation.export_revenue_contribution != -explanation.delta_export_revenue:
        raise ValueError("export_revenue_contribution must negate delta_export_revenue")
    if explanation.degradation_cost_contribution != explanation.delta_degradation_cost:
        raise ValueError(
            "degradation_cost_contribution must equal delta_degradation_cost"
        )
    if explanation.terminal_value_contribution != -explanation.delta_terminal_value:
        raise ValueError("terminal_value_contribution must negate delta_terminal_value")
    contribution_total = (
        explanation.import_cost_contribution
        + explanation.export_revenue_contribution
        + explanation.degradation_cost_contribution
        + explanation.terminal_value_contribution
    )
    if not isclose(
        explanation.delta_adjusted_cost,
        contribution_total,
        rel_tol=0.0,
        abs_tol=_RECONCILIATION_ABSOLUTE_TOLERANCE,
    ):
        raise ValueError("component contributions must reconcile with adjusted delta")


def _validate_ranking(explanation: EconomicComparisonExplanation) -> None:
    if explanation.ranking is not _ranking(explanation.delta_adjusted_cost):
        raise ValueError("ranking must follow adjusted cost delta sign")


def _validate_dominance(explanation: EconomicComparisonExplanation) -> None:
    contributions = {
        EconomicComparisonComponent.IMPORT_COST: explanation.import_cost_contribution,
        EconomicComparisonComponent.EXPORT_REVENUE: explanation.export_revenue_contribution,
        EconomicComparisonComponent.DEGRADATION_COST: explanation.degradation_cost_contribution,
        EconomicComparisonComponent.TERMINAL_VALUE: explanation.terminal_value_contribution,
    }
    expected_components = _dominant_components(contributions)
    if explanation.dominant_components != expected_components:
        raise ValueError(
            "dominant_components must retain all exact ties in stable order"
        )
    expected_component = (
        expected_components[0]
        if len(expected_components) == 1
        else EconomicComparisonComponent.NONE
    )
    if explanation.dominant_component is not expected_component:
        raise ValueError("dominant_component must be NONE for no or tied dominance")


def _ranking(delta_adjusted_cost: float) -> EconomicComparisonRanking:
    if delta_adjusted_cost < 0.0:
        return EconomicComparisonRanking.CANDIDATE_BETTER
    if delta_adjusted_cost > 0.0:
        return EconomicComparisonRanking.REFERENCE_BETTER
    return EconomicComparisonRanking.TIED


def _normalize_near_zero(value: float) -> float:
    """Remove only sub-tolerance arithmetic residue from displayed evidence."""

    return (
        0.0
        if isclose(
            value,
            0.0,
            rel_tol=0.0,
            abs_tol=_RECONCILIATION_ABSOLUTE_TOLERANCE,
        )
        else value
    )


def _dominant_components(
    contributions: dict[EconomicComparisonComponent, float],
) -> tuple[EconomicComparisonComponent, ...]:
    maximum = max(abs(value) for value in contributions.values())
    if maximum == 0.0:
        return ()
    return tuple(
        component
        for component in _COMPONENT_ORDER
        if abs(contributions[component]) == maximum
    )


def format_economic_comparison_explanation(
    explanation: EconomicComparisonExplanation,
) -> str:
    """Return deterministic, accounting-basis-only human-readable text."""

    if not isinstance(explanation, EconomicComparisonExplanation):
        raise TypeError("explanation must be EconomicComparisonExplanation")
    source = explanation.source_input
    candidate = source.candidate_path_name
    reference = source.reference_path_name
    header = _summary_sentence(explanation)
    scenario = f"Scenario: {source.scenario_id}\n" if source.scenario_id else ""
    basis = (
        f"Accounting basis: {source.accounting_basis_label}\n"
        if source.accounting_basis_label
        else ""
    )
    component_lines = "\n\n".join(
        _component_text(
            component,
            _component_contribution(explanation, component),
            candidate,
        )
        for component in _COMPONENT_ORDER
    )
    return (
        f"{scenario}{basis}{header}\n\n"
        f"Component contributions to {candidate} - {reference}:\n\n"
        f"{component_lines}\n\n"
        f"Net: {_number(explanation.delta_adjusted_cost)}\n\n"
        f"Dominant factor: {_dominant_text(explanation, candidate)}\n"
    )


def _summary_sentence(explanation: EconomicComparisonExplanation) -> str:
    candidate = explanation.source_input.candidate_path_name
    reference = explanation.source_input.reference_path_name
    amount = _number(abs(explanation.delta_adjusted_cost))
    if explanation.ranking is EconomicComparisonRanking.CANDIDATE_BETTER:
        return f"{candidate} is better than {reference} by {amount} currency under this accounting basis."
    if explanation.ranking is EconomicComparisonRanking.REFERENCE_BETTER:
        return f"{reference} is better than {candidate} by {amount} currency under this accounting basis."
    return f"{candidate} and {reference} are tied under this accounting basis."


def _component_contribution(
    explanation: EconomicComparisonExplanation,
    component: EconomicComparisonComponent,
) -> float:
    return {
        EconomicComparisonComponent.IMPORT_COST: explanation.import_cost_contribution,
        EconomicComparisonComponent.EXPORT_REVENUE: explanation.export_revenue_contribution,
        EconomicComparisonComponent.DEGRADATION_COST: explanation.degradation_cost_contribution,
        EconomicComparisonComponent.TERMINAL_VALUE: explanation.terminal_value_contribution,
    }[component]


def _component_text(
    component: EconomicComparisonComponent,
    contribution: float,
    candidate: str,
) -> str:
    label = {
        EconomicComparisonComponent.IMPORT_COST: "Import cost",
        EconomicComparisonComponent.EXPORT_REVENUE: "Export revenue",
        EconomicComparisonComponent.DEGRADATION_COST: "Battery degradation",
        EconomicComparisonComponent.TERMINAL_VALUE: "Terminal value",
    }[component]
    return f"{label}:\n  {_signed_number(contribution)}\n  {_component_effect(component, contribution, candidate)}"


def _component_effect(
    component: EconomicComparisonComponent,
    contribution: float,
    candidate: str,
) -> str:
    if contribution == 0.0:
        return f"Neutral for {candidate}."
    helpful = contribution < 0.0
    if component is EconomicComparisonComponent.IMPORT_COST:
        return (
            f"{'Lower' if helpful else 'Higher'} import cost "
            f"{'helps' if helpful else 'hurts'} {candidate}."
        )
    if component is EconomicComparisonComponent.EXPORT_REVENUE:
        return (
            f"{'Higher' if helpful else 'Lower'} export revenue "
            f"{'helps' if helpful else 'hurts'} {candidate}."
        )
    if component is EconomicComparisonComponent.DEGRADATION_COST:
        return (
            f"{'Lower' if helpful else 'Higher'} degradation cost "
            f"{'helps' if helpful else 'hurts'} {candidate}."
        )
    return (
        f"{'Higher' if helpful else 'Lower'} terminal value "
        f"{'helps' if helpful else 'hurts'} {candidate}."
    )


def _dominant_text(
    explanation: EconomicComparisonExplanation,
    candidate: str,
) -> str:
    if not explanation.dominant_components:
        return "No non-zero component contribution."
    if len(explanation.dominant_components) > 1:
        labels = ", ".join(
            component.value for component in explanation.dominant_components
        )
        return f"Exact tie between {labels}."
    component = explanation.dominant_component
    contribution = _component_contribution(explanation, component)
    return _component_effect(component, contribution, candidate).rstrip(".") + "."


def comparison_summary_csv(
    explanations: Iterable[EconomicComparisonExplanation],
) -> str:
    """Serialize completed comparison explanations with deterministic columns."""

    values = tuple(explanations)
    if any(not isinstance(value, EconomicComparisonExplanation) for value in values):
        raise TypeError("explanations must contain EconomicComparisonExplanation")
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        (
            "scenario_id",
            "reference_path",
            "candidate_path",
            "ranking",
            "reference_adjusted_cost",
            "candidate_adjusted_cost",
            "delta_adjusted_cost",
            "delta_import_cost",
            "delta_export_revenue",
            "delta_degradation_cost",
            "delta_terminal_value",
            "import_cost_contribution",
            "export_revenue_contribution",
            "degradation_cost_contribution",
            "terminal_value_contribution",
            "dominant_component",
            "dominant_components",
        )
    )
    for explanation in values:
        source = explanation.source_input
        writer.writerow(
            (
                source.scenario_id or "",
                source.reference_path_name,
                source.candidate_path_name,
                explanation.ranking.value,
                *(
                    _number(value)
                    for value in (
                        explanation.reference_adjusted_net_economic_cost,
                        explanation.candidate_adjusted_net_economic_cost,
                        explanation.delta_adjusted_cost,
                        explanation.delta_import_cost,
                        explanation.delta_export_revenue,
                        explanation.delta_degradation_cost,
                        explanation.delta_terminal_value,
                        explanation.import_cost_contribution,
                        explanation.export_revenue_contribution,
                        explanation.degradation_cost_contribution,
                        explanation.terminal_value_contribution,
                    )
                ),
                explanation.dominant_component.value,
                "|".join(
                    component.value for component in explanation.dominant_components
                ),
            )
        )
    return stream.getvalue()


def comparison_explanations_text(
    explanations: Iterable[EconomicComparisonExplanation],
) -> str:
    """Serialize human-readable explanations in caller-supplied stable order."""

    values = tuple(explanations)
    if any(not isinstance(value, EconomicComparisonExplanation) for value in values):
        raise TypeError("explanations must contain EconomicComparisonExplanation")
    return "\n---\n".join(
        format_economic_comparison_explanation(value) for value in values
    )


def write_economic_comparison_outputs(
    explanations: Iterable[EconomicComparisonExplanation],
    output_directory: Path,
) -> tuple[Path, Path]:
    """Write comparison read-model output; no evidence or trajectory is recomputed."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    values = tuple(explanations)
    output_directory.mkdir(parents=True, exist_ok=True)
    summary_path = output_directory / "economic_comparison_summary.csv"
    text_path = output_directory / "economic_comparison_explanations.txt"
    summary_path.write_text(
        comparison_summary_csv(values), encoding="utf-8", newline=""
    )
    text_path.write_text(
        comparison_explanations_text(values),
        encoding="utf-8",
        newline="",
    )
    return summary_path, text_path


def _task172_baseline_explanations(
    output_directory: Path,
) -> tuple[EconomicComparisonExplanation, ...]:
    """Materialize reference samples outside the pure comparison boundary.

    This CLI adapter asks the pre-existing TASK-172 runner for completed
    baseline outcomes.  The explainer itself only receives those final outcome
    objects and never runs a controller or an accounting calculator.
    """

    from ems_simulator.extended_economic_re_evaluation import (
        run_extended_economic_re_evaluation,
    )

    task172 = run_extended_economic_re_evaluation(output_directory / "task172_source")
    baseline = tuple(
        evaluation
        for evaluation in task172.evaluations
        if (
            evaluation.export_revenue_evidence.export_tariff_per_kwh == 0.20
            and evaluation.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
            == 0.05
            and evaluation.terminal_energy_value_evidence.valuation_import_price == 0.85
        )
    )
    by_scenario_and_path = {
        (evaluation.fixed_path.scenario_id, evaluation.fixed_path.path): evaluation
        for evaluation in baseline
    }
    explainer = DeterministicEconomicComparisonExplainer()
    scenario_order = ("E0", "E1", "E2", "C_TERMINAL_SOC_DIVERGENCE")
    return tuple(
        explainer.explain(
            EconomicComparisonInput(
                "Schedule",
                "Economic",
                by_scenario_and_path[
                    (scenario_id, "Schedule")
                ].extended_outcome_evidence,
                by_scenario_and_path[
                    (scenario_id, "Economic")
                ].extended_outcome_evidence,
                scenario_id,
                "TASK-172 baseline extended accounting",
            )
        )
        for scenario_id in scenario_order
    )


def _number(value: float) -> str:
    return f"{value:.6f}"


def _signed_number(value: float) -> str:
    return f"{value:+.6f}"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS TASK-174 economic comparison explanation"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("simulation_output_task174_economic_explanation"),
    )
    arguments = parser.parse_args(argv)
    explanations = _task172_baseline_explanations(arguments.output_dir)
    summary_path, text_path = write_economic_comparison_outputs(
        explanations,
        arguments.output_dir,
    )
    print(summary_path)
    print(text_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
