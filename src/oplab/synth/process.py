"""Process measurements for statistical process control."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SpecialCause:
    """A deliberate disturbance injected into a measurement series.

    Attributes:
        start: Index of the first affected subgroup.
        mean_shift_sigma: Shift of the process mean, expressed in process sigmas.
        sigma_multiplier: Multiplier applied to process dispersion from ``start`` onwards.
    """

    start: int
    mean_shift_sigma: float = 0.0
    sigma_multiplier: float = 1.0


def generate_subgroups(
    rng: np.random.Generator,
    n_subgroups: int = 60,
    subgroup_size: int = 5,
    target: float = 500.0,
    sigma: float = 2.0,
    causes: tuple[SpecialCause, ...] = (SpecialCause(start=42, mean_shift_sigma=1.6),),
    start: str = "2025-06-02",
) -> pd.DataFrame:
    """Generate subgrouped measurements with known special causes.

    The series is stable up to the first injected cause, which is what makes it useful as a
    test fixture: control limits computed on the stable phase should flag the disturbance, and
    limits computed on the whole series should be inflated enough to hide it. That contrast is
    the single most common mistake in applied control charting.

    Args:
        rng: Seeded generator.
        n_subgroups: Number of subgroups (rational subgroups, typically one per shift or hour).
        subgroup_size: Observations per subgroup.
        target: Process mean during the stable phase.
        sigma: Process standard deviation during the stable phase.
        causes: Disturbances to inject.
        start: Timestamp of the first subgroup; subgroups are spaced one hour apart.

    Returns:
        Long frame with columns ``subgroup``, ``timestamp``, ``unit`` and ``value``.
    """
    if subgroup_size < 1:
        raise ValueError("subgroup_size must be positive")
    if n_subgroups < 2:
        raise ValueError("n_subgroups must be at least 2")

    mean = np.full(n_subgroups, target, dtype=float)
    spread = np.full(n_subgroups, sigma, dtype=float)
    for cause in causes:
        if not 0 <= cause.start < n_subgroups:
            raise ValueError(f"special cause start {cause.start} is outside the series")
        mean[cause.start :] += cause.mean_shift_sigma * sigma
        spread[cause.start :] *= cause.sigma_multiplier

    values = rng.normal(
        loc=np.repeat(mean, subgroup_size),
        scale=np.repeat(spread, subgroup_size),
    )

    timestamps = pd.date_range(start, periods=n_subgroups, freq="h")
    return pd.DataFrame(
        {
            "subgroup": np.repeat(np.arange(1, n_subgroups + 1), subgroup_size),
            "timestamp": np.repeat(timestamps.to_numpy(), subgroup_size),
            "unit": np.tile(np.arange(1, subgroup_size + 1), n_subgroups),
            "value": np.round(values, 3),
        }
    )
