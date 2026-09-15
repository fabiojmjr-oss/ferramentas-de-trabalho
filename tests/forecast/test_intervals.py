"""The forecast error distribution, and the two traps in front of reading it."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.forecast import (
    error_profile,
    horizon_profile,
    interval_coverage,
    prediction_interval,
    residuals,
)


def backtest(errors: dict[str, list[float]], steps: int = 2) -> pd.DataFrame:
    """Build a backtest result with known errors, so every statistic is hand-checkable."""
    rows = []
    for series, values in errors.items():
        for index, error in enumerate(values):
            rows.append(
                {
                    "series": series,
                    "model": "m",
                    "origin": index // steps,
                    "step": index % steps + 1,
                    "actual": 10.0,
                    "forecast": 10.0 + error,
                }
            )
    return pd.DataFrame(rows)


def test_error_is_forecast_minus_actual() -> None:
    """The sign convention decides every statement about direction, so it is pinned."""
    frame = residuals(backtest({"a": [2.0, -3.0]}))
    assert list(frame["error"]) == [2.0, -3.0]


def test_residuals_guards() -> None:
    with pytest.raises(KeyError, match="missing columns"):
        residuals(pd.DataFrame({"model": ["m"]}))
    with pytest.raises(KeyError, match="no model named"):
        residuals(backtest({"a": [1.0, 1.0]}), model="other")


def test_error_profile_against_hand_computed_values() -> None:
    frame = backtest({"a": [1.0, -1.0, 3.0, -3.0]})
    profile = error_profile(frame, "m").set_index("series")
    row = profile.loc["a"]
    assert row["observations"] == 4
    assert row["bias"] == pytest.approx(0.0)
    assert row["mae"] == pytest.approx(2.0)
    assert row["sd"] == pytest.approx(np.std([1.0, -1.0, 3.0, -3.0], ddof=1))
    # Every actual is 10, so demand has no variation and the ratio is not defined.
    assert row["demand_sd"] == pytest.approx(0.0)
    assert np.isnan(row["sd_ratio"])


def test_the_ratio_answers_whether_forecasting_reduces_the_buffer() -> None:
    """The finding this module exists for: the ratio runs in both directions."""
    rows = []
    rng = np.random.default_rng(1)
    actuals = rng.normal(100.0, 20.0, size=40)
    for name, error_scale in (("sharp", 5.0), ("useless", 40.0)):
        for index, actual in enumerate(actuals):
            error = rng.normal(0.0, error_scale)
            rows.append(
                {
                    "series": name,
                    "model": "m",
                    "origin": index // 2,
                    "step": index % 2 + 1,
                    "actual": float(actual),
                    "forecast": float(actual + error),
                }
            )
    profile = error_profile(pd.DataFrame(rows), "m").set_index("series")

    # A forecast tighter than the demand spread is worth buffering against.
    assert profile.loc["sharp", "sd_ratio"] < 1.0
    assert bool(profile.loc["sharp", "reduces_buffer"])
    # A forecast looser than it adds uncertainty to the replenishment decision.
    assert profile.loc["useless", "sd_ratio"] > 1.0
    assert not bool(profile.loc["useless", "reduces_buffer"])


def test_error_profile_needs_a_series_column() -> None:
    frame = backtest({"a": [1.0, 1.0]}).drop(columns=["series"])
    with pytest.raises(KeyError, match="no 'series' column"):
        error_profile(frame, "m")


def test_the_phase_lock_flag_is_reported_rather_than_left_to_be_noticed() -> None:
    """A step that is a whole number of seasons pins every horizon step to one phase."""
    frame = backtest({"a": [1.0, 2.0, 1.0, 2.0]})
    assert bool(
        horizon_profile(frame, "m", step_between_origins=28, season=7)["phase_locked"].all()
    )
    assert not horizon_profile(frame, "m", step_between_origins=25, season=7)["phase_locked"].any()
    # Not supplied means not asserted, rather than silently false.
    assert horizon_profile(frame, "m")["phase_locked"].isna().all()
    with pytest.raises(ValueError, match="must both be positive"):
        horizon_profile(frame, "m", step_between_origins=0, season=7)


def test_horizon_profile_reports_sqrt_step_for_comparison_not_as_a_model() -> None:
    # Errors have to vary within a step, or step one has no spread to scale the others against.
    frame = backtest({"a": [1.0, 2.0, 3.0, 6.0, -1.0, -2.0]})
    table = horizon_profile(frame, "m")
    assert list(table["step"]) == [1, 2]
    assert table["sqrt_step"].to_list() == pytest.approx([1.0, 2.0**0.5])
    assert table.loc[0, "sd_vs_step_1"] == pytest.approx(1.0)


def test_the_interval_is_empirical_and_the_normal_one_is_shown_beside_it() -> None:
    """On a skewed error distribution the two differ, which is the reason for reporting both."""
    rng = np.random.default_rng(2)
    skewed = rng.exponential(5.0, size=400) - 5.0
    rows = [
        {
            "series": "a",
            "model": "m",
            "origin": index,
            "step": 1,
            "actual": 50.0,
            "forecast": 50.0 + float(error),
        }
        for index, error in enumerate(skewed)
    ]
    frame = pd.DataFrame(rows)
    interval = prediction_interval(frame, "m", 0.95).iloc[0]

    # A right-skewed error means the forecast overshoots far more than it undershoots, so the
    # interval around the actual is asymmetric - and the normal one is not.
    assert abs(interval["lower"]) != pytest.approx(abs(interval["upper"]), rel=0.1)
    normal_width = interval["normal_upper"] - interval["normal_lower"]
    empirical_width = interval["upper"] - interval["lower"]
    assert normal_width > empirical_width

    with pytest.raises(ValueError, match="coverage must be"):
        prediction_interval(frame, "m", 1.0)


def test_coverage_reports_which_side_the_normal_interval_misses_on() -> None:
    """Which side decides whether the miss is a stockout or dead stock, so both are reported."""
    rng = np.random.default_rng(3)
    skewed = rng.exponential(5.0, size=600) - 5.0
    rows = [
        {
            "series": "a",
            "model": "m",
            "origin": index,
            "step": 1,
            "actual": 50.0,
            "forecast": 50.0 + float(error),
        }
        for index, error in enumerate(skewed)
    ]
    table = interval_coverage(pd.DataFrame(rows), "m", 0.95).iloc[0]

    assert table["nominal"] == pytest.approx(0.95)
    # The empirical interval is fitted to the residuals it is scored on, so it hits its nominal
    # level almost by construction. That is stated in the docstring and asserted here so the
    # figure is never mistaken for out-of-sample validation.
    assert table["empirical_coverage"] == pytest.approx(0.95, abs=0.01)
    # The normal interval, fitted to two moments of the same residuals, misses asymmetrically.
    assert table["normal_below"] != pytest.approx(table["normal_above"], abs=0.01)
    assert table["normal_below"] + table["normal_above"] == pytest.approx(
        1.0 - table["normal_coverage"], abs=1e-9
    )
