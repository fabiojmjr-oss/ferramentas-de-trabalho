"""Logistics indicators with explicit definitions.

Each function validates its input against a contract in :mod:`oplab.kpi.schemas` and exposes
its reporting conventions as arguments rather than burying them in the implementation. Where a
metric has more than one legitimate definition, all of them are computed and returned
together instead of one being chosen silently.
"""

from .flow import (
    appointment_adherence,
    dock_to_stock,
    duration_profile,
    order_cycle_time,
)
from .inventory import inventory_record_accuracy, variance_pareto
from .schemas import (
    CYCLE_COUNTS,
    ORDER_LINES,
    RECEIPTS,
    Column,
    Contract,
    ContractError,
)
from .service import (
    ServicePolicy,
    fill_rate,
    in_full_rate,
    line_service,
    on_time_rate,
    otif,
    service_sensitivity,
)

__all__ = [
    "CYCLE_COUNTS",
    "ORDER_LINES",
    "RECEIPTS",
    "Column",
    "Contract",
    "ContractError",
    "ServicePolicy",
    "appointment_adherence",
    "dock_to_stock",
    "duration_profile",
    "fill_rate",
    "in_full_rate",
    "inventory_record_accuracy",
    "line_service",
    "on_time_rate",
    "order_cycle_time",
    "otif",
    "service_sensitivity",
    "variance_pareto",
]
