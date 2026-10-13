"""Test-only AC-bus PV curtailment and Zero Export execution experiment.

The existing hourly EMS request and time-energy physics are not modified.  PV
availability is an external fact; this executor controls only the AC PV
injection cap and the battery request passed to the frozen physics function.
"""

import argparse
import csv
from dataclasses import asdict, dataclass, field, replace
from math import fsum
from pathlib import Path
from xml.etree import ElementTree as ET

from ems_simulator.input import BatteryParameters
from ems_simulator.time_energy import (
    EnergySlice,
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
from tools.grid_charge_interlock_probe import constrain_charge_request


@dataclass(frozen=True, slots=True)
class CurtailmentSettings:
    check_period_s: int = 60
    observation_delay_s: int = 20
    execution_delay_s: int = 10
    pv_ac_max_kw: float = 5.0
    pv_ramp_kw_per_s: float = 1.0
    # The joint entry requires a complete first observation delay.  The
    # original PV experiment keeps its previously accepted startup default.
    strict_startup_observation: bool = False
    # Preserve the PV-only experiment's additional instantaneous AC-surplus
    # clamp by default.  The joint entry disables it to reproduce the
    # accepted interlock's delayed PV-loss response and records its transient.
    current_pv_surplus_guard: bool = True
    # Joint-only: a controlled AC output rise cannot count as already
    # delivered PV.  Later source loss still follows delayed observation.
    guard_controlled_pv_rise: bool = False
    duration_seconds: int = DURATION_SECONDS
    battery_parameters: BatteryParameters = field(default_factory=battery)

    def __post_init__(self) -> None:
        if type(self.check_period_s) is not int or self.check_period_s <= 0:
            raise ValueError("check period must be a positive integer")
        if type(self.duration_seconds) is not int or self.duration_seconds <= 0:
            raise ValueError("duration must be a positive integer")
        if self.duration_seconds % self.check_period_s:
            raise ValueError("check period must divide scenario duration")
        for field_name in ("observation_delay_s", "execution_delay_s"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.pv_ac_max_kw <= 0 or self.pv_ramp_kw_per_s < 0:
            raise ValueError("PV rating must be positive and ramp non-negative")
        if type(self.strict_startup_observation) is not bool:
            raise ValueError("strict startup observation must be a boolean")
        if type(self.current_pv_surplus_guard) is not bool:
            raise ValueError("current PV surplus guard must be a boolean")
        if type(self.guard_controlled_pv_rise) is not bool:
            raise ValueError("controlled PV rise guard must be a boolean")

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
        return self.pv_ac_max_kw + self.battery_parameters.max_discharge_power_kw

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
class PhysicalLedgerPart:
    """Lossless two-component time; start/end remain local simulation seconds."""

    origin_s: float
    start_s: float
    end_s: float
    actual_battery_kw: float
    grid_kw: float
    soc_before: float
    soc_after: float


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
    physical_parts: tuple[PhysicalLedgerPart, ...] = ()
    audit_duration_s: float | None = None

    @property
    def duration_s(self) -> float:
        """Audit expansions use local duration, never rounded endpoint subtraction."""
        return (
            self.end_s - self.start_s
            if self.audit_duration_s is None
            else self.audit_duration_s
        )


def _absolute_slice_groups(
    slices: tuple[EnergySlice, ...], origin_s: float
) -> tuple[tuple[EnergySlice, ...], ...]:
    """Coalesce only unrepresentable endpoints within ONE constant-fact call.

    No slice is discarded; a leading remainder joins its successor and a
    trailing remainder joins its predecessor. Physics and event times stay put.
    """
    groups: list[tuple[EnergySlice, ...]] = []
    pending: list[EnergySlice] = []
    for sl in slices:
        if sl.end_seconds <= sl.start_seconds:
            raise AssertionError("nonpositive physical slice")
        pending.append(sl)
        if origin_s + sl.end_seconds > origin_s + pending[0].start_seconds:
            groups.append(tuple(pending))
            pending = []
    if pending:
        if not groups:
            raise AssertionError("physical call has no representable duration")
        groups[-1] += tuple(pending)
    return tuple(groups)


def physical_audit_rows(rows: tuple[CurtailmentRow, ...]) -> tuple[CurtailmentRow, ...]:
    """Expand retained parts for peaks/durations/energy, not control or display.

    Absolute endpoints may round together; duration_s is the original positive
    local duration. These audit records are NOT zero-width state transitions.
    """
    expanded: list[CurtailmentRow] = []
    for row in rows:
        if not row.physical_parts:
            expanded.append(row)
            continue
        for part in row.physical_parts:
            duration = part.end_s - part.start_s
            hours = duration / HOUR_SECONDS
            charge = (
                max(
                    0.0,
                    part.actual_battery_kw
                    - max(row.delivered_pv_kw - row.load_kw, 0.0),
                )
                * hours
            )
            # Capacity is derived from this row only for storage bookkeeping;
            # exact part SOC-to-energy is supplied below by proportional delta.
            delta = row.soc_after - row.soc_before
            stored = (
                row.storage_delta_kwh * (part.soc_after - part.soc_before) / delta
                if delta
                else 0.0
            )
            battery_kwh = part.actual_battery_kw * hours
            expanded.append(
                replace(
                    row,
                    start_s=part.origin_s + part.start_s,
                    end_s=part.origin_s + part.end_s,
                    actual_battery_kw=part.actual_battery_kw,
                    grid_kw=part.grid_kw,
                    soc_before=part.soc_before,
                    soc_after=part.soc_after,
                    available_pv_kwh=row.available_pv_kw * hours,
                    delivered_pv_kwh=row.delivered_pv_kw * hours,
                    curtailed_pv_kwh=row.curtailed_pv_kw * hours,
                    load_kwh=row.load_kw * hours,
                    battery_kwh=battery_kwh,
                    import_kwh=max(part.grid_kw, 0.0) * hours,
                    export_kwh=max(-part.grid_kw, 0.0) * hours,
                    grid_to_battery_kwh=charge,
                    prohibited_grid_charge_kwh=charge
                    if not row.grid_charge_allowed
                    else 0.0,
                    storage_delta_kwh=stored,
                    conversion_loss_kwh=battery_kwh - stored,
                    physical_parts=(part,),
                    audit_duration_s=duration,
                )
            )
    return tuple(expanded)


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
    check_times = set(range(0, settings.duration_seconds, settings.check_period_s))
    if settings.strict_startup_observation and settings.observation_delay_s:
        # The joint experiment requires a full post-start observation delay;
        # clamping a negative sample time to t=0 would backdate knowledge.
        check_times = {at for at in check_times if at >= settings.observation_delay_s}
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


def _soc_boundary_seconds(
    soc: float, request: float, params: BatteryParameters | None = None
) -> float | None:
    params = battery() if params is None else params
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
        or settings.duration_seconds % control_period_s
    ):
        raise ValueError("control period must divide scenario duration")
    expected = 0
    for fact in case.segments:
        if fact.start != expected or fact.end <= fact.start:
            raise ValueError("facts must be contiguous and advancing")
        if fact.pv_kw > settings.pv_ac_max_kw:
            raise ValueError("available PV exceeds explicit AC PV rating")
        expected = fact.end
    if expected != settings.duration_seconds:
        raise ValueError("facts must cover scenario duration")

    params = settings.battery_parameters
    checks = _checks(case, settings)
    effects = {
        check.effect_at: check
        for check in checks
        if check.effect_at < settings.duration_seconds
    }
    event_times = {0, settings.duration_seconds}
    event_times.update(range(0, settings.duration_seconds, control_period_s))
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

    while now < settings.duration_seconds:
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
            # For the joint entry, an unobserved fail-closed startup is not a
            # revocation; a fresh request may execute after an affirmative
            # delayed observation.  Preserve the older probe's default.
            latched_old_request = (
                original_request > 0
                and not effective_permission
                and (has_observation or not settings.strict_startup_observation)
            )
            decisions.append(EMSDecision(int(now), soc, original_request))

        fact = _fact_at(case, now)
        update_target = has_observation and (
            check is not None
            or (at_event and int(now) % control_period_s == 0)
            or retarget_on_soc
        )
        prior_target_pv_cap = target_pv_cap
        if update_target:
            battery_target, _gate_reason = constrain_charge_request(
                original_request,
                effective_permission=effective_permission,
                latched_old_request=latched_old_request,
                observed_surplus_kw=max(observed.pv_kw - observed.load_kw, 0.0),
            )
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
        # Delayed permission and source observations use the same accepted
        # interlock gate.  A source revoke can cause a bounded transient until
        # its observation effect; do not relabel that energy as safe.
        if (
            (
                settings.current_pv_surplus_guard
                or (
                    settings.guard_controlled_pv_rise
                    and (ramp_due_at is not None or output_ramp_due_at is not None)
                )
            )
            and constrained > 0
            and (not effective_permission or latched_old_request)
        ):
            constrained = min(constrained, max(delivered_pv - fact.load_kw, 0.0))

        next_event = next(point for point in timeline if point > now)
        end = float(next_event)
        if ramp_due_at is not None:
            end = min(end, ramp_due_at)
        if output_ramp_due_at is not None:
            end = min(end, output_ramp_due_at)
        # Physics uses local time. Do not round a SOC-boundary duration through
        # (absolute origin + duration) - origin before giving it to physics.
        # Return after each existing physical step so the next boundary uses
        # the actual returned SOC, not a prediction spanning multiple rounded
        # SOC updates. Scheduled EMS/observation/effect predicates above do not
        # change: returning physics is not a new control decision.
        physical_duration = min(end - now, physical_step_s)
        end = now + physical_duration
        boundary = _soc_boundary_seconds(soc, constrained, params)
        if boundary is not None and 1e-8 < boundary < physical_duration:
            physical_duration = boundary
            end = now + boundary
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
                (
                    PowerInterval(
                        0, physical_duration, fact.load_kw, delivered_pv, constrained
                    ),
                ),
                params,
                soc,
            )
        )
        for group in _absolute_slice_groups(physical.slices, now):
            start_s = now + group[0].start_seconds
            end_s = now + group[-1].end_seconds
            if end_s <= start_s:
                raise AssertionError("unrepresentable physical group")
            local_hours = (
                fsum(sl.end_seconds - sl.start_seconds for sl in group) / HOUR_SECONDS
            )
            battery_kwh = fsum(
                sl.actual_battery_power_kw
                * (sl.end_seconds - sl.start_seconds)
                / HOUR_SECONDS
                for sl in group
            )
            # Display row power is a local-duration average. Retained parts,
            # not this average, are authoritative for sign/peak/duration audits.
            actual = battery_kwh / local_hours
            grid = fact.load_kw + actual - delivered_pv
            available = fact.pv_kw * local_hours
            delivered = delivered_pv * local_hours
            curtailed = available - delivered
            stored = (group[-1].soc_after - group[0].soc_before) * params.capacity_kwh
            grid_charge = fsum(
                max(
                    0.0,
                    sl.actual_battery_power_kw - max(delivered_pv - fact.load_kw, 0.0),
                )
                * (sl.end_seconds - sl.start_seconds)
                / HOUR_SECONDS
                for sl in group
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
                    group[0].soc_before,
                    group[-1].soc_after,
                    available,
                    delivered,
                    curtailed,
                    fact.load_kw * local_hours,
                    battery_kwh,
                    fsum(
                        max(sl.grid_power_kw, 0.0)
                        * (sl.end_seconds - sl.start_seconds)
                        / HOUR_SECONDS
                        for sl in group
                    ),
                    fsum(
                        max(-sl.grid_power_kw, 0.0)
                        * (sl.end_seconds - sl.start_seconds)
                        / HOUR_SECONDS
                        for sl in group
                    ),
                    grid_charge,
                    grid_charge if not fact.grid_charge_allowed else 0.0,
                    stored,
                    battery_kwh - stored,
                    tuple(
                        PhysicalLedgerPart(
                            now,
                            sl.start_seconds,
                            sl.end_seconds,
                            sl.actual_battery_power_kw,
                            sl.grid_power_kw,
                            sl.soc_before,
                            sl.soc_after,
                        )
                        for sl in group
                    ),
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
        row
        for row in physical_audit_rows(tuple(rows))
        if row.grid_kw < -1e-10 and row.zero_export_requested
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
        sum(row.duration_s for row in export_rows),
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
            f"{30 + row.end_s / result.settings.duration_seconds * 940:.2f},"
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
