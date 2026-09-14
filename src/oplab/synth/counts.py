"""Cycle count records for inventory record accuracy."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

LOCATIONS_PER_COUNT = 220
LARGE_ERROR_SHARE = 0.15


def generate_cycle_counts(
    cfg: SynthConfig, catalog: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Generate weekly cycle count records.

    Discrepancies are generated in both directions and with two magnitudes: many small
    picking errors and a minority of large errors from mis-receipts or wrong locations.
    The split matters because it separates the two accuracy definitions - counting locations
    that match, and counting units that match - which can differ by several points on the
    same physical inventory.

    Returns:
        One row per counted location with ``system_qty`` and ``counted_qty``.
    """
    count_dates = pd.date_range(cfg.start, periods=cfg.days, freq="D")
    count_dates = count_dates[count_dates.dayofweek == 2]  # Wednesday cycle counts
    if len(count_dates) == 0:
        raise ValueError("horizon contains no count day; increase days")

    frames: list[pd.DataFrame] = []
    for profile in cfg.sites:
        n_per_day = max(20, int(LOCATIONS_PER_COUNT * profile.demand_scale))
        total = n_per_day * len(count_dates)

        system_qty = np.maximum(1, rng.poisson(90, size=total))
        matches = rng.random(total) < profile.count_accuracy

        small_error = rng.integers(-3, 4, size=total)
        large_error = np.round(system_qty * rng.uniform(-0.45, 0.45, size=total)).astype(int)
        use_large = rng.random(total) < LARGE_ERROR_SHARE
        error = np.where(use_large, large_error, small_error)
        # A "mismatch" must actually differ; nudge zero errors away from zero.
        error = np.where(error == 0, rng.choice([-1, 1], size=total), error)
        error = np.where(matches, 0, error)

        aisle = rng.integers(1, 41, size=total)
        bay = rng.integers(1, 61, size=total)
        level = rng.integers(1, 6, size=total)

        frames.append(
            pd.DataFrame(
                {
                    "count_date": np.repeat(count_dates.to_numpy(), n_per_day),
                    "site": profile.code,
                    "location": [
                        f"{a:02d}-{b:02d}-{lv}" for a, b, lv in zip(aisle, bay, level, strict=True)
                    ],
                    "sku": rng.choice(catalog["sku"].to_numpy(), size=total),
                    "system_qty": system_qty,
                    "counted_qty": np.maximum(0, system_qty + error),
                }
            )
        )

    counts = pd.concat(frames, ignore_index=True)
    counts["count_id"] = [f"CC-{i:07d}" for i in range(1, len(counts) + 1)]
    cols = ["count_id", "count_date", "site", "location", "sku", "system_qty", "counted_qty"]
    return counts[cols].sort_values(["count_date", "site", "location"], ignore_index=True)
