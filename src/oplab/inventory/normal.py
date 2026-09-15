"""The three normal-distribution functions an inventory policy needs, and no more.

`scipy` would supply all three. It is not a dependency here because this module needs exactly
these functions, and a heavy dependency for three closed-form expressions is a cost paid by
every user of the package. They are tested against published values rather than against
themselves.

The third function is the one usually missing from a spreadsheet, and its absence is why fill
rate and cycle service level get confused. The unit normal loss function gives the expected
shortfall per cycle, which is what a fill-rate target constrains; the inverse normal gives the
probability of not stocking out at all, which is what a cycle-service target constrains. They
are different questions with different answers, and only one of them is in `NORM.S.INV`.
"""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt

# Acklam's rational approximation to the inverse normal CDF. The coefficients are his; the
# Halley refinement below takes the relative error from about 1.15e-9 to full double precision.
_A = (
    -3.969683028665376e01,
    2.209460984245205e02,
    -2.759285104469687e02,
    1.383577518672690e02,
    -3.066479806614716e01,
    2.506628277459239e00,
)
_B = (
    -5.447609879822406e01,
    1.615858368580409e02,
    -1.556989798598866e02,
    6.680131188771972e01,
    -1.328068155288572e01,
)
_C = (
    -7.784894002430293e-03,
    -3.223964580411365e-01,
    -2.400758277161838e00,
    -2.549732539343734e00,
    4.374664141464968e00,
    2.938163982698783e00,
)
_D = (
    7.784695709041462e-03,
    3.224671290700398e-01,
    2.445134137142996e00,
    3.754408661907416e00,
)
_LOW = 0.02425
_HIGH = 1.0 - _LOW


def norm_cdf(z: float) -> float:
    """Standard normal cumulative distribution function."""
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def norm_pdf(z: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def norm_ppf(p: float) -> float:
    """Inverse of :func:`norm_cdf`, the safety factor for a cycle-service target.

    Args:
        p: Probability strictly between 0 and 1.

    Returns:
        The ``z`` such that ``norm_cdf(z) == p``.

    Raises:
        ValueError: If ``p`` is not strictly between 0 and 1. The boundaries are excluded
            deliberately: a 100% cycle-service target has no finite safety stock, and reporting
            a large number there would hide an infeasible request behind a plausible figure.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")

    if p < _LOW:
        q = math.sqrt(-2.0 * math.log(p))
        z = (((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )
    elif p <= _HIGH:
        q = p - 0.5
        r = q * q
        z = (
            (((((_A[0] * r + _A[1]) * r + _A[2]) * r + _A[3]) * r + _A[4]) * r + _A[5])
            * q
            / (((((_B[0] * r + _B[1]) * r + _B[2]) * r + _B[3]) * r + _B[4]) * r + 1.0)
        )
    else:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        z = -(((((_C[0] * q + _C[1]) * q + _C[2]) * q + _C[3]) * q + _C[4]) * q + _C[5]) / (
            (((_D[0] * q + _D[1]) * q + _D[2]) * q + _D[3]) * q + 1.0
        )

    # One step of Halley's method on erfc, which is what lifts the approximation to full
    # precision. Without it the safety factor is accurate to nine digits, which is plenty for
    # inventory and not enough for a test against published tables.
    error = 0.5 * math.erfc(-z / math.sqrt(2.0)) - p
    slope = norm_pdf(z)
    if slope > 0.0:
        step = error / slope
        z -= step / (1.0 + 0.5 * z * step)
    return z


# Above this the closed form cancels catastrophically and the asymptotic series is exact to
# double precision, so the switch loses nothing and gains everything.
_LOSS_ASYMPTOTIC_FROM = 6.0


def unit_normal_loss(z: float) -> float:
    """Expected shortfall per cycle, in standard deviations, at safety factor ``z``.

    ``G(z) = phi(z) - z * (1 - Phi(z))``. Multiplied by the standard deviation of demand over
    lead time it gives the expected units short per replenishment cycle, which is the quantity
    a fill-rate target actually constrains.

    The closed form is only usable over part of the range. Both of its terms tend to zero as
    ``z`` grows and their difference is a small fraction of either, so above about ``z = 6`` the
    subtraction loses every significant digit and eventually returns a negative number for a
    quantity that is positive everywhere. Mills' ratio expansion gives
    ``G(z) = phi(z) * (1/z^2 - 3/z^4 + 15/z^6 - 105/z^8 + ...)``, which has no cancellation at
    all, and that is what is used in the tail. This matters in practice rather than in principle:
    a demanding fill-rate target on a low-variability item lands in exactly that range.

    Args:
        z: Safety factor.

    Returns:
        ``G(z)``, which is positive for every finite ``z`` and decreasing in it.
    """
    if z >= _LOSS_ASYMPTOTIC_FROM:
        w = 1.0 / (z * z)
        return norm_pdf(z) * w * (1.0 - 3.0 * w + 15.0 * w * w - 105.0 * w * w * w)
    return norm_pdf(z) - z * (1.0 - norm_cdf(z))


def unit_normal_loss_inverse(target: float, tolerance: float = 1e-12) -> float:
    """Invert :func:`unit_normal_loss` by bisection.

    There is no closed form, and the function is monotone decreasing, so bisection is both
    sufficient and exact to tolerance. The bracket widens until it contains the target rather
    than being fixed, because a very small target needs a large ``z``.

    Args:
        target: A positive value of ``G(z)``.
        tolerance: Absolute tolerance on ``z``.

    Returns:
        The ``z`` with ``unit_normal_loss(z) == target``.

    Raises:
        ValueError: If ``target`` is not positive.
    """
    if target <= 0.0:
        raise ValueError("target must be positive; G(z) is positive for every finite z")

    low, high = -40.0, 1.0
    while unit_normal_loss(high) > target:
        high *= 2.0
        if high > 1e6:  # pragma: no cover - defensive
            raise ValueError("target is too small to invert")

    while high - low > tolerance:
        mid = 0.5 * (low + high)
        if unit_normal_loss(mid) > target:
            low = mid
        else:
            high = mid
    return 0.5 * (low + high)


def empirical_quantile(sample: npt.ArrayLike, p: float) -> float:
    """Quantile of an observed sample, for comparison against the normal assumption.

    Args:
        sample: Observed values.
        p: Probability between 0 and 1.

    Returns:
        The ``p`` quantile of ``sample``.

    Raises:
        ValueError: If ``sample`` is empty or ``p`` is outside ``[0, 1]``.
    """
    values = np.asarray(sample, dtype=float)
    if values.size == 0:
        raise ValueError("sample is empty")
    if not 0.0 <= p <= 1.0:
        raise ValueError("p must be between 0 and 1")
    return float(np.quantile(values, p))
