"""The forecasts a proposal has to beat, and the three methods built for sparse demand.

Every model here takes a history and a horizon and returns a forecast. Nothing here is a
production forecasting library - use ``statsforecast`` or its equivalents for that. These exist
so that the comparison is auditable: a proposal that cannot beat ``seasonal_naive`` on a
rolling-origin backtest has not been shown to do anything, and that claim is only as credible
as the baseline it is made against.

**Seasonal naive is the baseline that matters.** Repeating the value from one season ago costs
nothing to build, needs no data pipeline, and on weekly demand with a strong weekly or annual
pattern it is hard to beat by much. A great many forecasting projects are evaluated against
either nothing or against a moving average, which is a lower bar, and then report an
improvement that a one-line rule would have delivered.

**Croston's method is biased, and its two successors say so.** Croston forecasts demand per
period as estimated size divided by estimated interval, and the expectation of that ratio is
larger than the expectation of the demand rate - so it forecasts high, systematically. The
Syntetos-Boylan approximation multiplies by ``1 - alpha / 2`` to correct it. Teunter-Syntetos-
Babai updates the demand probability in **every** period rather than only when demand occurs,
which is what lets it recognise that an item has stopped selling. Running all three and
reporting the difference is the only way to know which regime an assortment is in.
"""

from __future__ import annotations

import numpy as np

Forecast = np.ndarray


def _validate(history: np.ndarray, horizon: int) -> np.ndarray:
    if horizon < 1:
        raise ValueError("horizon must be at least 1")
    values = np.asarray(history, dtype=float).reshape(-1)
    if values.size == 0:
        raise ValueError("history is empty")
    if not np.isfinite(values).all():
        raise ValueError("history contains non-finite values")
    return values


def naive(history: np.ndarray, horizon: int) -> Forecast:
    """Repeat the last observation. The lowest bar there is, and it is not always beaten."""
    values = _validate(history, horizon)
    return np.repeat(values[-1], horizon)


def seasonal_naive(history: np.ndarray, horizon: int, season: int = 52) -> Forecast:
    """Repeat the observation from one season ago.

    Falls back to :func:`naive` when the history is shorter than a season, which is a real
    limitation rather than a convenience: a series with less than one full season of history
    cannot be evaluated against a seasonal baseline, and pretending otherwise flatters
    whatever is being compared to it.
    """
    values = _validate(history, horizon)
    if season < 1:
        raise ValueError("season must be at least 1")
    if values.size < season:
        return naive(values, horizon)
    pattern = values[-season:]
    return np.array([pattern[index % season] for index in range(horizon)])


def moving_average(history: np.ndarray, horizon: int, window: int = 8) -> Forecast:
    """Repeat the mean of the last ``window`` observations."""
    values = _validate(history, horizon)
    if window < 1:
        raise ValueError("window must be at least 1")
    return np.repeat(values[-min(window, values.size) :].mean(), horizon)


def drift(history: np.ndarray, horizon: int) -> Forecast:
    """Extrapolate the average change per period from first to last observation."""
    values = _validate(history, horizon)
    if values.size < 2:
        return naive(values, horizon)
    slope = (values[-1] - values[0]) / (values.size - 1)
    return values[-1] + slope * np.arange(1, horizon + 1)


def croston(history: np.ndarray, horizon: int, alpha: float = 0.1) -> Forecast:
    """Croston's method for intermittent demand.

    Separately smooths the size of a demand occurrence and the interval between occurrences,
    and forecasts size divided by interval. Both estimates update only in periods where demand
    occurred, which is the method's insight and also why it cannot notice that an item has gone
    quiet.

    It is **biased high**. See :func:`sba` for the correction, and the module docstring for why
    running both matters.
    """
    values = _validate(history, horizon)
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")

    occurrences = np.flatnonzero(values > 0)
    if occurrences.size == 0:
        return np.zeros(horizon)
    if occurrences.size == 1:
        return np.repeat(values[occurrences[0]] / values.size, horizon)

    size = values[occurrences[0]]
    interval = float(occurrences[0] + 1)
    for previous, current in zip(occurrences[:-1], occurrences[1:], strict=True):
        size += alpha * (values[current] - size)
        interval += alpha * ((current - previous) - interval)

    rate = size / interval if interval > 0 else 0.0
    return np.repeat(rate, horizon)


def sba(history: np.ndarray, horizon: int, alpha: float = 0.1) -> Forecast:
    """Syntetos-Boylan approximation: Croston with its bias removed.

    Multiplies Croston's rate by ``1 - alpha / 2``. The correction is small at the smoothing
    constants normally used, and it is in the direction that matters: Croston forecasts high,
    and a forecast that is high on a slow mover buys inventory nobody needs.
    """
    if not 0.0 < alpha <= 1.0:
        raise ValueError("alpha must be in (0, 1]")
    return croston(history, horizon, alpha=alpha) * (1.0 - alpha / 2.0)


def tsb(
    history: np.ndarray,
    horizon: int,
    alpha: float = 0.1,
    beta: float = 0.05,
) -> Forecast:
    """Teunter-Syntetos-Babai: demand probability updated every period.

    The difference from Croston is that the probability of a demand occurrence is smoothed in
    **every** period, including the empty ones, so a series that stops selling has its forecast
    decay towards zero. Croston's estimate of the interval only updates when demand arrives, so
    an item that has gone dead keeps whatever rate it had when it was alive. On an assortment
    with obsolescence that difference is the whole result.

    Args:
        history: Demand per period.
        horizon: Periods to forecast.
        alpha: Smoothing constant for the demand size.
        beta: Smoothing constant for the demand probability.
    """
    values = _validate(history, horizon)
    if not 0.0 < alpha <= 1.0 or not 0.0 < beta <= 1.0:
        raise ValueError("alpha and beta must be in (0, 1]")

    occurrences = values > 0
    if not occurrences.any():
        return np.zeros(horizon)

    probability = float(occurrences.mean())
    size = float(values[occurrences].mean())
    for index in range(values.size):
        if occurrences[index]:
            probability += beta * (1.0 - probability)
            size += alpha * (values[index] - size)
        else:
            probability += beta * (0.0 - probability)

    return np.repeat(probability * size, horizon)


#: The baselines a proposal is measured against. Seasonal naive is the reference.
BASELINES = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "moving_average": moving_average,
    "drift": drift,
}

#: Methods built for demand that arrives in sparse bursts.
INTERMITTENT = {
    "croston": croston,
    "sba": sba,
    "tsb": tsb,
}
