"""An operating cost ledger, one row per order.

The ledger exists so that a cost variance has something real to explain, and it is derived from
the delivery table rather than generated beside it. That ordering matters: **freight cost
depends on how far the delivery is**, so the geography has to exist first. An earlier version
generated the ledger before the geography, which left a freight cost that ignored distance and
a distance that affected nothing - physically incoherent, and it hid the geographic confound a
benchmarking comparison has to remove.

Four movements are built in on purpose, because each one is a different conversation:

* **A rate movement.** A fuel index rises through the year, lifting the distance and weight
  components everywhere. Nobody in the operation did anything wrong.
* **A local rate movement.** Handling cost per line rises at one site only. Somebody did.
* **A channel mix movement.** The direct-to-consumer share grows from 8% to 34%, and a home
  delivery costs nearly twice as much per stop as a store delivery.
* **A geographic difference between sites.** Each site serves a territory of its own dispersion,
  so part of a remote site's cost per order is where its customers are rather than how it runs.

A decomposition that cannot separate those is worse than useless in a performance review,
because the room will attribute all of it to whoever owns the last one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

# Freight per order: a fixed stop cost by site, a network rate per kilometre, and a network
# rate per kilogram. The site differentiation sits in the stop cost - local labour and market -
# while distance and weight are paid at the same rate everywhere. That split is what makes the
# geographic part of a site's cost removable by standardisation and the rest attributable.
SITE_STOP_COST_BRL: dict[str, float] = {
    "CD-SP": 18.0,
    "CD-RJ": 24.0,
    "CD-PE": 33.0,
    "CD-RS": 28.0,
}
DEFAULT_STOP_COST_BRL = 25.0
FREIGHT_PER_KM_BRL = 1.20
FREIGHT_PER_KG_BRL = 0.45

D2C_STOP_COST_MULTIPLIER = 1.95

HANDLING_PER_LINE_BRL = 2.30
FUEL_INDEX_ANNUAL_RISE = 0.18
HANDLING_DRIFT_SITE = "CD-PE"
HANDLING_DRIFT_ANNUAL_RISE = 0.34


def generate_cost_ledger(
    cfg: SynthConfig,
    deliveries: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Derive the per-order cost ledger from the delivery table.

    Args:
        cfg: Generation parameters, used for the horizon length.
        deliveries: Delivery stops, supplying composition, channel and distance.
        rng: Seeded generator, used only for the idiosyncratic noise on each order.

    Returns:
        One row per order with ``order_id``, ``site``, ``order_date``, ``month``, ``lines``,
        ``units``, ``weight_kg``, ``distance_km``, ``size_band``, ``channel``, ``freight_brl``,
        ``handling_brl`` and ``total_brl``.
    """
    if deliveries.empty:
        raise ValueError("deliveries is empty; generate it before the cost ledger")

    orders = deliveries.copy()
    order_date = pd.to_datetime(orders["order_date"])
    elapsed = ((order_date - pd.Timestamp(cfg.start)).dt.days / max(cfg.days, 1)).to_numpy(
        dtype=float
    )
    fuel_index = 1.0 + FUEL_INDEX_ANNUAL_RISE * elapsed

    stop_cost = (
        orders["site"].map(SITE_STOP_COST_BRL).fillna(DEFAULT_STOP_COST_BRL).to_numpy(dtype=float)
    )
    stop_cost = stop_cost * np.where(
        orders["channel"].to_numpy() == "d2c", D2C_STOP_COST_MULTIPLIER, 1.0
    )

    # Idiosyncratic cost noise: two orders of identical composition never cost exactly the same.
    noise = rng.lognormal(0.0, 0.12, size=len(orders))

    distance = orders["distance_km"].to_numpy(dtype=float)
    weight = orders["weight_kg"].to_numpy(dtype=float)
    orders["freight_brl"] = (
        (stop_cost + FREIGHT_PER_KM_BRL * distance + FREIGHT_PER_KG_BRL * weight)
        * fuel_index
        * noise
    ).round(2)

    handling_rate = np.where(
        orders["site"].to_numpy() == HANDLING_DRIFT_SITE,
        HANDLING_PER_LINE_BRL * (1.0 + HANDLING_DRIFT_ANNUAL_RISE * elapsed),
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
        "distance_km",
        "size_band",
        "channel",
        "freight_brl",
        "handling_brl",
        "total_brl",
    ]
    return orders[columns].sort_values(["order_date", "order_id"], ignore_index=True)
