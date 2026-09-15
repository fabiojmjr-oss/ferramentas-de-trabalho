"""The two validations, tested against the defects they exist to catch."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.mining import profile_log, to_event_log, validate_log


def good_log() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "case_id": ["A", "A", "B", "B"],
            "activity": ["Pick", "Pack", "Pick", "Pack"],
            "start_ts": pd.to_datetime(
                ["2025-01-01 08:00", "2025-01-01 09:00", "2025-01-01 08:30", "2025-01-01 10:00"]
            ),
            "complete_ts": pd.to_datetime(
                ["2025-01-01 08:20", "2025-01-01 09:10", "2025-01-01 08:55", "2025-01-01 10:15"]
            ),
        }
    )


def test_a_valid_log_comes_back_sorted() -> None:
    shuffled = good_log().iloc[[3, 1, 2, 0]]
    validated = validate_log(shuffled)
    assert list(validated["case_id"]) == ["A", "A", "B", "B"]
    assert list(validated["activity"]) == ["Pick", "Pack", "Pick", "Pack"]


def test_every_problem_is_reported_in_one_pass() -> None:
    """A log is usually wrong in several ways at once; one exception per run is the slow route."""
    broken = good_log().drop(columns=["activity", "complete_ts"])
    with pytest.raises(ValueError) as error:
        validate_log(broken)
    assert "activity" in str(error.value)
    assert "complete_ts" in str(error.value)


def test_an_empty_log_says_so() -> None:
    with pytest.raises(ValueError, match="empty"):
        validate_log(pd.DataFrame())


@pytest.mark.filterwarnings("ignore:Could not infer format:UserWarning")
def test_unparseable_timestamps_are_counted_not_dropped() -> None:
    frame = good_log()
    frame["start_ts"] = frame["start_ts"].astype(str)
    frame.loc[0, "start_ts"] = "not a date"
    with pytest.raises(ValueError, match="start_ts has 1 unparseable"):
        validate_log(frame)


def test_an_event_that_finishes_before_it_starts_is_refused() -> None:
    frame = good_log()
    frame.loc[0, "complete_ts"] = frame.loc[0, "start_ts"] - pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="complete before they start"):
        validate_log(frame)


def test_the_profile_reports_whether_durations_exist_at_all() -> None:
    """This is the check that decides whether flow efficiency is computable."""
    profile = profile_log(good_log())
    assert profile.cases == 2
    assert profile.events == 4
    assert profile.activities == 2
    assert profile.events_per_case == pytest.approx(2.0)
    assert profile.zero_duration_events == 0
    assert profile.separates_work_from_wait

    flattened = good_log()
    flattened["complete_ts"] = flattened["start_ts"]
    assert not profile_log(flattened).separates_work_from_wait


def test_a_wide_table_reshapes_and_admits_what_it_lost() -> None:
    wide = pd.DataFrame(
        {
            "order_id": ["A", "B"],
            "site": ["CD-SP", "CD-RJ"],
            "ordered": pd.to_datetime(["2025-01-01 08:00", "2025-01-01 09:00"]),
            "shipped": pd.to_datetime(["2025-01-02 08:00", None]),
        }
    )
    log = to_event_log(
        wide, "order_id", {"ordered": "Order Received", "shipped": "Ship"}, extra=("site",)
    )
    # The missing milestone is not an event, so B has one event and not a null one.
    assert len(log) == 3
    assert list(log.loc[log["case_id"] == "B", "activity"]) == ["Order Received"]
    assert "site" in log.columns
    # And the reshape cannot invent durations, which the profile then reports honestly.
    assert not profile_log(log).separates_work_from_wait


def test_reshape_guards() -> None:
    wide = pd.DataFrame({"order_id": ["A"], "ordered": pd.to_datetime(["2025-01-01"])})
    with pytest.raises(ValueError, match="at least one activity column"):
        to_event_log(wide, "order_id", {})
    with pytest.raises(KeyError, match="shipped"):
        to_event_log(wide, "order_id", {"shipped": "Ship"})
    with pytest.raises(KeyError, match="site"):
        to_event_log(wide, "order_id", {"ordered": "Order Received"}, extra=("site",))
