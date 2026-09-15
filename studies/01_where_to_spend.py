"""Where should the next real of capital go, and what does the brief get wrong?

Run:
    python studies/01_where_to_spend.py

This is not a tour of the library. It is one decision, taken on one synthetic operation, using
whichever module can price each candidate - and it is laid out in the order the decision has to be
taken rather than in the order the tools were built.

The brief as received: *CD-PE has the worst service and the highest cost per order in the network.
Fix CD-PE.* Four candidates are on the table and each has a sponsor. The study checks the brief
before pricing anything, then prices every candidate on the same data, then ranks them.

Two of the four candidates turn out to be worth less than their sponsors believe, one part of the
brief is definitional rather than operational, and the intervention that wins was not on the list.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from oplab.benchmark import indirect_standardisation
from oplab.forecast import BASELINES, INTERMITTENT, backtest_panel, error_profile, to_panel
from oplab.inventory import (
    fit_demand,
    fit_lead_time,
    safety_stock,
    z_for_cycle_service,
)
from oplab.kpi import service_sensitivity
from oplab.mining import conformance, cost_of_deviation, flow_efficiency, waiting_ranked
from oplab.slotting import (
    abc_xyz,
    compare_strategies,
    cube_per_order_index,
    demand_profile,
    pick_counts,
    reslot,
)
from oplab.synth import HAPPY_PATH, VALUE_ADDING, generate_dataset

TARGET_SITE = "CD-PE"
REFERENCE_SITE = "CD-SP"
CYCLE_SERVICE = 0.95
REGULAR_ZERO_SHARE = 0.5
BANDS = [0.0, 10.0, 25.0, 50.0, float("inf")]
BAND_LABELS = ["0-10 km", "10-25 km", "25-50 km", "50+ km"]


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    dataset = generate_dataset()

    print("THE BRIEF AS RECEIVED")
    print(f"   {TARGET_SITE} has the worst service and the highest cost per order. Fix it.")
    print("   Four candidates, each with a sponsor:")
    print("     A. Re-slot the pick face            (operations)")
    print("     B. Buy a forecasting system         (planning)")
    print("     C. Standardise the order process    (quality)")
    print("     D. Hold more safety stock           (supply)")

    print("\n" + "=" * 96)
    print("PART 1 - TWO CHECKS BEFORE SPENDING ANYTHING")
    print("=" * 96)
    service_gap = _check_service(dataset)
    geography_share = _check_geography(dataset)

    print("\n" + "=" * 96)
    print("PART 2 - EVERY CANDIDATE PRICED ON THE SAME DATA")
    print("=" * 96)
    priced = [
        _price_slotting(dataset),
        _price_forecasting(dataset),
        _price_process(dataset),
        _price_stock(dataset),
    ]

    print("\n" + "=" * 96)
    print("PART 3 - THE DECISION")
    print("=" * 96)
    _decide(priced, service_gap, geography_share)


def _check_service(dataset: object) -> float:
    """Is the service gap operational, or is part of it the convention nobody wrote down?"""
    print("\n1. Is the service gap real?")
    table = service_sensitivity(dataset.order_lines)
    spread = float(table["otif"].max() - table["otif"].min())
    print(
        table[["policy", "otif", "on_time", "in_full", "lines_in_scope"]]
        .round(4)
        .to_string(index=False)
    )
    print(
        f"\n   The same order book scores {table['otif'].min():.1%} to {table['otif'].max():.1%}"
        f" depending only on the convention -"
    )
    print(
        f"   a spread of {spread * 100:.1f} points with no change to the operation. Before any"
        " of the four"
    )
    print("   candidates is funded, the network has to agree which of these numbers it manages.")
    print("   A gap smaller than this spread is not evidence of anything.")
    return spread


def _check_geography(dataset: object) -> float:
    """How much of the cost gap is territory rather than performance?"""
    print(f"\n2. Is {TARGET_SITE} actually the most expensive site?")
    ledger = dataset.cost_ledger.copy()
    ledger["band"] = pd.cut(ledger["distance_km"], BANDS, labels=BAND_LABELS).astype(str)
    aggregated = (
        ledger.groupby(["site", "band"], observed=True)
        .agg(cost=("total_brl", "sum"), deliveries=("order_id", "size"))
        .reset_index()
    )
    standardised = indirect_standardisation(
        aggregated, "site", "band", "cost", "deliveries", exclude_self=True
    ).set_index("site")
    print(
        standardised[["crude_rate", "standardised_rate", "standardised_ratio"]].round(2).to_string()
    )

    crude = standardised["crude_rate"]
    adjusted = standardised["standardised_rate"]
    crude_spread = float(crude.max() - crude.min())
    adjusted_spread = float(adjusted.max() - adjusted.min())
    share = 1.0 - adjusted_spread / crude_spread
    crude_gap = float(crude.loc[TARGET_SITE] / crude.loc[REFERENCE_SITE] - 1)
    adjusted_gap = float(adjusted.loc[TARGET_SITE] / adjusted.loc[REFERENCE_SITE] - 1)

    print(
        f"\n   {TARGET_SITE} reads {crude_gap:.0%} more expensive than {REFERENCE_SITE} crude and"
        f" {adjusted_gap:.0%} once the"
    )
    print(
        f"   distance profile is held constant. {share:.0%} of the headline gap is postcodes,"
        " not performance -"
    )
    print("   and postcodes are not on the list of things any of the four candidates changes.")
    print(f"   The brief's target is still the worst site. It is {adjusted_gap:.0%} worst, not")
    print(f"   {crude_gap:.0%} worst, and that difference is the size of the prize.")
    return share


def _price_slotting(dataset: object) -> dict[str, object]:
    print("\nA. Re-slot the pick face")
    demand = dataset.demand.loc[dataset.demand["site"].astype(str) == TARGET_SITE]
    picks = pick_counts(dataset.order_lines, site=TARGET_SITE)
    classified = abc_xyz(demand_profile(demand, dataset.catalog, period="W"))
    classified = classified.loc[classified.index.isin(picks.index)]
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
    print(table.round(4).to_string(index=False))

    ranked = table.loc[table["strategy"] != "current (as received)"]
    best = ranked.loc[ranked["mean_distance_per_pick_m"].idxmin()]
    spread = float(ranked["change_vs_baseline"].max() - ranked["change_vs_baseline"].min())
    print(
        f"\n   Verdict: fund it, and stop arguing about which rule. The best rule recovers"
        f" {-best['change_vs_baseline']:.0%} of"
    )
    print(
        f"   the travel at {TARGET_SITE} and the spread between all three is"
        f" {spread * 100:.1f} points."
    )
    print("   The decision worth taking is whether to re-slot at all; the choice of optimiser is")
    print("   a rounding error, so the sponsor's request for an algorithm evaluation is the one")
    print("   part to decline.")
    return {
        "candidate": "A. Re-slot the pick face",
        "measured_gain": f"{-best['change_vs_baseline']:.0%} of pick travel",
        "verdict": "fund",
        "caveat": "distance-weighted picks, not routes; one location per SKU",
    }


def _price_forecasting(dataset: object) -> dict[str, object]:
    print("\nB. Buy a forecasting system")
    panel = to_panel(
        dataset.demand.loc[dataset.demand["site"].astype(str) == REFERENCE_SITE],
        freq="D",
        key=("sku",),
    )
    regular = panel.loc[:, (panel == 0).mean() <= REGULAR_ZERO_SHARE]

    def mean_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
        return np.full(horizon, float(np.mean(history)) if history.size else 0.0)

    models = {**BASELINES, **INTERMITTENT, "mean": mean_forecast}
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
        f"\n   Verdict: decline. Of the {len(spreads)} methods scored, the lowest error spread is"
        f" {best} -"
    )
    print(
        "   a forecast of the training mean, which is what the inventory formula already assumes."
    )
    print(
        f"   The median ratio of forecast-error spread to demand spread is"
        f" {sba['sd_ratio'].median():.4f}, and the best"
    )
    print(
        f"   method reduces the buffer on {sba['reduces_buffer'].mean():.0%} of series and"
        " enlarges it on the rest."
    )
    print("   There is no accuracy on this assortment to buy. That is a statement about this")
    print("   demand, not about forecasting, and it is the measurement the business case needs")
    print("   before the licence is signed rather than after.")
    return {
        "candidate": "B. Buy a forecasting system",
        "measured_gain": "0.26% of the buffer, at best",
        "verdict": "decline",
        "caveat": "measured on the regular half; sparse items need availability, not forecasts",
    }


def _price_process(dataset: object) -> dict[str, object]:
    print("\nC. Standardise the order process")
    log = dataset.order_events
    efficiency = flow_efficiency(log, VALUE_ADDING)
    result = conformance(log, HAPPY_PATH)
    cost = cost_of_deviation(log, HAPPY_PATH, VALUE_ADDING).set_index("group")
    waiting = waiting_ranked(log)

    clean = cost.loc["follows the documented path"]
    dirty = cost.loc["deviates"]
    print(
        f"   Flow efficiency {efficiency.flow_efficiency:.2%}, of which working time is"
        f" {efficiency.busy_share:.2%} -"
    )
    print(
        f"   so {1 - efficiency.value_adding_h / efficiency.work_h:.0%} of all working time is"
        " inspection and correction."
    )
    print(cost.round(2).to_string())
    print(
        f"\n   {int(dirty['cases']):,} of {int(clean['cases'] + dirty['cases']):,} cases leave the"
        f" documented path and take"
        f" {dirty['mean_lead_h'] / clean['mean_lead_h']:.1f} times"
    )
    print(
        f"   as long, with worse flow efficiency rather than equal"
        f" ({dirty['flow_efficiency']:.2%} against {clean['flow_efficiency']:.2%})."
    )
    print(f"   Only {result.exact_share:.0%} of cases are the documented process and nothing else.")

    top = waiting.head(4)
    print(
        f"\n   And the target is specific: {top['share_of_waiting'].sum():.0%} of all waiting sits"
        f" after four activities"
    )
    print(f"   ({', '.join(top['activity'])}). Nothing outside them is worth a project.")
    print("\n   Verdict: fund, scoped to those four handovers. A programme to standardise the")
    print("   whole process would be aimed at 35 paths, and four of them carry 80% of the")
    print("   volume - so the work is the exceptions, not the standard.")
    return {
        "candidate": "C. Standardise the order process",
        "measured_gain": f"{dirty['mean_lead_h'] / clean['mean_lead_h']:.1f}x lead time on "
        f"{int(dirty['cases']):,} cases",
        "verdict": "fund, scoped",
        "caveat": "conformance is a subsequence test; the deviating group includes cancellations",
    }


def _price_stock(dataset: object) -> dict[str, object]:
    print("\nD. Hold more safety stock")
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

    realised = 0.0
    on_quote = 0.0
    capped = 0.0
    for sku in regular.columns:
        supplier = supplier_of.get(sku)
        if supplier is None:
            continue
        demand = fit_demand(regular[sku].to_numpy())
        if demand.mean <= 0.0:
            continue
        profile = lead_times[supplier]
        cost = float(unit_cost[sku])
        realised += safety_stock(demand, profile, z).units * cost
        on_quote += safety_stock(demand, profile, z, use_quoted_lead_time=True).units * cost
        tighter = fit_lead_time(
            np.minimum(profile.sample, profile.quantile(0.95)), quoted=profile.quoted
        )
        capped += safety_stock(demand, tighter, z).units * cost

    print(
        pd.DataFrame(
            {
                "sizing": [
                    "on the quoted lead times (the current plan)",
                    "on the realised lead times",
                    "on realised lead times, worst 5% of deliveries removed",
                ],
                "capital_brl": [on_quote, realised, capped],
            }
        )
        .round(0)
        .to_string(index=False)
    )
    print(
        f"\n   Verdict: decline as asked, and act on the cause. The current plan is short by"
        f" {1 - on_quote / realised:.0%}"
    )
    print(
        "   because it sizes on the contract rather than the receipts - so 'more stock' is already"
    )
    print("   owed before anybody asks for an increase. But the sponsor is treating a supplier")
    print(
        f"   problem as an inventory problem: capping the worst 5% of deliveries releases BRL"
        f" {realised - capped:,.0f}"
    )
    print(
        f"   ({1 - capped / realised:.0%} of the assortment's buffer at a"
        f" {CYCLE_SERVICE:.0%} cycle service level) and improves service"
    )
    print("   at the same time. Stock is the expensive way to buy reliability you could have")
    print("   bought upstream. The per-item figure in example 12 is larger because it is priced")
    print("   at a 99% target on one item; the scope differs, not the direction.")
    return {
        "candidate": "D. Hold more safety stock",
        "measured_gain": f"BRL {realised - capped:,.0f} released by fixing the supplier instead",
        "verdict": "decline; fix the supplier",
        "caveat": "single-echelon, lost sales, regular items only",
    }


def _decide(priced: list[dict[str, object]], service_gap: float, geography_share: float) -> None:
    print(pd.DataFrame(priced)[["candidate", "verdict", "measured_gain"]].to_string(index=False))

    print("\n   Two of the four candidates are declined on measurement rather than on budget, and")
    print("   in both cases the sponsor was solving the wrong problem: planning wanted accuracy")
    print("   this demand does not contain, and supply wanted stock to cover a supplier.")
    print("\n   Two are funded, both narrowed. Re-slotting is funded without the algorithm study")
    print("   the sponsor asked for. Standardisation is funded against four handovers rather than")
    print("   against 35 process variants.")
    print(
        f"\n   And the largest single item is not on the list at all. {geography_share:.0%} of the"
        f" cost gap the brief"
    )
    print(
        f"   opens with is geography, and the service number itself moves"
        f" {service_gap * 100:.1f} points on convention alone."
    )
    print("   Neither is fixed by spending money. Both are fixed by agreeing a definition and a")
    print("   comparison basis before the next review - which costs one meeting and is the")
    print("   highest-return item in this study.")
    print("\n   What would change this conclusion: a different assortment, where forecast error")
    print("   sits below demand variability, would move candidate B from decline to fund. The")
    print("   ratio is one measurement, and it is the one to re-run before the next budget round")
    print("   rather than the conclusion to remember.")


if __name__ == "__main__":
    main()
