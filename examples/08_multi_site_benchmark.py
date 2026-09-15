"""Which site is actually underperforming, once size and geography are held constant?

Run:
    python examples/08_multi_site_benchmark.py

Three questions, three different kinds of answer: how much of the cost gap is geography rather
than performance, whether the ranking is a fact or a weighting, and whether a four-site network
is large enough for the efficiency method everyone reaches for.
"""

from __future__ import annotations

import pandas as pd

from oplab.benchmark import (
    composite_index,
    dea,
    discrimination_check,
    indirect_standardisation,
    peer_z_scores,
    rank_stability,
)
from oplab.kpi import dock_to_stock, inventory_record_accuracy, line_service
from oplab.synth import generate_dataset

DISTANCE_BANDS = [0.0, 10.0, 25.0, 50.0, float("inf")]
BAND_LABELS = ["0-10 km", "10-25 km", "25-50 km", "50+ km"]
METRICS = ["otif", "cost_per_order", "dock_to_stock_p95_h", "inventory_accuracy"]
DIRECTION = {
    "otif": True,
    "cost_per_order": False,
    "dock_to_stock_p95_h": False,
    "inventory_accuracy": True,
}


def main() -> None:
    pd.set_option("display.width", 185)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    ledger = dataset.cost_ledger.copy()
    lines = line_service(dataset.order_lines)
    scoped = lines.loc[lines["in_scope"]].copy()

    print("1. How much of the cost gap is geography?")
    ledger["band"] = pd.cut(ledger["distance_km"], DISTANCE_BANDS, labels=BAND_LABELS).astype(str)
    mix = ledger.groupby(["site", "band"], observed=True).size().unstack(fill_value=0)
    print((mix.div(mix.sum(axis=1), axis=0)).round(3).to_string())
    print("\n   The sites do not serve the same territory. A third of one site's deliveries are")
    print("   inside 10 km; another site has a tenth. Ranking them on cost per order without")
    print("   removing that is ranking them on their postcodes.")

    aggregated = (
        ledger.groupby(["site", "band"], observed=True)
        .agg(cost=("total_brl", "sum"), deliveries=("order_id", "size"))
        .reset_index()
    )
    standardised = indirect_standardisation(
        aggregated, "site", "band", "cost", "deliveries", exclude_self=True
    )
    print("\n   Indirect standardisation: observed against what the rest of the network would")
    print("   spend on this site's own distance profile.")
    print(
        standardised[
            [
                "site",
                "crude_rate",
                "expected",
                "standardised_ratio",
                "standardised_rate",
                "mix_effect",
            ]
        ]
        .round(2)
        .to_string(index=False)
    )

    crude_spread = standardised["crude_rate"].max() - standardised["crude_rate"].min()
    adjusted_spread = (
        standardised["standardised_rate"].max() - standardised["standardised_rate"].min()
    )
    worst = standardised.loc[standardised["crude_rate"].idxmax()]
    best = standardised.loc[standardised["crude_rate"].idxmin()]
    print(
        f"\n   Spread between best and worst: {crude_spread:.2f} crude,"
        f" {adjusted_spread:.2f} adjusted."
    )
    print(f"   {1 - adjusted_spread / crude_spread:.0%} of the headline gap is geography.")
    print(
        f"   {worst['site']} reads {worst['crude_rate'] / best['crude_rate'] - 1:.0%} more"
        f" expensive than {best['site']} crude, and"
    )
    print(
        f"   {worst['standardised_rate'] / best['standardised_rate'] - 1:.0%} once the distance"
        " profile is held constant."
    )
    print("   The first number sets an unfair target. The second is arguable on its merits.")

    print("\n2. Is the ranking a fact or a weighting?")
    frame = _scorecard(dataset, ledger, scoped)
    print(frame.round(4).to_string(index=False))

    scores = peer_z_scores(frame, METRICS, DIRECTION, unit="site")
    print("\n   Under equal weights:")
    print(composite_index(scores, METRICS, unit="site").round(3).to_string(index=False))

    stability = rank_stability(scores, METRICS, unit="site")
    print("\n   Under 2,000 random weightings:")
    print(stability.round(3).to_string(index=False))
    movable = int((stability["best_rank"] != stability["worst_rank"]).sum())
    print(
        f"\n   {movable} of {len(stability)} sites can change rank. One site is first under"
        f" {stability['share_first'].max():.0%} of"
    )
    print("   weightings, and the bottom two cannot move at all: they are worse on every")
    print("   dimension. On this network the ranking is a fact, and the argument about weights")
    print("   is not worth having. That is the rare case, and the point is that you cannot tell")
    print("   which case you are in without measuring it.")

    print("\n3. The same test, one site month by month")
    monthly = _monthly(ledger, scoped, site="CD-SP")
    month_scores = peer_z_scores(
        monthly,
        ["otif", "cost_per_order", "handling_per_line"],
        {"otif": True, "cost_per_order": False, "handling_per_line": False},
        unit="month",
    )
    month_stability = rank_stability(
        month_scores, ["otif", "cost_per_order", "handling_per_line"], unit="month"
    )
    print(month_stability.round(3).to_string(index=False))
    swing = int((month_stability["worst_rank"] - month_stability["best_rank"]).max())
    movable_months = int((month_stability["best_rank"] != month_stability["worst_rank"]).sum())
    print(f"\n   {movable_months} of {len(month_stability)} months have a weighting-dependent")
    print(f"   rank, and the widest swing is {swing} places. One month can be first or")
    print("   near-last on the same data. Any best-month award here is a weighting artefact -")
    print("   same method, same tool, and the opposite conclusion from section 2.")

    print("\n4. Is the network big enough for DEA?")
    inputs, outputs = ["freight_brl", "handling_brl"], ["otif_lines", "units"]
    sites = _dea_frame(ledger, scoped, ["site"])
    print("   " + discrimination_check(len(sites), len(inputs), len(outputs)).message)
    for model in ("crs", "vrs"):
        scored = dea(sites, inputs, outputs, returns_to_scale=model)
        print(
            f"\n   {model.upper()}: {scored['on_frontier'].mean():.0%} on the frontier | "
            + ", ".join(f"{row.site} {row.efficiency:.3f}" for row in scored.itertuples())
        )
    print("\n   The worst site scores 0.63 under constant returns and 0.89 under variable")
    print("   returns. Most of that 27-point difference is a penalty for being small, not a")
    print("   measure of how it is run - and on a network whose site sizes are a deliberate")
    print("   design choice, charging a site for its size is measuring the wrong thing.")

    site_months = _dea_frame(ledger, scoped, ["site", "month"])
    print(f"\n   {len(site_months)} site-months instead:")
    print("   " + discrimination_check(len(site_months), len(inputs), len(outputs)).message)
    for model in ("crs", "vrs"):
        scored = dea(site_months, inputs, outputs, unit="unit", returns_to_scale=model)
        by_site = (
            scored.assign(site=scored["unit"].str.split(" ").str[0])
            .groupby("site")["efficiency"]
            .mean()
        )
        print(
            f"   {model.upper()}: {scored['on_frontier'].mean():.1%} on the frontier | "
            + ", ".join(f"{site} {value:.3f}" for site, value in by_site.items())
        )
    print("\n   Raising the unit count is the way out, and it costs interpretation: a")
    print("   site-month is efficient relative to other site-months including its own, so the")
    print("   result is about consistency over time as much as about the site.")


def _scorecard(dataset, ledger: pd.DataFrame, scoped: pd.DataFrame) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    service = scoped.groupby("site", observed=True)["otif"].mean().rename("otif")
    cost = ledger.groupby("site", observed=True)["total_brl"].mean().rename("cost_per_order")
    inbound = (
        dock_to_stock(dataset.receipts)
        .query("stage == 'dock_to_stock_h'")
        .set_index("site")["p95"]
        .rename("dock_to_stock_p95_h")
    )
    accuracy = (
        inventory_record_accuracy(dataset.cycle_counts)
        .set_index("site")["location_accuracy"]
        .rename("inventory_accuracy")
    )
    return pd.concat([service, cost, inbound, accuracy], axis=1).reset_index(names="site")


def _monthly(ledger: pd.DataFrame, scoped: pd.DataFrame, site: str) -> pd.DataFrame:
    marked = scoped.copy()
    marked["month"] = marked["order_ts"].dt.to_period("M").astype(str)
    service = (
        marked.loc[marked["site"].astype(str) == site]
        .groupby("month", observed=True)["otif"]
        .mean()
        .rename("otif")
    )
    site_ledger = ledger.loc[ledger["site"].astype(str) == site]
    cost = site_ledger.groupby("month", observed=True)["total_brl"].mean().rename("cost_per_order")
    handling = (
        site_ledger.groupby("month", observed=True)
        .apply(lambda g: g["handling_brl"].sum() / g["lines"].sum(), include_groups=False)
        .rename("handling_per_line")
    )
    return pd.concat([service, cost, handling], axis=1).reset_index(names="month")


def _dea_frame(ledger: pd.DataFrame, scoped: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    marked = scoped.copy()
    marked["month"] = marked["order_ts"].dt.to_period("M").astype(str)
    cost = ledger.groupby(keys, observed=True).agg(
        freight_brl=("freight_brl", "sum"), handling_brl=("handling_brl", "sum")
    )
    service = marked.groupby(keys, observed=True).agg(
        otif_lines=("otif", "sum"), units=("qty_delivered", "sum")
    )
    frame = cost.join(service, how="inner").reset_index()
    frame["otif_lines"] = frame["otif_lines"].astype(float)
    frame = frame[(frame[["freight_brl", "handling_brl", "otif_lines", "units"]] > 0).all(axis=1)]
    if len(keys) > 1:
        frame["unit"] = frame[keys[0]] + " " + frame[keys[1]]
    return frame.reset_index(drop=True)


if __name__ == "__main__":
    main()
