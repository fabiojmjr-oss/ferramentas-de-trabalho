"""Vehicle types, and the cost model behind them."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .problem import DeliveryProblem


@dataclass(frozen=True)
class VehicleType:
    """A homogeneous fleet.

    The cost model is the standard two-part one: a fixed cost charged only for a vehicle that
    is actually used, plus a rate per kilometre. That split is what makes the model able to
    decide *how many* vehicles to run, which is usually the expensive part of the decision -
    a solver given only a distance objective will happily use every vehicle offered.

    Attributes:
        name: Label used in reports.
        capacity_kg: Payload.
        fixed_cost: Cost of putting one vehicle on the road for the day, charged once.
        cost_per_km: Variable cost per kilometre.
        max_duration_h: Maximum route duration, driver shift included.
        count: Vehicles available. ``None`` derives a generous bound from the problem, letting
            the fixed cost decide how many are worth using.
    """

    name: str
    capacity_kg: float
    fixed_cost: float
    cost_per_km: float
    max_duration_h: float = 9.0
    count: int | None = None

    def __post_init__(self) -> None:
        if self.capacity_kg <= 0:
            raise ValueError("capacity_kg must be positive")
        if self.fixed_cost < 0 or self.cost_per_km < 0:
            raise ValueError("costs cannot be negative")
        if self.max_duration_h <= 0:
            raise ValueError("max_duration_h must be positive")
        if self.count is not None and self.count < 1:
            raise ValueError("count must be at least 1 when given")

    def available(self, problem: DeliveryProblem) -> int:
        """Vehicles to offer the solver.

        The bound is deliberately generous, and the reason is a mistake worth not repeating.
        A bound built from total **service** time ignores travel, and on a territory with a
        hundred-kilometre radius travel dominates: the bound came out at five vehicles for a
        day that needs six, and a perfectly feasible problem was reported infeasible. An
        infeasibility that is an artefact of the modeller's own bound is the worst kind,
        because it looks like a finding.

        Offering too many costs only search time, since the fixed cost stops an unused vehicle
        from being used. Offering too few changes the answer. So the bound errs high: enough
        for routes averaging two stops, which no sane territory requires.
        """
        if self.count is not None:
            return self.count

        by_weight = math.ceil(problem.total_weight_kg / self.capacity_kg)
        by_pairs = math.ceil(problem.n_stops / 2)
        return int(min(problem.n_stops, max(4, by_pairs, 2 * by_weight)))


#: A small reference fleet. The trade-off is the usual one: the van is cheap to put on the road
#: and expensive per tonne, the truck is the reverse, and which wins depends entirely on the
#: density and weight of the day being routed.
VAN = VehicleType(
    name="van", capacity_kg=1200.0, fixed_cost=180.0, cost_per_km=2.10, max_duration_h=9.0
)
TRUCK = VehicleType(
    name="truck", capacity_kg=4500.0, fixed_cost=320.0, cost_per_km=3.40, max_duration_h=9.0
)
