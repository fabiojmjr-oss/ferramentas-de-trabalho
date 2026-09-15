"""Inventory record accuracy behaviour."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.kpi import inventory_record_accuracy, variance_pareto


@pytest.fixture
def offsetting_counts() -> pd.DataFrame:
    """Four locations whose discrepancies cancel out exactly.

    Every location is wrong, yet the signed discrepancies sum to zero. Net accuracy therefore
    reports a perfect inventory, absolute accuracy reports 92.5%, and location accuracy reports
    zero. This is the construction that makes a net-based indicator indefensible.
    """
    return pd.DataFrame(
        {
            "count_date": pd.Timestamp("2025-01-01"),
            "site": "CD-SP",
            "location": ["01-01-1", "01-01-2", "01-01-3", "01-01-4"],
            "sku": ["S1", "S2", "S3", "S4"],
            "system_qty": [100, 100, 100, 100],
            "counted_qty": [110, 90, 105, 95],
        }
    )


def test_net_accuracy_hides_what_absolute_accuracy_exposes(
    offsetting_counts: pd.DataFrame,
) -> None:
    result = inventory_record_accuracy(offsetting_counts).iloc[0]
    assert result["unit_accuracy_net"] == pytest.approx(1.0)
    assert result["unit_accuracy_abs"] == pytest.approx(1 - 30 / 400)
    assert result["location_accuracy"] == pytest.approx(0.0)
    assert result["abs_variance_units"] == pytest.approx(30.0)
    assert result["net_variance_units"] == pytest.approx(0.0)


def test_tolerance_counts_near_misses_as_matches(offsetting_counts: pd.DataFrame) -> None:
    result = inventory_record_accuracy(offsetting_counts, tolerance_units=5).iloc[0]
    # Two locations are out by exactly five units.
    assert result["location_accuracy"] == pytest.approx(0.5)


def test_negative_tolerance_is_rejected(offsetting_counts: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="tolerance_units"):
        inventory_record_accuracy(offsetting_counts, tolerance_units=-1)


def test_value_weighting_requires_a_complete_price_list(
    offsetting_counts: pd.DataFrame,
) -> None:
    cost = pd.Series({"S1": 10.0, "S2": 10.0, "S3": 10.0})
    with pytest.raises(KeyError, match="missing a price"):
        inventory_record_accuracy(offsetting_counts, unit_cost=cost)


def test_value_weighting_reports_the_financial_exposure(
    offsetting_counts: pd.DataFrame,
) -> None:
    cost = pd.Series({"S1": 10.0, "S2": 1.0, "S3": 1.0, "S4": 1.0})
    result = inventory_record_accuracy(offsetting_counts, unit_cost=cost).iloc[0]
    # 10 units at 10.00 plus 20 units at 1.00.
    assert result["abs_variance_value"] == pytest.approx(120.0)


def test_pareto_ranks_by_value_when_prices_are_given(
    offsetting_counts: pd.DataFrame,
) -> None:
    cost = pd.Series({"S1": 10.0, "S2": 1.0, "S3": 1.0, "S4": 1.0})
    ranked = variance_pareto(offsetting_counts, unit_cost=cost, top=2)
    assert ranked.iloc[0]["sku"] == "S1"
    assert ranked.iloc[0]["share"] == pytest.approx(100 / 120)
    assert ranked["cumulative_share"].is_monotonic_increasing


def test_pareto_rejects_an_unknown_key(offsetting_counts: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="zone"):
        variance_pareto(offsetting_counts, key="zone")


def test_accuracy_ordering_follows_site_maturity(dataset) -> None:  # type: ignore[no-untyped-def]
    result = inventory_record_accuracy(dataset.cycle_counts).set_index("site")
    assert result.loc["CD-SP", "location_accuracy"] > result.loc["CD-PE", "location_accuracy"]
    assert (result["unit_accuracy_abs"] <= result["unit_accuracy_net"] + 1e-12).all()
