"""Simulating a policy, because the formula's promise and the policy's behaviour differ.

The safety-stock formula is a normal approximation evaluated at one point. It assumes demand
over the protection interval is normally distributed, that the interval's variability is
captured by two moments, and that a stockout is a single event per cycle. On a real assortment
none of the three holds: demand is discrete and often intermittent, realised lead time is right
skewed, and the review period makes the exposure longer than the lead time.

None of that means the formula is useless. It means the number it promises has to be checked
against the service the policy actually delivers, and the gap is a property of the item rather
than a constant. This module runs the policy on resampled demand and resampled lead times and
reports the achieved service, so the promise can be compared with the outcome on the same table.

Unmet demand is **lost**, not backordered. That is the right assumption for a distribution
centre serving retail or e-commerce, it is the pessimistic one for fill rate, and it is stated
here because the alternative changes every number below.

One implementation detail is not a detail. The opening stock is an assumption, and on a horizon
short enough to contain few replenishment cycles it dominates the result: the same policy on the
same data measured between 89% and 97% cycle service on a one-year horizon depending only on
whether it started full, at the reorder point, or empty. A warm-up period, excluded from the
statistics, removes it. Without one, a policy comparison is partly a comparison of opening
assumptions, and the artefact is easy to mistake for a finding because it moves in the direction
intuition expects.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
import pandas as pd


@dataclass(frozen=True)
class ContinuousReview:
    """An ``(s, Q)`` policy: order ``Q`` units whenever the inventory position falls to ``s``.

    Attributes:
        reorder_point: The level ``s`` at which an order is placed.
        order_quantity: The quantity ``Q`` ordered.
    """

    reorder_point: float
    order_quantity: float
    review_period: int = 1

    def __post_init__(self) -> None:
        if self.order_quantity <= 0:
            raise ValueError("order_quantity must be positive")
        if self.review_period < 1:
            raise ValueError("review_period must be at least one period")


@dataclass(frozen=True)
class PeriodicReview:
    """An ``(R, S)`` policy: every ``R`` periods, order up to ``S``.

    Attributes:
        review_period: Periods between reviews, ``R``.
        order_up_to: The target level ``S``.
    """

    review_period: int
    order_up_to: float

    def __post_init__(self) -> None:
        if self.review_period < 1:
            raise ValueError("review_period must be at least one period")
        if self.order_up_to <= 0:
            raise ValueError("order_up_to must be positive")


Policy = ContinuousReview | PeriodicReview


@dataclass(frozen=True)
class SimulationResult:
    """Achieved service and inventory from a set of replications.

    Attributes:
        replications: One row per replication.
    """

    replications: pd.DataFrame

    def summary(self) -> pd.Series:
        """Mean of every metric across replications."""
        return self.replications.mean()

    def interval(self, metric: str, confidence: float = 0.95) -> tuple[float, float]:
        """Normal-approximation confidence interval on the mean of ``metric``.

        Args:
            metric: Column of :attr:`replications`.
            confidence: Coverage.

        Returns:
            Lower and upper bound. Both bounds are the mean when there is one replication, which
            says there is no information about the spread rather than implying a tight one.

        Raises:
            KeyError: If ``metric`` is not a column.
        """
        from .normal import norm_ppf

        if metric not in self.replications.columns:
            raise KeyError(f"no metric named {metric!r}")
        values = self.replications[metric].to_numpy(dtype=float)
        mean = float(values.mean())
        if values.size < 2:
            return mean, mean
        half = norm_ppf(0.5 + confidence / 2.0) * float(values.std(ddof=1)) / values.size**0.5
        return mean - half, mean + half


def simulate_policy(
    policy: Policy,
    demand_sample: npt.ArrayLike,
    lead_time_sample: npt.ArrayLike,
    periods: int = 365,
    replications: int = 30,
    seed: int = 7,
    initial_stock: float | None = None,
    warmup: int | None = None,
) -> SimulationResult:
    """Run a policy against resampled demand and resampled lead times.

    Both inputs are resampled from the observed data rather than drawn from a fitted normal.
    That is the whole point: the formula already assumes normality, so validating it against
    normal draws would only confirm its own arithmetic. Resampling keeps the skew of the lead
    time and the zeros of the demand, which is where the promise breaks.

    Args:
        policy: A :class:`ContinuousReview` or :class:`PeriodicReview` policy.
        demand_sample: Observed demand per period, including zero periods, resampled with
            replacement to build each replication's demand path.
        lead_time_sample: Observed lead times in periods, resampled per order.
        periods: Length of each replication.
        replications: Number of independent replications.
        seed: Seed for the resampling, so the result is reproducible.
        initial_stock: Opening stock. Defaults to the policy's order-up-to level or reorder
            point plus one order quantity, which is the steady state a policy is usually already
            in - starting empty would charge the policy for a transient it does not own.
        warmup: Periods simulated but excluded from the statistics, to remove the opening-stock
            transient. Defaults to two replenishment cycles, which is what makes the result
            insensitive to ``initial_stock``; it is capped at half of ``periods`` so a short
            horizon still reports something, and a horizon that short should be lengthened rather
            than trusted.

    Returns:
        A :class:`SimulationResult` whose columns are ``fill_rate`` (share of demand met from
        stock), ``cycle_service`` (share of replenishment cycles with no shortfall),
        ``period_service`` (share of periods with no shortfall), ``mean_on_hand``,
        ``orders_placed`` and ``unmet_units``. Every metric is measured after the warm-up.

    Raises:
        ValueError: If a sample is empty, or ``periods`` or ``replications`` is not positive.
    """
    demand_values = np.asarray(demand_sample, dtype=float)
    lead_values = np.asarray(lead_time_sample, dtype=float)
    if demand_values.size == 0:
        raise ValueError("demand_sample is empty")
    if lead_values.size == 0:
        raise ValueError("lead_time_sample is empty")
    if periods < 1:
        raise ValueError("periods must be positive")
    if replications < 1:
        raise ValueError("replications must be positive")

    if isinstance(policy, PeriodicReview):
        review = policy.review_period
        opening = policy.order_up_to if initial_stock is None else initial_stock
    else:
        review = policy.review_period
        opening = (
            policy.reorder_point + policy.order_quantity if initial_stock is None else initial_stock
        )

    if warmup is None:
        mean_demand = float(demand_values.mean())
        cover = (
            policy.order_quantity / mean_demand
            if isinstance(policy, ContinuousReview) and mean_demand > 0
            else float(review)
        )
        warmup = int(round(2.0 * (float(lead_values.mean()) + cover)))
    if warmup < 0:
        raise ValueError("warmup must not be negative")
    warmup = min(warmup, periods // 2)

    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(replications):
        path = rng.choice(demand_values, size=periods)
        on_hand = float(opening)
        pipeline: list[tuple[int, float]] = []
        unmet = 0.0
        total = 0.0
        stockout_periods = 0
        cycles = 0
        cycles_short = 0
        cycle_short = False
        on_hand_trace = np.empty(periods, dtype=float)

        for period in range(periods):
            arriving = [qty for due, qty in pipeline if due == period]
            if arriving:
                on_hand += float(sum(arriving))
                pipeline = [(due, qty) for due, qty in pipeline if due != period]
                # A cycle closes when stock arrives; whether it was short is known only then.
                if period >= warmup:
                    cycles += 1
                    cycles_short += int(cycle_short)
                cycle_short = False

            counting = period >= warmup
            want = float(path[period])
            served = min(on_hand, want)
            on_hand -= served
            if counting:
                total += want
            if served < want:
                if counting:
                    unmet += want - served
                    stockout_periods += 1
                cycle_short = True

            on_hand_trace[period] = on_hand

            if period % review == 0:
                position = on_hand + float(sum(qty for _, qty in pipeline))
                if isinstance(policy, PeriodicReview):
                    quantity = max(0.0, policy.order_up_to - position)
                else:
                    quantity = policy.order_quantity if position <= policy.reorder_point else 0.0
                if quantity > 0.0:
                    lead = float(rng.choice(lead_values))
                    pipeline.append((period + max(1, int(round(lead))), quantity))

        # An open cycle at the horizon is counted, so that a policy whose last cycle is short
        # does not get the shortfall dropped for free.
        if cycle_short:
            cycles += 1
            cycles_short += 1

        rows.append(
            {
                "fill_rate": 1.0 - unmet / total if total > 0 else float("nan"),
                "cycle_service": 1.0 - cycles_short / cycles if cycles > 0 else float("nan"),
                "period_service": 1.0 - stockout_periods / (periods - warmup),
                "mean_on_hand": float(on_hand_trace[warmup:].mean()),
                "orders_placed": float(cycles),
                "unmet_units": unmet,
            }
        )

    return SimulationResult(replications=pd.DataFrame(rows))
