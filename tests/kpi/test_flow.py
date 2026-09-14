"""Flow indicator behaviour."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.kpi import appointment_adherence, dock_to_stock, duration_profile, order_cycle_time


def test_duration_profile_reports_hand_computed_statistics() -> None:
    hours = pd.Series([1.0, 2.0, 3.0, 4.0, np.nan])
    profile = duration_profile(hours, quantiles=(0.5,))
    row = profile.iloc[0]
    assert row["n"] == 4
    assert row["n_missing"] == 1
    assert row["mean"] == pytest.approx(2.5)
    assert row["p50"] == pytest.approx(2.5)


def test_duration_profile_rejects_out_of_range_quantiles() -> None:
    with pytest.raises(ValueError, match="strictly between 0 and 1"):
        duration_profile(pd.Series([1.0]), quantiles=(1.0,))


def test_duration_profile_groups_by_key() -> None:
    hours = pd.Series([1.0, 3.0, 10.0, 20.0])
    keys = pd.Series(["a", "a", "b", "b"], name="site")
    profile = duration_profile(hours, by=keys, quantiles=(0.5,)).set_index("site")
    assert profile.loc["a", "mean"] == pytest.approx(2.0)
    assert profile.loc["b", "mean"] == pytest.approx(15.0)


def test_dock_to_stock_stages_sum_to_the_total(dataset) -> None:  # type: ignore[no-untyped-def]
    profile = dock_to_stock(dataset.receipts, by=None).set_index("stage")
    parts = profile.loc[["dock_wait_h", "unload_h", "putaway_h"], "mean"].sum()
    assert parts == pytest.approx(profile.loc["dock_to_stock_h", "mean"], rel=1e-9)


def test_dock_to_stock_reports_every_stage_per_site(dataset) -> None:  # type: ignore[no-untyped-def]
    profile = dock_to_stock(dataset.receipts)
    assert set(profile["stage"]) == {"dock_wait_h", "unload_h", "putaway_h", "dock_to_stock_h"}
    assert profile["n_missing"].sum() == 0


def test_order_cycle_time_counts_undelivered_lines_as_missing(dataset) -> None:  # type: ignore[no-untyped-def]
    profile = order_cycle_time(dataset.order_lines).set_index("stage")
    undelivered = int(dataset.order_lines["delivered_ts"].isna().sum())
    assert profile.loc["total_h", "n_missing"] == undelivered
    assert profile.loc["total_h", "mean"] > profile.loc["transit_h", "mean"]


def test_appointment_adherence_separates_early_from_on_time() -> None:
    appointment = pd.Timestamp("2025-01-01 08:00")
    receipts = pd.DataFrame(
        {
            "receipt_id": ["r1", "r2", "r3"],
            "site": "CD-SP",
            "carrier": ["X", "X", "X"],
            "appointment_ts": appointment,
            "arrival_ts": [
                appointment - pd.Timedelta(hours=3),  # early
                appointment + pd.Timedelta(minutes=5),  # on time
                appointment + pd.Timedelta(hours=4),  # late
            ],
            "unload_start_ts": appointment,
            "unload_end_ts": appointment,
            "putaway_end_ts": appointment,
        }
    )
    result = appointment_adherence(receipts, by="carrier").iloc[0]
    assert result["early"] == pytest.approx(1 / 3)
    assert result["on_time"] == pytest.approx(1 / 3)
    assert result["late"] == pytest.approx(1 / 3)


def test_carrier_ranking_discriminates_on_the_generated_data(dataset) -> None:  # type: ignore[no-untyped-def]
    result = appointment_adherence(dataset.receipts)
    spread = result["on_time"].max() - result["on_time"].min()
    assert spread > 0.2, "a carrier indicator that ranks every carrier alike measures nothing"
