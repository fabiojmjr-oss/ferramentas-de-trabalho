"""The simulator, and the transient that would otherwise be mistaken for a result."""

from __future__ import annotations

import numpy as np
import pytest

from oplab.inventory import (
    ContinuousReview,
    PeriodicReview,
    fit_demand,
    fit_lead_time,
    reorder_point,
    safety_stock,
    simulate_policy,
    z_for_cycle_service,
)


def demand_sample() -> np.ndarray:
    """A year of daily demand with a mean of about 20 and a realistic spread."""
    rng = np.random.default_rng(3)
    return np.round(rng.gamma(shape=4.0, scale=5.0, size=365))


def lead_sample() -> np.ndarray:
    """A right-skewed lead time: mostly a week, occasionally three."""
    rng = np.random.default_rng(4)
    base = rng.lognormal(np.log(7.0), 0.25, size=300)
    base[:9] += rng.exponential(10.0, size=9)
    return np.round(base, 2)


def test_a_policy_with_no_stock_fails_and_one_with_plenty_does_not() -> None:
    """The two ends bracket every other result, so they are worth pinning."""
    demand, lead = demand_sample(), lead_sample()
    starved = simulate_policy(
        ContinuousReview(reorder_point=0.0, order_quantity=50.0),
        demand,
        lead,
        periods=400,
        replications=5,
    ).summary()
    assert starved["fill_rate"] < 0.6

    flooded = simulate_policy(
        ContinuousReview(reorder_point=5000.0, order_quantity=2000.0),
        demand,
        lead,
        periods=400,
        replications=5,
    ).summary()
    assert flooded["fill_rate"] == pytest.approx(1.0)
    assert flooded["cycle_service"] == pytest.approx(1.0)


def test_the_warmup_makes_the_result_independent_of_the_opening_stock() -> None:
    """This is the whole reason the warm-up exists, so it is asserted rather than described.

    Without it the same policy on the same data measures very differently depending only on an
    assumption nobody states, and the artefact moves in the direction intuition expects - which
    is what makes it dangerous.
    """
    demand, lead = demand_sample(), lead_sample()
    profile = fit_demand(demand)
    sized = safety_stock(profile, fit_lead_time(lead), z_for_cycle_service(0.95))
    rop = reorder_point(profile, fit_lead_time(lead), sized)
    policy = ContinuousReview(reorder_point=rop, order_quantity=profile.mean * 28.0)

    openings = [None, rop, 0.0]
    without = [
        simulate_policy(
            policy, demand, lead, periods=365, replications=20, initial_stock=opening, warmup=0
        ).summary()["cycle_service"]
        for opening in openings
    ]
    with_warmup = [
        simulate_policy(
            policy, demand, lead, periods=365, replications=20, initial_stock=opening
        ).summary()["cycle_service"]
        for opening in openings
    ]

    assert max(without) - min(without) > 0.05
    assert max(with_warmup) - min(with_warmup) < 0.02


def test_the_warmup_is_capped_so_a_short_horizon_still_reports() -> None:
    demand, lead = demand_sample(), lead_sample()
    result = simulate_policy(
        ContinuousReview(reorder_point=200.0, order_quantity=400.0),
        demand,
        lead,
        periods=40,
        replications=3,
    )
    assert result.replications["period_service"].notna().all()

    with pytest.raises(ValueError, match="warmup"):
        simulate_policy(
            ContinuousReview(200.0, 400.0), demand, lead, periods=40, replications=1, warmup=-1
        )


def test_more_safety_stock_never_lowers_service() -> None:
    demand, lead = demand_sample(), lead_sample()
    profile = fit_demand(demand)
    fills = []
    for level in (0.80, 0.90, 0.95, 0.99):
        lead_profile = fit_lead_time(lead)
        sized = safety_stock(profile, lead_profile, z_for_cycle_service(level))
        policy = ContinuousReview(
            reorder_point=reorder_point(profile, lead_profile, sized),
            order_quantity=profile.mean * 28.0,
        )
        fills.append(
            simulate_policy(policy, demand, lead, periods=730, replications=15).summary()[
                "fill_rate"
            ]
        )
    assert fills == sorted(fills)


def test_periodic_review_orders_on_the_review_cadence_only() -> None:
    demand, lead = demand_sample(), lead_sample()
    weekly = simulate_policy(
        PeriodicReview(review_period=7, order_up_to=500.0),
        demand,
        lead,
        periods=730,
        replications=10,
    ).summary()
    monthly = simulate_policy(
        PeriodicReview(review_period=28, order_up_to=500.0),
        demand,
        lead,
        periods=730,
        replications=10,
    ).summary()

    # A longer review period means fewer orders and, at the same order-up-to level, worse service:
    # the exposure window is the lead time plus the review period.
    assert monthly["orders_placed"] < weekly["orders_placed"]
    assert monthly["fill_rate"] < weekly["fill_rate"]


def test_fill_rate_is_never_below_cycle_service_on_these_policies() -> None:
    """A shortfall late in a cycle costs few units, so counting units flatters the policy."""
    demand, lead = demand_sample(), lead_sample()
    summary = simulate_policy(
        ContinuousReview(reorder_point=300.0, order_quantity=560.0),
        demand,
        lead,
        periods=730,
        replications=15,
    ).summary()
    assert summary["fill_rate"] > summary["cycle_service"]


def test_the_result_is_reproducible_from_its_seed() -> None:
    demand, lead = demand_sample(), lead_sample()
    args = (ContinuousReview(300.0, 560.0), demand, lead)
    first = simulate_policy(*args, periods=365, replications=5, seed=11).replications
    second = simulate_policy(*args, periods=365, replications=5, seed=11).replications
    third = simulate_policy(*args, periods=365, replications=5, seed=12).replications
    assert first.equals(second)
    assert not first.equals(third)


def test_confidence_interval_says_nothing_rather_than_something_wrong() -> None:
    demand, lead = demand_sample(), lead_sample()
    single = simulate_policy(
        ContinuousReview(300.0, 560.0), demand, lead, periods=365, replications=1
    )
    low, high = single.interval("fill_rate")
    assert low == high

    many = simulate_policy(
        ContinuousReview(300.0, 560.0), demand, lead, periods=365, replications=25
    )
    low, high = many.interval("fill_rate")
    assert low < many.summary()["fill_rate"] < high
    with pytest.raises(KeyError, match="no metric"):
        many.interval("profit")


def test_input_guards() -> None:
    demand, lead = demand_sample(), lead_sample()
    with pytest.raises(ValueError, match="order_quantity"):
        ContinuousReview(reorder_point=100.0, order_quantity=0.0)
    with pytest.raises(ValueError, match="review_period"):
        PeriodicReview(review_period=0, order_up_to=100.0)
    with pytest.raises(ValueError, match="order_up_to"):
        PeriodicReview(review_period=7, order_up_to=0.0)
    with pytest.raises(ValueError, match="demand_sample is empty"):
        simulate_policy(ContinuousReview(100.0, 200.0), [], lead)
    with pytest.raises(ValueError, match="lead_time_sample is empty"):
        simulate_policy(ContinuousReview(100.0, 200.0), demand, [])
    with pytest.raises(ValueError, match="periods"):
        simulate_policy(ContinuousReview(100.0, 200.0), demand, lead, periods=0)
    with pytest.raises(ValueError, match="replications"):
        simulate_policy(ContinuousReview(100.0, 200.0), demand, lead, replications=0)
