"""Predeclared daily-adapter acceptance; no predecessor assertions changed."""

from dataclasses import replace
from datetime import timedelta, timezone
from itertools import pairwise
from math import nextafter

import pytest

from ems_simulator.demo import create_demo_scenario
from ems_simulator.runner import DailySimulationRunner
from tools.dynamic_constraint_probe import Case, FactSegment, _request, battery
from tools.joint_daily_demo import run_daily_case
from tools.joint_daily_output import report_status, validate_ledger, window_totals
from tools.joint_execution_contract import (
    DAY_ENERGY_TOL,
    ENERGY_TOL,
    POWER_TOL,
    SOC_TOL,
    DailyEvent,
    JointExecutionContext,
    daily_case,
    validate_daily_case,
)
from tools.pv_grid_charge_joint_probe import run_joint, scenarios


def quantity_tolerance(key: str, *, daily: bool = False) -> float:
    if key == "soc_end":
        return SOC_TOL
    if key.startswith("average_") or key == "export_peak_kw":
        return POWER_TOL
    return DAY_ENERGY_TOL if daily else ENERGY_TOL


def fact(
    start: int,
    end: int,
    load: float,
    pv: float,
    allowed: bool = False,
    zero: bool = True,
    target: float = 0.2,
) -> FactSegment:
    return FactSegment(start, end, load, pv, allowed, zero, target)


@pytest.mark.parametrize("charging", [True, False])
@pytest.mark.parametrize("offset", [39600, 82800])
@pytest.mark.parametrize("step", [3600, 60, 15])
def test_late_boundary_coordinate_regression(
    charging: bool, offset: int, step: int
) -> None:
    """A one-ULP boundary remainder after idle must not disappear in the ledger."""
    soc = nextafter(1.0, 0.0) if charging else nextafter(0.2, 1.0)
    case = Case(
        "late-boundary",
        soc,
        (
            fact(0, offset, 0, 0, allowed=True, zero=False),
            fact(offset, 86400, 1, 4 if charging else 0, allowed=True, zero=False),
        ),
    )
    result = run_daily_case(case, mode="ideal", physical_step_s=step)
    validate_ledger(result.execution.ledger)
    rows = result.execution.ledger
    assert all(row.end_s > row.start_s for row in rows)
    assert all(
        a.end_s == b.start_s and a.soc_after == b.soc_before for a, b in pairwise(rows)
    )
    assert result.execution.final_soc == (1.0 if charging else 0.2)
    assert sum(row.battery_kwh for row in rows) != 0


def test_physical_parts_have_one_event_owner() -> None:
    """Retained sub-ULP peak may not be averaged away or counted in two windows."""
    from tools.pv_curtailment_probe import PhysicalLedgerPart
    from tools.pv_grid_charge_joint_probe import _event_outcomes, _excursions

    case = Case("ownership", 0.5, (fact(0, 3600, 0, 0), fact(3600, 86400, 0, 0)))
    execution = run_daily_case(case, mode="ideal").execution
    left = execution.ledger[59]
    right = execution.ledger[60]
    assert left.end_s == right.start_s == 3600
    # Tail lies before the event even when its absolute start rounds to 3600.
    tiny = 1e-13
    tail_start = nextafter(60.0, 0.0)
    left_parts = (
        PhysicalLedgerPart(3540, 0, tail_start, 0, 0, 0.5, 0.5),
        PhysicalLedgerPart(3540, tail_start, 60, 0, -3, 0.5, 0.5),
    )
    right_parts = (
        PhysicalLedgerPart(3600, 0, tiny, 0, -2, 0.5, 0.5),
        PhysicalLedgerPart(3600, tiny, 60, 0, 0, 0.5, 0.5),
    )
    left_energy = 3 * ((60 - tail_start) / 3600)
    right_energy = 2 * (tiny / 3600)
    modified = list(execution.ledger)
    modified[59] = replace(left, physical_parts=left_parts, export_kwh=left_energy)
    modified[60] = replace(right, physical_parts=right_parts, export_kwh=right_energy)
    modified_execution = replace(execution, ledger=tuple(modified))
    # This is an audit-consumer fixture, not a fabricated physics PASS.
    events = [
        e for e in _event_outcomes(modified_execution) if e.constraint == "ZERO_EXPORT"
    ]
    assert events[0].violation_energy_kwh == left_energy
    assert events[1].violation_energy_kwh == right_energy
    assert sum(e.violation_energy_kwh for e in events) == left_energy + right_energy
    assert events[0].peak_kw == 3
    assert events[1].peak_kw == 2
    excursions = _excursions(tuple(modified), execution.settings)
    assert max(e.peak_kw for e in excursions) == 3
    assert sum(e.energy_kwh for e in excursions) == left_energy + right_energy
    assert window_totals(tuple(modified), 0, 3600)["export_kwh"] == left_energy
    assert window_totals(tuple(modified), 3600, 7200)["export_kwh"] == right_energy


def test_original_defaults_and_evidence_counts() -> None:
    results = [
        run_joint(case, mode=mode, physical_step_s=60)
        for case in scenarios().values()
        for mode in ("ideal", "dynamic")
    ]
    assert all(result.passed for result in results)
    assert sum(len(result.excursions) for result in results) == 14
    assert (
        sum(f.status == "SOFT_TARGET" for result in results for f in result.findings)
        == 12
    )
    assert all(result.execution.settings.pv_ac_max_kw == 5 for result in results)
    assert all(result.execution.ledger[-1].end_s == 7200 for result in results)


def test_unmodified_source_curve_and_fixed_parameters() -> None:
    source = create_demo_scenario()
    case = daily_case(source)
    assert tuple(f.pv_kw for f in case.segments) == source.pv_power_curve_kw
    assert tuple(f.load_kw for f in case.segments) == source.load_power_curve_kw
    assert max(f.pv_kw for f in case.segments) == 5.8
    assert JointExecutionContext().battery_parameters == source.battery_parameters
    assert JointExecutionContext().pv_ac_max_kw == 6
    with pytest.raises(ValueError):
        JointExecutionContext(
            battery_parameters=replace(battery(), max_charge_power_kw=6)
        )


@pytest.mark.parametrize("soc", [0.5, 1.0, 0.2])
@pytest.mark.parametrize("mode", ["ideal", "dynamic"])
def test_daily_baseline_three_physical_steps(soc: float, mode: str) -> None:
    case = replace(daily_case(), initial_soc=soc)
    results = [
        run_daily_case(case, mode=mode, physical_step_s=step) for step in (3600, 60, 15)
    ]
    for result in results:
        validate_ledger(result.execution.ledger)
        assert result.passed, result.excursions
        assert report_status(result)[0] == "PASS", report_status(result)
        assert tuple(item.at for item in result.execution.decisions) == tuple(
            range(0, 86400, 3600)
        )
        assert result.execution.ledger[-1].end_s == 86400
        if mode == "dynamic":
            checks = result.execution.checks
            assert len(checks) == 1439
            assert (checks[0].check_at, checks[0].sampled_at, checks[0].effect_at) == (
                60,
                40,
                70,
            )
    for other in results[1:]:
        assert (
            abs(other.execution.final_soc - results[0].execution.final_soc) <= SOC_TOL
        )
        assert other.execution.checks == results[0].execution.checks
        for start in range(0, 86400, 7200):
            a = window_totals(results[0].execution.ledger, start, start + 7200)
            b = window_totals(other.execution.ledger, start, start + 7200)
            for key in a:
                tolerance = quantity_tolerance(key)
                assert abs(a[key] - b[key]) <= tolerance, (start, key, a[key], b[key])
        a = window_totals(results[0].execution.ledger, 0, 86400)
        b = window_totals(other.execution.ledger, 0, 86400)
        assert all(abs(a[k] - b[k]) <= quantity_tolerance(k, daily=True) for k in a)


def test_display_and_record_do_not_change_execution() -> None:
    case = daily_case()
    results = [
        run_daily_case(case, mode="dynamic", record_period_s=r, display_period_s=d)
        for r, d in ((60, 5), (15, 1), (3600, 60))
    ]
    for result in results[1:]:
        assert result.execution.ledger == results[0].execution.ledger
        assert result.execution.decisions == results[0].execution.decisions
        assert result.execution.checks == results[0].execution.checks


def test_reverse_flows_do_not_net_out() -> None:
    case = Case(
        "reverse",
        0.2,
        (
            fact(0, 1800, 2, 0, zero=False),
            fact(1800, 3600, 0, 2, zero=False),
            fact(3600, 86400, 0, 0, zero=False),
        ),
    )
    for step in (3600, 60, 15):
        result = run_daily_case(case, mode="ideal", physical_step_s=step)
        first = window_totals(result.execution.ledger, 0, 3600)
        assert first["import_kwh"] == pytest.approx(1, abs=ENERGY_TOL)
        assert first["export_kwh"] == pytest.approx(1, abs=ENERGY_TOL)
        assert first["average_grid_kw"] == pytest.approx(0, abs=1e-9)
        assert first["battery_kwh"] == 0


def test_permission_revoke_budget_and_restore_latch() -> None:
    case = Case(
        "late_revoke_daily",
        0.3,
        (
            fact(0, 4000, 1, 0, True, target=0.8),
            fact(4000, 4100, 1, 0, target=0.8),
            fact(4100, 86400, 1, 0, True, target=0.8),
        ),
    )
    result = run_daily_case(case, mode="dynamic")
    rows = result.execution.ledger
    assert sum(r.prohibited_grid_charge_kwh for r in rows) == pytest.approx(
        0.025, abs=ENERGY_TOL
    )
    assert all(r.actual_battery_kw == 0 for r in rows if 4030 <= r.start_s < 7200)
    assert result.passed


def test_timezones_are_equivalent_not_civil_day_shift() -> None:
    source = create_demo_scenario()
    shifted = replace(
        source,
        step_identities=tuple(
            replace(i, timestamp=i.timestamp.astimezone(timezone(timedelta(hours=8))))
            for i in source.step_identities
            if i.timestamp is not None
        ),
    )
    assert daily_case(shifted) == daily_case(source)
    wrong = replace(
        source,
        step_identities=tuple(
            replace(i, timestamp=i.timestamp + timedelta(hours=1))
            for i in source.step_identities
            if i.timestamp is not None
        ),
    )
    with pytest.raises(ValueError, match="UTC day"):
        daily_case(wrong)


@pytest.mark.parametrize("at", [-1, 86400, 1.5, True])
def test_invalid_event_times(at: int) -> None:
    with pytest.raises(ValueError):
        DailyEvent(at, zero_export=False)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 6.01])
def test_invalid_pv(value: float) -> None:
    with pytest.raises(ValueError):
        DailyEvent(1, pv_kw=value)


def test_duplicate_and_out_of_order_events_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        daily_case(
            events=(DailyEvent(1, zero_export=False), DailyEvent(1, zero_export=False))
        )
    with pytest.raises(ValueError, match="ordered"):
        daily_case(
            events=(DailyEvent(2, zero_export=False), DailyEvent(1, zero_export=True))
        )


def test_bad_facts_and_ledger_are_rejected() -> None:
    case = daily_case()
    with pytest.raises(ValueError):
        validate_daily_case(
            replace(case, segments=case.segments[1:]), JointExecutionContext()
        )
    result = run_daily_case(case, mode="ideal")
    rows = result.execution.ledger
    with pytest.raises(ValueError):
        validate_ledger(rows[1:])
    with pytest.raises(ValueError):
        validate_ledger((rows[0], *rows))


def test_end_and_dense_facts_are_not_blanket_pass() -> None:
    case = daily_case(events=(DailyEvent(86390, zero_export=False),))
    result = run_daily_case(case, mode="dynamic")
    assert report_status(result)[0] != "PASS"
    dense = daily_case(
        events=(DailyEvent(1810, zero_export=False), DailyEvent(1820, zero_export=True))
    )
    result = run_daily_case(dense, mode="dynamic")
    assert any("NOT_COVERED" in reason for reason in report_status(result)[1])


def test_strategy_difference_is_not_an_integrator_error() -> None:
    assert DailySimulationRunner._battery_request(0, 1, 0.3, 0.2) == -1
    assert _request(fact(0, 86400, 1, 0, True, target=0.8), 0.3, battery()) == 3


@pytest.mark.parametrize("revoke_at,expected_energy", [(40, 0.0), (41, 0.05)])
def test_observation_phase_40_41(revoke_at: int, expected_energy: float) -> None:
    """Predetermined: sample40 sees e40, not e41; the latter stops at130."""
    case = Case(
        "phase",
        0.3,
        (
            fact(0, revoke_at, 1, 0, True, target=0.8),
            fact(revoke_at, 86400, 1, 0, False, target=0.8),
        ),
    )
    result = run_daily_case(case, mode="dynamic")
    rows = result.execution.ledger
    validate_ledger(rows)
    assert sum(r.prohibited_grid_charge_kwh for r in rows) == pytest.approx(
        expected_energy, abs=ENERGY_TOL
    )
    violations = [r for r in rows if r.prohibited_grid_charge_kwh > 0]
    if revoke_at == 41:
        assert violations[0].start_s == 70
        assert violations[-1].end_s == 130
        assert violations[-1].end_s - revoke_at == 89
    else:
        assert not violations
    assert len(result.execution.decisions) == 24


@pytest.mark.parametrize(
    "name",
    [
        "upper_soc_same_time",
        "lower_soc_same_time",
        "same_time_facts",
        "interleaved_permission",
    ],
)
@pytest.mark.parametrize("mode", ["ideal", "dynamic"])
def test_existing_simultaneous_facts_extend_to_daily(name: str, mode: str) -> None:
    source = scenarios()[name]
    case = replace(
        source,
        segments=(*source.segments[:-1], replace(source.segments[-1], end=86400)),
    )
    result = run_daily_case(case, mode=mode)
    assert result.passed, result.excursions
    validate_ledger(result.execution.ledger)
    assert tuple(d.at for d in result.execution.decisions) == tuple(
        range(0, 86400, 3600)
    )
    for segment in case.segments[1:]:
        row = next(r for r in result.execution.ledger if r.start_s == segment.start)
        assert row.grid_charge_allowed == segment.grid_charge_allowed
        assert row.zero_export_requested == segment.zero_export
        assert row.reserve_target_soc == segment.reserve_target_soc
    if mode == "ideal" and name == "upper_soc_same_time":
        assert (
            next(d.feedback_soc for d in result.execution.decisions if d.at == 3600)
            == 1
        )
    if mode == "ideal" and name == "lower_soc_same_time":
        assert next(
            d.feedback_soc for d in result.execution.decisions if d.at == 3600
        ) == pytest.approx(0.2, abs=SOC_TOL)


def test_six_kw_cap_and_output_response_envelope() -> None:
    # e41 is first sampled at100/check120/effect130. Cap rises131..136;
    # actual PV output rises132..137. These are simulation assumptions.
    case = Case("six-kw", 1, (fact(0, 41, 0, 0), fact(41, 86400, 6, 6)))
    result = run_daily_case(case, mode="dynamic")
    rows = result.execution.ledger
    assert next(r.start_s for r in rows if r.pv_cap_kw == 6) == 136
    assert next(r.start_s for r in rows if r.delivered_pv_kw == 6) == 137
    assert 137 - 41 <= 97
    assert result.execution.settings.response_budget_s == 96
    validate_ledger(rows)


def test_97_envelope_cannot_waive_96_audit() -> None:
    from tools.pv_grid_charge_joint_probe import _excursions

    case = Case("audit-fixture", 0.2, (fact(0, 86400, 0, 0),))
    result = run_daily_case(case, mode="dynamic")
    # An isolated audit-consumer negative fixture, not a simulated PASS.
    row = replace(
        result.execution.ledger[0],
        start_s=0,
        end_s=96.5,
        grid_kw=-1,
        export_kwh=96.5 / 3600,
        physical_parts=(),
    )
    assessment = _excursions((row,), result.execution.settings)
    assert len(assessment) == 1
    assert assessment[0].duration_s < 97
    assert not assessment[0].within_budget


def test_pv_loss_really_intersects_output_rise() -> None:
    case = Case(
        "rise-loss",
        1,
        (
            fact(0, 41, 0, 0),
            fact(41, 133, 6, 6),
            fact(133, 86400, 6, 0),
        ),
    )
    result = run_daily_case(case, mode="dynamic")
    rows = result.execution.ledger
    before = next(r for r in rows if r.start_s == 132)
    assert 0 < before.delivered_pv_kw < 6
    after = next(r for r in rows if r.start_s == 133)
    assert after.available_pv_kw == after.delivered_pv_kw == 0
    assert after.grid_kw == 6  # load remains; no energy is manufactured
    assert any("NOT_COVERED" in reason for reason in report_status(result)[1])
    validate_ledger(rows)


@pytest.mark.parametrize("requested_kw", [-1.0, 1.0])
@pytest.mark.parametrize("step", [3600, 60, 15])
def test_contract_exact_one_kwh_efficiency(requested_kw: float, step: int) -> None:
    from ems_simulator.time_energy import (
        PowerInterval,
        SimulationCadences,
        TimeEnergyInput,
        simulate_time_energy,
    )

    result = simulate_time_energy(
        TimeEnergyInput(
            SimulationCadences(step, 3600, 3600, 60, 5),
            (PowerInterval(0, 3600, 0, 0, requested_kw),),
            battery(),
            0.5,
        )
    )
    expected_storage = 0.95 if requested_kw > 0 else -1 / 0.95
    assert abs(result.battery_delivered_energy_kwh - requested_kw) <= ENERGY_TOL
    stored = 10 * (result.final_soc - 0.5)
    assert abs(stored - expected_storage) <= ENERGY_TOL
    assert (
        abs((requested_kw - stored) - (requested_kw - expected_storage)) <= ENERGY_TOL
    )


@pytest.mark.parametrize("charging", [True, False])
@pytest.mark.parametrize("step", [3600, 60, 15])
@pytest.mark.parametrize("perturbation", [-1e-6, 0.0, 1e-6])
def test_contract_idle_boundary_perturbations(
    charging: bool, step: int, perturbation: float
) -> None:
    from ems_simulator.time_energy import (
        PowerInterval,
        SimulationCadences,
        TimeEnergyInput,
        simulate_time_energy,
    )

    soc = 0.95 if charging else 0.25
    boundary = (
        0.05 * 10 * 3600 / (3 * 0.95) if charging else 0.05 * 10 * 0.95 * 3600 / 3
    )
    duration = boundary + perturbation
    request = 3 if charging else -3
    result = simulate_time_energy(
        TimeEnergyInput(
            SimulationCadences(step, 3600, 3600, 60, 5),
            (
                PowerInterval(0, 900, 0, 0, 0),
                PowerInterval(900, 900 + duration, 0, 0, request),
            ),
            battery(),
            soc,
        )
    )
    expected_ac = request * min(duration, boundary) / 3600
    expected_stored = expected_ac * 0.95 if charging else expected_ac / 0.95
    assert abs(result.battery_delivered_energy_kwh - expected_ac) <= ENERGY_TOL
    assert abs(10 * (result.final_soc - soc) - expected_stored) <= ENERGY_TOL
    assert abs(result.final_soc - (soc + expected_stored / 10)) <= SOC_TOL
    assert all(s.end_seconds > s.start_seconds for s in result.slices)
    if perturbation > 0:
        moving = [s for s in result.slices if s.actual_battery_power_kw != 0]
        assert abs(moving[-1].end_seconds - (900 + boundary)) <= 1e-7
        assert result.slices[-1].actual_battery_power_kw == 0


@pytest.mark.parametrize("duration", [0.0, -1.0, float("nan")])
def test_contract_illegal_physical_duration(duration: float) -> None:
    from ems_simulator.time_energy import PowerInterval

    with pytest.raises(ValueError):
        PowerInterval(0, duration, 0, 0, 1)


def switching_daily_case() -> Case:
    return Case(
        "switching-contract",
        0.3,
        (
            fact(0, 4000, 1, 0, True, target=0.8),
            fact(4000, 4100, 1, 0, target=0.8),
            fact(4100, 86400, 1, 0, True, target=0.8),
        ),
    )


@pytest.mark.parametrize("mode", ["ideal", "dynamic"])
def test_switching_daily_step_and_view_invariance(mode: str) -> None:
    case = switching_daily_case()
    reference = run_daily_case(case, mode=mode, physical_step_s=3600)
    for step in (60, 15):
        other = run_daily_case(case, mode=mode, physical_step_s=step)
        validate_ledger(other.execution.ledger)
        assert other.execution.checks == reference.execution.checks
        assert tuple(d.at for d in other.execution.decisions) == tuple(
            range(0, 86400, 3600)
        )
        for left, right in zip(
            other.execution.decisions, reference.execution.decisions, strict=True
        ):
            assert abs(left.original_request_kw - right.original_request_kw) <= 1e-9
            assert abs(left.feedback_soc - right.feedback_soc) <= SOC_TOL
        for start in range(0, 86400, 7200):
            a = window_totals(reference.execution.ledger, start, start + 7200)
            b = window_totals(other.execution.ledger, start, start + 7200)
            assert all(abs(a[key] - b[key]) <= quantity_tolerance(key) for key in a)
    for record, display in ((15, 1), (3600, 60)):
        other = run_daily_case(
            case,
            mode=mode,
            physical_step_s=3600,
            record_period_s=record,
            display_period_s=display,
        )
        assert other.execution.ledger == reference.execution.ledger
        assert other.execution.decisions == reference.execution.decisions
        assert other.execution.checks == reference.execution.checks


def test_dynamic_reverse_flow_uses_actual_ramp_not_ideal_totals() -> None:
    from tools.pv_curtailment_probe import physical_audit_rows

    case = Case(
        "dynamic-reverse",
        0.2,
        (
            fact(0, 1800, 2, 0, zero=False),
            fact(1800, 3600, 0, 2, zero=False),
            fact(3600, 86400, 0, 0, zero=False),
        ),
    )
    totals = []
    for step in (3600, 60, 15):
        result = run_daily_case(case, mode="dynamic", physical_step_s=step)
        validate_ledger(result.execution.ledger)
        raw = physical_audit_rows(
            tuple(r for r in result.execution.ledger if r.end_s <= 3600)
        )
        hourly = window_totals(result.execution.ledger, 0, 3600)
        bought = sum(max(r.grid_kw, 0) * r.duration_s / 3600 for r in raw)
        sold = sum(max(-r.grid_kw, 0) * r.duration_s / 3600 for r in raw)
        assert abs(hourly["import_kwh"] - bought) <= ENERGY_TOL
        assert abs(hourly["export_kwh"] - sold) <= ENERGY_TOL
        assert bought > 0 and 0 < sold < 1  # real ramp, not the ideal 1 kWh
        assert hourly["battery_kwh"] == 0
        totals.append(hourly)
    assert all(
        abs(t[key] - totals[0][key]) <= quantity_tolerance(key)
        for t in totals[1:]
        for key in t
    )


def test_final_event_keeps_uncleared_nonzero_violation() -> None:
    case = Case("censored-export", 1, (fact(0, 86390, 6, 6), fact(86390, 86400, 0, 6)))
    result = run_daily_case(case, mode="dynamic")
    outcomes = [
        e
        for e in result.event_outcomes
        if e.source_at_s == 86390 and e.constraint == "ZERO_EXPORT"
    ]
    assert len(outcomes) == 1
    event = outcomes[0]
    assert event.censored and event.actual_stop_at_s is None
    assert abs(event.violation_energy_kwh - 6 * 10 / 3600) <= ENERGY_TOL
    assert report_status(result)[0] != "PASS"
    assert tuple(d.at for d in result.execution.decisions) == tuple(
        range(0, 86400, 3600)
    )


def test_old_five_kw_port_rejects_daily_peak() -> None:
    from tools.pv_curtailment_probe import run_curtailment

    with pytest.raises(ValueError, match="rating"):
        run_curtailment(
            Case("over-old-port", 0.5, (fact(0, 7200, 0, 5.8),)), physical_step_s=60
        )


def test_nonfixed_timezone_and_naive_source_rejected() -> None:
    from datetime import datetime, tzinfo

    class SeasonalZone(tzinfo):
        def utcoffset(self, dt: datetime | None) -> timedelta:
            return timedelta(hours=1)

        def dst(self, dt: datetime | None) -> timedelta:
            return timedelta(0)

        def tzname(self, dt: datetime | None) -> str:
            return "test-only-nonfixed-zone"

    source = create_demo_scenario()
    for zone in (None, SeasonalZone()):
        # Rejection may occur in the immutable source constructor or adapter;
        # neither case invokes the executor.
        with pytest.raises((ValueError, TypeError)):
            changed = replace(
                source,
                step_identities=tuple(
                    replace(i, timestamp=i.timestamp.replace(tzinfo=zone))
                    for i in source.step_identities
                    if i.timestamp is not None
                ),
            )
            daily_case(changed)
