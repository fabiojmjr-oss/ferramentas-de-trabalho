"""Small internal helpers for working with pandas results.

Not part of the public API.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def as_float(value: Any) -> float:
    """Coerce a pandas or numpy scalar to a plain float.

    Reductions and single-cell lookups come back with a union type that varies by pandas
    version and by whether stubs are installed, so every extraction of a scalar from a frame or
    a series goes through here rather than through a bare ``float()`` that type-checks on one
    machine and not another.
    """
    return float(np.asarray(value, dtype=float).item())


def as_int(value: Any) -> int:
    """Coerce a pandas or numpy scalar to a plain int.

    The integer counterpart of :func:`as_float`, and needed for the same reason: a groupby key
    arrives with a union type wide enough to include dates and strings, so a bare ``int()`` on it
    type-checks only where the stubs happen to narrow it.
    """
    return int(np.asarray(value).item())
