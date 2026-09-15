"""An order-fulfilment event log, with the path variation that makes a process worth discovering.

A process map discovered from a log whose every case follows the same sequence is a picture of the
flowchart, and drawing it proves nothing. What makes the technique worth the effort is that real
logs contain paths nobody documented: credit holds, shortages that send an order back to
allocation, a quality check that fails and loops, an address corrected before dispatch, a delivery
that has to be attempted twice. Each of those is a branch somebody decided was an exception, and
together they are the majority of cases.

The generator produces them with explicit probabilities so that the discovery can be checked
against what was generated. It also separates two kinds of time on purpose: the duration of an
activity, and the wait before the next one starts. Every value-stream exercise turns on that
distinction, and a log that records only one timestamp per step cannot make it - which is why the
log below carries a start and a complete timestamp for every event.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

# activity -> (median duration in minutes, log-scale sigma). These are touch times: what the step
# takes once somebody starts it.
ACTIVITY_MINUTES: dict[str, tuple[float, float]] = {
    "Order Received": (2.0, 0.3),
    "Credit Check": (6.0, 0.7),
    "Credit Hold": (240.0, 1.1),
    "Allocate Stock": (4.0, 0.5),
    "Stock Shortage": (90.0, 1.0),
    "Pick": (18.0, 0.6),
    "Pack": (9.0, 0.5),
    "Quality Check": (5.0, 0.5),
    "Repack": (12.0, 0.6),
    "Address Correction": (35.0, 0.9),
    "Load": (14.0, 0.5),
    "Ship": (3.0, 0.3),
    "Deliver": (26.0, 0.6),
    "Delivery Failed": (20.0, 0.5),
    "Cancel Order": (8.0, 0.6),
}

# activity -> (median wait in minutes before the NEXT activity starts, log-scale sigma). The wait
# is where the lead time is, and it is not where the improvement effort usually goes.
WAIT_MINUTES: dict[str, tuple[float, float]] = {
    "Order Received": (25.0, 1.0),
    "Credit Check": (55.0, 1.2),
    "Credit Hold": (900.0, 1.0),
    "Allocate Stock": (140.0, 1.1),
    "Stock Shortage": (1600.0, 1.0),
    "Pick": (35.0, 0.9),
    "Pack": (20.0, 0.8),
    "Quality Check": (30.0, 0.9),
    "Repack": (25.0, 0.8),
    "Address Correction": (300.0, 1.0),
    "Load": (210.0, 1.0),
    "Ship": (640.0, 0.8),
    "Delivery Failed": (1500.0, 0.8),
    "Deliver": (0.0, 0.0),
    "Cancel Order": (0.0, 0.0),
}

# The documented process: what a procedure note would say happens to every order.
HAPPY_PATH: tuple[str, ...] = (
    "Order Received",
    "Credit Check",
    "Allocate Stock",
    "Pick",
    "Pack",
    "Quality Check",
    "Load",
    "Ship",
    "Deliver",
)

# Activities that change the order's state towards the customer. Everything else is inspection,
# correction or waiting, which is the distinction a value-stream map is built on. Quality Check is
# deliberately excluded: inspection is not value added, it is the cost of not getting it right.
VALUE_ADDING: tuple[str, ...] = ("Pick", "Pack", "Load", "Ship", "Deliver")

CREDIT_HOLD_RATE = 0.11
SHORTAGE_RATE = 0.14
QUALITY_FAIL_RATE = 0.09
SECOND_QUALITY_FAIL_RATE = 0.22
ADDRESS_CORRECTION_RATE = 0.07
DELIVERY_FAIL_RATE = 0.06
CANCEL_AFTER_HOLD_RATE = 0.18
CASES = 4000


def generate_order_events(
    cfg: SynthConfig, order_lines: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Generate an order-fulfilment event log with documented and undocumented paths.

    Args:
        cfg: Dataset configuration, for the site list.
        order_lines: Order book, used only to draw case identifiers and start times so the log
            refers to orders that exist elsewhere in the dataset.
        rng: Random generator.

    Returns:
        One row per event with ``case_id``, ``site``, ``activity``, ``start_ts``, ``complete_ts``
        and ``position``. Sorted by case and time. Every case begins with ``Order Received``; most
        end with ``Deliver`` and some with ``Cancel Order``.
    """
    orders = order_lines.drop_duplicates("order_id")
    take = min(CASES, len(orders))
    chosen = orders.iloc[rng.choice(len(orders), size=take, replace=False)]

    rows: list[dict[str, object]] = []
    for case_id, site, start in zip(
        chosen["order_id"].to_numpy(),
        chosen["site"].to_numpy(),
        chosen["order_ts"].to_numpy(),
        strict=True,
    ):
        clock = pd.Timestamp(start)
        for activity in _path(rng):
            duration, wait = _minutes(activity, rng)
            complete = clock + pd.Timedelta(minutes=duration)
            rows.append(
                {
                    "case_id": case_id,
                    "site": site,
                    "activity": activity,
                    "start_ts": clock,
                    "complete_ts": complete,
                }
            )
            clock = complete + pd.Timedelta(minutes=wait)

    log = pd.DataFrame(rows)
    log["position"] = log.groupby("case_id").cumcount() + 1
    return log.sort_values(["case_id", "start_ts", "position"], ignore_index=True)


def _path(rng: np.random.Generator) -> list[str]:
    """Draw one case's activity sequence.

    The branches are nested rather than independent, which is what makes the variant count large:
    an order can be held for credit, then short on stock, then fail its quality check twice.
    """
    path = ["Order Received", "Credit Check"]

    if rng.random() < CREDIT_HOLD_RATE:
        path.append("Credit Hold")
        if rng.random() < CANCEL_AFTER_HOLD_RATE:
            path.append("Cancel Order")
            return path
        # A released hold re-enters the documented process at the check, which is a loop the
        # flowchart does not have.
        path.append("Credit Check")

    path.append("Allocate Stock")
    if rng.random() < SHORTAGE_RATE:
        path.extend(["Stock Shortage", "Allocate Stock"])

    path.extend(["Pick", "Pack", "Quality Check"])
    if rng.random() < QUALITY_FAIL_RATE:
        path.extend(["Repack", "Quality Check"])
        if rng.random() < SECOND_QUALITY_FAIL_RATE:
            path.extend(["Repack", "Quality Check"])

    if rng.random() < ADDRESS_CORRECTION_RATE:
        path.append("Address Correction")

    path.extend(["Load", "Ship"])
    if rng.random() < DELIVERY_FAIL_RATE:
        path.extend(["Delivery Failed", "Deliver"])
    else:
        path.append("Deliver")
    return path


def _minutes(activity: str, rng: np.random.Generator) -> tuple[float, float]:
    """Draw a duration and the wait that follows it."""
    median, sigma = ACTIVITY_MINUTES[activity]
    duration = float(rng.lognormal(np.log(median), sigma))
    wait_median, wait_sigma = WAIT_MINUTES[activity]
    wait = 0.0 if wait_median <= 0.0 else float(rng.lognormal(np.log(wait_median), wait_sigma))
    return round(duration, 2), round(wait, 2)
