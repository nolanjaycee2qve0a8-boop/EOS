"""Test-only AC-bus PV curtailment and Zero Export execution experiment.

The existing hourly EMS request and time-energy physics are not modified.  PV
availability is an external fact; this executor controls only the AC PV
injection cap and the battery request passed to the frozen physics function.
"""

import argparse
import csv
from dataclasses import asdict, dataclass
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
from tools.dynamic_constraint_probe import cases as predecessor_cases


@dataclass(frozen=True, slots=True)
class CurtailmentSettings:
    check_period_s: int = 60
    observation_delay_s: int = 20
    execution_delay_s: int = 10
    pv_ac_max_kw: float = 5.0
    pv_ramp_kw_per_s: float = 1.0

    def __post_init__(self) -> None:
        if type(self.check_period_s) is not int or self.check_period_s <= 0:
            raise ValueError("check period must be a positive integer")
        if DURATION_SECONDS % self.check_period_s:
            raise ValueError("check period must divide scenario duration")
        for field in ("observation_delay_s", "execution_delay_s"):
            value = getattr(self, field)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field} must be a non-negative integer")
        if self.pv_ac_max_kw <= 0 or self.pv_ramp_kw_per_s < 0:
            raise ValueError("PV rating must be positive and ramp non-negative")

    @classmethod
    def ideal(cls) -> "CurtailmentSettings":
        return cls(60, 0, 0, 5.0, 0.0)

    @property
    def response_budget_s(self) -> float:
        ramp_s = (
            self.pv_ac_max_kw / self.pv_ramp_kw_per_s if self.pv_ramp_kw_per_s else 0.0
        )
        return (
            self.check_period_s
            + self.observation_delay_s
            + self.execution_delay_s
            + ramp_s
        )

    @property
    def export_peak_budget_kw(self) -> float:
        return self.pv_ac_max_kw + battery().max_discharge_power_kw

    @property
    def export_energy_budget_kwh(self) -> float:
        return self.export_peak_budget_kw * self.response_budget_s / HOUR_SECONDS


@dataclass(frozen=True, slots=True)
class ExecutionCheck:
    check_at: int
    sampled_at: int
    effect_at: int
    observed_load_kw: float
    observed_available_pv_kw: float
    observed_permission: bool
    observed_zero_export: bool


@dataclass(frozen=True, slots=True)
class EMSDecision:
    at: int
    feedback_soc: float
    original_request_kw: float


@dataclass(frozen=True, slots=True)
class CurtailmentRow:
    start_s: float
    end_s: float
    original_request_kw: float
    constrained_request_kw: float
    actual_battery_kw: float
    available_pv_kw: float
    delivered_pv_kw: float
    curtailed_pv_kw: float
    pv_cap_kw: float
    load_kw: float
    grid_kw: float
    grid_charge_allowed: bool
    effective_permission: bool
    zero_export_requested: bool
    effective_zero_export: bool
    reserve_target_soc: float
    soc_before: float
    soc_after: float
    available_pv_kwh: float
    delivered_pv_kwh: float
    curtailed_pv_kwh: float
    load_kwh: float
    battery_kwh: float
    import_kwh: float
    export_kwh: float
    grid_to_battery_kwh: float
    prohibited_grid_charge_kwh: float
    storage_delta_kwh: float
    conversion_loss_kwh: float


@dataclass(frozen=True, slots=True)
class CurtailmentResult:
    case: Case
    settings: CurtailmentSettings
    physical_step_s: float
    control_period_s: int
    record_period_s: float
    decisions: tuple[EMSDecision, ...]
    checks: tuple[ExecutionCheck, ...]
    ledger: tuple[CurtailmentRow, ...]
    final_soc: float
    export_peak_kw: float
    export_duration_s: float
    export_kwh: float


def scenarios() -> dict[str, Case]:
    def seg(
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

    return {
        "full_battery": predecessor_cases()["full_battery"],
        "pv_jump": predecessor_cases()["pv_jump"],
        "full_pv_jump": Case(
            "full_pv_jump",
            1.0,
            (seg(0, 1800, 1, 0, zero=False), seg(1800, 7200, 1, 5)),
        ),
        "load_drop": predecessor_cases()["load_drop"],
        "charge_limit": Case("charge_limit", 0.5, (seg(0, 7200, 1, 5),)),
        "pv_and_battery": Case(
            "pv_and_battery",
            0.8,
            (seg(0, 1800, 3, 0, target=0.2), seg(1800, 7200, 3, 1, target=0.2)),
        ),
        "pv_loss": Case(
            "pv_loss",
            0.5,
            (seg(0, 1800, 1, 5), seg(1800, 7200, 1, 0)),
        ),
        "mode_switch": Case(
            "mode_switch",
            1.0,
            (seg(0, 1800, 1, 5, zero=False), seg(1800, 7200, 1, 5)),
        ),
        "permission_reserve": Case(
            "permission_reserve",
            0.3,
            (
                seg(0, 1800, 1, 0, allowed=True, zero=False, target=0.8),
                seg(1800, 7200, 1, 5, allowed=False, target=0.9),
            ),
        ),
        "battery_only_export": Case(
            "battery_only_export",
            0.8,
            (seg(0, 1800, 3, 0), seg(1800, 7200, 0, 0)),
        ),
        "simultaneous": predecessor_cases()["simultaneous"],
    }


def _checks(case: Case, settings: CurtailmentSettings) -> tuple[ExecutionCheck, ...]:
    check_times = set(range(0, DURATION_SECONDS, settings.check_period_s))
    if settings.observation_delay_s == 0 and settings.execution_delay_s == 0:
        check_times.update(fact.start for fact in case.segments)
    return tuple(
        ExecutionCheck(
            check_at,
            max(0, check_at - settings.observation_delay_s),
            check_at + settings.execution_delay_s,
            fact.load_kw,
            fact.pv_kw,
            fact.grid_charge_allowed,
            fact.zero_export,
        )
        for check_at in sorted(check_times)
        for fact in (_fact_at(case, max(0, check_at - settings.observation_delay_s)),)
    )


def _move_cap(current: float, target: float, settings: CurtailmentSettings) -> float:
    if settings.pv_ramp_kw_per_s == 0:
        return target
    delta = settings.pv_ramp_kw_per_s
    return (
        max(target, current - delta)
        if target < current
        else min(target, current + delta)
    )


def _soc_boundary_seconds(soc: float, request: float) -> float | None:
    params = battery()
    if request > 0 and soc < 1:
        return (
            (1 - soc)
            * params.capacity_kwh
            * HOUR_SECONDS
            / (request * params.charge_efficiency)
        )
    if request < 0 and soc > params.reserve_soc:
        return (
            (soc - params.reserve_soc)
            * params.capacity_kwh
            * params.discharge_efficiency
            * HOUR_SECONDS
            / -request
        )
    return None


def run_curtailment(
    case: Case,
    *,
    physical_step_s: float,
    settings: CurtailmentSettings | None = None,
    control_period_s: int = HOUR_SECONDS,
    record_period_s: float = 60.0,
    display_period_s: float = 5.0,
) -> CurtailmentResult:
    """Run one deterministic scenario; no command or device authority is created."""
    settings = settings or CurtailmentSettings()
    if (
        type(control_period_s) is not int
        or control_period_s <= 0
        or DURATION_SECONDS % control_period_s
    ):
        raise ValueError("control period must divide scenario duration")
    expected = 0
    for fact in case.segments:
        if fact.start != expected or fact.end <= fact.start:
            raise ValueError("facts must be contiguous and advancing")
        if fact.pv_kw > settings.pv_ac_max_kw:
            raise ValueError("available PV exceeds explicit AC PV rating")
        expected = fact.end
    if expected != DURATION_SECONDS:
        raise ValueError("facts must cover scenario duration")

    params = battery()
    checks = _checks(case, settings)
    effects = {
        check.effect_at: check for check in checks if check.effect_at < DURATION_SECONDS
    }
    event_times = {0, DURATION_SECONDS}
    event_times.update(range(0, DURATION_SECONDS, control_period_s))
    event_times.update(fact.start for fact in case.segments)
    event_times.update(effects)
    timeline = sorted(event_times)
    soc = case.initial_soc
    now = 0.0
    # No source measurement has matured at startup.  Until the first effect,
    # neither PV injection nor battery execution receives authority.
    pv_cap = 0.0
    target_pv_cap = pv_cap
    ramp_due_at: float | None = None
    original_request = 0.0
    constrained = 0.0
    battery_target = 0.0
    initial = case.segments[0]
    pv_output_kw = 0.0
    output_ramp_due_at: float | None = None
    observed = initial
    effective_permission = False
    effective_zero = True
    has_observation = False
    latched_old_request = False
    decisions: list[EMSDecision] = []
    rows: list[CurtailmentRow] = []
    retarget_on_soc = False

    while now < DURATION_SECONDS:
        # At a simultaneous boundary: external facts become right-continuous,
        # matured observations apply, then the scheduled EMS decision is made.
        at_event = int(now) == now and now in event_times
        check = effects.get(int(now)) if at_event else None
        if check is not None:
            prior_permission = effective_permission
            observed = _fact_at(case, check.sampled_at)
            effective_permission = check.observed_permission
            effective_zero = check.observed_zero_export
            has_observation = True
            if prior_permission and not effective_permission:
                latched_old_request = True
        if at_event and int(now) % control_period_s == 0:
            fact = _fact_at(case, now)
            original_request = _request(fact, soc, params)
            latched_old_request = original_request > 0 and not effective_permission
            decisions.append(EMSDecision(int(now), soc, original_request))

        fact = _fact_at(case, now)
        update_target = has_observation and (
            check is not None
            or (at_event and int(now) % control_period_s == 0)
            or retarget_on_soc
        )
        prior_target_pv_cap = target_pv_cap
        if update_target:
            if original_request > 0 and (
                not effective_permission or latched_old_request
            ):
                battery_target = min(
                    original_request, max(observed.pv_kw - observed.load_kw, 0.0)
                )
            else:
                battery_target = original_request
            if effective_zero:
                # Prioritize PV for load; discharge cannot export by itself.
                if battery_target < 0:
                    battery_target = max(
                        battery_target,
                        -max(
                            observed.load_kw - min(observed.pv_kw, observed.load_kw),
                            0.0,
                        ),
                    )
                charge_absorption = battery_target if soc < 1.0 - 1e-12 else 0.0
                target_pv_cap = max(
                    0.0,
                    min(settings.pv_ac_max_kw, observed.load_kw + charge_absorption),
                )
            else:
                target_pv_cap = settings.pv_ac_max_kw
        retarget_on_soc = False

        # A nonzero ramp waits one complete simulated second before each
        # 1-kW/s actuator step.  No power change is backdated to the event.
        if settings.pv_ramp_kw_per_s == 0:
            pv_cap = target_pv_cap
        else:
            if target_pv_cap != prior_target_pv_cap:
                ramp_due_at = now + 1.0 if pv_cap != target_pv_cap else None
            elif ramp_due_at is not None and now >= ramp_due_at:
                pv_cap = _move_cap(pv_cap, target_pv_cap, settings)
                ramp_due_at = now + 1.0 if pv_cap != target_pv_cap else None

        desired_pv = min(fact.pv_kw, pv_cap)
        if settings.pv_ramp_kw_per_s == 0:
            pv_output_kw = desired_pv
            output_ramp_due_at = None
        elif desired_pv < pv_output_kw:
            # Irradiance loss can force an immediate decrease; commanded cap
            # reductions have already been limited by the AC cap slew.
            pv_output_kw = desired_pv
            output_ramp_due_at = None
        elif desired_pv > pv_output_kw:
            if output_ramp_due_at is None:
                output_ramp_due_at = now + 1.0
            elif now >= output_ramp_due_at:
                pv_output_kw = min(desired_pv, pv_output_kw + settings.pv_ramp_kw_per_s)
                output_ramp_due_at = now + 1.0 if pv_output_kw < desired_pv else None
        else:
            output_ramp_due_at = None
        delivered_pv = pv_output_kw
        constrained = battery_target
        # A withdrawn permission remains a hard AC-side gate even while the PV
        # cap is slewing or source facts change between observation checks.
        if constrained > 0 and (not effective_permission or latched_old_request):
            constrained = min(constrained, max(delivered_pv - fact.load_kw, 0.0))

        next_event = next(point for point in timeline if point > now)
        end = float(next_event)
        if ramp_due_at is not None:
            end = min(end, ramp_due_at)
        if output_ramp_due_at is not None:
            end = min(end, output_ramp_due_at)
        boundary = _soc_boundary_seconds(soc, constrained)
        if boundary is not None and boundary > 1e-8:
            end = min(end, now + boundary)
        if end <= now:
            raise AssertionError("execution timeline did not advance")

        physical = simulate_time_energy(
            TimeEnergyInput(
                SimulationCadences(
                    physical_step_s,
                    control_period_s,
                    3600,
                    record_period_s,
                    display_period_s,
                ),
                (PowerInterval(0, end - now, fact.load_kw, delivered_pv, constrained),),
                params,
                soc,
            )
        )
        for sl in physical.slices:
            start_s = now + sl.start_seconds
            end_s = now + sl.end_seconds
            if end_s <= start_s:
                # The frozen integrator can emit a zero-energy, sub-ULP local
                # remainder at an exact SOC boundary.  It cannot be represented
                # as a distinct absolute simulation timestamp or ledger row.
                if sl.soc_before != sl.soc_after:
                    raise AssertionError("unrepresentable slice changed SOC")
                continue
            hours = (end_s - start_s) / HOUR_SECONDS
            actual = sl.actual_battery_power_kw
            grid = sl.grid_power_kw
            available = fact.pv_kw * hours
            delivered = delivered_pv * hours
            curtailed = available - delivered
            battery_kwh = actual * hours
            stored = (sl.soc_after - sl.soc_before) * params.capacity_kwh
            grid_charge = (
                max(0.0, actual - max(delivered_pv - fact.load_kw, 0.0)) * hours
            )
            rows.append(
                CurtailmentRow(
                    start_s,
                    end_s,
                    original_request,
                    constrained,
                    actual,
                    fact.pv_kw,
                    delivered_pv,
                    fact.pv_kw - delivered_pv,
                    pv_cap,
                    fact.load_kw,
                    grid,
                    fact.grid_charge_allowed,
                    effective_permission,
                    fact.zero_export,
                    effective_zero,
                    fact.reserve_target_soc,
                    sl.soc_before,
                    sl.soc_after,
                    available,
                    delivered,
                    curtailed,
                    fact.load_kw * hours,
                    battery_kwh,
                    max(grid, 0.0) * hours,
                    max(-grid, 0.0) * hours,
                    grid_charge,
                    grid_charge if not fact.grid_charge_allowed else 0.0,
                    stored,
                    battery_kwh - stored,
                )
            )
        prior_soc = soc
        soc = physical.final_soc
        retarget_on_soc = bool(
            settings.observation_delay_s == 0
            and settings.execution_delay_s == 0
            and (
                (prior_soc < 1.0 and soc == 1.0)
                or (prior_soc > params.reserve_soc and soc == params.reserve_soc)
            )
        )
        now = end

    export_rows = [
        row for row in rows if row.grid_kw < -1e-10 and row.zero_export_requested
    ]
    return CurtailmentResult(
        case,
        settings,
        physical_step_s,
        control_period_s,
        record_period_s,
        tuple(decisions),
        checks,
        tuple(rows),
        soc,
        max((-row.grid_kw for row in export_rows), default=0.0),
        sum(row.end_s - row.start_s for row in export_rows),
        sum(row.export_kwh for row in export_rows),
    )


def write_evidence(result: CurtailmentResult, output: Path) -> None:
    """Write test-only ledger and time curves outside production code paths."""
    output.mkdir(parents=True, exist_ok=True)
    with (output / "ledger.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(result.ledger[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in result.ledger)
    root = ET.Element(
        "svg",
        xmlns="http://www.w3.org/2000/svg",
        width="1000",
        height="380",
        viewBox="0 0 1000 380",
    )

    def y_value(row: CurtailmentRow, field: str) -> float:
        return (
            max(-row.grid_kw, 0.0) if field == "grid_export_kw" else getattr(row, field)
        )

    for label, key, color, scale, offset in (
        ("available PV", "available_pv_kw", "#c68d00", 35, 345),
        ("delivered PV", "delivered_pv_kw", "#188d57", 35, 345),
        ("grid export", "grid_export_kw", "#d03a36", 35, 345),
        ("SOC", "soc_after", "#3167bc", 260, 340),
    ):
        points = " ".join(
            f"{30 + row.end_s / DURATION_SECONDS * 940:.2f},"
            f"{offset - y_value(row, key) * scale:.2f}"
            for row in result.ledger
        )
        line = ET.SubElement(root, "polyline", points=points, fill="none", stroke=color)
        line.set("stroke-width", "2")
        ET.SubElement(
            root,
            "text",
            x="30",
            y=str(
                25
                + (
                    0
                    if label == "available PV"
                    else 18
                    if label == "delivered PV"
                    else 36
                    if label == "grid export"
                    else 54
                )
            ),
            fill=color,
        ).text = label
    ET.ElementTree(root).write(output / "curves.svg", encoding="unicode")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=tuple(scenarios()), default="full_battery")
    parser.add_argument("--mode", choices=("ideal", "dynamic"), default="ideal")
    parser.add_argument("--step", type=float, default=60.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    settings = (
        CurtailmentSettings.ideal() if args.mode == "ideal" else CurtailmentSettings()
    )
    result = run_curtailment(
        scenarios()[args.case], physical_step_s=args.step, settings=settings
    )
    write_evidence(result, args.output)
    print(
        f"{args.case} {args.mode}: export={result.export_kwh:.9f} kWh, "
        f"peak={result.export_peak_kw:.6f} kW, "
        f"duration={result.export_duration_s:.3f} s, SOC={result.final_soc:.9f}"
    )


if __name__ == "__main__":
    main()
