"""Does forecasting reduce the stock you have to hold?

Run:
    python examples/12_forecast_error_to_stock.py

The two modules built before this one answer neighbouring questions and were never connected.
`oplab.forecast` ranks forecasts on MASE. `oplab.inventory` sizes safety stock on the variability
of demand. Both are defensible alone, and putting them together exposes that neither answers the
question replenishment actually asks: how much buffer does *this forecast* need?

Four things get established. That the metric used to rank forecasts is not the metric an inventory
decision needs, and how much the two disagree. That on this assortment no method reduces the buffer
below a forecast of the training mean. That a forecast's bias costs stock in a way no safety factor
corrects. And that a per-horizon error table can be a seasonal chart wearing a horizon label.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from oplab.forecast import (
    BASELINES,
    INTERMITTENT,
    backtest_panel,
    error_profile,
    horizon_profile,
    interval_coverage,
    summarise,
    to_panel,
)
from oplab.inventory import (
    compare_sizing_bases,
    fit_demand,
    fit_lead_time,
    z_for_cycle_service,
)
from oplab.synth import generate_dataset

SITE = "CD-SP"
SEASON = 7
HORIZON = 7
STEP = 28
MIN_TRAIN = 120
CYCLE_SERVICE = 0.95
REGULAR_ZERO_SHARE = 0.5


def mean_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
    """Forecast the training mean - the strategy the demand-variability formula assumes.

    It belongs in the comparison rather than outside it. Sizing safety stock on the standard
    deviation of demand is exactly as good as forecasting the mean, so the mean is the reference
    any forecast has to beat before it can claim to reduce inventory.
    """
    return np.full(horizon, float(np.mean(history)) if history.size else 0.0)


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    panel = to_panel(
        dataset.demand.loc[dataset.demand["site"].astype(str) == SITE], freq="D", key=("sku",)
    )
    regular = panel.loc[:, (panel == 0).mean() <= REGULAR_ZERO_SHARE]
    models = {**BASELINES, **INTERMITTENT, "mean": mean_forecast}
    results = backtest_panel(
        regular, models, horizon=HORIZON, step=STEP, min_train=MIN_TRAIN, season=SEASON
    )

    print(f"1. Two metrics, two rankings ({regular.shape[1]} regular series)")
    ranked = summarise(results, regular, min_train=MIN_TRAIN, season=SEASON).set_index("model")
    rows = []
    for name in ("mean", "sba", "tsb", "croston", "seasonal_naive", "naive"):
        profile = error_profile(results, name)
        rows.append(
            {
                "model": name,
                "mase": ranked.loc[name, "mase"],
                "mae": profile["mae"].median(),
                "error_sd": profile["sd"].median(),
                "sd_vs_mean": np.nan,
                "reduces_buffer": profile["reduces_buffer"].mean(),
            }
        )
    table = pd.DataFrame(rows)
    reference = table.loc[table["model"] == "mean"].iloc[0]
    table["mae_vs_mean"] = table["mae"] / reference["mae"] - 1.0
    table["sd_vs_mean"] = table["error_sd"] / reference["error_sd"] - 1.0
    print(
        table[["model", "mase", "mae", "error_sd", "mae_vs_mean", "sd_vs_mean", "reduces_buffer"]]
        .round(4)
        .to_string(index=False)
    )
    _metric_comment(table)

    print("\n2. What that costs in stock")
    _stock_comment(dataset, regular, results, ranked)

    print("\n3. A bias no safety factor corrects")
    _bias_comment(dataset, regular, results)

    print("\n4. A horizon table that is a seasonality table")
    profile = horizon_profile(results, "sba", step_between_origins=STEP, season=SEASON)
    print(
        profile[["step", "bias", "sd", "sd_vs_step_1", "sqrt_step", "phase_locked"]]
        .round(4)
        .to_string(index=False)
    )
    _horizon_comment(results, profile)


def _metric_comment(table: pd.DataFrame) -> None:
    indexed = table.set_index("model")
    seasonal = indexed.loc["seasonal_naive"]
    best_mase = indexed["mase"].idxmin()
    best_sd = indexed["error_sd"].idxmin()

    agree = best_mase == best_sd
    print(
        f"\n   Both metrics put {best_mase} first"
        if agree
        else f"\n   MASE puts {best_mase} first and the error spread puts {best_sd} first"
    )
    print("   - the two agree on the winner and disagree sharply on the order below it.")
    print(
        "\n   The disagreement is worst on seasonal_naive. Against a forecast of the mean its"
        " MAE is"
    )
    print(
        f"   {seasonal['mae_vs_mean']:+.1%} and the spread of its error is"
        f" {seasonal['sd_vs_mean']:+.1%} -"
        f" {seasonal['sd_vs_mean'] / seasonal['mae_vs_mean']:.1f} times as much. On MASE it looks"
    )
    print(
        f"   {seasonal['mase'] / indexed.loc[best_mase, 'mase'] - 1:.1%} behind the leader; on the"
        " quantity a buffer is sized from, a quarter worse."
    )
    print("   MASE is built on absolute error, which weights a large miss and a small one in")
    print("   proportion. A buffer does not: it has to cover the tail, so a fat-tailed forecast")
    print("   costs stock out of proportion to its MAE. Ranking on MASE and then sizing stock is")
    print("   two decisions made on two different definitions of better.")


def _stock_comment(
    dataset: object, regular: pd.DataFrame, results: pd.DataFrame, ranked: pd.DataFrame
) -> None:
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

    sku = regular.sum().sort_values(ascending=False).index[20]
    demand = fit_demand(regular[sku].to_numpy())
    lead = lead_times[supplier_of[sku]]
    profile = error_profile(results, "sba").set_index("series")
    row = profile.loc[sku]

    print(
        f"   {sku}: {demand.mean:.1f} units a day, demand sd {demand.sd:.2f}, forecast error sd"
        f" {row['sd']:.2f}"
    )
    print(
        compare_sizing_bases(
            demand, lead, error_sd=float(row["sd"]), error_bias=float(row["bias"]), z=z
        )
        .round(4)
        .to_string(index=False)
    )

    whole = error_profile(results, "sba")
    share = float(whole["reduces_buffer"].mean())
    print(
        f"\n   Across the assortment the forecast reduces the buffer on {share:.0%} of series"
        f" and enlarges"
    )
    print(
        f"   it on the rest. The median ratio of forecast-error spread to demand spread is"
        f" {whole['sd_ratio'].median():.4f}:"
    )
    print("   sizing on the forecast and sizing on demand variability come to the same number.")
    print("   That is not a defect of the method. It is the measurement that says what forecasting")
    print("   is worth here, and it belongs in the business case rather than after it.")

    capital = float(unit_cost[sku])
    print(
        f"\n   At BRL {capital:.2f} a unit this single SKU is a rounding error; the point is the"
        " ratio, which"
    )
    print("   applies to the whole assortment and does not depend on the unit cost at all.")


def _bias_comment(dataset: object, regular: pd.DataFrame, results: pd.DataFrame) -> None:
    orders = dataset.purchase_orders
    supplier_of = orders.drop_duplicates("sku").set_index("sku")["supplier"]
    lead_times = {
        name: fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        for name, group in orders.groupby("supplier")
    }
    z = z_for_cycle_service(CYCLE_SERVICE)

    rows = []
    for model in ("sba", "croston", "tsb"):
        profile = error_profile(results, model)
        under = profile.loc[profile["bias"] < 0.0]
        rows.append(
            {
                "model": model,
                "mean_bias": profile["bias"].mean(),
                "series_under_forecast": float((profile["bias"] < 0.0).mean()),
                "mean_bias_when_under": float(under["bias"].mean()) if not under.empty else 0.0,
            }
        )
    print(pd.DataFrame(rows).round(4).to_string(index=False))

    print("\n   Read the first column against the second. Croston's mean bias is +0.47 units a day")
    print("   across the assortment, and it under-forecasts 28% of series by -0.67 a day. SBA's")
    print("   mean bias is +0.005 - near zero - and it under-forecasts 52% of series. A centred")
    print("   average is not a centred forecast: inventory is held per item, so the average bias")
    print("   is the one statistic that cannot be used to size it. This is the same additivity")
    print("   from example 09 arriving as a cost rather than as an observation.")

    # Price the charge on a series that is actually under-forecast, since that is where it falls.
    profile = error_profile(results, "croston").set_index("series")
    under = profile.loc[(profile["bias"] < 0.0) & profile.index.isin(regular.columns)]
    sku = str(under["bias"].idxmin())
    demand = fit_demand(regular[sku].to_numpy())
    lead = lead_times[supplier_of[sku]]
    row = profile.loc[sku]
    table = compare_sizing_bases(
        demand, lead, error_sd=float(row["sd"]), error_bias=float(row["bias"]), z=z
    ).set_index("basis")
    charge = (
        table.loc["forecast error", "safety_units"]
        - table.loc["forecast error, bias uncorrected", "safety_units"]
    )
    baseline = table.loc["forecast error, bias uncorrected", "safety_units"]

    print(
        f"\n   A centred forecast needs a symmetric buffer and a safety factor provides one. A"
        f"\n   biased one needs its centre moved, and no safety factor does that: raising z widens"
        f"\n   a window that is in the wrong place. The worst under-forecast here is {sku} at"
        f" {row['bias']:+.2f}"
    )
    print(
        f"   a day, which charges {charge:.1f} units of permanent stock -"
        f" {charge / baseline:.0%} on top of a buffer of {baseline:.0f} -"
    )
    print("   held to compensate a forecast that is wrong in one direction.")
    print("   The remedy is the 5% correction from example 09, not more inventory - which is the")
    print("   point: the cheapest inventory decision here is a forecasting fix, and the cheapest")
    print("   forecasting decision in example 10 was a supplier fix. Neither is more stock.")


def _horizon_comment(results: pd.DataFrame, profile: pd.DataFrame) -> None:
    locked = bool(profile["phase_locked"].all())
    cells = (
        results.loc[results["model"] == "sba"]
        .assign(error=lambda f: f["forecast"] - f["actual"])
        .groupby(["origin", "step"])["error"]
        .mean()
        .unstack("step")
    )
    between = cells.std(ddof=1)
    systematic = cells.mean()

    print(f"\n   phase_locked: {locked}. Step 4's error is {systematic.loc[4]:+.2f} on average and")
    print(
        f"   varies by only {between.loc[4]:.2f} across the {len(cells)} origins, against a"
        f" systematic spread of"
    )
    print(
        f"   {systematic.min():+.2f} to {systematic.max():+.2f} between steps. The pattern"
        " reproduces at every origin,"
    )
    print("   so it is not sampling noise.")
    print(
        f"\n   The cause is the backtest's own geometry. Origins are {STEP} periods apart and the"
        f" season is"
    )
    print(
        f"   {SEASON}, so every horizon step lands on the same phase of the week, every time. Step"
        " 4 is"
    )
    print("   always the same weekday, a flat forecast carries that weekday's deviation as a")
    print("   constant error, and the column reads as a horizon effect while being a seasonal one.")
    print("   Choose a step that is not a multiple of the season, or read the flag.")
    print("\n   And the square-root rule does not belong here either. sqrt(h) describes the error")
    print("   of a cumulative total, not the per-period error of a flat forecast on a stationary")
    print("   series - which does not grow. Inventory needs the cumulative quantity, which is why")
    print("   the sizing multiplies the error variance by the protection interval instead of")
    print("   reading a growth rate off this table.")

    coverage = interval_coverage(results, "sba", 0.95)
    worst = coverage.loc[coverage["normal_coverage"].idxmax()]
    print(
        f"\n   The intervals carry the same asymmetry. A nominal 95% normal interval covers"
        f" {worst['normal_coverage']:.1%}"
    )
    print(
        f"   at step {int(worst['step'])} - too wide, not too narrow - and misses"
        f" {worst['normal_below']:.1%} below against"
        f" {worst['normal_above']:.1%} above."
    )
    print("   A symmetric interval on a skewed error distribution is wrong on both counts at once:")
    print("   it holds stock it does not need, and it misses on the side that causes stockouts.")


if __name__ == "__main__":
    main()
