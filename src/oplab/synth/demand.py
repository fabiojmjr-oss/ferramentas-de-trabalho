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

    The intensity is the product of the SKU base demand, the site scale, a weekday factor, an
    annual harmonic, and a per-SKU gamma shock whose shape comes from the catalogue. The gamma
    layer makes demand negative binomial rather than Poisson, so volatility varies across items
    independently of their volume. Intermittent SKUs are additionally gated by a Bernoulli mask,
    and a small share of site-days receive a promotional multiplier.

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
    shape = catalog["dispersion_shape"].to_numpy()
    # Sparse items are active on a minority of days; the activity rate itself varies by item.
    active_rate = np.where(intermittent, rng.uniform(0.05, 0.30, size=len(base)), 1.0)

    frames: list[pd.DataFrame] = []
    for profile in cfg.sites:
        promo = np.where(
            rng.random(cfg.days) < cfg.promo_rate,
            rng.uniform(1.8, 3.5, size=cfg.days),
            1.0,
        )
        # A gamma multiplier with mean one and shape from the catalogue turns the Poisson draw
        # into a negative binomial one. Items with a low shape become genuinely erratic, which
        # is what gives the XYZ axis of a classification something to separate.
        #
        # The shock is drawn per week and held across the days inside it, not redrawn daily.
        # That is both more realistic - a promotion or a project order runs for days, not for
        # an afternoon - and statistically necessary: independent daily shocks average out
        # under weekly aggregation, shrinking the coefficient of variation by the square root
        # of seven and hiding exactly the volatility the model is trying to create.
        n_weeks = int(np.ceil(cfg.days / 7))
        weekly_shock = rng.gamma(shape=shape, scale=1.0 / shape, size=(n_weeks, len(base)))
        shock = np.repeat(weekly_shock, 7, axis=0)[: cfg.days]
        intensity = np.outer(day_factor * promo, base * profile.demand_scale) * shock
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
