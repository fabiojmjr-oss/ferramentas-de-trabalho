"""Fast configurations for the simulation tests.

The default :class:`SimConfig` simulates 24 days of a 900-order-a-day operation, which takes
about a second. Multiplied by replications and scenarios that becomes a slow test suite, so
everything here runs on a small operation unless the test is specifically about scale.
"""

from __future__ import annotations

import pytest

from oplab.simulation import SimConfig


@pytest.fixture
def small() -> SimConfig:
    return SimConfig(
        days=6,
        warmup_days=1,
        trucks_per_day=6.0,
        orders_per_day=120.0,
        pickers=4,
        checkers=2,
        inbound_docks=2,
        unloaders=2,
        putaway_operators=2,
    )
