"""Fixed-request sidecar comparison; never changes the legacy daily runner."""

import argparse
import csv
import json
from dataclasses import replace
from pathlib import Path

from ems_simulator.demo import create_demo_scenario
from ems_simulator.input import BatteryParameters, DailySimulationScenarioInput
from ems_simulator.runner import DailySimulationRunner
from ems_simulator.time_energy import (
    PowerInterval,
    SimulationCadences,
    TimeEnergyInput,
    simulate_time_energy,
)

HOUR_SECONDS = 3600.0
ABS_LIMIT = 1e-10
MEASURES = (
    "soc_end",
    "actual_average_kw",
    "charge_kwh",
    "discharge_kwh",
    "grid_import_kwh",
    "grid_export_kwh",
)


def scenarios() -> dict[str, DailySimulationScenarioInput]:
    """Keep each scenario's physical facts identical across both evaluators."""
    demo = create_demo_scenario()
    zeros = (0.0,) * 24
    normal = replace(
        demo,
        battery_parameters=replace(demo.battery_parameters, capacity_kwh=100.0),
    )
    upper = replace(
        demo,
        initial_soc=0.98,
        pv_power_curve_kw=(4.0, *zeros[1:]),
        load_power_curve_kw=(1.0, *zeros[1:]),
    )
    lower = replace(
        demo,
        initial_soc=0.21,
        pv_power_curve_kw=zeros,
        load_power_curve_kw=(3.0, *zeros[1:]),
    )
    boundary_parameters = BatteryParameters(10.0, 3.0, 3.0, 1.0, 1.0, 0.2)
    hour_boundary = replace(
        demo,
        battery_parameters=boundary_parameters,
        initial_soc=0.5,
        pv_power_curve_kw=(0.0, 3.0, *zeros[2:]),
        load_power_curve_kw=(3.0, 1.0, *zeros[2:]),
    )
    return {
        "normal_day": normal,
        "upper_bound": upper,
        "lower_bound": lower,
        "hour_boundary": hour_boundary,
    }


def compare_scenario(
    scenario: DailySimulationScenarioInput,
) -> tuple[list[dict[str, float | int | str | bool]], tuple[float, ...]]:
    """Record old requests once and compare per-hour delivered facts."""
    old = DailySimulationRunner.run(scenario)
    requests = tuple(
        trace.simulation_input.battery_input.actuation.battery_power_kw
        for trace in old.traces
    )
    intervals = tuple(
        PowerInterval(
            hour * HOUR_SECONDS,
            (hour + 1) * HOUR_SECONDS,
            scenario.load_power_curve_kw[hour],
            scenario.pv_power_curve_kw[hour],
            requests[hour],
        )
        for hour in range(24)
    )
    new = simulate_time_energy(
        TimeEnergyInput(
            SimulationCadences(3600.0, 3600.0, 3600.0, 3600.0, 3600.0),
            intervals,
            scenario.battery_parameters,
            scenario.initial_soc,
        )
    )

    rows: list[dict[str, float | int | str | bool]] = []
    for hour, trace in enumerate(old.traces):
        start, end = hour * HOUR_SECONDS, (hour + 1) * HOUR_SECONDS
        slices = [item for item in new.slices if start <= item.start_seconds < end]
        if not slices or slices[-1].end_seconds != end:
            raise AssertionError(f"new slices do not finish hour {hour}")
        if (
            abs(
                sum(item.end_seconds - item.start_seconds for item in slices)
                - HOUR_SECONDS
            )
            > ABS_LIMIT
        ):
            raise AssertionError(f"new slices do not cover hour {hour}")
        if any(item.requested_battery_power_kw != requests[hour] for item in slices):
            raise AssertionError(f"request was not replayed exactly at hour {hour}")

        old_actual = trace.state.battery_result.actual_power_kw
        old_grid = trace.state.grid_result.actual_grid_power_kw
        old_measures = {
            "soc_end": trace.state.battery_result.next_state.soc,
            "actual_average_kw": old_actual,
            "charge_kwh": max(old_actual, 0.0),
            "discharge_kwh": max(-old_actual, 0.0),
            "grid_import_kwh": max(old_grid, 0.0),
            "grid_export_kwh": max(-old_grid, 0.0),
        }
        new_measures = {
            "soc_end": slices[-1].soc_after,
            "actual_average_kw": sum(
                item.actual_battery_power_kw
                * (item.end_seconds - item.start_seconds)
                / HOUR_SECONDS
                for item in slices
            ),
            "charge_kwh": sum(
                max(item.actual_battery_power_kw, 0.0)
                * (item.end_seconds - item.start_seconds)
                / HOUR_SECONDS
                for item in slices
            ),
            "discharge_kwh": sum(
                max(-item.actual_battery_power_kw, 0.0)
                * (item.end_seconds - item.start_seconds)
                / HOUR_SECONDS
                for item in slices
            ),
            "grid_import_kwh": sum(
                max(item.grid_power_kw, 0.0)
                * (item.end_seconds - item.start_seconds)
                / HOUR_SECONDS
                for item in slices
            ),
            "grid_export_kwh": sum(
                max(-item.grid_power_kw, 0.0)
                * (item.end_seconds - item.start_seconds)
                / HOUR_SECONDS
                for item in slices
            ),
        }
        for measure in MEASURES:
            legacy_value, sidecar_value = old_measures[measure], new_measures[measure]
            rows.append(
                {
                    "hour": hour,
                    "request_kw": requests[hour],
                    "legacy_actual_kw": old_actual,
                    "measure": measure,
                    "legacy": legacy_value,
                    "sidecar": sidecar_value,
                    "delta": sidecar_value - legacy_value,
                    "within_limit": abs(sidecar_value - legacy_value) <= ABS_LIMIT,
                    "sidecar_slices": len(slices),
                }
            )
    return rows, requests


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=False)

    all_rows: list[dict[str, float | int | str | bool]] = []
    replay: dict[str, object] = {}
    for name, scenario in scenarios().items():
        rows, requests = compare_scenario(scenario)
        all_rows.extend({"scenario": name, **row} for row in rows)
        replay[name] = {
            "initial_soc": scenario.initial_soc,
            "battery_parameters": {
                key: getattr(scenario.battery_parameters, key)
                for key in (
                    "capacity_kwh",
                    "max_charge_power_kw",
                    "max_discharge_power_kw",
                    "charge_efficiency",
                    "discharge_efficiency",
                    "reserve_soc",
                )
            },
            "pv_power_curve_kw": scenario.pv_power_curve_kw,
            "load_power_curve_kw": scenario.load_power_curve_kw,
            "recorded_requests_kw": requests,
        }

    with (arguments.output_dir / "hourly_comparison.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=tuple(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)
    (arguments.output_dir / "replay_inputs.json").write_text(
        json.dumps(replay, indent=2) + "\n", encoding="utf-8"
    )
    for name in replay:
        sample = [row for row in all_rows if row["scenario"] == name]
        failures = [row for row in sample if not row["within_limit"]]
        clipped = {
            int(row["hour"])
            for row in sample
            if abs(float(row["request_kw"]) - float(row["legacy_actual_kw"]))
            > ABS_LIMIT
        }
        split = {int(row["hour"]) for row in sample if int(row["sidecar_slices"]) > 1}
        max_delta = max(abs(float(row["delta"])) for row in sample)
        print(
            f"{name}: rows={len(sample)} outside_limit={len(failures)} "
            f"max_abs_delta={max_delta:.12g} clipped_hours={sorted(clipped)} "
            f"split_hours={sorted(split)}"
        )
    return 1 if any(not row["within_limit"] for row in all_rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
