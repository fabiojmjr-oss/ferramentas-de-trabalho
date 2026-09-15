"""Cycle time split into the two parts that have different owners and different costs.

A value stream map has one number at the bottom: the share of lead time during which something is
happening to the order. It is usually computed in a workshop from estimates, it usually comes out
around a tenth, and the estimate is treated as the finding. It can be computed from a log instead,
and then it can be computed per activity, per site and per variant, which turns it from a slogan
into a list of places to look.

The split this module makes is between three things, not two:

* **Work** - an activity is in progress.
* **Wait** - nothing is happening between two activities.
* **Inspection and correction** - an activity is in progress, but it exists only because something
  went wrong earlier. Quality checks, repacks, address corrections, credit holds.

The third is the one that matters politically, because it is work by any measure of activity and it
is waste by any measure of value. Counting it as value-adding is how a flow-efficiency figure gets
flattered, so the value-adding set is an explicit argument with no default that guesses.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from .log import validate_log


@dataclass(frozen=True)
class FlowEfficiency:
    """Lead time decomposed.

    Attributes:
        lead_h: Mean case lead time in hours, first start to last completion.
        work_h: Mean hours in which some activity was in progress.
        wait_h: Mean hours between activities.
        value_adding_h: Mean hours in activities named as value adding.
        cases: Cases measured.
    """

    lead_h: float
    work_h: float
    wait_h: float
    value_adding_h: float
    cases: int

    @property
    def flow_efficiency(self) -> float:
        """Value-adding hours over lead time, the figure a value stream map ends with."""
        return self.value_adding_h / self.lead_h if self.lead_h > 0 else float("nan")

    @property
    def busy_share(self) -> float:
        """Every working hour over lead time, value adding or not.

        The gap between this and :attr:`flow_efficiency` is the inspection and correction work,
        and reporting only this number is the usual way flow efficiency is overstated.
        """
        return self.work_h / self.lead_h if self.lead_h > 0 else float("nan")


def case_times(log: pd.DataFrame) -> pd.DataFrame:
    """Lead time, working time and waiting time per case.

    Args:
        log: Event log.

    Returns:
        One row per case with ``events``, ``lead_h``, ``work_h``, ``wait_h`` and the first and last
        activity, so a truncated case can be identified rather than averaged into the result.
    """
    frame = validate_log(log)
    frame["duration_h"] = (frame["complete_ts"] - frame["start_ts"]).dt.total_seconds() / 3600.0

    grouped = frame.groupby("case_id", observed=True)
    table = grouped.agg(
        events=("activity", "size"),
        work_h=("duration_h", "sum"),
        first_activity=("activity", "first"),
        last_activity=("activity", "last"),
        start=("start_ts", "min"),
        end=("complete_ts", "max"),
    )
    table["lead_h"] = (table["end"] - table["start"]).dt.total_seconds() / 3600.0
    table["wait_h"] = table["lead_h"] - table["work_h"]
    return table.drop(columns=["start", "end"]).reset_index()


def activity_times(log: pd.DataFrame) -> pd.DataFrame:
    """Work and downstream waiting time per activity, with the totals that rank them.

    Args:
        log: Event log.

    Returns:
        One row per activity with ``executions``, the mean and median duration hours, the mean
        hours waited *after* it before the next activity starts, and the total hours of each
        summed across the log. The totals are what a bottleneck argument needs: an activity that is
        slow and rare costs less than one that is quick and universal.
    """
    frame = validate_log(log)
    frame["duration_h"] = (frame["complete_ts"] - frame["start_ts"]).dt.total_seconds() / 3600.0
    frame["next_start"] = frame.groupby("case_id")["start_ts"].shift(-1)
    frame["wait_after_h"] = (frame["next_start"] - frame["complete_ts"]).dt.total_seconds() / 3600.0

    table = (
        frame.groupby("activity", observed=True)
        .agg(
            executions=("activity", "size"),
            mean_duration_h=("duration_h", "mean"),
            median_duration_h=("duration_h", "median"),
            total_duration_h=("duration_h", "sum"),
            mean_wait_after_h=("wait_after_h", "mean"),
            total_wait_after_h=("wait_after_h", "sum"),
        )
        .reset_index()
    )
    return table.sort_values("total_wait_after_h", ascending=False, ignore_index=True)


def flow_efficiency(log: pd.DataFrame, value_adding: Sequence[str]) -> FlowEfficiency:
    """Decompose lead time and compute flow efficiency.

    Args:
        log: Event log.
        value_adding: Activities that advance the order towards the customer. Required rather than
            defaulted, because the choice decides the answer and an inspection step counted here
            turns a rework cost into value.

    Returns:
        A :class:`FlowEfficiency`.

    Raises:
        ValueError: If ``value_adding`` is empty, or names an activity absent from the log - which
            almost always means a typo silently deflating the result.
    """
    if not value_adding:
        raise ValueError("value_adding must name at least one activity")

    frame = validate_log(log)
    present = set(frame["activity"].unique())
    unknown = sorted(set(value_adding) - present)
    if unknown:
        raise ValueError(f"value_adding names activities absent from the log: {unknown}")

    frame["duration_h"] = (frame["complete_ts"] - frame["start_ts"]).dt.total_seconds() / 3600.0
    frame["is_value_adding"] = frame["activity"].isin(list(value_adding))

    times = case_times(frame).set_index("case_id")
    value_hours = (
        frame.loc[frame["is_value_adding"]].groupby("case_id", observed=True)["duration_h"].sum()
    )
    value_hours = value_hours.reindex(times.index).fillna(0.0)

    return FlowEfficiency(
        lead_h=float(times["lead_h"].mean()),
        work_h=float(times["work_h"].mean()),
        wait_h=float(times["wait_h"].mean()),
        value_adding_h=float(value_hours.mean()),
        cases=int(len(times)),
    )


def waiting_ranked(log: pd.DataFrame) -> pd.DataFrame:
    """Where the lead time actually goes, as a share of all waiting in the log.

    Args:
        log: Event log.

    Returns:
        One row per activity with total waiting hours after it, its share of all waiting, and the
        cumulative share. The cumulative column is the point: on most logs a handful of handovers
        hold the majority of the lead time, and they are rarely the steps a workshop nominates.
    """
    table = activity_times(log)[["activity", "executions", "total_wait_after_h"]].copy()
    table = table.loc[table["total_wait_after_h"] > 0]
    total = table["total_wait_after_h"].sum()
    table["share_of_waiting"] = table["total_wait_after_h"] / total
    table = table.sort_values("total_wait_after_h", ascending=False, ignore_index=True)
    table["cumulative_share"] = table["share_of_waiting"].cumsum()
    return table
