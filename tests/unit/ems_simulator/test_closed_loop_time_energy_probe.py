"""SOC-feedback and cadence invariants for the independent time/energy probe."""

import pytest

from tools.closed_loop_time_energy_probe import (
    DAY_SECONDS,
    HOUR_SECONDS,
    ProbeResult,
    cases,
    hourly_rows,
    run_probe,
)

TIME_ABS_SECONDS = 1e-9
POWER_ABS_KW = 1e-10
SOC_ABS = 1e-9
ENERGY_ABS_PER_HOUR_KWH = 4e-11


def energy_limit(seconds: float) -> float:
    return ENERGY_ABS_PER_HOUR_KWH * max(seconds, 1.0) / HOUR_SECONDS


def assert_physical_invariants(result: ProbeResult) -> None:
    parameters = result.case.battery_parameters
    assert len(result.decisions) == DAY_SECONDS // result.control_period_seconds
    assert [item.time_seconds for item in result.decisions] == list(
        range(0, DAY_SECONDS, result.control_period_seconds)
    )
    assert result.slices[0].start_seconds == 0
    assert result.slices[-1].end_seconds == DAY_SECONDS

    previous_end = 0.0
    previous_soc = result.case.initial_soc
    charge_kwh = discharge_kwh = import_kwh = export_kwh = 0.0
    load_kwh = pv_kwh = 0.0
    external_boundaries = {
        item.start_seconds for item in result.case.external_segments[1:]
    }
    control_boundaries = set(
        range(result.control_period_seconds, DAY_SECONDS, result.control_period_seconds)
    )
    for item in result.slices:
        assert abs(item.start_seconds - previous_end) <= TIME_ABS_SECONDS
        assert item.start_seconds < item.end_seconds
        assert not any(
            item.start_seconds < boundary < item.end_seconds
            for boundary in external_boundaries | control_boundaries
        )
        duration_seconds = item.end_seconds - item.start_seconds
        duration_hours = duration_seconds / HOUR_SECONDS
        assert abs(item.soc_before - previous_soc) <= SOC_ABS
        assert parameters.reserve_soc - SOC_ABS <= item.soc_after <= 1.0 + SOC_ABS
        assert (
            -parameters.max_discharge_power_kw - POWER_ABS_KW
            <= item.actual_power_kw
            <= parameters.max_charge_power_kw + POWER_ABS_KW
        )
        assert (
            abs(
                item.grid_power_kw
                - (item.load_power_kw + item.actual_power_kw - item.pv_power_kw)
            )
            <= POWER_ABS_KW
        )
        decision_index = int(item.start_seconds // result.control_period_seconds)
        assert (
            item.request_power_kw == result.decisions[decision_index].request_power_kw
        )

        delivered_kwh = item.actual_power_kw * duration_hours
        storage_delta_kwh = (item.soc_after - item.soc_before) * parameters.capacity_kwh
        if delivered_kwh >= 0:
            assert abs(
                storage_delta_kwh - delivered_kwh * parameters.charge_efficiency
            ) <= energy_limit(duration_seconds)
        else:
            assert abs(
                storage_delta_kwh - delivered_kwh / parameters.discharge_efficiency
            ) <= energy_limit(duration_seconds)
        charge_kwh += max(delivered_kwh, 0.0)
        discharge_kwh += max(-delivered_kwh, 0.0)
        import_kwh += max(item.grid_power_kw, 0.0) * duration_hours
        export_kwh += max(-item.grid_power_kw, 0.0) * duration_hours
        load_kwh += item.load_power_kw * duration_hours
        pv_kwh += item.pv_power_kw * duration_hours
        previous_end = item.end_seconds
        previous_soc = item.soc_after

    full_limit = energy_limit(DAY_SECONDS)
    assert abs(previous_soc - result.final_soc) <= SOC_ABS
    assert abs(import_kwh - result.grid_import_energy_kwh) <= full_limit
    assert abs(export_kwh - result.grid_export_energy_kwh) <= full_limit
    assert abs(load_kwh - result.load_energy_kwh) <= full_limit
    assert abs(pv_kwh - result.pv_energy_kwh) <= full_limit
    assert (
        abs(charge_kwh - discharge_kwh - result.battery_delivered_energy_kwh)
        <= full_limit
    )
    assert (
        abs(import_kwh - export_kwh - (load_kwh - pv_kwh + charge_kwh - discharge_kwh))
        <= full_limit
    )
    for decision in result.decisions[1:]:
        prior = next(
            item for item in result.slices if item.end_seconds == decision.time_seconds
        )
        assert abs(decision.feedback_soc - prior.soc_after) <= SOC_ABS


@pytest.mark.parametrize("name", tuple(cases()))
def test_fixed_control_events_are_stable_across_physical_steps(name: str) -> None:
    case = cases()[name]
    runs = [
        run_probe(case, physical_step_seconds=step) for step in (3600.0, 60.0, 15.0)
    ]
    for result in runs:
        assert_physical_invariants(result)
    reference = runs[0]
    for result in runs[1:]:
        assert [item.time_seconds for item in result.decisions] == [
            item.time_seconds for item in reference.decisions
        ]
        assert len(result.decisions) == 24
        assert abs(result.final_soc - reference.final_soc) <= SOC_ABS
        for field in (
            "load_energy_kwh",
            "pv_energy_kwh",
            "battery_delivered_energy_kwh",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
        ):
            assert abs(
                getattr(result, field) - getattr(reference, field)
            ) <= energy_limit(DAY_SECONDS)
        for actual, expected in zip(
            hourly_rows(result), hourly_rows(reference), strict=True
        ):
            assert abs(actual["soc_end"] - expected["soc_end"]) <= SOC_ABS
            for field in (
                "average_actual_kw",
                "charge_kwh",
                "discharge_kwh",
                "import_kwh",
                "export_kwh",
            ):
                limit = (
                    POWER_ABS_KW
                    if field == "average_actual_kw"
                    else energy_limit(HOUR_SECONDS)
                )
                assert abs(actual[field] - expected[field]) <= limit


def test_within_hour_event_reverses_grid_direction_without_netting() -> None:
    result = run_probe(cases()["flow_reversal"], physical_step_seconds=3600.0)
    assert_physical_invariants(result)

    first_hour = hourly_rows(result)[0]
    assert first_hour["import_kwh"] == pytest.approx(
        1.0, abs=energy_limit(HOUR_SECONDS)
    )
    assert first_hour["export_kwh"] == pytest.approx(
        1.0, abs=energy_limit(HOUR_SECONDS)
    )
    assert first_hour["import_kwh"] - first_hour["export_kwh"] == pytest.approx(0.0)
    assert result.decisions[0].request_power_kw == 0.0
    assert result.decisions[1].time_seconds == HOUR_SECONDS
    assert [(item.start_seconds, item.end_seconds) for item in result.slices[:2]] == [
        (0.0, 1800.0),
        (1800.0, 3600.0),
    ]
    assert result.slices[0].grid_power_kw > 0
    assert result.slices[1].grid_power_kw < 0


def test_lower_soc_feedback_changes_the_next_hour_request() -> None:
    result = run_probe(cases()["lower_bound"], physical_step_seconds=60.0)

    assert result.decisions[0].feedback_soc == 0.21
    assert result.decisions[0].request_power_kw == -3.0
    assert result.decisions[1].feedback_soc == pytest.approx(0.2, abs=SOC_ABS)
    assert result.decisions[1].request_power_kw == 0.0
    assert len(result.decisions) == 24


def test_record_and_display_cadences_cannot_change_physics_or_decisions() -> None:
    case = cases()["flow_reversal"]
    first = run_probe(
        case, physical_step_seconds=60.0, record_seconds=1.0, display_seconds=0.1
    )
    second = run_probe(
        case, physical_step_seconds=60.0, record_seconds=3600.0, display_seconds=3600.0
    )

    assert first.decisions == second.decisions
    assert hourly_rows(first) == hourly_rows(second)
    assert first.final_soc == second.final_soc
    assert first.grid_import_energy_kwh == second.grid_import_energy_kwh
    assert first.grid_export_energy_kwh == second.grid_export_energy_kwh
    assert len(first.decisions) == len(second.decisions) == 24


def test_control_period_change_is_a_strategy_change_not_integration_error() -> None:
    case = cases()["flow_reversal"]
    hourly = run_probe(case, physical_step_seconds=60.0, control_period_seconds=3600)
    half_hourly = run_probe(
        case, physical_step_seconds=60.0, control_period_seconds=1800
    )
    assert_physical_invariants(hourly)
    assert_physical_invariants(half_hourly)

    assert len(hourly.decisions) == 24
    assert len(half_hourly.decisions) == 48
    assert half_hourly.decisions[1].time_seconds == 1800
    assert half_hourly.decisions[1].request_power_kw == 2.0
    assert hourly.grid_import_energy_kwh == pytest.approx(1.0)
    assert hourly.grid_export_energy_kwh == pytest.approx(1.0)
    assert half_hourly.grid_import_energy_kwh == pytest.approx(1.0)
    assert half_hourly.grid_export_energy_kwh < hourly.grid_export_energy_kwh
