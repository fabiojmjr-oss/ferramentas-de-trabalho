"""The event log, and the path variation that makes discovery worth running."""

from __future__ import annotations

import numpy as np
import pandas as pd

from oplab.synth import (
    HAPPY_PATH,
    VALUE_ADDING,
    SynthConfig,
    generate_catalog,
    generate_demand,
    generate_order_events,
    generate_order_lines,
)


def log() -> pd.DataFrame:
    cfg = SynthConfig(days=60, n_skus=40)
    rng = np.random.default_rng(cfg.seed)
    catalog = generate_catalog(cfg, rng)
    demand = generate_demand(cfg, catalog, rng)
    lines = generate_order_lines(cfg, demand, rng)
    return generate_order_events(cfg, lines, rng)


def test_every_case_starts_at_the_start_and_ends_at_an_end() -> None:
    frame = log()
    grouped = frame.groupby("case_id", observed=True)["activity"]
    assert (grouped.first() == "Order Received").all()
    assert grouped.last().isin(["Deliver", "Cancel Order"]).all()


def test_events_are_ordered_and_have_a_positive_duration() -> None:
    frame = log()
    assert (frame["complete_ts"] >= frame["start_ts"]).all()
    # The log records a start and a completion per event, which is what makes work separable
    # from wait. A log with one timestamp per step cannot support a flow-efficiency figure.
    assert (frame["complete_ts"] > frame["start_ts"]).all()
    ordered = frame.sort_values(["case_id", "position"])
    assert ordered.equals(frame)
    within = ordered.groupby("case_id", observed=True)["start_ts"]
    assert (within.diff().dropna() >= pd.Timedelta(0)).all()


def test_the_documented_path_is_a_minority_of_the_variants_and_a_majority_of_the_cases() -> None:
    """Both halves matter: a process with one variant proves nothing, and one whose top path is
    rare cannot be standardised."""
    frame = log()
    paths = frame.groupby("case_id", observed=True)["activity"].apply(tuple)
    assert paths.nunique() > 10
    shares = paths.value_counts(normalize=True)
    assert shares.index[0] == tuple(HAPPY_PATH)
    assert 0.4 < shares.iloc[0] < 0.8


def test_the_undocumented_activities_are_all_present_and_all_a_minority() -> None:
    frame = log()
    counts = frame["activity"].value_counts()
    for activity in (
        "Credit Hold",
        "Stock Shortage",
        "Repack",
        "Address Correction",
        "Delivery Failed",
        "Cancel Order",
    ):
        assert activity in counts.index, activity
        assert counts[activity] < counts["Order Received"] * 0.25, activity


def test_rework_loops_return_to_the_activity_they_came_from() -> None:
    """A loop that does not return is a branch; the distinction is what rework means."""
    frame = log()
    paths = frame.groupby("case_id", observed=True)["activity"].apply(list)
    with_repack = [p for p in paths if "Repack" in p]
    assert with_repack
    for path in with_repack:
        index = path.index("Repack")
        assert path[index - 1] == "Quality Check"
        assert path[index + 1] == "Quality Check"

    with_shortage = [p for p in paths if "Stock Shortage" in p]
    assert with_shortage
    for path in with_shortage:
        index = path.index("Stock Shortage")
        assert path[index - 1] == "Allocate Stock"
        assert path[index + 1] == "Allocate Stock"


def test_a_cancelled_case_stops_and_does_not_ship() -> None:
    frame = log()
    paths = frame.groupby("case_id", observed=True)["activity"].apply(list)
    cancelled = [p for p in paths if "Cancel Order" in p]
    assert cancelled
    for path in cancelled:
        assert path[-1] == "Cancel Order"
        assert "Ship" not in path and "Deliver" not in path


def test_inspection_is_not_counted_as_value_adding() -> None:
    """The value-adding set decides the flow-efficiency answer, so it is asserted here."""
    assert "Quality Check" not in VALUE_ADDING
    assert "Repack" not in VALUE_ADDING
    assert "Credit Check" not in VALUE_ADDING
    assert set(VALUE_ADDING) < set(HAPPY_PATH)


def test_waiting_dominates_working_time() -> None:
    """If it did not, the generator would be describing a process nobody has."""
    frame = log()
    frame = frame.sort_values(["case_id", "position"])
    work = (frame["complete_ts"] - frame["start_ts"]).dt.total_seconds().sum()
    spans = frame.groupby("case_id", observed=True).agg(
        start=("start_ts", "min"), end=("complete_ts", "max")
    )
    lead = (spans["end"] - spans["start"]).dt.total_seconds().sum()
    assert work / lead < 0.2


def test_the_log_is_reproducible_from_the_seed() -> None:
    assert log().equals(log())
