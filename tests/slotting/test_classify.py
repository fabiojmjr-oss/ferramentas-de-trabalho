"""ABC-XYZ classification behaviour."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.slotting import (
    POLICY_MATRIX,
    abc_classes,
    abc_xyz,
    cell_summary,
    demand_profile,
    policy_table,
    xyz_classes,
)


@pytest.fixture
def sparse_and_steady() -> pd.DataFrame:
    """Two items over eight weeks with the same total and opposite predictability.

    ``STEADY`` sells 10 units in every week. ``LUMPY`` sells 80 units in one week and nothing
    afterwards. Averaged over selling weeks only, both have a coefficient of variation of zero.
    Averaged over the full horizon, ``LUMPY`` is the most erratic item there is.
    """
    weeks = pd.date_range("2025-01-06", periods=8, freq="W-MON")
    rows = [{"date": week, "sku": "STEADY", "demand": 10} for week in weeks]
    rows.append({"date": weeks[0], "sku": "LUMPY", "demand": 80})
    return pd.DataFrame(rows)


def test_zero_periods_are_counted(sparse_and_steady: pd.DataFrame) -> None:
    profile = demand_profile(sparse_and_steady, period="W")

    assert profile.loc["STEADY", "total_units"] == 80
    assert profile.loc["LUMPY", "total_units"] == 80
    assert profile.loc["STEADY", "periods"] == profile.loc["LUMPY", "periods"] == 8
    assert profile.loc["STEADY", "active_periods"] == 8
    assert profile.loc["LUMPY", "active_periods"] == 1

    assert profile.loc["STEADY", "cv"] == pytest.approx(0.0)
    assert profile.loc["LUMPY", "cv"] > 2.0, (
        "an item selling once in eight weeks must not look stable; that is what happens when "
        "the zero periods are dropped"
    )


def test_the_two_items_land_in_opposite_xyz_classes(sparse_and_steady: pd.DataFrame) -> None:
    profile = demand_profile(sparse_and_steady, period="W")
    classes = xyz_classes(profile)
    assert classes["STEADY"] == "X"
    assert classes["LUMPY"] == "Z"


def test_annual_value_needs_a_catalogue(sparse_and_steady: pd.DataFrame) -> None:
    without = demand_profile(sparse_and_steady, period="W")
    assert "annual_value" not in without.columns

    catalog = pd.DataFrame({"sku": ["STEADY", "LUMPY"], "unit_cost": [1.0, 5.0]})
    with_value = demand_profile(sparse_and_steady, catalog, period="W")
    assert with_value.loc["LUMPY", "annual_value"] == pytest.approx(400.0)
    assert with_value.loc["STEADY", "annual_value"] == pytest.approx(80.0)


def test_demand_profile_validates_its_input() -> None:
    with pytest.raises(KeyError, match="date"):
        demand_profile(pd.DataFrame({"sku": ["A"], "demand": [1]}))
    with pytest.raises(ValueError, match="empty"):
        demand_profile(pd.DataFrame({"date": [], "sku": [], "demand": []}))


def test_abc_cuts_follow_cumulative_value() -> None:
    frame = pd.DataFrame({"annual_value": [100.0, 50.0, 20.0, 5.0, 1.0]})
    classes = abc_classes(frame)
    assert classes.iloc[0] == "A"
    assert classes.iloc[-1] == "C"
    assert set(classes) <= {"A", "B", "C"}


def test_abc_rejects_a_degenerate_or_missing_column() -> None:
    with pytest.raises(ValueError, match="positive value"):
        abc_classes(pd.DataFrame({"annual_value": [0.0, 0.0]}))
    with pytest.raises(KeyError, match="annual_value"):
        abc_classes(pd.DataFrame({"other": [1.0]}))
    with pytest.raises(ValueError, match="cuts must satisfy"):
        abc_classes(pd.DataFrame({"annual_value": [1.0]}), cuts=(0.95, 0.8))


def test_xyz_classes_handle_a_null_cv() -> None:
    frame = pd.DataFrame({"cv": [0.2, 0.8, 1.5, np.nan]})
    classes = xyz_classes(frame)
    assert list(classes) == ["X", "Y", "Z", "Z"]


def test_cell_summary_covers_every_occupied_cell(sparse_and_steady: pd.DataFrame) -> None:
    catalog = pd.DataFrame({"sku": ["STEADY", "LUMPY"], "unit_cost": [1.0, 5.0]})
    classified = abc_xyz(demand_profile(sparse_and_steady, catalog, period="W"))
    summary = cell_summary(classified)

    assert summary["skus"].sum() == 2
    assert summary["sku_share"].sum() == pytest.approx(1.0)
    assert summary["annual_value_share"].sum() == pytest.approx(1.0)
    assert set(summary["cell"]) == set(classified["cell"])


def test_cell_summary_requires_a_classified_frame() -> None:
    with pytest.raises(KeyError, match="'cell' column"):
        cell_summary(pd.DataFrame({"annual_value": [1.0]}))


def test_the_policy_matrix_covers_all_nine_cells() -> None:
    expected = {a + x for a in "ABC" for x in "XYZ"}
    assert set(POLICY_MATRIX) == expected

    table = policy_table()
    assert len(table) == 9
    for column in ("slotting", "replenishment", "forecasting", "counting", "rationale"):
        assert table[column].str.len().gt(0).all()


def test_the_az_cell_is_flagged_as_the_dangerous_one() -> None:
    assert "dangerous" in POLICY_MATRIX["AZ"].rationale
    assert "do not expect" in POLICY_MATRIX["AZ"].forecasting


def test_generated_assortment_reaches_the_high_value_erratic_cells(dataset) -> None:  # type: ignore[no-untyped-def]
    """The generator must be able to produce a high-value unpredictable item.

    An assortment where every erratic item is also a slow mover cannot produce an AY or AZ
    cell, and the most useful finding of an ABC-XYZ analysis becomes unobservable. This test
    guards the decoupling of volatility from volume in the generator.
    """
    profile = abc_xyz(demand_profile(dataset.demand, dataset.catalog, period="W"))
    a_class = profile.loc[profile["abc"] == "A"]
    non_stable_value = a_class.loc[a_class["xyz"] != "X", "annual_value"].sum()
    assert non_stable_value / a_class["annual_value"].sum() > 0.05
