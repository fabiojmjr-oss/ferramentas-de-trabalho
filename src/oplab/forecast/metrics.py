"""Forecast error, and why the metric everyone uses cannot be used here.

**MAPE is undefined wherever the actual is zero**, and on an assortment with slow movers that
is most of the periods. It is also asymmetric: a forecast of 2 against an actual of 1 scores
100% error, while a forecast of 0 against an actual of 1 also scores 100% - so over-forecasting
is unboundedly punishable and under-forecasting is capped. Optimise a model against MAPE on
sparse demand and the model learns to forecast low, which on a service-critical item is the
expensive direction.

:func:`mape_coverage` measures the damage directly: it reports the share of periods and of
series on which MAPE cannot be computed at all. On the bundled assortment that share is most of
it, which settles the argument faster than the theory does.

**MASE and RMSSE** are the replacements. Both divide the error by the error a naive forecast
would have made **in-sample**, so they are scale-free, defined when actuals are zero, and
comparable across series. A MASE of 1.0 means "no better than repeating last season"; above 1.0
means worse than doing nothing. The M5 competition settled on RMSSE for exactly this reason.

They have one failure mode worth knowing: the scale is zero when the in-sample naive error is
zero - a training window that is entirely flat, which happens on very sparse items. That
returns ``nan`` rather than infinity, and the count of such series is reported rather than
dropped silently.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _pair(actual: np.ndarray, forecast: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(actual, dtype=float).reshape(-1)
    f = np.asarray(forecast, dtype=float).reshape(-1)
    if a.size != f.size:
        raise ValueError(f"actual has {a.size} values and forecast has {f.size}")
    if a.size == 0:
        raise ValueError("actual is empty")
    return a, f


def mae(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean absolute error."""
    a, f = _pair(actual, forecast)
    return float(np.mean(np.abs(a - f)))


def rmse(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Root mean squared error."""
    a, f = _pair(actual, forecast)
    return float(np.sqrt(np.mean((a - f) ** 2)))


def bias(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean error, signed. Positive means the forecast runs high.

    Reported alongside every accuracy figure because accuracy hides direction, and direction is
    what buys or starves inventory. Croston's method is accurate and biased high; a summary that
    only shows MASE cannot see that.
    """
    a, f = _pair(actual, forecast)
    return float(np.mean(f - a))


def naive_scale(insample: np.ndarray, season: int = 1, squared: bool = False) -> float:
    """In-sample error of a seasonal naive forecast, the denominator for MASE and RMSSE.

    Args:
        insample: The training window.
        season: Seasonal lag. ``1`` gives the non-seasonal scale.
        squared: Return the root mean squared difference instead of the mean absolute one.

    Returns:
        The scale, or ``nan`` when the training window is too short or entirely flat.
    """
    values = np.asarray(insample, dtype=float).reshape(-1)
    if season < 1:
        raise ValueError("season must be at least 1")
    if values.size <= season:
        return float("nan")
    differences = values[season:] - values[:-season]
    scale = (
        float(np.sqrt(np.mean(differences**2))) if squared else float(np.mean(np.abs(differences)))
    )
    return scale if scale > 0 else float("nan")


def mase(actual: np.ndarray, forecast: np.ndarray, insample: np.ndarray, season: int = 1) -> float:
    """Mean absolute scaled error. 1.0 is "no better than the naive forecast"."""
    scale = naive_scale(insample, season=season)
    return mae(actual, forecast) / scale if np.isfinite(scale) else float("nan")


def rmsse(actual: np.ndarray, forecast: np.ndarray, insample: np.ndarray, season: int = 1) -> float:
    """Root mean squared scaled error, as used in the M5 competition."""
    scale = naive_scale(insample, season=season, squared=True)
    return rmse(actual, forecast) / scale if np.isfinite(scale) else float("nan")


def mape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean absolute percentage error, over the periods where it is defined.

    Provided so that the comparison against MASE can be made rather than asserted. Read
    :func:`mape_coverage` in the same breath: a MAPE computed on a third of the periods is not a
    measure of the forecast, it is a measure of the periods that happened to be non-zero.
    """
    a, f = _pair(actual, forecast)
    defined = a != 0
    if not defined.any():
        return float("nan")
    return float(np.mean(np.abs((a[defined] - f[defined]) / a[defined])))


@dataclass(frozen=True)
class MapeCoverage:
    """How much of the data MAPE can actually be computed on.

    Attributes:
        periods: Total period-observations considered.
        defined_periods: Those with a non-zero actual.
        series: Total series considered.
        fully_defined_series: Series with no zero actual at all.
        undefined_series: Series with no non-zero actual, where MAPE does not exist.
    """

    periods: int
    defined_periods: int
    series: int
    fully_defined_series: int
    undefined_series: int

    @property
    def period_coverage(self) -> float:
        """Share of period-observations on which MAPE is defined."""
        return self.defined_periods / self.periods if self.periods else float("nan")

    @property
    def series_coverage(self) -> float:
        """Share of series on which MAPE is defined for every period."""
        return self.fully_defined_series / self.series if self.series else float("nan")

    def summary(self) -> str:
        """One line for a report, stating the damage rather than implying it."""
        return (
            f"MAPE is defined on {self.period_coverage:.1%} of period-observations and on "
            f"{self.series_coverage:.1%} of series without gaps; it does not exist at all for "
            f"{self.undefined_series} of {self.series} series."
        )


def mape_coverage(panel: np.ndarray) -> MapeCoverage:
    """Measure how much of a panel MAPE can be computed on.

    Args:
        panel: Two-dimensional array of actuals, periods by series.

    Returns:
        A :class:`MapeCoverage`.

    Raises:
        ValueError: If ``panel`` is not two-dimensional or is empty.
    """
    values = np.asarray(panel, dtype=float)
    if values.ndim != 2:
        raise ValueError("panel must be two-dimensional, periods by series")
    if values.size == 0:
        raise ValueError("panel is empty")

    non_zero = values != 0
    return MapeCoverage(
        periods=int(values.size),
        defined_periods=int(non_zero.sum()),
        series=int(values.shape[1]),
        fully_defined_series=int(non_zero.all(axis=0).sum()),
        undefined_series=int((~non_zero).all(axis=0).sum()),
    )
