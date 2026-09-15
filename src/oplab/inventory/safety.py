"""Safety stock, and the two questions it is sized against.

There are two service targets in common use and they are not the same quantity:

* **Cycle service level** is the probability of not running out during a replenishment cycle.
  It is what ``NORM.S.INV(0.95)`` answers, and it counts cycles, not units.
* **Fill rate** is the share of demand met from stock. It counts units.

A policy set to a 95% cycle service level will usually deliver a fill rate well above 95%,
because a stockout near the end of a cycle is short and affects little demand. Quoting one as
the other is not a rounding difference - it systematically misprices the inventory needed for a
contractual service commitment, and the direction of the error depends on the order quantity,
which is why it cannot be corrected with a fudge factor.

The second point this module is built around is the decomposition. The combined formula

    ss = z * sqrt((L + R) * sd_d^2 + mu_d^2 * sd_L^2)

has two variance terms, and in logistics the second one usually dominates - so the lever on
inventory is the *reliability* of replenishment rather than the accuracy of the forecast or the
length of the lead time. Setting ``sd_L`` to zero, which is what using a quoted lead time does,
removes that term entirely and understates safety stock by whatever share it held.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .normal import norm_ppf, unit_normal_loss, unit_normal_loss_inverse
from .profile import DemandProfile, LeadTimeProfile

BASES = ("demand", "lead_time", "combined")


@dataclass(frozen=True)
class SafetyStock:
    """A sized safety stock and the terms it came from.

    Attributes:
        units: Safety stock in units.
        z: Safety factor used.
        sigma: Standard deviation of demand over the protection interval, in units.
        demand_variance: The ``(L + R) * sd_d^2`` term.
        lead_time_variance: The ``mu_d^2 * sd_L^2`` term.
        protection_periods: ``L + R``, the interval the stock has to cover.
    """

    units: float
    z: float
    sigma: float
    demand_variance: float
    lead_time_variance: float
    protection_periods: float

    @property
    def lead_time_share(self) -> float:
        """Share of the variance contributed by lead-time variability."""
        total = self.demand_variance + self.lead_time_variance
        return self.lead_time_variance / total if total > 0 else float("nan")


def z_for_cycle_service(level: float) -> float:
    """Safety factor for a cycle-service target.

    Args:
        level: Probability of not stocking out in a cycle, strictly between 0 and 1.

    Returns:
        The safety factor.

    Raises:
        ValueError: If ``level`` is not strictly between 0 and 1.
    """
    return norm_ppf(level)


def z_for_fill_rate(level: float, sigma: float, order_quantity: float) -> float:
    """Safety factor for a fill-rate target, which needs the order quantity.

    The expected shortfall per cycle is ``sigma * G(z)`` and the demand per cycle is the order
    quantity, so a fill-rate target of ``f`` requires ``G(z) = Q * (1 - f) / sigma``. The order
    quantity is an input rather than an afterthought: a larger order covers the shortfall over
    more units, so the same safety stock buys a higher fill rate. This is precisely the
    dependency the cycle-service formula does not have, and the reason the two targets cannot
    be converted into one another without it.

    Args:
        level: Share of demand to be met from stock, strictly between 0 and 1.
        sigma: Standard deviation of demand over the protection interval, in units.
        order_quantity: Units per replenishment order.

    Returns:
        The safety factor.

    Raises:
        ValueError: If ``level`` is outside ``(0, 1)``, or ``sigma`` or ``order_quantity`` is
            not positive.
    """
    if not 0.0 < level < 1.0:
        raise ValueError("level must be strictly between 0 and 1")
    if sigma <= 0.0:
        raise ValueError("sigma must be positive")
    if order_quantity <= 0.0:
        raise ValueError("order_quantity must be positive")
    return unit_normal_loss_inverse(order_quantity * (1.0 - level) / sigma)


def expected_fill_rate(z: float, sigma: float, order_quantity: float) -> float:
    """Fill rate implied by a safety factor, the inverse of :func:`z_for_fill_rate`.

    Args:
        z: Safety factor.
        sigma: Standard deviation of demand over the protection interval, in units.
        order_quantity: Units per replenishment order.

    Returns:
        The implied fill rate, which can exceed the cycle service level of the same ``z``.

    Raises:
        ValueError: If ``sigma`` or ``order_quantity`` is not positive.
    """
    if sigma <= 0.0:
        raise ValueError("sigma must be positive")
    if order_quantity <= 0.0:
        raise ValueError("order_quantity must be positive")
    return 1.0 - sigma * unit_normal_loss(z) / order_quantity


def safety_stock(
    demand: DemandProfile,
    lead_time: LeadTimeProfile,
    z: float,
    basis: str = "combined",
    review_period: float = 0.0,
    use_quoted_lead_time: bool = False,
) -> SafetyStock:
    """Size safety stock from a demand and a lead-time profile.

    Args:
        demand: Demand per period.
        lead_time: Realised replenishment lead time.
        z: Safety factor, from :func:`z_for_cycle_service` or :func:`z_for_fill_rate`.
        basis: ``"combined"`` for both variance terms, ``"demand"`` to ignore lead-time
            variability, ``"lead_time"`` to ignore demand variability. The two partial bases
            exist to be compared against the combined one, not to be used.
        review_period: Periods between review opportunities, added to the protection interval.
            A periodic review policy is exposed for the review period as well as the lead time,
            and omitting it is a common understatement.
        use_quoted_lead_time: Use the supplier's quoted lead time with zero variability, which
            is what a calculation built on the contract rather than the receipts does. Provided
            so the error can be measured rather than described.

    Returns:
        A :class:`SafetyStock`.

    Raises:
        ValueError: If ``basis`` is unknown or ``review_period`` is negative.
    """
    if basis not in BASES:
        raise ValueError(f"basis must be one of {BASES}")
    if review_period < 0.0:
        raise ValueError("review_period must not be negative")

    mean_lead = lead_time.quoted if use_quoted_lead_time else lead_time.mean
    sd_lead = 0.0 if use_quoted_lead_time else lead_time.sd
    protection = mean_lead + review_period

    demand_term = protection * demand.sd**2
    lead_term = (demand.mean * sd_lead) ** 2
    if basis == "demand":
        lead_term = 0.0
    elif basis == "lead_time":
        demand_term = 0.0

    sigma = (demand_term + lead_term) ** 0.5
    return SafetyStock(
        units=z * sigma,
        z=z,
        sigma=sigma,
        demand_variance=demand_term,
        lead_time_variance=lead_term,
        protection_periods=protection,
    )


def decompose_safety_stock(
    demand: DemandProfile,
    lead_time: LeadTimeProfile,
    z: float,
    review_period: float = 0.0,
) -> pd.DataFrame:
    """Compare the combined sizing against each way of ignoring one source of variability.

    Args:
        demand: Demand per period.
        lead_time: Realised replenishment lead time.
        z: Safety factor.
        review_period: Periods between review opportunities.

    Returns:
        One row per basis with the safety stock in units, the share of variance attributable to
        lead time, and the error relative to the combined figure. The row for the quoted lead
        time is included because it is the sizing most operations actually use.
    """
    combined = safety_stock(demand, lead_time, z, "combined", review_period)
    rows = []
    variants = {
        "combined (realised lead time)": combined,
        "demand variability only": safety_stock(demand, lead_time, z, "demand", review_period),
        "lead-time variability only": safety_stock(
            demand, lead_time, z, "lead_time", review_period
        ),
        "quoted lead time, no variability": safety_stock(
            demand, lead_time, z, "combined", review_period, use_quoted_lead_time=True
        ),
    }
    for label, sized in variants.items():
        rows.append(
            {
                "basis": label,
                "safety_units": sized.units,
                "protection_periods": sized.protection_periods,
                "lead_time_variance_share": sized.lead_time_share,
                "error_vs_combined": sized.units / combined.units - 1.0
                if combined.units > 0
                else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def reorder_point(demand: DemandProfile, lead_time: LeadTimeProfile, sized: SafetyStock) -> float:
    """Reorder point: expected demand over the protection interval plus safety stock.

    Args:
        demand: Demand per period.
        lead_time: Realised replenishment lead time.
        sized: Output of :func:`safety_stock`, whose protection interval is reused so that a
            review period included in the sizing is not dropped here.

    Returns:
        The reorder point in units.
    """
    return demand.mean * sized.protection_periods + sized.units


def economic_order_quantity(
    annual_demand: float, order_cost: float, unit_cost: float, holding_rate: float
) -> float:
    """Economic order quantity.

    Included because the order quantity is an input to every fill-rate calculation above, so it
    cannot be left implicit. It is also the most over-applied formula in the field: it assumes
    constant demand, a fixed ordering cost that is knowable, and no capacity or MOQ constraint,
    and it is insensitive enough near the optimum that any quantity within about 20% of it costs
    under 2% more.

    Args:
        annual_demand: Units per year.
        order_cost: Cost of placing one order.
        unit_cost: Cost of one unit.
        holding_rate: Annual holding cost as a fraction of unit cost.

    Returns:
        The order quantity in units.

    Raises:
        ValueError: If any argument is not positive.
    """
    if min(annual_demand, order_cost, unit_cost, holding_rate) <= 0.0:
        raise ValueError("every argument must be positive")
    return (2.0 * annual_demand * order_cost / (unit_cost * holding_rate)) ** 0.5
