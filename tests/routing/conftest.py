"""Small routing problems.

Every solve costs its time limit in wall-clock seconds, so the fixtures here are deliberately
tiny and the limits short. A test that needs a big problem to prove its point is testing the
solver rather than this code.
"""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.routing import DeliveryProblem, build_problem


def stop(x: float, y: float, weight: float = 10.0, window: tuple[float, float] = (8.0, 18.0)):  # type: ignore[no-untyped-def]
    return {
        "x_km": x,
        "y_km": y,
        "weight_kg": weight,
        "service_min": 10.0,
        "window_start_h": window[0],
        "window_end_h": window[1],
    }


@pytest.fixture
def single_stop() -> DeliveryProblem:
    """One stop 10 km east of the depot, with no circuity, so the arithmetic is exact."""
    return build_problem(pd.DataFrame([stop(10.0, 0.0)]), circuity=1.0, speed_kmh=60.0)


@pytest.fixture
def four_corners() -> DeliveryProblem:
    """Four stops on the axes at 10 km, no circuity."""
    frame = pd.DataFrame([stop(10.0, 0.0), stop(-10.0, 0.0), stop(0.0, 10.0), stop(0.0, -10.0)])
    return build_problem(frame, circuity=1.0, speed_kmh=60.0)
