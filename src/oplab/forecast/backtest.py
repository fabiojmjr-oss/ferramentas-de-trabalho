"""Rolling-origin evaluation, and the two ways a summary hides what happened.

A forecast is evaluated by pretending to stand at a past date, forecasting forward, and
comparing against what came next - repeated at several origins. Anything less is a single
sample, and a single sample of forecast accuracy is worth about as much as a single run of a
stochastic simulation.

Two reporting habits are enforced here because both failures are common and both flatter the
proposal:

**A pooled average hides who won.** A model can have a better mean error than the baseline while
being worse on most series, because the mean is dominated by a handful of large-volume wins.
:func:`summarise` therefore reports the share of series the model actually beats alongside the
pooled figure, and those two numbers routinely disagree.

**Accuracy hides direction.** Bias is reported next to every error figure, because a method can
be accurate and systematically high - which is the Croston case, and which buys inventory nobody
asked for.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .._pandas import as_float
from .metrics import bias as bias_metric
from .metrics import mae, mase, rmsse

Model = Callable[..., np.ndarray]

DEFAULT_SEASON = 52


@dataclass(frozen=True)
class SeasonFeasibility:
    """Whether a seasonal baseline can be evaluated on this history at all.

    Attributes:
        periods: Length of the series.
        season: Seasonal lag requested.
        min_train: Training length before the first origin.
        horizon: Periods forecast from each origin.
        origins: Number of origins the backtest will actually use.
        scale_available: Whether the training window is longer than one season, which is what a
            scaled metric needs.
        seasonal_baseline_available: Whether the training window holds a full season, which is
            what a seasonal baseline needs.
        message: One line to print above the results.
    """

    periods: int
    season: int
    min_train: int
    horizon: int
    origins: int
    scale_available: bool
    seasonal_baseline_available: bool
    message: str

    @property
    def usable(self) -> bool:
        return self.origins > 0 and self.scale_available and self.seasonal_baseline_available


def season_feasibility(
    periods: int,
    season: int = DEFAULT_SEASON,
    min_train: int = 52,
    horizon: int = 4,
    step: int = 4,
) -> SeasonFeasibility:
    """Check the history against the season before running anything.

    This exists because of a failure that is easy to miss and fatal when missed. A seasonal
    baseline needs a full season inside the training window; a scaled metric needs **more** than
    a season, since it differences the training series at the seasonal lag. Weekly data over one
    year satisfies neither: there are 52 or 53 periods, so every week of the year is observed
    exactly once, and there is no repetition either to learn from or to validate against.

    What happens without the check is worse than an error. :func:`~oplab.forecast.seasonal_naive`
    falls back to a non-seasonal forecast, so the run completes and reports a "seasonal baseline"
    that is nothing of the kind, while every scaled metric comes back as ``nan``. Annual
    seasonality on weekly data needs at least two years. Weekly seasonality on **daily** data
    needs a fortnight, which is why a daily grid with ``season=7`` is usually the tractable
    question on one year of history.

    Args:
        periods: Length of the series.
        season: Seasonal lag.
        min_train: Training length before the first origin.
        horizon: Periods forecast from each origin.
        step: Periods between origins.

    Returns:
        A :class:`SeasonFeasibility`.

    Raises:
        ValueError: If any argument is not positive.
    """
    if min(periods, season, min_train, horizon, step) < 1:
        raise ValueError("every argument must be positive")

    origins = (
        max(0, (periods - horizon - min_train) // step + 1) if periods >= min_train + horizon else 0
    )
    scale_available = min_train > season
    baseline_available = min_train >= season

    problems = []
    if origins == 0:
        problems.append(
            f"no origin fits: {periods} periods cannot hold {min_train} of training plus "
            f"{horizon} of horizon"
        )
    if not baseline_available:
        problems.append(
            f"the training window of {min_train} is shorter than the season of {season}, so a "
            "seasonal baseline will silently fall back to a non-seasonal one"
        )
    elif not scale_available:
        problems.append(
            f"the training window of {min_train} does not exceed the season of {season}, so "
            "every scaled metric will be nan"
        )

    if problems:
        message = "Not usable as specified: " + "; ".join(problems) + "."
    else:
        message = (
            f"{origins} origins on {periods} periods, training on {min_train} with a season of "
            f"{season}: the seasonal baseline and the scaled metrics are both available."
        )

    return SeasonFeasibility(
        periods=periods,
        season=season,
        min_train=min_train,
        horizon=horizon,
        origins=origins,
        scale_available=scale_available,
        seasonal_baseline_available=baseline_available,
        message=message,
    )


def rolling_origin(
    series: pd.Series,
    models: Mapping[str, Model],
    horizon: int = 4,
    step: int = 4,
    min_train: int = 52,
    season: int = DEFAULT_SEASON,
) -> pd.DataFrame:
    """Evaluate models on one series at several origins.

    Args:
        series: One demand series, indexed by period, with no gaps.
        models: Named forecasting functions taking ``(history, horizon)``.
        horizon: Periods forecast from each origin.
        step: Periods between origins.
        min_train: Minimum training length before the first origin. Set it to at least one
            season, or a seasonal baseline has nothing to be seasonal about.
        season: Seasonal lag used by the scaled metrics and by the seasonal baseline.

    Returns:
        One row per model, origin and horizon step, with ``actual`` and ``forecast``. Empty when
        the series is too short for even one origin, which is information rather than an error.

    Raises:
        ValueError: If any parameter is non-positive, or ``models`` is empty.
    """
    if min(horizon, step, min_train, season) < 1:
        raise ValueError("horizon, step, min_train and season must all be positive")
    if not models:
        raise ValueError("at least one model is required")

    values = np.asarray(series, dtype=float).reshape(-1)
    periods = list(series.index)
    rows: list[dict[str, object]] = []

    origin = min_train
    while origin + horizon <= values.size:
        history = values[:origin]
        actual = values[origin : origin + horizon]
        for name, model in models.items():
            forecast = _predict(model, history, horizon, season)
            for offset in range(horizon):
                rows.append(
                    {
                        "model": name,
                        "origin": periods[origin - 1],
                        "step": offset + 1,
                        "actual": float(actual[offset]),
                        "forecast": float(forecast[offset]),
                    }
                )
        origin += step

    return pd.DataFrame(rows, columns=["model", "origin", "step", "actual", "forecast"])


def _predict(model: Model, history: np.ndarray, horizon: int, season: int) -> np.ndarray:
    """Call a model, passing the season only to the models that take one."""
    try:
        return np.asarray(model(history, horizon, season=season), dtype=float)
    except TypeError:
        return np.asarray(model(history, horizon), dtype=float)


def backtest_panel(
    panel: pd.DataFrame,
    models: Mapping[str, Model],
    horizon: int = 4,
    step: int = 4,
    min_train: int = 52,
    season: int = DEFAULT_SEASON,
) -> pd.DataFrame:
    """Run :func:`rolling_origin` across every series in a panel.

    Returns:
        One row per series, model, origin and horizon step, with the training window's naive
        scale attached so that scaled metrics can be computed per series rather than pooled
        across series of different magnitude.
    """
    frames: list[pd.DataFrame] = []
    for name in panel.columns:
        series = panel[name]
        result = rolling_origin(
            series, models, horizon=horizon, step=step, min_train=min_train, season=season
        )
        if result.empty:
            continue
        result.insert(0, "series", name)
        frames.append(result)

    if not frames:
        return pd.DataFrame(columns=["series", "model", "origin", "step", "actual", "forecast"])
    return pd.concat(frames, ignore_index=True)


def summarise(
    results: pd.DataFrame,
    panel: pd.DataFrame,
    reference: str = "seasonal_naive",
    season: int = DEFAULT_SEASON,
    min_train: int = 52,
) -> pd.DataFrame:
    """Score every model against a reference baseline, pooled and per series.

    Args:
        results: Output of :func:`backtest_panel`.
        panel: The panel the backtest ran on, used to compute each series' naive scale from its
            training window.
        reference: Model every other model is measured against.
        season: Seasonal lag for the scaled metrics.
        min_train: Training length used in the backtest, so the scale is computed on the same
            window the models saw.

    Returns:
        One row per model with ``mase``, ``rmsse``, ``bias``, ``relative_mase`` against the
        reference, and ``beats_reference_share`` - the share of series on which the model has a
        lower absolute error than the reference. Read the last two together: they disagree
        whenever a pooled average is being carried by a few large series.

    Raises:
        KeyError: If ``reference`` is not among the models.
        ValueError: If ``results`` is empty.
    """
    if results.empty:
        raise ValueError("results is empty; nothing was backtested")
    if reference not in set(results["model"]):
        raise KeyError(f"reference {reference!r} is not among {sorted(set(results['model']))}")

    per_series = _per_series_errors(results, panel, season=season, min_train=min_train)
    reference_error = per_series.loc[per_series["model"] == reference].set_index("series")["mae"]

    rows = []
    for name, group in per_series.groupby("model", observed=True):
        indexed = group.set_index("series")
        comparable = reference_error.reindex(indexed.index)
        wins = (indexed["mae"] < comparable).sum()
        counted = comparable.notna().sum()
        rows.append(
            {
                "model": name,
                "mase": float(indexed["mase"].mean(skipna=True)),
                "rmsse": float(indexed["rmsse"].mean(skipna=True)),
                "bias": float(indexed["bias"].mean(skipna=True)),
                "series_scored": int(len(indexed)),
                "series_without_scale": int(indexed["mase"].isna().sum()),
                "beats_reference_share": float(wins / counted) if counted else float("nan"),
            }
        )

    table = pd.DataFrame(rows).set_index("model")
    reference_mase = as_float(table.loc[reference, "mase"])
    table["relative_mase"] = table["mase"] / reference_mase
    table.loc[reference, "beats_reference_share"] = float("nan")
    return table.sort_values("mase").reset_index()


def _per_series_errors(
    results: pd.DataFrame, panel: pd.DataFrame, season: int, min_train: int
) -> pd.DataFrame:
    """Error metrics for each series and model, scaled on that series' training window."""
    rows = []
    for (series, model), group in results.groupby(["series", "model"], observed=True):
        insample = np.asarray(panel[series], dtype=float)[:min_train]
        actual = group["actual"].to_numpy()
        forecast = group["forecast"].to_numpy()
        rows.append(
            {
                "series": series,
                "model": model,
                "mae": mae(actual, forecast),
                "mase": mase(actual, forecast, insample, season=season),
                "rmsse": rmsse(actual, forecast, insample, season=season),
                "bias": bias_metric(actual, forecast),
            }
        )
    return pd.DataFrame(rows)


def aggregation_effect(
    panels: Mapping[str, pd.DataFrame],
    models: Mapping[str, Model],
    horizon: int = 4,
    step: int = 4,
    min_train: int = 52,
    season: int = DEFAULT_SEASON,
    reference: str = "seasonal_naive",
) -> pd.DataFrame:
    """Score the same models at several levels of aggregation.

    Forecasting a total is a different and much easier problem than forecasting its parts,
    because the errors on the parts partly cancel. A headline forecast accuracy figure is
    therefore almost always an accuracy figure for an aggregate, and it says very little about
    whether the replenishment of any individual item can be trusted.

    Args:
        panels: Named panels, for example ``{"sku": fine, "site": coarse, "total": one}``.
        models: Named forecasting functions.
        horizon: Periods forecast from each origin.
        step: Periods between origins.
        min_train: Minimum training length.
        season: Seasonal lag.
        reference: Model to measure the others against at each level.

    Returns:
        One row per level and model, with the scored metrics and the series count.
    """
    frames = []
    for level, panel in panels.items():
        results = backtest_panel(
            panel, models, horizon=horizon, step=step, min_train=min_train, season=season
        )
        if results.empty:
            continue
        summary = summarise(results, panel, reference=reference, season=season, min_train=min_train)
        summary.insert(0, "level", level)
        summary.insert(1, "series", panel.shape[1])
        frames.append(summary)

    if not frames:
        return pd.DataFrame(columns=["level", "series", "model", "mase", "rmsse", "bias"])
    return pd.concat(frames, ignore_index=True)
