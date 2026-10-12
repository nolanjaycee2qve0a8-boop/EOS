"""Test-only periodic grid-charge interlock over frozen time-energy physics."""

import argparse
import csv
from dataclasses import asdict, dataclass
from itertools import pairwise
from pathlib import Path
from xml.etree import ElementTree as ET

from ems_simulator.time_energy import (
    PowerInterval,
    SimulationCadences,
    TimeEnergyInput,
    simulate_time_energy,
)
from tools.dynamic_constraint_probe import (
    DURATION_SECONDS,
    HOUR_SECONDS,
    Case,
    FactSegment,
    _fact_at,
    _request,
    battery,
)
from tools.dynamic_constraint_probe import (
    cases as predecessor_cases,
)


@dataclass(frozen=True, slots=True)
class InterlockSettings:
    check_period_s: int = 60
    observation_delay_s: int = 20
    execution_delay_s: int = 10

    def __post_init__(self) -> None:
        if type(self.check_period_s) is not int or self.check_period_s <= 0:
            raise ValueError("check_period_s must be a positive integer")
        if DURATION_SECONDS % self.check_period_s:
            raise ValueError("check period must divide scenario duration")
        for name in ("observation_delay_s", "execution_delay_s"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")

    @property
    def latency_budget_s(self) -> int:
        return self.observation_delay_s + self.check_period_s + self.execution_delay_s


@dataclass(frozen=True, slots=True)
class ExecutionCheck:
    check_at: int
    sampled_at: int
    effect_at: int
    observed_permission: bool
    observed_surplus_kw: float


@dataclass(frozen=True, slots=True)
class GateTransition:
    effective_at: int
    source_check_at: int
    source_sampled_at: int
    permission: bool


@dataclass(frozen=True, slots=True)
class EMSDecision:
    at: int
    feedback_soc: float
    original_request_kw: float


@dataclass(frozen=True, slots=True)
class ExecutionSpan:
    start: int
    end: int
    fact: FactSegment
    original_request_kw: float
    constrained_request_kw: float
    effective_permission: bool
    observed_surplus_kw: float
    source_sampled_at: int
    effect_at: int
    reason: str


@dataclass(frozen=True, slots=True)
class InterlockLedgerRow:
    start_s: float
    end_s: float
    original_request_kw: float
    constrained_request_kw: float
    actual_battery_kw: float
    load_kw: float
    pv_kw: float
    grid_kw: float
    source_permission: bool
    effective_permission: bool
    observed_surplus_kw: float
    source_sampled_at: int
    effect_at: int
    reason: str
    soc_before: float
    soc_after: float
    load_kwh: float
    pv_kwh: float
    battery_kwh: float
    import_kwh: float
    export_kwh: float
    grid_to_battery_kwh: float
    pv_to_battery_kwh: float
    normal_load_import_kwh: float
    prohibited_grid_charge_kwh: float
    storage_delta_kwh: float
    conversion_loss_kwh: float
    curtailed_pv_kwh: float


@dataclass(frozen=True, slots=True)
class RevocationOutcome:
    source_revoke_at: int
    effective_off_at: int | None
    initial_grid_charge_stop_at: float | None
    initial_stop_delay_s: float | None
    lag_violation_kwh: float
    post_gate_transient_kwh: float
    steady_residual_kwh: float | None
    budget_s: int
    budget_kwh: float


@dataclass(frozen=True, slots=True)
class SurplusLossOutcome:
    source_change_at: int
    observed_effect_at: int | None
    actual_grid_charge_stop_at: float | None
    stop_delay_s: float | None
    transient_violation_kwh: float
    steady_residual_kwh: float | None
    budget_s: int
    budget_kwh: float


@dataclass(frozen=True, slots=True)
class InterlockResult:
    case: Case
    settings: InterlockSettings
    physical_step_s: float
    control_period_s: int
    record_period_s: float
    display_period_s: float
    ems_decisions: tuple[EMSDecision, ...]
    execution_checks: tuple[ExecutionCheck, ...]
    gate_transitions: tuple[GateTransition, ...]
    ledger: tuple[InterlockLedgerRow, ...]
    revocations: tuple[RevocationOutcome, ...]
    surplus_losses: tuple[SurplusLossOutcome, ...]
    final_soc: float


def scenarios() -> dict[str, Case]:
    def seg(
        start: int,
        end: int,
        load: float,
        pv: float,
        allowed: bool,
        target: float = 0.8,
        zero_export: bool = False,
    ) -> FactSegment:
        return FactSegment(start, end, load, pv, allowed, zero_export, target)

    return {
        "no_pv_revoke": Case(
            "no_pv_revoke",
            predecessor_cases()["permission_mid_tick"].initial_soc,
            predecessor_cases()["permission_mid_tick"].segments,
        ),
        "pv_insufficient": Case(
            "pv_insufficient",
            0.3,
            (seg(0, 1800, 2, 1, True), seg(1800, 7200, 2, 1, False)),
        ),
        "pv_surplus": Case(
            "pv_surplus",
            0.3,
            (seg(0, 1800, 1, 3, True), seg(1800, 7200, 1, 3, False)),
        ),
        "pv_loss_while_revoked": Case(
            "pv_loss_while_revoked",
            0.3,
            (
                seg(0, 1800, 1, 3, True),
                seg(1800, 2000, 1, 3, False),
                seg(2000, 7200, 1, 0, False),
            ),
        ),
        "pv_loss_policy_marker": Case(
            "pv_loss_policy_marker",
            0.3,
            (
                seg(0, 1800, 1, 3, True),
                seg(1800, 2000, 1, 3, False),
                seg(2000, 2020, 1, 0, False),
                seg(2020, 7200, 1, 0, False, 0.9),
            ),
        ),
        "pv_loss_same_surplus_marker": Case(
            "pv_loss_same_surplus_marker",
            0.3,
            (
                seg(0, 1800, 1, 3, True),
                seg(1800, 2000, 1, 3, False),
                seg(2000, 2020, 1, 2, False),
                seg(2020, 7200, 2, 3, False),
            ),
        ),
        "pv_loss_on_prior_effect": Case(
            "pv_loss_on_prior_effect",
            0.3,
            (
                seg(0, 1800, 1, 3, True),
                seg(1800, 2000, 1, 3, False),
                seg(2000, 2050, 1, 2, False),
                seg(2050, 7200, 1, 1, False),
            ),
        ),
        "late_revoke": Case(
            "late_revoke",
            0.2,
            (seg(0, 7190, 1, 0, True, 1.0), seg(7190, 7200, 1, 0, False, 1.0)),
        ),
        "late_pv_loss": Case(
            "late_pv_loss",
            0.2,
            (
                seg(0, 1800, 1, 3, True, 1.0),
                seg(1800, 7190, 1, 3, False, 1.0),
                seg(7190, 7200, 1, 0, False, 1.0),
            ),
        ),
        "normal_load_import": Case(
            "normal_load_import", 0.2, (seg(0, 7200, 2, 0, False, 0.2),)
        ),
        "revoke_restore": Case(
            "revoke_restore",
            0.3,
            (
                seg(0, 1800, 1, 0, True),
                seg(1800, 3000, 1, 0, False),
                seg(3000, 7200, 1, 0, True),
            ),
        ),
        "repeat_revoke": Case(
            "repeat_revoke",
            0.3,
            (
                seg(0, 1800, 1, 0, True),
                seg(1800, 2400, 1, 0, False),
                seg(2400, 7200, 1, 0, False),
            ),
        ),
        "check_boundary": Case(
            "check_boundary",
            0.3,
            (seg(0, 1800, 1, 0, True), seg(1800, 7200, 1, 0, False)),
        ),
        "soc_upper_boundary": Case(
            "soc_upper_boundary",
            0.99,
            (seg(0, 1800, 1, 0, True, 1.0), seg(1800, 7200, 1, 0, False, 1.0)),
        ),
        "simultaneous": predecessor_cases()["simultaneous"],
    }


def _checks(case: Case, settings: InterlockSettings) -> tuple[ExecutionCheck, ...]:
    checks: list[ExecutionCheck] = []
    for check_at in range(0, DURATION_SECONDS, settings.check_period_s):
        sampled_at = max(0, check_at - settings.observation_delay_s)
        fact = _fact_at(case, sampled_at)
        checks.append(
            ExecutionCheck(
                check_at,
                sampled_at,
                check_at + settings.execution_delay_s,
                fact.grid_charge_allowed,
                max(0.0, fact.pv_kw - fact.load_kw),
            )
        )
    return tuple(checks)


def _source_revokes(case: Case) -> tuple[int, ...]:
    return tuple(
        current.start
        for previous, current in zip(case.segments, case.segments[1:], strict=False)
        if previous.grid_charge_allowed and not current.grid_charge_allowed
    )


def _source_restore_after(case: Case, revoke_at: int) -> int:
    for fact in case.segments:
        if fact.start > revoke_at and fact.grid_charge_allowed:
            return fact.start
    return DURATION_SECONDS


def _revocation_outcomes(
    case: Case,
    settings: InterlockSettings,
    transitions: tuple[GateTransition, ...],
    ledger: tuple[InterlockLedgerRow, ...],
) -> tuple[RevocationOutcome, ...]:
    outcomes: list[RevocationOutcome] = []
    checks = _checks(case, settings)
    for revoke_at in _source_revokes(case):
        restore_at = _source_restore_after(case, revoke_at)
        effect_at = next(
            (
                transition.effective_at
                for transition in transitions
                if revoke_at <= transition.effective_at < restore_at
                and not transition.permission
            ),
            None,
        )
        violating = [
            row
            for row in ledger
            if revoke_at <= row.start_s < restore_at and row.grid_to_battery_kwh > 0
        ]
        lag_end = float(effect_at if effect_at is not None else restore_at)
        initial_stop_at = (
            max(
                (row.end_s for row in violating if row.start_s < lag_end),
                default=float(revoke_at),
            )
            if effect_at is not None
            else None
        )
        last_change = max(
            fact.start for fact in case.segments if revoke_at <= fact.start < restore_at
        )
        first_settled_at = next(
            (check.effect_at for check in checks if check.sampled_at >= last_change),
            restore_at,
        )
        settled_at = max(float(first_settled_at), lag_end)
        settled_in_window = first_settled_at < restore_at
        lag_energy = sum(
            row.grid_to_battery_kwh for row in violating if row.start_s < lag_end
        )
        post_gate_transient = sum(
            row.grid_to_battery_kwh
            for row in violating
            if lag_end <= row.start_s < settled_at
        )
        residual = sum(
            row.grid_to_battery_kwh for row in violating if row.start_s >= settled_at
        )
        outcomes.append(
            RevocationOutcome(
                revoke_at,
                effect_at,
                initial_stop_at,
                initial_stop_at - revoke_at if initial_stop_at is not None else None,
                lag_energy,
                post_gate_transient,
                residual if settled_in_window else None,
                settings.latency_budget_s,
                battery().max_charge_power_kw
                * settings.latency_budget_s
                / HOUR_SECONDS,
            )
        )
    return tuple(outcomes)


def _surplus_loss_outcomes(
    case: Case,
    settings: InterlockSettings,
    ledger: tuple[InterlockLedgerRow, ...],
) -> tuple[SurplusLossOutcome, ...]:
    outcomes: list[SurplusLossOutcome] = []
    checks = _checks(case, settings)
    for previous, current in pairwise(case.segments):
        previous_surplus = max(previous.pv_kw - previous.load_kw, 0.0)
        current_surplus = max(current.pv_kw - current.load_kw, 0.0)
        if (
            previous.grid_charge_allowed
            or current.grid_charge_allowed
            or current_surplus >= previous_surplus
        ):
            continue
        effect_at = next(
            (
                check.effect_at
                for check in checks
                if check.sampled_at >= current.start
                and check.effect_at < DURATION_SECONDS
            ),
            None,
        )
        restore_at = _source_restore_after(case, current.start)
        window_end = min(restore_at, effect_at or restore_at)
        transient = [
            row
            for row in ledger
            if current.start <= row.start_s < window_end and row.grid_to_battery_kwh > 0
        ]
        stopped_at = (
            max((row.end_s for row in transient), default=float(current.start))
            if effect_at is not None and effect_at <= restore_at
            else None
        )
        next_loss_after_effect = next(
            (
                later.start
                for earlier, later in pairwise(case.segments)
                if later.start >= window_end
                and not earlier.grid_charge_allowed
                and not later.grid_charge_allowed
                and max(later.pv_kw - later.load_kw, 0.0)
                < max(earlier.pv_kw - earlier.load_kw, 0.0)
            ),
            restore_at,
        )
        settled_residual = sum(
            row.grid_to_battery_kwh
            for row in ledger
            if window_end <= row.start_s < min(restore_at, next_loss_after_effect)
        )
        outcomes.append(
            SurplusLossOutcome(
                current.start,
                effect_at,
                stopped_at,
                stopped_at - current.start if stopped_at is not None else None,
                sum(row.grid_to_battery_kwh for row in transient),
                settled_residual if stopped_at is not None else None,
                settings.latency_budget_s,
                battery().max_charge_power_kw
                * settings.latency_budget_s
                / HOUR_SECONDS,
            )
        )
    return tuple(outcomes)


def run_interlock(
    case: Case,
    *,
    physical_step_s: float,
    settings: InterlockSettings | None = None,
    control_period_s: int = HOUR_SECONDS,
    record_period_s: float = 60.0,
    display_period_s: float = 5.0,
) -> InterlockResult:
    if settings is None:
        settings = InterlockSettings()
    if type(control_period_s) is not int or control_period_s <= 0:
        raise ValueError("control period must be a positive integer")
    if DURATION_SECONDS % control_period_s:
        raise ValueError("control period must divide duration")
    expected = 0
    for fact in case.segments:
        if fact.start != expected or fact.end <= fact.start:
            raise ValueError("external facts must be contiguous and advancing")
        expected = fact.end
    if expected != DURATION_SECONDS:
        raise ValueError("external facts must cover duration")

    parameters = battery()
    checks = _checks(case, settings)
    effects: dict[int, list[ExecutionCheck]] = {}
    for check in checks:
        if check.effect_at < DURATION_SECONDS:
            effects.setdefault(check.effect_at, []).append(check)
    boundaries = {0, DURATION_SECONDS}
    boundaries.update(range(0, DURATION_SECONDS, control_period_s))
    boundaries.update(check.check_at for check in checks)
    boundaries.update(effects)
    boundaries.update(fact.start for fact in case.segments)
    boundaries.update(fact.end for fact in case.segments)
    timeline = sorted(boundaries)

    effective_permission = case.segments[0].grid_charge_allowed
    observed_surplus = max(0.0, case.segments[0].pv_kw - case.segments[0].load_kw)
    last_sampled_at = 0
    last_effect_at = 0
    latched_old_request = False
    original_request = 0.0
    soc = case.initial_soc
    ems: list[EMSDecision] = []
    transitions: list[GateTransition] = []
    rows: list[InterlockLedgerRow] = []

    for tick in range(0, DURATION_SECONDS, control_period_s):
        tick_end = tick + control_period_s
        points = [point for point in timeline if tick <= point <= tick_end]
        spans: list[ExecutionSpan] = []
        for start, end in pairwise(points):
            # Facts at start are right-continuous. Effects due at the same time
            # mature before any fresh EMS request at that scheduled tick.
            for check in effects.get(start, ()):
                if effective_permission != check.observed_permission:
                    transitions.append(
                        GateTransition(
                            start,
                            check.check_at,
                            check.sampled_at,
                            check.observed_permission,
                        )
                    )
                    if effective_permission and not check.observed_permission:
                        latched_old_request = True
                effective_permission = check.observed_permission
                observed_surplus = check.observed_surplus_kw
                last_sampled_at = check.sampled_at
                last_effect_at = start

            fact = _fact_at(case, start)
            if start == tick:
                original_request = _request(fact, soc, parameters)
                latched_old_request = bool(
                    original_request > 0 and not effective_permission
                )
                ems.append(EMSDecision(tick, soc, original_request))

            if original_request <= 0:
                constrained = original_request
                reason = "NON_CHARGE"
            elif effective_permission and not latched_old_request:
                constrained = original_request
                reason = "PERMITTED_FRESH_REQUEST"
            else:
                constrained = min(original_request, observed_surplus)
                reason = (
                    "PV_ONLY_WHILE_REVOKED"
                    if not effective_permission
                    else "RESTORED_AWAIT_FRESH_EMS"
                )
            spans.append(
                ExecutionSpan(
                    start,
                    end,
                    fact,
                    original_request,
                    constrained,
                    effective_permission,
                    observed_surplus,
                    last_sampled_at,
                    last_effect_at,
                    reason,
                )
            )

        physical = simulate_time_energy(
            TimeEnergyInput(
                SimulationCadences(
                    physical_step_s,
                    float(control_period_s),
                    3600.0,
                    record_period_s,
                    display_period_s,
                ),
                tuple(
                    PowerInterval(
                        span.start - tick,
                        span.end - tick,
                        span.fact.load_kw,
                        span.fact.pv_kw,
                        span.constrained_request_kw,
                    )
                    for span in spans
                ),
                parameters,
                soc,
            )
        )
        span_index = 0
        for physical_slice in physical.slices:
            slice_start = tick + physical_slice.start_seconds
            slice_end = tick + physical_slice.end_seconds
            while span_index + 1 < len(spans) and slice_start >= spans[span_index].end:
                span_index += 1
            span = spans[span_index]
            if slice_start < span.start or slice_end > span.end + 1e-9:
                raise AssertionError("physical slice crossed an execution boundary")
            hours = (slice_end - slice_start) / HOUR_SECONDS
            actual = physical_slice.actual_battery_power_kw
            grid = physical_slice.grid_power_kw
            grid_charge_kw = max(
                0.0, actual - max(span.fact.pv_kw - span.fact.load_kw, 0.0)
            )
            pv_charge_kw = max(actual, 0.0) - grid_charge_kw
            battery_kwh = actual * hours
            storage_delta = (
                physical_slice.soc_after - physical_slice.soc_before
            ) * parameters.capacity_kwh
            import_kwh = max(grid, 0.0) * hours
            grid_charge_kwh = grid_charge_kw * hours
            rows.append(
                InterlockLedgerRow(
                    slice_start,
                    slice_end,
                    span.original_request_kw,
                    span.constrained_request_kw,
                    actual,
                    span.fact.load_kw,
                    span.fact.pv_kw,
                    grid,
                    span.fact.grid_charge_allowed,
                    span.effective_permission,
                    span.observed_surplus_kw,
                    span.source_sampled_at,
                    span.effect_at,
                    span.reason,
                    physical_slice.soc_before,
                    physical_slice.soc_after,
                    span.fact.load_kw * hours,
                    span.fact.pv_kw * hours,
                    battery_kwh,
                    import_kwh,
                    max(-grid, 0.0) * hours,
                    grid_charge_kwh,
                    pv_charge_kw * hours,
                    import_kwh - grid_charge_kwh,
                    grid_charge_kwh if not span.fact.grid_charge_allowed else 0.0,
                    storage_delta,
                    battery_kwh - storage_delta,
                    0.0,
                )
            )
        soc = physical.final_soc

    complete_rows = tuple(rows)
    complete_transitions = tuple(transitions)
    return InterlockResult(
        case,
        settings,
        physical_step_s,
        control_period_s,
        record_period_s,
        display_period_s,
        tuple(ems),
        checks,
        complete_transitions,
        complete_rows,
        _revocation_outcomes(case, settings, complete_transitions, complete_rows),
        _surplus_loss_outcomes(case, settings, complete_rows),
        soc,
    )


def _csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _svg_curve(result: InterlockResult, path: Path) -> None:
    """Plot held request, constrained request, actual and SOC in simulation time."""
    width, height = 1000, 480
    left, right, top, bottom = 78, 24, 72, 42
    plot_width = width - left - right
    power_mid = 190
    power_scale = 32
    soc_top, soc_bottom = 315, height - bottom

    def x(seconds: float) -> float:
        return left + seconds / DURATION_SECONDS * plot_width

    def power_y(power: float) -> float:
        return power_mid - power * power_scale

    def soc_y(soc: float) -> float:
        return soc_bottom - soc * (soc_bottom - soc_top)

    root = ET.Element(
        "svg",
        {
            "xmlns": "http://www.w3.org/2000/svg",
            "width": str(width),
            "height": str(height),
            "viewBox": f"0 0 {width} {height}",
        },
    )
    ET.SubElement(root, "rect", {"width": "100%", "height": "100%", "fill": "white"})

    def label(y: int, content: str) -> None:
        ET.SubElement(
            root,
            "text",
            {"x": str(left), "y": str(y), "font-family": "sans-serif"},
        ).text = content

    label(25, f"{result.case.name}: periodic charge interlock (simulation only)")
    label(
        46,
        "power axis kW: request=gray; constrained=orange; actual=blue; "
        "model grid-to-battery=red; SOC 0-1=green",
    )
    label(height - 12, "0 s                                                 7200 s")
    ET.SubElement(
        root,
        "line",
        {
            "x1": str(left),
            "x2": str(width - right),
            "y1": str(power_mid),
            "y2": str(power_mid),
            "stroke": "#999",
        },
    )
    for event in result.case.segments[1:]:
        ET.SubElement(
            root,
            "line",
            {
                "x1": f"{x(event.start):.2f}",
                "x2": f"{x(event.start):.2f}",
                "y1": str(top),
                "y2": str(soc_bottom),
                "stroke": "#bbb",
                "stroke-dasharray": "4 4",
            },
        )
    for field, color in (
        ("original_request_kw", "#666666"),
        ("constrained_request_kw", "#d4821b"),
        ("actual_battery_kw", "#2671b7"),
        ("grid_to_battery_kwh", "#c53030"),
    ):
        points: list[str] = []
        for row in result.ledger:
            value = getattr(row, field)
            if field == "grid_to_battery_kwh":
                value *= HOUR_SECONDS / (row.end_s - row.start_s)
            points.extend(
                [
                    f"{x(row.start_s):.2f},{power_y(value):.2f}",
                    f"{x(row.end_s):.2f},{power_y(value):.2f}",
                ]
            )
        ET.SubElement(
            root,
            "polyline",
            {
                "points": " ".join(points),
                "fill": "none",
                "stroke": color,
                "stroke-width": "2",
            },
        )
    soc_points = [
        f"{x(result.ledger[0].start_s):.2f},{soc_y(result.ledger[0].soc_before):.2f}"
    ]
    soc_points.extend(
        f"{x(row.end_s):.2f},{soc_y(row.soc_after):.2f}" for row in result.ledger
    )
    ET.SubElement(
        root,
        "polyline",
        {
            "points": " ".join(soc_points),
            "fill": "none",
            "stroke": "#2f8a47",
            "stroke-width": "2",
        },
    )
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=False)
    results = [
        run_interlock(case, physical_step_s=step)
        for case in scenarios().values()
        for step in (3600.0, 60.0, 15.0)
    ]
    summaries: list[dict[str, object]] = []
    ledger: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    checks: list[dict[str, object]] = []
    transitions: list[dict[str, object]] = []
    revocations: list[dict[str, object]] = []
    surplus_losses: list[dict[str, object]] = []
    for result in results:
        key: dict[str, object] = {
            "case": result.case.name,
            "physical_step_s": result.physical_step_s,
        }
        summaries.append(
            {
                **key,
                "ems_decisions": len(result.ems_decisions),
                "execution_checks": len(result.execution_checks),
                "gate_transitions": len(result.gate_transitions),
                "final_soc": result.final_soc,
                "import_kwh": sum(row.import_kwh for row in result.ledger),
                "export_kwh": sum(row.export_kwh for row in result.ledger),
                "prohibited_grid_charge_kwh": sum(
                    row.prohibited_grid_charge_kwh for row in result.ledger
                ),
                "curtailed_pv_kwh": 0.0,
            }
        )
        ledger.extend({**key, **asdict(row)} for row in result.ledger)
        decisions.extend({**key, **asdict(row)} for row in result.ems_decisions)
        checks.extend({**key, **asdict(row)} for row in result.execution_checks)
        transitions.extend({**key, **asdict(row)} for row in result.gate_transitions)
        revocations.extend({**key, **asdict(row)} for row in result.revocations)
        surplus_losses.extend({**key, **asdict(row)} for row in result.surplus_losses)
        if result.physical_step_s == 60.0:
            _svg_curve(
                result,
                arguments.output_dir / f"{result.case.name}_curve.svg",
            )
    for name, rows in (
        ("summary.csv", summaries),
        ("ledger.csv", ledger),
        ("ems_decisions.csv", decisions),
        ("execution_checks.csv", checks),
        ("gate_transitions.csv", transitions),
        ("revocations.csv", revocations),
        ("surplus_losses.csv", surplus_losses),
    ):
        _csv(arguments.output_dir / name, rows)
    for summary in summaries:
        print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
