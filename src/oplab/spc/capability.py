"""Process capability and performance indices.

Two pairs of indices answer two different questions, and reporting one while the audience
assumes the other is the standard way a capability study misleads:

``Cp`` / ``Cpk``
    **Capability** - what the process could deliver if it stayed as consistent as it is within
    a subgroup. Computed from short-term (within-subgroup) variation.
``Pp`` / ``Ppk``
    **Performance** - what the process actually delivered over the period, including drift,
    setup changes and shift effects. Computed from the overall standard deviation.

``Cp`` ignores centring and ``Cpk`` does not, so a process can be capable and still produce
defects. A large gap between ``Cpk`` and ``Ppk`` is the most useful number in the study: it
means the process is capable in the short run but is not held there, which is a control
problem, not a variation-reduction problem. The interventions are different and so is the
owner.

Three conditions must hold before any of these numbers mean anything:

1. **The process is in statistical control.** An index computed on an unstable process
   describes a state the process does not have. Chart first - :mod:`oplab.spc.charts`.
2. **The measurement system is adequate.** If gauge variation is a large share of total
   variation, the study is measuring the gauge.
3. **The distribution is approximately normal.** The expected-defect figures here come from the
   normal distribution. Cycle times, waiting times and most logistics durations are right
   skewed, and applying a normal capability model to them understates defects, sometimes by an
   order of magnitude. :func:`capability` reports skewness and kurtosis so the assumption is
   visible instead of implied.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import NormalDist

import numpy as np
import pandas as pd

from .constants import MAX_SUBGROUP, MIN_SUBGROUP, d2

_NORMAL = NormalDist()


@dataclass(frozen=True)
class Capability:
    """Result of a capability study.

    Attributes:
        n: Observations used.
        mean: Process mean.
        sigma_within: Short-term standard deviation, from within-subgroup variation.
        sigma_overall: Standard deviation of all observations, ``ddof=1``.
        lsl: Lower specification limit, if any.
        usl: Upper specification limit, if any.
        target: Target value, if any. Defaults to the midpoint of a two-sided specification.
        cp: Capability index, two-sided specification only.
        cpk: Capability index adjusted for centring.
        cpu: One-sided capability against the upper limit.
        cpl: One-sided capability against the lower limit.
        pp: Performance index, two-sided specification only.
        ppk: Performance index adjusted for centring.
        cpm: Taguchi index, penalising distance from target.
        expected_ppm: Expected non-conforming parts per million under a normal model with
            ``sigma_overall``.
        sigma_level: Process sigma level, ``Z_bench``, computed from ``expected_ppm``.
        skewness: Sample skewness. Values beyond roughly +/-1 undermine ``expected_ppm``.
        excess_kurtosis: Sample excess kurtosis, on the same caveat.
    """

    n: int
    mean: float
    sigma_within: float
    sigma_overall: float
    lsl: float | None
    usl: float | None
    target: float | None
    cp: float
    cpk: float
    cpu: float
    cpl: float
    pp: float
    ppk: float
    cpm: float
    expected_ppm: float
    sigma_level: float
    skewness: float
    excess_kurtosis: float

    def to_series(self) -> pd.Series:
        """Flat representation for reporting."""
        return pd.Series(asdict(self))

    @property
    def normality_warning(self) -> str | None:
        """Warning text when the normal model behind ``expected_ppm`` is doubtful."""
        if abs(self.skewness) > 1.0 or abs(self.excess_kurtosis) > 2.0:
            return (
                f"skewness={self.skewness:.2f}, excess kurtosis={self.excess_kurtosis:.2f}: "
                "the normal model is doubtful, so expected_ppm and sigma_level are unreliable. "
                "Transform the data or use a distribution-appropriate method."
            )
        return None


def _index(half_width: float, sigma: float) -> float:
    """A capability index is a spec half-width measured in three-sigma units."""
    if sigma <= 0 or not np.isfinite(sigma):
        return float("nan")
    return half_width / (3.0 * sigma)


def sigma_within_from_subgroups(data: pd.DataFrame, value: str, subgroup: str) -> float:
    """Estimate short-term sigma from the average subgroup range.

    Args:
        data: Long-format measurements.
        value: Measurement column.
        subgroup: Subgroup identifier column.

    Returns:
        ``R_bar / d2(n)``.

    Raises:
        ValueError: If the subgroup size is not constant or is outside the tabulated range.
    """
    grouped = data.groupby(subgroup, observed=True)[value]
    sizes = grouped.size()
    if sizes.min() != sizes.max():
        raise ValueError(
            "a within-subgroup estimate requires a constant subgroup size; found "
            f"{sorted(sizes.unique().tolist())}"
        )
    n = int(sizes.iloc[0])
    if not MIN_SUBGROUP <= n <= MAX_SUBGROUP:
        raise ValueError(
            f"subgroup size must be between {MIN_SUBGROUP} and {MAX_SUBGROUP}, got {n}"
        )
    r_bar = float((grouped.max() - grouped.min()).mean())
    return r_bar / d2(n)


def sigma_within_from_moving_range(values: pd.Series) -> float:
    """Estimate short-term sigma from the average moving range of individual measurements."""
    series = pd.to_numeric(values, errors="coerce").astype(float).dropna()
    if len(series) < 2:
        raise ValueError("at least 2 observations are required for a moving range estimate")
    return float(series.diff().abs().mean()) / d2(2)


def capability(
    values: pd.Series,
    lsl: float | None = None,
    usl: float | None = None,
    sigma_within: float | None = None,
    target: float | None = None,
) -> Capability:
    """Run a capability study on a measurement series.

    Args:
        values: Measurements. Nulls are dropped.
        lsl: Lower specification limit. Omit for a one-sided upper specification.
        usl: Upper specification limit. Omit for a one-sided lower specification.
        sigma_within: Short-term sigma. Defaults to the moving range estimate, which assumes
            the observations are in time order. Pass
            :func:`sigma_within_from_subgroups` when the data is subgrouped, because the
            moving range estimate absorbs between-subgroup drift into short-term variation and
            understates capability.
        target: Target value, used by ``cpm``. Defaults to the specification midpoint.

    Returns:
        A :class:`Capability`. Indices that are undefined for the given specification - ``cp``
        and ``pp`` with a one-sided limit, for instance - are ``nan`` rather than silently
        computed from a substituted bound.

    Raises:
        ValueError: If no specification limit is given, or if ``lsl >= usl``.
    """
    if lsl is None and usl is None:
        raise ValueError("at least one specification limit is required")
    if lsl is not None and usl is not None and lsl >= usl:
        raise ValueError(f"lsl ({lsl}) must be below usl ({usl})")

    series = pd.to_numeric(values, errors="coerce").astype(float).dropna()
    n = len(series)
    if n < 2:
        raise ValueError("at least 2 observations are required")

    mean = float(series.mean())
    sigma_overall = float(series.std(ddof=1))
    within = (
        float(sigma_within) if sigma_within is not None else sigma_within_from_moving_range(series)
    )

    if target is None and lsl is not None and usl is not None:
        target = (lsl + usl) / 2.0

    cpu = _index(usl - mean, within) if usl is not None else float("nan")
    cpl = _index(mean - lsl, within) if lsl is not None else float("nan")
    ppu = _index(usl - mean, sigma_overall) if usl is not None else float("nan")
    ppl = _index(mean - lsl, sigma_overall) if lsl is not None else float("nan")

    cp = pp = cpm = float("nan")
    if lsl is not None and usl is not None:
        spec_half_width = (usl - lsl) / 2.0
        cp = _index(spec_half_width, within)
        pp = _index(spec_half_width, sigma_overall)
        if target is not None and sigma_overall > 0:
            # Taguchi's index charges the process for distance from target, not only for
            # spread, so a perfectly consistent but off-target process scores poorly.
            tau = np.sqrt(sigma_overall**2 + (mean - target) ** 2)
            cpm = _index(spec_half_width, float(tau))

    cpk = float(np.nanmin([cpu, cpl]))
    ppk = float(np.nanmin([ppu, ppl]))

    # Expected defects use overall sigma: the customer experiences long-term performance, not
    # the short-term potential.
    tail = 0.0
    if sigma_overall > 0:
        if usl is not None:
            tail += 1.0 - _NORMAL.cdf((usl - mean) / sigma_overall)
        if lsl is not None:
            tail += _NORMAL.cdf((lsl - mean) / sigma_overall)
    expected_ppm = float(tail * 1e6)
    sigma_level = float(_NORMAL.inv_cdf(1.0 - tail)) if 0.0 < tail < 1.0 else float("nan")

    return Capability(
        n=n,
        mean=mean,
        sigma_within=within,
        sigma_overall=sigma_overall,
        lsl=lsl,
        usl=usl,
        target=target,
        cp=cp,
        cpk=cpk,
        cpu=cpu,
        cpl=cpl,
        pp=pp,
        ppk=ppk,
        cpm=cpm,
        expected_ppm=expected_ppm,
        sigma_level=sigma_level,
        skewness=float(series.skew()),
        excess_kurtosis=float(series.kurtosis()),
    )


def capability_from_subgroups(
    data: pd.DataFrame,
    value: str = "value",
    subgroup: str = "subgroup",
    lsl: float | None = None,
    usl: float | None = None,
    target: float | None = None,
) -> Capability:
    """Run a capability study on subgrouped data, using the average range for short-term sigma.

    This is the correct entry point whenever the data has rational subgroups, because it keeps
    between-subgroup drift out of the short-term estimate and therefore preserves the
    ``Cpk`` versus ``Ppk`` comparison that makes the study actionable.
    """
    within = sigma_within_from_subgroups(data, value, subgroup)
    return capability(data[value], lsl=lsl, usl=usl, sigma_within=within, target=target)
