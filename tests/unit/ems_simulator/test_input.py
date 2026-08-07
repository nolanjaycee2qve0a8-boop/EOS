"""Tests for immutable 24-hour simulation input contracts."""

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from math import inf, nan

import pytest

from ems_simulator import BatteryParameters, DailySimulationScenarioInput
from simulator import SimulationStepIdentity


def make_steps() -> tuple[SimulationStepIdentity, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    return tuple(
        SimulationStepIdentity(
            sequence=hour,
            duration_seconds=3600,
            timestamp=start + timedelta(hours=hour),
        )
        for hour in range(24)
    )


def make_battery_parameters() -> BatteryParameters:
    return BatteryParameters(
        capacity_kwh=10,
        max_charge_power_kw=5,
        max_discharge_power_kw=5,
        charge_efficiency=0.95,
        discharge_efficiency=0.95,
        reserve_soc=0.2,
    )


def make_scenario(**overrides: object) -> DailySimulationScenarioInput:
    values: dict[str, object] = {
        "step_identities": make_steps(),
        "pv_power_curve_kw": tuple(float(hour) for hour in range(24)),
        "load_power_curve_kw": (2.0,) * 24,
        "tariff_curve_cny_per_kwh": (0.5,) * 24,
        "battery_parameters": make_battery_parameters(),
        "initial_soc": 0.5,
    }
    values.update(overrides)
    return DailySimulationScenarioInput(**values)  # type: ignore[arg-type]


def test_valid_scenario_preserves_exact_inputs_and_caller_order() -> None:
    steps = make_steps()
    pv_curve = tuple(float(hour) for hour in range(24))
    load_curve = tuple(float(24 - hour) for hour in range(24))
    tariff_curve = tuple(-0.1 if hour == 0 else 0.5 for hour in range(24))
    battery = make_battery_parameters()

    scenario = make_scenario(
        step_identities=steps,
        pv_power_curve_kw=pv_curve,
        load_power_curve_kw=load_curve,
        tariff_curve_cny_per_kwh=tariff_curve,
        battery_parameters=battery,
    )

    assert scenario.step_identities is steps
    assert scenario.pv_power_curve_kw is pv_curve
    assert scenario.load_power_curve_kw is load_curve
    assert scenario.tariff_curve_cny_per_kwh is tariff_curve
    assert scenario.battery_parameters is battery
    assert scenario.step_identities[7] is steps[7]
    assert scenario.pv_power_curve_kw == pv_curve
    assert scenario.tariff_curve_cny_per_kwh[0] == -0.1


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("capacity_kwh", 0),
        ("capacity_kwh", inf),
        ("max_charge_power_kw", -1),
        ("max_discharge_power_kw", nan),
        ("charge_efficiency", 0),
        ("charge_efficiency", 1.1),
        ("discharge_efficiency", 0),
        ("reserve_soc", -0.1),
        ("reserve_soc", 1.1),
    ],
)
def test_battery_parameters_reject_invalid_values(
    field_name: str,
    value: float,
) -> None:
    values = {
        "capacity_kwh": 10,
        "max_charge_power_kw": 5,
        "max_discharge_power_kw": 5,
        "charge_efficiency": 0.95,
        "discharge_efficiency": 0.95,
        "reserve_soc": 0.2,
    }
    values[field_name] = value

    with pytest.raises(ValueError):
        BatteryParameters(**values)


def test_battery_parameters_reject_boolean_number() -> None:
    with pytest.raises(TypeError):
        BatteryParameters(True, 5, 5, 0.95, 0.95, 0.2)


@pytest.mark.parametrize(
    "field_name",
    [
        "step_identities",
        "pv_power_curve_kw",
        "load_power_curve_kw",
        "tariff_curve_cny_per_kwh",
    ],
)
def test_scenario_rejects_mutable_lists(field_name: str) -> None:
    with pytest.raises(TypeError):
        make_scenario(**{field_name: [0.0] * 24})


@pytest.mark.parametrize(
    "field_name",
    [
        "step_identities",
        "pv_power_curve_kw",
        "load_power_curve_kw",
        "tariff_curve_cny_per_kwh",
    ],
)
def test_scenario_rejects_non_24_hour_inputs(field_name: str) -> None:
    value: tuple[object, ...] = (
        make_steps()[:-1] if field_name == "step_identities" else (0.0,) * 23
    )
    with pytest.raises(ValueError):
        make_scenario(**{field_name: value})


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("pv_power_curve_kw", (-1.0,) + (0.0,) * 23),
        ("load_power_curve_kw", (inf,) + (0.0,) * 23),
        ("tariff_curve_cny_per_kwh", (nan,) + (0.0,) * 23),
        ("pv_power_curve_kw", (True,) + (0.0,) * 23),
    ],
)
def test_scenario_rejects_invalid_curve_values(
    field_name: str,
    value: tuple[object, ...],
) -> None:
    expected_error = TypeError if value[0] is True else ValueError
    with pytest.raises(expected_error):
        make_scenario(**{field_name: value})


def test_scenario_rejects_invalid_battery_parameters_type() -> None:
    with pytest.raises(TypeError):
        make_scenario(battery_parameters=object())


@pytest.mark.parametrize("initial_soc", [-0.1, 1.1, nan])
def test_scenario_rejects_invalid_initial_soc(initial_soc: float) -> None:
    with pytest.raises(ValueError):
        make_scenario(initial_soc=initial_soc)


def test_scenario_rejects_boolean_initial_soc() -> None:
    with pytest.raises(TypeError):
        make_scenario(initial_soc=True)


def test_scenario_requires_exact_sequence_order() -> None:
    steps = make_steps()
    reordered = (steps[1], steps[0], *steps[2:])

    with pytest.raises(ValueError, match="sequences"):
        make_scenario(step_identities=reordered)


def test_scenario_requires_exact_hour_duration() -> None:
    steps = make_steps()
    replacement = SimulationStepIdentity(0, 1800, steps[0].timestamp)

    with pytest.raises(ValueError, match="3600"):
        make_scenario(step_identities=(replacement, *steps[1:]))


def test_scenario_requires_explicit_consecutive_timestamps() -> None:
    steps = make_steps()
    missing = SimulationStepIdentity(0, 3600, None)
    with pytest.raises(ValueError, match="explicitly supplied"):
        make_scenario(step_identities=(missing, *steps[1:]))

    second_timestamp = steps[1].timestamp
    assert second_timestamp is not None
    skipped = SimulationStepIdentity(
        1,
        3600,
        second_timestamp + timedelta(hours=1),
    )
    with pytest.raises(ValueError, match="consecutive"):
        make_scenario(step_identities=(steps[0], skipped, *steps[2:]))


def test_contracts_are_frozen_slotted_and_contain_no_mutable_containers() -> None:
    battery = make_battery_parameters()
    scenario = make_scenario(battery_parameters=battery)

    assert not hasattr(battery, "__dict__")
    assert not hasattr(scenario, "__dict__")
    assert tuple(field.name for field in fields(BatteryParameters)) == (
        "capacity_kwh",
        "max_charge_power_kw",
        "max_discharge_power_kw",
        "charge_efficiency",
        "discharge_efficiency",
        "reserve_soc",
    )
    assert tuple(field.name for field in fields(DailySimulationScenarioInput)) == (
        "step_identities",
        "pv_power_curve_kw",
        "load_power_curve_kw",
        "tariff_curve_cny_per_kwh",
        "battery_parameters",
        "initial_soc",
    )
    with pytest.raises(FrozenInstanceError):
        scenario.initial_soc = 0.6  # type: ignore[misc]


def test_equal_reconstructed_battery_is_not_substituted() -> None:
    original = make_battery_parameters()
    reconstructed = make_battery_parameters()
    scenario = make_scenario(battery_parameters=original)

    assert reconstructed == original
    assert reconstructed is not original
    assert scenario.battery_parameters is original
    assert scenario.battery_parameters is not reconstructed
