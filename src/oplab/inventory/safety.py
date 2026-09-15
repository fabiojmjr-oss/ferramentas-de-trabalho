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

The third confusion is the one this module was initially wrong about, and it is the subtlest.
The formula below buffers against ``sd_d``, the standard deviation of **demand**. That is the
right quantity only when the replenishment target is the long-run mean. When it is a **forecast**,
the quantity to buffer is the standard deviation of the **forecast error**, and the two are not
interchangeable: a forecast that tracks the series reduces the buffer below demand variability,
and a forecast that does not adds uncertainty to the decision and enlarges it. Sizing on demand
variability is therefore not the conservative choice - it is a choice that can be wrong in either
direction, and which direction depends on a measurement nobody takes.
:func:`safety_stock_from_forecast_error` takes it, and :func:`compare_sizing_bases` puts the two
side by side.

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


def safety_stock_from_forecast_error(
    error_sd: float,
    error_bias: float,
    lead_time: LeadTimeProfile,
    z: float,
    demand_mean: float,
    review_period: float = 0.0,
    correct_bias: bool = True,
) -> SafetyStock:
    """Size safety stock on the forecast error rather than on demand variability.

    This is the version that applies when replenishment is driven by a forecast. The demand term
    becomes the forecast error variance over the protection interval; the lead-time term is
    unchanged, because lead-time variability multiplies the demand *rate* whether or not that rate
    came from a forecast.

    Args:
        error_sd: Standard deviation of the forecast error per period, from
            :func:`~oplab.forecast.error_profile`.
        error_bias: Mean forecast error per period, forecast minus actual. A positive value is an
            over-forecast, which inflates stock on its own and needs no buffer; a negative value
            is an under-forecast, whose shortfall accumulates over the protection interval and is
            not covered by any amount of symmetric buffer.
        lead_time: Realised replenishment lead time.
        z: Safety factor.
        demand_mean: Mean demand per period, for the lead-time variance term.
        review_period: Periods between review opportunities.
        correct_bias: Add the accumulated under-forecast over the protection interval to the
            buffer. Defaults to true because leaving it out is the common error: a biased forecast
            produces a policy that misses its service target every cycle in the same direction,
            and no increase in ``z`` fixes a centre that is in the wrong place. The honest remedy
            is to fix the forecast; this is what it costs until someone does.

    Returns:
        A :class:`SafetyStock` whose ``demand_variance`` term is the forecast error variance.

    Raises:
        ValueError: If ``error_sd`` is negative or ``review_period`` is negative.
    """
    if error_sd < 0.0:
        raise ValueError("error_sd must not be negative")
    if review_period < 0.0:
        raise ValueError("review_period must not be negative")

    protection = lead_time.mean + review_period
    error_term = protection * error_sd**2
    lead_term = (demand_mean * lead_time.sd) ** 2
    sigma = (error_term + lead_term) ** 0.5

    units = z * sigma
    if correct_bias and error_bias < 0.0:
        units += -error_bias * protection

    return SafetyStock(
        units=units,
        z=z,
        sigma=sigma,
        demand_variance=error_term,
        lead_time_variance=lead_term,
        protection_periods=protection,
    )


def compare_sizing_bases(
    demand: DemandProfile,
    lead_time: LeadTimeProfile,
    error_sd: float,
    error_bias: float,
    z: float,
    review_period: float = 0.0,
) -> pd.DataFrame:
    """Put the demand-variability and forecast-error sizings side by side.

    Args:
        demand: Demand per period.
        lead_time: Realised replenishment lead time.
        error_sd: Standard deviation of the forecast error per period.
        error_bias: Mean forecast error per period, forecast minus actual.
        z: Safety factor.
        review_period: Periods between review opportunities.

    Returns:
        Three rows - sized on demand variability, sized on forecast error, and sized on forecast
        error without the bias correction - with the safety stock in units and the change against
        the demand-variability figure. The third row exists to separate the two effects: how much
        of the difference is the forecast being sharper than the mean, and how much is the price
        of its bias.
    """
    on_demand = safety_stock(demand, lead_time, z, "combined", review_period)
    on_error = safety_stock_from_forecast_error(
        error_sd, error_bias, lead_time, z, demand.mean, review_period
    )
    no_correction = safety_stock_from_forecast_error(
        error_sd, error_bias, lead_time, z, demand.mean, review_period, correct_bias=False
    )

    rows = []
    for label, sized in (
        ("demand variability", on_demand),
        ("forecast error", on_error),
        ("forecast error, bias uncorrected", no_correction),
    ):
        rows.append(
            {
                "basis": label,
                "safety_units": sized.units,
                "sigma": sized.sigma,
                "lead_time_variance_share": sized.lead_time_share,
                "change_vs_demand": sized.units / on_demand.units - 1.0
                if on_demand.units > 0
                else float("nan"),
            }
        )
    return pd.DataFrame(rows)
