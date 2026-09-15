"""The forecast error distribution, which is what replenishment actually consumes.

A point forecast cannot size a buffer. What sizes a buffer is the distribution of the error
around that forecast over the replenishment lead time — and that distribution is already implied
by a rolling-origin backtest, one residual per series, per origin, per horizon step. This module
reads it out rather than assuming it.

Three things it refuses to assume, each of which is normally assumed:

1. **That the interval is normal.** On intermittent demand the error distribution is skewed and
   discrete, and a normal interval centred on the forecast puts its lower bound below zero and
   its upper bound too close in. :func:`prediction_interval` uses empirical quantiles of the
   observed residuals, and :func:`interval_coverage` then measures whether the nominal coverage
   was achieved — because a 95% interval that covers 78% of outcomes is worse than no interval,
   which at least does not get planned against.

2. **That error grows with the square root of the horizon.** That holds for a random walk and is
   quoted for everything. :func:`horizon_profile` measures the growth instead, which matters
   because the lead time decides which horizon's error the buffer has to cover.

3. **That the error is centred.** Bias is a separate parameter from spread, it survives
   aggregation where spread does not, and a buffer sized on spread alone will not correct it.
   Every function here reports both.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .._pandas import as_int

RESIDUAL_COLUMNS = ("series", "model", "origin", "step", "actual", "forecast")


@dataclass(frozen=True)
class ErrorProfile:
    """The forecast error distribution of one series under one model.

    Attributes:
        series: Series name.
        model: Model name.
        observations: Residuals observed.
        bias: Mean error, defined as forecast minus actual, so a positive value is over-forecast.
        sd: Standard deviation of the error.
        mae: Mean absolute error.
        demand_sd: Standard deviation of the actuals themselves, which is the error a forecast of
            the long-run mean would have made. It is the benchmark that decides whether
            forecasting reduces the buffer or enlarges it.
    """

    series: str
    model: str
    observations: int
    bias: float
    sd: float
    mae: float
    demand_sd: float

    @property
    def sd_ratio(self) -> float:
        """Forecast error spread over demand spread.

        Below one, the forecast is worth buffering against: it tracks the series more closely
        than its own mean does, so a policy sized on forecast error holds less stock than one
        sized on demand variability. Above one, the forecast is *adding* uncertainty to the
        replenishment decision, and sizing the buffer on demand variability is not conservative -
        it is wrong in the expensive direction.
        """
        return self.sd / self.demand_sd if self.demand_sd > 0 else float("nan")

    @property
    def reduces_buffer(self) -> bool:
        """Whether buffering against this forecast costs less than buffering against the mean."""
        return bool(self.sd_ratio < 1.0)


def residuals(results: pd.DataFrame, model: str | None = None) -> pd.DataFrame:
    """Extract forecast errors from a backtest.

    Args:
        results: Output of :func:`~oplab.forecast.backtest_panel` or
            :func:`~oplab.forecast.rolling_origin`.
        model: Keep only this model. ``None`` keeps all of them.

    Returns:
        The input rows plus an ``error`` column, defined as ``forecast - actual`` so that a
        positive error is an over-forecast. That sign convention is chosen to match
        :func:`~oplab.forecast.bias` and stated here because the opposite convention is equally
        common and silently inverts every conclusion about direction.

    Raises:
        KeyError: If a required column is missing, or ``model`` is not in the results.
    """
    required = ("model", "step", "actual", "forecast")
    missing = [column for column in required if column not in results.columns]
    if missing:
        raise KeyError(f"results is missing columns: {', '.join(missing)}")

    frame = results.copy()
    if model is not None:
        if model not in set(frame["model"]):
            raise KeyError(f"no model named {model!r} in results")
        frame = frame.loc[frame["model"] == model]

    frame["error"] = frame["forecast"] - frame["actual"]
    return frame.reset_index(drop=True)


def error_profile(results: pd.DataFrame, model: str) -> pd.DataFrame:
    """Summarise the error distribution per series, against the demand it has to buffer.

    Args:
        results: Output of :func:`~oplab.forecast.backtest_panel`.
        model: The model whose errors are to be profiled.

    Returns:
        One row per series with ``observations``, ``bias``, ``sd``, ``mae``, ``demand_sd``,
        ``sd_ratio`` and ``reduces_buffer``. A series with no variation in its actuals has no
        ``demand_sd`` to divide by and its ratio is ``nan`` rather than infinite, so it can be
        counted rather than silently dominating a mean.

    Raises:
        KeyError: If ``series`` is absent from ``results`` - a single-series backtest has to be
            given a series name before it can be profiled per series.
    """
    if "series" not in results.columns:
        raise KeyError(
            "results has no 'series' column; profile per series needs backtest_panel output"
        )

    frame = residuals(results, model=model)
    rows = []
    for name, group in frame.groupby("series", observed=True):
        errors = group["error"].to_numpy(dtype=float)
        actuals = group["actual"].to_numpy(dtype=float)
        demand_sd = float(actuals.std(ddof=1)) if actuals.size > 1 else 0.0
        sd = float(errors.std(ddof=1)) if errors.size > 1 else 0.0
        profile = ErrorProfile(
            series=str(name),
            model=model,
            observations=int(errors.size),
            bias=float(errors.mean()),
            sd=sd,
            mae=float(np.abs(errors).mean()),
            demand_sd=demand_sd,
        )
        rows.append(
            {
                "series": profile.series,
                "observations": profile.observations,
                "bias": profile.bias,
                "sd": profile.sd,
                "mae": profile.mae,
                "demand_sd": profile.demand_sd,
                "sd_ratio": profile.sd_ratio,
                "reduces_buffer": profile.reduces_buffer,
            }
        )
    return pd.DataFrame(rows).sort_values("sd_ratio", ignore_index=True)


def horizon_profile(
    results: pd.DataFrame,
    model: str,
    step_between_origins: int | None = None,
    season: int | None = None,
) -> pd.DataFrame:
    """Measure how the error varies with the forecast horizon, and whether that reading is safe.

    Two traps sit in front of this table, and both produce a plausible chart.

    **The square-root rule does not apply to a per-period error.** ``sqrt(h)`` describes the error
    of a *cumulative* total over ``h`` periods, or of a random walk. The per-period error of a flat
    forecast on a stationary series does not grow at all. Inventory needs the cumulative quantity,
    which is why :func:`~oplab.inventory.safety_stock_from_forecast_error` multiplies the error
    *variance* by the protection interval rather than reading a growth rate off this table.

    **When the origins are spaced a whole number of seasons apart, each horizon step is locked to
    one phase of the season.** Step 4 then always falls on the same weekday, and a flat forecast
    carries that weekday's deviation as a constant error - so the column reads as a horizon effect
    and is a seasonal one. Pass ``step_between_origins`` and ``season`` and the returned frame
    carries a ``phase_locked`` flag saying whether that is the case, rather than leaving the reader
    to notice.

    Args:
        results: Output of :func:`~oplab.forecast.backtest_panel`.
        model: The model whose errors are to be profiled.
        step_between_origins: The ``step`` the backtest used. Optional; needed for the flag.
        season: The seasonal period. Optional; needed for the flag.

    Returns:
        One row per horizon step with the pooled ``bias``, ``sd`` and ``mae``, the ``sd`` relative
        to step one, ``sqrt_step`` for comparison, and ``phase_locked`` - true when every step is
        pinned to one phase of the season and the profile therefore cannot be read as a horizon
        effect. ``phase_locked`` is ``None`` when the two arguments were not supplied.
    """
    frame = residuals(results, model=model)
    table = (
        frame.groupby("step", observed=True)
        .agg(
            observations=("error", "size"),
            bias=("error", "mean"),
            sd=("error", "std"),
            mae=("error", lambda s: float(np.abs(s).mean())),
        )
        .reset_index()
        .sort_values("step", ignore_index=True)
    )
    first = float(table["sd"].iloc[0]) if not table.empty else float("nan")
    table["sd_vs_step_1"] = table["sd"] / first if first > 0 else float("nan")
    table["sqrt_step"] = np.sqrt(table["step"].to_numpy(dtype=float))

    if step_between_origins is None or season is None:
        table["phase_locked"] = None
    else:
        if min(step_between_origins, season) < 1:
            raise ValueError("step_between_origins and season must both be positive")
        table["phase_locked"] = step_between_origins % season == 0
    return table


def prediction_interval(results: pd.DataFrame, model: str, coverage: float = 0.95) -> pd.DataFrame:
    """Empirical prediction interval per horizon step, from the observed residuals.

    The interval is built from quantiles of the residuals rather than from a normal fitted to
    their first two moments, because the shape is the point: an intermittent series produces a
    right-skewed error distribution whose normal approximation is symmetric about a forecast it
    is not symmetric about.

    Args:
        results: Output of :func:`~oplab.forecast.backtest_panel`.
        model: The model whose errors define the interval.
        coverage: Nominal coverage, strictly between 0 and 1.

    Returns:
        One row per horizon step with the ``lower`` and ``upper`` offsets to add to a forecast,
        and the equivalent ``normal_lower`` and ``normal_upper`` from a fitted normal, so the
        difference between the two is visible rather than argued about.

    Raises:
        ValueError: If ``coverage`` is not strictly between 0 and 1.
    """
    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be strictly between 0 and 1")

    from ..inventory.normal import norm_ppf

    tail = (1.0 - coverage) / 2.0
    z = norm_ppf(1.0 - tail)
    frame = residuals(results, model=model)

    rows = []
    for step, group in frame.groupby("step", observed=True):
        errors = group["error"].to_numpy(dtype=float)
        mean, sd = float(errors.mean()), float(errors.std(ddof=1)) if errors.size > 1 else 0.0
        # The interval is on the actual, so the residual quantiles enter with their sign flipped:
        # a large positive error means the forecast was above the actual.
        rows.append(
            {
                "step": as_int(step),
                "observations": int(errors.size),
                "lower": -float(np.quantile(errors, 1.0 - tail)),
                "upper": -float(np.quantile(errors, tail)),
                "normal_lower": -(mean + z * sd),
                "normal_upper": -(mean - z * sd),
            }
        )
    return pd.DataFrame(rows).sort_values("step", ignore_index=True)


def interval_coverage(results: pd.DataFrame, model: str, coverage: float = 0.95) -> pd.DataFrame:
    """Measure the coverage a nominal interval actually achieves, per horizon step.

    An interval fitted to the same residuals it is then scored on is optimistic by construction,
    so the empirical row here is close to its nominal level almost by definition. The row that
    carries information is the normal one: it is fitted to two moments of the same residuals and
    still misses, and by how much is a statement about the shape of the distribution rather than
    about the sample.

    Args:
        results: Output of :func:`~oplab.forecast.backtest_panel`.
        model: The model whose errors define the interval.
        coverage: Nominal coverage.

    Returns:
        One row per horizon step with ``nominal``, ``empirical_coverage``, ``normal_coverage`` and
        the share of outcomes falling below and above the normal interval - because a symmetric
        interval on a skewed distribution misses asymmetrically, and which side it misses on
        decides whether the error is a stockout or dead stock.
    """
    intervals = prediction_interval(results, model, coverage).set_index("step")
    frame = residuals(results, model=model)

    rows = []
    for step, group in frame.groupby("step", observed=True):
        bounds = intervals.loc[as_int(step)]
        actual = group["actual"].to_numpy(dtype=float)
        forecast = group["forecast"].to_numpy(dtype=float)
        empirical = (actual >= forecast + bounds["lower"]) & (actual <= forecast + bounds["upper"])
        below = actual < forecast + bounds["normal_lower"]
        above = actual > forecast + bounds["normal_upper"]
        rows.append(
            {
                "step": as_int(step),
                "observations": int(actual.size),
                "nominal": coverage,
                "empirical_coverage": float(empirical.mean()),
                "normal_coverage": float(1.0 - (below | above).mean()),
                "normal_below": float(below.mean()),
                "normal_above": float(above.mean()),
            }
        )
    return pd.DataFrame(rows).sort_values("step", ignore_index=True)
