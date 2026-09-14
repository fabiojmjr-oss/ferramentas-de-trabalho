"""Explaining why a total or a per-unit metric moved.

Two entry points, for two different questions:

:func:`price_volume_mix`
    Why did the **total** move? Splits the change into volume, mix, rate, and the segments that
    exist in only one of the two periods.
:func:`unit_value_bridge`
    Why did the **per-unit** metric move? Two exact terms, rate and mix. Volume is absent by
    construction, which is the useful part: growth alone cannot move a cost per order.

Both are exact - the effects sum to the change with no residual - and both are only as good as
the segmentation, since mix can only be seen along a dimension you segment by.
"""

from .bridge import BridgeResult, unit_value_bridge
from .pvm import EFFECT_ORDER, PVMResult, price_volume_mix
from .report import contribution_pareto, waterfall

__all__ = [
    "EFFECT_ORDER",
    "BridgeResult",
    "PVMResult",
    "contribution_pareto",
    "price_volume_mix",
    "unit_value_bridge",
    "waterfall",
]
