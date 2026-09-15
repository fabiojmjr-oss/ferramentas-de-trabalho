"""What the process does, measured against what the flowchart says it does.

Run:
    python examples/11_process_mining.py

Five things get established. That the log can support the analysis at all. That the documented
path describes a minority of cases while a handful of variants describe most of them - two facts
that are usually conflated into "the process is chaotic". That the lead time is almost all waiting,
and half of the working time is inspection and correction rather than work. That the step with the
longest touch time is not the step that holds the lead time. And that a conformance figure computed
the usual way can read 98% on a process 61% of cases follow.
"""

from __future__ import annotations

import pandas as pd

from oplab.mining import (
    conformance,
    cost_of_deviation,
    deviations,
    directly_follows,
    flow_efficiency,
    profile_log,
    rework,
    to_event_log,
    variant_coverage,
    waiting_ranked,
)
from oplab.synth import HAPPY_PATH, VALUE_ADDING, generate_dataset

COVERAGE_TARGET = 0.8


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    log = dataset.order_events

    print("1. Can this log support the analysis?")
    profile = profile_log(log)
    print(
        f"   {profile.cases:,} cases, {profile.events:,} events, {profile.activities} activities,"
        f" {profile.events_per_case:.2f} events per case."
    )
    print(f"   Separates work from wait: {profile.separates_work_from_wait}.")
    print("\n   Two defects make everything below meaningless and neither is visible downstream.")
    print("   A case identifier coarser than the case - an order id on a line-level log - makes")
    print("   every multi-line order look like a loop, which inflates exactly the rework figure")
    print("   the exercise was run to find. And a single timestamp per step cannot separate the")
    print("   duration of an activity from the wait before the next one, so flow efficiency")
    print("   cannot be computed and every improvement target defaults to the touch time.")

    milestones = to_event_log(
        dataset.order_lines.drop_duplicates("order_id"),
        "order_id",
        {"order_ts": "Order Received", "ship_ts": "Ship", "delivered_ts": "Deliver"},
    )
    flattened = profile_log(milestones)
    print(
        f"\n   The same orders as a wide milestone table: {flattened.events:,} events,"
        f" separates work from wait: {flattened.separates_work_from_wait}."
    )
    print("   That is the shape operational data usually arrives in, and it can support a")
    print("   handover analysis but not a value-stream one. Worth knowing before the workshop.")

    print("\n2. Does a standard process exist?")
    needed, total, top = variant_coverage(log, COVERAGE_TARGET)
    print(f"   {total} distinct paths. The documented one covers {top:.1%} of cases.")
    print(f"   {needed} paths cover {COVERAGE_TARGET:.0%} of the volume.")
    print("\n   Those two numbers are usually collapsed into one conclusion and they point in")
    print("   opposite directions. A path count in the tens is presented as evidence that the")
    print(f"   process is out of control; the coverage figure says {needed} routes carry four")
    print("   fifths of the work, so the process is standardisable and the tail is exceptions.")
    print("   The tail is also where the cost is, which is section 5.")

    print("\n3. Where the lead time goes")
    efficiency = flow_efficiency(log, VALUE_ADDING)
    print(
        pd.DataFrame(
            {
                "hours": [
                    efficiency.lead_h,
                    efficiency.work_h,
                    efficiency.wait_h,
                    efficiency.value_adding_h,
                ],
                "share of lead time": [
                    1.0,
                    efficiency.busy_share,
                    efficiency.wait_h / efficiency.lead_h,
                    efficiency.flow_efficiency,
                ],
            },
            index=["lead time", "working", "waiting", "value adding"],
        )
        .round(4)
        .to_string()
    )
    print(
        f"\n   Flow efficiency is {efficiency.flow_efficiency:.2%}. The number usually quoted is"
        f" the busy share,"
    )
    print(
        f"   {efficiency.busy_share:.2%}, and the gap between them is"
        f" {efficiency.work_h - efficiency.value_adding_h:.2f} hours of credit checks,"
    )
    print(
        f"   quality checks and repacks -"
        f" {1 - efficiency.value_adding_h / efficiency.work_h:.0%} of all working time exists only"
    )
    print("   because something went wrong earlier. It is work by any measure of activity and")
    print("   waste by any measure of value, and counting it as value is how a flow-efficiency")
    print("   figure gets flattered without anybody lying.")

    print("\n4. The step that takes longest is not the step that costs most")
    activities = waiting_ranked(log)
    print(activities.head(6).round(4).to_string(index=False))
    graph = directly_follows(log)
    edges = graph.loc[graph["source"].isin(activities["activity"].head(4))]
    print("\n   The handovers behind them:")
    print(
        edges.sort_values("transitions", ascending=False)
        .head(6)[["source", "target", "transitions", "mean_handover_h", "median_handover_h"]]
        .round(3)
        .to_string(index=False)
    )
    _bottleneck_comment(log, activities)

    print("\n5. Conformance, and what the exceptions cost")
    result = conformance(log, HAPPY_PATH)
    print(
        f"   Containment fitness: {result.fitness:.4f}. Cases that are the documented process and"
        f" nothing else: {result.exact_share:.4f}."
    )
    cancelled = int((log["activity"] == "Cancel Order").sum())
    print(
        f"\n   The first number is almost useless here and it is worth seeing why. A containment"
        f"\n   test permits inserted steps, so the only cases it rejects are the {cancelled} that"
        f"\n   were cancelled and never reached delivery:"
        f" {1 - cancelled / result.cases:.4f} is exactly the"
        f"\n   fitness. It is blind to the {result.conforming - result.exact:,} cases that reached"
        " the end by a route nobody"
    )
    print("   documented. A conformance figure near one is not evidence of a standard process.")
    print("\n   What the deviations are:")
    print(deviations(log, HAPPY_PATH).head(8).round(4).to_string(index=False))
    print("\n   What rework costs the cases that have it:")
    print(rework(log).round(4).to_string(index=False))
    print("\n   And what leaving the documented path costs in lead time:")
    cost = cost_of_deviation(log, HAPPY_PATH, VALUE_ADDING)
    print(cost.round(4).to_string(index=False))
    _cost_comment(cost)


def _bottleneck_comment(log: pd.DataFrame, waiting: pd.DataFrame) -> None:
    from oplab.mining import activity_times

    durations = activity_times(log).set_index("activity")
    slowest = durations["mean_duration_h"].idxmax()
    worst_wait = waiting.iloc[0]
    slow_share = float(
        waiting.loc[waiting["activity"] == slowest, "share_of_waiting"].iloc[0]
        if slowest in set(waiting["activity"])
        else 0.0
    )
    print(
        f"\n   {slowest} has the longest touch time in the log at"
        f" {durations.loc[slowest, 'mean_duration_h']:.2f} hours"
    )
    print(
        f"   and holds {slow_share:.1%} of all waiting. {worst_wait['activity']} takes"
        f" {durations.loc[worst_wait['activity'], 'mean_duration_h']:.2f} hours"
    )
    print(
        f"   and holds {worst_wait['share_of_waiting']:.1%}, because it runs"
        f" {int(worst_wait['executions']):,} times rather than"
        f" {int(durations.loc[slowest, 'executions']):,}."
    )
    print("   A workshop nominates the step that feels slow. The log ranks by hours contributed,")
    print("   and the two answers are different: the expensive handover is quick and universal,")
    print("   not slow and rare. The cumulative column is the shortlist - the top few handovers")
    print("   hold most of the lead time, and nothing outside them is worth a project.")


def _cost_comment(cost: pd.DataFrame) -> None:
    indexed = cost.set_index("group")
    clean = indexed.loc["follows the documented path"]
    dirty = indexed.loc["deviates"]
    print(
        f"\n   A deviating case takes {dirty['mean_lead_h'] / clean['mean_lead_h']:.1f} times as"
        f" long - {dirty['mean_lead_h']:.1f} hours against {clean['mean_lead_h']:.1f} - and its"
    )
    print(
        f"   flow efficiency is {dirty['flow_efficiency']:.2%} against"
        f" {clean['flow_efficiency']:.2%}, so it is not simply a longer"
    )
    print("   version of the same process: proportionally more of its lead time is spent waiting.")
    print("   That pair of numbers is the business case. A variant count says the process is not")
    print("   standard, which invites an argument about whether that matters. This says what the")
    print("   non-standard cases cost, which is the question a sponsor can answer.")


if __name__ == "__main__":
    main()
