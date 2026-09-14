"""ABC-XYZ classification and the policy that follows from it.

ABC ranks items by how much they matter; XYZ ranks them by how predictable they are. Neither
is useful alone. An A item with erratic demand and an A item with stable demand carry the same
revenue and need opposite policies: the first needs availability bought with inventory or
flexibility, the second needs a tight forecast and a thin buffer. Classifying on value only
collapses that distinction and is the reason so many ABC exercises change nothing.

Two implementation details decide whether the XYZ axis means anything:

**Zero periods count.** The coefficient of variation must be computed over every period in the
horizon, including the periods with no demand. An item selling 40 units once a quarter has a CV
of zero if only its selling weeks are averaged, and lands in X - the most stable class - when
it is in fact the least predictable thing in the assortment. This module reindexes onto the
full period grid before computing anything.

**The cuts are conventions, not findings.** The defaults here (80% / 95% cumulative value, CV
of 0.5 and 1.0) are the common textbook values. They are a starting point for a conversation
about where the assortment actually breaks, not a result. Look at the distribution before
accepting them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

ABC_CUTS: tuple[float, float] = (0.8, 0.95)
XYZ_CUTS: tuple[float, float] = (0.5, 1.0)


def demand_profile(
    demand: pd.DataFrame,
    catalog: pd.DataFrame | None = None,
    period: str = "W",
    date_col: str = "date",
    sku_col: str = "sku",
    qty_col: str = "demand",
) -> pd.DataFrame:
    """Summarise demand per SKU over a regular period grid.

    Args:
        demand: Long demand frame holding only the periods where demand occurred.
        catalog: Optional SKU master. When it carries ``unit_cost``, annual value is computed.
        period: Pandas period alias to aggregate on, for example ``"W"`` or ``"ME"``.
        date_col: Date column in ``demand``.
        sku_col: SKU column in ``demand``.
        qty_col: Quantity column in ``demand``.

    Returns:
        One row per SKU with ``total_units``, ``periods`` (the number of periods in the whole
        horizon), ``active_periods`` (periods with demand), ``mean_per_period``,
        ``std_per_period``, ``cv`` and, when available, ``annual_value``.

    Raises:
        KeyError: If a named column is missing.
        ValueError: If ``demand`` is empty.
    """
    for column in (date_col, sku_col, qty_col):
        if column not in demand.columns:
            raise KeyError(f"demand has no column {column!r}")
    if demand.empty:
        raise ValueError("demand is empty")

    frame = demand[[date_col, sku_col, qty_col]].copy()
    frame["period"] = pd.to_datetime(frame[date_col]).dt.to_period(period)
    per_period = frame.groupby([sku_col, "period"], observed=True)[qty_col].sum()

    # The full grid is what makes a sparse item look sparse. Without it, a slow mover with one
    # large order per quarter is indistinguishable from a steady daily seller.
    all_periods = pd.period_range(
        frame["period"].min(), frame["period"].max(), freq=frame["period"].dt.freq
    )
    skus = per_period.index.get_level_values(sku_col).unique()
    grid = pd.MultiIndex.from_product([skus, all_periods], names=[sku_col, "period"])
    dense = per_period.reindex(grid, fill_value=0)

    grouped = dense.groupby(level=sku_col, observed=True)
    profile = pd.DataFrame(
        {
            "total_units": grouped.sum(),
            "periods": len(all_periods),
            "active_periods": grouped.apply(lambda s: int((s > 0).sum())),
            "mean_per_period": grouped.mean(),
            "std_per_period": grouped.std(ddof=1),
        }
    )
    profile["cv"] = (profile["std_per_period"] / profile["mean_per_period"]).replace(
        [np.inf, -np.inf], np.nan
    )

    if catalog is not None and "unit_cost" in catalog.columns:
        cost = catalog.set_index("sku")["unit_cost"]
        profile["annual_value"] = (profile["total_units"] * cost.reindex(profile.index)).round(2)

    return profile.reset_index().rename(columns={sku_col: "sku"}).set_index("sku")


def abc_classes(
    frame: pd.DataFrame,
    value_col: str = "annual_value",
    cuts: tuple[float, float] = ABC_CUTS,
) -> pd.Series:
    """Assign ABC classes by cumulative share of a value column.

    Args:
        frame: Frame containing ``value_col``.
        value_col: Column holding the value to concentrate on: revenue, cost, units or picks.
        cuts: Cumulative share boundaries between A/B and B/C.

    Returns:
        Series of ``"A"``, ``"B"`` or ``"C"`` aligned to ``frame.index``.

    Raises:
        KeyError: If ``value_col`` is absent.
        ValueError: If ``cuts`` are not ordered, or ``value_col`` does not sum to a positive
            value.
    """
    if value_col not in frame.columns:
        raise KeyError(f"frame has no column {value_col!r}")
    lo, hi = cuts
    if not 0 < lo < hi < 1:
        raise ValueError("cuts must satisfy 0 < lo < hi < 1")

    ordered = frame[value_col].sort_values(ascending=False)
    total = ordered.sum()
    if total <= 0:
        raise ValueError(f"{value_col!r} must sum to a positive value")
    cumulative = ordered.cumsum() / total

    classes = pd.Series("C", index=ordered.index, dtype="object")
    classes[cumulative <= hi] = "B"
    classes[cumulative <= lo] = "A"
    return classes.reindex(frame.index).rename("abc")


def xyz_classes(
    frame: pd.DataFrame,
    cv_col: str = "cv",
    cuts: tuple[float, float] = XYZ_CUTS,
) -> pd.Series:
    """Assign XYZ classes by coefficient of variation.

    ``X`` is stable, ``Y`` is variable, ``Z`` is erratic. A null CV - an item with no demand in
    the horizon - is classed ``Z``, since an item nobody ordered is not a predictable one.

    Args:
        frame: Frame containing ``cv_col``.
        cv_col: Column holding the coefficient of variation.
        cuts: Upper bound of X and upper bound of Y.

    Returns:
        Series of ``"X"``, ``"Y"`` or ``"Z"`` aligned to ``frame.index``.
    """
    if cv_col not in frame.columns:
        raise KeyError(f"frame has no column {cv_col!r}")
    lo, hi = cuts
    if not 0 < lo < hi:
        raise ValueError("cuts must satisfy 0 < lo < hi")

    cv = frame[cv_col]
    classes = pd.Series("Z", index=frame.index, dtype="object")
    classes[cv <= hi] = "Y"
    classes[cv <= lo] = "X"
    classes[cv.isna()] = "Z"
    return classes.rename("xyz")


def abc_xyz(
    profile: pd.DataFrame,
    value_col: str = "annual_value",
    cv_col: str = "cv",
    abc_cuts: tuple[float, float] = ABC_CUTS,
    xyz_cuts: tuple[float, float] = XYZ_CUTS,
) -> pd.DataFrame:
    """Add ``abc``, ``xyz`` and ``cell`` columns to a demand profile.

    Args:
        profile: Per-SKU profile, normally from :func:`demand_profile`.
        value_col: Column driving the ABC axis.
        cv_col: Column driving the XYZ axis.
        abc_cuts: Cumulative value boundaries.
        xyz_cuts: Coefficient of variation boundaries.

    Returns:
        ``profile`` with the three classification columns appended.
    """
    out = profile.copy()
    out["abc"] = abc_classes(out, value_col=value_col, cuts=abc_cuts)
    out["xyz"] = xyz_classes(out, cv_col=cv_col, cuts=xyz_cuts)
    out["cell"] = out["abc"] + out["xyz"]
    return out


def cell_summary(
    classified: pd.DataFrame,
    value_col: str = "annual_value",
    extra: Sequence[str] = (),
) -> pd.DataFrame:
    """Cross-tabulate the nine cells by item count and value share.

    This is the table that makes the classification actionable: it shows how much of the
    assortment sits in each cell and how much of the value rides on it. A large AZ cell is the
    finding - a material share of revenue on items nobody can forecast.

    Args:
        classified: Output of :func:`abc_xyz`.
        value_col: Column to share out across cells.
        extra: Additional numeric columns to sum per cell.

    Returns:
        One row per occupied cell with ``skus``, ``sku_share``, the value total and its share,
        plus any ``extra`` sums, ordered A to C then X to Z.
    """
    if "cell" not in classified.columns:
        raise KeyError("classified must contain a 'cell' column; run abc_xyz first")

    aggregations: dict[str, tuple[str, str]] = {"skus": ("cell", "size")}
    if value_col in classified.columns:
        aggregations[value_col] = (value_col, "sum")
    for column in extra:
        if column not in classified.columns:
            raise KeyError(f"classified has no column {column!r}")
        aggregations[column] = (column, "sum")

    summary = classified.groupby(["abc", "xyz"], observed=True).agg(**aggregations).reset_index()
    summary["sku_share"] = summary["skus"] / summary["skus"].sum()
    if value_col in summary.columns:
        total = summary[value_col].sum()
        summary[f"{value_col}_share"] = summary[value_col] / total if total else np.nan
    summary["cell"] = summary["abc"] + summary["xyz"]

    order = {c: i for i, c in enumerate("ABC")}, {c: i for i, c in enumerate("XYZ")}
    summary = summary.sort_values(
        by=["abc", "xyz"], key=lambda s: s.map(order[0] if s.name == "abc" else order[1])
    )
    front = ["cell", "abc", "xyz", "skus", "sku_share"]
    rest = [c for c in summary.columns if c not in front]
    return summary[front + rest].reset_index(drop=True)


@dataclass(frozen=True)
class CellPolicy:
    """The policy a cell implies, across the four decisions it actually drives.

    Attributes:
        slotting: Where the item belongs in the pick area.
        replenishment: Review and ordering policy.
        forecasting: What a forecast can and cannot be expected to do.
        counting: Cycle count frequency.
        rationale: Why, in one line.
    """

    slotting: str
    replenishment: str
    forecasting: str
    counting: str
    rationale: str


POLICY_MATRIX: dict[str, CellPolicy] = {
    "AX": CellPolicy(
        slotting="golden zone, closest faces",
        replenishment="continuous review, thin safety stock",
        forecasting="statistical forecast is reliable; hold a tight tolerance",
        counting="monthly",
        rationale="high value and predictable: the one cell where a thin buffer is safe",
    ),
    "AY": CellPolicy(
        slotting="golden zone",
        replenishment="continuous review, moderate safety stock",
        forecasting="statistical forecast plus a promotion and event overlay",
        counting="monthly",
        rationale="high value with real variability: buy availability with buffer, not with hope",
    ),
    "AZ": CellPolicy(
        slotting="forward area, accept the space cost",
        replenishment="target a service level explicitly; consider make-to-order or postponement",
        forecasting="do not expect a usable point forecast; plan the distribution, not the mean",
        counting="monthly",
        rationale="the dangerous cell: material revenue on demand nobody can predict",
    ),
    "BX": CellPolicy(
        slotting="mid zone",
        replenishment="periodic review, economic lot",
        forecasting="statistical forecast is adequate",
        counting="quarterly",
        rationale="steady middle: automate it and stop discussing it",
    ),
    "BY": CellPolicy(
        slotting="mid zone",
        replenishment="periodic review with a wider band",
        forecasting="statistical forecast with judgment override",
        counting="quarterly",
        rationale="moderate on both axes: the cell where policy beats attention",
    ),
    "BZ": CellPolicy(
        slotting="mid zone",
        replenishment="min-max with a wide band",
        forecasting="forecast unreliable; size the buffer from the demand distribution",
        counting="quarterly",
        rationale="erratic middle: manage by rule, not by plan",
    ),
    "CX": CellPolicy(
        slotting="far aisles, upper levels",
        replenishment="periodic review, large lot, low frequency",
        forecasting="a seasonal naive baseline is enough",
        counting="half-yearly",
        rationale="low value and predictable: minimise handling and attention",
    ),
    "CY": CellPolicy(
        slotting="far aisles, upper levels",
        replenishment="min-max",
        forecasting="a simple baseline is enough",
        counting="half-yearly",
        rationale="low value, some variability: cheap to be wrong",
    ),
    "CZ": CellPolicy(
        slotting="far aisles or bulk; candidate for delisting",
        replenishment="make-to-order, or stock a token quantity as a deliberate decision",
        forecasting="do not forecast; decide an availability rule",
        counting="half-yearly",
        rationale="the assortment tail: the question is whether to carry it at all",
    ),
}


def policy_table() -> pd.DataFrame:
    """The nine-cell policy matrix as a frame, ordered A to C then X to Z."""
    rows = [
        {"cell": cell, "abc": cell[0], "xyz": cell[1], **policy.__dict__}
        for cell, policy in POLICY_MATRIX.items()
    ]
    return pd.DataFrame(rows)
