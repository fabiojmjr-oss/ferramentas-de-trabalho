"""Cycle time and flow efficiency against a log whose hours are known exactly."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.mining import (
    activity_times,
    case_times,
    flow_efficiency,
    waiting_ranked,
)


def log() -> pd.DataFrame:
    """One case: one hour of picking, three hours of waiting, one hour of packing.

    Lead time is five hours, work is two, wait is three, and value-adding work is one if only
    picking counts. Every assertion below is that arithmetic.
    """
    return pd.DataFrame(
        {
            "case_id": ["A", "A"],
            "activity": ["Pick", "Pack"],
            "start_ts": pd.to_datetime(["2025-01-01 08:00", "2025-01-01 12:00"]),
            "complete_ts": pd.to_datetime(["2025-01-01 09:00", "2025-01-01 13:00"]),
        }
    )


def test_case_times_split_lead_into_work_and_wait() -> None:
    table = case_times(log()).set_index("case_id")
    assert table.loc["A", "lead_h"] == pytest.approx(5.0)
    assert table.loc["A", "work_h"] == pytest.approx(2.0)
    assert table.loc["A", "wait_h"] == pytest.approx(3.0)
    assert table.loc["A", "events"] == 2
    # The first and last activity are reported so a truncated case can be spotted rather than
    # averaged into the result.
    assert table.loc["A", "first_activity"] == "Pick"
    assert table.loc["A", "last_activity"] == "Pack"


def test_activity_times_attribute_the_wait_to_the_step_before_it() -> None:
    table = activity_times(log()).set_index("activity")
    assert table.loc["Pick", "mean_wait_after_h"] == pytest.approx(3.0)
    # The last activity of a case has nothing after it, so its wait is missing, not zero.
    assert pd.isna(table.loc["Pack", "mean_wait_after_h"])
    assert table.loc["Pick", "total_duration_h"] == pytest.approx(1.0)


def test_flow_efficiency_and_the_gap_that_inspection_hides() -> None:
    efficiency = flow_efficiency(log(), value_adding=("Pick",))
    assert efficiency.lead_h == pytest.approx(5.0)
    assert efficiency.work_h == pytest.approx(2.0)
    assert efficiency.wait_h == pytest.approx(3.0)
    assert efficiency.value_adding_h == pytest.approx(1.0)
    assert efficiency.flow_efficiency == pytest.approx(0.2)
    # Busy share counts packing too; the gap between the two is the number that gets quoted
    # instead of flow efficiency.
    assert efficiency.busy_share == pytest.approx(0.4)
    assert efficiency.cases == 1


def test_a_typo_in_the_value_adding_set_is_refused_rather_than_deflating_the_answer() -> None:
    """Silently scoring an unmatched name as zero would understate flow efficiency invisibly."""
    with pytest.raises(ValueError, match="absent from the log"):
        flow_efficiency(log(), value_adding=("Picking",))
    with pytest.raises(ValueError, match="at least one activity"):
        flow_efficiency(log(), value_adding=())


def test_waiting_is_ranked_by_total_and_not_by_mean() -> None:
    """A slow rare step costs less than a quick universal one, and the ranking has to show it."""
    frame = pd.DataFrame(
        {
            "case_id": ["A", "A", "B", "B", "C", "C"],
            "activity": ["Slow", "End", "Quick", "End", "Quick", "End"],
            "start_ts": pd.to_datetime(
                [
                    "2025-01-01 08:00",
                    "2025-01-01 18:00",
                    "2025-01-01 08:00",
                    "2025-01-01 14:00",
                    "2025-01-01 08:00",
                    "2025-01-01 14:00",
                ]
            ),
            "complete_ts": pd.to_datetime(
                [
                    "2025-01-01 08:30",
                    "2025-01-01 18:30",
                    "2025-01-01 08:30",
                    "2025-01-01 14:30",
                    "2025-01-01 08:30",
                    "2025-01-01 14:30",
                ]
            ),
        }
    )
    activities = activity_times(frame).set_index("activity")
    assert activities.loc["Slow", "mean_wait_after_h"] == pytest.approx(9.5)
    assert activities.loc["Quick", "mean_wait_after_h"] == pytest.approx(5.5)

    ranked = waiting_ranked(frame).set_index("activity")
    # Quick waits less each time and twice as often, so it holds more of the lead time.
    assert ranked.loc["Quick", "total_wait_after_h"] == pytest.approx(11.0)
    assert ranked.loc["Slow", "total_wait_after_h"] == pytest.approx(9.5)
    assert ranked.index[0] == "Quick"
    assert ranked["share_of_waiting"].sum() == pytest.approx(1.0)
    assert ranked["cumulative_share"].iloc[-1] == pytest.approx(1.0)
    # The final activity of every case contributes no waiting, so it is absent.
    assert "End" not in ranked.index
