"""Control charts for variables and attributes data.

Choosing the chart is most of the work, and getting it wrong invalidates everything
downstream:

=========================  ==========================================  ====================
Data                       Chart                                       Function
=========================  ==========================================  ====================
Measurements in subgroups  X-bar and R                                 :func:`xbar_r_chart`
Individual measurements    Individuals and moving range                :func:`i_mr_chart`
Proportion defective       p chart (binomial, varying sample size)     :func:`p_chart`
Defects per unit           u chart (Poisson, varying exposure)         :func:`u_chart`
=========================  ==========================================  ====================

The most frequent error in applied work is plotting a proportion on an individuals chart. The
limits come out symmetric and constant, which looks reasonable, but a proportion measured on
80 orders and one measured on 8,000 do not carry the same information. The p chart widens its
limits for the small sample and narrows them for the large one, and that is the whole point.

Every chart is built from **within-subgroup** variation - the average range, or the average
moving range - never from the standard deviation of the plotted points. Using the overall
standard deviation absorbs the shift you are trying to detect into the limits themselves, so
an unstable process gets a chart that declares it stable.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .constants import MAX_SUBGROUP, MIN_SUBGROUP, a2, d2, d3, d4
from .rules import PRACTICAL_RULES, RuleResult, apply_rules


@dataclass(frozen=True)
class ControlChart:
    """A fitted control chart.

    Attributes:
        name: Chart name, for example ``"X-bar"`` or ``"p"``.
        points: The plotted statistic.
        center: Centre line.
        sigma: Standard error of the plotted statistic at each point. Constant for variables
            charts with a fixed subgroup size, varying for attributes charts.
        ucl: Upper control limit at each point.
        lcl: Lower control limit at each point.
        rule_result: Outcome of the run rules applied to the chart.
        subgroup_size: Observations per subgroup, or the sample size at each point.
    """

    name: str
    points: pd.Series
    center: float
    sigma: pd.Series
    ucl: pd.Series
    lcl: pd.Series
    rule_result: RuleResult
    subgroup_size: pd.Series

    @property
    def z(self) -> pd.Series:
        """Standardised statistic, ``(point - centre) / sigma``."""
        return ((self.points - self.center) / self.sigma).rename("z")

    @property
    def out_of_control(self) -> pd.Series:
        """Whether any applied run rule fired at each point."""
        return self.rule_result.any_rule.rename("out_of_control")

    @property
    def violations(self) -> pd.DataFrame:
        """Tidy frame of rule signals."""
        return self.rule_result.violations

    def to_frame(self) -> pd.DataFrame:
        """Everything needed to plot or audit the chart, as one frame."""
        frame = pd.DataFrame(
            {
                "point": self.points,
                "center": self.center,
                "lcl": self.lcl,
                "ucl": self.ucl,
                "sigma": self.sigma,
                "n": self.subgroup_size,
                "z": self.z,
            }
        )
        return frame.join(self.rule_result.flags).assign(out_of_control=self.out_of_control)

    def summary(self) -> pd.Series:
        """Headline numbers for a report line."""
        return pd.Series(
            {
                "chart": self.name,
                "points": int(len(self.points)),
                "center": float(self.center),
                "lcl": float(self.lcl.mean()),
                "ucl": float(self.ucl.mean()),
                "signals": int(self.out_of_control.sum()),
                "signal_rate": float(self.out_of_control.mean()),
            }
        )


def _pivot_subgroups(
    data: pd.DataFrame, value: str, subgroup: str
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Reduce long-format measurements to per-subgroup mean, range and size."""
    for column in (value, subgroup):
        if column not in data.columns:
            raise KeyError(f"data has no column {column!r}")

    grouped = data.groupby(subgroup, observed=True)[value]
    sizes = grouped.size()
    if sizes.min() != sizes.max():
        raise ValueError(
            "X-bar and R charts require a constant subgroup size; found sizes "
            f"{sorted(sizes.unique().tolist())}. Use i_mr_chart for individual measurements."
        )
    n = int(sizes.iloc[0])
    if not MIN_SUBGROUP <= n <= MAX_SUBGROUP:
        raise ValueError(
            f"subgroup size must be between {MIN_SUBGROUP} and {MAX_SUBGROUP}, got {n}"
        )

    return grouped.mean(), grouped.max() - grouped.min(), sizes


def xbar_r_chart(
    data: pd.DataFrame,
    value: str = "value",
    subgroup: str = "subgroup",
    baseline: slice | None = None,
    rules: tuple[int, ...] = PRACTICAL_RULES,
) -> tuple[ControlChart, ControlChart]:
    """Fit an X-bar and R chart pair to subgrouped measurements.

    Read the R chart first. Control limits on the X-bar chart are derived from the average
    range, so if dispersion is unstable the X-bar limits are computed from a quantity that has
    no single value, and any conclusion about the mean is unsafe.

    Args:
        data: Long-format measurements, one row per observation.
        value: Column holding the measurement.
        subgroup: Column identifying the subgroup.
        baseline: Optional slice of subgroups used to estimate the limits, for example
            ``slice(0, 30)``. Use it to establish limits on a period known to be stable and
            then judge later periods against them - which is what a control chart is for.

            Estimating the limits on a series that already contains the disturbance does not
            widen them here, and it is worth being precise about why: the limit half-width is
            ``A2 * R_bar``, built from within-subgroup range, and a shift in the process mean
            between subgroups leaves the within-subgroup range untouched. What moves is the
            **centre line**, which is pulled towards the disturbed period. The chart then
            reports the stable period as off-centre and dilutes the signal at the point where
            the process actually changed, so the shift is dated wrongly - and a wrong date
            sends the investigation to the wrong shift, the wrong batch and the wrong cause.

            Limits genuinely inflate when sigma is estimated from the standard deviation of the
            plotted points instead of within-subgroup variation. That is a different error, and
            no function in this module commits it.
        rules: Run rules to apply.

    Returns:
        ``(xbar_chart, r_chart)``.
    """
    means, ranges, sizes = _pivot_subgroups(data, value, subgroup)
    n = int(sizes.iloc[0])

    fit_means = means if baseline is None else means.iloc[baseline]
    fit_ranges = ranges if baseline is None else ranges.iloc[baseline]
    if len(fit_ranges) < 2:
        raise ValueError("at least 2 subgroups are required to estimate control limits")

    grand_mean = float(fit_means.mean())
    r_bar = float(fit_ranges.mean())

    # A2 * R-bar is three standard errors of the subgroup mean, so sigma follows by division.
    xbar_sigma = a2(n) * r_bar / 3.0
    xbar = ControlChart(
        name="X-bar",
        points=means.rename("xbar"),
        center=grand_mean,
        sigma=pd.Series(xbar_sigma, index=means.index, name="sigma"),
        ucl=pd.Series(grand_mean + a2(n) * r_bar, index=means.index, name="ucl"),
        lcl=pd.Series(grand_mean - a2(n) * r_bar, index=means.index, name="lcl"),
        rule_result=apply_rules(
            ((means - grand_mean) / xbar_sigma) if xbar_sigma > 0 else means * 0.0, rules
        ),
        subgroup_size=sizes,
    )

    # The range distribution is skewed, so its limits are not symmetric and rules that assume
    # symmetry around the centre line do not apply. Only rule 1 is used on the R chart.
    r_ucl = d4(n) * r_bar
    r_lcl = d3(n) * r_bar
    r_sigma = (r_ucl - r_bar) / 3.0
    r_chart = ControlChart(
        name="R",
        points=ranges.rename("range"),
        center=r_bar,
        sigma=pd.Series(r_sigma, index=ranges.index, name="sigma"),
        ucl=pd.Series(r_ucl, index=ranges.index, name="ucl"),
        lcl=pd.Series(r_lcl, index=ranges.index, name="lcl"),
        rule_result=apply_rules(
            pd.Series(
                np.where(ranges > r_ucl, 3.1, np.where(ranges < r_lcl, -3.1, 0.0)),
                index=ranges.index,
            ),
            (1,),
        ),
        subgroup_size=sizes,
    )
    return xbar, r_chart


def i_mr_chart(
    values: pd.Series,
    baseline: slice | None = None,
    rules: tuple[int, ...] = PRACTICAL_RULES,
) -> tuple[ControlChart, ControlChart]:
    """Fit an individuals and moving range chart pair.

    Use this when measurements arrive one at a time and there is no rational basis for
    subgrouping: a daily cost per order, a weekly inventory accuracy figure, a monthly cost per
    pallet. The individuals chart is markedly less sensitive than X-bar and is more affected by
    non-normality, so a strongly skewed series should be transformed before charting.

    Args:
        values: Individual measurements, in time order.
        baseline: Optional slice used to estimate the limits.
        rules: Run rules to apply to the individuals chart.

    Returns:
        ``(individuals_chart, moving_range_chart)``.
    """
    series = pd.to_numeric(values, errors="coerce").astype(float)
    if len(series) < 3:
        raise ValueError("at least 3 observations are required for an I-MR chart")

    moving_range = series.diff().abs()
    fit_values = series if baseline is None else series.iloc[baseline]
    fit_mr = moving_range if baseline is None else moving_range.iloc[baseline]

    center = float(fit_values.mean())
    mr_bar = float(fit_mr.mean())
    sigma = mr_bar / d2(2)

    ones = pd.Series(1, index=series.index, name="n")
    individuals = ControlChart(
        name="Individuals",
        points=series.rename("value"),
        center=center,
        sigma=pd.Series(sigma, index=series.index, name="sigma"),
        ucl=pd.Series(center + 3 * sigma, index=series.index, name="ucl"),
        lcl=pd.Series(center - 3 * sigma, index=series.index, name="lcl"),
        rule_result=apply_rules(((series - center) / sigma) if sigma > 0 else series * 0.0, rules),
        subgroup_size=ones,
    )

    mr_ucl = d4(2) * mr_bar
    mr_sigma = (mr_ucl - mr_bar) / 3.0
    mr_chart = ControlChart(
        name="Moving range",
        points=moving_range.rename("moving_range"),
        center=mr_bar,
        sigma=pd.Series(mr_sigma, index=series.index, name="sigma"),
        ucl=pd.Series(mr_ucl, index=series.index, name="ucl"),
        lcl=pd.Series(0.0, index=series.index, name="lcl"),
        rule_result=apply_rules(
            pd.Series(np.where(moving_range.fillna(0.0) > mr_ucl, 3.1, 0.0), index=series.index),
            (1,),
        ),
        subgroup_size=pd.Series(2, index=series.index, name="n"),
    )
    return individuals, mr_chart


def p_chart(
    defectives: pd.Series,
    sample_size: pd.Series,
    baseline: slice | None = None,
    rules: tuple[int, ...] = PRACTICAL_RULES,
) -> ControlChart:
    """Fit a p chart to a proportion with varying sample size.

    This is the right chart for most logistics service data, because the denominator moves:
    the share of late deliveries, damaged lines, or failed picks, measured weekly on a volume
    that is never the same twice.

    Limits are computed per point from that point's sample size, and the lower limit is clipped
    at zero, since a negative proportion has no meaning. When a sample size is small enough
    that ``n * p_bar < 5`` the normal approximation behind the limits is weak and the point
    should be read with caution rather than acted on.

    Args:
        defectives: Count of defective units at each point.
        sample_size: Units inspected at each point.
        baseline: Optional slice used to estimate the centre line.
        rules: Run rules to apply.

    Returns:
        The fitted chart.
    """
    counts = pd.to_numeric(defectives, errors="coerce").astype(float)
    sizes = pd.to_numeric(sample_size, errors="coerce").astype(float)
    if not counts.index.equals(sizes.index):
        raise ValueError("defectives and sample_size must share an index")
    if (sizes <= 0).any():
        raise ValueError("sample_size must be positive at every point")
    if (counts > sizes).any():
        raise ValueError("defectives cannot exceed sample_size")

    proportion = (counts / sizes).rename("p")
    fit_counts = counts if baseline is None else counts.iloc[baseline]
    fit_sizes = sizes if baseline is None else sizes.iloc[baseline]

    # The centre line is the pooled proportion, not the mean of the proportions: points built
    # on larger samples must carry more weight.
    p_bar = float(fit_counts.sum() / fit_sizes.sum())
    sigma = (p_bar * (1 - p_bar) / sizes).pow(0.5).rename("sigma")

    return ControlChart(
        name="p",
        points=proportion,
        center=p_bar,
        sigma=sigma,
        ucl=(p_bar + 3 * sigma).clip(upper=1.0).rename("ucl"),
        lcl=(p_bar - 3 * sigma).clip(lower=0.0).rename("lcl"),
        rule_result=apply_rules(
            ((proportion - p_bar) / sigma).replace([np.inf, -np.inf], np.nan), rules
        ),
        subgroup_size=sizes.rename("n"),
    )


def u_chart(
    defects: pd.Series,
    exposure: pd.Series,
    baseline: slice | None = None,
    rules: tuple[int, ...] = PRACTICAL_RULES,
) -> ControlChart:
    """Fit a u chart to defects per unit of exposure.

    Use it when a single unit can carry several defects, so a proportion is not defined:
    damages per thousand pallets shipped, exceptions per hundred order lines, non-conformities
    per audit. The distinction from the p chart is the question being asked - "what share of
    units failed" is binomial, "how many failures occurred" is Poisson - and using the wrong
    one misstates the limits in both directions.

    Args:
        defects: Count of defects at each point.
        exposure: Units of exposure at each point, in whatever unit the rate is quoted in.
        baseline: Optional slice used to estimate the centre line.
        rules: Run rules to apply.

    Returns:
        The fitted chart.
    """
    counts = pd.to_numeric(defects, errors="coerce").astype(float)
    units = pd.to_numeric(exposure, errors="coerce").astype(float)
    if not counts.index.equals(units.index):
        raise ValueError("defects and exposure must share an index")
    if (units <= 0).any():
        raise ValueError("exposure must be positive at every point")

    rate = (counts / units).rename("u")
    fit_counts = counts if baseline is None else counts.iloc[baseline]
    fit_units = units if baseline is None else units.iloc[baseline]

    u_bar = float(fit_counts.sum() / fit_units.sum())
    sigma = (u_bar / units).pow(0.5).rename("sigma")

    return ControlChart(
        name="u",
        points=rate,
        center=u_bar,
        sigma=sigma,
        ucl=(u_bar + 3 * sigma).rename("ucl"),
        lcl=(u_bar - 3 * sigma).clip(lower=0.0).rename("lcl"),
        rule_result=apply_rules(((rate - u_bar) / sigma).replace([np.inf, -np.inf], np.nan), rules),
        subgroup_size=units.rename("n"),
    )


def overdispersion_ratio(chart: ControlChart) -> float:
    """Compare observed point-to-point variation with what the chart's model predicts.

    Attributes and count charts assume independent trials: a p chart assumes each inspected
    unit fails independently, a u chart assumes defects arrive as a Poisson process. When the
    data is clustered, that assumption fails and the modelled sigma is too small, so the chart
    signals constantly on a process that is perfectly stable.

    The clustering is usually a wrong unit of analysis rather than a wrong chart. Charting late
    **order lines** is the standard example: the lines of one order travel on one vehicle, so
    one late truck produces a dozen correlated failures. The effective sample size is the
    number of orders, not the number of lines.

    Interpretation:

    ``~1.0``
        The model fits. Signals can be read as signals.
    ``> 1.2``
        Overdispersed. Find the cluster and chart at that level, or use a chart built for
        extra variation. Do not act on the signals first: most of them are artefacts.
    ``< 0.8``
        Underdispersed, which usually means the denominator is wrong or the data has been
        smoothed, rounded or averaged before charting.

    Args:
        chart: A fitted chart, normally from :func:`p_chart` or :func:`u_chart`.

    Returns:
        Observed standard deviation of the plotted points divided by the mean modelled sigma.
        ``nan`` when there are fewer than two points or the modelled sigma is zero.
    """
    points = chart.points.dropna()
    if len(points) < 2:
        return float("nan")
    modelled = float(chart.sigma.reindex(points.index).mean())
    if not np.isfinite(modelled) or modelled <= 0:
        return float("nan")
    return float(points.std(ddof=1)) / modelled
