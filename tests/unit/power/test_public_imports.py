"""Tests for the public power-domain import boundary."""

from kernel.power import PowerFlow


def test_power_flow_is_publicly_importable() -> None:
    flow = PowerFlow(
        pv_power_kw=1.0,
        load_power_kw=1.0,
        battery_power_kw=0.0,
        grid_power_kw=0.0,
    )

    assert isinstance(flow, PowerFlow)
