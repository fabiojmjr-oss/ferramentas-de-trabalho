"""Flow indicators: order cycle time and dock-to-stock.

Averages hide the behaviour that matters in flow metrics. A dock-to-stock mean of 9 hours with
a 95th percentile of 40 is a different operation from a mean of 9 with a 95th percentile of
12, and only the second one is under control. Every function here reports percentiles
alongside the mean, and decomposes total time into the intervals that are managed separately.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .schemas import ORDER_LINES, RECEIPTS

DEFAULT_QUANTILES: tuple[float, ...] = (0.5, 0.9, 0.95)


def _hours(later: pd.Series, earlier: pd.Series) -> pd.Series:
    """Elapsed hours between two timestamp columns, as a float Series."""
    return (later - earlier).dt.total_seconds() / 3600.0


def duration_profile(
    hours: pd.Series,
    by: pd.Series | pd.DataFrame | None = None,
    quantiles: Sequence[float] = DEFAULT_QUANTILES,
) -> pd.DataFrame:
    """Summarise a duration series by count, mean, standard deviation and percentiles.

    Args:
        hours: Durations in hours. Nulls are dropped and reported as ``n_missing``.
        by: Optional grouping key aligned to ``hours``.
        quantiles: Percentiles to report, as fractions.

    Returns:
        One row overall, or one row per group, with columns ``n``, ``n_missing``, ``mean``,
        ``std`` and one ``p{q}`` column per quantile.
    """
    if any(not 0 < q < 1 for q in quantiles):
        raise ValueError("quantiles must be strictly between 0 and 1")

    def summarise(values: pd.Series) -> pd.Series:
        clean = values.dropna()
        stats: dict[str, float] = {
            "n": float(len(clean)),
            "n_missing": float(values.isna().sum()),
            "mean": float(clean.mean()) if len(clean) else np.nan,
            "std": float(clean.std(ddof=1)) if len(clean) > 1 else np.nan,
        }
        for q in quantiles:
            stats[f"p{int(round(q * 100))}"] = float(clean.quantile(q)) if len(clean) else np.nan
        return pd.Series(stats)

    if by is None:
        return summarise(hours).to_frame().T.reset_index(drop=True)

    frame = pd.DataFrame({"value": hours.to_numpy()})
    keys = pd.DataFrame(by).reset_index(drop=True)
    frame[keys.columns] = keys
    return (
        frame.groupby(list(keys.columns), observed=True)["value"]
        .apply(summarise)
        .unstack()
        .reset_index()
    )


def order_cycle_time(lines: pd.DataFrame, by: str | Sequence[str] | None = None) -> pd.DataFrame:
    """Order-to-delivery cycle time, decomposed into internal and transport time.

    Only delivered lines contribute. Undelivered lines are right-censored: including them as
    if their cycle time were the time elapsed so far biases the result downwards, which is why
    they are counted in ``n_missing`` rather than imputed.

    Args:
        lines: Order lines satisfying the ``order_lines`` contract.
        by: Optional grouping column(s), for example ``"site"``.

    Returns:
        Duration profiles for ``internal_h`` (order to dispatch), ``transit_h`` (dispatch to
        delivery) and ``total_h``, stacked with a ``stage`` column.
    """
    subset = ["order_ts", "ship_ts", "delivered_ts"]
    if by is not None:
        subset += [by] if isinstance(by, str) else list(by)
    ORDER_LINES.validate(lines, subset=subset)

    stages = {
        "internal_h": _hours(lines["ship_ts"], lines["order_ts"]),
        "transit_h": _hours(lines["delivered_ts"], lines["ship_ts"]),
        "total_h": _hours(lines["delivered_ts"], lines["order_ts"]),
    }
    keys = None if by is None else lines[[by] if isinstance(by, str) else list(by)]

    frames = []
    for stage, values in stages.items():
        profile = duration_profile(values, by=keys)
        profile.insert(0, "stage", stage)
        frames.append(profile)
    return pd.concat(frames, ignore_index=True)


def dock_to_stock(receipts: pd.DataFrame, by: str | Sequence[str] | None = "site") -> pd.DataFrame:
    """Dock-to-stock time, decomposed into waiting, unloading and put-away.

    The decomposition is the point. A long total is acted on very differently depending on
    which interval owns it: waiting time is an appointment and yard management problem,
    unloading is a labour and equipment problem, and put-away is a layout and systems problem.
    Reporting only the total sends improvement effort to the wrong owner.

    Args:
        receipts: Receipts satisfying the ``receipts`` contract.
        by: Optional grouping column(s). Defaults to ``"site"``.

    Returns:
        Duration profiles for ``dock_wait_h``, ``unload_h``, ``putaway_h`` and
        ``dock_to_stock_h``, stacked with a ``stage`` column.
    """
    subset = ["arrival_ts", "unload_start_ts", "unload_end_ts", "putaway_end_ts"]
    if by is not None:
        subset += [by] if isinstance(by, str) else list(by)
    RECEIPTS.validate(receipts, subset=subset)

    stages = {
        "dock_wait_h": _hours(receipts["unload_start_ts"], receipts["arrival_ts"]),
        "unload_h": _hours(receipts["unload_end_ts"], receipts["unload_start_ts"]),
        "putaway_h": _hours(receipts["putaway_end_ts"], receipts["unload_end_ts"]),
        "dock_to_stock_h": _hours(receipts["putaway_end_ts"], receipts["arrival_ts"]),
    }
    keys = None if by is None else receipts[[by] if isinstance(by, str) else list(by)]

    frames = []
    for stage, values in stages.items():
        profile = duration_profile(values, by=keys)
        profile.insert(0, "stage", stage)
        frames.append(profile)
    return pd.concat(frames, ignore_index=True)


def appointment_adherence(
    receipts: pd.DataFrame,
    early_tolerance_min: int = 30,
    late_tolerance_min: int = 30,
    by: str | Sequence[str] | None = "carrier",
) -> pd.DataFrame:
    """Carrier adherence to the booked inbound appointment.

    Early arrivals are counted separately rather than lumped into "on time". An early truck
    consumes dock capacity booked for someone else, so from the yard's point of view it is a
    deviation, not a favour.

    Args:
        receipts: Receipts satisfying the ``receipts`` contract, including ``appointment_ts``.
        early_tolerance_min: Minutes a carrier may arrive early and still count as on time.
        late_tolerance_min: Minutes a carrier may arrive late and still count as on time.
        by: Optional grouping column(s). Defaults to ``"carrier"``.

    Returns:
        One row per group with the share of early, on-time and late arrivals, the median
        deviation in minutes, and the arrival count.
    """
    subset = ["arrival_ts", "appointment_ts"]
    if by is not None:
        subset += [by] if isinstance(by, str) else list(by)
    RECEIPTS.validate(receipts, subset=subset)
    if "appointment_ts" not in receipts.columns:
        raise KeyError("appointment_ts is required to measure appointment adherence")

    deviation = (receipts["arrival_ts"] - receipts["appointment_ts"]).dt.total_seconds() / 60.0
    frame = pd.DataFrame(
        {
            "deviation_min": deviation,
            "early": deviation < -early_tolerance_min,
            "late": deviation > late_tolerance_min,
        }
    )
    frame["on_time"] = ~(frame["early"] | frame["late"])

    if by is None:
        return pd.DataFrame(
            [
                {
                    "arrivals": int(len(frame)),
                    "early": float(frame["early"].mean()),
                    "on_time": float(frame["on_time"].mean()),
                    "late": float(frame["late"].mean()),
                    "median_deviation_min": float(frame["deviation_min"].median()),
                }
            ]
        )

    keys = [by] if isinstance(by, str) else list(by)
    frame[keys] = receipts[keys].to_numpy()
    grouped = frame.groupby(keys, observed=True)
    return (
        grouped.agg(
            arrivals=("deviation_min", "size"),
            early=("early", "mean"),
            on_time=("on_time", "mean"),
            late=("late", "mean"),
            median_deviation_min=("deviation_min", "median"),
        )
        .reset_index()
        .sort_values("on_time", ascending=False, ignore_index=True)
    )
