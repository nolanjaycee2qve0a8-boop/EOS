"""Acceptance tests for explicit opt-in simulated PV curtailment."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest

from capability import (
    ActiveCapabilityCollection,
    AvailableCapabilityCollection,
    CapabilityDescriptor,
    CapabilityMatch,
    CapabilityMatchCollection,
    RequiredCapabilityCollection,
)
from decision_formation import DecisionIntent as EMSDecisionIntent
from ems_simulator.battery import SimpleBatteryPhysicsModel
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner,
    _schedule_runner,
)
from ems_simulator.input import BatteryParameters
from ems_strategy import (
    ActuationHandoffResult,
    DecisionProvenance,
    EMSContext,
    EMSDecision,
    EMSStrategyDescriptor,
    FeasibleDecision,
    ZeroExportFeasibility,
)
from examples.virtual_home_storage_defect_campaign.campaign import (
    CONFIGURATION,
    _inputs,
    executable_scenarios,
    run_campaign,
)
from examples.virtual_home_storage_zero_export.correction import (
    POWER_TOLERANCE_KW,
    DeterministicZeroExportCurtailment,
    OptInZeroExportStepExecutor,
    ZeroExportCurtailmentInput,
)
from examples.virtual_home_storage_zero_export.demo import run_demo
from kernel.decision import DecisionContext, DecisionIntent, FeasibleDecisionIntent
from objective import (
    ObjectiveCapabilityActivationComposition,
    ObjectiveDescriptor,
)
from simulator import (
    BatterySimulationActuation,
    BatterySimulationInput,
    BatterySimulationResult,
    BatterySimulationState,
    GridSimulationInput,
    LoadSimulationInput,
    LoadSimulationResult,
    PVSimulationInput,
    SimulationStepIdentity,
)

START = datetime(2026, 3, 1, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _Fixture:
    correction_input: ZeroExportCurtailmentInput


def _fixture(
    available: float,
    load: float,
    battery: float,
    export_limit: float,
    *,
    duration_seconds: float = 3600.0,
    allowed: bool = True,
) -> _Fixture:
    identity = SimulationStepIdentity(0, duration_seconds, START)
    pv_input = PVSimulationInput(identity, available)
    load_input = LoadSimulationInput(identity, load)
    load_result = LoadSimulationResult(load_input, load)
    feasible_intent = FeasibleDecisionIntent(DecisionIntent(battery))
    battery_input = BatterySimulationInput(
        identity,
        BatterySimulationState(0.50),
        BatterySimulationActuation(feasible_intent, battery),
    )
    battery_result = BatterySimulationResult(
        battery_input,
        battery_input.source_state,
        battery,
    )
    grid_input = GridSimulationInput(identity, load + battery - available)

    required = CapabilityDescriptor("zero-export", "Required capability.")
    available_capability = CapabilityDescriptor("zero-export", "Available capability.")
    required_collection = RequiredCapabilityCollection((required,))
    available_collection = AvailableCapabilityCollection((available_capability,))
    matches = CapabilityMatchCollection(
        required_collection,
        available_collection,
        (CapabilityMatch(required, available_capability),),
        (),
    )
    active = ActiveCapabilityCollection(matches, (available_capability,), ())
    composition = ObjectiveCapabilityActivationComposition(
        ObjectiveDescriptor("zero-export", "Avoid Grid export."),
        active,
    )
    context = EMSContext(
        DecisionContext(
            START,
            0.50,
            3.0,
            10.0,
            available,
            load,
            load + battery - available,
            0.50,
            0.20,
            export_limit,
        ),
        composition,
        available_capability,
    )
    if battery > 0.0:
        intent = EMSDecisionIntent("charge")
    elif battery < 0.0:
        intent = EMSDecisionIntent("discharge")
    else:
        intent = EMSDecisionIntent("idle")
    strategy = EMSStrategyDescriptor("fixture", "1.0")
    decision = EMSDecision(
        context,
        strategy,
        intent,
        abs(battery),
    )
    provenance = DecisionProvenance(context, strategy, decision)
    zero_export = ZeroExportFeasibility(decision, provenance, False)
    feasible = FeasibleDecision(decision, provenance, intent, abs(battery))
    handoff = ActuationHandoffResult(feasible, battery_input.actuation)
    return _Fixture(
        ZeroExportCurtailmentInput(
            zero_export,
            provenance,
            handoff,
            pv_input,
            load_result,
            battery_result,
            grid_input,
            export_limit,
            allowed,
        )
    )


@pytest.mark.parametrize(
    (
        "case_id",
        "available",
        "load",
        "battery",
        "limit",
        "utilized",
        "curtailed",
        "grid",
    ),
    (
        ("Z01", 0.0, 2.0, 0.0, 0.0, 0.0, 0.0, 2.0),
        ("Z02", 2.0, 2.0, 0.0, 0.0, 2.0, 0.0, 0.0),
        ("Z03", 3.0, 1.0, 0.0, 2.0, 3.0, 0.0, -2.0),
        ("Z04", 4.0, 1.0, 0.0, 2.0, 3.0, 1.0, -2.0),
        ("Z05", 5.0, 2.0, 3.0, 0.0, 5.0, 0.0, 0.0),
        ("Z06", 10.0, 1.0, 3.0, 0.0, 4.0, 6.0, 0.0),
        ("Z07", 10.0, 0.0, 0.0, 0.0, 0.0, 10.0, 0.0),
        ("Z08", 0.0, 3.0, -2.0, 0.0, 0.0, 0.0, 1.0),
        ("Z09", 1.0, 3.0, -3.0, 1.0, 1.0, 0.0, -1.0),
        ("Z14", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    ),
)
def test_satisfied_matrix_uses_independent_fixed_oracles(
    case_id: str,
    available: float,
    load: float,
    battery: float,
    limit: float,
    utilized: float,
    curtailed: float,
    grid: float,
) -> None:
    result = DeterministicZeroExportCurtailment.evaluate(
        _fixture(available, load, battery, limit).correction_input
    )
    evidence = result.evidence

    assert evidence.status == "SATISFIED", case_id
    assert evidence.pv_utilized_kw == pytest.approx(utilized), case_id
    assert evidence.pv_curtailed_kw == pytest.approx(curtailed), case_id
    assert evidence.resulting_grid_power_kw == pytest.approx(grid), case_id
    assert evidence.pv_available_kw == pytest.approx(utilized + curtailed), case_id
    assert grid == pytest.approx(load + battery - utilized), case_id
    assert grid >= -limit - POWER_TOLERANCE_KW, case_id
    assert result.pv_result is not None and result.grid_result is not None
    assert result.pv_result.simulation_input is result.source_input.pv_input, case_id


def test_z10_battery_driven_export_rejects_without_changing_action() -> None:
    source = _fixture(0.0, 0.0, -1.0, 0.0).correction_input
    result = DeterministicZeroExportCurtailment.evaluate(source)

    assert result.evidence.status == "REJECTED"
    assert result.evidence.reason_code == "NON_PV_EXPORT_CANNOT_BE_CORRECTED"
    assert result.pv_result is None and result.grid_result is None
    assert source.battery_result.actual_power_kw == -1.0


def test_z11_required_but_unauthorized_curtailment_fails_closed() -> None:
    result = DeterministicZeroExportCurtailment.evaluate(
        _fixture(10.0, 0.0, 0.0, 0.0, allowed=False).correction_input
    )

    assert result.evidence.status == "REJECTED"
    assert result.evidence.reason_code == "CURTAILMENT_NOT_AUTHORIZED"
    assert result.evidence.pv_utilized_kw is None
    assert result.pv_result is None and result.grid_result is None


def test_precheck_boolean_does_not_replace_actual_boundary_recalculation() -> None:
    source = _fixture(10.0, 0.0, 0.0, 0.0).correction_input
    optimistic = ZeroExportFeasibility(
        source.zero_export_feasibility.source_decision,
        source.zero_export_feasibility.source_provenance,
        True,
    )
    result = DeterministicZeroExportCurtailment.evaluate(
        replace(source, zero_export_feasibility=optimistic)
    )

    assert result.evidence.reason_code == "PV_CURTAILED_TO_EXPORT_LIMIT"
    assert result.evidence.pv_curtailed_kw == 10.0
    assert result.evidence.resulting_grid_power_kw == 0.0


def test_z12_partial_headroom_uses_real_battery_model_preview() -> None:
    base = _fixture(2.0, 0.0, 3.0, 0.0).correction_input
    battery_input = BatterySimulationInput(
        base.pv_input.step_identity,
        BatterySimulationState(0.95),
        BatterySimulationActuation(
            FeasibleDecisionIntent(DecisionIntent(3.0)),
            3.0,
        ),
    )
    battery_result = SimpleBatteryPhysicsModel(
        BatteryParameters(10.0, 3.0, 3.0, 0.95, 0.95, 0.10)
    ).simulate(battery_input)
    handoff = ActuationHandoffResult(
        base.source_handoff.source_feasible_decision,
        battery_input.actuation,
    )
    result = DeterministicZeroExportCurtailment.evaluate(
        replace(base, source_handoff=handoff, battery_result=battery_result)
    )

    expected_battery_kw = 10.0 * (1.0 - 0.95) / 0.95
    assert battery_result.actual_power_kw == pytest.approx(expected_battery_kw)
    assert battery_result.next_state.soc == pytest.approx(1.0)
    assert result.evidence.pv_utilized_kw == pytest.approx(expected_battery_kw)
    assert result.evidence.pv_curtailed_kw == pytest.approx(2.0 - expected_battery_kw)
    assert result.evidence.resulting_grid_power_kw == pytest.approx(0.0)


def test_z13_duration_energy_accounting_is_separate_from_power() -> None:
    result = DeterministicZeroExportCurtailment.evaluate(
        _fixture(4.0, 1.0, 1.0, 0.0, duration_seconds=1800.0).correction_input
    )
    evidence = result.evidence

    assert evidence.duration_hours == 0.5
    assert evidence.pv_available_energy_kwh == 2.0
    assert evidence.pv_utilized_energy_kwh == 1.0
    assert evidence.pv_curtailed_energy_kwh == 1.0
    assert evidence.load_served_energy_kwh == 0.5
    assert evidence.battery_exchange_energy_kwh == 0.5
    assert evidence.resulting_grid_energy_kwh == 0.0


@pytest.mark.parametrize(
    ("contract", "value"),
    (
        ("pv", -1.0),
        ("pv", float("nan")),
        ("pv", float("inf")),
        ("load", -1.0),
        ("load", float("nan")),
        ("load", float("inf")),
        ("battery", float("nan")),
        ("battery", float("inf")),
        ("battery", float("-inf")),
    ),
)
def test_z16_invalid_component_power_is_rejected(contract: str, value: float) -> None:
    identity = SimulationStepIdentity(0, 3600.0, START)
    if contract == "pv":
        with pytest.raises(ValueError):
            PVSimulationInput(identity, value)
    elif contract == "load":
        with pytest.raises(ValueError):
            LoadSimulationInput(identity, value)
    else:
        battery_input = BatterySimulationInput(
            identity,
            BatterySimulationState(0.50),
            BatterySimulationActuation(
                FeasibleDecisionIntent(DecisionIntent(0.0)),
                0.0,
            ),
        )
        with pytest.raises(ValueError):
            BatterySimulationResult(battery_input, battery_input.source_state, value)


def test_z15_equal_but_distinct_step_identity_is_rejected() -> None:
    source = _fixture(2.0, 1.0, 0.0, 0.0).correction_input
    reconstructed = SimulationStepIdentity(0, 3600.0, START)
    mismatched_grid = GridSimulationInput(reconstructed, -1.0)

    with pytest.raises(ValueError, match="exact step identity"):
        ZeroExportCurtailmentInput(
            source.zero_export_feasibility,
            source.expected_provenance,
            source.source_handoff,
            source.pv_input,
            source.load_result,
            source.battery_result,
            mismatched_grid,
            0.0,
            True,
        )


@pytest.mark.parametrize("value", (-1.0, float("nan"), float("inf"), float("-inf")))
def test_z16_invalid_export_limit_is_rejected(value: float) -> None:
    source = _fixture(2.0, 1.0, 0.0, 0.0).correction_input

    with pytest.raises(ValueError):
        ZeroExportCurtailmentInput(
            source.zero_export_feasibility,
            source.expected_provenance,
            source.source_handoff,
            source.pv_input,
            source.load_result,
            source.battery_result,
            source.grid_input,
            value,
            True,
        )


def test_z16_non_boolean_permission_is_rejected() -> None:
    source = _fixture(2.0, 1.0, 0.0, 0.0).correction_input
    with pytest.raises(TypeError, match="curtailment_allowed"):
        ZeroExportCurtailmentInput(
            source.zero_export_feasibility,
            source.expected_provenance,
            source.source_handoff,
            source.pv_input,
            source.load_result,
            source.battery_result,
            source.grid_input,
            0.0,
            cast(Any, 1),
        )


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("pv_utilized_kw", float("nan")),
        ("pv_curtailed_kw", float("inf")),
        ("resulting_grid_power_kw", float("-inf")),
        ("pv_utilized_energy_kwh", cast(Any, True)),
        ("resulting_grid_energy_kwh", float("nan")),
    ),
)
def test_z16_reconstructed_nonfinite_or_boolean_evidence_is_rejected(
    field_name: str,
    value: object,
) -> None:
    evidence = DeterministicZeroExportCurtailment.evaluate(
        _fixture(2.0, 1.0, 0.0, 0.0).correction_input
    ).evidence

    with pytest.raises((TypeError, ValueError)):
        replace(cast(Any, evidence), **{field_name: value})


def test_explicit_tolerance_only_absorbs_sub_tolerance_residual() -> None:
    within = DeterministicZeroExportCurtailment.evaluate(
        _fixture(1.0, 0.0, 0.0, 1.0 - 0.5e-9).correction_input
    )
    above = DeterministicZeroExportCurtailment.evaluate(
        _fixture(1.0, 0.0, 0.0, 1.0 - 2.0e-9).correction_input
    )

    assert within.evidence.pv_curtailed_kw == 0.0
    assert within.evidence.resulting_grid_power_kw == -1.0
    assert above.evidence.pv_curtailed_kw == pytest.approx(2.0e-9)
    assert above.evidence.resulting_grid_power_kw == pytest.approx(-(1.0 - 2.0e-9))


def _scenario(scenario_id: str):  # type: ignore[no-untyped-def]
    return next(
        item for item in executable_scenarios() if item.scenario_id == scenario_id
    )


def _schedule_trace(scenario_id: str, tmp_path: Path, hour: int = 0):  # type: ignore[no-untyped-def]
    spec = _scenario(scenario_id)
    schedule_input, _ = _inputs(spec, tmp_path)
    trajectory = _schedule_runner(CONFIGURATION).run(schedule_input)
    return spec, trajectory.step_traces[hour]


def _parameters(spec) -> BatteryParameters:  # type: ignore[no-untyped-def]
    model = spec.battery_model
    return BatteryParameters(
        model.usable_capacity_kwh,
        model.max_charge_power_kw,
        model.max_discharge_power_kw,
        model.charge_efficiency,
        model.discharge_efficiency,
        model.min_soc_fraction,
    )


def test_paired_wrong_strategy_lineage_with_same_step_values_is_rejected(
    tmp_path: Path,
) -> None:
    spec = _scenario("S09_ZERO_EXPORT_FULL")
    schedule_input, economic_input = _inputs(spec, tmp_path / "cross_strategy")
    schedule_trace = _schedule_runner(CONFIGURATION).run(schedule_input).step_traces[0]
    economic_trace = _economic_runner(CONFIGURATION).run(economic_input).step_traces[0]
    wrong_feasibility = ZeroExportFeasibility(
        economic_trace.decision_provenance.decision,
        economic_trace.decision_provenance,
        False,
    )

    with pytest.raises(ValueError, match="exact battery actuation"):
        OptInZeroExportStepExecutor.execute(
            schedule_trace.simulation_trace.simulation_input,
            zero_export_feasibility=wrong_feasibility,
            expected_provenance=economic_trace.decision_provenance,
            source_handoff=economic_trace.handoff,
            battery_model=SimpleBatteryPhysicsModel(_parameters(spec)),
            export_limit_kw=0.0,
            curtailment_allowed=True,
        )


def test_s09_opt_in_uses_real_battery_preview_and_preserves_default_trace(
    tmp_path: Path,
) -> None:
    spec, trace = _schedule_trace("S09_ZERO_EXPORT_FULL", tmp_path / "s09")
    original = trace.simulation_trace
    feasibility = ZeroExportFeasibility(
        trace.decision_provenance.decision,
        trace.decision_provenance,
        False,
    )
    corrected = OptInZeroExportStepExecutor.execute(
        original.simulation_input,
        zero_export_feasibility=feasibility,
        expected_provenance=trace.decision_provenance,
        source_handoff=trace.handoff,
        battery_model=SimpleBatteryPhysicsModel(_parameters(spec)),
        export_limit_kw=0.0,
        curtailment_allowed=True,
    )

    assert original.state.pv_result.actual_power_kw == 10.0
    assert original.state.grid_result.actual_grid_power_kw == -10.0
    assert corrected.simulation_trace is not None
    state = corrected.simulation_trace.state
    assert (
        corrected.correction.source_input.pv_input is original.simulation_input.pv_input
    )
    assert state.pv_result.actual_power_kw == 0.0
    assert corrected.correction.evidence.pv_curtailed_kw == 10.0
    assert state.battery_result.actual_power_kw == 0.0
    assert state.grid_result.actual_grid_power_kw == 0.0
    assert corrected.correction.evidence.pv_available_energy_kwh == 10.0
    assert corrected.correction.evidence.pv_curtailed_energy_kwh == 10.0
    assert corrected.correction.evidence.resulting_grid_energy_kwh == 0.0
    assert state.battery_result.next_state is original.state.battery_result.next_state


def test_rejected_preview_has_no_trace_and_does_not_commit_soc(tmp_path: Path) -> None:
    spec, trace = _schedule_trace("S07_CHARGE_LIMIT", tmp_path / "s07")
    original = trace.simulation_trace
    source_state = original.simulation_input.battery_input.source_state
    feasibility = ZeroExportFeasibility(
        trace.decision_provenance.decision,
        trace.decision_provenance,
        False,
    )
    rejected = OptInZeroExportStepExecutor.execute(
        original.simulation_input,
        zero_export_feasibility=feasibility,
        expected_provenance=trace.decision_provenance,
        source_handoff=trace.handoff,
        battery_model=SimpleBatteryPhysicsModel(_parameters(spec)),
        export_limit_kw=spec.export_limit_kw,
        curtailment_allowed=False,
    )

    assert rejected.correction.evidence.status == "REJECTED"
    assert rejected.simulation_trace is None
    assert original.simulation_input.battery_input.source_state is source_state
    assert source_state.soc == 0.50


def test_default_campaign_is_unchanged_and_other_limitations_remain(
    tmp_path: Path,
) -> None:
    campaign = run_campaign(tmp_path / "default_campaign")
    assert Counter(item.status for item in campaign.path_results) == {
        "PASS": 24,
        "LIMITATION": 8,
        "REJECTED_AS_EXPECTED": 3,
    }
    limitation_codes = Counter(
        item.finding_code
        for item in campaign.path_results
        if item.status == "LIMITATION"
    )
    assert limitation_codes == {
        "ZERO_EXPORT_NOT_ENFORCED_NO_CURTAILMENT": 2,
        "NO_PRICE_ONLY_ARBITRAGE": 2,
        "FALSE_PV_FORECAST_CAUSES_GRID_CHARGE": 2,
        "MISSED_LOAD_SPIKE_NO_DISCHARGE": 2,
    }


def test_opt_in_demo_reports_both_paths_without_overwriting_default(
    tmp_path: Path,
) -> None:
    result = run_demo(tmp_path / "demo")

    assert [row.strategy for row in result.rows] == ["Schedule", "Economic"]
    for row in result.rows:
        assert row.evidence_kind == "SIMULATED"
        assert row.telemetry is False
        assert row.default_pv_available_kw == 10.0
        assert row.default_pv_actual_kw == 10.0
        assert row.default_battery_actual_kw == 0.0
        assert row.default_grid_actual_kw == -10.0
        assert row.opt_in_status == "SATISFIED"
        assert row.opt_in_pv_utilized_kw == 0.0
        assert row.opt_in_pv_curtailed_kw == 10.0
        assert row.opt_in_grid_power_kw == 0.0
        assert row.opt_in_pv_curtailed_kwh == 10.0
        assert row.opt_in_grid_energy_kwh == 0.0
        assert row.battery_action_unchanged
        assert row.source_pv_input_unchanged
    report = next(
        path for path in result.output_paths if path.name.endswith("report_zh.md")
    ).read_text(encoding="utf-8")
    assert "SIMULATED" in report
    assert "默认 runner 保持未修正证据" in report
    assert "NO_PRICE_ONLY_ARBITRAGE" in report
    for path in result.output_paths:
        if path.suffix in {".json", ".csv"}:
            contents = path.read_text(encoding="utf-8")
            assert "SIMULATED" in contents
            assert "telemetry" in contents
