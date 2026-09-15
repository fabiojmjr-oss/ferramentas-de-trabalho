"""Control chart constants.

Values follow the ASTM E2587 / ASQ tables used by every standard reference on statistical
process control. They are tabulated rather than computed because the tabulated values are what
auditors, certification bodies and textbooks check against; ``c4`` is the exception, since it
has a closed form.
"""

from __future__ import annotations

from math import gamma, sqrt

# Subgroup size -> (A2, D3, D4, d2)
_TABLE: dict[int, tuple[float, float, float, float]] = {
    2: (1.880, 0.000, 3.267, 1.128),
    3: (1.023, 0.000, 2.574, 1.693),
    4: (0.729, 0.000, 2.282, 2.059),
    5: (0.577, 0.000, 2.114, 2.326),
    6: (0.483, 0.000, 2.004, 2.534),
    7: (0.419, 0.076, 1.924, 2.704),
    8: (0.373, 0.136, 1.864, 2.847),
    9: (0.337, 0.184, 1.816, 2.970),
    10: (0.308, 0.223, 1.777, 3.078),
    11: (0.285, 0.256, 1.744, 3.173),
    12: (0.266, 0.283, 1.717, 3.258),
    13: (0.249, 0.307, 1.693, 3.336),
    14: (0.235, 0.328, 1.672, 3.407),
    15: (0.223, 0.347, 1.653, 3.472),
    16: (0.212, 0.363, 1.637, 3.532),
    17: (0.203, 0.378, 1.622, 3.588),
    18: (0.194, 0.391, 1.608, 3.640),
    19: (0.187, 0.403, 1.597, 3.689),
    20: (0.180, 0.415, 1.585, 3.735),
    21: (0.173, 0.425, 1.575, 3.778),
    22: (0.167, 0.434, 1.566, 3.819),
    23: (0.162, 0.443, 1.557, 3.858),
    24: (0.157, 0.451, 1.548, 3.895),
    25: (0.153, 0.459, 1.541, 3.931),
}

MIN_SUBGROUP = min(_TABLE)
MAX_SUBGROUP = max(_TABLE)


def _lookup(n: int, position: int, label: str) -> float:
    if n not in _TABLE:
        raise ValueError(
            f"{label} is tabulated for subgroup sizes {MIN_SUBGROUP}-{MAX_SUBGROUP}, got {n}"
        )
    return _TABLE[n][position]


def a2(n: int) -> float:
    """Factor for X-bar chart limits built from the average range."""
    return _lookup(n, 0, "A2")


def d3(n: int) -> float:
    """Lower control limit factor for the R chart."""
    return _lookup(n, 1, "D3")


def d4(n: int) -> float:
    """Upper control limit factor for the R chart."""
    return _lookup(n, 2, "D4")


def d2(n: int) -> float:
    """Expected range of a normal sample of size ``n``, in standard deviations.

    Dividing the average range by ``d2`` gives an unbiased estimate of within-subgroup
    standard deviation, which is the short-term variation a capability study should use.
    """
    return _lookup(n, 3, "d2")


def c4(n: int) -> float:
    """Bias correction for the sample standard deviation.

    ``s / c4(n)`` is an unbiased estimator of sigma. The correction is material at small
    subgroup sizes - about 6% at ``n = 3`` - which is exactly where control charts operate.
    """
    if n < 2:
        raise ValueError(f"c4 requires n >= 2, got {n}")
    return sqrt(2.0 / (n - 1)) * gamma(n / 2.0) / gamma((n - 1) / 2.0)


def e2(n: int = 2) -> float:
    """Factor for individuals chart limits built from the average moving range.

    With the conventional moving range of two consecutive observations this equals
    ``3 / d2(2) = 2.66``.
    """
    return 3.0 / d2(n)
