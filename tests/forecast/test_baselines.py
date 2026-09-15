"""The baseline and intermittent-demand models, on histories short enough to check by hand."""

from __future__ import annotations

import numpy as np
import pytest

from oplab.forecast import croston, drift, moving_average, naive, sba, seasonal_naive, tsb

# Two demand occurrences of five units, three periods apart.
SPARSE = np.array([0.0, 0.0, 5.0, 0.0, 0.0, 5.0])


def test_naive_repeats_the_last_observation() -> None:
    assert list(naive([1.0, 2.0, 3.0], 2)) == [3.0, 3.0]


def test_seasonal_naive_repeats_the_last_season() -> None:
    history = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    assert list(seasonal_naive(history, 4, season=3)) == [4.0, 5.0, 6.0, 4.0]


def test_seasonal_naive_falls_back_when_the_history_is_too_short() -> None:
    """The fallback is a real limitation, and it is why season_feasibility exists.

    A series with less than one season of history cannot be forecast seasonally. Falling back
    silently is what turns "we compared against a seasonal baseline" into a false statement.
    """
    history = [1.0, 2.0, 3.0]
    assert list(seasonal_naive(history, 2, season=10)) == list(naive(history, 2))


def test_moving_average_uses_the_window() -> None:
    assert list(moving_average([1.0, 2.0, 3.0, 4.0], 2, window=2)) == [3.5, 3.5]


def test_moving_average_shortens_the_window_to_the_history() -> None:
    assert list(moving_average([2.0, 4.0], 1, window=10)) == [3.0]


def test_drift_extrapolates_the_average_change() -> None:
    # From 1 to 5 over two steps is a slope of 2.
    assert list(drift([1.0, 3.0, 5.0], 2)) == [7.0, 9.0]


def test_croston_forecasts_size_over_interval() -> None:
    """Size smooths to 5 and interval to 3, so the rate is 5/3 regardless of the horizon."""
    assert croston(SPARSE, 3) == pytest.approx([5 / 3] * 3)


def test_sba_is_croston_scaled_by_the_bias_correction() -> None:
    alpha = 0.1
    assert sba(SPARSE, 2) == pytest.approx(croston(SPARSE, 2) * (1 - alpha / 2))


def test_sba_removes_croston_bias_on_a_stationary_sparse_series() -> None:
    """Croston forecasts high on stationary intermittent demand; SBA is closer to the truth.

    The series below has a known mean of exactly 1.0 unit per period. Croston's ratio of
    smoothed size to smoothed interval overshoots it, which is the bias the Syntetos-Boylan
    correction exists to remove.
    """
    rng = np.random.default_rng(7)
    occurrences = rng.random(4000) < 0.2
    history = np.where(occurrences, 5.0, 0.0)
    true_rate = float(history.mean())

    croston_rate = float(croston(history, 1)[0])
    sba_rate = float(sba(history, 1)[0])

    assert croston_rate > true_rate, "Croston overshoots the true rate"
    assert abs(sba_rate - true_rate) < abs(croston_rate - true_rate)


def test_tsb_decays_towards_zero_when_demand_stops() -> None:
    """This is the difference from Croston, and on an assortment with obsolescence it is the
    whole result: Croston only updates at demand epochs, so a dead item keeps the rate it had
    when it was alive."""
    alive = np.tile([0.0, 0.0, 0.0, 0.0, 10.0], 20)
    dead = np.concatenate([alive, np.zeros(120)])

    assert float(tsb(dead, 1)[0]) < float(tsb(alive, 1)[0]) / 2
    # Croston cannot see the gap at all: its interval estimate never updates after the last
    # occurrence, so the forecast is unchanged.
    assert float(croston(dead, 1)[0]) == pytest.approx(float(croston(alive, 1)[0]))


def test_every_method_returns_zero_for_a_series_with_no_demand() -> None:
    empty = np.zeros(20)
    for method in (croston, sba, tsb):
        assert list(method(empty, 3)) == [0.0, 0.0, 0.0]


def test_a_single_occurrence_is_spread_over_the_history() -> None:
    history = np.array([0.0, 0.0, 4.0, 0.0])
    assert croston(history, 1) == pytest.approx([1.0])


@pytest.mark.parametrize(
    "method", [naive, seasonal_naive, moving_average, drift, croston, sba, tsb]
)
def test_a_non_positive_horizon_is_refused(method: object) -> None:
    with pytest.raises(ValueError, match="horizon must be at least 1"):
        method(np.array([1.0, 2.0]), 0)  # type: ignore[operator]


@pytest.mark.parametrize("method", [naive, croston, sba, tsb])
def test_an_empty_history_is_refused(method: object) -> None:
    with pytest.raises(ValueError, match="history is empty"):
        method(np.array([]), 1)  # type: ignore[operator]


def test_a_non_finite_history_is_refused() -> None:
    with pytest.raises(ValueError, match="non-finite"):
        naive(np.array([1.0, np.nan]), 1)


@pytest.mark.parametrize(
    ("method", "kwargs", "message"),
    [
        (seasonal_naive, {"season": 0}, "season must be at least 1"),
        (moving_average, {"window": 0}, "window must be at least 1"),
        (croston, {"alpha": 0.0}, "alpha must be in"),
        (sba, {"alpha": 1.5}, "alpha must be in"),
        (tsb, {"beta": 0.0}, "alpha and beta must be in"),
    ],
)
def test_parameters_are_validated(method: object, kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        method(np.array([1.0, 0.0, 2.0]), 1, **kwargs)  # type: ignore[operator]
