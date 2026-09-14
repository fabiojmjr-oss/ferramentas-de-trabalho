"""Delivery stops for the routing problem.

Geography is generated rather than taken from a map, and two details of that generation carry
most of the realism:

**Customers are not uniformly spread.** A share sit in a dense urban core and the rest in a
sparse periphery, drawn from two different Rayleigh scales. Uniform customers make every
routing result look better than it is, because density is the single strongest driver of cost
per delivery and a uniform field has none of the concentration a real territory has.

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


def generate_deliveries(
    cfg: SynthConfig,
    cost_ledger: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Give every order a delivery location, a service time and a time window.

    One order is one stop. Consolidating several orders going to the same customer into one
    stop would lower cost per delivery, and no such consolidation is modelled - so the figures
    here are an upper bound on cost and the routing has no easy win taken away from it.

    Args:
        cfg: Generation parameters.
        cost_ledger: Per-order ledger, supplying site, date, weight and channel.
        rng: Seeded generator.

    Returns:
        One row per order with ``order_id``, ``site``, ``order_date``, ``channel``,
        ``x_km`` and ``y_km`` relative to the site depot, ``distance_km`` (road distance from
        the depot), ``weight_kg``, ``service_min``, ``window_label``, ``window_start_h`` and
        ``window_end_h``.
    """
    if cost_ledger.empty:
        raise ValueError("cost_ledger is empty; generate it before deliveries")

    n = len(cost_ledger)
    # Consumer deliveries go to homes, which are more concentrated in the urban core than
    # store deliveries are.
    urban_probability = np.where(cost_ledger["channel"].to_numpy() == "d2c", 0.82, URBAN_SHARE)
    urban = rng.random(n) < urban_probability
    scale = np.where(urban, URBAN_SCALE_KM, PERIPHERY_SCALE_KM)

    radius = rng.rayleigh(scale)
    angle = rng.uniform(0.0, 2.0 * np.pi, size=n)
    x_km = radius * np.cos(angle)
    y_km = radius * np.sin(angle)

    labels = [item[0] for item in WINDOW_MIX]
    shares = [item[1] for item in WINDOW_MIX]
    chosen = rng.choice(len(labels), size=n, p=shares)
    window_start = np.array([WINDOW_MIX[i][2] for i in chosen])
    window_end = np.array([WINDOW_MIX[i][3] for i in chosen])

    weight = cost_ledger["weight_kg"].to_numpy(dtype=float)
    service_min = SERVICE_BASE_MIN + SERVICE_MIN_PER_100KG * weight / 100.0

    deliveries = pd.DataFrame(
        {
            "order_id": cost_ledger["order_id"].to_numpy(),
            "site": cost_ledger["site"].to_numpy(),
            "order_date": cost_ledger["order_date"].to_numpy(),
            "channel": cost_ledger["channel"].to_numpy(),
            "urban": urban,
            "x_km": np.round(x_km, 3),
            "y_km": np.round(y_km, 3),
            "distance_km": np.round(np.hypot(x_km, y_km) * CIRCUITY_FACTOR, 3),
            "weight_kg": np.round(weight, 3),
            "service_min": np.round(service_min, 2),
            "window_label": [labels[i] for i in chosen],
            "window_start_h": window_start,
            "window_end_h": window_end,
        }
    )
    return deliveries.sort_values(["order_date", "site", "order_id"], ignore_index=True)
