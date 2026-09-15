"""Does the forecast beat doing nothing, and how would you know?

Run:
    python examples/09_forecast_baseline.py

Four things get established before any model is judged: that the history can support the
baseline at all, that the usual accuracy metric cannot be computed, that the best of seven
methods beats a one-line rule by under a percent, and that a per-item bias small enough to
ignore is not small enough to ignore for the network.
"""

from __future__ import annotations

import pandas as pd

from oplab.forecast import (
    BASELINES,
    INTERMITTENT,
    aggregate_panel,
    backtest_panel,
    mape_coverage,
    season_feasibility,
    summarise,
    to_panel,
)
from oplab.synth import generate_dataset

SITE = "CD-SP"
SEASON = 7
HORIZON = 7
STEP = 28
MIN_TRAIN = 120


def main() -> None:
    pd.set_option("display.width", 185)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    site_demand = dataset.demand.loc[dataset.demand["site"].astype(str) == SITE]

    print("1. Can this history support a seasonal baseline at all?")
    weekly = to_panel(site_demand, freq="W", key=("sku",))
    weekly_check = season_feasibility(weekly.shape[0], season=52, min_train=40, horizon=4, step=4)
    print(f"   Weekly grid, annual season: {weekly.shape[0]} periods.")
    print(f"   {weekly_check.message}")
    print("\n   That is the trap. Every week of the year is observed once, so there is no")
    print("   repetition either to learn from or to validate against. Run it anyway and nothing")
    print("   raises: the seasonal baseline falls back to a non-seasonal one, every scaled")
    print("   metric comes back nan, and the report still has a number in it.")

    daily = to_panel(site_demand, freq="D", key=("sku",))
    daily_check = season_feasibility(
        daily.shape[0], season=SEASON, min_train=MIN_TRAIN, horizon=HORIZON, step=STEP
    )
    print(f"\n   Daily grid, weekly season: {daily.shape[0]} periods.")
    print(f"   {daily_check.message}")

    print("\n2. Can the usual metric be computed?")
    coverage = mape_coverage(daily.to_numpy())
    print(f"   {coverage.summary()}")
    print(f"\n   {1 - coverage.series_coverage:.0%} of SKUs have at least one period where MAPE")
    print("   does not exist. It is also asymmetric - a forecast of five against an actual of")
    print("   one scores 400%, while forecasting zero scores 100% - so a model tuned on MAPE")
    print("   learns to forecast low, which on a service item is the expensive direction.")
    print("   MASE and RMSSE are scale-free, defined at zero, and comparable across series.")

    print("\n3. Seven methods against a one-line rule")
    zero_share = (daily == 0).mean()
    segments = {
        "regular (<=50% empty periods)": daily[zero_share[zero_share <= 0.5].index],
        "sparse (>50% empty periods)": daily[zero_share[zero_share > 0.5].index],
    }
    models = {**BASELINES, **INTERMITTENT}

    for label, panel in segments.items():
        results = backtest_panel(
            panel, models, horizon=HORIZON, step=STEP, min_train=MIN_TRAIN, season=SEASON
        )
        summary = summarise(results, panel, min_train=MIN_TRAIN, season=SEASON)
        print(f"\n   {label}: {panel.shape[1]} series, {results['origin'].nunique()} origins")
        print(
            summary[["model", "mase", "rmsse", "bias", "relative_mase", "beats_reference_share"]]
            .round(4)
            .to_string(index=False)
        )
        _comment(summary, label)

    print("\n4. What aggregation does, and what it does not do")
    full = to_panel(dataset.demand, freq="D", key=("site", "sku"))
    total = aggregate_panel(full)
    reference = {"seasonal_naive": BASELINES["seasonal_naive"]}
    kwargs = {"horizon": HORIZON, "step": STEP, "min_train": MIN_TRAIN, "season": SEASON}

    fine = summarise(
        backtest_panel(full, reference, **kwargs), full, min_train=MIN_TRAIN, season=SEASON
    ).set_index("model")
    coarse = summarise(
        backtest_panel(total, reference, **kwargs), total, min_train=MIN_TRAIN, season=SEASON
    ).set_index("model")

    print(
        pd.DataFrame(
            {
                "series": [full.shape[1], 1],
                "mase": [fine.loc["seasonal_naive", "mase"], coarse.loc["seasonal_naive", "mase"]],
                "bias": [fine.loc["seasonal_naive", "bias"], coarse.loc["seasonal_naive", "bias"]],
            },
            index=["per SKU and site", "network total"],
        )
        .round(4)
        .to_string()
    )

    per_series_bias = fine.loc["seasonal_naive", "bias"]
    total_bias = coarse.loc["seasonal_naive", "bias"]
    print(
        f"\n   Error: the total scores"
        f" {1 - coarse.loc['seasonal_naive', 'mase'] / fine.loc['seasonal_naive', 'mase']:.0%}"
        " better relative to its own naive benchmark,"
    )
    print("   because the errors on the parts partly cancel when they are summed. That is why a")
    print("   headline forecast accuracy figure is almost always an accuracy figure for an")
    print("   aggregate, and says little about whether any single item can be replenished.")
    print(
        f"\n   Bias: {per_series_bias:+.6f} units a day per series, times {full.shape[1]} series,"
    )
    print(f"   is {per_series_bias * full.shape[1]:+.4f} - and the bias of the total is")
    print(f"   {total_bias:+.4f}. Identical, because bias is additive.")
    print("\n   That is the finding worth taking away. Aggregation shrinks error and leaves bias")
    print("   untouched. A bias too small to notice on one item is the same bias, undiminished,")
    print("   on the warehouse.")


def _comment(summary: pd.DataFrame, label: str) -> None:
    indexed = summary.set_index("model")
    best = summary.iloc[0]
    reference_mase = indexed.loc["seasonal_naive", "mase"]

    if "regular" in label:
        gain = 1 - best["mase"] / reference_mase
        print(f"\n   The best of seven, {best['model']}, beats the seasonal rule by {gain:.1%} and")
        print(f"   wins on {best['beats_reference_share']:.0%} of series - a coin flip. A project")
        print("   promising a large accuracy gain on this data is promising something the data")
        print("   does not contain.")
        print(
            f"\n   Croston's bias is {indexed.loc['croston', 'bias']:+.4f} units a day and SBA's"
            f" is {indexed.loc['sba', 'bias']:+.4f}:"
        )
        print("   a 5% multiplicative correction removes 99% of the bias, because the bias is")
        print("   proportional to the rate, which is what the correction was derived for.")
    else:
        print(f"\n   Nothing gets below a MASE of 1.0. The best, {best['model']}, is at")
        print(f"   {best['mase']:.4f} - worse than the in-sample naive benchmark it is scaled")
        print("   against. On this half of the assortment no method is reliably better than a")
        print("   rule, and the honest plan is an availability decision rather than a forecast.")
        print("   TSB leads here and not on the regular half, because it is the only method that")
        print("   updates the demand probability in empty periods and so can notice an item")
        print("   going quiet. The best model is a property of the segment, not the assortment.")


if __name__ == "__main__":
    main()
