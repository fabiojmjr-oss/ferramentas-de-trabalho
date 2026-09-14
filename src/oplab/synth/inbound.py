"""Inbound receipts, from gate arrival to put-away."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

# Arrival deviation profile per carrier: (systematic bias in minutes, dispersion in minutes,
# mean of the late tail in minutes). The profiles differ on purpose - a carrier indicator that
# ranks every carrier the same is not measuring anything.
CARRIER_PROFILES: dict[str, tuple[float, float, float]] = {
    "FROTA-PROPRIA": (-5.0, 18.0, 6.0),
    "TRANSP-A": (4.0, 26.0, 14.0),
    "TRANSP-B": (12.0, 38.0, 34.0),
    "TRANSP-C": (26.0, 55.0, 70.0),
}
CARRIER_MIX: tuple[float, ...] = (0.25, 0.30, 0.25, 0.20)
RECEIPTS_PER_DAY_PER_SCALE = 9.0
UNLOAD_MIN_PER_PALLET = 3.5


def generate_receipts(cfg: SynthConfig, rng: np.random.Generator) -> pd.DataFrame:
    """Generate inbound receipt events.

    Dock-to-stock is decomposed into the three intervals that are actually managed
    separately: dock waiting time, unloading, and put-away. Waiting time grows with the
    number of trucks booked on the same day, which is the congestion effect that a static
    capacity spreadsheet cannot show.

    Returns:
        One row per receipt with arrival, unload and put-away timestamps.
    """
    dates = pd.date_range(cfg.start, periods=cfg.days, freq="D")
    frames: list[pd.DataFrame] = []

    for profile in cfg.sites:
        daily = rng.poisson(RECEIPTS_PER_DAY_PER_SCALE * profile.demand_scale, size=cfg.days)
        # Inbound is scheduled on working days only.
        daily = np.where(dates.dayofweek.to_numpy() >= 5, 0, daily)
        total = int(daily.sum())
        if total == 0:
            continue

        day_index = np.repeat(np.arange(cfg.days), daily)
        load = daily[day_index]

        appointment_h = rng.integers(6, 19, size=total)
        appointment_ts = (
            dates.to_numpy()[day_index] + pd.to_timedelta(appointment_h, unit="h").to_numpy()
        )
        carriers = rng.choice(list(CARRIER_PROFILES), size=total, p=list(CARRIER_MIX))
        bias = np.array([CARRIER_PROFILES[c][0] for c in carriers])
        spread = np.array([CARRIER_PROFILES[c][1] for c in carriers])
        tail = np.array([CARRIER_PROFILES[c][2] for c in carriers])
        # Deviation is symmetric noise around a carrier-specific bias, plus a one-sided tail:
        # a truck can be an hour late far more easily than an hour early.
        deviation_min = np.round(rng.normal(bias, spread) + rng.exponential(tail, size=total))
        arrival_ts = appointment_ts + pd.to_timedelta(deviation_min, unit="m").to_numpy()

        congestion = load / max(1.0, RECEIPTS_PER_DAY_PER_SCALE * profile.demand_scale)
        dock_wait_min = np.round(
            rng.lognormal(np.log(20.0), 0.8, size=total) * np.power(congestion, 1.6)
        )
        unload_start_ts = arrival_ts + pd.to_timedelta(dock_wait_min, unit="m").to_numpy()

        pallets = np.maximum(1, rng.poisson(14, size=total))
        unload_min = np.round(
            pallets * UNLOAD_MIN_PER_PALLET * rng.lognormal(0.0, 0.25, size=total)
        )
        unload_end_ts = unload_start_ts + pd.to_timedelta(unload_min, unit="m").to_numpy()

        putaway_h = rng.lognormal(np.log(profile.putaway_median_h), 0.6, size=total)
        putaway_end_ts = (
            unload_end_ts + pd.to_timedelta(np.round(putaway_h, 3), unit="h").to_numpy()
        )

        frames.append(
            pd.DataFrame(
                {
                    "receipt_id": [f"{profile.code}-R{i:06d}" for i in range(1, total + 1)],
                    "site": profile.code,
                    "carrier": carriers,
                    "appointment_ts": pd.to_datetime(appointment_ts),
                    "arrival_ts": pd.to_datetime(arrival_ts),
                    "unload_start_ts": pd.to_datetime(unload_start_ts),
                    "unload_end_ts": pd.to_datetime(unload_end_ts),
                    "putaway_end_ts": pd.to_datetime(putaway_end_ts),
                    "pallets": pallets,
                    "lines": np.maximum(1, rng.poisson(pallets * 1.8)),
                }
            )
        )

    receipts = pd.concat(frames, ignore_index=True)
    return receipts.sort_values(["arrival_ts", "receipt_id"], ignore_index=True)
