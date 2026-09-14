"""Diagnosing a problem, and the three experiments worth running on it."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd

from .fleet import VehicleType
from .problem import DeliveryProblem, build_problem
from .solver import solve


def diagnose(problem: DeliveryProblem, vehicle: VehicleType) -> pd.DataFrame:
    """Find stops that no route can serve, before blaming the solver.

    An infeasible solve says nothing about why, and the reason is usually not the routing. A
    single stop whose round trip exceeds the driver shift, or that cannot be reached before its
    window closes, makes the whole day infeasible however good the algorithm is. Checking that
    first is the difference between "we need better routing" and "we need to renegotiate one
    delivery window".

    Args:
        problem: The day to check.
        vehicle: The fleet it would be routed with.

    Returns:
        One row per problematic stop with the reason. Empty when every stop is individually
        servable - in which case an infeasible solve is about the fleet as a whole, and the
        lower bounds in :func:`fleet_lower_bounds` are the place to look next.
    """
    travel_out = problem.travel_min[0, 1:]
    service = problem.stops["service_min"].to_numpy(dtype=float)
    window_close = (
        problem.stops["window_end_h"].to_numpy(dtype=float) - problem.day_start_h
    ) * 60.0
    window_open = (
        problem.stops["window_start_h"].to_numpy(dtype=float) - problem.day_start_h
    ) * 60.0

    round_trip = 2.0 * travel_out + service
    horizon = (problem.day_end_h - problem.day_start_h) * 60.0

    reasons: list[dict[str, object]] = []
    for position in range(problem.n_stops):
        problems = []
        if travel_out[position] > window_close[position] + 1e-9:
            problems.append("cannot arrive before the window closes")
        if round_trip[position] > vehicle.max_duration_h * 60.0 + 1e-9:
            problems.append("round trip exceeds the driver shift")
        if window_open[position] + service[position] + travel_out[position] > horizon + 1e-9:
            problems.append("cannot return within the working day")
        if problem.stops.iloc[position]["weight_kg"] > vehicle.capacity_kg + 1e-9:
            problems.append("weight exceeds vehicle capacity")
        if problems:
            reasons.append(
                {
                    "stop": position,
                    "distance_km": float(problem.distance_km[0, position + 1]),
                    "travel_min": float(travel_out[position]),
                    "window": f"{problem.stops.iloc[position]['window_start_h']:.0f}"
                    f"-{problem.stops.iloc[position]['window_end_h']:.0f}",
                    "weight_kg": float(problem.stops.iloc[position]["weight_kg"]),
                    "reason": "; ".join(problems),
                }
            )
    return pd.DataFrame(reasons)


def fleet_lower_bounds(problem: DeliveryProblem, vehicle: VehicleType) -> pd.Series:
    """Valid lower bounds on the fleet the day needs, and the gap routing has to close.

    Only two cheap bounds are actually valid, and both come from quantities that cannot be
    shared between vehicles: the payload has to be carried, and the time spent at the door has
    to be spent. The binding one names the lever - a day bounded by weight is a vehicle-size
    question, one bounded by service time is a shift or a headcount question.

    There is deliberately **no travel-based bound here**, and the reason is worth stating
    because it is an easy mistake to make. Summing the outbound leg to every stop and dividing
    by the shift is *not* a lower bound: it assumes each stop needs its own round trip, when a
    route visiting fifteen stops drives the radius once and amortises it across all of them.
    That figure came out at seven vehicles for a day this solver routes with five - a "lower
    bound" above the achieved solution, which is simply a wrong bound. The amount by which
    routing beats it is the density effect :func:`density_curve` measures.

    Returns:
        ``by_weight``, ``by_service_time`` and ``binding``. Expect the real fleet to exceed
        both, by whatever travel the territory imposes.
    """
    shift_min = vehicle.max_duration_h * 60.0
    bounds = {
        "by_weight": float(np.ceil(problem.total_weight_kg / vehicle.capacity_kg)),
        "by_service_time": float(np.ceil(problem.total_service_min / shift_min)),
    }
    binding = max(bounds, key=lambda key: bounds[key])
    return pd.Series({**bounds, "binding": binding})


def quality_curve(
    problem: DeliveryProblem,
    vehicle: VehicleType,
    solution_limits: Sequence[int] = (20, 60, 120, 300),
) -> pd.DataFrame:
    """Solve the same problem under increasing search budgets.

    The point is not to find the best budget. It is that a routing cost is a function of how
    hard the solver looked, that the search never proves optimality, and that a cost quoted
    without its budget is a cost quoted without its error bar. A tender decided on a cheap
    solve is a tender decided on an artefact - and the fleet size, not only the cost, moves
    with the budget.

    The budget is a solution count rather than a stopwatch so the curve is reproducible; see
    :mod:`oplab.routing.solver` for why a wall-clock limit is not.

    Returns:
        One row per budget with the cost, the distance, the vehicles used, the wall-clock time
        it happened to take, and the improvement against the smallest budget.
    """
    if not solution_limits:
        raise ValueError("at least one solution limit is required")

    rows = []
    for limit in sorted(solution_limits):
        solution = solve(problem, vehicle, solution_limit=limit)
        rows.append(
            {
                "solution_limit": limit,
                "feasible": solution.feasible,
                "vehicles_used": solution.vehicles_used,
                "total_km": solution.total_km,
                "total_cost": solution.total_cost,
                "cost_per_delivery": solution.cost_per_delivery,
                "elapsed_s": round(solution.elapsed_s, 2),
                "hit_time_cap": solution.hit_time_cap,
            }
        )

    table = pd.DataFrame(rows)
    baseline = table["total_cost"].iloc[0]
    table["improvement_vs_cheapest"] = table["total_cost"] / baseline - 1.0 if baseline else np.nan
    return table


def density_curve(
    problem: DeliveryProblem,
    vehicle: VehicleType,
    shares: Sequence[float] = (0.25, 0.5, 0.75, 1.0),
    solution_limit: int = 300,
    seed: int = 42,
) -> pd.DataFrame:
    """Route random subsets of the same territory, to isolate the effect of density.

    The stops are sampled from one day at one depot, so the **area does not change** - only how
    many customers there are in it. That is the experiment worth running, because cost per
    delivery in last-mile distribution is governed by drop density far more than by distance,
    and the intuition of anyone who thinks in kilometres runs the other way.

    Args:
        problem: The full day.
        vehicle: The fleet.
        shares: Fractions of the stops to route.
        solution_limit: Search budget per solve.
        seed: Sampling seed.

    Returns:
        One row per share with stops routed, cost per delivery, stops per vehicle and
        kilometres per delivery.
    """
    if any(not 0.0 < share <= 1.0 for share in shares):
        raise ValueError("shares must be in (0, 1]")

    rng = np.random.default_rng(seed)
    rows = []
    for share in sorted(shares):
        count = max(2, int(round(share * problem.n_stops)))
        chosen = rng.choice(problem.n_stops, size=count, replace=False)
        subset = build_problem(
            problem.stops.iloc[np.sort(chosen)],
            speed_kmh=problem.speed_kmh,
            circuity=problem.circuity,
            day_start_h=problem.day_start_h,
            day_end_h=problem.day_end_h,
        )
        solution = solve(subset, vehicle, solution_limit=solution_limit)
        rows.append(
            {
                "share": share,
                "stops": subset.n_stops,
                "feasible": solution.feasible,
                "vehicles_used": solution.vehicles_used,
                "stops_per_vehicle": solution.stops_per_vehicle,
                "km_per_delivery": solution.total_km / solution.stops_served
                if solution.stops_served
                else np.nan,
                "cost_per_delivery": solution.cost_per_delivery,
            }
        )
    return pd.DataFrame(rows)


def compare_fleets(
    problem: DeliveryProblem,
    fleets: dict[str, VehicleType],
    solution_limit: int = 300,
    third_party_price_per_delivery: float | None = None,
) -> pd.DataFrame:
    """Price the same day under several fleets, and optionally against an outsourced rate.

    Args:
        problem: The day to route.
        fleets: Named vehicle types.
        solution_limit: Search budget per solve.
        third_party_price_per_delivery: Optional per-delivery price for a carrier that needs no
            routing. Included as a row so the make-or-buy comparison sits in the same table
            rather than in a separate conversation.

    Returns:
        One row per option, cheapest first, with cost per delivery and the vehicles used.
    """
    if not fleets:
        raise ValueError("at least one fleet is required")

    rows = []
    for name, vehicle in fleets.items():
        solution = solve(problem, vehicle, solution_limit=solution_limit)
        rows.append(
            {
                "option": name,
                "feasible": solution.feasible,
                "vehicles_used": float(solution.vehicles_used),
                "total_km": solution.total_km,
                "total_cost": solution.total_cost,
                "cost_per_delivery": solution.cost_per_delivery,
            }
        )

    if third_party_price_per_delivery is not None:
        if third_party_price_per_delivery < 0:
            raise ValueError("third_party_price_per_delivery cannot be negative")
        rows.append(
            {
                "option": "third party",
                "feasible": True,
                "vehicles_used": np.nan,
                "total_km": np.nan,
                "total_cost": third_party_price_per_delivery * problem.n_stops,
                "cost_per_delivery": third_party_price_per_delivery,
            }
        )

    return pd.DataFrame(rows).sort_values("cost_per_delivery", ignore_index=True)


def window_cost(
    problem: DeliveryProblem,
    vehicle: VehicleType,
    solution_limit: int = 300,
) -> pd.DataFrame:
    """Price the delivery time windows by routing the same day with and without them.

    Windows fragment routes in a way capacity does not: a vehicle with payload to spare still
    has to come back, because it cannot reach the next window in time. The difference between
    these two rows is what the commercial promise costs to keep, and it is a number the
    commercial conversation rarely has.

    Returns:
        Two rows - windows enforced and windows opened to the full day - with the cost
        difference between them.
    """
    open_problem = build_problem(
        problem.stops,
        speed_kmh=problem.speed_kmh,
        circuity=problem.circuity,
        day_start_h=problem.day_start_h,
        day_end_h=problem.day_end_h,
        open_windows=True,
    )

    rows = []
    for label, candidate in (("windows enforced", problem), ("windows opened", open_problem)):
        solution = solve(candidate, vehicle, solution_limit=solution_limit)
        rows.append(
            {
                "case": label,
                "feasible": solution.feasible,
                "vehicles_used": float(solution.vehicles_used),
                "total_km": solution.total_km,
                "total_cost": solution.total_cost,
                "cost_per_delivery": solution.cost_per_delivery,
            }
        )

    table = pd.DataFrame(rows)
    open_cost = float(table.loc[table["case"] == "windows opened", "cost_per_delivery"].iloc[0])
    table["premium_vs_open"] = table["cost_per_delivery"] / open_cost - 1.0 if open_cost else np.nan
    return table
