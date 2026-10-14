"""One-ledger, test-only PV curtailment plus grid-charge interlock audit.

This module defines facts and reports.  The accepted PV executor remains the
only execution/physics implementation; no second energy state is composed.
"""

import argparse
import csv
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from pathlib import Path
from xml.etree import ElementTree as ET

from tools.dynamic_constraint_probe import HOUR_SECONDS, Case, FactSegment
from tools.joint_execution_contract import JointExecutionContext
from tools.joint_strategy_adapter import JOINT, RequestStrategy
from tools.pv_curtailment_probe import (
    CurtailmentResult,
    CurtailmentRow,
    CurtailmentSettings,
    physical_audit_rows,
    run_curtailment,
)
from tools.pv_curtailment_probe import (
    write_evidence as write_execution_evidence,
)

POWER_TOL_KW = 1e-9
ENERGY_TOL_KWH = 2e-9


@dataclass(frozen=True, slots=True)
class Excursion:
    kind: str
    start_s: float
    end_s: float
    peak_kw: float
    duration_s: float
    energy_kwh: float
    within_budget: bool


@dataclass(frozen=True, slots=True)
class ConstraintFinding:
    code: str
    status: str
    amount_kwh: float
    detail: str


@dataclass(frozen=True, slots=True)
class EventOutcome:
    event_kind: str
    constraint: str
    source_at_s: float
    window_end_s: float
    had_violation: bool
    actual_stop_at_s: float | None
    peak_kw: float
    violation_duration_s: float
    violation_energy_kwh: float
    censored: bool


@dataclass(frozen=True, slots=True)
class JointResult:
    execution: CurtailmentResult
    excursions: tuple[Excursion, ...]
    event_outcomes: tuple[EventOutcome, ...]
    findings: tuple[ConstraintFinding, ...]
    passed: bool


def scenarios() -> dict[str, Case]:
    """Predeclared finite facts; no runtime policy or optimizer is created."""

    def fact(
        start: int,
        end: int,
        load: float,
        pv: float,
        *,
        allowed: bool = False,
        zero: bool = True,
        target: float = 0.2,
    ) -> FactSegment:
        return FactSegment(start, end, load, pv, allowed, zero, target)

    # The upper and lower same-time cases have an exact 3600-second physical
    # boundary in ideal mode (0.95 efficiency, +/-3 kW, 10 kWh battery).
    upper_soc = 1.0 - 3.0 * 0.95 / 10.0
    lower_soc = 0.2 + 3.0 / (10.0 * 0.95)
    return {
        "full_battery_legacy": Case("full_battery_legacy", 1.0, (fact(0, 7200, 1, 5),)),
        "permission_off_pv_startup": Case(
            "permission_off_pv_startup", 0.3, (fact(0, 7200, 1, 5, target=0.9),)
        ),
        "full_pv_load_drop": Case(
            "full_pv_load_drop",
            1.0,
            (
                fact(0, 1800, 1, 0),
                fact(1800, 2400, 1, 5),
                fact(2400, 7200, 0, 5),
            ),
        ),
        "revoke_pv_loss": Case(
            "revoke_pv_loss",
            0.3,
            (
                fact(0, 1800, 1, 3, allowed=True, target=0.9),
                fact(1800, 2000, 1, 3, target=0.9),
                fact(2000, 7200, 1, 0, target=0.9),
            ),
        ),
        "revoke_pv_jump_ramp": Case(
            "revoke_pv_jump_ramp",
            0.3,
            (
                fact(0, 1800, 1, 0, allowed=True, zero=False, target=0.9),
                fact(1800, 7200, 1, 5, target=0.9),
            ),
        ),
        "discharge_load_drop": Case(
            "discharge_load_drop",
            0.8,
            (fact(0, 1800, 3, 1), fact(1800, 7200, 0, 1)),
        ),
        "revoke_restore_modes": Case(
            "revoke_restore_modes",
            0.3,
            (
                fact(0, 1800, 1, 0, allowed=True, zero=False, target=0.9),
                fact(1800, 2400, 1, 0, target=0.9),
                fact(2400, 3000, 1, 0, allowed=True, target=0.9),
                fact(3000, 3600, 1, 0, zero=False, target=0.9),
                fact(3600, 7200, 1, 0, allowed=True, target=0.9),
            ),
        ),
        "upper_soc_same_time": Case(
            "upper_soc_same_time",
            upper_soc,
            (
                fact(0, 3600, 1, 5, allowed=True, target=1.0),
                fact(3600, 7200, 1, 5, target=1.0),
            ),
        ),
        "lower_soc_same_time": Case(
            "lower_soc_same_time",
            lower_soc,
            (
                fact(0, 3600, 3, 0),
                fact(3600, 7200, 3, 0, allowed=True),
            ),
        ),
        "interleaved_permission": Case(
            "interleaved_permission",
            0.3,
            (
                fact(0, 1800, 1, 0, allowed=True, zero=False, target=0.9),
                fact(1800, 1810, 1, 0, target=0.9),
                fact(1810, 1820, 1, 0, allowed=True, target=0.9),
                fact(1820, 1900, 1, 0, target=0.9),
                fact(1900, 7200, 1, 0, allowed=True, target=0.9),
            ),
        ),
        "late_revoke": Case(
            "late_revoke",
            0.3,
            (
                fact(0, 4000, 1, 0, allowed=True, zero=False, target=0.9),
                fact(4000, 4100, 1, 0, target=0.9),
                fact(4100, 7200, 1, 0, allowed=True, target=0.9),
            ),
        ),
        "threshold_chatter": Case(
            "threshold_chatter",
            0.8,
            tuple(
                fact(start, min(start + 30, 7200), 1, 1.01 if i % 2 else 0.99)
                for i, start in enumerate(range(0, 7200, 30))
            ),
        ),
        "same_time_facts": Case(
            "same_time_facts",
            0.5,
            (
                fact(0, 1800, 2, 0, allowed=True, zero=False, target=0.8),
                fact(1800, 7200, 0, 5, allowed=False, zero=True, target=0.9),
            ),
        ),
    }


def _excursions(
    rows: tuple[CurtailmentRow, ...], settings: CurtailmentSettings
) -> tuple[Excursion, ...]:
    groups: list[tuple[str, list[CurtailmentRow]]] = []
    for row in physical_audit_rows(rows):
        violations = (
            ("ZERO_EXPORT", max(-row.grid_kw, 0.0), row.export_kwh)
            if row.zero_export_requested
            else ("ZERO_EXPORT", 0.0, 0.0),
            (
                "GRID_CHARGE_FORBIDDEN",
                row.grid_to_battery_kwh * HOUR_SECONDS / row.duration_s
                if not row.grid_charge_allowed
                else 0.0,
                row.prohibited_grid_charge_kwh,
            ),
        )
        for kind, power, _energy in violations:
            if power <= POWER_TOL_KW:
                continue
            if (
                groups
                and groups[-1][0] == kind
                and abs(groups[-1][1][-1].end_s - row.start_s) < 1e-7
            ):
                groups[-1][1].append(row)
            else:
                groups.append((kind, [row]))
    outcomes: list[Excursion] = []
    for kind, group in groups:
        peak = max(
            max(-row.grid_kw, 0.0)
            if kind == "ZERO_EXPORT"
            else row.grid_to_battery_kwh * HOUR_SECONDS / row.duration_s
            for row in group
        )
        energy = sum(
            row.export_kwh if kind == "ZERO_EXPORT" else row.prohibited_grid_charge_kwh
            for row in group
        )
        duration = sum(row.duration_s for row in group)
        charge_gate_budget_s = (
            settings.observation_delay_s
            + settings.check_period_s
            + settings.execution_delay_s
        )
        # A PV rise can be observed as available power before the AC output
        # actually finishes slewing.  Include that final actuator delay.
        charge_budget_s = charge_gate_budget_s + (
            settings.pv_ac_max_kw / settings.pv_ramp_kw_per_s
            if settings.pv_ramp_kw_per_s
            else 0.0
        )
        if kind == "GRID_CHARGE_FORBIDDEN":
            within = (
                peak <= settings.battery_parameters.max_charge_power_kw + POWER_TOL_KW
                and duration <= charge_budget_s + 1e-7
                and energy
                <= settings.battery_parameters.max_charge_power_kw
                * charge_budget_s
                / HOUR_SECONDS
                + ENERGY_TOL_KWH
            )
        else:
            within = (
                peak <= settings.export_peak_budget_kw + POWER_TOL_KW
                and duration <= settings.response_budget_s + 1e-7
                and energy <= settings.export_energy_budget_kwh + ENERGY_TOL_KWH
            )
        outcomes.append(
            Excursion(
                kind, group[0].start_s, group[-1].end_s, peak, duration, energy, within
            )
        )
    return tuple(outcomes)


def _event_outcomes(execution: CurtailmentResult) -> tuple[EventOutcome, ...]:
    case = execution.case
    events = sorted(
        {fact.start for fact in case.segments}
        | {decision.at for decision in execution.decisions}
        | {execution.settings.duration_seconds}
    )
    fact_starts = {fact.start for fact in case.segments}
    decision_times = {decision.at for decision in execution.decisions}
    outcomes: list[EventOutcome] = []
    for start, end in pairwise(events):
        fact = next(item for item in case.segments if item.start <= start < item.end)
        event_kind = (
            "FACT_AND_EMS"
            if start in fact_starts and start in decision_times
            else "FACT_CHANGE"
            if start in fact_starts
            else "EMS_TICK"
        )
        # Assign positive-width parent rows BEFORE expanding local parts.
        # A sub-ULP part can round to the common endpoint of two windows;
        # that does not give it ownership in both. Tolerance is not ownership.
        parents = tuple(
            row
            for row in execution.ledger
            if row.start_s >= start
            and row.end_s <= end
            and row.start_s < end
            and row.end_s > start
        )
        rows = physical_audit_rows(parents)
        for constraint, applicable in (
            ("ZERO_EXPORT", fact.zero_export),
            ("GRID_CHARGE_FORBIDDEN", not fact.grid_charge_allowed),
        ):
            if not applicable:
                continue
            violations = tuple(
                row
                for row in rows
                if (
                    max(-row.grid_kw, 0.0)
                    if constraint == "ZERO_EXPORT"
                    else row.grid_to_battery_kwh * HOUR_SECONDS / row.duration_s
                )
                > POWER_TOL_KW
            )
            peak = (
                max(
                    (
                        max(-row.grid_kw, 0.0)
                        if constraint == "ZERO_EXPORT"
                        else row.grid_to_battery_kwh * HOUR_SECONDS / row.duration_s
                    )
                    for row in violations
                )
                if violations
                else 0.0
            )
            energy = sum(
                row.export_kwh
                if constraint == "ZERO_EXPORT"
                else row.prohibited_grid_charge_kwh
                for row in violations
            )
            duration = sum(row.duration_s for row in violations)
            censored = bool(violations and abs(violations[-1].end_s - end) < 1e-7)
            outcomes.append(
                EventOutcome(
                    event_kind,
                    constraint,
                    float(start),
                    float(end),
                    bool(violations),
                    None if censored or not violations else float(violations[-1].end_s),
                    peak,
                    duration,
                    energy,
                    censored,
                )
            )
    return tuple(outcomes)


def run_joint(
    case: Case,
    *,
    mode: str,
    physical_step_s: float,
    record_period_s: float = 60.0,
    display_period_s: float = 5.0,
    context: JointExecutionContext | None = None,
    strategy: RequestStrategy | None = None,
) -> JointResult:
    """Run the accepted executor once under both delayed execution gates."""
    if mode not in {"ideal", "dynamic"}:
        raise ValueError("mode must be ideal or dynamic")
    if strategy is not None and not isinstance(strategy, RequestStrategy):
        raise TypeError("strategy must be a RequestStrategy")
    if context is not None and context.strategy != (
        JOINT if strategy is None else strategy.identifier
    ):
        raise ValueError("context and selected strategy differ")
    settings = replace(
        CurtailmentSettings.ideal() if mode == "ideal" else CurtailmentSettings(),
        strict_startup_observation=True,
        current_pv_surplus_guard=False,
        guard_controlled_pv_rise=True,
    )
    if context is not None:
        settings = replace(
            settings,
            duration_seconds=context.duration_seconds,
            pv_ac_max_kw=context.pv_ac_max_kw,
            battery_parameters=context.battery_parameters,
        )
    execution = run_curtailment(
        case,
        physical_step_s=physical_step_s,
        settings=settings,
        record_period_s=record_period_s,
        display_period_s=display_period_s,
        strategy=strategy,
    )
    excursions = _excursions(execution.ledger, settings)
    event_outcomes = _event_outcomes(execution)
    findings = [
        ConstraintFinding(
            excursion.kind,
            "WITHIN_DYNAMIC_BUDGET" if excursion.within_budget else "FAIL",
            excursion.energy_kwh,
            (
                f"{excursion.start_s:g}-{excursion.end_s:g}s, "
                f"peak {excursion.peak_kw:g} kW"
            ),
        )
        for excursion in excursions
    ]
    reserve_gap = (
        max(
            0.0,
            case.segments[-1].reserve_target_soc - execution.final_soc,
        )
        * settings.battery_parameters.capacity_kwh
    )
    if reserve_gap > ENERGY_TOL_KWH:
        findings.append(
            ConstraintFinding(
                "SOFT_RESERVE_UNMET",
                "SOFT_TARGET",
                reserve_gap,
                "The reserve target is not an instantaneous hard constraint.",
            )
        )
    return JointResult(
        execution,
        excursions,
        event_outcomes,
        tuple(findings),
        all(excursion.within_budget for excursion in excursions)
        and (mode != "ideal" or not excursions),
    )


def write_evidence(result: JointResult, output: Path) -> None:
    """Save one execution ledger plus joint findings and request/actual plot."""
    write_execution_evidence(result.execution, output)
    with (output / "constraint-findings.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=tuple(ConstraintFinding.__dataclass_fields__)
        )
        writer.writeheader()
        writer.writerows(asdict(item) for item in result.findings)
    with (output / "excursions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=tuple(Excursion.__dataclass_fields__)
        )
        writer.writeheader()
        writer.writerows(asdict(item) for item in result.excursions)
    with (output / "event-outcomes.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=tuple(EventOutcome.__dataclass_fields__)
        )
        writer.writeheader()
        writer.writerows(asdict(item) for item in result.event_outcomes)
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width="1000",
        height="360",
        viewBox="0 0 1000 360",
    )
    for label, field, color in (
        ("EMS request", "original_request_kw", "#555555"),
        ("execution request", "constrained_request_kw", "#b17800"),
        ("actual battery", "actual_battery_kw", "#2763a4"),
        ("delivered PV", "delivered_pv_kw", "#218750"),
    ):
        points = " ".join(
            f"{30 + row.end_s / result.execution.settings.duration_seconds * 940:.2f},"
            f"{190 - getattr(row, field) * 25:.2f}"
            for row in result.execution.ledger
        )
        line = ET.SubElement(root, "polyline", points=points, fill="none", stroke=color)
        line.set("stroke-width", "2")
        ET.SubElement(
            root, "text", x="30", y=str(24 + 20 * len(root)), fill=color
        ).text = label
    ET.ElementTree(root).write(output / "request-actual.svg", encoding="unicode")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=tuple(scenarios()))
    parser.add_argument("--mode", required=True, choices=("ideal", "dynamic"))
    parser.add_argument("--step", required=True, type=float)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = run_joint(
        scenarios()[args.case], mode=args.mode, physical_step_s=args.step
    )
    write_evidence(result, args.output)
    if not result.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
