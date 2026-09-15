"""SKU catalogue generation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

# Bulk density by category, in kg per cubic metre, used to derive storage cube from unit
# weight. These are shipped-case densities rather than material densities: electronics are
# dense as material and bulky as packed freight, which is why the value is the lowest here.
CATEGORY_DENSITY: dict[str, float] = {
    "dry_goods": 400.0,
    "beverages": 900.0,
    "personal_care": 350.0,
    "home_care": 500.0,
    "electronics": 200.0,
}
DEFAULT_DENSITY = 400.0


def generate_catalog(cfg: SynthConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Build the SKU master with a long-tailed demand profile.

    Base demand is drawn from a lognormal distribution, which reproduces the concentration
    seen in real assortments: a small share of items carries most of the volume, and a long
    tail of slow movers dominates the item count. A configurable share of the tail is flagged
    as intermittent, meaning demand arrives in sparse bursts rather than every day.

    Volatility is a separate axis. ``cfg.erratic_share`` of the assortment - drawn independently
    of volume - receives a low gamma dispersion shape, which turns its demand from Poisson into
    heavily overdispersed negative binomial. Without that independence every erratic item would
    also be a slow mover, and no classification could ever find a high-value unpredictable item.

    Returns:
        One row per SKU with columns ``sku``, ``category``, ``base_demand``, ``unit_cost``,
        ``unit_weight_kg``, ``units_per_case``, ``intermittent``, ``erratic``,
        ``dispersion_shape``, ``unit_volume_m3`` and ``case_volume_m3``.
    """
    n = cfg.n_skus
    skus = [f"SKU-{i:05d}" for i in range(1, n + 1)]

    base_demand = rng.lognormal(mean=1.1, sigma=1.35, size=n)
    # Slow movers are the natural candidates for intermittent behaviour, so rank the tail
    # rather than flagging items at random.
    tail_rank = np.argsort(np.argsort(base_demand))
    intermittent = tail_rank < int(round(cfg.intermittent_share * n))

    # Volatility is drawn independently of volume, so that a fast mover can be erratic and a
    # slow mover can be steady. The value is the shape of a gamma multiplier applied to demand
    # intensity, which makes daily demand negative binomial rather than Poisson: a low shape
    # means heavy overdispersion. See SynthConfig.erratic_share.
    erratic = rng.random(n) < cfg.erratic_share
    dispersion_shape = np.where(
        erratic, rng.uniform(0.6, 2.0, size=n), rng.uniform(20.0, 60.0, size=n)
    )

    unit_cost = np.round(rng.lognormal(mean=2.6, sigma=0.8, size=n), 2)

    catalog = pd.DataFrame(
        {
            "sku": skus,
            "category": rng.choice(list(cfg.categories), size=n),
            "base_demand": np.round(base_demand, 4),
            "unit_cost": unit_cost,
            "unit_weight_kg": np.round(rng.lognormal(mean=-0.3, sigma=0.7, size=n), 3),
            "units_per_case": rng.choice([6, 12, 24, 48], size=n, p=[0.2, 0.45, 0.25, 0.1]),
            "intermittent": intermittent,
            "erratic": erratic,
            "dispersion_shape": np.round(dispersion_shape, 3),
        }
    )

    # Cube is derived from weight and category density rather than drawn independently. That
    # keeps it physically coherent with the weight already generated, and - just as usefully -
    # consumes no random numbers, so adding it does not shift the generator stream and every
    # figure published from an earlier version of this dataset still reproduces.
    density = catalog["category"].map(CATEGORY_DENSITY).fillna(DEFAULT_DENSITY)
    catalog["unit_volume_m3"] = (catalog["unit_weight_kg"] / density).round(6)
    catalog["case_volume_m3"] = (catalog["unit_volume_m3"] * catalog["units_per_case"]).round(6)
    return catalog
