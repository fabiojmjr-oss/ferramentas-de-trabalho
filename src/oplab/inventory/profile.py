"""Estimating what a policy has to protect against, from data rather than from an assumption.

Two distributions size an inventory position: demand per period and replenishment lead time.
Almost every safety-stock calculation in circulation estimates the first from data and the
second from a number somebody typed - usually the quoted lead time, which is a commercial
promise rather than a measurement. That single substitution is the largest source of error in
inventory sizing, because it sets the variability of the lead time to zero, and lead-time
variability is the term that dominates.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd

from .normal import empirical_quantile


@dataclass(frozen=True)
class DemandProfile:
    """Demand per period for one series.

    Attributes:
        mean: Mean demand per period, counting periods of zero demand.
        sd: Standard deviation of demand per period.
        periods: Number of periods observed.
        zero_share: Share of periods with no demand, which is what decides whether the normal
            approximation behind the textbook formula is defensible at all.
    """

    mean: float
    sd: float
    periods: int
    zero_share: float

    @property
    def cv(self) -> float:
        """Coefficient of variation, or ``nan`` when mean demand is zero."""
        return self.sd / self.mean if self.mean > 0 else float("nan")


@dataclass(frozen=True)
class LeadTimeProfile:
    """Replenishment lead time in periods.

    Attributes:
        mean: Mean realised lead time.
        sd: Standard deviation of realised lead time.
        quoted: Lead time the supplier quotes, kept separate on purpose - the gap between
            ``quoted`` and ``mean`` is a commercial question and the gap between ``quoted`` and
            ``sd`` is an inventory one.
        observations: Number of orders observed.
        sample: The realised lead times, retained so a simulation can resample the actual
            distribution instead of a normal fitted to its first two moments.
    """

    mean: float
    sd: float
    quoted: float
    observations: int
    sample: npt.NDArray[np.float64]

    @property
    def cv(self) -> float:
        """Coefficient of variation of lead time."""
        return self.sd / self.mean if self.mean > 0 else float("nan")

    @property
    def skew(self) -> float:
        """Sample skewness, as evidence about the normal assumption rather than a decoration."""
        if self.sample.size < 3 or self.sd == 0.0:
            return float("nan")
        centred = self.sample - self.sample.mean()
        return float(np.mean(centred**3) / (self.sample.std(ddof=0) ** 3))

    def quantile(self, p: float) -> float:
        """Observed quantile of the lead-time sample."""
        return empirical_quantile(self.sample, p)


def fit_demand(demand: npt.ArrayLike) -> DemandProfile:
    """Summarise a demand series into the two moments a policy uses.

    Args:
        demand: Demand per period, including the periods of zero demand. Passing only the
            periods where demand occurred overstates the mean and understates the variance,
            which is the densification failure :func:`~oplab.forecast.to_panel` exists to avoid.

    Returns:
        A :class:`DemandProfile`.

    Raises:
        ValueError: If fewer than two periods are supplied, since a standard deviation of one
            observation is not a standard deviation.
    """
    values = np.asarray(demand, dtype=float)
    if values.size < 2:
        raise ValueError("at least two periods of demand are required")
    return DemandProfile(
        mean=float(values.mean()),
        sd=float(values.std(ddof=1)),
        periods=int(values.size),
        zero_share=float(np.mean(values == 0.0)),
    )


def fit_lead_time(lead_days: npt.ArrayLike, quoted: float | None = None) -> LeadTimeProfile:
    """Summarise realised lead times, keeping the sample for resampling.

    Args:
        lead_days: Realised lead times, one per replenishment order.
        quoted: The supplier's quoted lead time. Defaults to the observed mean, which makes the
            no-information case explicit rather than silently flattering the supplier.

    Returns:
        A :class:`LeadTimeProfile`.

    Raises:
        ValueError: If fewer than two orders are supplied.
    """
    values = np.asarray(lead_days, dtype=float)
    if values.size < 2:
        raise ValueError("at least two realised lead times are required")
    mean = float(values.mean())
    return LeadTimeProfile(
        mean=mean,
        sd=float(values.std(ddof=1)),
        quoted=float(quoted) if quoted is not None else mean,
        observations=int(values.size),
        sample=values,
    )


def lead_time_by_supplier(purchase_orders: pd.DataFrame) -> pd.DataFrame:
    """Fit a lead-time profile per supplier from a replenishment history.

    Args:
        purchase_orders: Frame with ``supplier``, ``lead_days`` and ``quoted_lead_days``.

    Returns:
        One row per supplier with the quoted lead time, the realised mean and standard
        deviation, the coefficient of variation, the skewness and the observed 95th percentile.
        The last two columns are there so that the normal assumption can be challenged on the
        same table it is used on.

    Raises:
        KeyError: If a required column is missing.
    """
    for column in ("supplier", "lead_days", "quoted_lead_days"):
        if column not in purchase_orders.columns:
            raise KeyError(f"purchase_orders has no column {column!r}")

    rows = []
    for supplier, group in purchase_orders.groupby("supplier", observed=True):
        profile = fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        rows.append(
            {
                "supplier": supplier,
                "orders": profile.observations,
                "quoted_lead_days": profile.quoted,
                "mean_lead_days": profile.mean,
                "sd_lead_days": profile.sd,
                "cv_lead_days": profile.cv,
                "skew_lead_days": profile.skew,
                "p95_lead_days": profile.quantile(0.95),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_lead_days", ignore_index=True)
