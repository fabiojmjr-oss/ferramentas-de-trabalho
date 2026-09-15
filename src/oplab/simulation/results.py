"""Reading the output of a run.

Two habits are enforced here because both are easy to get wrong and both invalidate the
answer:

**Filter the warm-up.** Entities released before the warm-up ends are dropped, and resource
statistics were already reset at that point. A model that starts empty reports a shorter queue
than the operation ever has.

**Compare completions against releases.** An over-committed configuration does not announce
itself with a large number; it accumulates a backlog. Cycle time averaged over only the orders
that finished is then computed from a biased sample and looks reassuring.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .._pandas import as_float
from .config import SimConfig

QUANTILES: tuple[float, ...] = (0.5, 0.9, 0.95)


@dataclass(frozen=True)
class SimResult:
    """Outcome of one replication.

    Attributes:
        config: The configuration that produced it.
        resources: One row per resource with utilisation and waiting time.
        trucks: Completed inbound trucks, warm-up excluded.
        orders: Completed outbound orders, warm-up excluded.
        trucks_released: Trucks that arrived in the measured window.
        orders_released: Orders released in the measured window.
    """

    config: SimConfig
    resources: pd.DataFrame
    trucks: pd.DataFrame
    orders: pd.DataFrame
    trucks_released: int
    orders_released: int

    @property
    def orders_unfinished(self) -> int:
        """Orders released in the window that had not been packed when the horizon ended."""
        return max(0, self.orders_released - len(self.orders))

    @property
    def backlog_share(self) -> float:
        """Unfinished share of released orders.

        Anything materially above zero means the configuration cannot keep up, and every other
        statistic in the result is then measured on the subset that happened to get through.
        """
        return self.orders_unfinished / self.orders_released if self.orders_released else 0.0

    def bottleneck(self) -> pd.Series:
        """The resource the rest of the operation waits on most.

        Ranked by **total** waiting time caused, not by utilisation. The two usually agree and
        when they disagree the waiting time is the one that matters: a resource at 90% that
        everybody queues behind costs more than one at 95% that nobody needs urgently.
        """
        if self.resources.empty:
            raise ValueError("no resource statistics were collected")
        return self.resources.sort_values("total_wait_h", ascending=False).iloc[0]

    def throughput(self) -> pd.Series:
        """Daily throughput and completion, over the measured window."""
        days = max(1, self.config.measured_days)
        return pd.Series(
            {
                "orders_released_per_day": self.orders_released / days,
                "orders_packed_per_day": len(self.orders) / days,
                "orders_unfinished": float(self.orders_unfinished),
                "backlog_share": self.backlog_share,
                "trucks_per_day": self.trucks_released / days,
                "pallets_per_day": as_float(self.trucks["pallets"].sum()) / days
                if len(self.trucks)
                else 0.0,
            }
        )

    def order_flow(self) -> pd.DataFrame:
        """Cycle time of outbound orders, decomposed into waiting and working."""
        return _profile(
            {
                "wait_for_picker_h": self.orders["pick_start"] - self.orders["released"],
                "picking_h": self.orders["pick_end"] - self.orders["pick_start"],
                "wait_for_checker_h": self.orders["check_start"] - self.orders["pick_end"],
                "checking_h": self.orders["check_end"] - self.orders["check_start"],
                "total_cycle_h": self.orders["check_end"] - self.orders["released"],
            }
        )

    def truck_flow(self) -> pd.DataFrame:
        """Inbound truck timings, decomposed into the intervals a yard manager controls."""
        return _profile(
            {
                "yard_wait_h": self.trucks["dock_in"] - self.trucks["arrival"],
                "unload_wait_h": self.trucks["unload_start"] - self.trucks["dock_in"],
                "unloading_h": self.trucks["unload_end"] - self.trucks["unload_start"],
                "truck_dwell_h": self.trucks["unload_end"] - self.trucks["arrival"],
                "dock_to_stock_h": self.trucks["putaway_end"] - self.trucks["arrival"],
            }
        )

    def capacity_review(self) -> pd.DataFrame:
        """The table a capacity decision should be made on, beside the one it usually is.

        The first two columns are the spreadsheet answer and the simulated answer for
        utilisation, and **they agree**. That agreement is the finding, not a validation:
        utilisation is conserved, a spreadsheet computes it correctly, and it still does not
        answer the question. Two resources at 78% and 95% can produce waiting times in the
        opposite order, because how work arrives matters as much as how much of it there is.

        The remaining columns are what the spreadsheet cannot produce at all, and what the
        decision actually turns on.

        Returns:
            One row per resource with ``static_utilisation``, ``utilisation``, ``mean_wait_h``,
            ``total_wait_h`` and ``held_while_closed_h``.
        """
        static = pd.Series(self.config.static_utilisation(), name="static_utilisation")
        simulated = self.resources.set_index("resource")[
            ["utilisation", "mean_wait_h", "total_wait_h", "held_while_closed_h"]
        ]
        frame = pd.concat([static, simulated], axis=1)
        return frame.reset_index(names="resource")

    def utilisation_ranks_nothing(self) -> pd.DataFrame:
        """Resources ordered by utilisation, and separately by the waiting they cause.

        When the two orderings disagree, managing to a utilisation target is managing to the
        wrong number. A resource can sit at a comfortable load and still be where the whole
        operation waits, if work is released to it in batches.

        Returns:
            One row per resource with its rank on each measure and the gap between them.
        """
        frame = self.resources.set_index("resource")[["utilisation", "total_wait_h"]].copy()
        frame["rank_by_utilisation"] = frame["utilisation"].rank(ascending=False).astype(int)
        frame["rank_by_waiting"] = frame["total_wait_h"].rank(ascending=False).astype(int)
        frame["rank_disagreement"] = (frame["rank_by_utilisation"] - frame["rank_by_waiting"]).abs()
        return frame.sort_values("total_wait_h", ascending=False).reset_index()


def _profile(stages: dict[str, pd.Series]) -> pd.DataFrame:
    """Summarise a set of duration series into one row each."""
    rows = []
    for stage, values in stages.items():
        clean = pd.to_numeric(values, errors="coerce").dropna()
        row: dict[str, float | str] = {
            "stage": stage,
            "n": float(len(clean)),
            "mean_h": as_float(clean.mean()) if len(clean) else np.nan,
        }
        for quantile in QUANTILES:
            row[f"p{int(round(quantile * 100))}_h"] = (
                as_float(clean.quantile(quantile)) if len(clean) else np.nan
            )
        rows.append(row)
    return pd.DataFrame(rows)
