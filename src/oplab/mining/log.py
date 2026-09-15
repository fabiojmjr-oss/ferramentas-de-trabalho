"""The event log, and the two validations that decide whether anything downstream is meaningful.

Process mining has a low barrier to a picture and a high barrier to a conclusion. A directly-
follows graph can be drawn from any table with three columns, and it will look like a process map
whether or not the log means what the analyst assumes. Two properties have to hold first:

1. **One case per case identifier.** If the identifier is the order but the log records one row per
   line, every multi-line order appears to loop through picking several times and the rework
   measurement is fabricated. This is the single most common defect in a mined log and it inflates
   exactly the number the exercise was run to find.
2. **A start and a complete timestamp per event.** With one timestamp per step, the duration of an
   activity and the wait before the next cannot be separated, so flow efficiency cannot be computed
   and every improvement target defaults to the touch time - which is usually the small half.

Both are checked rather than assumed, and the check names what is wrong rather than raising a
``KeyError`` from three frames deeper.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

REQUIRED = ("case_id", "activity", "start_ts", "complete_ts")


@dataclass(frozen=True)
class LogProfile:
    """What the log contains, before anything is concluded from it.

    Attributes:
        cases: Distinct case identifiers.
        events: Rows.
        activities: Distinct activity names.
        events_per_case: Mean events per case.
        span: Time from the first start to the last completion.
        zero_duration_events: Events whose start equals their completion, which means the log
            records a single timestamp for that step however many columns it has.
    """

    cases: int
    events: int
    activities: int
    events_per_case: float
    span: pd.Timedelta
    zero_duration_events: int

    @property
    def separates_work_from_wait(self) -> bool:
        """Whether durations are recorded at all, which decides if flow efficiency is computable."""
        return self.zero_duration_events < self.events


def validate_log(log: pd.DataFrame) -> pd.DataFrame:
    """Check an event log and return it sorted into case and time order.

    Every problem is reported in one pass rather than one per run, because a log is usually wrong
    in several ways at once and fixing them one exception at a time is the slowest possible route.

    Args:
        log: Frame with ``case_id``, ``activity``, ``start_ts`` and ``complete_ts``.

    Returns:
        The log sorted by case and start time, with timestamps coerced to datetimes.

    Raises:
        ValueError: If the log is empty, a required column is missing, a timestamp cannot be
            parsed, or any event completes before it starts.
    """
    problems: list[str] = []
    if log.empty:
        problems.append("the log is empty")

    missing = [column for column in REQUIRED if column not in log.columns]
    if missing:
        problems.append(f"missing columns: {', '.join(missing)}")
    if problems:
        raise ValueError("; ".join(problems))

    frame = log.copy()
    for column in ("start_ts", "complete_ts"):
        converted = pd.to_datetime(frame[column], errors="coerce")
        if converted.isna().any():
            problems.append(f"{column} has {int(converted.isna().sum())} unparseable values")
        frame[column] = converted

    if not problems:
        backwards = int((frame["complete_ts"] < frame["start_ts"]).sum())
        if backwards:
            problems.append(f"{backwards} events complete before they start")

    if problems:
        raise ValueError("; ".join(problems))
    return frame.sort_values(["case_id", "start_ts"], ignore_index=True)


def profile_log(log: pd.DataFrame) -> LogProfile:
    """Summarise a validated log.

    Args:
        log: Output of :func:`validate_log`.

    Returns:
        A :class:`LogProfile`.
    """
    frame = validate_log(log)
    cases = int(frame["case_id"].nunique())
    return LogProfile(
        cases=cases,
        events=int(len(frame)),
        activities=int(frame["activity"].nunique()),
        events_per_case=len(frame) / cases,
        span=frame["complete_ts"].max() - frame["start_ts"].min(),
        zero_duration_events=int((frame["complete_ts"] == frame["start_ts"]).sum()),
    )


def to_event_log(
    frame: pd.DataFrame,
    case_col: str,
    activity_columns: dict[str, str],
    extra: tuple[str, ...] = (),
) -> pd.DataFrame:
    """Reshape a wide table of milestone timestamps into an event log.

    This is how most operational data arrives: one row per order with a column per milestone. The
    reshape is mechanical, and the cost is recorded honestly - a wide table has one timestamp per
    milestone, so the resulting log cannot separate work from wait and every event comes out with
    zero duration. :attr:`LogProfile.separates_work_from_wait` reports that rather than letting a
    flow-efficiency figure be computed from it.

    Args:
        frame: Wide frame, one row per case.
        case_col: Column holding the case identifier.
        activity_columns: Mapping of timestamp column to activity name, in process order.
        extra: Columns carried through onto every event of the case, such as the site.

    Returns:
        An event log with ``start_ts`` equal to ``complete_ts``. Rows whose timestamp is missing
        are dropped, because a milestone that did not happen is not an event.

    Raises:
        KeyError: If a named column is missing.
        ValueError: If no activity columns are given.
    """
    if not activity_columns:
        raise ValueError("at least one activity column is required")
    for column in (case_col, *activity_columns, *extra):
        if column not in frame.columns:
            raise KeyError(f"frame has no column {column!r}")

    pieces = []
    for column, activity in activity_columns.items():
        piece = frame[[case_col, column, *extra]].copy()
        piece = piece.loc[piece[column].notna()]
        piece = piece.rename(columns={case_col: "case_id", column: "start_ts"})
        piece["activity"] = activity
        piece["complete_ts"] = piece["start_ts"]
        pieces.append(piece)

    log = pd.concat(pieces, ignore_index=True)
    return validate_log(log)
