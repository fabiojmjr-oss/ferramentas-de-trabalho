"""The panel builder, the feasibility check and rolling-origin evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.forecast import (
    BASELINES,
    aggregate_panel,
    aggregation_effect,
    backtest_panel,
    rolling_origin,
    season_feasibility,
    summarise,
    to_panel,
)


@pytest.fixture
def sparse_demand() -> pd.DataFrame:
    """Two SKUs at one site, where one sells only in two of five weeks."""
    return pd.DataFrame(
        [
            {"date": "2025-01-06", "site": "A", "sku": "STEADY", "demand": 10},
            {"date": "2025-01-13", "site": "A", "sku": "STEADY", "demand": 10},
            {"date": "2025-01-20", "site": "A", "sku": "STEADY", "demand": 10},
            {"date": "2025-01-27", "site": "A", "sku": "STEADY", "demand": 10},
            {"date": "2025-02-03", "site": "A", "sku": "STEADY", "demand": 10},
            {"date": "2025-01-06", "site": "A", "sku": "LUMPY", "demand": 25},
            {"date": "2025-02-03", "site": "A", "sku": "LUMPY", "demand": 25},
        ]
    )


def test_to_panel_fills_the_missing_periods_with_zero(sparse_demand: pd.DataFrame) -> None:
    """The absent periods are zeros, not absent. Fitting to the rows you were given fits the
    selling weeks of a slow mover, which is a different and much easier series."""
    panel = to_panel(sparse_demand, freq="W")

    assert panel.shape == (5, 2)
    assert list(panel["A | LUMPY"]) == [25.0, 0.0, 0.0, 0.0, 25.0]
    assert list(panel["A | STEADY"]) == [10.0] * 5


def test_to_panel_validates_its_input(sparse_demand: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="quantity"):
        to_panel(sparse_demand, value_col="quantity")
    with pytest.raises(ValueError, match="demand is empty"):
        to_panel(sparse_demand.iloc[:0])


def test_aggregate_panel_collapses_to_a_total(sparse_demand: pd.DataFrame) -> None:
    panel = to_panel(sparse_demand, freq="W")
    total = aggregate_panel(panel)

    assert list(total.columns) == ["total"]
    assert list(total["total"]) == [35.0, 10.0, 10.0, 10.0, 35.0]


def test_aggregate_panel_can_keep_one_key_component(sparse_demand: pd.DataFrame) -> None:
    panel = to_panel(sparse_demand, freq="W")
    by_site = aggregate_panel(panel, level="0")
    assert list(by_site.columns) == ["A"]
    assert by_site["A"].sum() == panel.to_numpy().sum()


def test_aggregate_panel_refuses_an_out_of_range_level(sparse_demand: pd.DataFrame) -> None:
    panel = to_panel(sparse_demand, freq="W")
    with pytest.raises(ValueError, match="out of range"):
        aggregate_panel(panel, level="5")


def test_season_feasibility_catches_the_one_year_weekly_trap() -> None:
    """Weekly data over one year cannot support an annual baseline, and the failure is silent.

    Every week of the year is observed once, so there is no repetition to learn from and none to
    validate against. The seasonal baseline falls back to a non-seasonal one and every scaled
    metric returns nan, while the run completes and reports a number.
    """
    check = season_feasibility(periods=53, season=52, min_train=40, horizon=4)

    assert not check.usable
    assert not check.seasonal_baseline_available
    assert "silently fall back" in check.message


def test_season_feasibility_accepts_weekly_seasonality_on_daily_data() -> None:
    check = season_feasibility(periods=365, season=7, min_train=120, horizon=7, step=28)

    assert check.usable
    assert check.origins == 9
    assert check.scale_available
    assert "both available" in check.message


def test_season_feasibility_reports_when_no_origin_fits() -> None:
    check = season_feasibility(periods=20, season=7, min_train=18, horizon=7)
    assert check.origins == 0
    assert not check.usable
    assert "no origin fits" in check.message


def test_season_feasibility_validates_its_arguments() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        season_feasibility(periods=0)


def test_rolling_origin_walks_forward_and_scores_every_step() -> None:
    series = pd.Series(np.arange(20.0), index=pd.period_range("2025-01-01", periods=20, freq="D"))
    results = rolling_origin(series, {"naive": BASELINES["naive"]}, horizon=2, step=3, min_train=10)

    # Origins at 10, 13 and 16; the next would be 19, which needs a period 21 that does not
    # exist. season_feasibility computes the same count from the same arithmetic.
    assert results["origin"].nunique() == 3
    assert season_feasibility(periods=20, season=1, min_train=10, horizon=2, step=3).origins == 3
    assert set(results["step"]) == {1, 2}
    first = results.iloc[0]
    assert first["forecast"] == 9.0, "the naive forecast repeats the last training value"
    assert first["actual"] == 10.0


def test_rolling_origin_returns_nothing_when_the_series_is_too_short() -> None:
    series = pd.Series([1.0, 2.0], index=pd.period_range("2025-01-01", periods=2, freq="D"))
    assert rolling_origin(series, {"naive": BASELINES["naive"]}, min_train=10).empty


def test_rolling_origin_validates_its_arguments() -> None:
    series = pd.Series([1.0] * 20, index=pd.period_range("2025-01-01", periods=20, freq="D"))
    with pytest.raises(ValueError, match="must all be positive"):
        rolling_origin(series, {"naive": BASELINES["naive"]}, horizon=0)
    with pytest.raises(ValueError, match="at least one model"):
        rolling_origin(series, {})


def test_summarise_reports_the_share_of_series_beaten_not_only_the_average() -> None:
    """A pooled average can favour a model that loses on most series, because the mean is
    carried by a few large ones. Both numbers are reported so the disagreement is visible."""
    periods = pd.period_range("2025-01-01", periods=40, freq="D")
    rng = np.random.default_rng(3)
    panel = pd.DataFrame(
        {
            "small": 5.0 + rng.normal(0, 1, 40),
            "large": 500.0 + rng.normal(0, 1, 40),
        },
        index=periods,
    )
    models = {
        "seasonal_naive": BASELINES["seasonal_naive"],
        "moving_average": BASELINES["moving_average"],
    }
    results = backtest_panel(panel, models, horizon=3, step=5, min_train=20, season=7)
    summary = summarise(results, panel, min_train=20, season=7).set_index("model")

    assert set(summary.index) == {"seasonal_naive", "moving_average"}
    assert np.isnan(summary.loc["seasonal_naive", "beats_reference_share"])
    assert 0.0 <= summary.loc["moving_average", "beats_reference_share"] <= 1.0
    assert summary.loc["seasonal_naive", "relative_mase"] == pytest.approx(1.0)


def test_summarise_counts_the_series_it_could_not_scale() -> None:
    periods = pd.period_range("2025-01-01", periods=40, freq="D")
    panel = pd.DataFrame({"flat": np.full(40, 7.0)}, index=periods)
    results = backtest_panel(panel, {"naive": BASELINES["naive"]}, horizon=3, step=5, min_train=20)
    summary = summarise(results, panel, reference="naive", min_train=20, season=1).set_index(
        "model"
    )

    assert summary.loc["naive", "series_without_scale"] == 1
    assert np.isnan(summary.loc["naive", "mase"])


def test_summarise_validates_its_arguments() -> None:
    periods = pd.period_range("2025-01-01", periods=40, freq="D")
    panel = pd.DataFrame({"a": np.arange(40.0)}, index=periods)
    results = backtest_panel(panel, {"naive": BASELINES["naive"]}, horizon=3, step=5, min_train=20)

    with pytest.raises(KeyError, match="is not among"):
        summarise(results, panel, reference="ets", min_train=20)
    with pytest.raises(ValueError, match="results is empty"):
        summarise(results.iloc[:0], panel, reference="naive", min_train=20)


def test_bias_is_additive_under_aggregation() -> None:
    """Errors partly cancel when series are summed. Bias does not - it adds up exactly.

    This is an arithmetic identity rather than an empirical result, and it is the reason a
    per-item bias that looks negligible is not negligible for the network: the mean bias per
    series times the number of series is the bias of the total, to the last decimal.
    """
    periods = pd.period_range("2025-01-01", periods=40, freq="D")
    rng = np.random.default_rng(11)
    panel = pd.DataFrame(
        {f"s{index}": 10.0 + rng.normal(0, 2, 40) for index in range(12)}, index=periods
    )
    total = aggregate_panel(panel)

    models = {"moving_average": BASELINES["moving_average"]}
    kwargs = {"horizon": 3, "step": 5, "min_train": 20, "season": 7}
    per_series = summarise(
        backtest_panel(panel, models, **kwargs),  # type: ignore[arg-type]
        panel,
        reference="moving_average",
        min_train=20,
        season=7,
    ).set_index("model")
    aggregated = summarise(
        backtest_panel(total, models, **kwargs),  # type: ignore[arg-type]
        total,
        reference="moving_average",
        min_train=20,
        season=7,
    ).set_index("model")

    assert per_series.loc["moving_average", "bias"] * panel.shape[1] == pytest.approx(
        aggregated.loc["moving_average", "bias"], abs=1e-9
    )


def test_aggregation_effect_scores_every_level() -> None:
    periods = pd.period_range("2025-01-01", periods=60, freq="D")
    rng = np.random.default_rng(5)
    fine = pd.DataFrame(
        {f"s{index}": 10.0 + rng.normal(0, 2, 60) for index in range(6)}, index=periods
    )
    table = aggregation_effect(
        {"series": fine, "total": aggregate_panel(fine)},
        {"seasonal_naive": BASELINES["seasonal_naive"], "naive": BASELINES["naive"]},
        horizon=7,
        step=14,
        min_train=30,
        season=7,
    )

    assert set(table["level"]) == {"series", "total"}
    assert table.loc[table["level"] == "series", "series"].iloc[0] == 6
    assert table.loc[table["level"] == "total", "series"].iloc[0] == 1


def test_aggregation_effect_handles_a_level_with_no_usable_origin() -> None:
    periods = pd.period_range("2025-01-01", periods=5, freq="D")
    tiny = pd.DataFrame({"a": np.arange(5.0)}, index=periods)
    assert aggregation_effect({"tiny": tiny}, {"naive": BASELINES["naive"]}, min_train=52).empty
