"""Nelson run rules for control charts.

The rules detect patterns that are unlikely under a stable process but do not require a point
outside the control limits. Rule 1 alone is a blunt instrument: on a chart with 25 subgroups it
misses a one-sigma mean shift most of the time, while rules 2, 5 and 6 catch it within a few
subgroups.

The cost is false alarms, and the trade-off is quantified rather than asserted. Simulating a
perfectly stable normal process gives these false-alarm rates per plotted point
(reproduced by ``tests/spc/test_rules.py::test_false_alarm_rates``):

============================  ===============  ==========================
Rule set                      Rate per point   One false signal every
============================  ===============  ==========================
Rule 1 only                   0.0024           ~420 points
:data:`PRACTICAL_RULES`       0.0142           ~70 points
:data:`ALL_RULES`             0.0238           ~42 points
============================  ===============  ==========================

One signal every 42 points is acceptable when a signal triggers an investigation and
unacceptable when it triggers a process adjustment, because adjusting a stable process
increases its variation - the failure mode Deming demonstrated with the funnel experiment.
Choose the rule set to match what the organisation actually does with a signal, not by how
sensitive it sounds.

All rules are evaluated on the standardised statistic ``z = (point - centre) / sigma``, so they
work unchanged on charts with varying subgroup size, where the control limits move from point
to point.

Signalling convention: the pattern is attributed to its **last** point, which is the
convention used by Minitab and by most SPC references. Pass ``flag_window=True`` to mark every
point in the pattern instead - useful when annotating a chart, misleading when counting
signals.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

RULE_DESCRIPTIONS: dict[int, str] = {
    1: "1 point beyond 3 sigma",
    2: "9 points in a row on the same side of the centre line",
    3: "6 points in a row steadily increasing or decreasing",
    4: "14 points in a row alternating up and down",
    5: "2 out of 3 consecutive points beyond 2 sigma on the same side",
    6: "4 out of 5 consecutive points beyond 1 sigma on the same side",
    7: "15 points in a row within 1 sigma of the centre line",
    8: "8 points in a row with none within 1 sigma of the centre line",
}

#: The rules most organisations can act on without over-adjusting: an out-of-limit point, a
#: sustained shift, and the two early-warning rules. Rules 3, 4 and 7 are excluded because
#: they most often reflect measurement or stratification artefacts rather than process change.
PRACTICAL_RULES: tuple[int, ...] = (1, 2, 5, 6)
ALL_RULES: tuple[int, ...] = tuple(RULE_DESCRIPTIONS)


@dataclass(frozen=True)
class RuleResult:
    """Outcome of applying run rules to a standardised series.

    Attributes:
        flags: Boolean frame indexed like the input, one column ``rule_{k}`` per rule applied.
        violations: Tidy frame with one row per signal: ``rule``, ``description``, ``position``
            (0-based), ``label`` (the original index value) and ``z``.
    """

    flags: pd.DataFrame
    violations: pd.DataFrame

    @property
    def any_rule(self) -> pd.Series:
        """Whether any applied rule fired at each point."""
        if self.flags.empty:
            return pd.Series(dtype=bool)
        return self.flags.any(axis=1)

    def counts(self) -> pd.Series:
        """Number of signals per rule, including rules that never fired."""
        return self.flags.sum().rename("signals")


def _terminal_flags(hits: np.ndarray, window: int, n: int) -> np.ndarray:
    """Expand per-window hits into point flags on the last point of each window."""
    flags = np.zeros(n, dtype=bool)
    if hits.size:
        flags[np.flatnonzero(hits) + window - 1] = True
    return flags


def _window_flags(hits: np.ndarray, window: int, n: int) -> np.ndarray:
    """Expand per-window hits into point flags on every point of each window."""
    flags = np.zeros(n, dtype=bool)
    for start in np.flatnonzero(hits):
        flags[start : start + window] = True
    return flags


def _rolling_all(mask: np.ndarray, window: int) -> np.ndarray:
    """For each window position, whether ``mask`` holds throughout the window."""
    if mask.size < window:
        return np.zeros(0, dtype=bool)
    view = np.lib.stride_tricks.sliding_window_view(mask, window)
    return np.asarray(view.all(axis=1), dtype=bool)


def _rolling_count(mask: np.ndarray, window: int) -> np.ndarray:
    """For each window position, how many times ``mask`` holds inside the window."""
    if mask.size < window:
        return np.zeros(0, dtype=bool)
    view = np.lib.stride_tricks.sliding_window_view(mask, window)
    return view.sum(axis=1)


def apply_rules(
    z: pd.Series,
    rules: tuple[int, ...] = PRACTICAL_RULES,
    flag_window: bool = False,
) -> RuleResult:
    """Apply Nelson run rules to a standardised control chart statistic.

    Args:
        z: Standardised statistic, ``(point - centre) / sigma``. Nulls are treated as
            non-signalling and break every run.
        rules: Rule numbers to apply. Defaults to :data:`PRACTICAL_RULES`; pass
            :data:`ALL_RULES` for the full set.
        flag_window: Mark every point in a pattern instead of only its last point.

    Returns:
        A :class:`RuleResult`.

    Raises:
        ValueError: If ``rules`` contains an unknown rule number.
    """
    unknown = set(rules) - set(RULE_DESCRIPTIONS)
    if unknown:
        raise ValueError(f"unknown rule number(s) {sorted(unknown)}")

    values = pd.to_numeric(z, errors="coerce").to_numpy(dtype=float)
    n = values.size
    expand = _window_flags if flag_window else _terminal_flags

    finite = np.isfinite(values)
    safe = np.where(finite, values, 0.0)
    above = finite & (safe > 0)
    below = finite & (safe < 0)

    flags: dict[str, np.ndarray] = {}

    if 1 in rules:
        flags["rule_1"] = finite & (np.abs(safe) > 3.0)

    if 2 in rules:
        hits = _rolling_all(above, 9) | _rolling_all(below, 9)
        flags["rule_2"] = expand(hits, 9, n)

    if 3 in rules:
        diffs = np.diff(safe)
        valid = finite[:-1] & finite[1:]
        up = _rolling_all(valid & (diffs > 0), 5)
        down = _rolling_all(valid & (diffs < 0), 5)
        # Five consecutive monotone differences span six points.
        flags["rule_3"] = expand(up | down, 6, n)

    if 4 in rules:
        diffs = np.diff(safe)
        valid = finite[:-1] & finite[1:]
        sign = np.sign(diffs)
        alternating = valid[:-1] & valid[1:] & (sign[:-1] * sign[1:] < 0)
        # Thirteen alternating differences span fourteen points.
        flags["rule_4"] = expand(_rolling_all(alternating, 12), 14, n)

    if 5 in rules:
        beyond_up = above & (safe > 2.0)
        beyond_down = below & (safe < -2.0)
        hits = (_rolling_count(beyond_up, 3) >= 2) | (_rolling_count(beyond_down, 3) >= 2)
        flags["rule_5"] = expand(np.asarray(hits, dtype=bool), 3, n)

    if 6 in rules:
        beyond_up = above & (safe > 1.0)
        beyond_down = below & (safe < -1.0)
        hits = (_rolling_count(beyond_up, 5) >= 4) | (_rolling_count(beyond_down, 5) >= 4)
        flags["rule_6"] = expand(np.asarray(hits, dtype=bool), 5, n)

    if 7 in rules:
        inside = finite & (np.abs(safe) < 1.0)
        flags["rule_7"] = expand(_rolling_all(inside, 15), 15, n)

    if 8 in rules:
        outside = finite & (np.abs(safe) > 1.0)
        flags["rule_8"] = expand(_rolling_all(outside, 8), 8, n)

    ordered = {f"rule_{k}": flags[f"rule_{k}"] for k in sorted(rules)}
    flag_frame = pd.DataFrame(ordered, index=z.index)

    records = []
    for column, mask in ordered.items():
        rule_no = int(column.split("_")[1])
        for position in np.flatnonzero(mask):
            records.append(
                {
                    "rule": rule_no,
                    "description": RULE_DESCRIPTIONS[rule_no],
                    "position": int(position),
                    "label": z.index[position],
                    "z": float(values[position]),
                }
            )
    violations = pd.DataFrame(
        records, columns=["rule", "description", "position", "label", "z"]
    ).sort_values(["position", "rule"], ignore_index=True)

    return RuleResult(flags=flag_frame, violations=violations)
