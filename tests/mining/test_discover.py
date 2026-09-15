"""Discovery against a log whose paths are known, so the graph can be checked rather than admired."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.mining import directly_follows, rework, variant_coverage, variants


def build(paths: dict[str, list[str]], step_minutes: int = 30) -> pd.DataFrame:
    """One event per activity, each taking ten minutes and handing over after ``step_minutes``."""
    rows = []
    for case_id, activities in paths.items():
        clock = pd.Timestamp("2025-01-01 08:00")
        for activity in activities:
            complete = clock + pd.Timedelta(minutes=10)
            rows.append(
                {
                    "case_id": case_id,
                    "activity": activity,
                    "start_ts": clock,
                    "complete_ts": complete,
                }
            )
            clock = complete + pd.Timedelta(minutes=step_minutes)
    return pd.DataFrame(rows)


def test_the_graph_counts_the_pairs_that_were_generated() -> None:
    log = build(
        {
            "A": ["Pick", "Pack", "Ship"],
            "B": ["Pick", "Pack", "Ship"],
            "C": ["Pick", "Check", "Pack", "Ship"],
        }
    )
    graph = directly_follows(log).set_index(["source", "target"])
    assert graph.loc[("Pick", "Pack"), "transitions"] == 2
    assert graph.loc[("Pick", "Check"), "transitions"] == 1
    assert graph.loc[("Pack", "Ship"), "transitions"] == 3
    # Three cases of 3, 3 and 4 events give 2 + 2 + 3 transitions, and the shares sum to one.
    assert graph["transitions"].sum() == 7
    assert graph["share"].sum() == pytest.approx(1.0)
    # The handover time is measured from completion to the next start, not start to start.
    assert graph.loc[("Pick", "Pack"), "mean_handover_h"] == pytest.approx(0.5)


def test_a_self_loop_is_an_edge_like_any_other() -> None:
    log = build({"A": ["Pick", "Pick", "Pack"]})
    graph = directly_follows(log).set_index(["source", "target"])
    assert graph.loc[("Pick", "Pick"), "transitions"] == 1


def test_variants_and_the_coverage_pair() -> None:
    log = build(
        {
            "A": ["Pick", "Pack"],
            "B": ["Pick", "Pack"],
            "C": ["Pick", "Pack"],
            "D": ["Pick", "Check", "Pack"],
            "E": ["Pick", "Repack", "Pack"],
        }
    )
    table = variants(log)
    assert len(table) == 3
    assert table["cases"].to_list() == [3, 1, 1]
    assert table["share"].iloc[0] == pytest.approx(0.6)
    assert table["cumulative_share"].iloc[-1] == pytest.approx(1.0)
    assert table["length"].to_list() == [2, 3, 3]

    needed, total, top = variant_coverage(log, target=0.8)
    assert (needed, total) == (2, 3)
    assert top == pytest.approx(0.6)
    # Covering everything needs every variant, which is the degenerate end of the same question.
    assert variant_coverage(log, target=1.0)[0] == 3

    with pytest.raises(ValueError, match="target must be in"):
        variant_coverage(log, target=0.0)


def test_rework_counts_repeats_and_prices_them() -> None:
    log = build(
        {
            "A": ["Pick", "Check", "Pack"],
            "B": ["Pick", "Check", "Repack", "Check", "Pack"],
            "C": ["Pick", "Check", "Repack", "Check", "Pack"],
        }
    )
    table = rework(log).set_index("activity")
    assert table.loc["Check", "cases_affected"] == 2
    assert table.loc["Check", "share_of_cases"] == pytest.approx(2 / 3)
    assert table.loc["Check", "mean_executions"] == pytest.approx(2.0)
    # Two ten-minute checks against one is ten extra minutes, or a sixth of an hour.
    assert table.loc["Check", "mean_repeat_hours"] == pytest.approx(10 / 60)
    # Pick and Pack run once everywhere, so they are absent rather than listed at zero.
    assert "Pick" not in table.index


def test_an_activity_never_run_once_has_no_baseline_and_says_so() -> None:
    """Substituting zero would report the whole duration as added cost, which is not rework."""
    log = build({"A": ["Pick", "Check", "Check"], "B": ["Pick", "Check", "Check"]})
    table = rework(log).set_index("activity")
    assert table.loc["Check", "mean_executions"] == pytest.approx(2.0)
    assert pd.isna(table.loc["Check", "mean_repeat_hours"])


def test_a_log_with_no_repeats_returns_an_empty_table_with_its_columns() -> None:
    """An empty result still has to be a frame the caller can index, not a special case."""
    table = rework(build({"A": ["Pick", "Pack"], "B": ["Pick", "Pack"]}))
    assert table.empty
    assert list(table.columns) == [
        "activity",
        "cases_affected",
        "share_of_cases",
        "mean_executions",
        "mean_repeat_hours",
    ]
