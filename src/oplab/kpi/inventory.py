"""Inventory record accuracy.

Accuracy is quoted as a single percentage far more often than it is defined. Three
definitions are in common use, they are computed from the same count sheet, and they can
differ by more than ten points:

* **Location accuracy** - the share of counted locations whose record matched exactly. This is
  the operational definition: it answers "how often can a picker trust the system".
* **Unit accuracy (absolute)** - one minus total absolute discrepancy over total system
  quantity. This is the financial definition.
* **Unit accuracy (net)** - the same ratio using the signed discrepancy. Overs cancel unders,
  so it flatters the result and can report high accuracy on an inventory that is wrong in
  every location. It is included here only so that it can be recognised and rejected.

Reporting the net figure without the absolute one is the most common way an inventory
indicator is made to look good, and it is usually done without any intent to mislead.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .schemas import CYCLE_COUNTS


def inventory_record_accuracy(
    counts: pd.DataFrame,
    by: str | Sequence[str] | None = "site",
    unit_cost: pd.Series | None = None,
    tolerance_units: int = 0,
) -> pd.DataFrame:
    """Compute the three accuracy definitions side by side.

    Args:
        counts: Cycle counts satisfying the ``cycle_counts`` contract.
        by: Optional grouping column(s). Defaults to ``"site"``.
        unit_cost: Optional cost per SKU, indexed by SKU. When provided, the absolute value of
            the discrepancy is reported so that the result can be reconciled with the ledger.
        tolerance_units: Absolute discrepancy, in units, still counted as a match. Use it only
            where a contract or a weighing tolerance justifies it.

    Returns:
        One row per group with ``locations_counted``, ``location_accuracy``,
        ``unit_accuracy_abs``, ``unit_accuracy_net``, ``system_units``, ``abs_variance_units``
        and, when ``unit_cost`` is given, ``abs_variance_value``.
    """
    if tolerance_units < 0:
        raise ValueError("tolerance_units cannot be negative")
    subset = ["location", "system_qty", "counted_qty"]
    if by is not None:
        subset += [by] if isinstance(by, str) else list(by)
    CYCLE_COUNTS.validate(counts, subset=subset)

    frame = counts.copy()
    frame["variance"] = frame["counted_qty"] - frame["system_qty"]
    frame["abs_variance"] = frame["variance"].abs()
    frame["match"] = frame["abs_variance"] <= tolerance_units

    if unit_cost is not None:
        if "sku" not in frame.columns:
            raise KeyError("unit_cost requires a 'sku' column in counts")
        frame["abs_variance_value"] = frame["abs_variance"] * frame["sku"].map(unit_cost)
        if frame["abs_variance_value"].isna().any():
            missing = int(frame["abs_variance_value"].isna().sum())
            raise KeyError(f"unit_cost is missing a price for {missing} counted row(s)")

    # Aggregate the three sums the ratios are built from, then derive the ratios once, so the
    # grouped and ungrouped paths cannot drift apart.
    aggregations: dict[str, tuple[str, str]] = {
        "locations_counted": ("match", "size"),
        "location_accuracy": ("match", "mean"),
        "system_units": ("system_qty", "sum"),
        "abs_variance_units": ("abs_variance", "sum"),
        "net_variance_units": ("variance", "sum"),
    }
    if unit_cost is not None:
        aggregations["abs_variance_value"] = ("abs_variance_value", "sum")

    keys = None if by is None else ([by] if isinstance(by, str) else list(by))
    if keys is None:
        totals = pd.DataFrame(
            [{name: frame[column].agg(how) for name, (column, how) in aggregations.items()}]
        )
    else:
        totals = frame.groupby(keys, observed=True).agg(**aggregations).reset_index()

    system_units = totals["system_units"].replace(0, np.nan)
    totals["unit_accuracy_abs"] = 1.0 - totals["abs_variance_units"] / system_units
    totals["unit_accuracy_net"] = 1.0 - totals["net_variance_units"].abs() / system_units
    totals["locations_counted"] = totals["locations_counted"].astype(int)

    ordered = [
        "locations_counted",
        "location_accuracy",
        "unit_accuracy_abs",
        "unit_accuracy_net",
        "system_units",
        "abs_variance_units",
        "net_variance_units",
    ]
    if unit_cost is not None:
        ordered.append("abs_variance_value")
    columns = ([] if keys is None else keys) + ordered

    if keys is None:
        return totals[columns]
    return totals[columns].sort_values("location_accuracy", ascending=False, ignore_index=True)


def variance_pareto(
    counts: pd.DataFrame,
    key: str = "sku",
    unit_cost: pd.Series | None = None,
    top: int = 20,
) -> pd.DataFrame:
    """Rank the largest contributors to absolute inventory discrepancy.

    Counting effort is finite, so it should be aimed at the items that actually move the
    balance. Ranking by value rather than units is what turns a count programme from a
    compliance exercise into a cost intervention.

    Args:
        counts: Cycle counts satisfying the ``cycle_counts`` contract.
        key: Column to rank by, typically ``"sku"`` or ``"location"``.
        unit_cost: Optional cost per SKU, indexed by SKU. When given, the ranking is by value.
        top: Number of rows to return.

    Returns:
        The top contributors with their absolute variance and cumulative share of the total.
    """
    if key not in counts.columns:
        raise KeyError(f"counts has no column {key!r}")
    if top < 1:
        raise ValueError("top must be positive")

    frame = counts.copy()
    frame["abs_variance"] = (frame["counted_qty"] - frame["system_qty"]).abs()
    measure = "abs_variance"
    if unit_cost is not None:
        frame["abs_variance_value"] = frame["abs_variance"] * frame["sku"].map(unit_cost)
        measure = "abs_variance_value"

    ranked = (
        frame.groupby(key, observed=True)[measure]
        .sum()
        .sort_values(ascending=False)
        .to_frame()
        .reset_index()
    )
    total = ranked[measure].sum()
    ranked["share"] = ranked[measure] / total if total else np.nan
    ranked["cumulative_share"] = ranked["share"].cumsum()
    return ranked.head(top)
