"""Replenishment orders, so that lead time is measured rather than assumed.

The inbound table in this generator describes dock-to-stock: what happens between a truck
arriving and the stock being available to pick. That is a warehouse interval. An inventory
policy needs a different one - the supplier lead time, from placing the order to the stock
being receivable - and the two are routinely confused, because the warehouse owns the data for
the first and nobody owns the data for the second.

The supplier profiles below are built around one property that decides whether the module has
anything to demonstrate: **mean lead time and lead-time variability are deliberately
uncorrelated**. The shortest-lead-time supplier here is also the least reliable one, and the
imported supplier with a thirty-day lead time is the tightest in relative terms. If short lead
times came bundled with low variability, every safety-stock comparison would rank suppliers the
same way on either property and the distinction that drives the result - that variability, not
the mean, sizes safety stock - would be unobservable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

# code -> (quoted lead days, median lead days, log-scale sigma, disruption probability,
# mean extra days when disrupted). Quoted and median differ where a supplier's commercial
# promise is not what it delivers.
SUPPLIER_PROFILES: dict[str, tuple[float, float, float, float, float]] = {
    "FORN-REGIONAL": (5.0, 5.2, 0.18, 0.02, 5.0),
    "FORN-NACIONAL": (7.0, 7.0, 0.32, 0.05, 9.0),
    "FORN-CONTRATO": (12.0, 12.0, 0.12, 0.01, 6.0),
    "FORN-IMPORT": (30.0, 31.0, 0.10, 0.03, 12.0),
}
SUPPLIER_MIX: tuple[float, ...] = (0.30, 0.34, 0.22, 0.14)
ORDERS_PER_WEEK_PER_SITE = 20.0
FILL_SHORTFALL_RATE = 0.06


def generate_purchase_orders(
    cfg: SynthConfig, catalog: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Generate a replenishment order history with realised lead times.

    Each SKU is sourced from exactly one supplier, which is what makes a per-SKU policy
    possible: the lead-time distribution a policy has to protect against is the distribution of
    that SKU's own supplier, not a network average. Realised lead time is lognormal around the
    supplier's median, plus an exponential tail on the fraction of orders that are disrupted -
    so the distribution is right skewed and the normal approximation behind the textbook
    safety-stock formula is being asked to cover a tail it does not have.

    Args:
        cfg: Dataset configuration.
        catalog: Catalogue frame, used for the SKU list and unit cost.
        rng: Random generator.

    Returns:
        One row per replenishment order, with ``ordered_date``, the ``promised_date`` implied by
        the supplier's quoted lead time, the ``received_date`` actually achieved, and the
        realised ``lead_days``.
    """
    skus = catalog["sku"].to_numpy()
    suppliers = list(SUPPLIER_PROFILES)
    sku_supplier = rng.choice(suppliers, size=len(skus), p=list(SUPPLIER_MIX))
    supplier_of = dict(zip(skus, sku_supplier, strict=True))

    dates = pd.date_range(cfg.start, periods=cfg.days, freq="D")
    frames: list[pd.DataFrame] = []

    for profile in cfg.sites:
        weeks = max(1, cfg.days // 7)
        total = int(rng.poisson(ORDERS_PER_WEEK_PER_SITE * profile.demand_scale * weeks))
        if total == 0:
            continue

        ordered_sku = rng.choice(skus, size=total)
        supplier = np.array([supplier_of[s] for s in ordered_sku])
        quoted = np.array([SUPPLIER_PROFILES[s][0] for s in supplier])
        median = np.array([SUPPLIER_PROFILES[s][1] for s in supplier])
        sigma = np.array([SUPPLIER_PROFILES[s][2] for s in supplier])
        disrupt_p = np.array([SUPPLIER_PROFILES[s][3] for s in supplier])
        disrupt_days = np.array([SUPPLIER_PROFILES[s][4] for s in supplier])

        # Orders are placed on working days only, and the horizon is shortened so that an
        # imported order placed on the last day still has somewhere to be received.
        placeable = dates[dates.dayofweek < 5]
        ordered_date = rng.choice(placeable.to_numpy(), size=total)

        base = rng.lognormal(np.log(median), sigma)
        disrupted = rng.random(total) < disrupt_p
        lead_days = np.round(base + np.where(disrupted, rng.exponential(disrupt_days), 0.0), 2)
        lead_days = np.maximum(1.0, lead_days)

        qty_ordered = np.maximum(1, rng.poisson(180, size=total))
        shortfall = rng.random(total) < FILL_SHORTFALL_RATE
        qty_received = np.where(
            shortfall,
            np.maximum(1, np.round(qty_ordered * rng.uniform(0.5, 0.95, size=total))),
            qty_ordered,
        ).astype(int)

        frames.append(
            pd.DataFrame(
                {
                    "po_id": [f"{profile.code}-P{i:06d}" for i in range(1, total + 1)],
                    "site": profile.code,
                    "sku": ordered_sku,
                    "supplier": supplier,
                    "ordered_date": pd.to_datetime(ordered_date),
                    "promised_date": pd.to_datetime(ordered_date)
                    + pd.to_timedelta(quoted, unit="D"),
                    "received_date": pd.to_datetime(ordered_date)
                    + pd.to_timedelta(lead_days, unit="D"),
                    "quoted_lead_days": quoted,
                    "lead_days": lead_days,
                    "disrupted": disrupted,
                    "qty_ordered": qty_ordered,
                    "qty_received": qty_received,
                }
            )
        )

    orders = pd.concat(frames, ignore_index=True)
    return orders.sort_values(["ordered_date", "po_id"], ignore_index=True)
