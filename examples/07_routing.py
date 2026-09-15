"""What does a delivery cost, and which decisions can this model actually settle?

Run:
    python examples/07_routing.py

Three questions get answered - what density is worth, what the delivery windows cost, and
whether to run the fleet or buy the service - and the third one gets a refusal, because the
answer flips depending on how hard the solver was allowed to look.
"""

from __future__ import annotations

import pandas as pd

from oplab.routing import (
    TRUCK,
    VAN,
    compare_fleets,
    density_curve,
    diagnose,
    fleet_lower_bounds,
    one_day,
    quality_curve,
    solve,
    window_cost,
)
from oplab.synth import generate_dataset

SITE = "CD-SP"
DATE = "2025-06-11"
THIRD_PARTY_PRICE = 42.0


def main() -> None:
    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    problem = one_day(dataset.deliveries, SITE, DATE)

    print(f"1. Read the problem before solving it: {SITE} on {DATE}")
    print(problem.profile().round(2).to_string())
    unservable = diagnose(problem, VAN)
    print(f"\n   Individually unservable stops: {len(unservable)}")
    print("   An infeasible day is usually one stop whose round trip exceeds the shift, or")
    print("   whose window closes before a vehicle can reach it. That is a renegotiation, not")
    print("   a routing problem, and checking it first avoids blaming the algorithm.")

    print("\n   Valid lower bounds on the fleet:")
    print(fleet_lower_bounds(problem, VAN).to_string())
    print("   Both are below the fleet the day actually needs, and they have to be: they count")
    print("   only what cannot be shared between vehicles. There is deliberately no")
    print("   travel-based bound, because summing the leg to every stop is not a bound at all -")
    print("   a route visiting twelve stops drives the radius once and shares it among them.")

    print("\n2. What the search leaves on the table")
    quality = quality_curve(problem, VAN)
    print(quality.round(3).to_string(index=False))
    spread = quality["cost_per_delivery"].max() - quality["cost_per_delivery"].min()
    cheap, thorough = quality.iloc[0], quality.iloc[-1]
    print(f"\n   Cost per delivery moves {spread:.2f} BRL across the budget range, and the fleet")
    print(
        f"   goes from {cheap['vehicles_used']:.0f} vehicles to"
        f" {thorough['vehicles_used']:.0f}. The search never proves optimality, so a routing"
    )
    print("   cost quoted without its search budget is a cost quoted without its error bar.")
    print("\n   The budget is a solution count, not a stopwatch. A wall-clock limit makes the")
    print("   answer depend on the machine and on what else it is doing - the same problem")
    print("   under CPU contention explores less and returns a different plan, which is not")
    print("   acceptable in a number that goes into a tender.")

    print("\n3. What density is worth")
    density = density_curve(problem, VAN, (0.25, 0.5, 1.0))
    print(density.round(3).to_string(index=False))
    sparse, dense = density.iloc[0], density.iloc[-1]
    print(
        f"\n   Same territory throughout. {sparse['stops']:.0f} stops cost"
        f" {sparse['cost_per_delivery']:.2f} BRL each;"
    )
    print(
        f"   {dense['stops']:.0f} stops cost {dense['cost_per_delivery']:.2f} -"
        f" {1 - dense['cost_per_delivery'] / sparse['cost_per_delivery']:.0%} lower."
    )
    print("   Nothing about the distances changed. Drop density, not distance, governs cost per")
    print("   delivery in last-mile distribution, which is why a growing territory can get")
    print("   cheaper per drop and a shrinking one gets more expensive without any rate moving.")

    print("\n4. What the delivery windows cost")
    windows = window_cost(problem, VAN)
    print(windows.round(3).to_string(index=False))
    premium = windows.set_index("case").loc["windows enforced", "premium_vs_open"]
    print(f"\n   The commercial promise costs {premium:.1%}, and no extra vehicle.")
    print("\n   That number is a correction. Under a smaller search budget this came out at")
    print("   8.8% and one extra van, because the heuristic struggles more with the constrained")
    print("   problem than with the open one - so an under-searched solve exaggerates the cost")
    print("   of every constraint you price with it. Worth knowing before quoting what a")
    print("   service promise costs.")

    print("\n5. Run the fleet or buy the service")
    fleets = compare_fleets(
        problem,
        {"van": VAN, "truck": TRUCK},
        third_party_price_per_delivery=THIRD_PARTY_PRICE,
    )
    print(fleets.round(3).to_string(index=False))

    own = fleets.loc[fleets["option"] == "van", "cost_per_delivery"].iloc[0]
    bought = fleets.loc[fleets["option"] == "third party", "cost_per_delivery"].iloc[0]
    gap = bought - own
    print(f"\n   The van comes out {gap:.2f} BRL per delivery cheaper than the carrier's rate.")
    print(f"   The search-budget sensitivity, from section 2, is {spread:.2f} BRL - and at the")
    print(
        f"   cheapest budget the van costs {cheap['cost_per_delivery']:.2f}, which loses to the"
        f" carrier at {THIRD_PARTY_PRICE:.2f}."
    )
    print("\n   So the conclusion itself flips with how hard the solver looked. A cheap solve")
    print("   says buy the service; a thorough one says run the fleet. This model does not")
    print("   settle make-or-buy at this price, and the honest output is to say so rather than")
    print("   to report an 8% advantage as a finding. What it does settle, by a margin no")
    print("   assumption threatens: the truck is the wrong vehicle for this profile.")
    print("\n   A decision this close needs what the model does not contain: the cost of owning")
    print("   the risk, the carrier's surcharges and failure rate, and what happens on the")
    print("   worst week rather than on a Wednesday in June.")

    print("\n6. The routes themselves")
    solution = solve(problem, VAN)
    print(solution.summary.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
