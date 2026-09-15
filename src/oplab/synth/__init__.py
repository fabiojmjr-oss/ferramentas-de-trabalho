"""Seeded synthetic supply chain data.

No table in this repository comes from a real operation. The generator is deliberately part
of the product: it makes every figure in the documentation reproducible, and it keeps the
repository free of confidentiality constraints. See ``DISCLAIMER.md``.
"""

from .catalog import generate_catalog
from .config import DEFAULT_SITES, SiteProfile, SynthConfig
from .costs import generate_cost_ledger
from .counts import generate_cycle_counts
from .dataset import Dataset, generate_dataset
from .deliveries import generate_deliveries, size_band
from .demand import generate_demand
from .inbound import generate_receipts
from .outbound import generate_order_lines
from .process import SpecialCause, generate_subgroups
from .procurement import SUPPLIER_PROFILES, generate_purchase_orders
from .warehouse import generate_assignment, generate_layout

__all__ = [
    "DEFAULT_SITES",
    "SUPPLIER_PROFILES",
    "Dataset",
    "SiteProfile",
    "SpecialCause",
    "SynthConfig",
    "generate_assignment",
    "generate_catalog",
    "generate_cost_ledger",
    "generate_cycle_counts",
    "generate_deliveries",
    "generate_dataset",
    "generate_demand",
    "generate_layout",
    "generate_order_lines",
    "generate_purchase_orders",
    "generate_receipts",
    "size_band",
    "generate_subgroups",
]
