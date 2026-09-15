"""Making sites comparable before comparing them.

Ranking sites of different size and mix on a raw indicator produces a political ranking rather
than a technical one, and everyone in the room knows it - which is why the discussion goes
straight to "our mix is harder" and stays there. The two techniques here answer that objection
properly instead of arguing about it.

**Scale normalisation** divides by a measure of size. Necessary, and nowhere near sufficient:
cost per order still favours the site whose orders are large.

**Indirect standardisation** is the one that settles the argument. It asks what the network
average rate would have produced *given this site's own mix*, and reports the ratio of observed
to expected. A site with a genuinely harder mix gets a higher expectation and is judged against
it. The technique comes from epidemiology, where comparing crude mortality between regions of
different age structure is the textbook error; the structure of the problem in a distribution
network is identical and the technique is almost never used there.

One detail decides whether the ratio means what it appears to mean. By default the benchmark
includes the unit being measured, so **a site is part of its own reference**. On a network of
four that is 25% of the benchmark, and a genuinely poor site drags the standard towards itself
and comes out looking closer to it than it is: a site 20% more expensive than its peers in
every stratum scores a ratio of 1.02 rather than 1.20. Pass ``exclude_self=True`` to compare
each unit against the rest of the network instead. On a large network the difference is
negligible; on a small one it is most of the signal.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


def scale_normalise(
    frame: pd.DataFrame,
    metrics: Sequence[str],
    scale: str,
    suffix: str = "_per_unit",
) -> pd.DataFrame:
    """Divide each metric by a measure of scale.

    Args:
        frame: One row per unit.
        metrics: Columns to normalise.
        scale: Column holding the size measure, for example orders or units shipped.
        suffix: Appended to each normalised column name.

    Returns:
        ``frame`` with one normalised column per metric.

    Raises:
        KeyError: If a column is missing.
        ValueError: If any scale value is not positive.
    """
    for column in [*metrics, scale]:
        if column not in frame.columns:
            raise KeyError(f"frame has no column {column!r}")
    if (frame[scale] <= 0).any():
        raise ValueError(f"{scale!r} must be positive for every unit")

    out = frame.copy()
    for metric in metrics:
        out[f"{metric}{suffix}"] = out[metric] / out[scale]
    return out


def indirect_standardisation(
    observations: pd.DataFrame,
    unit: str,
    stratum: str,
    numerator: str,
    denominator: str,
    exclude_self: bool = False,
) -> pd.DataFrame:
    """Compare each unit against what the network average would produce on its own mix.

    The expected value for a unit is the sum over strata of that unit's exposure times the
    **network** rate in the same stratum. The observed-over-expected ratio is then free of mix
    by construction: a unit whose mix is harder gets a larger expectation.

    Args:
        observations: Long frame with one row per unit and stratum.
        unit: Column identifying the unit being compared, for example the site.
        stratum: Column identifying the mix dimension - order size band, channel, product
            family. The choice of stratum is the analysis: mix can only be removed along a
            dimension you stratify by.
        numerator: Count of events, for example order lines delivered on time and in full.
        denominator: Exposure, for example order lines in scope.
        exclude_self: Compare each unit against the rest of the network rather than against a
            benchmark that includes it. Leave it off on a large network; turn it on whenever a
            unit is a material share of its own reference, which on a four-site network it
            always is.

    Returns:
        One row per unit with ``observed``, ``expected``, ``exposure``, ``crude_rate``,
        ``standardised_ratio`` and ``standardised_rate`` - the last being the ratio applied to
        the network's overall rate, so it reads on the same scale as the crude figure.

    Raises:
        KeyError: If a column is missing.
        ValueError: If the frame is empty or total exposure is not positive.
    """
    for column in (unit, stratum, numerator, denominator):
        if column not in observations.columns:
            raise KeyError(f"observations has no column {column!r}")
    if observations.empty:
        raise ValueError("observations is empty")

    totals = observations.groupby(stratum, observed=True)[[numerator, denominator]].sum()
    frame = observations.copy()

    if exclude_self:
        # Each unit is measured against the rest of the network, not against a benchmark it is
        # itself part of. On a four-site network a unit is a quarter of its own reference, and
        # a poor one drags the standard towards itself.
        rest_numerator = frame[stratum].map(totals[numerator]) - frame[numerator]
        rest_denominator = (frame[stratum].map(totals[denominator]) - frame[denominator]).replace(
            0.0, np.nan
        )
        reference_rate = (rest_numerator / rest_denominator).replace([np.inf, -np.inf], np.nan)
    else:
        network_rate = (totals[numerator] / totals[denominator]).replace([np.inf, -np.inf], np.nan)
        reference_rate = frame[stratum].map(network_rate)

    frame["_expected"] = frame[denominator] * reference_rate

    grouped = frame.groupby(unit, observed=True).agg(
        observed=(numerator, "sum"),
        expected=("_expected", "sum"),
        exposure=(denominator, "sum"),
    )

    total_exposure = float(grouped["exposure"].sum())
    if total_exposure <= 0:
        raise ValueError("total exposure must be positive")
    overall_rate = float(grouped["observed"].sum()) / total_exposure

    grouped["crude_rate"] = grouped["observed"] / grouped["exposure"]
    grouped["standardised_ratio"] = grouped["observed"] / grouped["expected"].replace(0.0, np.nan)
    grouped["standardised_rate"] = grouped["standardised_ratio"] * overall_rate
    grouped["mix_effect"] = grouped["standardised_rate"] - grouped["crude_rate"]
    return grouped.reset_index()
