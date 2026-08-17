"""TASK-174 completed-outcome economic comparison explanation tests."""

import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import Any, cast

import pytest

from ems_simulator.economic_comparison_explanation import (
    DeterministicEconomicComparisonExplainer,
    EconomicComparisonBoundary,
    EconomicComparisonComponent,
    EconomicComparisonExplanation,
    EconomicComparisonInput,
    EconomicComparisonRanking,
    comparison_explanations_text,
    comparison_summary_csv,
    format_economic_comparison_explanation,
    write_economic_comparison_outputs,
)
from ems_simulator.extended_economic_re_evaluation import (
    ExtendedEconomicEvaluation,
    ExtendedEconomicReEvaluationResult,
    run_extended_economic_re_evaluation,
)
from optimization import (
    BatteryOptimizationModel,
    DeterministicExtendedEconomicOutcomeCalculator,
    DeterministicTerminalEnergyValueCalculator,
    ExtendedEconomicOutcomeEvidence,
    ExtendedEconomicOutcomeInput,
    TerminalEnergyValueInput,
)

_MODEL = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)


def _outcome(
    import_cost: float = 10.0,
    export_revenue: float = 1.0,
    degradation_cost: float = 0.5,
    terminal_soc: float = 0.20,
) -> ExtendedEconomicOutcomeEvidence:
    terminal = DeterministicTerminalEnergyValueCalculator().calculate(
        TerminalEnergyValueInput(terminal_soc, _MODEL, 1.0)
    )
    return DeterministicExtendedEconomicOutcomeCalculator().calculate(
        ExtendedEconomicOutcomeInput(
            import_cost,
            export_revenue,
            degradation_cost,
            terminal,
        )
    )


def _explain(
    reference: ExtendedEconomicOutcomeEvidence | None = None,
    candidate: ExtendedEconomicOutcomeEvidence | None = None,
) -> EconomicComparisonExplanation:
    comparison_input = EconomicComparisonInput(
        "Schedule",
        "Economic",
        _outcome() if reference is None else reference,
        _outcome() if candidate is None else candidate,
        "TEST",
        "Limited extended accounting",
    )
    return DeterministicEconomicComparisonExplainer().explain(comparison_input)


def _baseline(
    result: ExtendedEconomicReEvaluationResult,
    scenario_id: str,
    path: str,
) -> ExtendedEconomicEvaluation:
    return next(
        evaluation
        for evaluation in result.evaluations
        if (
            evaluation.fixed_path.scenario_id == scenario_id
            and evaluation.fixed_path.path == path
            and evaluation.export_revenue_evidence.export_tariff_per_kwh == 0.20
            and (
                evaluation.battery_degradation_cost_evidence.degradation_cost_per_throughput_kwh
                == 0.05
            )
            and evaluation.terminal_energy_value_evidence.valuation_import_price == 0.85
        )
    )


def test_contracts_are_frozen_slotted_and_retain_exact_evidence_identity() -> None:
    reference = _outcome()
    candidate = _outcome(9.0)
    comparison_input = EconomicComparisonInput(
        "Schedule", "Economic", reference, candidate
    )
    explanation = DeterministicEconomicComparisonExplainer().explain(comparison_input)

    assert [field.name for field in fields(EconomicComparisonInput)] == [
        "reference_path_name",
        "candidate_path_name",
        "reference_outcome",
        "candidate_outcome",
        "scenario_id",
        "accounting_basis_label",
    ]
    assert explanation.source_input is comparison_input
    assert explanation.reference_outcome is reference
    assert explanation.candidate_outcome is candidate
    assert not hasattr(comparison_input, "__dict__")
    assert not hasattr(explanation, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, explanation).delta_adjusted_cost = 0.0


def test_tied_candidate_better_and_reference_better_rankings() -> None:
    tied = _explain()
    candidate_better = _explain(candidate=_outcome(9.0))
    reference_better = _explain(candidate=_outcome(11.0))

    assert tied.ranking is EconomicComparisonRanking.TIED
    assert tied.delta_adjusted_cost == 0.0
    assert candidate_better.ranking is EconomicComparisonRanking.CANDIDATE_BETTER
    assert candidate_better.delta_adjusted_cost == -1.0
    assert reference_better.ranking is EconomicComparisonRanking.REFERENCE_BETTER
    assert reference_better.delta_adjusted_cost == 1.0


@pytest.mark.parametrize(
    ("candidate", "component", "expected_contribution"),
    (
        (_outcome(9.0), EconomicComparisonComponent.IMPORT_COST, -1.0),
        (_outcome(10.0, 2.0), EconomicComparisonComponent.EXPORT_REVENUE, -1.0),
        (_outcome(10.0, 1.0, 0.0), EconomicComparisonComponent.DEGRADATION_COST, -0.5),
        (
            _outcome(10.0, 1.0, 0.5, 1.0),
            EconomicComparisonComponent.TERMINAL_VALUE,
            -7.6,
        ),
    ),
)
def test_individual_component_contribution_semantics(
    candidate: ExtendedEconomicOutcomeEvidence,
    component: EconomicComparisonComponent,
    expected_contribution: float,
) -> None:
    explanation = _explain(candidate=candidate)
    contributions = {
        EconomicComparisonComponent.IMPORT_COST: explanation.import_cost_contribution,
        EconomicComparisonComponent.EXPORT_REVENUE: (
            explanation.export_revenue_contribution
        ),
        EconomicComparisonComponent.DEGRADATION_COST: (
            explanation.degradation_cost_contribution
        ),
        EconomicComparisonComponent.TERMINAL_VALUE: (
            explanation.terminal_value_contribution
        ),
    }

    assert contributions[component] == pytest.approx(expected_contribution)
    assert explanation.dominant_component is component


def test_mixed_decomposition_reconciles_exact_outcome_difference() -> None:
    reference = _outcome(10.0, 1.0, 0.5, 1.0)
    candidate = _outcome(8.0, 0.5, 0.25, 0.20)
    explanation = _explain(reference, candidate)

    assert explanation.delta_import_cost == -2.0
    assert explanation.delta_export_revenue == -0.5
    assert explanation.delta_degradation_cost == -0.25
    assert explanation.delta_terminal_value == -7.6
    assert explanation.import_cost_contribution == -2.0
    assert explanation.export_revenue_contribution == 0.5
    assert explanation.degradation_cost_contribution == -0.25
    assert explanation.terminal_value_contribution == 7.6
    assert explanation.delta_adjusted_cost == pytest.approx(5.85)
    assert explanation.delta_adjusted_cost == pytest.approx(
        explanation.import_cost_contribution
        + explanation.export_revenue_contribution
        + explanation.degradation_cost_contribution
        + explanation.terminal_value_contribution
    )


def test_dominant_exact_tie_is_explicit_and_never_hidden() -> None:
    explanation = _explain(candidate=_outcome(9.0, 2.0))

    assert explanation.import_cost_contribution == -1.0
    assert explanation.export_revenue_contribution == -1.0
    assert explanation.dominant_component is EconomicComparisonComponent.NONE
    assert explanation.dominant_components == (
        EconomicComparisonComponent.IMPORT_COST,
        EconomicComparisonComponent.EXPORT_REVENUE,
    )
    assert (
        "Exact tie between import_cost, export_revenue."
        in format_economic_comparison_explanation(explanation)
    )


def test_formatter_and_csv_are_deterministic_and_accounting_clear(
    tmp_path: Path,
) -> None:
    explanation = _explain(candidate=_outcome(9.0, 0.5))
    first = format_economic_comparison_explanation(explanation)
    second = format_economic_comparison_explanation(explanation)
    summary = comparison_summary_csv((explanation,))
    explanations = comparison_explanations_text((explanation,))
    summary_path, text_path = write_economic_comparison_outputs(
        (explanation,), tmp_path
    )

    assert first == second == explanations
    assert "Economic is better than Schedule by 0.500000 currency" in first
    assert (
        "Export revenue:\n  +0.500000\n  Lower export revenue hurts Economic." in first
    )
    assert "profit" not in first.lower()
    assert summary.splitlines()[0].startswith(
        "scenario_id,reference_path,candidate_path"
    )
    assert summary_path.read_text(encoding="utf-8") == summary
    assert text_path.read_text(encoding="utf-8") == explanations


def test_task_172_e0_e1_and_terminal_soc_divergence_explanations(
    tmp_path: Path,
) -> None:
    evaluation = run_extended_economic_re_evaluation(tmp_path)

    def explain_scenario(scenario_id: str) -> EconomicComparisonExplanation:
        reference = _baseline(evaluation, scenario_id, "Schedule")
        candidate = _baseline(evaluation, scenario_id, "Economic")
        return DeterministicEconomicComparisonExplainer().explain(
            EconomicComparisonInput(
                "Schedule",
                "Economic",
                reference.extended_outcome_evidence,
                candidate.extended_outcome_evidence,
                scenario_id,
                "TASK-172 baseline extended accounting",
            )
        )

    e0 = explain_scenario("E0")
    e1 = explain_scenario("E1")
    terminal = explain_scenario("C_TERMINAL_SOC_DIVERGENCE")

    assert e0.ranking is EconomicComparisonRanking.TIED
    assert e0.delta_adjusted_cost == 0.0
    assert e1.ranking is EconomicComparisonRanking.CANDIDATE_BETTER
    assert e1.delta_import_cost == pytest.approx(-0.81795)
    assert e1.delta_export_revenue == pytest.approx(-0.2044876)
    assert e1.export_revenue_contribution == pytest.approx(0.2044876)
    assert e1.delta_adjusted_cost == pytest.approx(-0.6134624)
    assert e1.dominant_component is EconomicComparisonComponent.IMPORT_COST
    assert terminal.ranking is EconomicComparisonRanking.CANDIDATE_BETTER
    assert terminal.delta_import_cost == pytest.approx(-4.210526315789482)
    assert terminal.delta_degradation_cost == pytest.approx(-0.2631578947368421)
    assert terminal.delta_terminal_value == pytest.approx(-4.0375)
    assert terminal.terminal_value_contribution == pytest.approx(4.0375)
    assert terminal.delta_adjusted_cost == pytest.approx(-0.4361842105263247)
    text = format_economic_comparison_explanation(terminal)
    assert "Lower terminal value hurts Economic." in text
    assert "Lower import cost helps Economic." in text


def test_boundary_is_abstract_stateless_and_never_recalculates_components() -> None:
    source = Path("ems_simulator/economic_comparison_explanation.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    }
    explain_source = inspect.getsource(DeterministicEconomicComparisonExplainer.explain)

    assert inspect.isabstract(EconomicComparisonBoundary)
    assert EconomicComparisonBoundary.__slots__ == ()
    assert DeterministicEconomicComparisonExplainer.__slots__ == ()
    with pytest.raises(TypeError):
        cast(Any, EconomicComparisonBoundary)()
    assert not hasattr(DeterministicEconomicComparisonExplainer(), "__dict__")
    assert imports == {
        "abc",
        "argparse",
        "collections.abc",
        "csv",
        "dataclasses",
        "ems_simulator.extended_economic_re_evaluation",
        "enum",
        "io",
        "math",
        "optimization",
        "pathlib",
    }
    assert "Calculator" not in explain_source
    assert ".calculate(" not in explain_source
    assert "Simulator" not in explain_source
    assert "MPC" not in explain_source
