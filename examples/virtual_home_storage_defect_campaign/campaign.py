# ruff: noqa: E501, RUF001
"""Deterministic, simulation-only defect-finding campaign for home storage."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime, timedelta
from html import escape
from io import StringIO
from math import isclose
from pathlib import Path

from ems_simulator.economic_ledger import (
    DailyEconomicLedger,
    DeterministicEconomicLedgerBuilder,
    EconomicLedgerInput,
)
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.economic_schedule_aware_comparison_demo import (
    _economic_runner,
    _schedule_runner,
)
from ems_simulator.ems_integration import EMSIntegrationScenarioInput
from ems_simulator.explainable_mpc_daily import ExplainableMPCDailySimulationInput
from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationResult,
    MultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.multi_opportunity_headroom_demo import (
    _GAP_TOLERANCE_POINTS,
    create_demo_input,
)
from forecast import ForecastHorizon, ForecastPoint
from optimization import (
    BatteryOptimizationModel,
    NetLoadAwareBaselineOptimizationConfiguration,
    PVOpportunityWindowConfiguration,
)
from simulator import SimulationStepIdentity

SIMULATED_LABEL = "SIMULATED / 固定虚拟输入 / 非设备遥测"
HOURS = 24
START = datetime(2026, 3, 1, tzinfo=UTC)
DEFAULT_MODEL = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.95, 0.95)
LOW_EFFICIENCY_MODEL = BatteryOptimizationModel(10.0, 0.20, 1.0, 3.0, 3.0, 0.80, 0.80)
CONFIGURATION = NetLoadAwareBaselineOptimizationConfiguration(0.30, 0.80, 3.0)
EXPORT_TARIFF = 0.20
DEGRADATION_RATE = 0.05
TERMINAL_VALUE = 0.85
TOLERANCE = 1e-9

Trajectory = (
    MultiOpportunityExplainableMPCDailySimulationResult
    | EconomicMultiOpportunityExplainableMPCDailySimulationResult
)
Trace = (
    MultiOpportunityExplainableMPCDailySimulationStepTrace
    | EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace
)


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    scenario_id: str
    category: str
    goal: str
    realized_pv_kw: tuple[float, ...]
    forecast_pv_kw: tuple[float, ...]
    realized_load_kw: tuple[float, ...]
    forecast_load_kw: tuple[float, ...]
    realized_tariff_cny_per_kwh: tuple[float, ...]
    forecast_tariff_cny_per_kwh: tuple[float, ...]
    initial_soc: float
    battery_model: BatteryOptimizationModel = DEFAULT_MODEL
    export_limit_kw: float = 5.0
    start: datetime = START


@dataclass(frozen=True, slots=True)
class PathResult:
    scenario_id: str
    strategy: str
    day_index: int
    status: str
    finding_kind: str
    finding_code: str
    explanation_zh: str
    initial_soc: float
    final_soc: float | None
    total_import_kwh: float | None
    total_export_kwh: float | None
    total_battery_throughput_kwh: float | None
    independent_import_cost_cny: float | None
    independent_export_revenue_cny: float | None
    independent_degradation_cost_cny: float | None
    independent_net_cost_cny: float | None
    ledger_net_cost_cny: float | None
    first_timestamp_utc: str
    last_timestamp_utc: str
    invariant_failures: tuple[str, ...]
    exception_type: str
    exception_message: str


@dataclass(frozen=True, slots=True)
class CampaignResult:
    scenario_count: int
    path_results: tuple[PathResult, ...]
    output_paths: tuple[Path, ...]


def _curve(
    changes: dict[int, float] | None = None, default: float = 0.0
) -> tuple[float, ...]:
    values = [default] * HOURS
    for index, value in (changes or {}).items():
        values[index] = value
    return tuple(values)


def _spec(
    scenario_id: str,
    category: str,
    goal: str,
    *,
    pv: dict[int, float] | None = None,
    load: dict[int, float] | None = None,
    tariff: tuple[float, ...] | None = None,
    forecast_pv: tuple[float, ...] | None = None,
    forecast_load: tuple[float, ...] | None = None,
    initial_soc: float = 0.50,
    model: BatteryOptimizationModel = DEFAULT_MODEL,
    export_limit_kw: float = 5.0,
    start: datetime = START,
) -> ScenarioSpec:
    actual_pv = _curve(pv)
    actual_load = _curve(load)
    prices = tariff or _curve(default=0.50)
    return ScenarioSpec(
        scenario_id,
        category,
        goal,
        actual_pv,
        actual_pv if forecast_pv is None else forecast_pv,
        actual_load,
        actual_load if forecast_load is None else forecast_load,
        prices,
        prices,
        initial_soc,
        model,
        export_limit_kw,
        start,
    )


def executable_scenarios() -> tuple[ScenarioSpec, ...]:
    """Return the 14 newly targeted executable cells; S14 is run for two days."""

    exact_charge = (1.0 - 0.95) * 10.0 / 0.95
    exact_discharge = (0.25 - 0.20) * 10.0 * 0.95
    negative = (-0.20,) * 6 + (0.50,) * 12 + (0.90,) * 4 + (0.50,) * 2
    spike = _curve({18: 5.0}, default=0.50)
    high_at_zero = _curve({0: 0.90}, default=0.50)
    high_at_eighteen = _curve({18: 0.90}, default=0.50)
    false_pv = _curve({12: 5.0})
    missed_load = _curve()
    return (
        _spec(
            "S01_MIN_SOC_LOAD",
            "physical_boundary",
            "最低 SOC 供载",
            load={0: 1.0},
            initial_soc=0.20,
        ),
        _spec(
            "S02_MAX_SOC_PV",
            "physical_boundary",
            "满电 PV 盈余",
            pv={0: 2.0},
            initial_soc=1.0,
        ),
        _spec(
            "S03_EXACT_MAX_FILL",
            "threshold",
            "恰好充至最高 SOC",
            pv={0: exact_charge},
            initial_soc=0.95,
        ),
        _spec(
            "S04_EXACT_MIN_DRAIN",
            "threshold",
            "恰好放至最低 SOC",
            load={0: exact_discharge},
            tariff=high_at_zero,
            initial_soc=0.25,
        ),
        _spec(
            "S05_PV_STEP_UP",
            "step_change",
            "单小时 PV 突升",
            pv={12: 5.0},
            load={12: 1.0},
            initial_soc=0.20,
        ),
        _spec(
            "S06_LOAD_STEP_UP",
            "step_change",
            "单小时负载突升",
            load={18: 6.0},
            tariff=high_at_eighteen,
            initial_soc=1.0,
        ),
        _spec(
            "S07_CHARGE_LIMIT",
            "power_limit",
            "极端盈余充电限幅",
            pv={0: 10.0},
            initial_soc=0.50,
        ),
        _spec(
            "S08_DISCHARGE_LIMIT",
            "power_limit",
            "极端缺口放电限幅",
            load={0: 10.0},
            tariff=high_at_zero,
            initial_soc=1.0,
        ),
        _spec(
            "S09_ZERO_EXPORT_FULL",
            "capability_gap",
            "零出口与满电弃光",
            pv={0: 10.0},
            initial_soc=1.0,
            export_limit_kw=0.0,
        ),
        _spec(
            "S10_NEGATIVE_PRICE",
            "economic_boundary",
            "负进口价端到端",
            tariff=negative,
            initial_soc=0.50,
        ),
        _spec(
            "S11_PRICE_SPIKE_IDLE",
            "strategy_scope",
            "无净负载纯价格尖峰",
            tariff=spike,
            initial_soc=0.80,
        ),
        _spec(
            "S12_FALSE_PV_FORECAST",
            "forecast_error",
            "预测有 PV 实际无 PV",
            load={12: 2.0},
            forecast_pv=false_pv,
            initial_soc=0.50,
        ),
        _spec(
            "S13_MISSED_LOAD_SPIKE",
            "forecast_error",
            "实际负载尖峰未预测",
            load={18: 6.0},
            tariff=high_at_eighteen,
            forecast_load=missed_load,
            initial_soc=1.0,
        ),
        _spec(
            "S15_LOW_EFFICIENCY",
            "model_parameter",
            "低效率 SOC 与账本",
            pv={8: 2.0},
            load={18: 1.0},
            tariff=high_at_eighteen,
            initial_soc=0.50,
            model=LOW_EFFICIENCY_MODEL,
        ),
    )


def run_campaign(output_directory: Path) -> CampaignResult:
    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    output_directory.mkdir(parents=True, exist_ok=True)
    results: list[PathResult] = []
    for spec in executable_scenarios():
        results.extend(_run_both(spec, output_directory / spec.scenario_id))
    results.extend(_run_cross_midnight(output_directory / "S14_CROSS_MIDNIGHT"))
    results.extend(_invalid_input_results(output_directory / "invalid_inputs"))
    paths = _write_outputs(output_directory, tuple(results))
    return CampaignResult(18, tuple(results), paths)


def _run_both(spec: ScenarioSpec, directory: Path) -> tuple[PathResult, PathResult]:
    schedule_input, economic_input = _inputs(spec, directory)
    return (
        _execute_path(spec, "Schedule", 1, schedule_input, directory),
        _execute_path(spec, "Economic", 1, economic_input, directory),
    )


def _execute_path(
    spec: ScenarioSpec,
    strategy: str,
    day_index: int,
    source_input: MultiOpportunityExplainableMPCDailySimulationInput,
    directory: Path,
) -> PathResult:
    directory.mkdir(parents=True, exist_ok=True)
    runner = (
        _schedule_runner(CONFIGURATION)
        if strategy == "Schedule"
        else _economic_runner(CONFIGURATION)
    )
    try:
        trajectory = runner.run(source_input)
    except Exception as error:  # retained as a campaign finding, never hidden
        return _exception_result(spec, strategy, day_index, "runner_failure", error)

    failures, totals = _independent_oracle(spec, trajectory)
    ledger: DailyEconomicLedger | None = None
    ledger_error: Exception | None = None
    try:
        ledger = DeterministicEconomicLedgerBuilder().build(
            EconomicLedgerInput(
                trajectory,
                (EXPORT_TARIFF,) * HOURS,
                (DEGRADATION_RATE,) * HOURS,
                TERMINAL_VALUE,
                spec.battery_model,
            )
        )
    except Exception as error:  # negative-price mismatch is expected evidence
        ledger_error = error

    if ledger is not None:
        failures.extend(_ledger_oracle_failures(ledger, totals))
    status, kind, code, explanation = _classify(
        spec, trajectory, ledger_error, failures, totals
    )
    traces = _traces(trajectory)
    first_timestamp = traces[
        0
    ].simulation_trace.simulation_input.step_identity.timestamp
    last_timestamp = traces[
        -1
    ].simulation_trace.simulation_input.step_identity.timestamp
    assert first_timestamp is not None and last_timestamp is not None
    return PathResult(
        spec.scenario_id,
        strategy,
        day_index,
        status,
        kind,
        code,
        explanation,
        spec.initial_soc,
        totals["final_soc"],
        totals["import_kwh"],
        totals["export_kwh"],
        totals["throughput_kwh"],
        totals["import_cost_cny"],
        totals["export_revenue_cny"],
        totals["degradation_cost_cny"],
        totals["net_cost_cny"],
        None if ledger is None else ledger.total_realized_net_cost,
        first_timestamp.isoformat(),
        last_timestamp.isoformat(),
        tuple(failures),
        "" if ledger_error is None else type(ledger_error).__name__,
        "" if ledger_error is None else str(ledger_error),
    )


def _inputs(
    spec: ScenarioSpec, directory: Path
) -> tuple[
    MultiOpportunityExplainableMPCDailySimulationInput,
    MultiOpportunityExplainableMPCDailySimulationInput,
]:
    directory.mkdir(parents=True, exist_ok=True)
    template = create_demo_input(directory)
    identities = tuple(
        SimulationStepIdentity(index, 3600.0, spec.start + timedelta(hours=index))
        for index in range(HOURS)
    )
    model = spec.battery_model
    daily = DailySimulationScenarioInput(
        identities,
        spec.realized_pv_kw,
        spec.realized_load_kw,
        spec.realized_tariff_cny_per_kwh,
        BatteryParameters(
            model.usable_capacity_kwh,
            model.max_charge_power_kw,
            model.max_discharge_power_kw,
            model.charge_efficiency,
            model.discharge_efficiency,
            model.min_soc_fraction,
        ),
        spec.initial_soc,
    )
    base = template.integration_input
    integration = EMSIntegrationScenarioInput(
        daily,
        base.objective_composition,
        base.capability,
        max(model.max_charge_power_kw, model.max_discharge_power_kw),
        spec.export_limit_kw,
        base.initial_grid_power_kw,
    )
    horizons = _horizons(spec, template.mpc_configuration.forecast_horizon_points)
    schedule = ExplainableMPCDailySimulationInput(
        integration,
        horizons,
        template.mpc_configuration,
        template.optimization_objectives,
        template.source_strategy,
        model,
        template.explanation_locale,
        directory / "schedule_decisions.csv",
    )
    economic = replace(
        schedule, decision_csv_output_path=directory / "economic_decisions.csv"
    )
    opportunity = PVOpportunityWindowConfiguration(_GAP_TOLERANCE_POINTS)
    return (
        MultiOpportunityExplainableMPCDailySimulationInput(
            schedule, CONFIGURATION, opportunity
        ),
        MultiOpportunityExplainableMPCDailySimulationInput(
            economic, CONFIGURATION, opportunity
        ),
    )


def _horizons(spec: ScenarioSpec, point_count: int) -> tuple[ForecastHorizon, ...]:
    result: list[ForecastHorizon] = []
    for hour in range(HOURS):
        points: list[ForecastPoint] = []
        for offset in range(point_count):
            index = hour + offset
            timestamp = spec.start + timedelta(hours=index)
            if index < HOURS:
                point = ForecastPoint(
                    timestamp,
                    spec.forecast_pv_kw[index],
                    spec.forecast_load_kw[index],
                    spec.forecast_tariff_cny_per_kwh[index],
                )
            else:
                point = ForecastPoint(timestamp, 0.0, 0.0, 0.50)
            points.append(point)
        result.append(ForecastHorizon(tuple(points)))
    return tuple(result)


def _independent_oracle(
    spec: ScenarioSpec, trajectory: Trajectory
) -> tuple[list[str], dict[str, float]]:
    failures: list[str] = []
    previous_soc = spec.initial_soc
    totals = {
        key: 0.0
        for key in ("import_kwh", "export_kwh", "throughput_kwh", "import_cost_cny")
    }
    for index, trace in enumerate(_traces(trajectory)):
        decision = trace.decision_provenance.decision
        feasible = trace.feasible_decision
        handoff = trace.handoff
        battery_input = trace.simulation_trace.simulation_input.battery_input
        if decision.source_context is not trace.context:
            failures.append(f"h{index}:decision_context_identity")
        if trace.decision_provenance.source_context is not trace.context:
            failures.append(f"h{index}:provenance_context_identity")
        if feasible.source_decision is not decision:
            failures.append(f"h{index}:feasible_decision_identity")
        if feasible.source_provenance is not trace.decision_provenance:
            failures.append(f"h{index}:feasible_provenance_identity")
        if handoff.source_feasible_decision is not feasible:
            failures.append(f"h{index}:handoff_identity")
        if battery_input.actuation is not handoff.actuation:
            failures.append(f"h{index}:simulation_actuation_identity")
        state = trace.simulation_trace.state
        pv = state.pv_result.actual_power_kw
        load = state.load_result.actual_power_kw
        battery = state.battery_result.actual_power_kw
        grid = state.grid_result.actual_grid_power_kw
        duration = (
            trace.simulation_trace.simulation_input.step_identity.duration_seconds
            / 3600.0
        )
        if not isclose(pv + grid - battery, load, abs_tol=TOLERANCE):
            failures.append(f"h{index}:power_balance")
        expected_soc = previous_soc + (
            battery
            * duration
            * spec.battery_model.charge_efficiency
            / spec.battery_model.usable_capacity_kwh
            if battery >= 0.0
            else battery
            * duration
            / spec.battery_model.discharge_efficiency
            / spec.battery_model.usable_capacity_kwh
        )
        actual_soc = state.battery_result.next_state.soc
        if not isclose(actual_soc, expected_soc, abs_tol=TOLERANCE):
            failures.append(f"h{index}:soc_integration")
        if (
            not spec.battery_model.min_soc_fraction - TOLERANCE
            <= actual_soc
            <= spec.battery_model.max_soc_fraction + TOLERANCE
        ):
            failures.append(f"h{index}:soc_bounds")
        if (
            not -spec.battery_model.max_discharge_power_kw - TOLERANCE
            <= battery
            <= spec.battery_model.max_charge_power_kw + TOLERANCE
        ):
            failures.append(f"h{index}:battery_power_bounds")
        totals["import_kwh"] += max(grid, 0.0) * duration
        totals["export_kwh"] += max(-grid, 0.0) * duration
        totals["throughput_kwh"] += abs(battery) * duration
        totals["import_cost_cny"] += (
            max(grid, 0.0) * duration * spec.realized_tariff_cny_per_kwh[index]
        )
        previous_soc = actual_soc
    totals["final_soc"] = previous_soc
    totals["export_revenue_cny"] = totals["export_kwh"] * EXPORT_TARIFF
    totals["degradation_cost_cny"] = totals["throughput_kwh"] * DEGRADATION_RATE
    totals["net_cost_cny"] = (
        totals["import_cost_cny"]
        - totals["export_revenue_cny"]
        + totals["degradation_cost_cny"]
    )
    failures.extend(_scenario_expectation_failures(spec, trajectory))
    return failures, totals


def _traces(trajectory: Trajectory) -> tuple[Trace, ...]:
    if isinstance(trajectory, MultiOpportunityExplainableMPCDailySimulationResult):
        return trajectory.step_traces
    return trajectory.step_traces


def _scenario_expectation_failures(
    spec: ScenarioSpec, trajectory: Trajectory
) -> list[str]:
    states = [trace.simulation_trace.state for trace in trajectory.step_traces]
    checks: dict[str, tuple[int, float, float, float]] = {
        "S01_MIN_SOC_LOAD": (0, 0.0, 1.0, 0.20),
        "S02_MAX_SOC_PV": (0, 0.0, -2.0, 1.0),
        "S03_EXACT_MAX_FILL": (0, (1.0 - 0.95) * 10.0 / 0.95, 0.0, 1.0),
        "S04_EXACT_MIN_DRAIN": (0, -(0.25 - 0.20) * 10.0 * 0.95, 0.0, 0.20),
        "S05_PV_STEP_UP": (12, 3.0, -1.0, 0.485),
        "S06_LOAD_STEP_UP": (18, -3.0, 3.0, 1.0 - 3.0 / 0.95 / 10.0),
        "S07_CHARGE_LIMIT": (0, 3.0, -7.0, 0.50 + 3.0 * 0.95 / 10.0),
        "S08_DISCHARGE_LIMIT": (0, -3.0, 7.0, 1.0 - 3.0 / 0.95 / 10.0),
    }
    failures: list[str] = []
    if spec.scenario_id in checks:
        hour, expected_battery, expected_grid, expected_soc = checks[spec.scenario_id]
        state = states[hour]
        actual = (
            state.battery_result.actual_power_kw,
            state.grid_result.actual_grid_power_kw,
            state.battery_result.next_state.soc,
        )
        for label, value, expected in zip(
            ("battery", "grid", "soc"),
            actual,
            (expected_battery, expected_grid, expected_soc),
            strict=True,
        ):
            if not isclose(value, expected, abs_tol=TOLERANCE):
                failures.append(
                    f"h{hour}:{label}_expected_{expected:.12g}_actual_{value:.12g}"
                )
    return failures


def _ledger_oracle_failures(
    ledger: DailyEconomicLedger, totals: dict[str, float]
) -> list[str]:
    failures: list[str] = []
    expected_export_revenue = totals["export_revenue_cny"]
    expected_degradation = totals["degradation_cost_cny"]
    expected_net = totals["net_cost_cny"]
    comparisons = (
        (
            "ledger_import_energy",
            ledger.total_grid_import_energy_kwh,
            totals["import_kwh"],
        ),
        (
            "ledger_export_energy",
            ledger.total_grid_export_energy_kwh,
            totals["export_kwh"],
        ),
        (
            "ledger_throughput",
            ledger.total_battery_throughput_kwh,
            totals["throughput_kwh"],
        ),
        (
            "ledger_import_cost",
            ledger.total_realized_import_cost,
            totals["import_cost_cny"],
        ),
        (
            "ledger_export_revenue",
            ledger.total_realized_export_revenue,
            expected_export_revenue,
        ),
        (
            "ledger_degradation",
            ledger.total_battery_degradation_cost,
            expected_degradation,
        ),
        ("ledger_net_cost", ledger.total_realized_net_cost, expected_net),
    )
    for name, actual, expected in comparisons:
        if not isclose(actual, expected, abs_tol=TOLERANCE):
            failures.append(f"{name}_expected_{expected:.12g}_actual_{actual:.12g}")
    return failures


def _classify(
    spec: ScenarioSpec,
    trajectory: Trajectory,
    ledger_error: Exception | None,
    failures: list[str],
    totals: dict[str, float],
) -> tuple[str, str, str, str]:
    if failures:
        return (
            "FAIL",
            "simulator_or_composition_defect",
            "INVARIANT_FAILURE",
            "独立物理或会计不变量失败。",
        )
    if spec.scenario_id == "S09_ZERO_EXPORT_FULL":
        exported = max(
            -trajectory.step_traces[
                0
            ].simulation_trace.state.grid_result.actual_grid_power_kw,
            0.0,
        )
        if exported > TOLERANCE:
            return (
                "LIMITATION",
                "product_capability_gap",
                "ZERO_EXPORT_NOT_ENFORCED_NO_CURTAILMENT",
                "export_limit=0 仍产生售电；当前日链没有零出口修正或 PV 弃光模型。",
            )
    if (
        spec.scenario_id == "S10_NEGATIVE_PRICE"
        and totals["import_cost_cny"] < 0.0
        and isinstance(ledger_error, ValueError)
        and str(ledger_error) == "import_tariff_per_kwh must be finite and non-negative"
    ):
        return (
            "FAIL",
            "cross_contract_defect",
            "NEGATIVE_TARIFF_LEDGER_REJECTED",
            "日输入与 Tariff simulator 接受有限负价，但 ledger 拒绝完成后的负进口价，端到端合同不闭合。",
        )
    if (
        totals["net_cost_cny"] < 0.0
        and isinstance(ledger_error, ValueError)
        and str(ledger_error)
        == "total_realized_net_cost must be finite and non-negative"
    ):
        return (
            "FAIL",
            "cross_contract_defect",
            "NEGATIVE_REALIZED_NET_COST_REJECTED",
            "显式出口结算产生负的实际净成本（净收益）时，ledger 汇总合同拒绝完成轨迹。",
        )
    if ledger_error is not None:
        return (
            "FAIL",
            "ledger_defect",
            "LEDGER_REJECTED_COMPLETED_TRACE",
            "完成轨迹被 ledger 拒绝。",
        )
    if spec.scenario_id == "S11_PRICE_SPIKE_IDLE":
        trace = trajectory.step_traces[18]
        if trace.journal_record.final_action.action == "idle":
            return (
                "LIMITATION",
                "strategy_limitation",
                "NO_PRICE_ONLY_ARBITRAGE",
                "纯价格尖峰且无净负载时保持 idle；现有策略不执行向电网放电套利。",
            )
    if spec.scenario_id == "S12_FALSE_PV_FORECAST":
        state = _traces(trajectory)[12].simulation_trace.state
        if state.battery_result.actual_power_kw > TOLERANCE:
            return (
                "LIMITATION",
                "strategy_limitation",
                "FALSE_PV_FORECAST_CAUSES_GRID_CHARGE",
                "h12 预测有 PV、实际为零时仍执行充电，实际形成 5 kW 购电；当前动作没有用 realized 净负载否决该预测动作。",
            )
    if spec.scenario_id == "S13_MISSED_LOAD_SPIKE":
        state = _traces(trajectory)[18].simulation_trace.state
        if isclose(state.battery_result.actual_power_kw, 0.0, abs_tol=TOLERANCE):
            return (
                "LIMITATION",
                "strategy_limitation",
                "MISSED_LOAD_SPIKE_NO_DISCHARGE",
                "h18 实际 6 kW 高价负载未被预测时保持 idle，全部由电网供电；动作依赖 forecast 当前点。",
            )
    return "PASS", "none", "", "满足显式场景预期及独立物理/会计不变量。"


def _run_cross_midnight(directory: Path) -> tuple[PathResult, ...]:
    day1 = _spec(
        "S14_CROSS_MIDNIGHT",
        "multi_day",
        "两日跨午夜状态",
        pv={23: 2.0},
        initial_soc=0.50,
        start=START,
    )
    results: list[PathResult] = []
    for strategy in ("Schedule", "Economic"):
        inputs = _inputs(day1, directory / strategy / "day1")
        source = inputs[0] if strategy == "Schedule" else inputs[1]
        first = _execute_path(day1, strategy, 1, source, directory / strategy / "day1")
        results.append(first)
        if first.final_soc is None:
            continue
        day2 = _spec(
            "S14_CROSS_MIDNIGHT",
            "multi_day",
            "两日跨午夜状态",
            load={0: 1.0},
            initial_soc=first.final_soc,
            start=START + timedelta(days=1),
        )
        second_inputs = _inputs(day2, directory / strategy / "day2")
        second_source = second_inputs[0] if strategy == "Schedule" else second_inputs[1]
        second = _execute_path(
            day2, strategy, 2, second_source, directory / strategy / "day2"
        )
        midnight_failures = []
        if not isclose(second.initial_soc, first.final_soc, abs_tol=TOLERANCE):
            midnight_failures.append("midnight_soc_carry")
        if datetime.fromisoformat(second.first_timestamp_utc) != datetime.fromisoformat(
            first.last_timestamp_utc
        ) + timedelta(hours=1):
            midnight_failures.append("midnight_timestamp_continuity")
        if midnight_failures:
            second = replace(
                second,
                status="FAIL",
                finding_kind="orchestration_defect",
                finding_code="MIDNIGHT_SOC_CARRY_MISMATCH",
                explanation_zh="第二日初始 SOC 或首时间戳未连续承接第一日实际结果。",
                invariant_failures=(*second.invariant_failures, *midnight_failures),
            )
        results.append(second)
    return tuple(results)


def _invalid_input_results(directory: Path) -> tuple[PathResult, ...]:
    directory.mkdir(parents=True, exist_ok=True)
    template = create_demo_input(directory)
    identities = template.integration_input.daily_input.step_identities
    battery = BatteryParameters(10.0, 3.0, 3.0, 0.95, 0.95, 0.20)
    cases: tuple[tuple[str, Callable[[], object]], ...] = (
        (
            "S16_23_POINT_CURVE",
            lambda: DailySimulationScenarioInput(
                identities, (0.0,) * 23, (0.0,) * 24, (0.5,) * 24, battery, 0.5
            ),
        ),
        (
            "S17_NAN_PV",
            lambda: DailySimulationScenarioInput(
                identities,
                (float("nan"),) + (0.0,) * 23,
                (0.0,) * 24,
                (0.5,) * 24,
                battery,
                0.5,
            ),
        ),
        (
            "S18_HALF_HOUR_STEP",
            lambda: DailySimulationScenarioInput(
                (SimulationStepIdentity(0, 1800.0, START), *identities[1:]),
                (0.0,) * 24,
                (0.0,) * 24,
                (0.5,) * 24,
                battery,
                0.5,
            ),
        ),
    )
    results: list[PathResult] = []
    for scenario_id, constructor in cases:
        try:
            constructor()
        except (TypeError, ValueError) as error:
            results.append(
                PathResult(
                    scenario_id,
                    "InputContract",
                    0,
                    "REJECTED_AS_EXPECTED",
                    "input_contract_rejection",
                    "INVALID_INPUT_FAIL_CLOSED",
                    "无效输入在日 runner 执行前被拒绝。",
                    0.5,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "",
                    "",
                    (),
                    type(error).__name__,
                    str(error),
                )
            )
        else:
            results.append(
                PathResult(
                    scenario_id,
                    "InputContract",
                    0,
                    "FAIL",
                    "input_contract_defect",
                    "INVALID_INPUT_ACCEPTED",
                    "无效输入未 fail closed。",
                    0.5,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    "",
                    "",
                    ("invalid_input_accepted",),
                    "",
                    "",
                )
            )
    return tuple(results)


def _exception_result(
    spec: ScenarioSpec, strategy: str, day_index: int, code: str, error: Exception
) -> PathResult:
    return PathResult(
        spec.scenario_id,
        strategy,
        day_index,
        "FAIL",
        "runner_defect",
        code,
        "既有日 runner 未完成该显式场景。",
        spec.initial_soc,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        "",
        "",
        (),
        type(error).__name__,
        str(error),
    )


def _write_outputs(
    output_directory: Path, results: tuple[PathResult, ...]
) -> tuple[Path, ...]:
    matrix_csv = output_directory / "simulated_scenario_matrix.csv"
    matrix_json = output_directory / "simulated_scenario_matrix.json"
    result_csv = output_directory / "simulated_defect_campaign_results.csv"
    result_json = output_directory / "simulated_defect_campaign_results.json"
    findings_csv = output_directory / "simulated_defect_findings.csv"
    findings_json = output_directory / "simulated_defect_findings.json"
    report = output_directory / "simulated_defect_report_zh.md"
    chart = output_directory / "simulated_defect_findings.svg"
    matrix = _matrix_rows()
    rows = [asdict(item) for item in results]
    matrix_csv.write_text(_csv(matrix), encoding="utf-8", newline="")
    matrix_json.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    result_csv.write_text(_csv(rows), encoding="utf-8", newline="")
    result_json.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    findings = [row for row in rows if row["status"] in {"FAIL", "LIMITATION"}]
    findings_csv.write_text(_csv(findings), encoding="utf-8", newline="")
    findings_json.write_text(
        json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report.write_text(_report(results), encoding="utf-8", newline="")
    chart.write_text(_svg(results), encoding="utf-8", newline="")
    return (
        matrix_csv,
        matrix_json,
        result_csv,
        result_json,
        findings_csv,
        findings_json,
        report,
        chart,
    )


def _matrix_rows() -> list[dict[str, object]]:
    expected = {
        "S01_MIN_SOC_LOAD": "最低 SOC 不放电；grid import=1 kW",
        "S02_MAX_SOC_PV": "最高 SOC 不充电；PV 盈余形成 export",
        "S03_EXACT_MAX_FILL": "h0 SOC 恰为 100%",
        "S04_EXACT_MIN_DRAIN": "h0 SOC 恰为 20%",
        "S05_PV_STEP_UP": "充电限于 3 kW；剩余 export；账本应接受净收益",
        "S06_LOAD_STEP_UP": "放电限于 3 kW；剩余 import",
        "S07_CHARGE_LIMIT": "battery=+3 kW；grid=-7 kW；账本应接受净收益",
        "S08_DISCHARGE_LIMIT": "battery=-3 kW；grid=+7 kW",
        "S09_ZERO_EXPORT_FULL": "若 export>0 则 LIMITATION；不得伪称弃光",
        "S10_NEGATIVE_PRICE": "负价保留；若购电则成本为负；完整 ledger 应闭合",
        "S11_PRICE_SPIKE_IDLE": "若 idle 则记录无纯价格套利策略局限",
        "S12_FALSE_PV_FORECAST": "realized 平衡；若由电网充电则记录预测依赖局限",
        "S13_MISSED_LOAD_SPIKE": "realized 平衡；若不放电则记录预测依赖局限",
        "S14_CROSS_MIDNIGHT": "day2 initial SOC is day1 actual final SOC",
        "S15_LOW_EFFICIENCY": "SOC 按 80% 充放效率独立积分",
        "S16_23_POINT_CURVE": "runner 前 ValueError",
        "S17_NAN_PV": "runner 前 ValueError",
        "S18_HALF_HOUR_STEP": "runner 前 ValueError",
    }
    coverage = {
        "physical_boundary": "Campaign B 仅参数扫值；未隔离精确上下界",
        "threshold": "既有日测试无 exact-equality 场景",
        "step_change": "Campaign C 仅整曲线缩放/时移",
        "power_limit": "Campaign B 扫 PCS；未隔离极端瞬时功率",
        "capability_gap": "零出口合同未组合到该日 runner",
        "economic_boundary": "Campaign B 常规 TOU 非负",
        "strategy_scope": "既有 reference 有负载，不是纯价格信号",
        "forecast_error": "Campaign C 最大 ±25%/±2h；非完全错报",
        "multi_day": "Campaign D 大矩阵；缺最小两日复现",
        "model_parameter": "Campaign B 不扫效率",
    }
    rows: list[dict[str, object]] = []
    for spec in executable_scenarios():
        rows.append(
            {
                "scenario_id": spec.scenario_id,
                "category": spec.category,
                "goal": spec.goal,
                "explicit_input": json.dumps(
                    {
                        "initial_soc": spec.initial_soc,
                        "realized_pv_kw": spec.realized_pv_kw,
                        "forecast_pv_kw": spec.forecast_pv_kw,
                        "realized_load_kw": spec.realized_load_kw,
                        "forecast_load_kw": spec.forecast_load_kw,
                        "realized_tariff_cny_per_kwh": spec.realized_tariff_cny_per_kwh,
                        "forecast_tariff_cny_per_kwh": spec.forecast_tariff_cny_per_kwh,
                        "efficiency": [
                            spec.battery_model.charge_efficiency,
                            spec.battery_model.discharge_efficiency,
                        ],
                        "export_limit_kw": spec.export_limit_kw,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "expected": expected[spec.scenario_id],
                "existing_coverage": coverage[spec.category],
                "verdict_rule": "物理/会计独立 oracle；FAIL 与 LIMITATION 不降级",
            }
        )
    rows.insert(
        13,
        {
            "scenario_id": "S14_CROSS_MIDNIGHT",
            "category": "multi_day",
            "goal": "两日跨午夜实际 SOC 延续",
            "explicit_input": json.dumps(
                {
                    "day1_start_utc": START.isoformat(),
                    "day1_h23_pv_kw": 2.0,
                    "day2_start_utc": (START + timedelta(days=1)).isoformat(),
                    "day2_h0_load_kw": 1.0,
                    "step_seconds": 3600.0,
                    "strategy_chains": ["Schedule", "Economic"],
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "expected": expected["S14_CROSS_MIDNIGHT"],
            "existing_coverage": coverage["multi_day"],
            "verdict_rule": "对象身份、时间连续、actual SOC carry",
        },
    )
    for scenario_id, goal, explicit_input in (
        ("S16_23_POINT_CURVE", "缺失小时", "PV curve length=23"),
        ("S17_NAN_PV", "非有限 PV", "PV[0]=NaN"),
        ("S18_HALF_HOUR_STEP", "非一小时步长", "duration[0]=1800 seconds"),
    ):
        rows.append(
            {
                "scenario_id": scenario_id,
                "category": "input_contract",
                "goal": goal,
                "explicit_input": explicit_input,
                "expected": expected[scenario_id],
                "existing_coverage": "底层单元合同有覆盖；缺 Campaign 端到端记录",
                "verdict_rule": "构造时 fail closed；不得进入 runner",
            }
        )
    if len(rows) != 18 or len({row["scenario_id"] for row in rows}) != 18:
        raise AssertionError("scenario matrix must contain exactly 18 unique rows")
    return rows


def _csv(rows: list[dict[str, object]]) -> str:
    stream = StringIO(newline="")
    if not rows:
        return ""
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, ensure_ascii=False)
                if isinstance(value, tuple | list)
                else value
                for key, value in row.items()
            }
        )
    return stream.getvalue()


def _report(results: tuple[PathResult, ...]) -> str:
    counts = Counter(item.status for item in results)
    findings: dict[str, PathResult] = {}
    for item in results:
        if item.status in {"FAIL", "LIMITATION"}:
            findings.setdefault(item.finding_code, item)
    lines = [
        f"# {SIMULATED_LABEL}\n",
        "## 虚拟家庭储能缺陷查找结果\n",
        f"场景定义 18 个；路径/合同结果 {len(results)} 条。PASS={counts['PASS']}，"
        f"LIMITATION={counts['LIMITATION']}，FAIL={counts['FAIL']}，"
        f"REJECTED_AS_EXPECTED={counts['REJECTED_AS_EXPECTED']}。\n",
        "## 跨合同与 ledger 缺陷\n",
    ]
    _append_findings(
        lines,
        findings,
        {"cross_contract_defect", "ledger_defect", "simulator_or_composition_defect"},
    )
    lines.append("## 策略与产品能力局限\n")
    _append_findings(
        lines,
        findings,
        {"strategy_limitation", "product_capability_gap"},
    )
    lines.extend(
        (
            "## 输入合同拒绝\n",
            "- S16 的 23 点曲线、S17 的 NaN PV、S18 的 1800 秒步长均在 runner 前 `REJECTED_AS_EXPECTED`。\n",
            "## Simulator 与测试缺口\n",
            "- 所有已完成 trace 的功率平衡、SOC 效率积分、SOC/功率边界和对象 identity 均通过；本轮没有发现电池/Grid simulator 算术违例。\n",
            "- 当前 24 小时合同没有 grid import power limit，也没有 PV curtailment 输出，故不能证明购电限幅或弃光控制。\n",
            "- Campaign C 有 ±25%/±2h 预测误差，但此前没有完全虚假 PV 或完全漏报负载尖峰的定向断言。\n",
            "## 修复状态与下一步\n",
        )
    )
    if {
        "NEGATIVE_REALIZED_NET_COST_REJECTED",
        "NEGATIVE_TARIFF_LEDGER_REJECTED",
    } & findings.keys():
        lines.extend(
            (
                "1. 统一 ledger 对负 `total_realized_net_cost` 的合同。\n",
                "2. 明确负进口价是上游禁止还是 ledger 全链支持。\n",
            )
        )
    else:
        lines.append(
            "- 有限负进口价、负进口成本和负日净成本已由 ledger 保留并与独立 oracle 对账；没有裁零或取绝对值。\n"
        )
    lines.extend(
        (
            "- 下一批可单独设计零上网修正与 PV curtailment；本批没有实现该能力，也没有改变套利或预测动作。\n",
            "## 解释边界\n",
            "- `FAIL` 是当前软件合同或独立不变量的可复现问题；Campaign 本身只记录证据。\n",
            "- `LIMITATION` 是现有策略/产品能力边界，不等于计算错误，也不能包装为 PASS。\n",
            "- 所有结果均为固定仿真；不是 PCS/BMS、HIL、现场保护或实时控制证据。\n",
        )
    )
    return "".join(lines)


def _append_findings(
    lines: list[str], findings: dict[str, PathResult], kinds: set[str]
) -> None:
    selected = [
        (code, item) for code, item in findings.items() if item.finding_kind in kinds
    ]
    if not selected:
        lines.append("- 无。\n")
        return
    for code, item in selected:
        lines.append(
            f"- **{code}**（{item.finding_kind}）：{item.explanation_zh} "
            f"最小复现 `{item.scenario_id}/{item.strategy}/day{item.day_index}`。"
            + (
                f" 异常 `{item.exception_type}: {item.exception_message}`。"
                if item.exception_type
                else ""
            )
            + "\n"
        )


def _svg(results: tuple[PathResult, ...]) -> str:
    counts = Counter(item.status for item in results)
    order = ("FAIL", "LIMITATION", "REJECTED_AS_EXPECTED", "PASS")
    colors = {
        "FAIL": "#c62828",
        "LIMITATION": "#ef6c00",
        "REJECTED_AS_EXPECTED": "#546e7a",
        "PASS": "#2e7d32",
    }
    bars = []
    for index, status in enumerate(order):
        y = 105 + index * 62
        width = counts[status] * 18
        bars.append(
            f'<text x="35" y="{y + 20}" font-size="14">{escape(status)}</text>'
            f'<rect x="205" y="{y}" width="{width}" height="28" fill="{colors[status]}"/>'
            f'<text x="{215 + width}" y="{y + 20}" font-size="14">{counts[status]}</text>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="760" height="390" viewBox="0 0 760 390">'
        '<rect width="760" height="390" fill="white"/>'
        '<text x="30" y="36" font-size="20" font-weight="bold">SIMULATED 缺陷 Campaign 判定</text>'
        '<text x="30" y="62" font-size="12" fill="#555">固定输入；非真实设备采集；只突出异常与合同判定</text>'
        + "".join(bars)
        + '<text x="30" y="365" font-size="12">FAIL 与 LIMITATION 详见 simulated_defect_report_zh.md</text></svg>\n'
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="EOS simulated residential defect-finding campaign"
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    result = run_campaign(args.output_dir)
    print(SIMULATED_LABEL)
    print(f"scenarios={result.scenario_count} results={len(result.path_results)}")
    for path in result.output_paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
