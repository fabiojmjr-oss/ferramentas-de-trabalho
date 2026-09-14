"""Vehicle routing with time windows, and the questions worth asking of it.

Built on OR-Tools. Install the extra: ``pip install -e ".[routing]"``.

The objective is **cost** - a fixed charge for each vehicle actually used plus a rate per
kilometre - not distance and not vehicle count. Distance and vehicle count are reported as
outcomes, because optimising either one directly answers a different question: a tender
evaluated on kilometres can select the more expensive bid.

Order of use:

1. :func:`diagnose` and :func:`fleet_lower_bounds` before solving. An infeasible day is usually
   one unreachable stop, not a routing failure.
2. :func:`solve` for one plan, and read the time limit it carries.
3. :func:`quality_curve` to see how much the search left on the table.
4. :func:`density_curve`, :func:`window_cost` and :func:`compare_fleets` for the three
   decisions this tool exists to inform.
"""

from .analysis import (
    compare_fleets,
    density_curve,
    diagnose,
    fleet_lower_bounds,
    quality_curve,
    window_cost,
)
from .fleet import TRUCK, VAN, VehicleType
from .problem import DeliveryProblem, build_problem, one_day
from .solver import RouteSolution, solve

__all__ = [
    "TRUCK",
    "VAN",
    "DeliveryProblem",
    "RouteSolution",
    "VehicleType",
    "build_problem",
    "compare_fleets",
    "density_curve",
    "diagnose",
    "fleet_lower_bounds",
    "one_day",
    "quality_curve",
    "solve",
    "window_cost",
]
