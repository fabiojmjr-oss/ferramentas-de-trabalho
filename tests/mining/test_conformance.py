"""Conformance, and the blindness of the measure it uses - asserted, because it is the finding."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.mining import conformance, cost_of_deviation, deviations

MODEL = ("Pick", "Pack", "Ship")


def build(paths: dict[str, list[str]]) -> pd.DataFrame:
    rows = []
    for case_id, activities in paths.items():
        clock = pd.Timestamp("2025-01-01 08:00")
        for activity in activities:
            complete = clock + pd.Timedelta(hours=1)
            rows.append(
                {
                    "case_id": case_id,
                    "activity": activity,
                    "start_ts": clock,
                    "complete_ts": complete,
                }
            )
            clock = complete + pd.Timedelta(hours=1)
    return pd.DataFrame(rows)


def test_fitness_counts_containment_and_exact_counts_the_process() -> None:
    log = build(
        {
            "A": ["Pick", "Pack", "Ship"],
            "B": ["Pick", "Check", "Pack", "Ship"],
            "C": ["Pick", "Pack"],
        }
    )
    result = conformance(log, MODEL)
    assert result.cases == 3
    # A and B contain the documented sequence in order; C is missing a step.
    assert result.conforming == 2
    assert result.fitness == pytest.approx(2 / 3)
    # Only A is the documented process and nothing else.
    assert result.exact == 1
    assert result.exact_share == pytest.approx(1 / 3)
    assert result.model == MODEL


def test_the_measure_is_blind_to_insertions_and_that_is_the_point() -> None:
    """A containment test permits extra steps, so it scores a heavily reworked case as conformant.

    This is asserted rather than described because the gap between fitness and the exact share is
    the finding the module reports: a high fitness can coexist with a process most cases do not
    follow, and quoting the first as 'conformance' is how that gets missed.
    """
    log = build(
        {
            "A": ["Pick", "Hold", "Pick", "Check", "Pack", "Repack", "Pack", "Ship"],
            "B": ["Pick", "Pack", "Ship"],
        }
    )
    result = conformance(log, MODEL)
    assert result.fitness == pytest.approx(1.0)
    assert result.exact_share == pytest.approx(0.5)


def test_a_reordered_case_is_caught_when_the_order_actually_breaks() -> None:
    log = build({"A": ["Ship", "Pack", "Pick"]})
    assert conformance(log, MODEL).conforming == 0


def test_deviations_separate_inserted_skipped_and_repeated() -> None:
    log = build(
        {
            "A": ["Pick", "Pack", "Ship"],
            "B": ["Pick", "Check", "Pack", "Ship"],
            "C": ["Pick", "Pack", "Pack", "Ship"],
            "D": ["Pick", "Ship"],
        }
    )
    table = deviations(log, MODEL).set_index(["activity", "kind"])
    assert table.loc[("Check", "inserted"), "cases"] == 1
    assert table.loc[("Pack", "repeated"), "cases"] == 1
    assert table.loc[("Pack", "skipped"), "cases"] == 1
    assert table.loc[("Check", "inserted"), "share_of_cases"] == pytest.approx(0.25)
    # Activities that always run exactly once appear nowhere, which keeps the table readable.
    assert "Pick" not in table.index.get_level_values("activity")


def test_a_fully_conformant_log_gives_an_empty_deviation_table_with_its_columns() -> None:
    table = deviations(build({"A": ["Pick", "Pack", "Ship"]}), MODEL)
    assert table.empty
    assert list(table.columns) == ["activity", "kind", "cases", "share_of_cases"]


def test_cost_of_deviation_puts_the_two_groups_side_by_side() -> None:
    log = build(
        {
            "A": ["Pick", "Pack", "Ship"],
            "B": ["Pick", "Pack", "Ship"],
            "C": ["Pick", "Check", "Pack", "Ship"],
        }
    )
    table = cost_of_deviation(log, MODEL, value_adding=("Pick", "Pack")).set_index("group")
    assert table.loc["follows the documented path", "cases"] == 2
    assert table.loc["deviates", "cases"] == 1
    # Each activity is an hour and each handover an hour, so three steps span five hours and four
    # steps span seven.
    assert table.loc["follows the documented path", "mean_lead_h"] == pytest.approx(5.0)
    assert table.loc["deviates", "mean_lead_h"] == pytest.approx(7.0)
    # The inserted step is work, and it is not value-adding work, so flow efficiency falls.
    assert (
        table.loc["deviates", "flow_efficiency"]
        < table.loc["follows the documented path", "flow_efficiency"]
    )


def test_conformance_guards() -> None:
    log = build({"A": ["Pick", "Pack", "Ship"]})
    with pytest.raises(ValueError, match="at least one activity"):
        conformance(log, ())
    with pytest.raises(ValueError, match="at least one activity"):
        deviations(log, ())
    with pytest.raises(ValueError, match="model must name"):
        cost_of_deviation(log, (), value_adding=("Pick",))
    with pytest.raises(ValueError, match="value_adding must name"):
        cost_of_deviation(log, MODEL, value_adding=())
