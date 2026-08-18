"""Residential EMS Campaign E: seeded synthetic forecast-error characterization.

This post-freeze validation module samples only caller-owned forecast facts and
reuses Campaign C's frozen daily execution composition.  It is not a stochastic
optimizer, production runtime, or field-calibrated forecast model.
"""

import argparse
import csv
import hashlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from io import StringIO
from math import ceil, isfinite, sqrt
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.sax.saxutils import escape

from ems_simulator.economic_comparison_explanation import EconomicComparisonRanking
from ems_simulator.economic_multi_opportunity_explainable_mpc_daily import (
    EconomicMultiOpportunityExplainableMPCDailySimulationResult,
    EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.multi_opportunity_explainable_mpc_daily import (
    MultiOpportunityExplainableMPCDailySimulationStepTrace,
)
from ems_simulator.residential_acceptance import (
    NUMERIC_TOLERANCE,
    DeterministicResidentialAcceptanceEvaluator,
)
from ems_simulator.residential_campaign_c import (
    ForecastErrorEvidence,
    ResidentialCampaignCPathResult,
    ResidentialCampaignCScenario,
    _actual_powers,
    _matches_perfect_anchor_fingerprint,
    _run_scenario,
    _shift_earlier,
    _shift_later,
    campaign_c_scenarios,
)

_SEED = 20260817
_SAMPLE_COUNT = 64
_ENVIRONMENTS = ("REFERENCE", "HIGH_PV", "HIGH_EVENING_LOAD")


@dataclass(frozen=True, slots=True)
class CampaignESampleDefinition:
    environment: str
    sample_index: int
    seed: int
    pv_amplitude_error: float
    load_amplitude_error: float
    tariff_amplitude_error: float
    pv_shift_hours: int
    load_shift_hours: int
    tariff_shift_hours: int


@dataclass(frozen=True, slots=True)
class CampaignEAnchorResult:
    environment: str
    strategy: str
    path: ResidentialCampaignCPathResult


@dataclass(frozen=True, slots=True)
class CampaignEPathResult:
    sample: CampaignESampleDefinition
    scenario: ResidentialCampaignCScenario
    strategy: str
    path: ResidentialCampaignCPathResult
    forecast_error: ForecastErrorEvidence

    @property
    def actual_powers_kw(self) -> tuple[float, ...]:
        """Actual simulator battery powers, deliberately not planned powers."""

        return _actual_powers(self.path)


@dataclass(frozen=True, slots=True)
class CampaignERegretEvidence:
    path: CampaignEPathResult
    anchor: CampaignEAnchorResult
    adjusted_cost_regret: float
    actual_power_divergence_hours: int
    maximum_actual_power_difference_kw: float


@dataclass(frozen=True, slots=True)
class CampaignEStrategyComparison:
    sample: CampaignESampleDefinition
    ranking: EconomicComparisonRanking
    adjusted_cost_delta: float


@dataclass(frozen=True, slots=True)
class CampaignEDistributionStatistic:
    environment: str
    strategy: str
    metric: str
    count: int
    mean: float
    population_standard_deviation: float
    minimum: float
    p05: float
    p50: float
    p90: float
    p95: float
    maximum: float
    positive_count: int
    zero_count: int
    negative_count: int


@dataclass(frozen=True, slots=True)
class CampaignEResult:
    samples: tuple[CampaignESampleDefinition, ...]
    anchors: tuple[CampaignEAnchorResult, ...]
    paths: tuple[CampaignEPathResult, ...]
    regrets: tuple[CampaignERegretEvidence, ...]
    comparisons: tuple[CampaignEStrategyComparison, ...]
    distributions: tuple[CampaignEDistributionStatistic, ...]
    anchor_fingerprints_reproduced: bool
    sampled_execution_count: int
    anchor_execution_count: int
    hard_passed: bool
    output_paths: tuple[Path, ...]


def campaign_e_samples() -> tuple[CampaignESampleDefinition, ...]:
    """Return order-independent, keyed synthetic sample definitions."""

    return tuple(
        CampaignESampleDefinition(
            environment,
            index,
            _SEED,
            _triangular(environment, index, "pv_amplitude", 0.30),
            _triangular(environment, index, "load_amplitude", 0.25),
            _triangular(environment, index, "tariff_amplitude", 0.20),
            _choice(
                environment,
                index,
                "pv_shift",
                (-2, -1, 0, 1, 2),
                (0.05, 0.15, 0.60, 0.15, 0.05),
            ),
            _choice(
                environment,
                index,
                "load_shift",
                (-2, -1, 0, 1, 2),
                (0.05, 0.15, 0.60, 0.15, 0.05),
            ),
            _choice(environment, index, "tariff_shift", (-1, 0, 1), (0.15, 0.70, 0.15)),
        )
        for environment in _ENVIRONMENTS
        for index in range(_SAMPLE_COUNT)
    )


def run_residential_campaign_e(output_directory: Path) -> CampaignEResult:
    """Execute the fixed synthetic matrix using one fresh runner per path."""

    if not isinstance(output_directory, Path):
        raise TypeError("output_directory must be a pathlib.Path")
    evaluator = DeterministicResidentialAcceptanceEvaluator()
    perfect = {
        scenario.environment: scenario
        for scenario in campaign_c_scenarios()
        if scenario.forecast_error_case_id == "PERFECT"
    }
    if set(perfect) != set(_ENVIRONMENTS):
        raise AssertionError(
            "Campaign E requires Campaign C's three perfect environments"
        )
    samples = campaign_e_samples()
    paths: list[CampaignEPathResult] = []
    comparisons: list[CampaignEStrategyComparison] = []
    # The existing daily runners write their own per-run decision CSV.  Campaign E
    # retains only its own aggregate validation evidence, so those transient files
    # are isolated from the deterministic campaign output directory.
    with TemporaryDirectory(prefix="eos_campaign_e_") as temporary_directory:
        transient = Path(temporary_directory)
        anchors = tuple(
            CampaignEAnchorResult(environment, strategy, path)
            for environment in _ENVIRONMENTS
            for result in (
                _run_scenario(
                    perfect[environment], transient / "anchors" / environment, evaluator
                ),
            )
            for strategy, path in (
                ("Schedule", result.schedule),
                ("Economic", result.economic),
            )
        )
        for sample in samples:
            scenario = _sampled_scenario(perfect[sample.environment], sample)
            result = _run_scenario(
                scenario,
                transient
                / "samples"
                / sample.environment
                / f"{sample.sample_index:02d}",
                evaluator,
            )
            paths.extend(
                (
                    CampaignEPathResult(
                        sample,
                        scenario,
                        "Schedule",
                        result.schedule,
                        result.forecast_error,
                    ),
                    CampaignEPathResult(
                        sample,
                        scenario,
                        "Economic",
                        result.economic,
                        result.forecast_error,
                    ),
                )
            )
            comparisons.append(
                CampaignEStrategyComparison(
                    sample,
                    result.comparison.ranking,
                    result.comparison.delta_adjusted_cost,
                )
            )
    anchor_by_key = {(item.environment, item.strategy): item for item in anchors}
    regrets = tuple(
        _regret(path, anchor_by_key[(path.sample.environment, path.strategy)])
        for path in paths
    )
    distributions = _distributions(regrets)
    anchors_reproduced = all(
        _matches_perfect_anchor_fingerprint(item.path) for item in anchors
    )
    sampled_paths = tuple(paths)
    hard_passed = (
        anchors_reproduced
        and len(samples) == 192
        and len(sampled_paths) == 384
        and len(anchors) == 6
        and len({id(item.path.trajectory) for item in sampled_paths + anchors}) == 390
        and all(item.path.acceptance.passed for item in sampled_paths)
        and all(
            item.path.kpi.ledger_reconciled and item.path.kpi.comparison_reconciled
            for item in sampled_paths
        )
        and all(_finite_regret(item) for item in regrets)
    )
    outputs = _write_outputs(
        output_directory,
        samples,
        anchors,
        sampled_paths,
        regrets,
        tuple(comparisons),
        distributions,
        anchors_reproduced,
        hard_passed,
    )
    return CampaignEResult(
        samples,
        anchors,
        sampled_paths,
        regrets,
        tuple(comparisons),
        distributions,
        anchors_reproduced,
        384,
        6,
        hard_passed,
        outputs,
    )


def _sampled_scenario(
    source: ResidentialCampaignCScenario, sample: CampaignESampleDefinition
) -> ResidentialCampaignCScenario:
    return replace(
        source,
        scenario_id=f"E_{sample.environment}_{sample.sample_index:02d}",
        forecast_error_case_id="SYNTHETIC",
        description=(
            f"Campaign E keyed synthetic forecast sample {sample.sample_index} "
            f"for {sample.environment}."
        ),
        forecast_pv_profile_kw=_transform(
            source.realized_pv_profile_kw,
            sample.pv_amplitude_error,
            sample.pv_shift_hours,
        ),
        forecast_load_profile_kw=_transform(
            source.realized_load_profile_kw,
            sample.load_amplitude_error,
            sample.load_shift_hours,
        ),
        forecast_tariff_profile_cny_per_kwh=_transform(
            source.realized_tariff_profile_cny_per_kwh,
            sample.tariff_amplitude_error,
            sample.tariff_shift_hours,
        ),
        transformation_metadata=(
            f"seed={sample.seed}; "
            f"pv={sample.pv_amplitude_error:.6f}/{sample.pv_shift_hours}; "
            f"load={sample.load_amplitude_error:.6f}/{sample.load_shift_hours}; "
            f"tariff={sample.tariff_amplitude_error:.6f}/"
            f"{sample.tariff_shift_hours}"
        ),
    )


def _transform(
    values: tuple[float, ...], amplitude: float, shift: int
) -> tuple[float, ...]:
    """Apply Campaign C's sign-preserving shift convention, then nonnegative scale."""

    if shift > 0:
        shifted = _shift_earlier(values, shift)
    elif shift < 0:
        shifted = _shift_later(values, -shift)
    else:
        shifted = values
    # Scaling leaves source zeroes at zero, so a PV night hour cannot be invented.
    return tuple(max(value * (1.0 + amplitude), 0.0) for value in shifted)


def _regret(
    path: CampaignEPathResult, anchor: CampaignEAnchorResult
) -> CampaignERegretEvidence:
    differences = tuple(
        abs(left - right)
        for left, right in zip(
            path.actual_powers_kw, _actual_powers(anchor.path), strict=True
        )
    )
    return CampaignERegretEvidence(
        path,
        anchor,
        path.path.kpi.adjusted_net_economic_cost
        - anchor.path.kpi.adjusted_net_economic_cost,
        sum(value > NUMERIC_TOLERANCE for value in differences),
        max(differences),
    )


def _finite_regret(regret: CampaignERegretEvidence) -> bool:
    return isfinite(regret.adjusted_cost_regret) and isfinite(
        regret.maximum_actual_power_difference_kw
    )


def _uniform(environment: str, sample: int, variable: str) -> float:
    digest = hashlib.sha256(
        f"{_SEED}|{environment}|{sample}|{variable}".encode()
    ).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def _triangular(environment: str, sample: int, variable: str, bound: float) -> float:
    u = _uniform(environment, sample, variable)
    return (
        bound * (sqrt(2.0 * u) - 1.0)
        if u <= 0.5
        else bound * (1.0 - sqrt(2.0 * (1.0 - u)))
    )


def _choice(
    environment: str,
    sample: int,
    variable: str,
    values: tuple[int, ...],
    probabilities: tuple[float, ...],
) -> int:
    u = _uniform(environment, sample, variable)
    total = 0.0
    for value, probability in zip(values, probabilities, strict=True):
        total += probability
        if u < total:
            return value
    return values[-1]


def _nearest(values: tuple[float, ...], percentile: float) -> float:
    ordered = tuple(sorted(values))
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _distributions(
    regrets: tuple[CampaignERegretEvidence, ...],
) -> tuple[CampaignEDistributionStatistic, ...]:
    result: list[CampaignEDistributionStatistic] = []
    for environment in _ENVIRONMENTS:
        for strategy in ("Schedule", "Economic"):
            subset = tuple(
                item
                for item in regrets
                if item.path.sample.environment == environment
                and item.path.strategy == strategy
            )
            metrics = (
                (
                    "adjusted_cost_regret_cny",
                    tuple(item.adjusted_cost_regret for item in subset),
                ),
                (
                    "actual_power_divergence_hours",
                    tuple(float(item.actual_power_divergence_hours) for item in subset),
                ),
                (
                    "maximum_actual_power_difference_kw",
                    tuple(item.maximum_actual_power_difference_kw for item in subset),
                ),
                (
                    "physical_revisions",
                    tuple(
                        float(item.path.path.kpi.physical_revision_count)
                        for item in subset
                    ),
                ),
                (
                    "final_actual_soc",
                    tuple(item.path.path.kpi.final_soc_fraction for item in subset),
                ),
            )
            for metric, values in metrics:
                mean = sum(values) / len(values)
                variance = sum((value - mean) ** 2 for value in values) / len(values)
                result.append(
                    CampaignEDistributionStatistic(
                        environment,
                        strategy,
                        metric,
                        len(values),
                        mean,
                        sqrt(variance),
                        min(values),
                        _nearest(values, 0.05),
                        _nearest(values, 0.50),
                        _nearest(values, 0.90),
                        _nearest(values, 0.95),
                        max(values),
                        sum(value > 0 for value in values),
                        sum(value == 0 for value in values),
                        sum(value < 0 for value in values),
                    )
                )
    return tuple(result)


def _csv(rows: Iterable[Iterable[object]]) -> str:
    stream = StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(rows)
    return stream.getvalue()


def _write_outputs(
    directory: Path,
    samples: tuple[CampaignESampleDefinition, ...],
    anchors: tuple[CampaignEAnchorResult, ...],
    paths: tuple[CampaignEPathResult, ...],
    regrets: tuple[CampaignERegretEvidence, ...],
    comparisons: tuple[CampaignEStrategyComparison, ...],
    distributions: tuple[CampaignEDistributionStatistic, ...],
    anchors_reproduced: bool,
    hard_passed: bool,
) -> tuple[Path, ...]:
    """Write deterministic reporting evidence only after all 390 runs succeed."""

    directory.mkdir(parents=True, exist_ok=True)
    source_by_environment = {
        path.sample.environment: path.scenario
        for path in paths
        if path.sample.sample_index == 0
    }
    files: dict[str, str] = {
        "campaign_e_summary.txt": _summary(
            anchors_reproduced, hard_passed, comparisons, distributions
        ),
        "campaign_e_sample_manifest.csv": _sample_manifest_csv(
            samples, source_by_environment
        ),
        "campaign_e_anchor_results.csv": _anchor_results_csv(anchors),
        "campaign_e_path_results.csv": _path_results_csv(paths),
        "campaign_e_regret_evidence.csv": _regret_csv(regrets),
        "campaign_e_strategy_comparisons.csv": _comparison_csv(comparisons),
        "campaign_e_distribution_summary.csv": _distribution_csv(distributions),
        "campaign_e_hourly_trace.csv": _hourly_trace_csv(paths),
        "campaign_e_anchor_hourly_trace.csv": _anchor_hourly_trace_csv(anchors),
        "campaign_e_acceptance_findings.csv": _findings_csv(paths),
    }
    for environment in _ENVIRONMENTS:
        files[f"campaign_e_regret_ecdf_{environment.lower()}.svg"] = _ecdf_svg(
            environment,
            "Adjusted-cost regret ECDF",
            "CNY; sampled path minus same-environment perfect anchor",
            {
                strategy: tuple(
                    item.adjusted_cost_regret
                    for item in regrets
                    if item.path.sample.environment == environment
                    and item.path.strategy == strategy
                )
                for strategy in ("Schedule", "Economic")
            },
        )
        files[f"campaign_e_divergence_ecdf_{environment.lower()}.svg"] = _ecdf_svg(
            environment,
            "Maximum actual executed battery-power difference ECDF",
            "kW; source=Simulator trace actual_power_kw",
            {
                strategy: tuple(
                    item.maximum_actual_power_difference_kw
                    for item in regrets
                    if item.path.sample.environment == environment
                    and item.path.strategy == strategy
                )
                for strategy in ("Schedule", "Economic")
            },
        )
    files["campaign_e_physical_revisions.svg"] = _bar_svg(
        "Physical revision distribution",
        "count; grouped by environment / strategy",
        tuple(
            (
                f"{stat.environment}:{stat.strategy}",
                stat.mean,
            )
            for stat in distributions
            if stat.metric == "physical_revisions"
        ),
    )
    ranking_counts = tuple(
        (
            ranking.value,
            float(sum(item.ranking is ranking for item in comparisons)),
        )
        for ranking in EconomicComparisonRanking
    )
    files["campaign_e_ranking_summary.svg"] = _bar_svg(
        "Sampled strategy ranking summary",
        "comparison count; Economic minus Schedule; 192 synthetic paired samples",
        ranking_counts,
    )
    output_paths: list[Path] = []
    for name, text in files.items():
        path = directory / name
        path.write_text(text, encoding="utf-8", newline="")
        output_paths.append(path)
    return tuple(output_paths)


def _sample_manifest_csv(
    samples: tuple[CampaignESampleDefinition, ...],
    source_by_environment: dict[str, ResidentialCampaignCScenario],
) -> str:
    header = (
        "seed",
        "environment",
        "sample_index",
        "source_scenario_id",
        "realized_pv_fingerprint",
        "realized_load_fingerprint",
        "realized_tariff_fingerprint",
        "forecast_pv_fingerprint",
        "forecast_load_fingerprint",
        "forecast_tariff_fingerprint",
        "forecast_combined_fingerprint",
        "pv_amplitude_error",
        "load_amplitude_error",
        "tariff_amplitude_error",
        "pv_shift_hours",
        "load_shift_hours",
        "tariff_shift_hours",
    )
    rows: list[tuple[object, ...]] = [header]
    for sample in samples:
        source = source_by_environment[sample.environment]
        scenario = _sampled_scenario(source, sample)
        forecast_pv_fingerprint = _profile_fingerprint(scenario.forecast_pv_profile_kw)
        forecast_load_fingerprint = _profile_fingerprint(
            scenario.forecast_load_profile_kw
        )
        forecast_tariff_fingerprint = _profile_fingerprint(
            scenario.forecast_tariff_profile_cny_per_kwh
        )
        rows.append(
            (
                sample.seed,
                sample.environment,
                sample.sample_index,
                scenario.realized_source_scenario_id,
                _profile_fingerprint(scenario.realized_pv_profile_kw),
                _profile_fingerprint(scenario.realized_load_profile_kw),
                _profile_fingerprint(scenario.realized_tariff_profile_cny_per_kwh),
                forecast_pv_fingerprint,
                forecast_load_fingerprint,
                forecast_tariff_fingerprint,
                _combined_forecast_fingerprint(
                    forecast_pv_fingerprint,
                    forecast_load_fingerprint,
                    forecast_tariff_fingerprint,
                ),
                _decimal(sample.pv_amplitude_error),
                _decimal(sample.load_amplitude_error),
                _decimal(sample.tariff_amplitude_error),
                sample.pv_shift_hours,
                sample.load_shift_hours,
                sample.tariff_shift_hours,
            )
        )
    return _csv(rows)


def _anchor_results_csv(anchors: tuple[CampaignEAnchorResult, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "environment",
            "strategy",
            "scenario_id",
            "adjusted_net_economic_cost",
            "grid_import_energy_kwh",
            "grid_export_energy_kwh",
            "battery_throughput_kwh",
            "final_actual_soc",
            "frozen_campaign_a_fingerprint_reproduced",
        )
    ]
    for anchor in anchors:
        kpi = anchor.path.kpi
        rows.append(
            (
                anchor.environment,
                anchor.strategy,
                anchor.path.scenario.scenario_id,
                _decimal(kpi.adjusted_net_economic_cost),
                _decimal(kpi.grid_import_energy_kwh),
                _decimal(kpi.grid_export_energy_kwh),
                _decimal(kpi.battery_throughput_kwh),
                _decimal(kpi.final_soc_fraction),
                str(_matches_perfect_anchor_fingerprint(anchor.path)).lower(),
            )
        )
    return _csv(rows)


def _path_results_csv(paths: tuple[CampaignEPathResult, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "environment",
            "sample_index",
            "strategy",
            "scenario_id",
            "adjusted_net_economic_cost",
            "physical_revisions",
            "final_actual_soc",
            "acceptance_passed",
            "ledger_reconciled",
            "comparison_reconciled",
        )
    ]
    for item in paths:
        kpi = item.path.kpi
        rows.append(
            (
                item.sample.environment,
                item.sample.sample_index,
                item.strategy,
                item.scenario.scenario_id,
                _decimal(kpi.adjusted_net_economic_cost),
                kpi.physical_revision_count,
                _decimal(kpi.final_soc_fraction),
                str(item.path.acceptance.passed).lower(),
                str(kpi.ledger_reconciled).lower(),
                str(kpi.comparison_reconciled).lower(),
            )
        )
    return _csv(rows)


def _regret_csv(regrets: tuple[CampaignERegretEvidence, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "environment",
            "sample_index",
            "strategy",
            "anchor_scenario_id",
            "adjusted_cost_regret_cny",
            "actual_power_divergence_hours",
            "maximum_actual_power_difference_kw",
            "actual_power_source",
        )
    ]
    rows.extend(
        (
            item.path.sample.environment,
            item.path.sample.sample_index,
            item.path.strategy,
            item.anchor.path.scenario.scenario_id,
            _decimal(item.adjusted_cost_regret),
            item.actual_power_divergence_hours,
            _decimal(item.maximum_actual_power_difference_kw),
            "simulation_trace.state.battery_result.actual_power_kw",
        )
        for item in regrets
    )
    return _csv(rows)


def _comparison_csv(comparisons: tuple[CampaignEStrategyComparison, ...]) -> str:
    return _csv(
        [
            (
                "environment",
                "sample_index",
                "ranking",
                "economic_minus_schedule_adjusted_cost_cny",
            ),
            *(
                (
                    item.sample.environment,
                    item.sample.sample_index,
                    item.ranking.value,
                    _decimal(item.adjusted_cost_delta),
                )
                for item in comparisons
            ),
        ]
    )


def _distribution_csv(distributions: tuple[CampaignEDistributionStatistic, ...]) -> str:
    header = (
        "environment",
        "strategy",
        "metric",
        "count",
        "mean",
        "population_standard_deviation",
        "minimum",
        "p05_nearest_rank",
        "p50_nearest_rank",
        "p90_nearest_rank",
        "p95_nearest_rank",
        "maximum",
        "positive_count",
        "zero_count",
        "negative_count",
    )
    rows: list[tuple[object, ...]] = [header]
    for item in distributions:
        rows.append(
            (
                item.environment,
                item.strategy,
                item.metric,
                item.count,
                *(
                    _decimal(value)
                    for value in (
                        item.mean,
                        item.population_standard_deviation,
                        item.minimum,
                        item.p05,
                        item.p50,
                        item.p90,
                        item.p95,
                        item.maximum,
                    )
                ),
                item.positive_count,
                item.zero_count,
                item.negative_count,
            )
        )
    return _csv(rows)


def _hourly_trace_csv(paths: tuple[CampaignEPathResult, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "environment",
            "sample_index",
            "strategy",
            "execution_scope",
            "hour_index",
            "actual_battery_power_kw",
            "power_source",
        )
    ]
    for path in paths:
        for hour, actual_power in enumerate(path.actual_powers_kw):
            rows.append(
                (
                    path.sample.environment,
                    path.sample.sample_index,
                    path.strategy,
                    "sampled",
                    hour,
                    _decimal(actual_power),
                    "simulation_trace.state.battery_result.actual_power_kw",
                )
            )
    return _csv(rows)


def _anchor_hourly_trace_csv(anchors: tuple[CampaignEAnchorResult, ...]) -> str:
    """Write hourly facts from retained anchor traces without rerunning them."""

    rows: list[tuple[object, ...]] = [
        (
            "environment",
            "strategy",
            "execution_scope",
            "hour_index",
            "timestamp",
            "realized_pv_power_kw",
            "realized_load_power_kw",
            "realized_import_tariff_cny_per_kwh",
            "actual_battery_power_kw",
            "actual_soc_fraction",
            "actual_grid_power_kw",
            "anchor_scenario_id",
            "frozen_campaign_a_fingerprint_reproduced",
        )
    ]
    for anchor in anchors:
        for hour, trace in enumerate(_daily_step_traces(anchor.path)):
            state = trace.simulation_trace.state
            rows.append(
                (
                    anchor.environment,
                    anchor.strategy,
                    "perfect_anchor",
                    hour,
                    trace.context.source_context.timestamp.isoformat(),
                    _decimal(state.pv_result.actual_power_kw),
                    _decimal(state.load_result.actual_power_kw),
                    _decimal(state.tariff_result.import_price_cny_per_kwh),
                    _decimal(state.battery_result.actual_power_kw),
                    _decimal(state.battery_result.next_state.soc),
                    _decimal(state.grid_result.actual_grid_power_kw),
                    anchor.path.scenario.scenario_id,
                    str(_matches_perfect_anchor_fingerprint(anchor.path)).lower(),
                )
            )
    return _csv(rows)


def _daily_step_traces(
    path: ResidentialCampaignCPathResult,
) -> tuple[
    MultiOpportunityExplainableMPCDailySimulationStepTrace
    | EconomicMultiOpportunityExplainableMPCDailySimulationStepTrace,
    ...,
]:
    """Expose typed retained daily traces without creating an execution path."""

    trajectory = path.trajectory
    if isinstance(
        trajectory, EconomicMultiOpportunityExplainableMPCDailySimulationResult
    ):
        return trajectory.step_traces
    return trajectory.step_traces


def _findings_csv(paths: tuple[CampaignEPathResult, ...]) -> str:
    rows: list[tuple[object, ...]] = [
        (
            "environment",
            "sample_index",
            "strategy",
            "criterion",
            "severity",
            "status",
            "message",
        )
    ]
    for item in paths:
        rows.extend(
            (
                item.sample.environment,
                item.sample.sample_index,
                item.strategy,
                finding.criterion_id,
                finding.severity.value,
                finding.status.value,
                finding.message,
            )
            for finding in item.path.acceptance.findings
        )
    return _csv(rows)


def _summary(
    anchors_reproduced: bool,
    hard_passed: bool,
    comparisons: tuple[CampaignEStrategyComparison, ...],
    distributions: tuple[CampaignEDistributionStatistic, ...],
) -> str:
    ranking_counts = {
        ranking.value: sum(item.ranking is ranking for item in comparisons)
        for ranking in EconomicComparisonRanking
    }
    return "\n".join(
        (
            "Campaign E: seeded synthetic probabilistic forecast robustness "
            "characterization",
            f"seed={_SEED}",
            "matrix=3 environments x 64 synthetic samples = 192 scenarios",
            "executions=384 fresh sampled Schedule/Economic paths + 6 fresh "
            "perfect anchors = 390",
            "comparisons=192 paired sampled strategy comparisons; "
            "regrets=384 sample-to-anchor comparisons",
            f"frozen_campaign_a_anchor_fingerprints_reproduced={str(anchors_reproduced).lower()}",
            f"hard_status={'PASS' if hard_passed else 'FAIL'}",
            f"ranking_counts={ranking_counts}",
            f"distribution_rows={len(distributions)}; percentiles=nearest_rank; "
            "standard_deviation=population",
            "output_files=18; sampled_hourly_trace_rows=9216; "
            "anchor_hourly_trace_rows=144",
            "interpretation=synthetic fixed-seed descriptive evidence, not field "
            "probability or production reliability certification",
            "actual_power_source=simulation_trace.state.battery_result.actual_power_kw",
            "",
        )
    )


def _decimal(value: float) -> str:
    return f"{value:.6f}"


def _profile_fingerprint(values: tuple[float, ...]) -> str:
    payload = ",".join(_normalized_fingerprint_value(value) for value in values).encode(
        "utf-8"
    )
    return hashlib.sha256(payload).hexdigest()


def _normalized_fingerprint_value(value: float) -> str:
    """Serialize one finite evidence value at the reporting precision only."""

    if not isfinite(value):
        raise ValueError("fingerprint values must be finite")
    normalized = 0.0 if round(value, 6) == 0.0 else value
    return f"{normalized:.6f}"


def _combined_forecast_fingerprint(
    pv_fingerprint: str, load_fingerprint: str, tariff_fingerprint: str
) -> str:
    """Hash labelled profile fingerprints so component boundaries stay unambiguous."""

    payload = (
        f"pv:{pv_fingerprint}|load:{load_fingerprint}|tariff:{tariff_fingerprint}"
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _xml(value: object) -> str:
    return escape(str(value), {'"': "&quot;"})


def _ecdf_svg(
    environment: str,
    title: str,
    unit: str,
    series: dict[str, tuple[float, ...]],
) -> str:
    width, height = 1024, 440
    left, right, top, bottom = 92.0, 976.0, 82.0, 370.0
    values = tuple(value for item in series.values() for value in item)
    low = min(0.0, min(values))
    high = max(0.0, max(values))
    if high == low:
        high = low + 1.0

    def scale_x(value: float) -> float:
        return left + (value - low) * (right - left) / (high - low)

    def scale_y(value: float) -> float:
        return bottom - value * (bottom - top)

    colors = {"Schedule": "#2563eb", "Economic": "#b45309"}
    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        f'<text x="36" y="30">{_xml(title)}</text>',
        f'<text x="36" y="52">environment={_xml(environment)}; seed={_SEED}; '
        f"{_xml(unit)}</text>",
        f'<line x1="{left:.2f}" y1="{bottom:.2f}" x2="{right:.2f}" '
        f'y2="{bottom:.2f}" stroke="#475569"/>',
        f'<line id="zero-axis" x1="{scale_x(0.0):.2f}" y1="{top:.2f}" '
        f'x2="{scale_x(0.0):.2f}" y2="{bottom:.2f}" stroke="#64748b"/>',
        f'<text x="{left:.2f}" y="398">min={low:.6f}</text>',
        f'<text x="{right - 130:.2f}" y="398">max={high:.6f}</text>',
    ]
    for row, (strategy, raw_values) in enumerate(series.items()):
        ordered = tuple(sorted(raw_values))
        points = " ".join(
            f"{scale_x(value):.2f},{scale_y((index + 1) / len(ordered)):.2f}"
            for index, value in enumerate(ordered)
        )
        pieces.extend(
            (
                f'<polyline data-strategy="{_xml(strategy)}" '
                f'data-count="{len(ordered)}" points="{points}" fill="none" '
                f'stroke="{colors[strategy]}" stroke-width="2"/>',
                f'<text x="{left + row * 180:.2f}" y="{top - 16:.2f}" '
                f'fill="{colors[strategy]}">{_xml(strategy)} n={len(ordered)}</text>',
            )
        )
    pieces.append("</svg>\n")
    return "".join(pieces)


def _bar_svg(title: str, unit: str, values: tuple[tuple[str, float], ...]) -> str:
    width, height = 1024, 440
    left, right, top, bottom = 62.0, 996.0, 82.0, 330.0
    minimum = min(0.0, *(value for _, value in values))
    maximum = max(0.0, *(value for _, value in values))
    if maximum == minimum:
        maximum = minimum + 1.0

    def y_for(value: float) -> float:
        return bottom - (value - minimum) * (bottom - top) / (maximum - minimum)

    zero_y = y_for(0.0)
    bar_width = (right - left) / len(values) * 0.68
    pieces = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}">',
        f'<text x="36" y="30">{_xml(title)}</text>',
        f'<text x="36" y="52">seed={_SEED}; {_xml(unit)}</text>',
        f'<line id="zero-axis" x1="{left:.2f}" y1="{zero_y:.2f}" '
        f'x2="{right:.2f}" y2="{zero_y:.2f}" stroke="#475569"/>',
    ]
    for index, (label, value) in enumerate(values):
        center = left + (index + 0.5) * (right - left) / len(values)
        value_y = y_for(value)
        height_value = abs(value_y - zero_y)
        pieces.extend(
            (
                f'<rect data-label="{_xml(label)}" x="{center - bar_width / 2:.2f}" '
                f'y="{min(value_y, zero_y):.2f}" width="{bar_width:.2f}" '
                f'height="{height_value:.2f}" fill="#2563eb"/>',
                f'<text x="{center - bar_width / 2:.2f}" y="{bottom + 22:.2f}" '
                f'font-size="10">{_xml(label)}</text>',
                f'<text x="{center - bar_width / 2:.2f}" '
                f'y="{min(value_y, zero_y) - 5:.2f}" font-size="10">'
                f"{value:.3f}</text>",
            )
        )
    pieces.append("</svg>\n")
    return "".join(pieces)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="EOS Residential EMS Campaign E")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("simulation_output_campaign_e")
    )
    arguments = parser.parse_args(argv)
    result = run_residential_campaign_e(arguments.output_dir)
    print("PASS" if result.hard_passed else "FAIL")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
