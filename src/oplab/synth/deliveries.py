"""Delivery stops for the routing problem.

Geography is generated rather than taken from a map, and two details of that generation carry
most of the realism:

**Customers are not uniformly spread.** A share sit in a dense urban core and the rest in a
sparse periphery, drawn from two different Rayleigh scales. Uniform customers make every
routing result look better than it is, because density is the single strongest driver of cost
per delivery and a uniform field has none of the concentration a real territory has.

**Territories differ by site.** Each site's radius is scaled by its ``territory_scale``, so a
metropolitan site serves a concentrated territory and a regional one serves a dispersed one.
That difference matters twice over: it is realistic, and it is the confound a benchmarking
comparison has to remove before ranking sites on cost per delivery. An earlier version of this
generator gave every site an identically shaped territory, which made the ranking
uncontaminated - and therefore left :mod:`oplab.benchmark` with nothing to demonstrate on.

**Straight-line distance is not road distance.** A circuity factor is applied to the Euclidean
distance. The value used here, 1.35, is in the range commonly quoted for urban road networks;
it is a stated assumption rather than a measurement, and any absolute cost from this model
inherits it.

Time windows matter more than they look. A material share of stops accept delivery only in the
morning or only in the afternoon, which fragments routes in a way capacity never does.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

SIZE_BAND_EDGES: tuple[int, ...] = (1, 2, 5)
SIZE_BAND_LABELS: tuple[str, ...] = ("1 line", "2-4 lines", "5+ lines")

# Channel. Delivering to a home costs far more per stop than delivering to a store, and the
# direct-to-consumer share grows through the year.
D2C_SHARE_START = 0.08
D2C_SHARE_END = 0.34
# Small orders are far more likely to be consumer orders, so the channel and the size profile
# are not independent - which is exactly why the two have to be segmented together.
D2C_SIZE_WEIGHT: dict[str, float] = {"1 line": 2.2, "2-4 lines": 1.0, "5+ lines": 0.3}

CIRCUITY_FACTOR = 1.35
URBAN_SHARE = 0.70
URBAN_SCALE_KM = 8.0
PERIPHERY_SCALE_KM = 34.0

SERVICE_BASE_MIN = 8.0
SERVICE_MIN_PER_100KG = 3.0

DAY_START_H = 8.0
DAY_END_H = 18.0
WINDOW_MIX: tuple[tuple[str, float, float, float], ...] = (
    # label, share, window start, window end
    ("all_day", 0.60, DAY_START_H, DAY_END_H),
    ("morning", 0.25, DAY_START_H, 12.0),
    ("afternoon", 0.15, 13.0, DAY_END_H),
)


def size_band(lines: pd.Series) -> pd.Series:
    """Bucket orders by line count.

    Cost per order is driven more by how many lines it carries than by anything else, so this
    is the segmentation a cost decomposition needs. Reporting cost per order across a shifting
    size profile without it attributes a mix movement to the operation.
    """
    bins = [*SIZE_BAND_EDGES, np.inf]
    return pd.cut(lines, bins=bins, labels=list(SIZE_BAND_LABELS), right=False).astype(str)


def generate_deliveries(
    cfg: SynthConfig,
    order_lines: pd.DataFrame,
    catalog: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Turn the order book into delivery stops: composition, channel, geography and windows.

    This runs **before** the cost ledger, and the ordering is the point. Freight cost depends
    on how far the delivery is, so the geography has to exist before the cost can be derived
    from it. An earlier version generated the ledger first and the geography afterwards, which
    left a freight cost that ignored distance and a distance that affected nothing - physically
    incoherent, and it made the geographic confound that :mod:`oplab.benchmark` exists to remove
    impossible to observe in this data.

    One order is one stop. Consolidating several orders going to the same customer into one
    stop would lower cost per delivery, and no such consolidation is modelled - so the figures
    here are an upper bound on cost and the routing has no easy win taken away from it.

    Args:
        cfg: Generation parameters.
        order_lines: The order book, supplying order composition.
        catalog: SKU master, for ``unit_weight_kg``.
        rng: Seeded generator.

    Returns:
        One row per order with ``order_id``, ``site``, ``order_date``, ``month``, ``lines``,
        ``units``, ``weight_kg``, ``size_band``, ``channel``, ``urban``, ``x_km`` and ``y_km``
        relative to the site depot, ``distance_km`` (road distance from the depot),
        ``service_min``, ``window_label``, ``window_start_h`` and ``window_end_h``.
    """
    if order_lines.empty:
        raise ValueError("order_lines is empty; generate it before deliveries")

    unit_weight = catalog.set_index("sku")["unit_weight_kg"]
    lines = order_lines.copy()
    lines["line_weight_kg"] = lines["qty_ordered"] * lines["sku"].map(unit_weight)

    orders = (
        lines.groupby("order_id", observed=True)
        .agg(
            site=("site", "first"),
            order_ts=("order_ts", "first"),
            lines=("line_id", "size"),
            units=("qty_ordered", "sum"),
            weight_kg=("line_weight_kg", "sum"),
        )
        .reset_index()
    )
    orders["order_date"] = orders["order_ts"].dt.normalize()
    orders["month"] = orders["order_ts"].dt.to_period("M").astype(str)
    orders["size_band"] = size_band(orders["lines"])

    n = len(orders)
    elapsed = (orders["order_ts"] - pd.Timestamp(cfg.start)).dt.days / max(cfg.days, 1)
    d2c_share = D2C_SHARE_START + (D2C_SHARE_END - D2C_SHARE_START) * elapsed
    size_weight = orders["size_band"].map(D2C_SIZE_WEIGHT).fillna(1.0).to_numpy(dtype=float)
    p_d2c = np.clip(d2c_share.to_numpy(dtype=float) * size_weight, 0.0, 0.95)
    orders["channel"] = np.where(rng.random(n) < p_d2c, "d2c", "store")

    # Consumer deliveries go to homes, which are more concentrated in the urban core than
    # store deliveries are.
    urban_probability = np.where(orders["channel"].to_numpy() == "d2c", 0.82, URBAN_SHARE)
    urban = rng.random(n) < urban_probability
    territory = (
        orders["site"].map({site.code: site.territory_scale for site in cfg.sites}).fillna(1.0)
    )
    scale = np.where(urban, URBAN_SCALE_KM, PERIPHERY_SCALE_KM) * territory.to_numpy(dtype=float)

    radius = rng.rayleigh(scale)
    angle = rng.uniform(0.0, 2.0 * np.pi, size=n)
    x_km = radius * np.cos(angle)
    y_km = radius * np.sin(angle)

    labels = [item[0] for item in WINDOW_MIX]
    shares = [item[1] for item in WINDOW_MIX]
    chosen = rng.choice(len(labels), size=n, p=shares)

    orders["urban"] = urban
    orders["x_km"] = np.round(x_km, 3)
    orders["y_km"] = np.round(y_km, 3)
    orders["distance_km"] = np.round(np.hypot(x_km, y_km) * CIRCUITY_FACTOR, 3)
    orders["weight_kg"] = orders["weight_kg"].round(3)
    orders["service_min"] = (
        SERVICE_BASE_MIN + SERVICE_MIN_PER_100KG * orders["weight_kg"] / 100.0
    ).round(2)
    orders["window_label"] = [labels[i] for i in chosen]
    orders["window_start_h"] = np.array([WINDOW_MIX[i][2] for i in chosen])
    orders["window_end_h"] = np.array([WINDOW_MIX[i][3] for i in chosen])

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
        "urban",
        "x_km",
        "y_km",
        "distance_km",
        "service_min",
        "window_label",
        "window_start_h",
        "window_end_h",
    ]
    return orders[columns].sort_values(["order_date", "site", "order_id"], ignore_index=True)
