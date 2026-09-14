"""Daily demand generation with weekly and annual seasonality."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

# Monday-to-Sunday multipliers. Outbound in consumer distribution peaks mid-week and
# collapses on Sunday; the profile is what makes a seasonal-naive baseline non-trivial.
WEEKDAY_FACTORS = np.array([1.05, 1.15, 1.20, 1.12, 0.95, 0.45, 0.08])


def _annual_factor(day_of_year: np.ndarray) -> np.ndarray:
    """Single-harmonic annual seasonality peaking in the fourth quarter."""
    phase = 2 * np.pi * (day_of_year - 320) / 365.25
    return 1.0 + 0.18 * np.cos(phase)


def generate_demand(
    cfg: SynthConfig, catalog: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Generate daily demand per site and SKU.

    The intensity of a Poisson draw is the product of four terms: the SKU base demand, the
    site scale, a weekday factor and an annual harmonic. Intermittent SKUs are additionally
    gated by a Bernoulli mask, and a small share of site-days receive a promotional multiplier.

    Returns:
        Long frame with columns ``date``, ``site``, ``sku`` and ``demand``, containing only
        rows where ``demand > 0``.
    """
    dates = pd.date_range(cfg.start, periods=cfg.days, freq="D")
    weekday = WEEKDAY_FACTORS[dates.dayofweek.to_numpy()]
    annual = _annual_factor(dates.dayofyear.to_numpy())
    day_factor = weekday * annual

    base = catalog["base_demand"].to_numpy()
    intermittent = catalog["intermittent"].to_numpy()
    # Sparse items are active on a minority of days; the activity rate itself varies by item.
    active_rate = np.where(intermittent, rng.uniform(0.05, 0.30, size=len(base)), 1.0)

    frames: list[pd.DataFrame] = []
    for profile in cfg.sites:
        promo = np.where(
            rng.random(cfg.days) < cfg.promo_rate,
            rng.uniform(1.8, 3.5, size=cfg.days),
            1.0,
        )
        intensity = np.outer(day_factor * promo, base * profile.demand_scale)
        counts = rng.poisson(intensity)
        counts *= rng.random(counts.shape) < active_rate

        nz_day, nz_sku = np.nonzero(counts)
        if nz_day.size == 0:
            continue
        frames.append(
            pd.DataFrame(
                {
                    "date": dates.to_numpy()[nz_day],
                    "site": profile.code,
                    "sku": catalog["sku"].to_numpy()[nz_sku],
                    "demand": counts[nz_day, nz_sku],
                }
            )
        )

    if not frames:
        return pd.DataFrame(columns=["date", "site", "sku", "demand"])

    demand = pd.concat(frames, ignore_index=True)
    demand["site"] = demand["site"].astype("category")
    return demand.sort_values(["date", "site", "sku"], ignore_index=True)
