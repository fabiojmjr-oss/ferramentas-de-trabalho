"""What does a point of service level cost, and which lever actually buys it?

Run:
    python examples/10_inventory_policy.py

Five things get established. That the lead time in the contract is not the lead time in the
receipts, and what the substitution costs. Which of the two variability terms is the lever, with
a closed-form condition for deciding. That the supplier with the shorter lead time can need more
safety stock, not less. That a service commitment expressed as a fill rate and sized as a cycle
service level is overbought by four fifths. And that the price of a point of service rises an
order of magnitude across the curve, while the cheapest point on offer is not on the curve at all.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from oplab.forecast import to_panel
from oplab.inventory import (
    ContinuousReview,
    achieved_curve,
    decompose_safety_stock,
    expected_fill_rate,
    fit_demand,
    fit_lead_time,
    lead_time_by_supplier,
    reorder_point,
    safety_stock,
    simulate_policy,
    z_for_cycle_service,
    z_for_fill_rate,
)
from oplab.inventory.normal import norm_cdf
from oplab.synth import generate_dataset

SITE = "CD-SP"
CYCLE_SERVICE = 0.95
COMMITMENT = 0.99
REGULAR_ZERO_SHARE = 0.2
COVER_DAYS = 28
HORIZON = 1095
REPLICATIONS = 40
# The measured headroom of the best of seven forecasting methods over a one-line seasonal rule,
# from examples/09_forecast_baseline.py. Reused here as the size of the demand-side lever.
FORECAST_HEADROOM = 0.008


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    orders = dataset.purchase_orders
    unit_cost = dataset.catalog.set_index("sku")["unit_cost"]

    panel = to_panel(
        dataset.demand.loc[dataset.demand["site"].astype(str) == SITE], freq="D", key=("sku",)
    )
    regular = panel.loc[:, (panel == 0).mean() <= REGULAR_ZERO_SHARE]
    supplier_of = orders.drop_duplicates("sku").set_index("sku")["supplier"]
    lead_times = {
        name: fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        for name, group in orders.groupby("supplier")
    }
    z = z_for_cycle_service(CYCLE_SERVICE)

    print("1. The lead time in the contract is not the lead time in the receipts")
    table = lead_time_by_supplier(orders)
    print(table.round(2).to_string(index=False))
    print("\n   Every supplier delivers close to its quoted mean, which is why nobody questions")
    print("   the contract. The quote says nothing at all about the second column that matters:")
    print("   one supplier's lead time varies by 46% of its own mean and another's by 13%, and")
    print("   the safety stock that covers them differs by more than the lead times do. Every")
    print("   distribution is right skewed, so the normal formula below is being asked to cover")
    print("   a tail it does not have.")

    sized = _size_assortment(regular, supplier_of, lead_times, unit_cost, z)
    print(f"\n2. What sizing on the contract costs, across {len(sized)} regular SKUs")
    summary = (
        sized.groupby("supplier")
        .agg(
            skus=("sku", "size"),
            capital=("capital", "sum"),
            capital_on_quote=("capital_on_quote", "sum"),
        )
        .assign(understated=lambda f: 1 - f["capital_on_quote"] / f["capital"])
    )
    print(summary.round(4).to_string())
    total, on_quote = sized["capital"].sum(), sized["capital_on_quote"].sum()
    print(
        f"\n   Network: BRL {total:,.0f} of safety stock is required at a {CYCLE_SERVICE:.0%} cycle"
        f" service level."
    )
    print(f"   Sized on the quoted lead times it comes to BRL {on_quote:,.0f}, which is")
    print(f"   {1 - on_quote / total:.1%} short. The plan is not slightly optimistic; it is")
    print(f"   missing {total / on_quote - 1:.0%} of the stock the service level needs, and the")
    print("   gap is invisible because both numbers are computed with the same formula.")

    print("\n3. Which variability is the lever, and how to tell without simulating")
    crossover = (
        sized.groupby("supplier")
        .agg(
            crossover_cv=("crossover_cv", "first"),
            mean_demand_cv=("demand_cv", "mean"),
            mean_lead_share=("lead_share", "mean"),
            lead_time_dominates=("lead_share", lambda s: float((s > 0.5).mean())),
        )
        .sort_values("crossover_cv")
    )
    print(crossover.round(4).to_string())
    print("\n   The combined formula has two variance terms and their ratio has a closed form.")
    print("   Lead-time variability dominates when CV_L^2 * L exceeds CV_d^2 - that is, on every")
    print("   item whose demand CV is below sqrt(CV_L^2 * L), the first column. It is a property")
    print("   of the supplier, not of the item: on this assortment the demand CV sits near")
    print(f"   {sized['demand_cv'].mean():.2f}, so lead time is the lever for two suppliers and")
    print("   demand is the lever for the other two. Asking which one matters in general is the")
    print(f"   wrong question; it dominates on {(sized['lead_share'] > 0.5).mean():.0%} of these")
    print("   SKUs and the split is entirely explained by who ships them.")

    print("\n4. The same item, sourced four ways")
    sku = regular.sum().sort_values(ascending=False).index[20]
    demand = fit_demand(regular[sku].to_numpy())
    rows = []
    for name, profile in sorted(lead_times.items(), key=lambda item: item[1].mean):
        stock = safety_stock(demand, profile, z)
        rows.append(
            {
                "supplier": name,
                "lead_days": profile.mean,
                "sd_lead_days": profile.sd,
                "safety_units": stock.units,
                "pipeline_units": demand.mean * profile.mean,
                "total_units": stock.units + demand.mean * profile.mean,
            }
        )
    compared = pd.DataFrame(rows).set_index("supplier")
    print(f"   {sku}: {demand.mean:.1f} units a day, demand CV {demand.cv:.2f}")
    print(compared.round(1).to_string())
    fast, slow = "FORN-NACIONAL", "FORN-CONTRATO"
    print(
        f"\n   {slow} takes"
        f" {compared.loc[slow, 'lead_days'] / compared.loc[fast, 'lead_days'] - 1:.0%} longer than"
        f" {fast} and needs"
        f" {1 - compared.loc[slow, 'safety_units'] / compared.loc[fast, 'safety_units']:.0%} less"
    )
    print(
        f"   safety stock, because its lead time is"
        f" {compared.loc[fast, 'sd_lead_days'] / compared.loc[slow, 'sd_lead_days']:.1f} times"
        " tighter. The ranking inverts, which"
    )
    print("   is why a sourcing decision made on quoted lead time alone gets the buffer wrong.")
    print("   Total inventory does not invert - pipeline stock scales with the mean and dominates")
    print("   the comparison - so the two questions have different answers and both are real.")

    print(f"\n   The four ways to size the same buffer, for {sku} from {supplier_of[sku]}:")
    print(
        decompose_safety_stock(demand, lead_times[supplier_of[sku]], z)
        .round(4)
        .to_string(index=False)
    )

    _commitment(demand, lead_times[supplier_of[sku]], float(unit_cost[sku]))
    _curve(demand, lead_times[supplier_of[sku]], regular[sku], float(unit_cost[sku]))
    _levers(demand, lead_times[supplier_of[sku]], regular[sku])


def _size_assortment(
    regular: pd.DataFrame,
    supplier_of: pd.Series,
    lead_times: dict[str, object],
    unit_cost: pd.Series,
    z: float,
) -> pd.DataFrame:
    rows = []
    for sku in regular.columns:
        supplier = supplier_of.get(sku)
        if supplier is None:
            continue
        demand = fit_demand(regular[sku].to_numpy())
        if demand.mean <= 0.0:
            continue
        profile = lead_times[supplier]
        realised = safety_stock(demand, profile, z)
        on_quote = safety_stock(demand, profile, z, use_quoted_lead_time=True)
        cost = float(unit_cost[sku])
        rows.append(
            {
                "sku": sku,
                "supplier": supplier,
                "demand_cv": demand.cv,
                "lead_share": realised.lead_time_share,
                "crossover_cv": float(np.sqrt(profile.cv**2 * profile.mean)),
                "capital": realised.units * cost,
                "capital_on_quote": on_quote.units * cost,
            }
        )
    return pd.DataFrame(rows)


def _commitment(demand: object, profile: object, unit_cost: float) -> None:
    quantity = round(demand.mean * COVER_DAYS)
    sigma = safety_stock(demand, profile, 1.0).sigma
    as_cycle = safety_stock(demand, profile, z_for_cycle_service(COMMITMENT))
    z_fill = z_for_fill_rate(COMMITMENT, sigma, quantity)
    as_fill = safety_stock(demand, profile, z_fill)

    print(f"\n5. One commitment of {COMMITMENT:.0%}, sized two ways")
    print(
        pd.DataFrame(
            {
                "z": [as_cycle.z, z_fill],
                "safety_units": [as_cycle.units, as_fill.units],
                "safety_capital": [as_cycle.units * unit_cost, as_fill.units * unit_cost],
                "implied_fill_rate": [
                    expected_fill_rate(as_cycle.z, sigma, quantity),
                    expected_fill_rate(z_fill, sigma, quantity),
                ],
                "implied_cycle_service": [COMMITMENT, norm_cdf(z_fill)],
            },
            index=["read as cycle service", "read as fill rate"],
        )
        .round(4)
        .to_string()
    )
    print(
        f"\n   Sizing a fill-rate commitment as a cycle-service one buys"
        f" {as_cycle.units / as_fill.units - 1:.0%} more stock"
    )
    print("   than the commitment requires. The cycle-service policy delivers a fill rate of")
    print(
        f"   {expected_fill_rate(as_cycle.z, sigma, quantity):.4f} - it is not wrong, it is"
        " answering a"
    )
    print("   different question. Cycle service counts cycles and fill rate counts units, and a")
    print("   shortfall late in a cycle costs few units, so the second is always the kinder")
    print("   number. The conversion between them needs the order quantity, which is why no")
    print("   fudge factor exists: a larger order spreads the same shortfall over more units.")


def _curve(demand: object, profile: object, path: pd.Series, unit_cost: float) -> None:
    quantity = round(demand.mean * COVER_DAYS)
    curve = achieved_curve(
        demand,
        profile,
        quantity,
        unit_cost,
        path,
        periods=HORIZON,
        replications=REPLICATIONS,
    )
    print("\n6. The price of a point, and what the point delivers")
    print(
        curve[
            [
                "cycle_service_target",
                "safety_capital",
                "capital_per_point",
                "achieved_cycle_service",
                "achieved_fill_rate",
            ]
        ]
        .round(4)
        .to_string(index=False)
    )
    per_point = curve["capital_per_point"].dropna()
    print(
        f"\n   A point of cycle service costs BRL {per_point.iloc[0]:.2f} at the bottom of the"
        f" curve and"
    )
    print(
        f"   BRL {per_point.iloc[-1]:.2f} at the top - {per_point.iloc[-1] / per_point.iloc[0]:.0f}"
        " times as much - because the normal tail"
    )
    print("   thins. That convexity is the argument for differentiating service by item rather")
    print("   than setting one target for the assortment: the same capital buys far more service")
    print("   spent on items that are cheap to protect.")
    top = curve.tail(2).reset_index(drop=True)
    print(
        f"\n   The top of the curve is worse than convex. Going from"
        f" {top.loc[0, 'cycle_service_target']:.1%} to {top.loc[1, 'cycle_service_target']:.1%}"
    )
    print(
        f"   costs {top.loc[1, 'safety_capital'] / top.loc[0, 'safety_capital'] - 1:.0%} more"
        f" capital and delivers"
        f" {top.loc[1, 'achieved_cycle_service'] - top.loc[0, 'achieved_cycle_service']:+.2%} of"
        " measured"
    )
    print("   cycle service. The promise keeps rising and the outcome does not follow, because")
    print("   what is left is the skewed tail of the lead time and a normal buffer is an")
    print("   expensive way to cover it.")


def _levers(demand: object, profile: object, path: pd.Series) -> None:
    z = z_for_cycle_service(COMMITMENT)
    base = safety_stock(demand, profile, z).units
    forecast = safety_stock(replace(demand, sd=demand.sd * (1 - FORECAST_HEADROOM)), profile, z)
    capped = fit_lead_time(
        np.minimum(profile.sample, profile.quantile(0.95)), quoted=profile.quoted
    )
    reliability = safety_stock(demand, capped, z)

    print("\n7. Two levers, priced against each other")
    print(
        pd.DataFrame(
            {
                "safety_units": [base, forecast.units, reliability.units],
                "change": [
                    0.0,
                    forecast.units / base - 1,
                    reliability.units / base - 1,
                ],
            },
            index=[
                "as measured",
                f"the entire forecast headroom ({FORECAST_HEADROOM:.1%} off demand sd)",
                "supplier tail capped at its own 95th percentile",
            ],
        )
        .round(4)
        .to_string()
    )
    gain_forecast = 1 - forecast.units / base
    gain_reliability = 1 - reliability.units / base
    print(
        f"\n   Capping the lead-time tail releases {gain_reliability:.0%} of the buffer."
        f" Spending the whole"
    )
    print(
        f"   forecasting headroom measured in example 09 releases {gain_forecast:.2%} -"
        f" a factor of {gain_reliability / gain_forecast:.0f}."
    )
    print("   And the two are not comparable in effort either: the forecasting gain requires")
    print("   beating a one-line rule across the assortment, while the reliability gain requires")
    print("   one conversation with one supplier about the worst 5% of its deliveries.")

    policy = ContinuousReview(
        reorder_point=reorder_point(demand, capped, reliability),
        order_quantity=round(demand.mean * COVER_DAYS),
    )
    achieved = simulate_policy(
        policy,
        path.to_numpy(dtype=float),
        capped.sample,
        periods=HORIZON,
        replications=REPLICATIONS,
    ).summary()
    print(
        f"\n   And it is not a trade: the capped-tail policy holds"
        f" {gain_reliability:.0%} less safety stock"
    )
    print(
        f"   and still measures {achieved['cycle_service']:.4f} cycle service against the"
        f" {COMMITMENT:.0%} promise."
    )
    print("   Reliability is the cheaper input, and it is bought upstream rather than held.")


if __name__ == "__main__":
    main()
