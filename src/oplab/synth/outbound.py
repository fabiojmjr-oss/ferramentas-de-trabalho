"""Outbound order lines and their fulfilment history."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

DAMAGE_RATE = 0.005
PICK_PACK_MEDIAN_H = 6.0
PICK_PACK_SIGMA = 0.5


def generate_order_lines(
    cfg: SynthConfig, demand: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Turn daily demand into order lines with a full fulfilment history.

    Demand rows are grouped into orders so that a single customer order carries several lines,
    which is what makes the distinction between line fill rate and order fill rate meaningful.
    Each line then receives a shipment and a delivery event drawn from the site profile.

    Three situations are generated on purpose, because each one breaks a naive service
    calculation:

    * **Partial shipments** - the line ships short, so on-time alone overstates service.
    * **Cancellations** - lines that never ship and must be excluded from the denominator.
    * **Censoring** - orders still in transit when the horizon ends. Counting them as failures
      understates service; dropping them silently overstates it.

    Returns:
        One row per order line. Timestamps are ``NaT`` where the event has not happened.
    """
    if demand.empty:
        raise ValueError("demand is empty; generate demand before order lines")

    lines = demand.rename(columns={"demand": "qty_ordered"}).copy()
    lines["site"] = lines["site"].astype(str)

    n = len(lines)
    group_sizes = lines.groupby(["date", "site"], observed=True)["sku"].transform("size")
    n_orders = np.maximum(1, np.round(group_sizes.to_numpy() / cfg.lines_per_order)).astype(int)
    order_seq = (rng.random(n) * n_orders).astype(int)

    date_key = pd.to_datetime(lines["date"]).dt.strftime("%Y%m%d")
    lines["order_id"] = (
        lines["site"]
        + "-"
        + date_key
        + "-"
        + pd.Series(order_seq, index=lines.index).astype(str).str.zfill(4)
    )
    lines["line_id"] = (
        lines["order_id"]
        + "-L"
        + (lines.groupby("order_id").cumcount() + 1).astype(str).str.zfill(2)
    )

    lines = _attach_order_timestamps(cfg, lines, rng)
    lines = _attach_fulfilment(cfg, lines, rng)

    ordered_cols = [
        "order_id",
        "line_id",
        "site",
        "sku",
        "order_ts",
        "promised_ts",
        "qty_ordered",
        "qty_shipped",
        "qty_delivered",
        "ship_ts",
        "delivered_ts",
        "status",
    ]
    return lines[ordered_cols].sort_values(["order_ts", "line_id"], ignore_index=True)


def _attach_order_timestamps(
    cfg: SynthConfig, lines: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Give every line the order and promise timestamps of its parent order."""
    orders = lines[["order_id", "site", "date"]].drop_duplicates("order_id").reset_index(drop=True)

    # Orders are captured through the working day, with a bias towards the afternoon.
    minutes = (8 * 60 + rng.beta(2.2, 1.8, size=len(orders)) * 10 * 60).astype(int)
    orders["order_ts"] = pd.to_datetime(orders["date"]) + pd.to_timedelta(minutes, unit="m")

    lead_days = orders["site"].map({s.code: s.promised_lead_days for s in cfg.sites}).to_numpy()
    # The commitment is a date, not an instant: end of day on the promised day.
    orders["promised_ts"] = (
        pd.to_datetime(orders["date"])
        + pd.to_timedelta(lead_days, unit="D")
        + pd.Timedelta(hours=18)
    )

    return lines.merge(orders[["order_id", "order_ts", "promised_ts"]], on="order_id", how="left")


def _attach_fulfilment(
    cfg: SynthConfig, lines: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Draw shipment and delivery outcomes for each line."""
    n = len(lines)
    qty = lines["qty_ordered"].to_numpy()
    availability = lines["site"].map({s.code: s.availability for s in cfg.sites}).to_numpy()

    cancelled = rng.random(n) < cfg.cancel_rate
    complete = rng.random(n) < availability

    # A shortfall is only possible when more than one unit was ordered.
    short_fraction = rng.uniform(0.2, 0.9, size=n)
    partial_qty = np.maximum(1, np.floor(qty * short_fraction)).astype(int)
    is_partial = (~complete) & (qty > 1) & (rng.random(n) < 0.6)

    qty_shipped = np.where(complete, qty, np.where(is_partial, partial_qty, 0))
    qty_shipped = np.where(cancelled, 0, qty_shipped)

    # Pick/pack and transit are drawn per order, not per line: an order leaves the dock as
    # one shipment on one vehicle. Drawing them per line would make order-level cycle time
    # meaningless and quietly smooth away the variability the charts are meant to expose.
    orders = lines[["order_id", "site"]].drop_duplicates("order_id").reset_index(drop=True)
    n_orders = len(orders)
    orders["pick_pack_h"] = rng.lognormal(
        np.log(PICK_PACK_MEDIAN_H), PICK_PACK_SIGMA, size=n_orders
    )
    order_transit_median = orders["site"].map({s.code: s.transit_median_h for s in cfg.sites})
    order_transit_sigma = orders["site"].map({s.code: s.transit_sigma for s in cfg.sites})
    orders["transit_h"] = rng.lognormal(
        np.log(order_transit_median.to_numpy()), order_transit_sigma.to_numpy(), size=n_orders
    )
    timing = lines[["order_id"]].merge(
        orders[["order_id", "pick_pack_h", "transit_h"]], on="order_id", how="left"
    )
    pick_pack_h = timing["pick_pack_h"].to_numpy()
    transit_h = timing["transit_h"].to_numpy()

    # The arithmetic stays in pandas so that the censoring below can use Series.mask, which
    # writes NaT while preserving the datetime dtype.
    ship_ts = lines["order_ts"] + pd.to_timedelta(np.round(pick_pack_h, 3), unit="h")
    delivered_ts = ship_ts + pd.to_timedelta(np.round(transit_h, 3), unit="h")

    horizon_end = pd.Timestamp(cfg.start) + pd.Timedelta(days=cfg.days)
    never_shipped = cancelled | (qty_shipped == 0)
    not_yet_shipped = (~never_shipped) & (ship_ts > horizon_end).to_numpy()
    in_transit = (~never_shipped) & (~not_yet_shipped) & (delivered_ts > horizon_end).to_numpy()

    damaged = rng.random(n) < DAMAGE_RATE
    qty_delivered = np.where(damaged, np.maximum(0, qty_shipped - 1), qty_shipped)

    status = np.full(n, "delivered", dtype=object)
    status[in_transit] = "in_transit"
    status[not_yet_shipped] = "open"
    status[qty_shipped == 0] = "stockout"
    status[cancelled] = "cancelled"

    qty_delivered = np.where(status == "delivered", qty_delivered, 0)

    out = lines.copy()
    out["qty_shipped"] = qty_shipped
    out["qty_delivered"] = qty_delivered
    out["ship_ts"] = ship_ts.mask(never_shipped | not_yet_shipped)
    out["delivered_ts"] = delivered_ts.mask(never_shipped | not_yet_shipped | in_transit)
    out["status"] = pd.Categorical(
        status, categories=["delivered", "in_transit", "open", "stockout", "cancelled"]
    )
    return out
