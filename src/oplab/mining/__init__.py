"""What the process actually does, as opposed to what the flowchart says it does.

A value stream map drawn in a workshop is a set of estimates with a consensus attached. The same
map derived from an event log is a measurement, and it usually disagrees with the workshop in three
specific ways: the documented path describes a minority of cases, the lead time sits in handovers
nobody nominated, and the steps that exist only because something went wrong are counted as work.

Use it in this order:

1. :func:`profile_log` before anything. The two defects that make every later number meaningless -
   a case identifier coarser than the case, and a single timestamp per step - are both visible
   here and invisible downstream.
2. :func:`variant_coverage` for whether a standard process exists at all.
3. :func:`flow_efficiency` and :func:`waiting_ranked` for where the lead time is.
4. :func:`rework` and :func:`deviations` for what the exceptions cost.
5. :func:`cost_of_deviation` to put the two groups side by side, which is the business case.

No extra dependency and no process-mining library. The directly-follows graph is a group-by, and
conformance here is a subsequence test whose limits are stated in :mod:`oplab.mining.conformance`.
"""

from .conformance import Conformance, conformance, cost_of_deviation, deviations
from .discover import directly_follows, rework, variant_coverage, variants
from .log import LogProfile, profile_log, to_event_log, validate_log
from .timing import (
    FlowEfficiency,
    activity_times,
    case_times,
    flow_efficiency,
    waiting_ranked,
)

__all__ = [
    "Conformance",
    "FlowEfficiency",
    "LogProfile",
    "activity_times",
    "case_times",
    "conformance",
    "cost_of_deviation",
    "deviations",
    "directly_follows",
    "flow_efficiency",
    "profile_log",
    "rework",
    "to_event_log",
    "validate_log",
    "variant_coverage",
    "variants",
    "waiting_ranked",
]
