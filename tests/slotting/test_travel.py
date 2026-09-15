"""Travel measurement and re-slotting behaviour."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.slotting import (
    compare_strategies,
    cube_per_order_index,
    pick_counts,
    reslot,
    travel_by_class,
    travel_detail,
    travel_summary,
)


@pytest.fixture
def tiny_layout() -> pd.DataFrame:
    """Three faces at 1, 10 and 100 metres, all able to hold any of the test SKUs."""
    return pd.DataFrame(
        {
            "location": ["NEAR", "MID", "FAR"],
            "effective_distance_m": [1.0, 10.0, 100.0],
            "distance_m": [1.0, 10.0, 100.0],
            "capacity_m3": [1.0, 1.0, 1.0],
        }
    )


@pytest.fixture
def tiny_picks() -> pd.Series:
    return pd.Series({"FAST": 100, "MEDIUM": 10, "SLOW": 1}, name="picks")


def test_travel_detail_weights_distance_by_picks(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    assignment = pd.DataFrame(
        {"sku": ["FAST", "MEDIUM", "SLOW"], "location": ["NEAR", "MID", "FAR"]}
    )
    detail = travel_detail(tiny_picks, assignment, tiny_layout)

    assert detail.loc["FAST", "weighted_distance_m"] == pytest.approx(100.0)
    assert detail.loc["MEDIUM", "weighted_distance_m"] == pytest.approx(100.0)
    assert detail.loc["SLOW", "weighted_distance_m"] == pytest.approx(100.0)


def test_the_worst_possible_assignment_costs_far_more(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    best = pd.DataFrame({"sku": ["FAST", "MEDIUM", "SLOW"], "location": ["NEAR", "MID", "FAR"]})
    worst = pd.DataFrame({"sku": ["FAST", "MEDIUM", "SLOW"], "location": ["FAR", "MID", "NEAR"]})

    # 100x1 + 10x10 + 1x100 = 300 against 100x100 + 10x10 + 1x1 = 10101.
    assert travel_summary(tiny_picks, best, tiny_layout)["weighted_distance_m"] == pytest.approx(
        300.0
    )
    assert travel_summary(tiny_picks, worst, tiny_layout)["weighted_distance_m"] == pytest.approx(
        10101.0
    )


def test_percentiles_are_weighted_by_picks(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    best = pd.DataFrame({"sku": ["FAST", "MEDIUM", "SLOW"], "location": ["NEAR", "MID", "FAR"]})
    summary = travel_summary(tiny_picks, best, tiny_layout)

    assert summary["picks"] == 111
    assert summary["mean_distance_per_pick_m"] == pytest.approx(300 / 111)
    # 90% of the 111 picks are on the near face, so the 90th percentile must be low.
    assert summary["p90_distance_per_pick_m"] == pytest.approx(1.0)


def test_a_sku_with_picks_but_no_location_is_an_error(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    partial = pd.DataFrame({"sku": ["FAST", "MEDIUM"], "location": ["NEAR", "MID"]})
    with pytest.raises(KeyError, match="picks but no location"):
        travel_detail(tiny_picks, partial, tiny_layout)


def test_an_assignment_to_an_unknown_location_is_an_error(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    assignment = pd.DataFrame(
        {"sku": ["FAST", "MEDIUM", "SLOW"], "location": ["NEAR", "MID", "GHOST"]}
    )
    with pytest.raises(KeyError, match="not in the layout"):
        travel_detail(tiny_picks, assignment, tiny_layout)


def test_stockout_lines_are_not_picks() -> None:
    lines = pd.DataFrame(
        {
            "sku": ["A", "A", "B"],
            "site": ["CD-SP", "CD-SP", "CD-SP"],
            "qty_shipped": [5, 0, 3],
        }
    )
    picks = pick_counts(lines)
    assert picks["A"] == 1, "a line that never shipped costs service, not travel"
    assert picks["B"] == 1


def test_pick_counts_filter_by_site() -> None:
    lines = pd.DataFrame({"sku": ["A", "B"], "site": ["CD-SP", "CD-RJ"], "qty_shipped": [1, 1]})
    assert list(pick_counts(lines, site="CD-SP").index) == ["A"]
    with pytest.raises(KeyError, match="no order lines for site"):
        pick_counts(lines, site="CD-XX")


def test_travel_by_class_exposes_badly_placed_fast_movers(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    assignment = pd.DataFrame(
        {"sku": ["FAST", "MEDIUM", "SLOW"], "location": ["FAR", "MID", "NEAR"]}
    )
    classes = pd.Series({"FAST": "A", "MEDIUM": "B", "SLOW": "C"})
    by_class = travel_by_class(tiny_picks, assignment, tiny_layout, classes).set_index("class")

    assert by_class.loc["A", "mean_distance_per_pick_m"] == pytest.approx(100.0)
    assert by_class.loc["C", "mean_distance_per_pick_m"] == pytest.approx(1.0)
    assert by_class["pick_share"].sum() == pytest.approx(1.0)


def test_cube_per_order_index_prices_the_space() -> None:
    picks = pd.Series({"BULKY": 100, "COMPACT": 100})
    cube = pd.Series({"BULKY": 1.0, "COMPACT": 0.1})
    coi = cube_per_order_index(picks, cube)

    assert list(coi.index) == ["COMPACT", "BULKY"], "equal picks, so the compact item wins"
    assert coi["COMPACT"] == pytest.approx(0.001)


def test_cube_per_order_index_validates_its_input() -> None:
    with pytest.raises(KeyError, match="no storage cube"):
        cube_per_order_index(pd.Series({"A": 1}), pd.Series({"B": 1.0}))
    with pytest.raises(ValueError, match="positive pick counts"):
        cube_per_order_index(pd.Series({"A": 0}), pd.Series({"A": 1.0}))


def test_reslot_walks_both_sorted_lists(tiny_picks: pd.Series, tiny_layout: pd.DataFrame) -> None:
    plan = reslot(-tiny_picks, tiny_layout).set_index("sku")
    assert plan.loc["FAST", "location"] == "NEAR"
    assert plan.loc["SLOW", "location"] == "FAR"


def test_reslot_respects_face_capacity(tiny_picks: pd.Series) -> None:
    layout = pd.DataFrame(
        {
            "location": ["NEAR_SMALL", "FAR_BIG"],
            "effective_distance_m": [1.0, 100.0],
            "capacity_m3": [0.2, 2.0],
        }
    )
    picks = pd.Series({"FAST_BULKY": 100, "SLOW_COMPACT": 1})
    cube = pd.Series({"FAST_BULKY": 1.5, "SLOW_COMPACT": 0.1})

    plan = reslot(-picks, layout, cube=cube).set_index("sku")
    assert plan.loc["FAST_BULKY", "location"] == "FAR_BIG", "it does not fit the near face"
    assert plan.loc["SLOW_COMPACT", "location"] == "NEAR_SMALL"


def test_reslot_refuses_an_item_that_fits_nowhere(tiny_layout: pd.DataFrame) -> None:
    picks = pd.Series({"HUGE": 10})
    cube = pd.Series({"HUGE": 99.0})
    with pytest.raises(ValueError, match="bulk storage"):
        reslot(-picks, tiny_layout, cube=cube)


def test_reslot_refuses_an_undersized_layout(tiny_picks: pd.Series) -> None:
    layout = pd.DataFrame(
        {"location": ["ONLY"], "effective_distance_m": [1.0], "capacity_m3": [1.0]}
    )
    with pytest.raises(ValueError, match="each SKU needs its own face"):
        reslot(-tiny_picks, layout)


def test_popularity_is_optimal_when_every_face_is_the_same_size(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    """With one face per SKU and uniform capacity, ranking by picks cannot be beaten.

    Every SKU consumes exactly one face, so cube carries no information about the objective and
    the cube-per-order index can only add noise. This is why the module reports the comparison
    rather than asserting that the more sophisticated rule wins.
    """
    cube = pd.Series({"FAST": 0.9, "MEDIUM": 0.1, "SLOW": 0.1})
    strategies = {
        "popularity": reslot(-tiny_picks, tiny_layout),
        "coi": reslot(cube_per_order_index(tiny_picks, cube), tiny_layout),
    }
    table = compare_strategies(
        tiny_picks, tiny_layout, strategies, baseline="popularity"
    ).set_index("strategy")

    assert table.loc["popularity", "weighted_distance_m"] <= table.loc["coi", "weighted_distance_m"]


def test_compare_strategies_reports_change_against_the_named_baseline(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    strategies = {
        "current": pd.DataFrame(
            {"sku": ["FAST", "MEDIUM", "SLOW"], "location": ["FAR", "MID", "NEAR"]}
        ),
        "reslotted": reslot(-tiny_picks, tiny_layout),
    }
    table = compare_strategies(tiny_picks, tiny_layout, strategies, baseline="current").set_index(
        "strategy"
    )

    assert table.loc["current", "change_vs_baseline"] == pytest.approx(0.0)
    assert table.loc["reslotted", "change_vs_baseline"] == pytest.approx(300 / 10101 - 1)
    assert table.index[0] == "reslotted", "best plan first"


def test_compare_strategies_requires_a_known_baseline(
    tiny_picks: pd.Series, tiny_layout: pd.DataFrame
) -> None:
    with pytest.raises(KeyError, match="is not among"):
        compare_strategies(tiny_picks, tiny_layout, {"a": pd.DataFrame()}, baseline="missing")


def test_reslotting_the_generated_warehouse_beats_random_placement(dataset) -> None:  # type: ignore[no-untyped-def]
    picks = pick_counts(dataset.order_lines, site="CD-SP")
    cube = dataset.catalog.set_index("sku")["case_volume_m3"]
    strategies = {
        "current": dataset.assignment,
        "popularity": reslot(-picks, dataset.layout, cube=cube),
    }
    table = compare_strategies(picks, dataset.layout, strategies, baseline="current").set_index(
        "strategy"
    )

    assert table.loc["popularity", "change_vs_baseline"] < -0.4
