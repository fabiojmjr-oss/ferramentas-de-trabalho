"""Statistical process control.

The order of work is not optional. Chart the process first, remove assignable causes, and only
then compute capability: an index calculated on an unstable process describes a state the
process does not have, and is the single most common defect in applied capability studies.
"""

from .capability import (
    Capability,
    capability,
    capability_from_subgroups,
    sigma_within_from_moving_range,
    sigma_within_from_subgroups,
)
from .charts import (
    ControlChart,
    i_mr_chart,
    overdispersion_ratio,
    p_chart,
    u_chart,
    xbar_r_chart,
)
from .constants import a2, c4, d2, d3, d4, e2
from .rules import (
    ALL_RULES,
    PRACTICAL_RULES,
    RULE_DESCRIPTIONS,
    RuleResult,
    apply_rules,
)

__all__ = [
    "ALL_RULES",
    "PRACTICAL_RULES",
    "RULE_DESCRIPTIONS",
    "Capability",
    "ControlChart",
    "RuleResult",
    "a2",
    "apply_rules",
    "c4",
    "capability",
    "capability_from_subgroups",
    "d2",
    "d3",
    "d4",
    "e2",
    "i_mr_chart",
    "overdispersion_ratio",
    "p_chart",
    "sigma_within_from_moving_range",
    "sigma_within_from_subgroups",
    "u_chart",
    "xbar_r_chart",
]
