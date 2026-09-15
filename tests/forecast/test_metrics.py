"""Forecast error metrics, and the coverage problem that rules MAPE out."""

from __future__ import annotations

import numpy as np
import pytest

from oplab.forecast import bias, mae, mape, mape_coverage, mase, naive_scale, rmse, rmsse


def test_mae_and_rmse_match_the_hand_calculation() -> None:
    actual, forecast = [1.0, 2.0], [2.0, 4.0]
    assert mae(actual, forecast) == pytest.approx(1.5)
    assert rmse(actual, forecast) == pytest.approx(np.sqrt(2.5))


def test_bias_is_signed_and_reports_direction() -> None:
    assert bias([1.0, 2.0], [2.0, 4.0]) == pytest.approx(1.5), "forecast runs high"
    assert bias([2.0, 4.0], [1.0, 2.0]) == pytest.approx(-1.5), "forecast runs low"
    assert bias([1.0, 3.0], [3.0, 1.0]) == pytest.approx(0.0), "errors cancel, bias does not exist"


def test_naive_scale_is_the_in_sample_naive_error() -> None:
    # Differences of a straight line are all 1.
    assert naive_scale([1.0, 2.0, 3.0, 4.0], season=1) == pytest.approx(1.0)
    # At a seasonal lag of 2 the differences are all 2.
    assert naive_scale([1.0, 2.0, 3.0, 4.0], season=2) == pytest.approx(2.0)


def test_naive_scale_is_undefined_on_a_flat_window() -> None:
    """A training window with no movement gives a scale of zero, and a scaled metric divided by
    zero is not infinity - it is unavailable. Returning nan keeps it countable."""
    assert np.isnan(naive_scale([3.0, 3.0, 3.0, 3.0], season=1))
    assert np.isnan(naive_scale([1.0, 2.0], season=5)), "window shorter than the season"


def test_mase_is_the_error_divided_by_the_naive_scale() -> None:
    assert mase([1.0, 2.0], [2.0, 4.0], insample=[1.0, 2.0, 3.0, 4.0], season=1) == pytest.approx(
        1.5
    )


def test_rmsse_uses_the_squared_scale() -> None:
    value = rmsse([1.0, 2.0], [2.0, 4.0], insample=[1.0, 2.0, 3.0, 4.0], season=1)
    assert value == pytest.approx(np.sqrt(2.5) / 1.0)


def test_a_scaled_metric_above_one_means_worse_than_doing_nothing() -> None:
    insample = [10.0, 12.0, 10.0, 12.0]  # naive scale of 2
    good = mase([10.0], [10.0], insample=insample, season=1)
    bad = mase([10.0], [30.0], insample=insample, season=1)
    assert good == pytest.approx(0.0)
    assert bad == pytest.approx(10.0)
    assert bad > 1.0


def test_mase_is_unavailable_rather_than_infinite_on_a_flat_window() -> None:
    assert np.isnan(mase([1.0], [2.0], insample=[5.0, 5.0, 5.0], season=1))


def test_mape_skips_the_periods_where_it_is_undefined() -> None:
    # The zero actual cannot be divided by, so only the second period counts.
    assert mape([0.0, 2.0], [1.0, 4.0]) == pytest.approx(1.0)


def test_mape_does_not_exist_for_an_all_zero_series() -> None:
    assert np.isnan(mape([0.0, 0.0], [1.0, 2.0]))


def test_mape_is_asymmetric() -> None:
    """Over-forecasting is unboundedly punishable and under-forecasting is capped at 100%.

    Optimise against MAPE on sparse demand and the model learns to forecast low, which on a
    service-critical item is the expensive direction.
    """
    over = mape([1.0], [5.0])
    under = mape([1.0], [0.0])
    assert over == pytest.approx(4.0)
    assert under == pytest.approx(1.0)
    assert over > under


def test_mape_coverage_counts_what_cannot_be_computed() -> None:
    panel = np.array(
        [
            [1.0, 0.0, 0.0],
            [2.0, 3.0, 0.0],
        ]
    )
    coverage = mape_coverage(panel)

    assert coverage.periods == 6
    assert coverage.defined_periods == 3
    assert coverage.series == 3
    assert coverage.fully_defined_series == 1, "only the first column has no zeros"
    assert coverage.undefined_series == 1, "the third column is all zeros"
    assert coverage.period_coverage == pytest.approx(0.5)
    assert coverage.series_coverage == pytest.approx(1 / 3)
    assert "MAPE is defined on" in coverage.summary()


def test_mape_coverage_validates_its_input() -> None:
    with pytest.raises(ValueError, match="two-dimensional"):
        mape_coverage(np.array([1.0, 2.0]))
    with pytest.raises(ValueError, match="panel is empty"):
        mape_coverage(np.empty((0, 0)))


def test_mismatched_lengths_are_refused() -> None:
    with pytest.raises(ValueError, match="actual has 2 values and forecast has 3"):
        mae([1.0, 2.0], [1.0, 2.0, 3.0])


def test_an_empty_comparison_is_refused() -> None:
    with pytest.raises(ValueError, match="actual is empty"):
        mae([], [])
