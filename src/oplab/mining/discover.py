"""Discovering what the process does, as opposed to what the flowchart says it does.

The directly-follows graph is the whole of process discovery that matters operationally: for every
ordered pair of activities, how often one is immediately followed by the other and how long the
handover takes. Everything else - Petri nets, inductive mining, BPMN export - is presentation.

The one judgement this module refuses to make silently is the filter. A discovered graph on a real
log has a long tail of edges traversed once, and drawing all of them produces the picture people
call spaghetti, which is then used as evidence that the process is chaotic when it is mostly
evidence that the graph was not filtered. :func:`directly_follows` reports every edge with its
frequency share so the filter is a decision with a number attached rather than a default.
"""

from __future__ import annotations

import pandas as pd

from .log import validate_log


def directly_follows(log: pd.DataFrame) -> pd.DataFrame:
    """Build the directly-follows graph with frequency and handover time per edge.

    Args:
        log: Event log with ``case_id``, ``activity``, ``start_ts`` and ``complete_ts``.

    Returns:
        One row per ordered pair of activities with ``transitions`` (how often the pair occurs),
        ``cases`` (how many distinct cases traverse it), ``share`` of all transitions, and the
        mean and median handover hours from the completion of the first to the start of the second.
        Sorted by frequency.
    """
    frame = validate_log(log)
    frame["next_activity"] = frame.groupby("case_id")["activity"].shift(-1)
    frame["next_start"] = frame.groupby("case_id")["start_ts"].shift(-1)
    edges = frame.loc[frame["next_activity"].notna()].copy()
    edges["handover_h"] = (edges["next_start"] - edges["complete_ts"]).dt.total_seconds() / 3600.0

    grouped = (
        edges.groupby(["activity", "next_activity"], observed=True)
        .agg(
            transitions=("case_id", "size"),
            cases=("case_id", "nunique"),
            mean_handover_h=("handover_h", "mean"),
            median_handover_h=("handover_h", "median"),
        )
        .reset_index()
        .rename(columns={"activity": "source", "next_activity": "target"})
    )
    grouped["share"] = grouped["transitions"] / grouped["transitions"].sum()
    return grouped.sort_values("transitions", ascending=False, ignore_index=True)


def variants(log: pd.DataFrame) -> pd.DataFrame:
    """Every distinct activity sequence in the log, with its share of cases.

    Args:
        log: Event log.

    Returns:
        One row per variant with the ``path`` as a tuple, the number of ``cases``, its ``share``
        and the ``cumulative_share``. Sorted by frequency, so the number of variants needed to
        cover most of the volume can be read straight off the last column.
    """
    frame = validate_log(log)
    paths = frame.groupby("case_id", observed=True)["activity"].apply(tuple)
    counts = paths.value_counts()
    table = pd.DataFrame(
        {
            "path": counts.index.to_list(),
            "cases": counts.to_numpy(),
        }
    )
    table["length"] = [len(path) for path in table["path"]]
    table["share"] = table["cases"] / table["cases"].sum()
    table["cumulative_share"] = table["share"].cumsum()
    return table


def variant_coverage(log: pd.DataFrame, target: float = 0.8) -> tuple[int, int, float]:
    """How many variants it takes to cover a share of the cases.

    The pair of numbers is the argument. A process with a hundred variants where six cover 80% of
    the volume is standardisable; one where sixty do is not, and the distinction is invisible in a
    variant count alone.

    Args:
        log: Event log.
        target: Share of cases to cover.

    Returns:
        The number of variants needed, the total number of variants, and the share of cases on the
        single most frequent path.

    Raises:
        ValueError: If ``target`` is not in ``(0, 1]``.
    """
    if not 0.0 < target <= 1.0:
        raise ValueError("target must be in (0, 1]")
    table = variants(log)
    needed = int((table["cumulative_share"] < target).sum() + 1)
    return min(needed, len(table)), int(len(table)), float(table["share"].iloc[0])


def rework(log: pd.DataFrame) -> pd.DataFrame:
    """Activities that cases revisit, and what the revisits cost.

    Rework is the most quotable output of process mining and the easiest to fabricate: if the case
    identifier is coarser than the case - an order identifier on a line-level log - every
    multi-line order looks like a loop. :func:`~oplab.mining.profile_log` is the check; this
    function assumes it has passed.

    Args:
        log: Event log.

    Returns:
        One row per activity that is executed more than once in at least one case, with the share
        of cases affected, the mean number of executions in those cases, and the mean duration
        hours added by the repeats. Sorted by cases affected.

        ``mean_repeat_hours`` is ``nan`` for an activity that is never executed exactly once,
        because there is then no baseline to measure the repeats against - reporting the full
        duration there would overstate the cost of rework by the cost of doing the work at all.
    """
    frame = validate_log(log)
    frame["duration_h"] = (frame["complete_ts"] - frame["start_ts"]).dt.total_seconds() / 3600.0
    total_cases = frame["case_id"].nunique()

    counts = (
        frame.groupby(["case_id", "activity"], observed=True)
        .agg(executions=("activity", "size"), duration_h=("duration_h", "sum"))
        .reset_index()
    )
    repeated = counts.loc[counts["executions"] > 1]
    if repeated.empty:
        return pd.DataFrame(
            columns=[
                "activity",
                "cases_affected",
                "share_of_cases",
                "mean_executions",
                "mean_repeat_hours",
            ]
        )

    rows = []
    for activity, group in repeated.groupby("activity", observed=True):
        single = counts.loc[
            (counts["activity"] == activity) & (counts["executions"] == 1), "duration_h"
        ]
        # With no single-execution case there is nothing to measure the repeats against, and
        # substituting zero would silently report the activity's whole duration as added cost.
        baseline = float(single.mean()) if not single.empty else float("nan")
        rows.append(
            {
                "activity": activity,
                "cases_affected": int(len(group)),
                "share_of_cases": len(group) / total_cases,
                "mean_executions": float(group["executions"].mean()),
                "mean_repeat_hours": float(group["duration_h"].mean()) - baseline,
            }
        )
    return pd.DataFrame(rows).sort_values("cases_affected", ascending=False, ignore_index=True)
