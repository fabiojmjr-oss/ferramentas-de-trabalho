"""Producing a slotting plan, and comparing it honestly against the current one.

Two ranking rules are implemented, and the difference between them is the whole argument for
doing this properly.

**Popularity.** Rank by picks, closest face to the most-picked item. Intuitive, and right when
every item occupies the same space.

**Cube-per-order index.** Rank by space required divided by picks, closest face to the lowest
index. This is Heskett's rule, and it is the correct objective when items differ in size: a
bulky item that is picked often still consumes several near faces, and those faces would have
served more picks had they gone to compact items. Popularity ignores the opportunity cost of
the space; COI prices it.

A third rule is included for comparison and is not a recommendation: **ranking by revenue**.
It is what an ABC exercise produces when the classification is drawn on value and then handed
to the warehouse, and it is one of the most common ways a slotting project delivers nothing.
Value and pick frequency correlate, but not tightly enough - a high-price item ordered monthly
outranks a cheap one picked daily, and the picker pays for the difference every day.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .travel import DISTANCE_COL, travel_summary


def cube_per_order_index(picks: pd.Series, cube: pd.Series) -> pd.Series:
    """Heskett's cube-per-order index: space required per pick.

    Args:
        picks: Pick counts indexed by SKU.
        cube: Storage cube required per SKU, in cubic metres, indexed by SKU.

    Returns:
        Series indexed by SKU, ascending. A low index earns a near face.

    Raises:
        KeyError: If a SKU in ``picks`` has no cube.
        ValueError: If any pick count is not positive.
    """
    aligned = cube.reindex(picks.index)
    if aligned.isna().any():
        missing = aligned.index[aligned.isna()].tolist()
        raise KeyError(f"no storage cube for {len(missing)} SKU(s), e.g. {missing[:3]}")
    if (picks <= 0).any():
        raise ValueError("cube_per_order_index requires positive pick counts")
    return (aligned / picks).sort_values().rename("coi")


def reslot(
    ranking: pd.Series,
    layout: pd.DataFrame,
    cube: pd.Series | None = None,
    distance_col: str = DISTANCE_COL,
    ascending: bool = True,
) -> pd.DataFrame:
    """Assign SKUs to pick faces by walking two sorted lists.

    The best-ranked SKU takes the nearest face, the next takes the next, and so on. With one
    face per SKU and a single distance measure this greedy pass is optimal for the
    distance-weighted objective, which is why no solver is involved. It stops being optimal the
    moment a SKU can occupy several faces or a face can hold several SKUs - and that is the
    boundary where the routing and simulation tools of a later wave take over.

    Args:
        ranking: Ranking key per SKU. Lower is better when ``ascending``.
        layout: Pick faces with ``location``, ``distance_col`` and optionally ``capacity_m3``.
        cube: Optional storage cube per SKU. When given, a SKU is never placed in a face whose
            ``capacity_m3`` cannot hold it.
        distance_col: Distance measure to rank faces on.
        ascending: Whether a low ranking value should get the near face.

    Returns:
        Frame with ``sku`` and ``location``, one row per SKU.

    Raises:
        ValueError: If there are fewer usable faces than SKUs.
    """
    if len(layout) < len(ranking):
        raise ValueError(
            f"{len(layout)} pick faces for {len(ranking)} SKUs; each SKU needs its own face"
        )

    order = ranking.sort_values(ascending=ascending)
    faces = layout.sort_values(distance_col, ignore_index=True)

    if cube is None:
        return pd.DataFrame(
            {"sku": order.index.to_numpy(), "location": faces["location"].to_numpy()[: len(order)]}
        )

    required = cube.reindex(order.index)
    if required.isna().any():
        missing = required.index[required.isna()].tolist()
        raise KeyError(f"no storage cube for {len(missing)} SKU(s), e.g. {missing[:3]}")
    if "capacity_m3" not in faces.columns:
        raise KeyError("layout must have a 'capacity_m3' column when cube is given")

    capacity = faces["capacity_m3"].to_numpy()
    locations = faces["location"].to_numpy()
    taken = np.zeros(len(faces), dtype=bool)

    chosen: list[str] = []
    for sku, needed in required.items():
        fits = np.flatnonzero((~taken) & (capacity >= needed))
        if fits.size == 0:
            raise ValueError(
                f"no free pick face can hold {sku} ({needed:.3f} m3); it needs bulk storage"
            )
        index = int(fits[0])
        taken[index] = True
        chosen.append(str(locations[index]))

    return pd.DataFrame({"sku": required.index.to_numpy(), "location": chosen})


def compare_strategies(
    picks: pd.Series,
    layout: pd.DataFrame,
    strategies: dict[str, pd.DataFrame],
    baseline: str,
    distance_col: str = DISTANCE_COL,
) -> pd.DataFrame:
    """Evaluate several slotting plans on the same pick profile.

    Args:
        picks: Pick counts indexed by SKU.
        layout: Pick faces.
        strategies: Named assignments, each a frame with ``sku`` and ``location``.
        baseline: Key in ``strategies`` to measure change against, normally the current state.
        distance_col: Distance measure to use.

    Returns:
        One row per strategy with the travel summary plus ``change_vs_baseline``, sorted best
        first. The percentage change is the reportable number; see :mod:`oplab.slotting.travel`
        for why the absolute metres are not.

    Raises:
        KeyError: If ``baseline`` is not among the strategies.
    """
    if baseline not in strategies:
        raise KeyError(f"baseline {baseline!r} is not among {sorted(strategies)}")

    rows = []
    for name, assignment in strategies.items():
        summary = travel_summary(picks, assignment, layout, distance_col)
        rows.append({"strategy": name, **summary.to_dict()})

    table = pd.DataFrame(rows).set_index("strategy")
    reference = float(np.asarray(table.loc[baseline, "weighted_distance_m"], dtype=float))
    table["change_vs_baseline"] = table["weighted_distance_m"] / reference - 1.0
    return table.sort_values("weighted_distance_m").reset_index()
