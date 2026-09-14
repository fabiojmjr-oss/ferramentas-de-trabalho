"""Synthetic dataset guarantees.

Reproducibility is the load-bearing property of this module: every figure quoted in the
documentation depends on the same seed producing the same tables.
"""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.synth import SpecialCause, SynthConfig, abc_classes, generate_dataset, generate_subgroups

TINY = SynthConfig(days=35, n_skus=25)


def test_the_same_seed_reproduces_the_same_tables() -> None:
    first = generate_dataset(TINY)
    second = generate_dataset(TINY)
    for name, frame in first.tables.items():
        pd.testing.assert_frame_equal(frame, second.tables[name])


def test_a_different_seed_changes_the_data() -> None:
    other = generate_dataset(SynthConfig(days=35, n_skus=25, seed=7))
    base = generate_dataset(TINY)
    assert not base.order_lines["qty_ordered"].equals(other.order_lines["qty_ordered"])


def test_every_table_is_populated(dataset) -> None:  # type: ignore[no-untyped-def]
    summary = dataset.summary().set_index("table")
    assert (summary["rows"] > 0).all()
    assert set(summary.index) == {
        "catalog",
        "demand",
        "order_lines",
        "receipts",
        "cycle_counts",
        "subgroups",
    }


def test_quantities_are_never_negative(dataset) -> None:  # type: ignore[no-untyped-def]
    for column in ("qty_ordered", "qty_shipped", "qty_delivered"):
        assert (dataset.order_lines[column] >= 0).all()
    assert (dataset.order_lines["qty_delivered"] <= dataset.order_lines["qty_shipped"]).all()
    assert (dataset.order_lines["qty_shipped"] <= dataset.order_lines["qty_ordered"]).all()


def test_event_timestamps_are_ordered(dataset) -> None:  # type: ignore[no-untyped-def]
    lines = dataset.order_lines.dropna(subset=["delivered_ts"])
    assert (lines["ship_ts"] >= lines["order_ts"]).all()
    assert (lines["delivered_ts"] >= lines["ship_ts"]).all()

    receipts = dataset.receipts
    assert (receipts["unload_start_ts"] >= receipts["arrival_ts"]).all()
    assert (receipts["unload_end_ts"] >= receipts["unload_start_ts"]).all()
    assert (receipts["putaway_end_ts"] >= receipts["unload_end_ts"]).all()


def test_lines_of_an_order_share_one_shipment(dataset) -> None:  # type: ignore[no-untyped-def]
    shipped = dataset.order_lines.dropna(subset=["ship_ts"])
    per_order = shipped.groupby("order_id")["ship_ts"].nunique()
    assert (per_order == 1).all(), "an order leaves the dock as a single shipment"


def test_censored_orders_exist_and_carry_no_delivery(dataset) -> None:  # type: ignore[no-untyped-def]
    lines = dataset.order_lines
    in_transit = lines.loc[lines["status"] == "in_transit"]
    assert len(in_transit) > 0, "the horizon must end mid-flight to exercise censoring"
    assert in_transit["delivered_ts"].isna().all()
    assert lines.loc[lines["status"] == "cancelled", "qty_shipped"].eq(0).all()


def test_demand_shows_weekly_seasonality(dataset) -> None:  # type: ignore[no-untyped-def]
    by_weekday = dataset.demand.groupby(
        pd.to_datetime(dataset.demand["date"]).dt.dayofweek, observed=True
    )["demand"].sum()
    assert by_weekday.idxmax() < 5, "the peak must fall on a working day"
    assert by_weekday.min() < 0.3 * by_weekday.max(), "the weekend trough must be visible"


def test_catalogue_demand_is_long_tailed(dataset) -> None:  # type: ignore[no-untyped-def]
    volume = (
        dataset.demand.groupby("sku", observed=True)["demand"].sum().sort_values(ascending=False)
    )
    top_fifth = volume.head(max(1, len(volume) // 5)).sum() / volume.sum()
    assert top_fifth > 0.5, "a realistic assortment concentrates volume in the fast movers"


def test_abc_classes_follow_the_cumulative_cuts() -> None:
    catalog = pd.DataFrame({"annual_value": [100.0, 50.0, 20.0, 5.0, 1.0]})
    classes = abc_classes(catalog)
    assert classes.iloc[0] == "A"
    assert classes.iloc[-1] == "C"
    assert set(classes) <= {"A", "B", "C"}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"annual_value": [0.0, 0.0]}, "positive value"),
    ],
)
def test_abc_classes_reject_a_degenerate_column(
    kwargs: dict[str, list[float]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        abc_classes(pd.DataFrame(kwargs))


def test_abc_classes_report_a_missing_column() -> None:
    with pytest.raises(KeyError, match="annual_value"):
        abc_classes(pd.DataFrame({"other": [1.0]}))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"days": 10}, "days must be at least 28"),
        ({"n_skus": 0}, "n_skus must be positive"),
        ({"sites": ()}, "at least one site profile"),
        ({"intermittent_share": 1.5}, "intermittent_share"),
    ],
)
def test_config_validates_its_arguments(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SynthConfig(**kwargs)  # type: ignore[arg-type]


def test_subgroups_place_the_special_cause_where_requested() -> None:
    import numpy as np

    rng = np.random.default_rng(1)
    frame = generate_subgroups(
        rng, n_subgroups=20, subgroup_size=4, causes=(SpecialCause(start=10, mean_shift_sigma=5.0),)
    )
    before = frame.loc[frame["subgroup"] <= 10, "value"].mean()
    after = frame.loc[frame["subgroup"] > 10, "value"].mean()
    assert after - before > 5.0


def test_subgroups_reject_a_cause_outside_the_series() -> None:
    import numpy as np

    with pytest.raises(ValueError, match="outside the series"):
        generate_subgroups(np.random.default_rng(1), n_subgroups=5, causes=(SpecialCause(start=9),))


def test_csv_export_writes_every_table(dataset, tmp_path) -> None:  # type: ignore[no-untyped-def]
    written = dataset.to_csv(tmp_path / "out")
    assert set(written) == set(dataset.tables)
    assert all(path.exists() and path.stat().st_size > 0 for path in written.values())
