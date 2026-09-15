"""Discrete-event simulation of a distribution centre.

Answers the question a static capacity spreadsheet cannot: **where is the constraint, and what
does relieving it buy?** The spreadsheet divides mean work by mean capacity and is blind to
queueing, to variability, and to work that arrives too late in a shift to be done that day.

Use it in this order:

1. :func:`run_once` for one replication, and :meth:`SimResult.static_versus_simulated` to see
   the gap against the spreadsheet answer.
2. :meth:`SimResult.bottleneck` to find the resource the rest of the operation waits on.
3. :func:`replicate` for a confidence interval, because one run is a sample of one.
4. :func:`compare_scenarios` to price the options against each other, with the honesty that
   overlapping intervals mean nothing has been shown.
"""

from .config import SimConfig
from .experiment import compare_scenarios, replicate, run_once
from .results import SimResult
from .shift import hours_until_open, open_hours_in_window, open_hours_remaining

__all__ = [
    "SimConfig",
    "SimResult",
    "compare_scenarios",
    "hours_until_open",
    "open_hours_in_window",
    "open_hours_remaining",
    "replicate",
    "run_once",
]
