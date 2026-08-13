# TASK-131 - Net-Load-Aware 24h MPC Demo Integration

## Objective

Integrate `NetLoadAwareBaselineOptimizer` into the existing explainable,
physically-aware 24-hour MPC application path, while retaining the TASK-129
price-only CLI unchanged as the A/B baseline.

## A/B architecture

```text
TASK-129 price-only demo
PriceAwareBaselineOptimizer -> Physical Revision -> 24h MPC -> Simulator

TASK-131 comparison demo
NetLoadAwareBaselineOptimizer -> same Physical Revision -> same 24h MPC -> same Simulator
```

The new runnable entry is:

```text
python -m ems_simulator.net_load_mpc_demo --output-dir simulation_output_net_load_mpc
```

It writes the same five artifacts as TASK-129: decision CSV, simulation CSV,
power SVG, SOC SVG, and daily summary.

## Preserved scenario and downstream evidence

TASK-131 reuses the TASK-129 profiles, UTC start time, 10 kWh battery, 50%
initial SOC, 20% reserve/minimum SOC, 100% maximum SOC, 3 kW charge/discharge
limits, 95% efficiencies, one-hour steps, and four-point repeating-day perfect
forecast convention. It changes only the candidate optimizer and identifies its
decisions with `physically-aware-net-load-mpc@1.0`.

Forecast -> OptimizationProblem -> Net-Load candidate -> Physical Revision ->
Control Plan -> Current Action -> EMSDecision -> Explanation -> Journal -> CSV
-> Feasibility -> Actuation -> Simulator remains intact.

## Behavioral semantics

- A high-price PV-surplus hour requests charge by exact PV surplus, never a
  price-driven discharge. Physical revision may reduce that request to idle at
  maximum SOC and records `max_soc_limit` evidence.
- A high-price load-deficit hour requests discharge by exact `load - pv`; it
  cannot request more than current forecast net household demand.
- Battery SOC and power revision remain active and separate from the candidate
  rule.

## Known limitation

Net-load awareness does not reserve headroom for future PV. Cheap overnight
grid charging can still fill the battery before daytime surplus arrives, so
PV-caused export can remain substantial. TASK-131 does not add terminal SOC,
export tariff, global optimization, zero-export behavior, or any runtime/device
feature.
