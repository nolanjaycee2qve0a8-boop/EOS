"""TASK-176 Residential EMS acceptance framework tests."""

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from ems_simulator.residential_acceptance import (
    DeterministicResidentialAcceptanceEvaluator,
    ResidentialAcceptanceCategory,
    ResidentialAcceptanceFinding,
    ResidentialAcceptanceKPI,
    ResidentialAcceptanceScenario,
    ResidentialAcceptanceSeverity,
    ResidentialAcceptanceStatus,
    ResidentialCampaignReadiness,
    _readiness,
    run_residential_acceptance,
)


def _scenario() -> ResidentialAcceptanceScenario:
    return ResidentialAcceptanceScenario(
        "TEST",
        "Synthetic acceptance evidence",
        "export_allowed",
        "Test-only acceptance evidence; no control path is executed.",
    )


def _kpi(
    *,
    min_soc_violation_count: int = 0,
    max_soc_violation_count: int = 0,
    charge_power_violation_count: int = 0,
    discharge_power_violation_count: int = 0,
    energy_balance_violation_count: int = 0,
    actual_feedback_used: bool = True,
    ledger_reconciled: bool = True,
    comparison_reconciled: bool = True,
    provenance_complete: bool = True,
    fixed_control_preserved: bool = True,
) -> ResidentialAcceptanceKPI:
    return ResidentialAcceptanceKPI(
        "TEST",
        "Economic",
        1.0,
        1.0,
        0.0,
        0.0,
        0.0,
        0.5,
        0,
        0,
        1,
        0,
        0,
        0.0,
        0.0,
        0.0,
        0.0,
        0.0,
        min_soc_violation_count,
        max_soc_violation_count,
        charge_power_violation_count,
        discharge_power_violation_count,
        energy_balance_violation_count,
        0,
        0,
        actual_feedback_used,
        ledger_reconciled,
        comparison_reconciled,
        provenance_complete,
        fixed_control_preserved,
    )


@pytest.mark.parametrize(
    "field",
    (
        "min_soc_violation_count",
        "max_soc_violation_count",
        "charge_power_violation_count",
        "discharge_power_violation_count",
        "energy_balance_violation_count",
    ),
)
def test_hard_physical_kpi_violation_becomes_blocker(field: str) -> None:
    kpis = {
        "min_soc_violation_count": _kpi(min_soc_violation_count=1),
        "max_soc_violation_count": _kpi(max_soc_violation_count=1),
        "charge_power_violation_count": _kpi(charge_power_violation_count=1),
        "discharge_power_violation_count": _kpi(discharge_power_violation_count=1),
        "energy_balance_violation_count": _kpi(energy_balance_violation_count=1),
    }
    criteria = {
        "min_soc_violation_count": "minimum_soc",
        "max_soc_violation_count": "maximum_soc",
        "charge_power_violation_count": "charge_power",
        "discharge_power_violation_count": "discharge_power",
        "energy_balance_violation_count": "energy_balance",
    }
    result = DeterministicResidentialAcceptanceEvaluator().evaluate(
        _scenario(), kpis[field]
    )
    finding = next(
        item for item in result.findings if item.criterion_id == criteria[field]
    )

    assert finding.status is ResidentialAcceptanceStatus.FAIL
    assert finding.severity is ResidentialAcceptanceSeverity.BLOCKER


@pytest.mark.parametrize(
    "field",
    (
        "ledger_reconciled",
        "comparison_reconciled",
        "actual_feedback_used",
        "fixed_control_preserved",
    ),
)
def test_accounting_or_control_bypass_becomes_blocker(field: str) -> None:
    kpis = {
        "ledger_reconciled": _kpi(ledger_reconciled=False),
        "comparison_reconciled": _kpi(comparison_reconciled=False),
        "actual_feedback_used": _kpi(actual_feedback_used=False),
        "fixed_control_preserved": _kpi(fixed_control_preserved=False),
    }
    result = DeterministicResidentialAcceptanceEvaluator().evaluate(
        _scenario(), kpis[field]
    )

    assert any(
        finding.status is ResidentialAcceptanceStatus.FAIL
        and finding.severity is ResidentialAcceptanceSeverity.BLOCKER
        for finding in result.findings
    )


def test_missing_provenance_becomes_major_and_blocks_readiness() -> None:
    result = DeterministicResidentialAcceptanceEvaluator().evaluate(
        _scenario(), _kpi(provenance_complete=False)
    )

    provenance = next(
        item for item in result.findings if item.criterion_id == "provenance"
    )
    assert provenance.status is ResidentialAcceptanceStatus.FAIL
    assert provenance.severity is ResidentialAcceptanceSeverity.MAJOR
    assert (
        _readiness((result,))
        is ResidentialCampaignReadiness.NOT_READY_FOR_SIMULATION_CAMPAIGN
    )


def test_informational_finding_does_not_block_readiness() -> None:
    finding = ResidentialAcceptanceFinding(
        "TEST",
        ResidentialAcceptanceCategory.QUALITY_METRIC,
        "quality_observation",
        ResidentialAcceptanceSeverity.INFORMATIONAL,
        ResidentialAcceptanceStatus.FAIL,
        "informational only",
        "observed",
        "does not block",
    )
    result = DeterministicResidentialAcceptanceEvaluator().evaluate(
        _scenario(), _kpi(), (finding,)
    )

    assert (
        _readiness((result,))
        is ResidentialCampaignReadiness.READY_FOR_SIMULATION_CAMPAIGN
    )


def test_contract_is_frozen_and_slotted() -> None:
    kpi = _kpi()

    assert not hasattr(kpi, "__dict__")
    with pytest.raises(FrozenInstanceError):
        cast(Any, kpi).path = "Schedule"


def test_full_reference_suite_passes_and_writes_required_deterministic_outputs(
    tmp_path: Path,
) -> None:
    first = run_residential_acceptance(tmp_path / "first")
    second = run_residential_acceptance(tmp_path / "second")

    assert first.readiness is ResidentialCampaignReadiness.READY_FOR_SIMULATION_CAMPAIGN
    assert all(result.passed for result in first.results)
    assert {result.scenario.scenario_id for result in first.results} == {
        "A1",
        "A2",
        "A3",
        "A4",
        "A5",
        "A6",
        "A7",
        "A8",
        "A9",
        "A10",
    }
    first_outputs = (
        first.summary_csv_path,
        first.findings_csv_path,
        first.kpis_csv_path,
        first.report_path,
    )
    second_outputs = (
        second.summary_csv_path,
        second.findings_csv_path,
        second.kpis_csv_path,
        second.report_path,
    )
    assert all(path.is_file() for path in first_outputs)
    assert [path.read_bytes() for path in first_outputs] == [
        path.read_bytes() for path in second_outputs
    ]
    report = first.report_path.read_text(encoding="utf-8")
    assert "ready_for_simulation_campaign" in report
    assert "not a hardware readiness statement" in report
