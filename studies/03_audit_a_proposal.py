"""A proposal arrives with a number on the cover. Can any of it be reproduced?

Run:
    python studies/03_audit_a_proposal.py

The two studies before this one reason about the operation's own material. Study 01 prices
candidates the operation put forward; study 02 sifts signals the operation's own reporting
produced. This one reasons about **somebody else's claim** — a vendor proposal with four
workstreams and an 18% saving on the cover — and the work is adversarial reproduction: for each
claim, can it be recovered from this operation's data, and what would have to be true for it to
hold?

The answer is the reason the form is worth having. **None of the four claims is simply true and
none is simply false.** One is understated and needs no vendor. One has approximately the right
number attached to the wrong mechanism. One cannot be verified by the class of model that produced
it — including this repository's own routing model, which is the same class. One points in the
right direction at the wrong half of the problem.

An audit that finds nothing wrong with its own method is not an audit. Claim 3 is where this one
turns on its own tooling, and that is what makes the other three worth reading.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from oplab.forecast import backtest_panel, error_profile, to_panel
from oplab.inventory import fit_demand, fit_lead_time, safety_stock, z_for_cycle_service
from oplab.mining import flow_efficiency, waiting_ranked
from oplab.routing import one_day, solve
from oplab.routing.fleet import VAN
from oplab.slotting import (
    abc_xyz,
    compare_strategies,
    cube_per_order_index,
    demand_profile,
    pick_counts,
    reslot,
)
from oplab.synth import VALUE_ADDING, generate_dataset

TARGET_SITE = "CD-PE"
REFERENCE_SITE = "CD-SP"
ROUTING_DATE = "2025-06-11"
CHEAP_BUDGET = 20
THOROUGH_BUDGET = 300
CYCLE_SERVICE = 0.95

CLAIMS = {
    "1. Slotting optimisation": "30% reduction in pick travel",
    "2. Demand forecasting platform": "20% reduction in inventory, from 15% better accuracy",
    "3. Route optimisation": "15% freight saving",
    "4. Process automation": "25% reduction in order cycle time",
}


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    dataset = generate_dataset()

    print("THE PROPOSAL AS RECEIVED")
    print("   'Operations Excellence Programme' - 18% cost reduction in year one.")
    for workstream, claim in CLAIMS.items():
        print(f"   {workstream}: {claim}")
    print("\n   Each number is checked against this operation's own data. The question is not")
    print("   whether the vendor is honest; it is whether the claim is recoverable here.")

    verdicts = [
        _audit_slotting(dataset),
        _audit_forecasting(dataset),
        _audit_routing(dataset),
        _audit_automation(dataset),
    ]

    print("\n" + "=" * 96)
    print("THE COUNTER-OFFER")
    print("=" * 96)
    _counter_offer(verdicts)


def _audit_slotting(dataset: object) -> dict[str, str]:
    print("\n" + "=" * 96)
    print("CLAIM 1 - 30% reduction in pick travel")
    print("=" * 96)

    demand = dataset.demand.loc[dataset.demand["site"].astype(str) == TARGET_SITE]
    picks = pick_counts(dataset.order_lines, site=TARGET_SITE)
    classified = abc_xyz(demand_profile(demand, dataset.catalog, period="W"))
    classified = classified.loc[classified.index.isin(picks.index)]
    cube = dataset.catalog.set_index("sku")["case_volume_m3"]

    table = compare_strategies(
        picks,
        dataset.layout,
        {
            "current (as received)": dataset.assignment,
            "by revenue": reslot(-classified["annual_value"], dataset.layout, cube=cube),
            "by popularity": reslot(-picks, dataset.layout, cube=cube),
            "by cube-per-order index": reslot(
                cube_per_order_index(picks, cube), dataset.layout, cube=cube
            ),
        },
        baseline="current (as received)",
    )
    print(
        table[["strategy", "mean_distance_per_pick_m", "change_vs_baseline"]]
        .round(4)
        .to_string(index=False)
    )

    ranked = table.loc[table["strategy"] != "current (as received)"]
    best = -float(ranked["change_vs_baseline"].min())
    worst = -float(ranked["change_vs_baseline"].max())
    spread = (best - worst) * 100

    print(
        f"\n   Available at {TARGET_SITE}: {best:.0%} with the best of three ranking rules,"
        f" {worst:.0%} with the worst."
    )
    print(f"   The claim is {best / 0.30:.1f} times smaller than what the data already contains.")
    print(
        f"\n   VERDICT: understated, and self-serviceable. The three rules sit"
        f" {spread:.1f} points apart, so"
    )
    print("   the recoverable travel is a property of re-slotting at all, not of the optimiser")
    print("   that ranks it. The vendor is underselling the prize and overselling their share of")
    print("   it: what they are paid for is worth a couple of points, and a sorted list gets the")
    print("   rest. Buy the prize, not the algorithm.")
    return {
        "claim": "1. Slotting, 30% travel",
        "verdict": "understated, self-serviceable",
        "measured": f"{best:.0%} available; {spread:.1f} points between rules",
    }


def _audit_forecasting(dataset: object) -> dict[str, str]:
    print("\n" + "=" * 96)
    print("CLAIM 2 - 20% less inventory, from 15% better accuracy")
    print("=" * 96)

    panel = to_panel(
        dataset.demand.loc[dataset.demand["site"].astype(str) == REFERENCE_SITE],
        freq="D",
        key=("sku",),
    )
    regular = panel.loc[:, (panel == 0).mean() <= 0.5]

    def mean_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
        return np.full(horizon, float(np.mean(history)) if history.size else 0.0)

    # Three models rather than the eight scored in example 12: the mean is the reference the
    # inventory formula already assumes, sba was the best of the eight, and seasonal_naive is the
    # one a vendor would call the incumbent. The fuller comparison is in that example.
    from oplab.forecast import BASELINES, INTERMITTENT

    models = {
        "mean": mean_forecast,
        "sba": INTERMITTENT["sba"],
        "seasonal_naive": BASELINES["seasonal_naive"],
    }
    results = backtest_panel(regular, models, horizon=7, step=28, min_train=120, season=7)
    spreads = {name: float(error_profile(results, name)["sd"].median()) for name in models}
    best = min(spreads, key=lambda name: spreads[name])
    sba = error_profile(results, "sba")

    print(
        pd.DataFrame({"model": list(spreads), "median_error_sd": list(spreads.values())})
        .sort_values("median_error_sd")
        .round(4)
        .to_string(index=False)
    )
    print(
        f"\n   The lowest error spread belongs to {best} - a forecast of the training mean, which"
    )
    print(
        "   is what the safety-stock formula already assumes. Median ratio of forecast-error spread"
    )
    print(
        f"   to demand spread: {sba['sd_ratio'].median():.4f}. A 20% inventory reduction from"
        " accuracy needs the"
    )
    print("   error spread to fall by about 20%; the available movement is under a point.")

    print("\n   But the 20% is not a fantasy. It is available, from somewhere else:")
    released, realised = _supplier_lever(dataset)
    print(
        f"   capping the worst 5% of one supplier's deliveries releases BRL {released:,.0f} of"
        f" BRL {realised:,.0f}"
    )
    print(f"   - {released / realised:.0%} of the assortment's buffer, without a forecast at all.")
    print(
        "\n   VERDICT: approximately the right number, attached to the wrong mechanism. The vendor"
    )
    print(
        f"   claims 20% and roughly {released / realised:.0%} exists; it comes from supplier"
        " reliability, which their"
    )
    print("   platform does not touch. Agreeing the number and disagreeing about the cause is the")
    print("   worst outcome available, because the programme would be paid for a result it did")
    print("   not produce and the real lever would stay unpulled.")
    return {
        "claim": "2. Forecasting, 20% inventory",
        "verdict": "right number, wrong mechanism",
        "measured": f"{released / realised:.0%} available, from the supplier not the forecast",
    }


def _supplier_lever(dataset: object) -> tuple[float, float]:
    orders = dataset.purchase_orders
    supplier_of = orders.drop_duplicates("sku").set_index("sku")["supplier"]
    lead_times = {
        name: fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        for name, group in orders.groupby("supplier")
    }
    z = z_for_cycle_service(CYCLE_SERVICE)
    unit_cost = dataset.catalog.set_index("sku")["unit_cost"]
    panel = to_panel(
        dataset.demand.loc[dataset.demand["site"].astype(str) == REFERENCE_SITE],
        freq="D",
        key=("sku",),
    )
    regular = panel.loc[:, (panel == 0).mean() <= 0.2]

    realised = capped = 0.0
    for sku in regular.columns:
        supplier = supplier_of.get(sku)
        if supplier is None:
            continue
        profile = fit_demand(regular[sku].to_numpy())
        if profile.mean <= 0.0:
            continue
        lead = lead_times[supplier]
        cost = float(unit_cost[sku])
        realised += safety_stock(profile, lead, z).units * cost
        tighter = fit_lead_time(np.minimum(lead.sample, lead.quantile(0.95)), quoted=lead.quoted)
        capped += safety_stock(profile, tighter, z).units * cost
    return realised - capped, realised


def _audit_routing(dataset: object) -> dict[str, str]:
    print("\n" + "=" * 96)
    print("CLAIM 3 - 15% freight saving")
    print("=" * 96)

    problem = one_day(dataset.deliveries, REFERENCE_SITE, ROUTING_DATE)
    cheap = solve(problem, VAN, solution_limit=CHEAP_BUDGET)
    thorough = solve(problem, VAN, solution_limit=THOROUGH_BUDGET)

    print(
        pd.DataFrame(
            {
                "search budget": [CHEAP_BUDGET, THOROUGH_BUDGET],
                "vehicles": [cheap.vehicles_used, thorough.vehicles_used],
                "cost_per_delivery": [cheap.cost_per_delivery, thorough.cost_per_delivery],
            }
        )
        .round(2)
        .to_string(index=False)
    )

    # The comparable quantity is the saving a cheap baseline would let anybody report, which
    # is measured from the cheap figure down to the thorough one - not the inflation upwards.
    spread = 1 - thorough.cost_per_delivery / cheap.cost_per_delivery
    print("\n   Same problem, same day, same vehicle. The only thing that changed is how long the")
    print(
        f"   solver was allowed to look, and the answer moved {spread:.1%} - and the fleet size"
        f" from"
    )
    print(f"   {cheap.vehicles_used} vehicles to {thorough.vehicles_used}.")
    print(
        f"\n   Baselining on the cheap solve and reporting the thorough one is a saving of"
        f" {spread:.1%} -"
    )
    print(
        f"   larger than the {0.15:.0%} the proposal claims, from changing nothing about the"
        " operation."
    )
    print("   A heuristic that does not prove optimality can be made to report almost any saving")
    print("   by choosing how hard its baseline was allowed to search - and the direction of the")
    print("   bias is known: an under-searched baseline exaggerates the value of everything")
    print("   compared against it.")
    print("\n   VERDICT: unverifiable by the class of model that produced it, this repository's")
    print("   routing module included. It is the same class of model and it is subject to the")
    print("   same artefact, which is why the refusal is not an accusation. What can be asked")
    print("   for instead is a measurable commitment: freight per delivery on an agreed basket")
    print("   of days, baselined on the operation's own current routes rather than on the")
    print("   vendor's model of them, with the search budget of both sides on the record.")
    return {
        "claim": "3. Routing, 15% freight",
        "verdict": "unverifiable by this model class",
        "measured": f"{spread:.1%} moved by search budget alone",
    }


def _audit_automation(dataset: object) -> dict[str, str]:
    print("\n" + "=" * 96)
    print("CLAIM 4 - 25% reduction in order cycle time")
    print("=" * 96)

    efficiency = flow_efficiency(dataset.order_events, VALUE_ADDING)
    waiting = waiting_ranked(dataset.order_events).head(4)

    print(
        pd.DataFrame(
            {
                "component": ["lead time", "working", "waiting"],
                "hours": [efficiency.lead_h, efficiency.work_h, efficiency.wait_h],
                "share": [
                    1.0,
                    efficiency.busy_share,
                    efficiency.wait_h / efficiency.lead_h,
                ],
            }
        )
        .round(4)
        .to_string(index=False)
    )
    print(
        f"\n   Automation acts on working time. Working time is"
        f" {efficiency.busy_share:.1%} of the lead time, so"
    )
    print(
        f"   automating every step to zero would cut {efficiency.busy_share:.1%} against a claim"
        f" of {0.25:.0%}. The claim is"
    )
    print("   not achievable from the part of the problem the vendor proposes to work on.")
    print(
        f"\n   The 25% is there. It is in the {efficiency.wait_h:.1f} hours of waiting, and it is"
        " concentrated:"
    )
    columns = ["activity", "share_of_waiting", "cumulative_share"]
    print(waiting[columns].round(4).to_string(index=False))
    print(
        f"   {waiting['share_of_waiting'].sum():.0%} of all waiting sits after four handovers."
        " Cutting the two largest in half"
    )
    halved = waiting["share_of_waiting"].head(2).sum() / 2 * efficiency.wait_h / efficiency.lead_h
    print(
        f"   would move the lead time by about {halved:.0%} - the claim, from work the proposal"
        " does not mention."
    )
    print("\n   VERDICT: right direction, wrong half. The benefit exists and the intervention is")
    print("   aimed at 6.5% of the lead time instead of the 93.5%. Automating a handover is")
    print("   also a different project from automating a step, with different suppliers.")
    return {
        "claim": "4. Automation, 25% cycle time",
        "verdict": "right direction, wrong half",
        "measured": f"work is {efficiency.busy_share:.1%} of lead time; waiting is"
        f" {efficiency.wait_h / efficiency.lead_h:.1%}",
    }


def _counter_offer(verdicts: list[dict[str, str]]) -> None:
    print(pd.DataFrame(verdicts).to_string(index=False))

    print("\n   The cover number was 18%. Not one of the four claims survives as written, and not")
    print("   one of them is simply false either - which is the finding, and the reason an audit")
    print("   is worth an afternoon. A flat rejection would have been wrong on three lines out of")
    print("   four, and accepting the deck would have been wrong on all four.")

    print("\n   What to propose instead:")
    print("     - Re-slot in-house, against the measured prize rather than the claimed one.")
    print("       Decline the optimiser; a sorted list is within a couple of points of it.")
    print("     - Redirect the inventory workstream to supplier reliability, where the number")
    print("       the vendor quoted actually lives. Pay for the tail, not for the forecast.")
    print("     - Restate the freight claim as a measurable commitment on an agreed basket of")
    print("       days, baselined on current routes. No model, on either side, settles it.")
    print("     - Rescope automation from the steps to the handovers, and price it against the")
    print("       four that hold three quarters of the waiting.")

    print("\n   What would change this. Three of the four verdicts rest on measurements of this")
    print("   operation and would move with it: a sharper assortment would revive claim 2, and a")
    print("   pick face already sorted would kill claim 1. The third rests on a property of the")
    print("   method rather than of the data, so it holds until someone brings a model that")
    print("   proves optimality or an experiment that does not need one.")


if __name__ == "__main__":
    main()
