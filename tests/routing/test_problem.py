"""Problem construction, diagnosis and bounds."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.routing import (
    DeliveryProblem,
    VehicleType,
    build_problem,
    diagnose,
    fleet_lower_bounds,
    one_day,
)

from .conftest import stop


def test_the_depot_is_node_zero(single_stop: DeliveryProblem) -> None:
    assert single_stop.distance_km.shape == (2, 2)
    assert single_stop.distance_km[0, 0] == 0.0
    assert single_stop.distance_km[0, 1] == pytest.approx(10.0)


def test_circuity_scales_straight_line_distance() -> None:
    frame = pd.DataFrame([stop(3.0, 4.0)])  # hypotenuse 5
    plain = build_problem(frame, circuity=1.0)
    padded = build_problem(frame, circuity=1.4)
    assert plain.distance_km[0, 1] == pytest.approx(5.0)
    assert padded.distance_km[0, 1] == pytest.approx(7.0)


def test_the_matrix_is_symmetric_with_a_zero_diagonal(four_corners: DeliveryProblem) -> None:
    matrix = four_corners.distance_km
    assert np.allclose(matrix, matrix.T)
    assert np.allclose(np.diag(matrix), 0.0)


def test_travel_time_follows_from_distance_and_speed() -> None:
    problem = build_problem(pd.DataFrame([stop(30.0, 0.0)]), circuity=1.0, speed_kmh=60.0)
    assert problem.travel_min[0, 1] == pytest.approx(30.0), "30 km at 60 km/h is half an hour"


def test_open_windows_replaces_every_window() -> None:
    frame = pd.DataFrame([stop(5.0, 0.0, window=(8.0, 10.0))])
    problem = build_problem(frame, open_windows=True, day_start_h=8.0, day_end_h=18.0)
    assert problem.stops.iloc[0]["window_start_h"] == 8.0
    assert problem.stops.iloc[0]["window_end_h"] == 18.0


def test_a_window_outside_the_working_day_is_refused() -> None:
    frame = pd.DataFrame([stop(5.0, 0.0, window=(6.0, 10.0))])
    with pytest.raises(ValueError, match="outside the working day"):
        build_problem(frame, day_start_h=8.0, day_end_h=18.0)


@pytest.mark.parametrize("missing", ["x_km", "weight_kg", "service_min", "window_start_h"])
def test_missing_columns_are_reported(missing: str) -> None:
    frame = pd.DataFrame([stop(1.0, 1.0)]).drop(columns=[missing])
    with pytest.raises(KeyError, match=missing):
        build_problem(frame)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"speed_kmh": 0.0}, "speed_kmh must be positive"),
        ({"circuity": 0.5}, "circuity at least 1"),
        ({"day_end_h": 8.0}, "day_end_h must be after"),
    ],
)
def test_build_problem_validates_its_arguments(kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        build_problem(pd.DataFrame([stop(1.0, 1.0)]), **kwargs)


def test_an_empty_frame_is_refused() -> None:
    frame = pd.DataFrame([stop(1.0, 1.0)]).iloc[:0]
    with pytest.raises(ValueError, match="deliveries is empty"):
        build_problem(frame)


def test_the_profile_describes_the_problem_before_solving(four_corners: DeliveryProblem) -> None:
    profile = four_corners.profile()
    assert profile["stops"] == 4
    assert profile["weight_kg"] == pytest.approx(40.0)
    assert profile["service_h"] == pytest.approx(40.0 / 60.0)
    assert profile["median_radius_km"] == pytest.approx(10.0)
    assert profile["windowed_share"] == pytest.approx(0.0)


def test_the_profile_counts_constrained_windows() -> None:
    frame = pd.DataFrame([stop(5.0, 0.0, window=(8.0, 12.0)), stop(-5.0, 0.0, window=(8.0, 18.0))])
    assert build_problem(frame).profile()["windowed_share"] == pytest.approx(0.5)


def test_diagnose_finds_nothing_wrong_with_a_tractable_day(
    four_corners: DeliveryProblem,
) -> None:
    vehicle = VehicleType("test", capacity_kg=1000.0, fixed_cost=100.0, cost_per_km=2.0)
    assert diagnose(four_corners, vehicle).empty


def test_diagnose_flags_a_stop_beyond_the_driver_shift() -> None:
    # 400 km each way at 60 km/h is over 13 hours of driving on a 9 hour shift.
    problem = build_problem(pd.DataFrame([stop(400.0, 0.0)]), circuity=1.0, speed_kmh=60.0)
    vehicle = VehicleType("test", capacity_kg=1000.0, fixed_cost=100.0, cost_per_km=2.0)
    reasons = diagnose(problem, vehicle)
    assert len(reasons) == 1
    assert "driver shift" in reasons.iloc[0]["reason"]


def test_diagnose_flags_a_stop_that_cannot_make_its_window() -> None:
    # 180 km at 60 km/h is three hours, and the window closes two hours in.
    frame = pd.DataFrame([stop(180.0, 0.0, window=(8.0, 10.0))])
    problem = build_problem(frame, circuity=1.0, speed_kmh=60.0)
    vehicle = VehicleType("test", capacity_kg=1000.0, fixed_cost=100.0, cost_per_km=2.0)
    reasons = diagnose(problem, vehicle)
    assert len(reasons) == 1
    assert "window closes" in reasons.iloc[0]["reason"]


def test_diagnose_flags_an_overweight_stop(single_stop: DeliveryProblem) -> None:
    tiny = VehicleType("tiny", capacity_kg=5.0, fixed_cost=10.0, cost_per_km=1.0)
    reasons = diagnose(single_stop, tiny)
    assert "exceeds vehicle capacity" in reasons.iloc[0]["reason"]


def test_lower_bounds_use_only_quantities_that_cannot_be_shared(
    four_corners: DeliveryProblem,
) -> None:
    """Weight and service time are valid bounds; a travel-based one would not be.

    Four stops of 10 kg against a 25 kg vehicle needs two vehicles by weight. Forty minutes of
    service against a 30-minute shift needs two by time.
    """
    vehicle = VehicleType(
        "test", capacity_kg=25.0, fixed_cost=100.0, cost_per_km=2.0, max_duration_h=0.5
    )
    bounds = fleet_lower_bounds(four_corners, vehicle)

    assert bounds["by_weight"] == 2.0
    assert bounds["by_service_time"] == 2.0
    assert set(bounds.index) == {"by_weight", "by_service_time", "binding"}
    assert "by_radial_travel" not in bounds.index


def test_one_day_selects_a_site_and_a_date(dataset) -> None:  # type: ignore[no-untyped-def]
    deliveries = dataset.deliveries
    site = str(deliveries.iloc[0]["site"])
    date = pd.Timestamp(deliveries.iloc[0]["order_date"])
    problem = one_day(deliveries, site, str(date.date()))

    assert problem.n_stops > 0
    expected = deliveries.loc[
        (deliveries["site"].astype(str) == site)
        & (pd.to_datetime(deliveries["order_date"]) == date)
    ]
    assert problem.n_stops == len(expected)


def test_one_day_reports_an_empty_selection(dataset) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError, match="no deliveries for site"):
        one_day(dataset.deliveries, "CD-XX", "2025-06-11")


def test_one_day_can_cap_the_problem_size(dataset) -> None:  # type: ignore[no-untyped-def]
    deliveries = dataset.deliveries
    site = str(deliveries.iloc[0]["site"])
    date = str(pd.Timestamp(deliveries.iloc[0]["order_date"]).date())
    capped = one_day(deliveries, site, date, limit=3)
    assert capped.n_stops <= 3
