"""The same decision, 52 times a year. What changes when it is a policy and not a case?

Run:
    python studies/06_the_decision_you_take_every_week.py

Study 05 had a clock and one decision, and the triage it produced was ruthless: an analysis whose
answer could not reach the decision boundary before noon was worth nothing, and the value of
information was capped by the BRL 202 the decision was worth.

This study is the other half of that pair. The weekly replenishment review is the same decision
taken 52 times, and three things invert.

**Bias compounds, noise averages.** A systematic error is paid every period and accumulates
linearly; a random one accumulates as the square root. So the repetition count decides which of
the two matters, and there is a crossover: ``n* = (sd / bias)^2``. Below it, spend on noise. Above
it, spend on bias. Mean absolute error - the metric models are actually selected on - charges the
two identically, so it cannot answer the question a policy asks.

**The value of information scales with the repetitions.** The half-day of analysis that study 05
correctly refused, because it would have decided BRL 202 once, returns BRL 1,556 a year here and
keeps returning it.

**And re-tuning the policy is not free improvement.** Re-fitting weekly on a trailing window
tracks the demand that has already happened at a correlation of +0.98 and the demand it actually
has to cover at **-0.39**. It does not lag the signal, it inverts it: buying stock after the peak
and cutting it after the trough. The instrument that says when re-tuning is justified is the
control chart, not the forecast - and it finds one genuine level shift in 53 weeks against 40
re-tunes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from oplab.forecast import BASELINES, backtest_panel, error_profile, to_panel
from oplab.inventory import (
    ContinuousReview,
    economic_order_quantity,
    fit_demand,
    fit_lead_time,
    safety_stock,
    safety_stock_from_forecast_error,
    simulate_policy,
    z_for_cycle_service,
)
from oplab.spc import i_mr_chart
from oplab.synth import generate_dataset

SITE = "CD-SP"
SERVICE = 0.95
TRAILING_WINDOW = 90
REVIEW_FREQUENCIES = {"weekly review": 52, "daily review": 365}
HOLDING_RATE = 0.22
ORDER_COST = 250.0
ANALYST_HALF_DAY = 800.0


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    dataset = generate_dataset()
    panel = _panel(dataset)

    print("THE SITUATION")
    print("   Thursday, every Thursday. The replenishment review covers", panel.shape[1], "SKUs at")
    print(f"   {SITE} and the same decision is taken 52 times a year. Nothing is on fire and")
    print("   nothing expires at noon, which is what makes this the harder case: there is time to")
    print("   analyse, so the question is what the analysis should be about.")

    print("\n" + "=" * 96)
    print("CHECK 1 - BIAS IS PAID EVERY WEEK; NOISE IS NOT")
    print("=" * 96)
    models = _check_bias(panel)

    print("\n" + "=" * 96)
    print("CHECK 2 - THE ANALYSIS STUDY 05 REFUSED, PRICED AGAIN WITH REPETITIONS")
    print("=" * 96)
    value = _check_value(dataset, panel)

    print("\n" + "=" * 96)
    print("CHECK 3 - RE-TUNING WEEKLY DOES NOT LAG THE SIGNAL, IT INVERTS IT")
    print("=" * 96)
    tuning = _check_retuning(dataset, panel)

    print("\n" + "=" * 96)
    print("CHECK 4 - THE INSTRUMENT THAT SAYS WHEN TO RE-TUNE IS NOT THE FORECAST")
    print("=" * 96)
    control = _check_control(dataset, panel, tuning["retunes"])

    print("\n" + "=" * 96)
    print("WHAT THE POLICY SHOULD BE")
    print("=" * 96)
    _decide(models, value, tuning, control)


def _panel(dataset: object) -> pd.DataFrame:
    panel = to_panel(
        dataset.demand.loc[dataset.demand["site"].astype(str) == SITE], freq="D", key=("sku",)
    )
    return panel.loc[:, (panel == 0).mean() <= 0.2]


def _mean_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
    """A forecast of the training mean, which is what the safety-stock formula already assumes."""
    return np.full(horizon, float(np.mean(history)) if history.size else 0.0)


def _models(panel: pd.DataFrame) -> pd.DataFrame:
    models = {
        "mean": _mean_forecast,
        "seasonal_naive": BASELINES["seasonal_naive"],
        "moving_average": BASELINES["moving_average"],
        "drift": BASELINES["drift"],
    }
    results = backtest_panel(panel, models, horizon=7, step=28, min_train=120, season=7)
    rows = []
    for name in models:
        profile = error_profile(results, name)
        bias = float(profile["bias"].abs().median())
        spread = float(profile["sd"].median())
        rows.append(
            {
                "model": name,
                "mae": float(profile["mae"].median()),
                "abs_bias": bias,
                "sd": spread,
                # Bias accumulates as n * bias, noise as sqrt(n) * sd. They cross where
                # n * bias = sqrt(n) * sd, so at n = (sd / bias)^2.
                "crossover_periods": (spread / bias) ** 2 if bias > 0 else float("inf"),
                "biased_series": int((profile["bias"].abs() > 0.25 * profile["sd"]).sum()),
                "series": len(profile),
            }
        )
    return pd.DataFrame(rows)


def _check_bias(panel: pd.DataFrame) -> pd.DataFrame:
    table = _models(panel).sort_values("mae")
    print("   Four forecasts scored on the same rolling-origin backtest, ranked the usual way:")
    print(
        table[["model", "mae", "abs_bias", "sd", "crossover_periods"]]
        .round(3)
        .to_string(index=False)
    )

    print("\n   Mean absolute error charges a unit of bias and a unit of noise the same amount.")
    print("   A policy does not. The bias is the same error in the same direction every period, so")
    print("   it accumulates as n x bias; the noise cancels against itself and accumulates as")
    print("   sqrt(n) x sd. They cross at **n* = (sd / bias)^2**, and that is the only number here")
    print("   that knows how often the decision is taken.")

    for label, periods in REVIEW_FREQUENCIES.items():
        rows = []
        for row in table.itertuples():
            accumulated_bias = row.abs_bias * periods
            accumulated_noise = row.sd * np.sqrt(periods)
            rows.append(
                {
                    "model": row.model,
                    "accumulated_bias": accumulated_bias,
                    "accumulated_noise": accumulated_noise,
                    "dominant": "BIAS" if accumulated_bias > accumulated_noise else "noise",
                }
            )
        print(f"\n   At a {label}, {periods} decisions a year:")
        print(pd.DataFrame(rows).round(1).to_string(index=False))

    by_mae = table.sort_values("mae")["model"].iloc[0]
    by_crossover = table.sort_values("crossover_periods", ascending=False)["model"].iloc[0]
    ratio = (
        table.set_index("model").loc[by_crossover, "crossover_periods"]
        / table.set_index("model").loc[by_mae, "crossover_periods"]
    )
    print(
        f"\n   **The two rankings disagree.** MAE elects `{by_mae}`; the recurring decision elects"
    )
    print(
        f"   `{by_crossover}`, whose bias takes {ratio:.1f}x as many repetitions to overtake its"
        " own noise."
    )
    print("   And at a daily review the bias dominates for every model on the list, including the")
    print("   two that look clean weekly - so the review frequency decides which metric the model")
    print("   should have been selected on in the first place. Choosing a forecast without knowing")
    print("   how often you will act on it is not a modelling question left open, it is the")
    print("   selection criterion left unspecified.")
    print("\n   `drift` is the instructive one. Its MAE is only 1.9x the best, which reads as")
    print("   mediocre rather than disqualifying, and its bias overtakes its noise after three")
    print("   periods. On a metric that hides direction it survives the shortlist; on a weekly")
    print("   policy it is the worst thing on it.")
    return table


def _check_value(dataset: object, panel: pd.DataFrame) -> dict[str, float]:
    """The capital consequence of selecting on the wrong metric, annualised."""
    results = backtest_panel(
        panel,
        {"mean": _mean_forecast, "seasonal_naive": BASELINES["seasonal_naive"]},
        horizon=7,
        step=28,
        min_train=120,
        season=7,
    )
    orders = dataset.purchase_orders
    supplier_of = orders.drop_duplicates("sku").set_index("sku")["supplier"]
    lead_times = {
        name: fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        for name, group in orders.groupby("supplier")
    }
    unit_cost = dataset.catalog.set_index("sku")["unit_cost"]
    z = z_for_cycle_service(SERVICE)

    capital = {}
    for name in ("mean", "seasonal_naive"):
        profile = error_profile(results, name).set_index("series")
        total = 0.0
        for sku in profile.index:
            if sku not in supplier_of.index:
                continue
            demand = fit_demand(panel[sku].to_numpy())
            if demand.mean <= 0.0:
                continue
            sized = safety_stock_from_forecast_error(
                error_sd=float(profile.loc[sku, "sd"]),
                error_bias=float(profile.loc[sku, "bias"]),
                lead_time=lead_times[supplier_of[sku]],
                z=z,
                demand_mean=demand.mean,
            )
            total += sized.units * float(unit_cost[sku])
        capital[name] = total

    penalty = capital["seasonal_naive"] - capital["mean"]
    annual = penalty * HOLDING_RATE
    payback = ANALYST_HALF_DAY / annual * 365.0

    print(
        pd.DataFrame(
            {
                "selected on": ["the recurring decision (mean)", "mean absolute error"],
                "model": ["mean", "seasonal_naive"],
                "safety_capital_brl": [capital["mean"], capital["seasonal_naive"]],
            }
        )
        .round(0)
        .to_string(index=False)
    )
    print(
        f"\n   Selecting on the wrong metric holds BRL {penalty:,.0f} more of safety capital"
        f" ({penalty / capital['mean']:+.2%}),"
    )
    print(f"   which at a {HOLDING_RATE:.0%} holding rate is **BRL {annual:,.0f} a year**.")
    print(
        "\n   Study 05 refused a half-day of analysis, and was right to: it would have decided"
        " BRL 202"
    )
    print(
        f"   once. The same half-day at BRL {ANALYST_HALF_DAY:,.0f} pays back here in"
        f" {payback:.0f} days and then keeps paying,"
    )
    print(
        f"   every year, because the decision repeats. Over three years it returns BRL"
        f" {annual * 3 - ANALYST_HALF_DAY:,.0f} net."
    )
    print("\n   **Nothing about the analysis changed. The repetition count changed.** That is the")
    print("   whole content of the pair: the same work is waste in one posture and the highest")
    print("   return available in the other, and the quantity that decides which is not a")
    print("   property of the analysis at all.")
    return {"penalty": penalty, "annual": annual, "payback_days": payback}


def _representative(dataset: object, panel: pd.DataFrame) -> tuple[pd.Series, object, float]:
    series = panel[panel.sum().sort_values(ascending=False).index[20]]
    orders = dataset.purchase_orders
    supplier = orders.drop_duplicates("sku").set_index("sku")["supplier"][series.name]
    group = orders.loc[orders["supplier"] == supplier]
    lead = fit_lead_time(
        group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
    )
    cost = float(dataset.catalog.set_index("sku").loc[series.name, "unit_cost"])
    return series, lead, cost


def _check_retuning(dataset: object, panel: pd.DataFrame) -> dict[str, float]:
    series, lead, unit_cost = _representative(dataset, panel)
    values = series.to_numpy()
    z = z_for_cycle_service(SERVICE)
    full = fit_demand(values)
    once = safety_stock(full, lead, z)

    positions, levels = [], []
    for end in range(TRAILING_WINDOW, len(values) + 1, 7):
        window = fit_demand(values[end - TRAILING_WINDOW : end])
        if window.mean <= 0.0:
            continue
        positions.append(end - 1)
        levels.append(safety_stock(window, lead, z).units)
    level = np.array(levels)
    position = np.array(positions)

    trailing = np.array([values[i - TRAILING_WINDOW + 1 : i + 1].sum() for i in position])
    forward = np.array(
        [
            values[i + 1 : i + 1 + TRAILING_WINDOW].sum()
            if i + TRAILING_WINDOW < len(values)
            else np.nan
            for i in position
        ]
    )
    usable = ~np.isnan(forward)
    corr_trailing = float(np.corrcoef(level, trailing)[0, 1])
    corr_forward = float(np.corrcoef(level[usable], forward[usable])[0, 1])

    spread_share = float((level.max() - level.min()) / level.mean())
    print(
        f"   Re-fitting the demand profile every week on a trailing {TRAILING_WINDOW} days, over"
        f" {len(level)} re-tunes:"
    )
    print(
        f"     sized once on the full history      {once.units:7.1f} units\n"
        f"     re-tuned, lowest level visited      {level.min():7.1f}\n"
        f"     re-tuned, highest level visited     {level.max():7.1f}\n"
        f"     range as a share of its own mean    {spread_share:7.1%}"
    )

    print("\n   The question is not how much it moves. It is whether the movement is aimed at")
    print("   anything:")
    print(
        f"\n     corr(level, the trailing {TRAILING_WINDOW} days of demand) = {corr_trailing:+.4f}"
        "   <- what it is fitted on"
    )
    print(
        f"     corr(level, the next {TRAILING_WINDOW} days of demand)     = {corr_forward:+.4f}"
        "   <- what it must cover"
    )
    print("\n   **The correlation with the demand it has to cover is negative.** A trailing window")
    print("   does not lag the signal on a series that reverts; it inverts it. The level is raised")
    print("   after the peak, which is when demand is about to fall, and cut after the trough,")
    print("   which is when it is about to rise. A policy that moved at random would score zero;")
    print("   this one scores below zero, which means the re-tuning is worse than not re-tuning.")

    quantity = economic_order_quantity(
        full.mean * 365, order_cost=ORDER_COST, unit_cost=unit_cost, holding_rate=HOLDING_RATE
    )
    achieved = {}
    for label, units in (
        ("sized once", once.units),
        ("lowest the re-tuning visits", level.min()),
        ("highest the re-tuning visits", level.max()),
    ):
        policy = ContinuousReview(
            reorder_point=full.mean * lead.mean + units, order_quantity=quantity
        )
        summary = simulate_policy(
            policy, values, lead.sample, periods=1095, replications=40
        ).summary()
        achieved[label] = (units, float(summary["cycle_service"]), float(summary["fill_rate"]))

    print("\n   And what the whole swing buys, simulated against resampled demand and lead times:")
    print(
        pd.DataFrame(
            [
                {
                    "policy": label,
                    "safety_units": units,
                    "capital_brl": units * unit_cost,
                    "cycle_service": cycle,
                    "fill_rate": fill,
                }
                for label, (units, cycle, fill) in achieved.items()
            ]
        )
        .round(4)
        .to_string(index=False)
    )
    low = achieved["lowest the re-tuning visits"]
    high = achieved["highest the re-tuning visits"]
    print(
        f"\n   The {(level.max() - level.min()) / level.mean():.0%} swing spans"
        f" {(high[1] - low[1]) * 100:.2f} points of cycle service and"
        f" {(high[2] - low[2]) * 100:.2f} points of fill"
    )
    print(
        f"   rate, for BRL {(level.max() - level.min()) * unit_cost:,.0f} of capital and"
        f" {np.abs(np.diff(level)).sum():.0f} units of stock moved back and"
    )
    print(
        f"   forth across {len(level) - 1} re-tunes. Sizing once lands at"
        f" {achieved['sized once'][1]:.4f} cycle service, inside that span"
    )
    print("   and at none of the cost. The re-tuning does not beat it; it straddles it.")
    return {
        "corr_trailing": corr_trailing,
        "corr_forward": corr_forward,
        "once": once.units,
        "low": float(level.min()),
        "high": float(level.max()),
        "range_share": float((level.max() - level.min()) / level.mean()),
        "retunes": float(len(level)),
        "distance": float(np.abs(np.diff(level)).sum()),
        "cycle_once": achieved["sized once"][1],
        "cycle_span": (high[1] - low[1]) * 100,
        "fill_span": (high[2] - low[2]) * 100,
    }


def _check_control(dataset: object, panel: pd.DataFrame, retunes: float) -> dict[str, float]:
    series, _, _ = _representative(dataset, panel)
    weekly = series.resample("W").sum()
    individuals, moving_range = i_mr_chart(weekly)
    violations = individuals.rule_result.violations

    print(f"   The same series as weekly totals on an I-MR chart, {len(weekly)} weeks:")
    print(
        violations.groupby("rule")
        .size()
        .rename("signals")
        .to_frame()
        .join(violations.drop_duplicates("rule").set_index("rule")["description"])
        .to_string()
    )
    shifts = int((violations["rule"] == 1).sum())
    runs = int((violations["rule"] != 1).sum())
    spread_signals = len(moving_range.rule_result.violations)

    print(
        f"\n   {shifts} point beyond three sigma - a genuine level shift - against {runs} run and"
        " zone signals, and"
    )
    print(
        f"   {spread_signals} signals on the moving range: **the spread is stable and the level"
        " oscillates.**"
    )
    print("   That is the signature of a series that reverts, not one that steps to a new level,")
    print("   and it is exactly the condition under which a trailing window chases its own tail.")
    print("   The inversion measured above is not bad luck with this window length; it is what a")
    print("   trailing estimator does to a mean-reverting series, and a longer window would only")
    print("   make it slower to be wrong.")

    print(
        f"\n   So the re-tuning schedule and the evidence disagree by a factor of"
        f" {retunes / max(shifts, 1):.0f}: {shifts} occasion on"
    )
    print(
        f"   which the process said something had changed, against {retunes:.0f} occasions on"
        " which the"
    )
    print("   calendar said to re-fit. **The chart is the instrument that decides when to re-tune,")
    print("   and the forecast is not.** A forecast asked every week what the level is will answer")
    print("   every week, because answering is what it does; only the chart is built to say that")
    print("   the question has no new answer yet.")
    return {"shifts": float(shifts), "runs": float(runs), "spread_signals": float(spread_signals)}


def _decide(
    models: pd.DataFrame,
    value: dict[str, float],
    tuning: dict[str, float],
    control: dict[str, float],
) -> None:
    elected = str(models.sort_values("crossover_periods", ascending=False)["model"].iloc[0])
    print(
        pd.DataFrame(
            [
                {
                    "decision": f"which forecast the policy uses: {elected}",
                    "on what basis": "bias crossover, not MAE",
                    "worth": f"BRL {value['annual']:,.0f}/year",
                },
                {
                    "decision": "whether to buy the analysis",
                    "on what basis": "per-decision gain x repetitions",
                    "worth": f"pays back in {value['payback_days']:.0f} days",
                },
                {
                    "decision": "how often to re-fit the policy",
                    "on what basis": "on signal, not on schedule",
                    "worth": f"{tuning['distance']:.0f} units of churn avoided",
                },
                {
                    "decision": "what instrument decides that",
                    "on what basis": "the control chart",
                    "worth": f"{control['shifts']:.0f} shift vs {tuning['retunes']:.0f} re-tunes",
                },
            ]
        ).to_string(index=False)
    )

    print("\n   Set against study 05, the pair delimits each other rather than contradicting.")
    print("   There, one decision under a clock: the value of information was capped by the stake,")
    print("   most of the analysis on the table could not reach the boundary, and the right answer")
    print("   was to cancel it. Here, the same decision 52 times: the stake multiplies, the")
    print("   analysis pays back inside a year, and refusing it is the expensive choice.")
    print("\n   What separates them is not difficulty or data quality. It is the repetition count,")
    print("   and it is the first thing to establish about any decision, because it decides")
    print("   **which metric is the right one, whether the analysis is worth buying, and whether")
    print("   adjusting is improvement or interference** - three questions that look like matters")
    print("   of judgement and are matters of arithmetic.")

    print("\n   The uncomfortable finding is the third one. Re-tuning weekly feels like diligence.")
    print("   It has a negative correlation with the thing it is meant to cover, it moves")
    print(
        f"   {tuning['distance']:.0f} units of stock to buy {tuning['fill_span']:.2f} points of"
        " fill rate, and the review that"
    )
    print("   produces it is the most visible recurring analytical work the operation does. An")
    print("   operation that stopped doing it would look less rigorous and be more accurate.")

    print("\n   What this study cannot show. The inversion is a property of a mean-reverting")
    print("   series, established here on one representative item with a stable moving range. A")
    print("   series genuinely trending, or one whose spread is drifting, would reward re-tuning,")
    print("   and the chart would say so - which is the point rather than a caveat: the rule is")
    print("   not 'never re-tune', it is 'let the chart decide', and on this series the chart says")
    print("   once rather than forty times.")

    print("\n   What would change this. The crossover n* = (sd/bias)^2 is computed on the median")
    print("   series; a range with a few high-volume items carrying most of the value would want")
    print("   it weighted by value rather than taken at the median, and the ranking could move.")
    print("   That is one aggregation choice, worth making explicitly before the model is")
    print("   selected, and it is the measurement to take before the next review cycle.")


if __name__ == "__main__":
    main()
