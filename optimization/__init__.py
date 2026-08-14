"""Public solver-independent EOS optimization contracts."""

from optimization.battery_horizon_constraint import (
    BatteryHorizonConstraintAggregateBoundary,
    BatteryHorizonConstraintEvaluation,
    BatteryHorizonConstraintInput,
    DeterministicBatteryHorizonConstraintAggregator,
)
from optimization.battery_planning import (
    BatteryOptimizationInput,
    BatteryOptimizationModel,
    BatteryOptimizationState,
)
from optimization.battery_power_constraint import (
    BatteryPowerConstraintViolation,
    BatteryPowerConstraintViolationKind,
    BatteryPowerHorizonConstraintBoundary,
    BatteryPowerHorizonConstraintEvaluation,
    BatteryPowerHorizonConstraintInput,
    DeterministicBatteryPowerHorizonConstraintEvaluator,
)
from optimization.battery_soc_constraint import (
    BatterySOCConstraintViolation,
    BatterySOCConstraintViolationKind,
    BatterySOCHorizonConstraintBoundary,
    BatterySOCHorizonConstraintEvaluation,
    BatterySOCHorizonConstraintInput,
    DeterministicBatterySOCHorizonConstraintEvaluator,
)
from optimization.battery_soc_projection import (
    BatterySOCHorizonProjection,
    BatterySOCHorizonProjectionBoundary,
    BatterySOCHorizonProjectionInput,
    BatterySOCProjectionStep,
    DeterministicBatterySOCHorizonProjector,
)
from optimization.boundary import OptimizationBoundary
from optimization.control_plan import OptimizationControlPlan, OptimizationControlStep
from optimization.control_plan_construction import (
    OptimizationControlPlanConstructionBoundary,
    OptimizationControlPlanConstructionInput,
)
from optimization.grid_charge_reservation import (
    DeterministicHeadroomAwareGridChargeReservationCalculator,
    HeadroomAwareGridChargeReservation,
    HeadroomAwareGridChargeReservationBoundary,
    HeadroomAwareGridChargeReservationInput,
)
from optimization.headroom_aware_candidate_planning import (
    DeterministicHeadroomAwareCandidatePlanner,
    HeadroomAwareCandidatePlanningBoundary,
    HeadroomAwareCandidatePlanningInput,
    HeadroomAwareCandidatePlanningResult,
)
from optimization.headroom_aware_physical_optimization import (
    DeterministicHeadroomAwarePhysicalOptimizer,
    HeadroomAwarePhysicalOptimizationBoundary,
    HeadroomAwarePhysicalOptimizationSolveOutput,
)
from optimization.model import (
    OptimizationObjective,
    OptimizationObjectiveCollection,
    OptimizationOutcome,
    OptimizationProblem,
    OptimizationResult,
    OptimizationSense,
)
from optimization.net_load_aware_baseline import (
    NetLoadAwareBaselineOptimizationConfiguration,
    NetLoadAwareBaselineOptimizer,
)
from optimization.physically_aware_baseline import (
    BatterySolutionRevision,
    BatterySolutionRevisionReason,
    BatterySolutionRevisionStep,
    DeterministicExplicitCandidatePhysicalReviser,
    ExplicitCandidatePhysicalRevisionBoundary,
    ExplicitCandidatePhysicalRevisionInput,
    PhysicallyAwareBaselineOptimizationInput,
    PhysicallyAwareBaselineOptimizer,
    PhysicallyAwareOptimizationBoundary,
    PhysicallyAwareOptimizationSolveOutput,
    PhysicallyAwarePriceBaselineOptimizer,
)
from optimization.price_aware_baseline import (
    PriceAwareBaselineOptimizationConfiguration,
    PriceAwareBaselineOptimizer,
)
from optimization.pv_headroom import (
    DeterministicPVHeadroomRequirementCalculator,
    PVHeadroomForecastStep,
    PVHeadroomRequirement,
    PVHeadroomRequirementBoundary,
    PVHeadroomRequirementInput,
)
from optimization.pv_opportunity_window import (
    DeterministicPVOpportunityWindowSelector,
    PVOpportunityWindow,
    PVOpportunityWindowConfiguration,
    PVOpportunityWindowSelectionBoundary,
    PVOpportunityWindowSelectionInput,
    PVOpportunityWindowStep,
)
from optimization.rolling_headroom_aware_physical_optimization import (
    DeterministicRollingHeadroomAwarePhysicalOptimizer,
    RollingHeadroomAwarePhysicalOptimizationBoundary,
    RollingHeadroomAwarePhysicalOptimizationSolveOutput,
)
from optimization.rolling_pv_headroom import (
    DeterministicRollingPVHeadroomRequirementCalculator,
    RollingPVHeadroomRequirement,
    RollingPVHeadroomRequirementBoundary,
    RollingPVHeadroomRequirementInput,
)
from optimization.solution import OptimizationSolution, OptimizationSolutionStep
from optimization.solution_boundary import (
    OptimizationSolutionBoundary,
    OptimizationSolveOutput,
)
from optimization.solution_control_plan import (
    OptimizationSolutionControlPlanBuilder,
    OptimizationSolutionControlPlanConstructionBoundary,
    OptimizationSolutionControlPlanConstructionInput,
)

__all__ = [
    "BatteryHorizonConstraintAggregateBoundary",
    "BatteryHorizonConstraintEvaluation",
    "BatteryHorizonConstraintInput",
    "BatteryOptimizationInput",
    "BatteryOptimizationModel",
    "BatteryOptimizationState",
    "BatteryPowerConstraintViolation",
    "BatteryPowerConstraintViolationKind",
    "BatteryPowerHorizonConstraintBoundary",
    "BatteryPowerHorizonConstraintEvaluation",
    "BatteryPowerHorizonConstraintInput",
    "BatterySOCConstraintViolation",
    "BatterySOCConstraintViolationKind",
    "BatterySOCHorizonConstraintBoundary",
    "BatterySOCHorizonConstraintEvaluation",
    "BatterySOCHorizonConstraintInput",
    "BatterySOCHorizonProjection",
    "BatterySOCHorizonProjectionBoundary",
    "BatterySOCHorizonProjectionInput",
    "BatterySOCProjectionStep",
    "BatterySolutionRevision",
    "BatterySolutionRevisionReason",
    "BatterySolutionRevisionStep",
    "DeterministicBatteryHorizonConstraintAggregator",
    "DeterministicBatteryPowerHorizonConstraintEvaluator",
    "DeterministicBatterySOCHorizonConstraintEvaluator",
    "DeterministicBatterySOCHorizonProjector",
    "DeterministicExplicitCandidatePhysicalReviser",
    "DeterministicHeadroomAwareCandidatePlanner",
    "DeterministicHeadroomAwareGridChargeReservationCalculator",
    "DeterministicHeadroomAwarePhysicalOptimizer",
    "DeterministicPVHeadroomRequirementCalculator",
    "DeterministicPVOpportunityWindowSelector",
    "DeterministicRollingHeadroomAwarePhysicalOptimizer",
    "DeterministicRollingPVHeadroomRequirementCalculator",
    "ExplicitCandidatePhysicalRevisionBoundary",
    "ExplicitCandidatePhysicalRevisionInput",
    "HeadroomAwareCandidatePlanningBoundary",
    "HeadroomAwareCandidatePlanningInput",
    "HeadroomAwareCandidatePlanningResult",
    "HeadroomAwareGridChargeReservation",
    "HeadroomAwareGridChargeReservationBoundary",
    "HeadroomAwareGridChargeReservationInput",
    "HeadroomAwarePhysicalOptimizationBoundary",
    "HeadroomAwarePhysicalOptimizationSolveOutput",
    "NetLoadAwareBaselineOptimizationConfiguration",
    "NetLoadAwareBaselineOptimizer",
    "OptimizationBoundary",
    "OptimizationControlPlan",
    "OptimizationControlPlanConstructionBoundary",
    "OptimizationControlPlanConstructionInput",
    "OptimizationControlStep",
    "OptimizationObjective",
    "OptimizationObjectiveCollection",
    "OptimizationOutcome",
    "OptimizationProblem",
    "OptimizationResult",
    "OptimizationSense",
    "OptimizationSolution",
    "OptimizationSolutionBoundary",
    "OptimizationSolutionControlPlanBuilder",
    "OptimizationSolutionControlPlanConstructionBoundary",
    "OptimizationSolutionControlPlanConstructionInput",
    "OptimizationSolutionStep",
    "OptimizationSolveOutput",
    "PVHeadroomForecastStep",
    "PVHeadroomRequirement",
    "PVHeadroomRequirementBoundary",
    "PVHeadroomRequirementInput",
    "PVOpportunityWindow",
    "PVOpportunityWindowConfiguration",
    "PVOpportunityWindowSelectionBoundary",
    "PVOpportunityWindowSelectionInput",
    "PVOpportunityWindowStep",
    "PhysicallyAwareBaselineOptimizationInput",
    "PhysicallyAwareBaselineOptimizer",
    "PhysicallyAwareOptimizationBoundary",
    "PhysicallyAwareOptimizationSolveOutput",
    "PhysicallyAwarePriceBaselineOptimizer",
    "PriceAwareBaselineOptimizationConfiguration",
    "PriceAwareBaselineOptimizer",
    "RollingHeadroomAwarePhysicalOptimizationBoundary",
    "RollingHeadroomAwarePhysicalOptimizationSolveOutput",
    "RollingPVHeadroomRequirement",
    "RollingPVHeadroomRequirementBoundary",
    "RollingPVHeadroomRequirementInput",
]
