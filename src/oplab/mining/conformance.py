"""Measuring the log against the documented process, in the direction that is actionable.

Conformance checking in the literature is mostly alignment-based: find the cheapest sequence of
model moves and log moves that reconciles a trace with a Petri net, and report a fitness between
zero and one. That number is rigorous and it is very hard to act on, because it does not say what
to fix.

What a process owner can act on is narrower and answerable from the log directly:

* Which cases follow the documented sequence, allowing extra steps but not missing or reordered
  ones. That is a subsequence test, and it needs no model formalism.
* For the cases that do not, **which documented step was skipped** and **which undocumented step
  was inserted**, counted.

The cost of this choice is stated rather than hidden: a subsequence test cannot detect two
documented steps performed in the wrong order if both are present in the right relative positions
somewhere in the trace, and it says nothing about concurrency. For a sequential fulfilment process
it is the right tool; for a process with genuine parallelism it is not, and the alternative is a
real aligner that this module does not implement.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from .log import validate_log


@dataclass(frozen=True)
class Conformance:
    """How much of the log the documented process describes.

    Attributes:
        cases: Cases measured.
        conforming: Cases containing the documented sequence in order.
        exact: Cases that are the documented sequence and nothing else.
        model: The documented sequence.
    """

    cases: int
    conforming: int
    exact: int
    model: tuple[str, ...]

    @property
    def fitness(self) -> float:
        """Share of cases that contain the documented sequence in order."""
        return self.conforming / self.cases if self.cases else float("nan")

    @property
    def exact_share(self) -> float:
        """Share of cases that follow the documented process and do nothing else."""
        return self.exact / self.cases if self.cases else float("nan")


def _contains_in_order(trace: tuple[str, ...], model: tuple[str, ...]) -> bool:
    position = 0
    for activity in trace:
        if position < len(model) and activity == model[position]:
            position += 1
    return position == len(model)


def conformance(log: pd.DataFrame, model: Sequence[str]) -> Conformance:
    """Compare every case against a documented activity sequence.

    Args:
        log: Event log.
        model: The documented sequence, in order.

    Returns:
        A :class:`Conformance`.

    Raises:
        ValueError: If ``model`` is empty.
    """
    if not model:
        raise ValueError("model must name at least one activity")
    expected = tuple(model)
    frame = validate_log(log)
    traces = frame.groupby("case_id", observed=True)["activity"].apply(tuple)

    conforming = int(sum(_contains_in_order(trace, expected) for trace in traces))
    exact = int(sum(trace == expected for trace in traces))
    return Conformance(cases=int(len(traces)), conforming=conforming, exact=exact, model=expected)


def deviations(log: pd.DataFrame, model: Sequence[str]) -> pd.DataFrame:
    """Count what the log does that the documented process does not, and the reverse.

    Args:
        log: Event log.
        model: The documented sequence.

    Returns:
        One row per activity with ``kind`` - ``"inserted"`` for an activity absent from the model,
        ``"skipped"`` for a documented activity missing from a case, ``"repeated"`` for a documented
        activity executed more than once - the number of cases affected and the share.

    Raises:
        ValueError: If ``model`` is empty.
    """
    if not model:
        raise ValueError("model must name at least one activity")
    expected = set(model)
    frame = validate_log(log)
    total = frame["case_id"].nunique()

    counts = frame.groupby(["case_id", "activity"], observed=True).size().unstack(fill_value=0)
    rows = []
    for activity in sorted(counts.columns):
        column = counts[activity]
        if activity not in expected:
            affected = int((column > 0).sum())
            rows.append({"activity": activity, "kind": "inserted", "cases": affected})
            continue
        skipped = int((column == 0).sum())
        if skipped:
            rows.append({"activity": activity, "kind": "skipped", "cases": skipped})
        repeated = int((column > 1).sum())
        if repeated:
            rows.append({"activity": activity, "kind": "repeated", "cases": repeated})

    table = pd.DataFrame(rows)
    if table.empty:
        return pd.DataFrame(columns=["activity", "kind", "cases", "share_of_cases"])
    table["share_of_cases"] = table["cases"] / total
    return table.sort_values("cases", ascending=False, ignore_index=True)


def cost_of_deviation(
    log: pd.DataFrame, model: Sequence[str], value_adding: Sequence[str]
) -> pd.DataFrame:
    """What a case costs in lead time when it leaves the documented path.

    The comparison a business case needs. A variant count says the process is not standard; this
    says what the non-standard cases cost, which is the number that decides whether standardising
    is worth funding.

    Args:
        log: Event log.
        model: The documented sequence.
        value_adding: Activities that advance the order, passed through to the flow-efficiency
            calculation for each group.

    Returns:
        Two rows - conforming and deviating - with ``cases``, mean lead hours, mean working hours,
        mean waiting hours and flow efficiency.

    Raises:
        ValueError: If either sequence is empty.
    """
    from .timing import case_times, flow_efficiency

    if not model:
        raise ValueError("model must name at least one activity")
    if not value_adding:
        raise ValueError("value_adding must name at least one activity")

    expected = tuple(model)
    frame = validate_log(log)
    traces = frame.groupby("case_id", observed=True)["activity"].apply(tuple)
    exact = {case for case, trace in traces.items() if trace == expected}

    times = case_times(frame).set_index("case_id")
    rows = []
    for label, cases in (
        ("follows the documented path", exact),
        ("deviates", set(times.index) - exact),
    ):
        if not cases:
            continue
        subset = frame.loc[frame["case_id"].isin(cases)]
        group = times.loc[sorted(cases)]
        efficiency = flow_efficiency(subset, value_adding)
        rows.append(
            {
                "group": label,
                "cases": int(len(group)),
                "mean_lead_h": float(group["lead_h"].mean()),
                "mean_work_h": float(group["work_h"].mean()),
                "mean_wait_h": float(group["wait_h"].mean()),
                "flow_efficiency": efficiency.flow_efficiency,
            }
        )
    return pd.DataFrame(rows)
