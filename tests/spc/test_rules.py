"""Nelson run rules.

Each rule is checked on a series built to trigger exactly that rule, and on a series built to
look similar but not qualify. Positive tests alone would pass a rule that fires on everything.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.spc import ALL_RULES, PRACTICAL_RULES, RULE_DESCRIPTIONS, apply_rules


def positions(z: list[float], rules: tuple[int, ...]) -> list[int]:
    return apply_rules(pd.Series(z), rules).violations["position"].tolist()


def test_rule_1_flags_a_point_beyond_three_sigma() -> None:
    assert positions([0.1, -0.2, 3.4, 0.0], (1,)) == [2]
    assert positions([0.1, -0.2, 2.9, 0.0], (1,)) == []


def test_rule_2_needs_nine_consecutive_points_on_one_side() -> None:
    assert positions([0.3] * 9, (2,)) == [8]
    assert positions([0.3] * 8, (2,)) == []
    # A single crossing resets the run.
    assert positions([0.3] * 8 + [-0.1] + [0.3] * 8, (2,)) == []


def test_rule_3_needs_six_monotone_points() -> None:
    assert positions([0.0, 0.1, 0.2, 0.3, 0.4, 0.5], (3,)) == [5]
    assert positions([0.5, 0.4, 0.3, 0.2, 0.1, 0.0], (3,)) == [5]
    # A repeated value is not an increase.
    assert positions([0.0, 0.1, 0.1, 0.2, 0.3, 0.4], (3,)) == []


def test_rule_4_needs_fourteen_alternating_points() -> None:
    alternating = [0.5 if i % 2 else -0.5 for i in range(14)]
    assert positions(alternating, (4,)) == [13]
    assert positions(alternating[:13], (4,)) == []


def test_rule_5_requires_the_same_side() -> None:
    assert positions([0.1, 2.3, 0.4, 2.5], (5,)) == [3]
    assert positions([0.1, 2.3, -2.5, 0.1], (5,)) == []
    assert positions([0.1, 1.9, 1.9, 0.1], (5,)) == []


def test_rule_6_requires_four_of_five_on_the_same_side() -> None:
    assert positions([1.2, 1.3, 0.1, 1.4, 1.5], (6,)) == [4]
    assert positions([1.2, 1.3, 0.1, 0.2, 1.5], (6,)) == []
    assert positions([1.2, 1.3, -1.4, -1.5, 1.6], (6,)) == []


def test_rule_7_detects_a_series_hugging_the_centre_line() -> None:
    assert positions([0.2, -0.3] * 8, (7,)) == [14, 15]
    assert positions([0.2, -0.3] * 7, (7,)) == []


def test_rule_8_detects_a_series_avoiding_the_centre_line() -> None:
    assert positions([1.5, -1.4, 1.6, -1.7, 1.2, -1.3, 1.8, -1.9], (8,)) == [7]
    assert positions([1.5, -1.4, 1.6, -1.7, 0.2, -1.3, 1.8, -1.9], (8,)) == []


def test_nulls_break_runs_instead_of_signalling() -> None:
    z = pd.Series([0.3] * 4 + [np.nan] + [0.3] * 4)
    result = apply_rules(z, (1, 2))
    assert result.violations.empty
    assert not result.any_rule.any()


def test_window_flagging_marks_every_point_in_the_pattern() -> None:
    z = pd.Series([0.3] * 9)
    terminal = apply_rules(z, (2,))
    windowed = apply_rules(z, (2,), flag_window=True)
    assert int(terminal.flags["rule_2"].sum()) == 1
    assert int(windowed.flags["rule_2"].sum()) == 9


def test_unknown_rule_numbers_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown rule"):
        apply_rules(pd.Series([0.0]), (1, 99))


def test_series_shorter_than_a_window_does_not_signal() -> None:
    result = apply_rules(pd.Series([0.5, 0.5]), ALL_RULES)
    assert result.violations.empty
    assert list(result.counts().index) == [f"rule_{k}" for k in sorted(ALL_RULES)]


def test_every_rule_has_a_description() -> None:
    assert set(ALL_RULES) == set(RULE_DESCRIPTIONS)
    assert set(PRACTICAL_RULES) <= set(ALL_RULES)


def test_false_alarm_rates() -> None:
    """Measure the false-alarm rate on a stable process.

    These are the numbers quoted in the module docstring. The tolerances are wide enough to
    absorb simulation noise but narrow enough to fail if a rule is implemented too loosely,
    which is the failure mode that matters: an over-eager rule set drives adjustment of a
    stable process.
    """
    rng = np.random.default_rng(11)
    series = [pd.Series(rng.normal(size=500)) for _ in range(120)]
    total_points = sum(len(s) for s in series)

    rates = {
        label: sum(int(apply_rules(s, rules).any_rule.sum()) for s in series) / total_points
        for label, rules in (("rule_1", (1,)), ("practical", PRACTICAL_RULES), ("all", ALL_RULES))
    }

    assert rates["rule_1"] == pytest.approx(0.0024, abs=0.0012)
    assert rates["practical"] == pytest.approx(0.0142, abs=0.004)
    assert rates["all"] == pytest.approx(0.0238, abs=0.005)
    assert rates["rule_1"] < rates["practical"] < rates["all"]
