"""Measuring a forecast honestly.

This is not a forecasting library. It is the harness a forecasting proposal has to survive, with
reference implementations of the baselines it has to beat - because the most common defect in a
forecasting project is not a weak model, it is the absence of anything to compare the model
against.

Use it in this order:

1. :func:`to_panel` to densify the demand extract. The periods with no demand are absent from a
   transactional table, not zero, and fitting to the rows you were given fits a different and
   easier series.
2. :func:`season_feasibility` before running anything. A seasonal baseline needs a full season
   inside the training window and a scaled metric needs more than one; weekly data over a single
   year satisfies neither, and what happens then is not an error but a silent fallback to a
   non-seasonal baseline with every scaled metric returning ``nan``.
3. :func:`mape_coverage` before choosing a metric. On sparse demand MAPE is undefined on most
   period-observations, and the number settles the argument faster than the theory.
4. :func:`backtest_panel` and :func:`summarise` for a rolling-origin comparison against
   ``seasonal_naive``, reporting both the pooled error and the share of series actually beaten.
5. :func:`aggregation_effect` to see how much of a headline accuracy figure is aggregation.
6. :func:`error_profile` when the forecast is going to drive replenishment. A point forecast
   cannot size a buffer; the distribution of its error over the lead time can, and that
   distribution is already implied by the backtest. The ratio it reports against demand
   variability answers a question that is usually skipped: whether forecasting reduces the
   inventory requirement or enlarges it.
"""

from .backtest import (
    SeasonFeasibility,
    aggregation_effect,
    backtest_panel,
    rolling_origin,
    season_feasibility,
    summarise,
)
from .baselines import (
    BASELINES,
    INTERMITTENT,
    croston,
    drift,
    moving_average,
    naive,
    sba,
    seasonal_naive,
    tsb,
)
from .intervals import (
    ErrorProfile,
    error_profile,
    horizon_profile,
    interval_coverage,
    prediction_interval,
    residuals,
)
from .metrics import (
    MapeCoverage,
    bias,
    mae,
    mape,
    mape_coverage,
    mase,
    naive_scale,
    rmse,
    rmsse,
)
from .panel import aggregate_panel, to_panel

__all__ = [
    "BASELINES",
    "INTERMITTENT",
    "ErrorProfile",
    "MapeCoverage",
    "SeasonFeasibility",
    "aggregate_panel",
    "aggregation_effect",
    "backtest_panel",
    "bias",
    "croston",
    "error_profile",
    "drift",
    "horizon_profile",
    "interval_coverage",
    "mae",
    "mape",
    "mape_coverage",
    "mase",
    "moving_average",
    "naive",
    "naive_scale",
    "prediction_interval",
    "residuals",
    "rmse",
    "rmsse",
    "rolling_origin",
    "season_feasibility",
    "sba",
    "seasonal_naive",
    "summarise",
    "to_panel",
    "tsb",
]
