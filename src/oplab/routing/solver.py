"""Solving the vehicle routing problem with time windows.

Two things about this solver are worth being explicit about, because reports built on it
routinely get both wrong.

**"Optimal" is not what comes back.** OR-Tools runs a construction heuristic and then local
search until its budget runs out. The result is the best solution found, and for a problem of
any size it is not proven optimal and usually is not optimal. :class:`RouteSolution` carries
the budget it was produced under, and :func:`oplab.routing.quality_curve` shows how much is
still on the table at each budget. A routing cost quoted without its search budget is a cost
quoted without its error bar.

**The budget is a solution count, not a stopwatch.** A wall-clock limit makes the answer depend
on the machine and on what else that machine is doing: the same problem solved under CPU
contention explores less and returns a worse - and different - plan. That is unacceptable for a
figure that goes into a tender, and it showed up here as a test that passed alone and failed
inside the full suite. ``solution_limit`` counts accepted solutions instead, so the result is
reproducible anywhere. ``time_limit_s`` remains as a safety cap so a pathological instance
cannot hang, and a solution that hits the cap instead of its solution limit says so.

**The objective decides the answer.** Minimising distance, minimising vehicles and minimising
cost give different solutions, and a tender evaluated on kilometres can select the more
expensive bid. This module minimises **cost** - fixed cost for vehicles actually used, plus a
rate per kilometre - because that is the quantity the business pays. Distance and vehicle count
are reported as outcomes rather than optimised as targets.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from .fleet import VehicleType
from .problem import DeliveryProblem

CENTS = 100.0
DEFAULT_SOLUTION_LIMIT = 300
DEFAULT_TIME_CAP_S = 120
MAX_WAIT_MIN = 480


@dataclass(frozen=True)
class RouteSolution:
    """Outcome of one solve.

    Attributes:
        feasible: Whether a solution serving every stop was found.
        routes: One list of stop positions per used vehicle, in visit order.
        summary: One row per used vehicle with ``stops``, ``km``, ``duration_h``, ``load_kg``,
            ``utilisation`` and ``cost``.
        total_cost: Fixed plus variable cost of the solution.
        total_km: Distance driven.
        vehicles_used: Vehicles that left the depot.
        vehicles_offered: Vehicles the solver was allowed to use.
        stops_served: Stops visited.
        solution_limit: Accepted-solution budget the result was produced under. This is the
            reproducible budget: the same limit gives the same plan on any machine.
        time_cap_s: Wall-clock safety cap. Reaching it means the search stopped early and the
            result is machine-dependent, which ``hit_time_cap`` reports.
        elapsed_s: Wall-clock time the search actually took.
        vehicle: The fleet used.
        problem: The problem solved.
    """

    feasible: bool
    routes: list[list[int]]
    summary: pd.DataFrame
    total_cost: float
    total_km: float
    vehicles_used: int
    vehicles_offered: int
    stops_served: int
    solution_limit: int
    time_cap_s: int
    elapsed_s: float
    vehicle: VehicleType
    problem: DeliveryProblem

    @property
    def hit_time_cap(self) -> bool:
        """Whether the wall-clock cap stopped the search before its solution budget.

        When true, the result is no longer reproducible across machines: raise the cap, or
        lower the solution limit, before quoting the cost.
        """
        return self.elapsed_s >= self.time_cap_s - 0.5

    @property
    def cost_per_delivery(self) -> float:
        """Total cost divided by stops served."""
        return self.total_cost / self.stops_served if self.stops_served else float("nan")

    @property
    def stops_per_vehicle(self) -> float:
        return self.stops_served / self.vehicles_used if self.vehicles_used else float("nan")

    def headline(self) -> pd.Series:
        """The numbers a route tender turns on, with the caveat attached."""
        return pd.Series(
            {
                "feasible": float(self.feasible),
                "vehicles_used": float(self.vehicles_used),
                "stops_served": float(self.stops_served),
                "total_km": self.total_km,
                "total_cost": self.total_cost,
                "cost_per_delivery": self.cost_per_delivery,
                "stops_per_vehicle": self.stops_per_vehicle,
                "km_per_delivery": self.total_km / self.stops_served
                if self.stops_served
                else float("nan"),
                "solution_limit": float(self.solution_limit),
                "elapsed_s": self.elapsed_s,
                "hit_time_cap": float(self.hit_time_cap),
            }
        )


def solve(
    problem: DeliveryProblem,
    vehicle: VehicleType,
    solution_limit: int = DEFAULT_SOLUTION_LIMIT,
    time_cap_s: int = DEFAULT_TIME_CAP_S,
) -> RouteSolution:
    """Solve the routing problem, minimising total cost.

    Args:
        problem: The day to route.
        vehicle: The fleet to route it with.
        solution_limit: Accepted solutions to explore before stopping. This is the budget to
            report alongside any cost, and it is reproducible: the same limit gives the same
            plan on any machine.
        time_cap_s: Wall-clock safety cap, so a pathological instance cannot hang. Reaching it
            makes the result machine-dependent; :attr:`RouteSolution.hit_time_cap` says so.

    Returns:
        A :class:`RouteSolution`. When no solution serving every stop exists within the fleet's
        capacity, duration and windows, ``feasible`` is ``False`` and the cost fields are zero -
        check :meth:`DeliveryProblem.profile` and :func:`oplab.routing.diagnose` before assuming
        the routing is at fault.

    Raises:
        ValueError: If either budget is not positive.
    """
    if solution_limit < 1:
        raise ValueError("solution_limit must be at least 1")
    if time_cap_s < 1:
        raise ValueError("time_cap_s must be at least 1")

    n_nodes = problem.n_stops + 1
    offered = vehicle.available(problem)
    manager = pywrapcp.RoutingIndexManager(n_nodes, offered, 0)
    routing = pywrapcp.RoutingModel(manager)

    # Arc cost is money, not distance. A distance objective would use every vehicle offered.
    distance_cents = np.rint(problem.distance_km * vehicle.cost_per_km * CENTS).astype(int)

    def arc_cost(from_index: int, to_index: int) -> int:
        return int(distance_cents[manager.IndexToNode(from_index)][manager.IndexToNode(to_index)])

    arc_callback = routing.RegisterTransitCallback(arc_cost)
    routing.SetArcCostEvaluatorOfAllVehicles(arc_callback)
    routing.SetFixedCostOfAllVehicles(int(round(vehicle.fixed_cost * CENTS)))

    demand_kg = np.concatenate([[0], np.rint(problem.stops["weight_kg"].to_numpy()).astype(int)])

    def demand(from_index: int) -> int:
        return int(demand_kg[manager.IndexToNode(from_index)])

    demand_callback = routing.RegisterUnaryTransitCallback(demand)
    routing.AddDimensionWithVehicleCapacity(
        demand_callback,
        0,
        [int(round(vehicle.capacity_kg))] * offered,
        True,
        "load",
    )

    service_min = np.concatenate([[0.0], problem.stops["service_min"].to_numpy(dtype=float)])
    travel_min = np.rint(problem.travel_min).astype(int)
    service_int = np.rint(service_min).astype(int)

    def transit_time(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(service_int[from_node] + travel_min[from_node][to_node])

    time_callback = routing.RegisterTransitCallback(transit_time)
    horizon = int(round((problem.day_end_h - problem.day_start_h) * 60))
    routing.AddDimension(
        time_callback,
        MAX_WAIT_MIN,
        horizon,
        False,  # cumulative time does not start at zero: the departure time is a decision
        "time",
    )
    time_dimension = routing.GetDimensionOrDie("time")
    # Route duration is a span, not a cumulative bound. Capping the dimension's cumulative
    # value instead would tie the latest departure to the maximum duration, so a vehicle
    # leaving at 10:00 would be allowed a shorter shift than one leaving at 08:00 - which is
    # not a shift rule, it is a modelling error, and it makes feasible problems infeasible.
    max_span_min = int(round(vehicle.max_duration_h * 60))
    for vehicle_id in range(offered):
        time_dimension.SetSpanUpperBoundForVehicle(min(max_span_min, horizon), vehicle_id)

    starts = np.rint(
        (problem.stops["window_start_h"].to_numpy(dtype=float) - problem.day_start_h) * 60
    ).astype(int)
    ends = np.rint(
        (problem.stops["window_end_h"].to_numpy(dtype=float) - problem.day_start_h) * 60
    ).astype(int)
    for stop in range(problem.n_stops):
        index = manager.NodeToIndex(stop + 1)
        time_dimension.CumulVar(index).SetRange(int(starts[stop]), int(ends[stop]))
    for vehicle_id in range(offered):
        time_dimension.CumulVar(routing.Start(vehicle_id)).SetRange(0, horizon)
        time_dimension.CumulVar(routing.End(vehicle_id)).SetRange(0, horizon)
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.Start(vehicle_id)))
        routing.AddVariableMinimizedByFinalizer(time_dimension.CumulVar(routing.End(vehicle_id)))

    parameters = pywrapcp.DefaultRoutingSearchParameters()
    parameters.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    parameters.solution_limit = solution_limit
    parameters.time_limit.FromSeconds(time_cap_s)
    parameters.log_search = False

    started = time.perf_counter()
    assignment = routing.SolveWithParameters(parameters)
    elapsed = time.perf_counter() - started
    if assignment is None:
        return RouteSolution(
            feasible=False,
            routes=[],
            summary=pd.DataFrame(),
            total_cost=0.0,
            total_km=0.0,
            vehicles_used=0,
            vehicles_offered=offered,
            stops_served=0,
            solution_limit=solution_limit,
            time_cap_s=time_cap_s,
            elapsed_s=elapsed,
            vehicle=vehicle,
            problem=problem,
        )

    return _extract(
        routing, manager, assignment, problem, vehicle, offered, solution_limit, time_cap_s, elapsed
    )


def _extract(
    routing: pywrapcp.RoutingModel,
    manager: pywrapcp.RoutingIndexManager,
    assignment: pywrapcp.Assignment,
    problem: DeliveryProblem,
    vehicle: VehicleType,
    offered: int,
    solution_limit: int,
    time_cap_s: int,
    elapsed_s: float,
) -> RouteSolution:
    """Read routes and costs out of a solved model."""
    time_dimension = routing.GetDimensionOrDie("time")
    routes: list[list[int]] = []
    rows: list[dict[str, float]] = []

    for vehicle_id in range(offered):
        index = routing.Start(vehicle_id)
        if not routing.IsVehicleUsed(assignment, vehicle_id):
            continue

        order: list[int] = []
        km = 0.0
        load = 0.0
        start_min = assignment.Value(time_dimension.CumulVar(index))
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != 0:
                order.append(node - 1)
                load += float(problem.stops.iloc[node - 1]["weight_kg"])
            next_index = assignment.Value(routing.NextVar(index))
            km += float(problem.distance_km[node][manager.IndexToNode(next_index)])
            index = next_index
        end_min = assignment.Value(time_dimension.CumulVar(index))

        routes.append(order)
        rows.append(
            {
                "vehicle": float(len(routes)),
                "stops": float(len(order)),
                "km": km,
                "duration_h": (end_min - start_min) / 60.0,
                "load_kg": load,
                "utilisation": load / vehicle.capacity_kg,
                "cost": vehicle.fixed_cost + vehicle.cost_per_km * km,
            }
        )

    summary = pd.DataFrame(rows)
    total_km = float(summary["km"].sum()) if not summary.empty else 0.0
    total_cost = float(summary["cost"].sum()) if not summary.empty else 0.0
    stops_served = int(summary["stops"].sum()) if not summary.empty else 0

    return RouteSolution(
        feasible=stops_served == problem.n_stops,
        routes=routes,
        summary=summary,
        total_cost=total_cost,
        total_km=total_km,
        vehicles_used=len(routes),
        vehicles_offered=offered,
        stops_served=stops_served,
        solution_limit=solution_limit,
        time_cap_s=time_cap_s,
        elapsed_s=elapsed_s,
        vehicle=vehicle,
        problem=problem,
    )
