"""Measuring what the current slotting costs.

The objective used here is **distance-weighted picks**: the sum over pick faces of the number
of picks at that face times its distance from the dock. It is the standard slotting objective
and it is deliberately not a route.

That distinction matters for how a result may be quoted. The absolute figure is proportional to
real walking distance only under return routing, where a picker collects one line and comes
back; under batch picking with an S-shape or largest-gap route the constant of proportionality
changes and is not even constant across orders. **The percentage change between two slotting
plans is far more robust than either absolute value**, because the routing constant largely
cancels. So report the improvement as a percentage and treat the metres as an order of
magnitude, not as a savings figure to put in a business case.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

DISTANCE_COL = "effective_distance_m"


def pick_counts(
    order_lines: pd.DataFrame,
    site: str | None = None,
    qty_col: str = "qty_shipped",
) -> pd.Series:
    """Count picks per SKU from an order book.

    A line that never shipped is not a pick: a stockout costs service, not travel. Counting it
    as a pick inflates the apparent value of re-slotting the very items the warehouse could not
    supply.

    Args:
        order_lines: Order lines with ``sku`` and ``qty_shipped``.
        site: Optional site filter. Slotting is a site-level decision, so when the order book
            spans several sites, pass the one being slotted.
        qty_col: Column deciding whether the line was picked.

    Returns:
        Series of pick counts indexed by SKU, descending.

    Raises:
        KeyError: If a required column is missing, or ``site`` matches no rows.
    """
    for column in ("sku", qty_col):
        if column not in order_lines.columns:
            raise KeyError(f"order_lines has no column {column!r}")

    frame = order_lines
    if site is not None:
        if "site" not in frame.columns:
            raise KeyError("order_lines has no column 'site'")
        frame = frame.loc[frame["site"].astype(str) == site]
        if frame.empty:
            raise KeyError(f"no order lines for site {site!r}")

    picked = frame.loc[frame[qty_col] > 0]
    return picked.groupby("sku", observed=True).size().sort_values(ascending=False).rename("picks")


def travel_detail(
    picks: pd.Series,
    assignment: pd.DataFrame,
    layout: pd.DataFrame,
    distance_col: str = DISTANCE_COL,
) -> pd.DataFrame:
    """Join picks to locations and distances, one row per SKU.

    Args:
        picks: Pick counts indexed by SKU, from :func:`pick_counts`.
        assignment: Frame with ``sku`` and ``location``.
        layout: Frame with ``location`` and ``distance_col``.
        distance_col: Distance measure to use. ``effective_distance_m`` includes the vertical
            access penalty; ``distance_m`` is the horizontal walk only.

    Returns:
        Frame indexed by SKU with ``location``, ``picks``, the distance and
        ``weighted_distance_m``.

    Raises:
        KeyError: If a column is missing, or a SKU with picks has no location.
    """
    if "sku" not in assignment.columns or "location" not in assignment.columns:
        raise KeyError("assignment must have 'sku' and 'location' columns")
    if "location" not in layout.columns or distance_col not in layout.columns:
        raise KeyError(f"layout must have 'location' and {distance_col!r} columns")

    placed = assignment.merge(
        layout[["location", distance_col]], on="location", how="left", validate="many_to_one"
    )
    if placed[distance_col].isna().any():
        missing = placed.loc[placed[distance_col].isna(), "location"].unique()
        raise KeyError(f"{len(missing)} assigned location(s) are not in the layout: {missing[:3]}")

    detail = placed.set_index("sku").join(picks.rename("picks"), how="right")
    if detail["location"].isna().any():
        unplaced = detail.index[detail["location"].isna()].tolist()
        raise KeyError(f"{len(unplaced)} SKU(s) have picks but no location, e.g. {unplaced[:3]}")

    detail["picks"] = detail["picks"].astype(int)
    detail["weighted_distance_m"] = detail["picks"] * detail[distance_col]
    return detail.sort_values("weighted_distance_m", ascending=False)


def travel_summary(
    picks: pd.Series,
    assignment: pd.DataFrame,
    layout: pd.DataFrame,
    distance_col: str = DISTANCE_COL,
) -> pd.Series:
    """Headline travel figures for one slotting plan.

    Returns:
        Series with ``skus``, ``picks``, ``weighted_distance_m`` (the objective),
        ``mean_distance_per_pick_m`` and ``p90_distance_per_pick_m``. The mean is the figure to
        compare plans on; the 90th percentile shows whether the plan is carried by a
        well-placed majority while a minority of picks still walk the building.
    """
    detail = travel_detail(picks, assignment, layout, distance_col)
    total_picks = int(detail["picks"].sum())
    weighted = float(detail["weighted_distance_m"].sum())

    # Percentiles are over picks, not over SKUs: a face with a thousand picks must weigh a
    # thousand times more than a face with one.
    per_pick = pd.Series(np.repeat(detail[distance_col].to_numpy(), detail["picks"].to_numpy()))

    return pd.Series(
        {
            "skus": int(len(detail)),
            "picks": total_picks,
            "weighted_distance_m": weighted,
            "mean_distance_per_pick_m": weighted / total_picks if total_picks else float("nan"),
            "p90_distance_per_pick_m": float(per_pick.quantile(0.9))
            if total_picks
            else float("nan"),
        }
    )


def travel_by_class(
    picks: pd.Series,
    assignment: pd.DataFrame,
    layout: pd.DataFrame,
    classes: pd.Series,
    distance_col: str = DISTANCE_COL,
) -> pd.DataFrame:
    """Where each class of item currently sits.

    This is the diagnostic that starts the conversation. A well-slotted warehouse has its
    highest-pick class closest to the dock; if class A averages the same distance as class C,
    the assortment is effectively slotted at random however the classification is drawn.

    Args:
        picks: Pick counts indexed by SKU.
        assignment: Frame with ``sku`` and ``location``.
        layout: Frame with ``location`` and ``distance_col``.
        classes: Class per SKU, for example the ``abc`` column of a classified profile.
        distance_col: Distance measure to use.

    Returns:
        One row per class with ``skus``, ``picks``, ``pick_share``,
        ``mean_distance_per_pick_m`` and ``weighted_distance_m``, ordered by class label.
    """
    detail = travel_detail(picks, assignment, layout, distance_col)
    detail["class"] = classes.reindex(detail.index)
    if detail["class"].isna().any():
        missing = int(detail["class"].isna().sum())
        raise KeyError(f"{missing} SKU(s) with picks have no class")

    grouped = detail.groupby("class", observed=True)
    summary = grouped.agg(
        skus=("picks", "size"),
        picks=("picks", "sum"),
        weighted_distance_m=("weighted_distance_m", "sum"),
    )
    summary["pick_share"] = summary["picks"] / summary["picks"].sum()
    summary["mean_distance_per_pick_m"] = summary["weighted_distance_m"] / summary["picks"]
    ordered = ["skus", "picks", "pick_share", "mean_distance_per_pick_m", "weighted_distance_m"]
    return summary[ordered].sort_index().reset_index()
