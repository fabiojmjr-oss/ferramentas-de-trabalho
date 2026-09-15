"""Sizing safety stock on the forecast error instead of on demand variability."""

from __future__ import annotations

import numpy as np
import pytest

from oplab.inventory import compare_sizing_bases, safety_stock, safety_stock_from_forecast_error
from oplab.inventory.profile import DemandProfile, LeadTimeProfile


def profiles() -> tuple[DemandProfile, LeadTimeProfile]:
    """Demand of 100 +/- 20 a day, lead time of 9 +/- 2 days - the same pair as test_safety."""
    demand = DemandProfile(mean=100.0, sd=20.0, periods=365, zero_share=0.0)
    lead = LeadTimeProfile(mean=9.0, sd=2.0, quoted=9.0, observations=50, sample=np.full(50, 9.0))
    return demand, lead


def test_an_error_equal_to_demand_variability_reproduces_the_demand_sizing() -> None:
    """The boundary case that proves the two formulas are the same formula, differently fed."""
    demand, lead = profiles()
    on_demand = safety_stock(demand, lead, 1.645)
    on_error = safety_stock_from_forecast_error(
        error_sd=demand.sd, error_bias=0.0, lead_time=lead, z=1.645, demand_mean=demand.mean
    )
    assert on_error.units == pytest.approx(on_demand.units)
    assert on_error.sigma == pytest.approx(on_demand.sigma)
    assert on_error.demand_variance == pytest.approx(on_demand.demand_variance)


def test_a_sharper_forecast_reduces_the_buffer_and_a_worse_one_enlarges_it() -> None:
    demand, lead = profiles()
    baseline = safety_stock(demand, lead, 1.645).units
    sharper = safety_stock_from_forecast_error(10.0, 0.0, lead, 1.645, demand.mean).units
    worse = safety_stock_from_forecast_error(40.0, 0.0, lead, 1.645, demand.mean).units
    assert sharper < baseline < worse


def test_only_the_demand_term_changes_because_lead_time_multiplies_the_rate() -> None:
    """Lead-time variability multiplies the demand rate whether or not a forecast produced it."""
    demand, lead = profiles()
    on_demand = safety_stock(demand, lead, 1.0)
    on_error = safety_stock_from_forecast_error(10.0, 0.0, lead, 1.0, demand.mean)
    assert on_error.lead_time_variance == pytest.approx(on_demand.lead_time_variance)
    assert on_error.demand_variance == pytest.approx(9.0 * 100.0)
    assert on_error.protection_periods == pytest.approx(9.0)


def test_an_under_forecast_is_charged_and_an_over_forecast_is_not() -> None:
    """A negative bias accumulates a real shortfall; a positive one already inflates stock."""
    demand, lead = profiles()
    centred = safety_stock_from_forecast_error(10.0, 0.0, lead, 1.645, demand.mean).units
    under = safety_stock_from_forecast_error(10.0, -2.0, lead, 1.645, demand.mean).units
    over = safety_stock_from_forecast_error(10.0, +2.0, lead, 1.645, demand.mean).units

    # The under-forecast costs exactly the shortfall accumulated over the protection interval.
    assert under - centred == pytest.approx(2.0 * 9.0)
    assert over == pytest.approx(centred)
    # And the correction can be switched off, which is what isolates its cost.
    uncorrected = safety_stock_from_forecast_error(
        10.0, -2.0, lead, 1.645, demand.mean, correct_bias=False
    ).units
    assert uncorrected == pytest.approx(centred)


def test_the_review_period_lengthens_both_terms_that_depend_on_it() -> None:
    demand, lead = profiles()
    sized = safety_stock_from_forecast_error(10.0, -1.0, lead, 1.0, demand.mean, review_period=7.0)
    assert sized.protection_periods == pytest.approx(16.0)
    assert sized.demand_variance == pytest.approx(16.0 * 100.0)
    # The bias charge grows with the interval too, because the shortfall accumulates over it.
    centred = safety_stock_from_forecast_error(10.0, 0.0, lead, 1.0, demand.mean, review_period=7.0)
    assert sized.units - centred.units == pytest.approx(16.0)


def test_guards() -> None:
    demand, lead = profiles()
    with pytest.raises(ValueError, match="error_sd"):
        safety_stock_from_forecast_error(-1.0, 0.0, lead, 1.0, demand.mean)
    with pytest.raises(ValueError, match="review_period"):
        safety_stock_from_forecast_error(1.0, 0.0, lead, 1.0, demand.mean, review_period=-1.0)


def test_the_comparison_separates_the_forecast_from_its_bias() -> None:
    """Three rows, because how much is sharpness and how much is bias are different questions."""
    demand, lead = profiles()
    table = compare_sizing_bases(demand, lead, error_sd=10.0, error_bias=-2.0, z=1.645).set_index(
        "basis"
    )
    assert len(table) == 3
    assert table.loc["demand variability", "change_vs_demand"] == pytest.approx(0.0)
    # Sharper than demand, so the uncorrected row is below the demand row.
    assert table.loc["forecast error, bias uncorrected", "change_vs_demand"] < 0.0
    # The bias charge is the difference between the two forecast-error rows.
    charge = (
        table.loc["forecast error", "safety_units"]
        - table.loc["forecast error, bias uncorrected", "safety_units"]
    )
    assert charge == pytest.approx(2.0 * 9.0)
