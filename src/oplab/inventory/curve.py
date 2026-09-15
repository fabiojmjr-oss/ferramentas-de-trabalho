"""The service-versus-working-capital curve, and what it costs to promise the last point.

This is the chart the conversation should start from. A service level is not a target handed
down and met; it is a purchase, and the price per point rises as the target rises because the
normal tail thins. Quoting a single service target without its price is what makes the
discussion about whether the operation is trying hard enough rather than about what the
commitment is worth.

The curve here is built two ways on purpose - from the formula and from the simulation - because
the gap between them is the finding. The formula's promise is the price a plan is built on; the
simulation's achievement is what the customer sees.
"""

from __future__ import annotations

import pandas as pd

from .._pandas import as_float
from .profile import DemandProfile, LeadTimeProfile
from .safety import (
    expected_fill_rate,
    reorder_point,
    safety_stock,
    z_for_cycle_service,
)
from .simulate import ContinuousReview, simulate_policy

DEFAULT_TARGETS: tuple[float, ...] = (0.80, 0.90, 0.95, 0.98, 0.99, 0.995)


def service_curve(
    demand: DemandProfile,
    lead_time: LeadTimeProfile,
    order_quantity: float,
    unit_cost: float,
    targets: tuple[float, ...] = DEFAULT_TARGETS,
    review_period: float = 0.0,
) -> pd.DataFrame:
    """Price each cycle-service target in safety stock and in working capital.

    Args:
        demand: Demand per period.
        lead_time: Realised replenishment lead time.
        order_quantity: Units per replenishment order, needed for the implied fill rate.
        unit_cost: Cost of one unit, to express the safety stock as working capital.
        targets: Cycle service levels to price.
        review_period: Periods between review opportunities.

    Returns:
        One row per target with the safety factor, safety stock in units and in currency, the
        reorder point, the fill rate the same policy implies, and the marginal cost of the point
        of service gained over the previous row.

    Raises:
        ValueError: If ``unit_cost`` or ``order_quantity`` is not positive, or fewer than two
            targets are given - a curve of one point is a number, and quoting it as a curve is
            the practice this function exists to replace.
    """
    if unit_cost <= 0.0:
        raise ValueError("unit_cost must be positive")
    if order_quantity <= 0.0:
        raise ValueError("order_quantity must be positive")
    if len(targets) < 2:
        raise ValueError("at least two targets are required to draw a curve")

    rows = []
    for target in sorted(targets):
        z = z_for_cycle_service(target)
        sized = safety_stock(demand, lead_time, z, "combined", review_period)
        rows.append(
            {
                "cycle_service_target": target,
                "z": z,
                "safety_units": sized.units,
                "safety_capital": sized.units * unit_cost,
                "reorder_point": reorder_point(demand, lead_time, sized),
                "implied_fill_rate": expected_fill_rate(z, sized.sigma, order_quantity),
            }
        )

    curve = pd.DataFrame(rows)
    capital = curve["safety_capital"]
    points = curve["cycle_service_target"] * 100.0
    curve["capital_per_point"] = capital.diff() / points.diff()
    return curve


def achieved_curve(
    demand: DemandProfile,
    lead_time: LeadTimeProfile,
    order_quantity: float,
    unit_cost: float,
    demand_sample: pd.Series,
    targets: tuple[float, ...] = DEFAULT_TARGETS,
    periods: int = 365,
    replications: int = 20,
    seed: int = 7,
) -> pd.DataFrame:
    """Price each target and then simulate what it actually delivers.

    Args:
        demand: Demand per period.
        lead_time: Realised replenishment lead time.
        order_quantity: Units per replenishment order.
        unit_cost: Cost of one unit.
        demand_sample: Observed demand per period, resampled by the simulation.
        targets: Cycle service levels to price.
        periods: Length of each replication.
        replications: Replications per target.
        seed: Seed for the resampling.

    Returns:
        The columns of :func:`service_curve` plus ``achieved_fill_rate``,
        ``achieved_cycle_service`` and ``mean_on_hand``, so the promise and the outcome sit side
        by side.
    """
    curve = service_curve(demand, lead_time, order_quantity, unit_cost, targets)
    achieved_fill, achieved_cycle, on_hand = [], [], []
    for row in curve.itertuples():
        policy = ContinuousReview(
            reorder_point=as_float(row.reorder_point), order_quantity=order_quantity
        )
        result = simulate_policy(
            policy,
            demand_sample.to_numpy(dtype=float),
            lead_time.sample,
            periods=periods,
            replications=replications,
            seed=seed,
        )
        means = result.summary()
        achieved_fill.append(float(means["fill_rate"]))
        achieved_cycle.append(float(means["cycle_service"]))
        on_hand.append(float(means["mean_on_hand"]))

    curve["achieved_fill_rate"] = achieved_fill
    curve["achieved_cycle_service"] = achieved_cycle
    curve["mean_on_hand"] = on_hand
    return curve
