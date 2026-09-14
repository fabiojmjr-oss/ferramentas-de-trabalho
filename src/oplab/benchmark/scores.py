"""Composite scores, and how much of a ranking is the weighting.

A scorecard that combines several indicators into one number has to weight them, and the
weights are almost never derived from anything. They are agreed in a meeting, and then the
ranking they produce is discussed as though it were a measurement.

:func:`rank_stability` measures that directly. It re-ranks the units under thousands of random
weightings and reports how often each one finishes where it finished. A unit that is first
under 12% of plausible weightings is not first - it is first under the weighting somebody
chose, and that is a different statement with a different owner.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import pandas as pd


def peer_z_scores(
    frame: pd.DataFrame,
    metrics: Sequence[str],
    higher_is_better: Mapping[str, bool],
    unit: str,
    group: str | None = None,
) -> pd.DataFrame:
    """Standardise each metric within its peer group, signed so that higher is always better.

    Args:
        frame: One row per unit.
        metrics: Metric columns.
        higher_is_better: Direction per metric. A cost and a service level cannot be averaged
            until they point the same way, and getting one sign wrong inverts the ranking
            silently.
        unit: Column identifying the unit.
        group: Optional peer-group column. Standardising across groups that are not comparable
            reintroduces exactly the bias normalisation was meant to remove.

    Returns:
        One row per unit with a ``z_{metric}`` column per metric.

    Raises:
        KeyError: If a column is missing or a metric has no declared direction.
    """
    for column in [*metrics, unit, *([group] if group else [])]:
        if column not in frame.columns:
            raise KeyError(f"frame has no column {column!r}")
    missing = [metric for metric in metrics if metric not in higher_is_better]
    if missing:
        raise KeyError(f"no direction declared for {missing}")

    out = frame[[unit, *([group] if group else []), *metrics]].copy()
    keys = [group] if group else None

    for metric in metrics:
        values = out[metric]
        if keys:
            centre = out.groupby(keys, observed=True)[metric].transform("mean").to_numpy()
            spread = out.groupby(keys, observed=True)[metric].transform("std").to_numpy()
        else:
            centre = np.full(len(out), values.mean())
            spread = np.full(len(out), values.std(ddof=1))
        z = (values.to_numpy(dtype=float) - centre) / spread
        out[f"z_{metric}"] = z if higher_is_better[metric] else -z
    return out


def composite_index(
    scores: pd.DataFrame,
    metrics: Sequence[str],
    weights: Mapping[str, float] | None = None,
    unit: str = "site",
) -> pd.DataFrame:
    """Combine standardised metrics into one score under an explicit weighting.

    Args:
        scores: Output of :func:`peer_z_scores`.
        metrics: Metrics to combine.
        weights: Weight per metric. Defaults to equal weights, which is a choice like any
            other and not a neutral one.
        unit: Column identifying the unit.

    Returns:
        One row per unit with ``composite`` and ``rank``, best first.

    Raises:
        KeyError: If a standardised column is missing.
        ValueError: If the weights do not sum to a positive value.
    """
    columns = [f"z_{metric}" for metric in metrics]
    missing = [column for column in columns if column not in scores.columns]
    if missing:
        raise KeyError(f"scores is missing {missing}; run peer_z_scores first")

    if weights is None:
        weights = dict.fromkeys(metrics, 1.0 / len(metrics))
    total = sum(weights[metric] for metric in metrics)
    if total <= 0:
        raise ValueError("weights must sum to a positive value")

    weighted = sum(scores[f"z_{metric}"] * (weights[metric] / total) for metric in metrics)
    out = scores[[unit]].copy()
    out["composite"] = weighted
    out["rank"] = out["composite"].rank(ascending=False).astype(int)
    return out.sort_values("rank", ignore_index=True)


def rank_stability(
    scores: pd.DataFrame,
    metrics: Sequence[str],
    unit: str = "site",
    draws: int = 2000,
    concentration: float = 1.0,
    seed: int = 42,
) -> pd.DataFrame:
    """Re-rank the units under many random weightings and report the spread.

    Weights are drawn from a Dirichlet distribution, so every draw is a valid weighting that
    sums to one. ``concentration`` sets how far they roam: at 1.0 the draws cover the whole
    simplex uniformly, which is the right question when nobody can defend a particular
    weighting; raise it to concentrate the draws near equal weights when the weighting is
    genuinely agreed and only its precision is in doubt.

    Args:
        scores: Output of :func:`peer_z_scores`.
        metrics: Metrics being combined.
        unit: Column identifying the unit.
        draws: Number of weightings to sample.
        concentration: Dirichlet concentration parameter.
        seed: Sampling seed.

    Returns:
        One row per unit with ``mean_rank``, ``best_rank``, ``worst_rank``, ``share_first`` and
        ``share_last``. A unit whose best and worst ranks differ has a position that the
        weighting decides, not the data.

    Raises:
        ValueError: If ``draws`` or ``concentration`` is not positive.
    """
    if draws < 1:
        raise ValueError("draws must be positive")
    if concentration <= 0:
        raise ValueError("concentration must be positive")

    columns = [f"z_{metric}" for metric in metrics]
    missing = [column for column in columns if column not in scores.columns]
    if missing:
        raise KeyError(f"scores is missing {missing}; run peer_z_scores first")

    matrix = scores[columns].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    weights = rng.dirichlet(np.full(len(metrics), concentration), size=draws)

    composites = matrix @ weights.T  # units x draws
    # Rank 1 is the best, so rank descending composite values.
    order = np.argsort(np.argsort(-composites, axis=0), axis=0) + 1

    n_units = matrix.shape[0]
    return pd.DataFrame(
        {
            unit: scores[unit].to_numpy(),
            "mean_rank": order.mean(axis=1),
            "best_rank": order.min(axis=1),
            "worst_rank": order.max(axis=1),
            "share_first": (order == 1).mean(axis=1),
            "share_last": (order == n_units).mean(axis=1),
        }
    ).sort_values("mean_rank", ignore_index=True)
