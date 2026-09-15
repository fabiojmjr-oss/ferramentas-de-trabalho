"""Safety stock against hand-computed values, and the two service definitions kept apart."""

from __future__ import annotations

import numpy as np
import pytest

from oplab.inventory import (
    decompose_safety_stock,
    economic_order_quantity,
    expected_fill_rate,
    fit_demand,
    fit_lead_time,
    reorder_point,
    safety_stock,
    z_for_cycle_service,
    z_for_fill_rate,
)
from oplab.inventory.normal import norm_cdf
from oplab.inventory.profile import DemandProfile, LeadTimeProfile


def profiles() -> tuple[DemandProfile, LeadTimeProfile]:
    """A demand and a lead-time profile whose safety stock is computable by hand.

    Demand of 100 +/- 20 a day, lead time of 9 +/- 2 days. The combined variance is
    9 * 400 + 10000 * 4 = 3600 + 40000 = 43600, so sigma is exactly 208.8061...
    """
    demand = DemandProfile(mean=100.0, sd=20.0, periods=365, zero_share=0.0)
    lead = LeadTimeProfile(mean=9.0, sd=2.0, quoted=9.0, observations=50, sample=np.full(50, 9.0))
    return demand, lead


def test_combined_sigma_is_the_hand_computed_value() -> None:
    demand, lead = profiles()
    sized = safety_stock(demand, lead, 1.0)
    assert sized.demand_variance == pytest.approx(3600.0)
    assert sized.lead_time_variance == pytest.approx(40000.0)
    assert sized.sigma == pytest.approx(43600.0**0.5)
    assert sized.units == pytest.approx(43600.0**0.5)
    assert sized.lead_time_share == pytest.approx(40000.0 / 43600.0)


def test_the_partial_bases_drop_exactly_one_term() -> None:
    demand, lead = profiles()
    assert safety_stock(demand, lead, 1.0, "demand").sigma == pytest.approx(60.0)
    assert safety_stock(demand, lead, 1.0, "lead_time").sigma == pytest.approx(200.0)


def test_the_review_period_lengthens_the_protection_interval() -> None:
    """A periodic review is exposed for the review period as well as the lead time."""
    demand, lead = profiles()
    without = safety_stock(demand, lead, 1.0)
    with_review = safety_stock(demand, lead, 1.0, review_period=7.0)
    assert with_review.protection_periods == pytest.approx(16.0)
    assert with_review.demand_variance == pytest.approx(16.0 * 400.0)
    # Only the demand term grows; lead-time variance does not depend on the interval's length.
    assert with_review.lead_time_variance == pytest.approx(without.lead_time_variance)
    assert with_review.units > without.units


def test_the_quoted_lead_time_deletes_the_dominant_term() -> None:
    """This is the error the module exists to price, so it is pinned numerically."""
    demand, lead = profiles()
    quoted = safety_stock(demand, lead, 1.0, use_quoted_lead_time=True)
    assert quoted.lead_time_variance == 0.0
    assert quoted.sigma == pytest.approx(60.0)
    assert quoted.units / safety_stock(demand, lead, 1.0).units == pytest.approx(
        60.0 / 43600.0**0.5
    )


def test_safety_stock_rejects_an_unknown_basis_and_a_negative_review() -> None:
    demand, lead = profiles()
    with pytest.raises(ValueError, match="basis must be"):
        safety_stock(demand, lead, 1.0, "guess")
    with pytest.raises(ValueError, match="review_period"):
        safety_stock(demand, lead, 1.0, review_period=-1.0)


def test_decomposition_reports_the_error_against_the_combined_figure() -> None:
    demand, lead = profiles()
    table = decompose_safety_stock(demand, lead, 1.645).set_index("basis")
    assert len(table) == 4
    assert table.loc["combined (realised lead time)", "error_vs_combined"] == pytest.approx(0.0)
    # Every other basis understates, which is the direction that matters.
    others = table.drop(index="combined (realised lead time)")["error_vs_combined"]
    assert (others < 0.0).all()


def test_reorder_point_uses_the_sizing_protection_interval() -> None:
    """A review period included in the sizing must not be dropped from the reorder point."""
    demand, lead = profiles()
    sized = safety_stock(demand, lead, 1.645, review_period=7.0)
    assert reorder_point(demand, lead, sized) == pytest.approx(1600.0 + sized.units)


def test_cycle_service_and_fill_rate_are_different_questions() -> None:
    """The same 99% sized two ways gives two different safety stocks, and the gap is large."""
    demand, lead = profiles()
    sigma = safety_stock(demand, lead, 1.0).sigma
    order_quantity = 100.0 * 28.0

    z_cycle = z_for_cycle_service(0.99)
    z_fill = z_for_fill_rate(0.99, sigma, order_quantity)
    assert z_cycle > z_fill
    # The cycle-service sizing delivers a fill rate far above the target it was not set for.
    assert expected_fill_rate(z_cycle, sigma, order_quantity) > 0.999
    # And the fill-rate sizing delivers a cycle service far below 99%.
    assert norm_cdf(z_fill) < 0.95


def test_fill_rate_and_its_inverse_round_trip() -> None:
    demand, lead = profiles()
    sigma = safety_stock(demand, lead, 1.0).sigma
    for target in (0.90, 0.95, 0.99, 0.999):
        z = z_for_fill_rate(target, sigma, 2800.0)
        assert expected_fill_rate(z, sigma, 2800.0) == pytest.approx(target, abs=1e-9)


def test_a_larger_order_quantity_buys_fill_rate_without_more_stock() -> None:
    """The dependency the cycle-service formula does not have, and the reason it cannot convert."""
    demand, lead = profiles()
    sigma = safety_stock(demand, lead, 1.0).sigma
    small = expected_fill_rate(1.645, sigma, 500.0)
    large = expected_fill_rate(1.645, sigma, 5000.0)
    assert large > small


def test_service_target_guards() -> None:
    with pytest.raises(ValueError, match="strictly between"):
        z_for_fill_rate(1.0, 100.0, 500.0)
    with pytest.raises(ValueError, match="sigma"):
        z_for_fill_rate(0.95, 0.0, 500.0)
    with pytest.raises(ValueError, match="order_quantity"):
        z_for_fill_rate(0.95, 100.0, 0.0)
    with pytest.raises(ValueError, match="sigma"):
        expected_fill_rate(1.0, -1.0, 500.0)
    with pytest.raises(ValueError, match="order_quantity"):
        expected_fill_rate(1.0, 100.0, -5.0)


def test_eoq_matches_the_closed_form_and_is_flat_near_the_optimum() -> None:
    """The flatness is the reason the formula's precision is not worth arguing about."""
    q = economic_order_quantity(
        annual_demand=36500.0, order_cost=200.0, unit_cost=10.0, holding_rate=0.25
    )
    assert q == pytest.approx((2 * 36500 * 200 / 2.5) ** 0.5)

    def total_cost(quantity: float) -> float:
        return 36500.0 / quantity * 200.0 + quantity / 2.0 * 2.5

    assert total_cost(q * 1.2) / total_cost(q) - 1 < 0.02
    assert total_cost(q * 0.8) / total_cost(q) - 1 < 0.03

    with pytest.raises(ValueError, match="positive"):
        economic_order_quantity(0.0, 200.0, 10.0, 0.25)


def test_profile_fitting_and_its_guards() -> None:
    demand = fit_demand([0.0, 4.0, 0.0, 8.0, 12.0])
    assert demand.mean == pytest.approx(4.8)
    assert demand.zero_share == pytest.approx(0.4)
    assert demand.cv == pytest.approx(demand.sd / 4.8)
    assert fit_demand([0.0, 0.0]).cv != fit_demand([0.0, 0.0]).cv  # nan on zero mean

    lead = fit_lead_time([4.0, 5.0, 6.0])
    assert lead.mean == pytest.approx(5.0)
    assert lead.quoted == pytest.approx(5.0)  # defaults to the mean, not to a flattering number
    assert lead.quantile(0.5) == pytest.approx(5.0)
    assert lead.skew == pytest.approx(0.0, abs=1e-12)

    with pytest.raises(ValueError, match="two periods"):
        fit_demand([1.0])
    with pytest.raises(ValueError, match="two realised"):
        fit_lead_time([3.0])


def test_skewness_is_reported_because_it_challenges_the_assumption() -> None:
    right_tailed = fit_lead_time([5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 30.0])
    assert right_tailed.skew > 2.0
    assert np.isnan(fit_lead_time([5.0, 5.0]).skew)
