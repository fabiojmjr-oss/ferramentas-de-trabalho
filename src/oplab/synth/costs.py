"""An operating cost ledger, one row per order.

The ledger exists so that a cost variance has something real to explain. Three movements are
built into it on purpose, because each one is a different conversation:

* **A rate movement.** A fuel index rises through the year, lifting freight per kilogram
  everywhere. Nobody in the operation did anything wrong.
* **A local rate movement.** Handling cost per line rises at one site only. Somebody did.
* **A mix movement.** The direct-to-consumer share grows from 8% to 34% through the year, and
  delivering to a home costs nearly twice as much per stop as delivering to a store. Average
  cost per order rises without a single rate rising.

A decomposition that cannot separate those three is worse than useless in a performance review,
because the room will attribute all of it to whoever owns the last one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

SIZE_BAND_EDGES: tuple[int, ...] = (1, 2, 5)
SIZE_BAND_LABELS: tuple[str, ...] = ("1 line", "2-4 lines", "5+ lines")

# Freight per order: a fixed stop cost plus a rate per kilogram, both by site. Remote sites pay
# more of each, which is why cost per order is not comparable across the network untreated.
SITE_STOP_COST_BRL: dict[str, float] = {
    "CD-SP": 18.0,
    "CD-RJ": 26.0,
    "CD-PE": 41.0,
    "CD-RS": 34.0,
}
SITE_FREIGHT_PER_KG: dict[str, float] = {
    "CD-SP": 1.15,
    "CD-RJ": 1.60,
    "CD-PE": 2.40,
    "CD-RS": 2.05,
}
DEFAULT_STOP_COST_BRL = 25.0
DEFAULT_FREIGHT_PER_KG = 1.60

# Channel. Delivering to a home costs far more per stop than delivering to a store, and the
# direct-to-consumer share grows through the year. This is the movement that makes a cost
# decomposition worth running: average cost per order rises without any rate rising, because
# the mix moved. Attributing it to the warehouse is the classic mistake, and it is a network
# and commercial decision rather than an operational failure.
D2C_STOP_COST_MULTIPLIER = 1.95
D2C_SHARE_START = 0.08
D2C_SHARE_END = 0.34
# Small orders are far more likely to be consumer orders, so the channel and the size profile
# are not independent - which is exactly why the two have to be segmented together.
D2C_SIZE_WEIGHT: dict[str, float] = {"1 line": 2.2, "2-4 lines": 1.0, "5+ lines": 0.3}

HANDLING_PER_LINE_BRL = 2.30
FUEL_INDEX_ANNUAL_RISE = 0.18
HANDLING_DRIFT_SITE = "CD-PE"
HANDLING_DRIFT_ANNUAL_RISE = 0.34


def size_band(lines: pd.Series) -> pd.Series:
    """Bucket orders by line count.

    Cost per order is driven more by how many lines it carries than by anything else, so this
    is the segmentation a cost decomposition needs. Reporting cost per order across a shifting
    size profile without it attributes a mix movement to the operation.
    """
    bins = [*SIZE_BAND_EDGES, np.inf]
    return pd.cut(lines, bins=bins, labels=list(SIZE_BAND_LABELS), right=False).astype(str)


def generate_cost_ledger(
    cfg: SynthConfig,
    order_lines: pd.DataFrame,
    catalog: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Build the per-order cost ledger.

    Args:
        cfg: Generation parameters, used for the horizon length.
        order_lines: Order lines, which supply the order composition and weight.
        catalog: SKU master, for ``unit_weight_kg``.
        rng: Seeded generator, used only for the idiosyncratic noise on each order.

    Returns:
        One row per order with ``order_id``, ``site``, ``order_date``, ``month``, ``lines``,
        ``units``, ``weight_kg``, ``size_band``, ``channel``, ``freight_brl``,
        ``handling_brl`` and ``total_brl``.
    """
    unit_weight = catalog.set_index("sku")["unit_weight_kg"]
    lines = order_lines.copy()
    lines["line_weight_kg"] = lines["qty_ordered"] * lines["sku"].map(unit_weight)

    orders = lines.groupby("order_id", observed=True).agg(
        site=("site", "first"),
        order_ts=("order_ts", "first"),
        lines=("line_id", "size"),
        units=("qty_ordered", "sum"),
        weight_kg=("line_weight_kg", "sum"),
    )
    orders = orders.reset_index()
    orders["order_date"] = orders["order_ts"].dt.normalize()
    orders["month"] = orders["order_ts"].dt.to_period("M").astype(str)
    orders["size_band"] = size_band(orders["lines"])

    elapsed = (orders["order_ts"] - pd.Timestamp(cfg.start)).dt.days / max(cfg.days, 1)
    fuel_index = 1.0 + FUEL_INDEX_ANNUAL_RISE * elapsed

    d2c_share = D2C_SHARE_START + (D2C_SHARE_END - D2C_SHARE_START) * elapsed
    size_weight = orders["size_band"].map(D2C_SIZE_WEIGHT).fillna(1.0).to_numpy(dtype=float)
    p_d2c = np.clip(d2c_share.to_numpy(dtype=float) * size_weight, 0.0, 0.95)
    orders["channel"] = np.where(rng.random(len(orders)) < p_d2c, "d2c", "store")

    # Rate lookups drop to numpy: these are per-row constants, not aligned series, and keeping
    # them as arrays makes the arithmetic below unambiguous.
    stop_cost = (
        orders["site"].map(SITE_STOP_COST_BRL).fillna(DEFAULT_STOP_COST_BRL).to_numpy(dtype=float)
    )
    stop_cost = stop_cost * np.where(
        orders["channel"].to_numpy() == "d2c", D2C_STOP_COST_MULTIPLIER, 1.0
    )
    per_kg = (
        orders["site"].map(SITE_FREIGHT_PER_KG).fillna(DEFAULT_FREIGHT_PER_KG).to_numpy(dtype=float)
    )

    # Idiosyncratic cost noise: two orders of identical composition never cost exactly the same.
    noise = rng.lognormal(0.0, 0.12, size=len(orders))

    order_weight = orders["weight_kg"].to_numpy(dtype=float)
    orders["freight_brl"] = (
        (stop_cost + per_kg * order_weight) * fuel_index.to_numpy(dtype=float) * noise
    ).round(2)

    handling_rate = np.where(
        orders["site"].to_numpy() == HANDLING_DRIFT_SITE,
        HANDLING_PER_LINE_BRL * (1.0 + HANDLING_DRIFT_ANNUAL_RISE * elapsed.to_numpy()),
        HANDLING_PER_LINE_BRL,
    )
    orders["handling_brl"] = (orders["lines"].to_numpy(dtype=float) * handling_rate * noise).round(
        2
    )
    orders["total_brl"] = (orders["freight_brl"] + orders["handling_brl"]).round(2)

    columns = [
        "order_id",
        "site",
        "order_date",
        "month",
        "lines",
        "units",
        "weight_kg",
        "size_band",
        "channel",
        "freight_brl",
        "handling_brl",
        "total_brl",
    ]
    return orders[columns].sort_values(["order_date", "order_id"], ignore_index=True)
