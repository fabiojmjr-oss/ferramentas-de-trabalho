"""A customer wants a service level with penalties attached. Sign it, or counter?

Run:
    python studies/04_commit_to_a_promise.py

The three studies before this one reason about claims already made: candidates the operation put
forward, signals its own reporting produced, a proposal that arrived from outside. This one makes a
claim the operation will be held to, which is a different position to reason from - being wrong
here is not an analytical error, it is a penalty payment.

The ask: **99% fill rate, a 24-hour delivery window, penalties for breach.**

What the measurements say is that the largest item on the table is not operational capability. It
is the wording. The same order book delivers 90.03% or 98.26% depending on which fill-rate basis
the contract names, the same promise costs 82% more in stock depending on which service definition
it means, and one policy sized for 99% breaches a 99% cycle-service clause while comfortably
clearing a 99% fill-rate clause. None of that is a trick to be used; all of it is a dispute waiting
to happen unless it is written down.
"""

from __future__ import annotations

import pandas as pd

from oplab.forecast import to_panel
from oplab.inventory import (
    achieved_curve,
    expected_fill_rate,
    fit_demand,
    fit_lead_time,
    safety_stock,
    z_for_cycle_service,
    z_for_fill_rate,
)
from oplab.inventory.normal import norm_cdf
from oplab.kpi import fill_rate, service_sensitivity
from oplab.routing import one_day, window_cost
from oplab.routing.fleet import VAN
from oplab.synth import generate_dataset

SITE = "CD-SP"
ROUTING_DATE = "2025-06-11"
PROMISE = 0.99
COVER_DAYS = 28
TARGETS = (0.95, 0.98, 0.99, 0.995)
WINDOW_BUDGETS = (20, 60, 120, 300)


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    dataset = generate_dataset()

    print("THE ASK")
    print(f"   {PROMISE:.0%} fill rate. A 24-hour delivery window. Penalties for breach.")
    print("   Commercial wants it signed this week. The question is what is being signed.")

    print("\n" + "=" * 96)
    print("CHECK 1 - WHICH 99%? THE WORDING IS THE LARGEST ITEM ON THE TABLE")
    print("=" * 96)
    bases = _check_definition(dataset)

    print("\n" + "=" * 96)
    print("CHECK 2 - THE SAME PROMISE, PRICED TWO WAYS")
    print("=" * 96)
    sized = _check_price(dataset)

    print("\n" + "=" * 96)
    print("CHECK 3 - SIZING FOR A LEVEL IS NOT DELIVERING IT")
    print("=" * 96)
    delivered = _check_delivery(dataset)

    print("\n" + "=" * 96)
    print("CHECK 4 - WHAT THE 24-HOUR WINDOW COSTS, AND HOW SURE WE ARE")
    print("=" * 96)
    window = _check_window(dataset)

    print("\n" + "=" * 96)
    print("WHAT TO SIGN")
    print("=" * 96)
    _counter(bases, sized, delivered, window)


def _check_definition(dataset: object) -> dict[str, float]:
    rates = {
        basis: float(fill_rate(dataset.order_lines, basis=basis))
        for basis in ("unit", "line", "order")
    }
    conventions = service_sensitivity(dataset.order_lines)
    convention_spread = float(conventions["otif"].max() - conventions["otif"].min())
    basis_spread = rates["unit"] - rates["order"]

    print(
        pd.DataFrame({"fill rate basis": list(rates), "delivered today": list(rates.values())})
        .round(4)
        .to_string(index=False)
    )
    print(
        f"\n   One order book, three defensible readings of the same words,"
        f" {basis_spread * 100:.1f} points apart."
    )
    print(
        f"   Against the asked-for {PROMISE:.0%}: on a unit basis the operation is already within"
        f" {(PROMISE - rates['unit']) * 100:.2f} points."
    )
    print(
        f"   On an order basis it is {(PROMISE - rates['order']) * 100:.1f} points short, and no"
        " programme in this"
    )
    print("   repository closes that in a year.")

    print("\n   The same is true of the delivery half of the promise:")
    print(conventions[["policy", "otif", "definition"]].to_string(index=False))
    print(
        f"\n   {convention_spread * 100:.1f} points between the strictest and the most tolerant"
        " convention, with no"
    )
    print("   change to the operation. A contract that says '99% fill rate, 24-hour window' and")
    print("   nothing else has not specified anything: it has deferred the specification to")
    print("   whoever writes the first report, and that is decided later by whoever is losing.")
    return {"basis_spread": basis_spread, "convention_spread": convention_spread, **rates}


def _check_price(dataset: object) -> dict[str, float]:
    demand, lead, unit_cost, quantity, sigma = _item(dataset)
    z_cycle = z_for_cycle_service(PROMISE)
    z_fill = z_for_fill_rate(PROMISE, sigma, quantity)
    as_cycle = safety_stock(demand, lead, z_cycle)
    as_fill = safety_stock(demand, lead, z_fill)

    print(
        pd.DataFrame(
            {
                "reading": ["'99%' as cycle service", "'99%' as fill rate"],
                "z": [z_cycle, z_fill],
                "safety_units": [as_cycle.units, as_fill.units],
                "safety_capital": [as_cycle.units * unit_cost, as_fill.units * unit_cost],
                "implied_fill_rate": [
                    expected_fill_rate(z_cycle, sigma, quantity),
                    PROMISE,
                ],
                "implied_cycle_service": [PROMISE, norm_cdf(z_fill)],
            }
        )
        .round(4)
        .to_string(index=False)
    )
    difference = as_cycle.units / as_fill.units - 1
    print(
        f"\n   Same number, same word, {difference:+.1%} of working capital between the two"
        " readings."
    )
    print("   Cycle service is the probability of not running out in a cycle; fill rate is the")
    print("   share of demand met. The customer almost certainly means the second - they care")
    print("   about lines they did not get, not about cycles they never saw - and the second is")
    print("   the cheaper commitment. Volunteering the expensive reading is not prudence, it is")
    print("   a self-inflicted cost that also weakens the negotiation on price.")
    return {"difference": difference, "as_cycle": as_cycle.units, "as_fill": as_fill.units}


def _check_delivery(dataset: object) -> dict[str, float]:
    demand, lead, unit_cost, quantity, _ = _item(dataset)
    curve = achieved_curve(
        demand,
        lead,
        quantity,
        unit_cost,
        _series(dataset),
        targets=TARGETS,
        periods=1095,
        replications=40,
    ).set_index("cycle_service_target")
    print(
        curve[
            [
                "safety_capital",
                "capital_per_point",
                "achieved_cycle_service",
                "achieved_fill_rate",
            ]
        ]
        .round(4)
        .to_string()
    )

    row = curve.loc[PROMISE]
    cycle_gap = PROMISE - float(row["achieved_cycle_service"])
    print(
        f"\n   Size the policy for {PROMISE:.0%} cycle service and the simulation delivers"
        f" {row['achieved_cycle_service']:.4f}"
    )
    print(
        f"   - {cycle_gap * 100:.2f} points short. A penalty clause pays on what was delivered, not"
        " on what the"
    )
    print("   policy was sized for, so that contract is in breach on a policy built to meet it.")
    print(
        f"\n   The same policy delivers {row['achieved_fill_rate']:.4f} on fill rate, which clears"
        f" {PROMISE:.0%} with"
    )
    print(
        f"   {(float(row['achieved_fill_rate']) - PROMISE) * 100:.2f} points to spare. **One"
        " policy, two contracts, one breach and one"
    )
    print("   comfortable margin** - decided by which word is in the clause and by nothing the")
    print("   operation does differently.")
    top = float(curve.loc[0.995, "capital_per_point"])
    mid = float(curve.loc[0.98, "capital_per_point"])
    print(f"\n   And the last half-point is the expensive one: {top:.2f} per point against")
    print(f"   {mid:.2f} at 98%. Promising the level you can only just size for means buying the")
    print("   most expensive points on the curve in order to breach anyway.")
    return {
        "achieved_cycle": float(row["achieved_cycle_service"]),
        "achieved_fill": float(row["achieved_fill_rate"]),
        "cycle_gap": cycle_gap,
        "per_point_top": float(curve.loc[0.995, "capital_per_point"]),
    }


def _check_window(dataset: object) -> dict[str, float]:
    problem = one_day(dataset.deliveries, SITE, ROUTING_DATE)
    rows = []
    for budget in WINDOW_BUDGETS:
        priced = window_cost(problem, VAN, solution_limit=budget).set_index("case")
        rows.append(
            {
                "search budget": budget,
                "premium_vs_open": float(priced.loc["windows enforced", "premium_vs_open"]),
                "extra_vehicles": float(
                    priced.loc["windows enforced", "vehicles_used"]
                    - priced.loc["windows opened", "vehicles_used"]
                ),
            }
        )
    table = pd.DataFrame(rows)
    print(table.round(4).to_string(index=False))

    thorough = float(table.loc[table["search budget"] == 300, "premium_vs_open"].iloc[0])
    cheapest = float(table["premium_vs_open"].min())
    highest = float(table["premium_vs_open"].max())

    print(
        f"\n   At a budget allowed to look properly the window costs {thorough:.1%} and no extra"
        " vehicle."
    )
    print(
        f"   Across the sweep the same comparison prices it anywhere from {cheapest:.1%} to"
        f" {highest:.1%},"
    )
    print("   and not monotonically.")

    print(
        f"\n   Read the first row again. A premium of {cheapest:.1%} says the delivery window is"
        " cheaper"
    )
    print("   than not having it, while spending an extra van on it. That cannot be true: the open")
    print("   problem is the constrained one with a restriction removed, so its optimum cannot be")
    print("   higher. A negative premium is not a small saving - it is proof that at least one of")
    print("   the two solves is nowhere near optimal.")
    print("\n   So the premium is a difference between two errors, not a measurement with a bias.")
    print("   Until both sides are searched properly the difference has no reliable sign, which")
    print("   is a stronger statement than the one this repository used to make about it - and a")
    print("   correction that was found here, with the number already on its way to a customer.")
    print("\n   In an internal review that is an embarrassment. In a negotiation it is a position")
    print("   you cannot defend: quote any single row without saying how it was produced and the")
    print("   customer is entitled to ask, and one of the rows would have you conceding that your")
    print("   own service promise costs you nothing.")
    return {"good": thorough, "cheapest": cheapest, "highest": highest}


def _item(dataset: object) -> tuple[object, object, float, int, float]:
    """The representative item every priced figure in this study is built on."""
    series = _series(dataset)
    demand = fit_demand(series.to_numpy())
    orders = dataset.purchase_orders
    supplier = orders.drop_duplicates("sku").set_index("sku")["supplier"][series.name]
    group = orders.loc[orders["supplier"] == supplier]
    lead = fit_lead_time(
        group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
    )
    unit_cost = float(dataset.catalog.set_index("sku").loc[series.name, "unit_cost"])
    quantity = round(demand.mean * COVER_DAYS)
    sigma = safety_stock(demand, lead, 1.0).sigma
    return demand, lead, unit_cost, quantity, sigma


def _series(dataset: object) -> pd.Series:
    panel = to_panel(
        dataset.demand.loc[dataset.demand["site"].astype(str) == SITE], freq="D", key=("sku",)
    )
    regular = panel.loc[:, (panel == 0).mean() <= 0.2]
    return regular[regular.sum().sort_values(ascending=False).index[20]]


def _counter(
    bases: dict[str, float],
    sized: dict[str, float],
    delivered: dict[str, float],
    window: dict[str, float],
) -> None:
    print(
        pd.DataFrame(
            [
                {
                    "term": "the fill-rate basis",
                    "worth": f"{bases['basis_spread'] * 100:.1f} points",
                    "position": "name it: unit basis, cancellations excluded",
                },
                {
                    "term": "the service definition",
                    "worth": f"{sized['difference']:.0%} of the buffer",
                    "position": "name it: fill rate, not cycle service",
                },
                {
                    "term": "the committed level",
                    "worth": f"{delivered['cycle_gap'] * 100:.2f} points of breach risk",
                    "position": "commit below what you can size for",
                },
                {
                    "term": "the delivery window",
                    "worth": f"{window['good']:.1%} of freight, at a defensible budget",
                    "position": "price separately, state the method",
                },
            ]
        ).to_string(index=False)
    )

    print("\n   Every one of the four largest items is a wording decision rather than an")
    print("   operational one. That is the finding, and it is uncomfortable: a year of")
    print(
        f"   operational programmes in this repository moves service by less than the"
        f" {bases['convention_spread'] * 100:.1f} points"
    )
    print("   that the choice of convention moves it, for free, on the same data.")

    print("\n   Which is exactly why the recommendation is to write the definitions down rather")
    print("   than to exploit them. A definitional advantage the counterparty has not understood")
    print("   is not a win, it is a dispute with a delay on it - and the delay ends at the first")
    print("   penalty invoice, with the relationship as the collateral. The asymmetry is also")
    print("   symmetric: the customer can discover a stricter reading as easily as we can find a")
    print("   kinder one, and the party who wrote nothing down has no answer either way.")

    print("\n   So: sign a clause that states the basis, the exclusions, the measurement window")
    print("   and who computes it. Commit to a level held with margin rather than the level the")
    print(
        f"   policy can just reach - the measured gap at {PROMISE:.0%} is"
        f" {delivered['cycle_gap'] * 100:.2f} points and the top half-point"
    )
    print(
        f"   costs {delivered['per_point_top']:.0f} per point. Price the window as a separate line"
        " with the search budget"
    )
    print("   of the estimate on the record.")

    print("\n   What would change this. The definitional spread is a property of this order book:")
    print("   an operation with few multi-line orders would see the three fill-rate bases")
    print("   converge, and then the wording would stop being the largest item and capability")
    print("   would take its place. That is one measurement, and it is the one to take before")
    print("   the next contract rather than after it.")


if __name__ == "__main__":
    main()
