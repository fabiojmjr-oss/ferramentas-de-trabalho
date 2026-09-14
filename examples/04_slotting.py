"""What the current slotting costs, and how much of that is recoverable.

Run:
    python examples/04_slotting.py

The finding is not the one a slotting vendor leads with. Three sensible ranking rules are
compared against random placement and against each other, and the gap between the rules turns
out to be an order of magnitude smaller than the gap between having a rule and not having one.
The decision on the table is therefore "do we re-slot", not "which algorithm".
"""

from __future__ import annotations

import pandas as pd

from oplab.slotting import (
    POLICY_MATRIX,
    abc_xyz,
    cell_summary,
    compare_strategies,
    cube_per_order_index,
    demand_profile,
    pick_counts,
    reslot,
    travel_by_class,
)
from oplab.synth import generate_dataset

SITE = "CD-SP"


def main() -> None:
    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    demand = dataset.demand.loc[dataset.demand["site"].astype(str) == SITE]
    picks = pick_counts(dataset.order_lines, site=SITE)
    classified = abc_xyz(demand_profile(demand, dataset.catalog, period="W"))
    classified = classified.loc[classified.index.isin(picks.index)]

    print(f"Site {SITE}: {len(classified)} SKUs, {int(picks.sum()):,} picks over the year")

    print("\n1. The nine cells, and why value alone is not enough")
    summary = cell_summary(classified)
    print(
        summary[["cell", "skus", "sku_share", "annual_value", "annual_value_share"]]
        .round(4)
        .to_string(index=False)
    )

    a_class = classified.loc[classified["abc"] == "A"]
    unstable = a_class.loc[a_class["xyz"] != "X"]
    share = unstable["annual_value"].sum() / a_class["annual_value"].sum()
    print(
        f"\n   {len(unstable)} of {len(a_class)} class A items are not stable, and they carry"
        f" {share:.1%}"
    )
    print("   of class A value. An ABC-only exercise would give all of them the same policy as")
    print("   the predictable ones, which is where the service failures come from.")
    print(f"\n   Policy for the AZ cell: {POLICY_MATRIX['AZ'].forecasting}")
    print(f"   Why: {POLICY_MATRIX['AZ'].rationale}")

    print("\n2. Diagnosis: where each class sits today")
    by_class = travel_by_class(picks, dataset.assignment, dataset.layout, classified["abc"])
    print(by_class.round(2).to_string(index=False))
    spread = by_class["mean_distance_per_pick_m"].max() - by_class["mean_distance_per_pick_m"].min()
    print(f"\n   Spread between the best and worst placed class: {spread:.1f} m per pick.")
    print("   Class A is not closer than class C. The warehouse is slotted at random, which is")
    print("   what happens when items go wherever there was space on the day they arrived.")

    print("\n3. Three ranking rules against the current state")
    cube = dataset.catalog.set_index("sku")["case_volume_m3"]
    strategies = {
        "current (as received)": dataset.assignment,
        "by revenue": reslot(-classified["annual_value"], dataset.layout, cube=cube),
        "by popularity": reslot(-picks, dataset.layout, cube=cube),
        "by cube-per-order index": reslot(
            cube_per_order_index(picks, cube), dataset.layout, cube=cube
        ),
    }
    table = compare_strategies(picks, dataset.layout, strategies, baseline="current (as received)")
    print(
        table[
            [
                "strategy",
                "mean_distance_per_pick_m",
                "p90_distance_per_pick_m",
                "change_vs_baseline",
            ]
        ]
        .round(4)
        .to_string(index=False)
    )

    rules = table.loc[table["strategy"] != "current (as received)", "change_vs_baseline"]
    print(f"\n   Every rule recovers between {-rules.max():.1%} and {-rules.min():.1%}.")
    print(f"   The spread between the best and the worst rule is {rules.max() - rules.min():.1%}.")
    print("\n   Read that carefully before funding an optimisation project. The decision worth")
    print("   money is whether to re-slot at all; the choice of rule is a rounding error next")
    print("   to it. A project scoped around the algorithm optimises the wrong variable.")

    print("\n4. Two results worth stating plainly rather than hiding")
    ranks = picks.rank().corr(classified["annual_value"].reindex(picks.index).rank())
    print("   Ranking by revenue loses to ranking by picks, but only just: the two rankings")
    print(f"   correlate at {ranks:.2f} on this assortment. Revenue is a usable proxy for")
    print("   velocity here; it stops being one wherever price and pick frequency diverge, and")
    print("   that has to be checked rather than assumed.")
    print("\n   The cube-per-order index comes last. That is correct, not a defect: with one")
    print("   face per SKU and uniform face capacity, every item consumes the same space, so")
    print("   cube carries no information about the objective and pricing it in only adds")
    print("   noise. COI earns its keep when items span several faces or faces differ in size,")
    print("   which is the regime the capacity simulation in a later wave models.")


if __name__ == "__main__":
    main()
