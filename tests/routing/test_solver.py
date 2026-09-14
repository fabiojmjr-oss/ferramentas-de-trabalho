"""Solving, and the three experiments.

Every solve here uses a one or two second limit on a handful of stops, so the results are
stable enough to assert without making the suite slow. The exact-arithmetic cases use a
circuity of one and a round speed, so the expected cost can be worked out on paper.
"""

from __future__ import annotations

import math

import pandas as pd
import pytest

from oplab.routing import (
    TRUCK,
    VAN,
    DeliveryProblem,
    VehicleType,
    build_problem,
    compare_fleets,
    density_curve,
    quality_curve,
    solve,
    window_cost,
)

from .conftest import stop

EXACT = VehicleType("exact", capacity_kg=1000.0, fixed_cost=100.0, cost_per_km=2.0)


def test_a_single_stop_costs_exactly_the_hand_calculation(
    single_stop: DeliveryProblem,
) -> None:
    """Ten kilometres out and back at 2.00 per km, plus 100.00 to put the van on the road."""
    solution = solve(single_stop, EXACT, solution_limit=20)

    assert solution.feasible
    assert solution.vehicles_used == 1
    assert solution.stops_served == 1
    assert solution.total_km == pytest.approx(20.0)
    assert solution.total_cost == pytest.approx(100.0 + 20.0 * 2.0)
    assert solution.cost_per_delivery == pytest.approx(140.0)


def test_the_fixed_cost_stops_the_solver_using_every_vehicle(
    four_corners: DeliveryProblem,
) -> None:
    """One van driving the diamond beats four vans each driving out and back.

    Four separate round trips cost 4 x (100 + 40) = 560. One vehicle going round the four axis
    points travels 10 + 3 x sqrt(200) + 10 = 62.43 km, for 100 + 124.85 = 224.85. A solver
    given a distance objective would be indifferent between one van and four; with a fixed
    cost per vehicle it is not.
    """
    solution = solve(four_corners, EXACT, solution_limit=40)

    diamond_km = 10.0 + 3.0 * math.sqrt(200.0) + 10.0

    assert solution.feasible
    assert solution.vehicles_used == 1
    assert solution.total_km == pytest.approx(diamond_km)
    assert solution.total_cost == pytest.approx(100.0 + diamond_km * 2.0)
    assert solution.total_cost < 4 * (100.0 + 40.0)


def test_capacity_forces_a_second_vehicle(four_corners: DeliveryProblem) -> None:
    small = VehicleType("small", capacity_kg=25.0, fixed_cost=100.0, cost_per_km=2.0)
    solution = solve(four_corners, small, solution_limit=40)

    assert solution.feasible
    assert solution.vehicles_used >= 2, "40 kg cannot ride in a 25 kg vehicle"
    assert (solution.summary["load_kg"] <= small.capacity_kg + 1e-9).all()


def test_every_route_respects_the_capacity_and_the_shift(
    four_corners: DeliveryProblem,
) -> None:
    solution = solve(four_corners, EXACT, solution_limit=40)
    assert (solution.summary["load_kg"] <= EXACT.capacity_kg + 1e-9).all()
    assert (solution.summary["duration_h"] <= EXACT.max_duration_h + 1e-9).all()


def test_every_stop_is_visited_exactly_once(four_corners: DeliveryProblem) -> None:
    solution = solve(four_corners, EXACT, solution_limit=40)
    visited = [position for route in solution.routes for position in route]
    assert sorted(visited) == list(range(four_corners.n_stops))


def test_an_impossible_day_is_reported_infeasible_not_solved() -> None:
    """One vehicle cannot serve two stops whose windows are both the same single hour 200 km
    apart in opposite directions."""
    frame = pd.DataFrame(
        [
            stop(200.0, 0.0, window=(8.0, 9.0)),
            stop(-200.0, 0.0, window=(8.0, 9.0)),
        ]
    )
    problem = build_problem(frame, circuity=1.0, speed_kmh=60.0)
    vehicle = VehicleType("one", capacity_kg=1000.0, fixed_cost=100.0, cost_per_km=2.0, count=1)
    solution = solve(problem, vehicle, solution_limit=40)

    assert not solution.feasible
    assert solution.stops_served == 0
    assert solution.total_cost == 0.0
    assert solution.headline()["feasible"] == 0.0


def test_the_search_budget_is_carried_in_the_result(four_corners: DeliveryProblem) -> None:
    solution = solve(four_corners, EXACT, solution_limit=60)
    assert solution.solution_limit == 60
    assert solution.headline()["solution_limit"] == 60.0
    assert not solution.hit_time_cap


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"solution_limit": 0}, "solution_limit must be at least 1"),
        ({"time_cap_s": 0}, "time_cap_s must be at least 1"),
    ],
)
def test_a_non_positive_budget_is_refused(
    four_corners: DeliveryProblem, kwargs: dict[str, int], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        solve(four_corners, EXACT, **kwargs)  # type: ignore[arg-type]


def test_the_same_budget_gives_the_same_plan_regardless_of_speed(
    four_corners: DeliveryProblem,
) -> None:
    """A solution-count budget is reproducible; a wall-clock one is not.

    This is why the budget is a solution count. Under CPU contention a wall-clock limit
    explores less and returns a different plan, which showed up here as a test that passed
    alone and failed inside the full suite - and which would be unacceptable in a figure that
    goes into a tender.
    """
    plans = [solve(four_corners, EXACT, solution_limit=40) for _ in range(3)]
    assert len({tuple(tuple(route) for route in plan.routes) for plan in plans}) == 1
    assert len({round(plan.total_cost, 6) for plan in plans}) == 1


def test_the_solve_is_reproducible(four_corners: DeliveryProblem) -> None:
    first = solve(four_corners, EXACT, solution_limit=40)
    second = solve(four_corners, EXACT, solution_limit=40)
    assert first.total_cost == pytest.approx(second.total_cost)
    assert first.routes == second.routes


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"capacity_kg": 0.0}, "capacity_kg must be positive"),
        ({"fixed_cost": -1.0}, "costs cannot be negative"),
        ({"cost_per_km": -1.0}, "costs cannot be negative"),
        ({"max_duration_h": 0.0}, "max_duration_h must be positive"),
        ({"count": 0}, "count must be at least 1"),
    ],
)
def test_vehicle_validation(kwargs: dict[str, float], message: str) -> None:
    defaults = {"name": "v", "capacity_kg": 100.0, "fixed_cost": 10.0, "cost_per_km": 1.0}
    with pytest.raises(ValueError, match=message):
        VehicleType(**{**defaults, **kwargs})  # type: ignore[arg-type]


def test_the_vehicle_bound_is_generous_enough_to_avoid_false_infeasibility(
    four_corners: DeliveryProblem,
) -> None:
    """A bound built from service time alone once made a feasible day look infeasible.

    Travel dominates on a wide territory, and no cheap bound captures it, so the offered count
    errs high. Offering too many costs search time; offering too few changes the answer.
    """
    offered = EXACT.available(four_corners)
    assert offered >= 2
    assert offered <= four_corners.n_stops


def test_quality_curve_shows_what_the_search_left_on_the_table(
    four_corners: DeliveryProblem,
) -> None:
    table = quality_curve(four_corners, EXACT, (20, 40))
    assert list(table["solution_limit"]) == [20, 40]
    assert (table["total_cost"].diff().dropna() <= 1e-6).all(), "a bigger budget cannot cost more"
    assert table["improvement_vs_cheapest"].iloc[0] == pytest.approx(0.0)
    assert not table["hit_time_cap"].any()


def test_quality_curve_needs_a_limit(four_corners: DeliveryProblem) -> None:
    with pytest.raises(ValueError, match="at least one solution limit"):
        quality_curve(four_corners, EXACT, ())


def test_density_lowers_cost_per_delivery_in_the_same_territory() -> None:
    """Twelve stops in a ring cost less each than four stops in the same ring.

    Same area, more customers. This is the economics of last-mile distribution, and it runs
    against the intuition of anyone reasoning in kilometres.
    """
    import numpy as np

    angles = np.linspace(0.0, 2.0 * np.pi, 12, endpoint=False)
    frame = pd.DataFrame([stop(float(20 * np.cos(a)), float(20 * np.sin(a))) for a in angles])
    problem = build_problem(frame, circuity=1.0, speed_kmh=60.0)

    table = density_curve(problem, EXACT, shares=(1 / 3, 1.0), solution_limit=40)
    assert table["cost_per_delivery"].is_monotonic_decreasing
    assert table["stops"].iloc[0] == 4
    assert table["stops"].iloc[-1] == 12


def test_density_curve_validates_its_shares(four_corners: DeliveryProblem) -> None:
    with pytest.raises(ValueError, match=r"shares must be in \(0, 1\]"):
        density_curve(four_corners, EXACT, shares=(0.0, 1.5))


def test_windows_cost_something_and_the_premium_is_measured() -> None:
    """Splitting the same stops into opposing half-day windows must not be free."""
    frame = pd.DataFrame(
        [
            stop(30.0, 0.0, window=(8.0, 12.0)),
            stop(-30.0, 0.0, window=(13.0, 18.0)),
            stop(0.0, 30.0, window=(8.0, 12.0)),
            stop(0.0, -30.0, window=(13.0, 18.0)),
        ]
    )
    problem = build_problem(frame, circuity=1.0, speed_kmh=60.0)
    table = window_cost(problem, EXACT, solution_limit=40).set_index("case")

    assert (
        table.loc["windows enforced", "cost_per_delivery"]
        >= table.loc["windows opened", "cost_per_delivery"]
    )
    assert table.loc["windows opened", "premium_vs_open"] == pytest.approx(0.0)
    assert table.loc["windows enforced", "premium_vs_open"] >= 0.0


def test_compare_fleets_puts_make_and_buy_in_one_table(
    four_corners: DeliveryProblem,
) -> None:
    table = compare_fleets(
        four_corners,
        {"van": VAN, "truck": TRUCK},
        solution_limit=40,
        third_party_price_per_delivery=50.0,
    )
    assert set(table["option"]) == {"van", "truck", "third party"}
    assert table["cost_per_delivery"].is_monotonic_increasing, "cheapest first"

    third_party = table.loc[table["option"] == "third party"].iloc[0]
    assert third_party["total_cost"] == pytest.approx(50.0 * four_corners.n_stops)


def test_compare_fleets_validates_its_arguments(four_corners: DeliveryProblem) -> None:
    with pytest.raises(ValueError, match="at least one fleet"):
        compare_fleets(four_corners, {}, solution_limit=20)
    with pytest.raises(ValueError, match="cannot be negative"):
        compare_fleets(
            four_corners, {"van": VAN}, solution_limit=20, third_party_price_per_delivery=-1.0
        )
