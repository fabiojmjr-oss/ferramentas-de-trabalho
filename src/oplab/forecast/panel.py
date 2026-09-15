"""Turning a transactional demand table into dense time series.

The densification is the whole preparation step and it is where forecasting work goes wrong
before any model is fitted. A demand extract contains the periods where something was sold;
the periods where nothing was sold are absent, not zero. Fit a model to the rows you were
given and you have fitted it to the selling weeks of a slow mover, which is a different and
much easier series than the one the operation actually faces.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd


def to_panel(
    demand: pd.DataFrame,
    freq: str = "W",
    key: Sequence[str] = ("site", "sku"),
    date_col: str = "date",
    value_col: str = "demand",
) -> pd.DataFrame:
    """Aggregate to a period grid and fill the missing periods with zero.

    Args:
        demand: Long demand frame holding only the periods where demand occurred.
        freq: Pandas period alias to aggregate on, for example ``"W"`` or ``"ME"``.
        key: Columns identifying a series.
        date_col: Date column.
        value_col: Quantity column.

    Returns:
        Wide frame indexed by period, one column per series. Series names are the key values
        joined by ``" | "``. Every period between the first and last observation in the whole
        frame is present for every series, with zeros where nothing was demanded.

    Raises:
        KeyError: If a named column is missing.
        ValueError: If ``demand`` is empty.
    """
    for column in [*key, date_col, value_col]:
        if column not in demand.columns:
            raise KeyError(f"demand has no column {column!r}")
    if demand.empty:
        raise ValueError("demand is empty")

    frame = demand[[*key, date_col, value_col]].copy()
    frame["period"] = pd.to_datetime(frame[date_col]).dt.to_period(freq)
    frame["series"] = frame[list(key)].astype(str).agg(" | ".join, axis=1)

    wide = frame.groupby(["period", "series"], observed=True)[value_col].sum().unstack("series")
    grid = pd.period_range(wide.index.min(), wide.index.max(), freq=freq)
    return wide.reindex(grid).fillna(0.0).astype(float)


def aggregate_panel(panel: pd.DataFrame, level: str | None = None) -> pd.DataFrame:
    """Sum a panel up a level, to measure how much easier the aggregate is to forecast.

    Args:
        panel: Wide panel from :func:`to_panel`, whose column names are key values joined by
            ``" | "``.
        level: Which part of the composite key to keep. ``None`` collapses everything into a
            single ``"total"`` series; ``"0"`` keeps the first key component, ``"1"`` the
            second, and so on.

    Returns:
        A wide panel with fewer columns.

    Raises:
        ValueError: If ``level`` does not index a component of the key.
    """
    if level is None:
        return pd.DataFrame({"total": panel.sum(axis=1)})

    try:
        position = int(level)
    except ValueError as error:  # pragma: no cover - defensive
        raise ValueError("level must be None or a key position such as '0'") from error

    parts = [name.split(" | ") for name in panel.columns]
    if any(position >= len(part) for part in parts):
        raise ValueError(f"key position {position} is out of range for these series names")

    groups = [part[position] for part in parts]
    return panel.T.groupby(groups).sum().T
