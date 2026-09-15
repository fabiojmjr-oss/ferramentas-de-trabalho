"""Shared fixtures.

The full dataset is expensive to build, so it is generated once per test session. Tests must
therefore treat it as read-only and copy before mutating.
"""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.synth import Dataset, SynthConfig, generate_dataset

SMALL = SynthConfig(days=60, n_skus=40)


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    return generate_dataset(SMALL)


@pytest.fixture
def order_lines() -> pd.DataFrame:
    """Six order lines covering every case that breaks a naive service calculation.

    ======  =========  ==========  ============  =========================
    Line    Ordered    Delivered   Status        Outcome under the default
    ======  =========  ==========  ============  =========================
    O1-L1   10         10          delivered     on time, in full
    O1-L2   5          4           delivered     on time, short
    O2-L1   8          8           delivered     8 h late, in full
    O2-L2   2          2           delivered     on time, in full
    O3-L1   4          0           cancelled     out of scope
    O3-L2   6          0           in_transit    out of scope by default
    ======  =========  ==========  ============  =========================
    """
    promised = pd.Timestamp("2025-01-03 18:00")
    ordered_at = pd.Timestamp("2025-01-01 09:00")
    nat = pd.NaT
    rows = [
        ("O1", "O1-L1", "CD-SP", "S1", 10, 10, pd.Timestamp("2025-01-03 17:00"), "delivered"),
        ("O1", "O1-L2", "CD-SP", "S2", 5, 4, pd.Timestamp("2025-01-03 17:00"), "delivered"),
        ("O2", "O2-L1", "CD-RJ", "S1", 8, 8, pd.Timestamp("2025-01-04 02:00"), "delivered"),
        ("O2", "O2-L2", "CD-RJ", "S3", 2, 2, pd.Timestamp("2025-01-03 17:00"), "delivered"),
        ("O3", "O3-L1", "CD-RJ", "S1", 4, 0, nat, "cancelled"),
        ("O3", "O3-L2", "CD-RJ", "S2", 6, 0, nat, "in_transit"),
    ]
    frame = pd.DataFrame(
        rows,
        columns=[
            "order_id",
            "line_id",
            "site",
            "sku",
            "qty_ordered",
            "qty_delivered",
            "delivered_ts",
            "status",
        ],
    )
    frame["order_ts"] = ordered_at
    frame["promised_ts"] = promised
    frame["qty_shipped"] = frame["qty_delivered"]
    frame["ship_ts"] = frame["delivered_ts"] - pd.Timedelta(hours=20)
    return frame
