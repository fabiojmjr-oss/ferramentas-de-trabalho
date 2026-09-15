"""What each point of service level costs in working capital, and what it actually buys.

The module is organised around three confusions that make inventory sizing wrong more often
than the arithmetic does:

1. **Quoted lead time instead of realised lead time.** Using the contract sets lead-time
   variability to zero, and that term usually dominates safety stock. :func:`fit_lead_time` and
   :func:`decompose_safety_stock` measure what the substitution costs.
2. **Cycle service level quoted as fill rate.** They are different quantities with different
   formulas, and the conversion between them needs the order quantity.
   :func:`z_for_cycle_service` and :func:`z_for_fill_rate` are deliberately separate.
3. **A promised service level reported as an achieved one.** The formula is a normal
   approximation; :func:`simulate_policy` runs the policy on resampled demand and resampled
   lead times and reports what it delivered.
4. **Demand variability used where forecast error belongs.** If replenishment is driven by a
   forecast, the quantity to buffer is the error of that forecast, not the variability of the
   demand. :func:`safety_stock_from_forecast_error` and :func:`compare_sizing_bases` measure the
   difference, which runs in both directions depending on whether the forecast is worth having.

Nothing here needs a solver or a statistics package: the three normal functions used are in
:mod:`oplab.inventory.normal` and are tested against published values.
"""

from .curve import DEFAULT_TARGETS, achieved_curve, service_curve
from .normal import (
    empirical_quantile,
    norm_cdf,
    norm_pdf,
    norm_ppf,
    unit_normal_loss,
    unit_normal_loss_inverse,
)
from .profile import (
    DemandProfile,
    LeadTimeProfile,
    fit_demand,
    fit_lead_time,
    lead_time_by_supplier,
)
from .safety import (
    BASES,
    SafetyStock,
    compare_sizing_bases,
    decompose_safety_stock,
    economic_order_quantity,
    expected_fill_rate,
    reorder_point,
    safety_stock,
    safety_stock_from_forecast_error,
    z_for_cycle_service,
    z_for_fill_rate,
)
from .simulate import (
    ContinuousReview,
    PeriodicReview,
    Policy,
    SimulationResult,
    simulate_policy,
)

__all__ = [
    "BASES",
    "DEFAULT_TARGETS",
    "ContinuousReview",
    "DemandProfile",
    "LeadTimeProfile",
    "PeriodicReview",
    "Policy",
    "SafetyStock",
    "SimulationResult",
    "achieved_curve",
    "compare_sizing_bases",
    "decompose_safety_stock",
    "economic_order_quantity",
    "empirical_quantile",
    "expected_fill_rate",
    "fit_demand",
    "fit_lead_time",
    "lead_time_by_supplier",
    "norm_cdf",
    "norm_pdf",
    "norm_ppf",
    "reorder_point",
    "safety_stock",
    "safety_stock_from_forecast_error",
    "service_curve",
    "simulate_policy",
    "unit_normal_loss",
    "unit_normal_loss_inverse",
    "z_for_cycle_service",
    "z_for_fill_rate",
]
