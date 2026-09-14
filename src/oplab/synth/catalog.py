"""SKU catalogue generation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig


def generate_catalog(cfg: SynthConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Build the SKU master with a long-tailed demand profile.

    Base demand is drawn from a lognormal distribution, which reproduces the concentration
    seen in real assortments: a small share of items carries most of the volume, and a long
    tail of slow movers dominates the item count. A configurable share of the tail is flagged
    as intermittent, meaning demand arrives in sparse bursts rather than every day.

    Returns:
        One row per SKU with columns ``sku``, ``category``, ``base_demand``, ``unit_cost``,
        ``unit_weight_kg``, ``units_per_case`` and ``intermittent``.
    """
    n = cfg.n_skus
    skus = [f"SKU-{i:05d}" for i in range(1, n + 1)]

    base_demand = rng.lognormal(mean=1.1, sigma=1.35, size=n)
    # Slow movers are the natural candidates for intermittent behaviour, so rank the tail
    # rather than flagging items at random.
    tail_rank = np.argsort(np.argsort(base_demand))
    intermittent = tail_rank < int(round(cfg.intermittent_share * n))

    unit_cost = np.round(rng.lognormal(mean=2.6, sigma=0.8, size=n), 2)

    return pd.DataFrame(
        {
            "sku": skus,
            "category": rng.choice(list(cfg.categories), size=n),
            "base_demand": np.round(base_demand, 4),
            "unit_cost": unit_cost,
            "unit_weight_kg": np.round(rng.lognormal(mean=-0.3, sigma=0.7, size=n), 3),
            "units_per_case": rng.choice([6, 12, 24, 48], size=n, p=[0.2, 0.45, 0.25, 0.1]),
            "intermittent": intermittent,
        }
    )


def abc_classes(
    catalog: pd.DataFrame,
    value_col: str = "annual_value",
    cuts: tuple[float, float] = (0.8, 0.95),
) -> pd.Series:
    """Assign ABC classes by cumulative share of a value column.

    Args:
        catalog: Frame containing ``value_col``.
        value_col: Column holding the value to concentrate on (revenue, cost, volume).
        cuts: Cumulative share boundaries between A/B and B/C.

    Returns:
        Series of classes ``"A"``, ``"B"`` or ``"C"`` aligned to ``catalog.index``.
    """
    if value_col not in catalog.columns:
        raise KeyError(f"catalog has no column {value_col!r}")
    lo, hi = cuts
    if not 0 < lo < hi < 1:
        raise ValueError("cuts must satisfy 0 < lo < hi < 1")

    ordered = catalog[value_col].sort_values(ascending=False)
    total = ordered.sum()
    if total <= 0:
        raise ValueError(f"{value_col!r} must sum to a positive value")
    cumulative = ordered.cumsum() / total

    classes = pd.Series("C", index=ordered.index, dtype="object")
    classes[cumulative <= hi] = "B"
    classes[cumulative <= lo] = "A"
    return classes.reindex(catalog.index)
