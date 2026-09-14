"""Control chart construction."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.spc import (
    a2,
    d2,
    d4,
    i_mr_chart,
    overdispersion_ratio,
    p_chart,
    u_chart,
    xbar_r_chart,
)


@pytest.fixture
def identical_subgroups() -> pd.DataFrame:
    """Twelve identical subgroups of ``[1, 2, 3, 4, 5]``.

    Every subgroup has mean 3 and range 4, so the limits are exact by hand:
    X-bar centre 3, half-width ``A2(5) * 4 = 2.308``; R centre 4, upper limit
    ``D4(5) * 4 = 8.456``.
    """
    return pd.DataFrame(
        {
            "subgroup": np.repeat(np.arange(1, 13), 5),
            "value": np.tile([1.0, 2.0, 3.0, 4.0, 5.0], 12),
        }
    )


def test_xbar_r_limits_match_the_hand_calculation(identical_subgroups: pd.DataFrame) -> None:
    xbar, r = xbar_r_chart(identical_subgroups)

    assert xbar.center == pytest.approx(3.0)
    assert xbar.ucl.iloc[0] == pytest.approx(3.0 + a2(5) * 4.0)
    assert xbar.lcl.iloc[0] == pytest.approx(3.0 - a2(5) * 4.0)
    assert xbar.sigma.iloc[0] == pytest.approx(a2(5) * 4.0 / 3.0)

    assert r.center == pytest.approx(4.0)
    assert r.ucl.iloc[0] == pytest.approx(d4(5) * 4.0)
    assert r.lcl.iloc[0] == pytest.approx(0.0), "D3 is zero for n = 5"


def test_a_perfectly_stable_process_produces_no_signals(
    identical_subgroups: pd.DataFrame,
) -> None:
    xbar, r = xbar_r_chart(identical_subgroups)
    assert not xbar.out_of_control.any()
    assert not r.out_of_control.any()


def test_varying_subgroup_size_is_refused_with_a_useful_message() -> None:
    data = pd.DataFrame({"subgroup": [1, 1, 1, 2, 2], "value": [1.0, 2.0, 3.0, 4.0, 5.0]})
    with pytest.raises(ValueError, match="constant subgroup size"):
        xbar_r_chart(data)


def test_missing_columns_are_reported_by_name(identical_subgroups: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="weight"):
        xbar_r_chart(identical_subgroups, value="weight")


def test_a_baseline_moves_the_centre_line_not_the_limit_width() -> None:
    """A mean shift changes the centre line; the limit width comes from within-subgroup range.

    This is the mechanism behind the ``baseline`` argument, and it is the opposite of the
    common belief that a contaminated baseline widens the limits.
    """
    rng = np.random.default_rng(3)
    stable = rng.normal(100.0, 1.0, size=(30, 5))
    shifted = rng.normal(104.0, 1.0, size=(30, 5))
    values = np.vstack([stable, shifted])
    data = pd.DataFrame(
        {
            "subgroup": np.repeat(np.arange(1, 61), 5),
            "value": values.reshape(-1),
        }
    )

    fitted_on_stable, _ = xbar_r_chart(data, baseline=slice(0, 30))
    fitted_on_all, _ = xbar_r_chart(data)

    width_stable = float(fitted_on_stable.ucl.iloc[0] - fitted_on_stable.center)
    width_all = float(fitted_on_all.ucl.iloc[0] - fitted_on_all.center)
    assert width_all == pytest.approx(width_stable, rel=0.10)

    assert fitted_on_all.center > fitted_on_stable.center + 1.0
    stable_false_alarms = int(fitted_on_all.out_of_control.iloc[:30].sum())
    assert stable_false_alarms > int(fitted_on_stable.out_of_control.iloc[:30].sum())


def test_i_mr_limits_use_the_average_moving_range() -> None:
    values = pd.Series([10.0, 12.0, 10.0, 12.0, 10.0, 12.0, 10.0, 12.0])
    individuals, mr = i_mr_chart(values)

    assert individuals.center == pytest.approx(11.0)
    assert individuals.sigma.iloc[0] == pytest.approx(2.0 / d2(2))
    assert mr.center == pytest.approx(2.0)
    assert mr.lcl.iloc[0] == pytest.approx(0.0)


def test_i_mr_needs_at_least_three_observations() -> None:
    with pytest.raises(ValueError, match="at least 3 observations"):
        i_mr_chart(pd.Series([1.0, 2.0]))


def test_p_chart_limits_widen_as_the_sample_shrinks() -> None:
    counts = pd.Series([5, 50])
    sizes = pd.Series([100, 1000])
    chart = p_chart(counts, sizes)

    assert chart.center == pytest.approx(55 / 1100)
    small, large = chart.ucl.iloc[0] - chart.center, chart.ucl.iloc[1] - chart.center
    assert small > large, "a smaller sample must get wider limits"
    assert large == pytest.approx(small / np.sqrt(10), rel=1e-9)


def test_p_chart_centre_line_is_pooled_not_averaged() -> None:
    counts = pd.Series([1, 100])
    sizes = pd.Series([10, 1000])
    chart = p_chart(counts, sizes)
    # The naive mean of the two proportions is 0.1; the pooled value weights by sample size.
    assert chart.center == pytest.approx(101 / 1010)


def test_p_chart_clips_impossible_limits() -> None:
    chart = p_chart(pd.Series([1, 1, 1]), pd.Series([50, 50, 50]))
    assert (chart.lcl >= 0.0).all()
    assert (chart.ucl <= 1.0).all()


@pytest.mark.parametrize(
    ("counts", "sizes", "message"),
    [
        ([5], [0], "sample_size must be positive"),
        ([50], [10], "cannot exceed sample_size"),
    ],
)
def test_p_chart_validates_its_inputs(counts: list[int], sizes: list[int], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        p_chart(pd.Series(counts), pd.Series(sizes))


def test_u_chart_scales_limits_by_exposure() -> None:
    defects = pd.Series([10, 100])
    exposure = pd.Series([100.0, 1000.0])
    chart = u_chart(defects, exposure)

    assert chart.center == pytest.approx(110 / 1100)
    assert chart.sigma.iloc[0] == pytest.approx(np.sqrt(chart.center / 100.0))
    assert (chart.lcl >= 0.0).all()


def test_u_chart_requires_positive_exposure() -> None:
    with pytest.raises(ValueError, match="exposure must be positive"):
        u_chart(pd.Series([1, 2]), pd.Series([1.0, 0.0]))


def test_chart_frame_exposes_everything_needed_to_plot(
    identical_subgroups: pd.DataFrame,
) -> None:
    xbar, _ = xbar_r_chart(identical_subgroups)
    frame = xbar.to_frame()
    assert {"point", "center", "lcl", "ucl", "sigma", "n", "z", "out_of_control"} <= set(
        frame.columns
    )
    assert len(frame) == 12
    assert xbar.summary()["chart"] == "X-bar"


def test_the_injected_special_cause_is_detected(dataset) -> None:  # type: ignore[no-untyped-def]
    """The generator shifts the process at subgroup 43; the chart must find it there."""
    xbar, r_chart = xbar_r_chart(dataset.subgroups, baseline=slice(0, 40))
    first_signal = xbar.violations.query("position >= 41")["position"].min()
    assert 41 <= first_signal <= 45
    assert not r_chart.out_of_control.any(), "a mean shift must not disturb the range chart"


def test_overdispersion_ratio_is_near_one_when_the_model_fits() -> None:
    rng = np.random.default_rng(19)
    sizes = pd.Series(rng.integers(200, 800, size=200).astype(float))
    counts = pd.Series(rng.binomial(sizes.astype(int), 0.1).astype(float))
    ratio = overdispersion_ratio(p_chart(counts, sizes))
    assert ratio == pytest.approx(1.0, abs=0.2)


def test_overdispersion_ratio_detects_clustered_failures() -> None:
    """Correlated trials inflate point-to-point variation beyond the binomial model."""
    rng = np.random.default_rng(19)
    # Each period's true rate varies; that extra layer of variation is what clustering does.
    rates = rng.beta(2, 18, size=200)
    sizes = pd.Series(np.full(200, 500.0))
    counts = pd.Series(rng.binomial(500, rates).astype(float))
    ratio = overdispersion_ratio(p_chart(counts, sizes))
    assert ratio > 1.5


def test_overdispersion_ratio_is_undefined_for_a_single_point() -> None:
    chart = p_chart(pd.Series([5.0]), pd.Series([100.0]))
    assert np.isnan(overdispersion_ratio(chart))
