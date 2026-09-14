"""Where is the constraint, and what does relieving it buy?

Run:
    python examples/06_capacity_simulation.py

This is the question a static capacity spreadsheet cannot answer, and the script shows why in
the least comfortable way available: the spreadsheet's utilisation figures turn out to be
correct, and still point at the wrong decision.
"""

from __future__ import annotations

import pandas as pd

from oplab.simulation import SimConfig, compare_scenarios, replicate, run_once

REPLICATIONS = 6


def main() -> None:
    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 30)

    config = SimConfig()
    result = run_once(config)

    print("1. The spreadsheet is right about utilisation")
    review = result.capacity_review()
    print(review.round(3).to_string(index=False))
    print("\n   The first two columns agree to within a couple of points. Utilisation is")
    print("   conserved, and dividing mean work by mean capacity computes it correctly. A")
    print("   capacity review that stops there is not wrong about arithmetic - it is answering")
    print("   a question nobody asked.")

    print("\n2. And utilisation ranks nothing")
    ranks = result.utilisation_ranks_nothing()
    print(ranks.round(3).to_string(index=False))
    picking = ranks.set_index("resource").loc["picking"]
    checking = ranks.set_index("resource").loc["checking"]
    print(
        f"\n   Picking sits at {picking['utilisation']:.0%} and causes"
        f" {picking['total_wait_h']:,.0f} hours of waiting."
    )
    print(
        f"   Checking sits at {checking['utilisation']:.0%} and causes"
        f" {checking['total_wait_h']:,.0f} hours."
    )
    print("   The busier resource is not the one the operation waits on. Orders are released")
    print("   to the pick face in two waves, so every order queues behind half a day's work")
    print("   the moment it arrives. That is a release policy, not a capacity shortfall, and")
    print("   no utilisation figure can tell the two apart.")

    print("\n3. One run is a sample of one")
    summary = replicate(config, replications=REPLICATIONS).set_index("metric")
    headline = summary.loc[
        ["order_cycle_mean_h", "order_cycle_p95_h", "truck_dwell_p95_h", "backlog_share"]
    ]
    print(headline[["mean", "ci_low", "ci_high", "half_width"]].round(4).to_string())
    print(f"\n   {REPLICATIONS} replications, 95% confidence. A capital decision taken on a")
    print("   single run is taken on a number with no interval around it, and two options")
    print("   that differ only by seed will look different.")

    print("\n4. Pricing the options against each other")
    scenarios = {
        "+4 pickers": {"pickers": 22},
        "+2 checkers": {"checkers": 7},
        "+2 inbound docks": {"inbound_docks": 6},
        "shift 8h to 10h": {"shift_hours": 10.0},
        "release in 8 waves": {"release_waves": 8},
    }
    table = compare_scenarios(
        config, scenarios, metric="order_cycle_mean_h", replications=REPLICATIONS
    )
    print(table.round(4).to_string(index=False))

    best = table.iloc[0]
    paid = table.loc[table["scenario"] == "+2 checkers", "change_vs_base"].iloc[0]
    ratio = best["change_vs_base"] / paid
    print(f"\n   Levelling the release wins by {-best['change_vs_base']:.0%} and costs nothing.")
    print(
        f"   It recovers {ratio:.1f} times what the best paid option does, and needs no approval."
    )
    print("\n   Two scenarios are marked indistinguishable, and that is the column that earns")
    print("   its place. Four more pickers - the intuitive move, aimed at the resource with the")
    print("   longest queue and the largest team - cannot be shown to do anything at all. Two")
    print("   more inbound doors cannot either, and in this model provably cannot: inbound and")
    print("   outbound share no resource, so an inbound investment is arithmetically incapable")
    print("   of moving an outbound cycle time. In an operation that cross-deploys labour")
    print("   between the two, it would.")

    print("\n5. What the trucks see")
    trucks = result.truck_flow()
    print(trucks.round(3).to_string(index=False))
    dock = result.resources.set_index("resource").loc["inbound_dock"]
    print(f"\n   Inbound docks run at {dock['utilisation']:.0%}, which reads as ample. They also")
    print(
        f"   spend {dock['held_while_closed_h']:,.0f} hours occupied while the operation is"
        " closed, by trailers"
    )
    print("   parked on a door waiting for the next shift. That is detention, it is invisible")
    print("   to a utilisation figure, and it is what the carrier bills for.")


if __name__ == "__main__":
    main()
