"""ABC-XYZ classification and pick-face slotting.

The order of use is classification, then diagnosis, then a plan:

1. :func:`demand_profile` and :func:`abc_xyz` say which items matter and which are predictable.
2. :func:`travel_by_class` says whether the current layout reflects that.
3. :func:`cube_per_order_index` and :func:`reslot` produce a plan, and
   :func:`compare_strategies` measures it against the current state.

Read :mod:`oplab.slotting.travel` before quoting any number from this module: the objective is
distance-weighted picks, not a route, and the percentage change is robust in a way the absolute
metres are not.
"""

from .classify import (
    ABC_CUTS,
    POLICY_MATRIX,
    XYZ_CUTS,
    CellPolicy,
    abc_classes,
    abc_xyz,
    cell_summary,
    demand_profile,
    policy_table,
    xyz_classes,
)
from .reslot import compare_strategies, cube_per_order_index, reslot
from .travel import pick_counts, travel_by_class, travel_detail, travel_summary

__all__ = [
    "ABC_CUTS",
    "POLICY_MATRIX",
    "XYZ_CUTS",
    "CellPolicy",
    "abc_classes",
    "abc_xyz",
    "cell_summary",
    "compare_strategies",
    "cube_per_order_index",
    "demand_profile",
    "pick_counts",
    "policy_table",
    "reslot",
    "travel_by_class",
    "travel_detail",
    "travel_summary",
    "xyz_classes",
]
