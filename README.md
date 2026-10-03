# EOS — Energy Operating System

*An Open Architecture for Explainable Energy Decision Systems*

EOS is the reference implementation of an Energy Decision Kernel. It provides
an engineering foundation for stable kernel architecture, evolving
capabilities, immutable domain objects, runtime-owned state transitions, and
first-class replay.

## EOS EMS Simulator 1.0 Demo

Run the deterministic 24-hour household PV and Battery example:

```powershell
python -m ems_simulator.demo --output-dir simulation_output
```

The command produces `simulation_result.csv`, `power_curve.svg`, `soc_curve.svg`, and
`daily_summary.txt`. See [the Demo guide](docs/EOS_EMS_Simulator_1.0_Demo.md) for the
scenario, sign conventions, and output interpretation.

The repository includes the evolving decision-kernel architecture and a
deterministic 24-hour Simulator 1.0 Demo. The Demo rule validates simulation
integration; it is not a production energy-management or device-control system.

## Virtual home storage teaching example

Run five bounded simulated scenarios through the actual self-consumption strategy
and controlled Edge composition:

```bash
python -m examples.virtual_home_storage.demo --output /tmp/eos-virtual-home-output
```

See the [Chinese teaching guide](docs/learning/VIRTUAL_HOME_STORAGE_GUIDE.md) for
explicit fixture approval, power limits, expiry and ACK mismatch. Outputs separate
virtual execution from scripted observations; they are not real device measurements.

Run the complementary 24-hour simulated household example:

```bash
python -m examples.virtual_home_storage_day.demo --output-dir /tmp/eos-virtual-home-day
```

It reuses the existing Residential EMS reference runner and produces linked PV,
load, battery, grid import/export and SOC curves plus Chinese hourly decision
records. See the [24-hour Chinese guide](docs/learning/VIRTUAL_HOME_STORAGE_DAY_GUIDE.md).

Run the bounded simulation-only defect campaign:

```bash
python -m examples.virtual_home_storage_defect_campaign.campaign \
  --output-dir /tmp/eos-defect-campaign
```

It targets 18 gaps left after Campaigns B/C/D, records cross-contract failures
and strategy limitations, and exports a machine-readable matrix plus CSV/JSON
evidence. See the
[Chinese defect-campaign guide](docs/learning/VIRTUAL_HOME_STORAGE_DEFECT_CAMPAIGN_GUIDE.md)
and the [signed-ledger contract](docs/learning/SIGNED_ECONOMIC_LEDGER_CONTRACT.md).

## Development

EOS requires Python 3.12.

```bash
python -m pip install -e ".[dev]"
pre-commit install
ruff check .
ruff format --check .
mypy .
pytest
```
