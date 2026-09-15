"""The service curve: monotone, convex, and priced against what it delivers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.inventory import (
    achieved_curve,
    fit_demand,
    fit_lead_time,
    lead_time_by_supplier,
    service_curve,
)


def inputs() -> tuple[object, object, pd.Series]:
    rng = np.random.default_rng(5)
    demand_path = pd.Series(np.round(rng.gamma(4.0, 5.0, size=365)))
    lead = np.round(rng.lognormal(np.log(8.0), 0.3, size=250), 2)
    return fit_demand(demand_path.to_numpy()), fit_lead_time(lead, quoted=8.0), demand_path


def test_the_curve_rises_and_its_price_per_point_rises_faster() -> None:
    """Convexity is the point of the chart: the last point of service is the expensive one."""
    demand, lead, _ = inputs()
    curve = service_curve(demand, lead, order_quantity=560.0, unit_cost=12.0)

    assert curve["safety_units"].is_monotonic_increasing
    assert curve["safety_capital"].is_monotonic_increasing
    assert curve["reorder_point"].is_monotonic_increasing
    assert curve["implied_fill_rate"].is_monotonic_increasing

    per_point = curve["capital_per_point"].dropna()
    assert per_point.is_monotonic_increasing
    assert per_point.iloc[-1] / per_point.iloc[0] > 3.0


def test_the_implied_fill_rate_is_above_the_cycle_service_target() -> None:
    """Every row of the curve is an instance of the confusion the module is built around."""
    demand, lead, _ = inputs()
    curve = service_curve(demand, lead, order_quantity=560.0, unit_cost=12.0)
    assert (curve["implied_fill_rate"] > curve["cycle_service_target"]).all()


def test_a_curve_of_one_point_is_refused() -> None:
    demand, lead, _ = inputs()
    with pytest.raises(ValueError, match="at least two targets"):
        service_curve(demand, lead, 560.0, 12.0, targets=(0.95,))
    with pytest.raises(ValueError, match="unit_cost"):
        service_curve(demand, lead, 560.0, 0.0)
    with pytest.raises(ValueError, match="order_quantity"):
        service_curve(demand, lead, 0.0, 12.0)


def test_the_achieved_curve_puts_promise_and_outcome_side_by_side() -> None:
    demand, lead, path = inputs()
    curve = achieved_curve(
        demand,
        lead,
        order_quantity=560.0,
        unit_cost=12.0,
        demand_sample=path,
        targets=(0.90, 0.95, 0.99),
        periods=730,
        replications=10,
    )
    assert list(curve["cycle_service_target"]) == [0.90, 0.95, 0.99]
    assert curve["achieved_cycle_service"].is_monotonic_increasing
    assert curve["mean_on_hand"].is_monotonic_increasing
    # The achieved figures are service levels, not promises, so they have to be probabilities.
    assert curve["achieved_fill_rate"].between(0.0, 1.0).all()
    assert curve["achieved_cycle_service"].between(0.0, 1.0).all()


def test_lead_time_by_supplier_reports_the_evidence_against_its_own_assumption() -> None:
    orders = pd.DataFrame(
        {
            "supplier": ["A"] * 6 + ["B"] * 6,
            "lead_days": [5, 5, 6, 5, 5, 20, 12, 12, 13, 12, 12, 13],
            "quoted_lead_days": [5] * 6 + [12] * 6,
        }
    )
    table = lead_time_by_supplier(orders).set_index("supplier")
    assert list(table.index) == ["A", "B"]  # sorted by realised mean, not by quoted
    assert table.loc["A", "skew_lead_days"] > 1.0
    assert table.loc["B", "skew_lead_days"] < 1.0
    # A is quoted shorter and is the less reliable of the two - the whole point of the table.
    assert table.loc["A", "quoted_lead_days"] < table.loc["B", "quoted_lead_days"]
    assert table.loc["A", "cv_lead_days"] > table.loc["B", "cv_lead_days"]

    with pytest.raises(KeyError, match="supplier"):
        lead_time_by_supplier(pd.DataFrame({"lead_days": [1.0, 2.0]}))
