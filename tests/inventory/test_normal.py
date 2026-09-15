"""The three normal functions are tested against published values, not against themselves."""

from __future__ import annotations

import math

import pytest

from oplab.inventory.normal import (
    empirical_quantile,
    norm_cdf,
    norm_pdf,
    norm_ppf,
    unit_normal_loss,
    unit_normal_loss_inverse,
)

# Standard normal quantiles as tabulated; these are the safety factors in every textbook.
TABULATED = {
    0.50: 0.000000,
    0.75: 0.674490,
    0.90: 1.281552,
    0.95: 1.644854,
    0.975: 1.959964,
    0.98: 2.053749,
    0.99: 2.326348,
    0.995: 2.575829,
    0.999: 3.090232,
    0.9999: 3.719016,
}


@pytest.mark.parametrize(("p", "expected"), TABULATED.items())
def test_ppf_matches_published_quantiles(p: float, expected: float) -> None:
    assert norm_ppf(p) == pytest.approx(expected, abs=5e-7)


@pytest.mark.parametrize("p", [1e-10, 0.001, 0.02, 0.0243, 0.3, 0.5, 0.7, 0.9757, 0.98, 1 - 1e-10])
def test_ppf_inverts_cdf_across_all_three_branches(p: float) -> None:
    """Acklam's approximation is piecewise; the joins are where an error would hide."""
    assert norm_cdf(norm_ppf(p)) == pytest.approx(p, rel=1e-12, abs=1e-15)


def test_ppf_rejects_the_boundaries() -> None:
    """A 100% service target has no finite safety stock, and saying so beats returning a number."""
    for p in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="strictly between"):
            norm_ppf(p)


def test_pdf_at_zero_is_the_closed_form() -> None:
    assert norm_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2.0 * math.pi), rel=1e-15)


def test_cdf_is_symmetric() -> None:
    for z in (0.3, 1.0, 1.6449, 3.0):
        assert norm_cdf(-z) == pytest.approx(1.0 - norm_cdf(z), abs=1e-15)


def test_loss_function_at_zero_is_the_density_at_zero() -> None:
    """G(0) = phi(0), since the second term vanishes."""
    assert unit_normal_loss(0.0) == pytest.approx(norm_pdf(0.0), rel=1e-15)


@pytest.mark.parametrize(
    ("z", "expected"),
    [(0.0, 0.398942), (0.5, 0.197797), (1.0, 0.083315), (1.645, 0.020886), (2.0, 0.008491)],
)
def test_loss_function_matches_published_table(z: float, expected: float) -> None:
    assert unit_normal_loss(z) == pytest.approx(expected, abs=5e-6)


def test_loss_function_is_positive_and_decreasing() -> None:
    values = [unit_normal_loss(z) for z in (-2.0, -1.0, 0.0, 1.0, 2.0, 4.0, 8.0, 12.0, 20.0)]
    assert all(v > 0.0 for v in values)
    assert values == sorted(values, reverse=True)


def test_loss_function_survives_the_tail_where_the_closed_form_cancels() -> None:
    """The naive difference returns a non-positive number by z = 8; the series does not.

    The two branches also have to agree where they meet, or the switch would put a step into a
    smooth function - which a monotonicity test on its own would not catch.
    """
    naive = norm_pdf(8.0) - 8.0 * (1.0 - norm_cdf(8.0))
    assert naive <= 0.0
    assert unit_normal_loss(8.0) > 0.0

    assert unit_normal_loss(6.0) == pytest.approx(unit_normal_loss(6.0 - 1e-9), rel=1e-9)


def test_loss_inverse_round_trips() -> None:
    for z in (-2.0, -0.5, 0.0, 1.0, 2.5, 4.0):
        assert unit_normal_loss_inverse(unit_normal_loss(z)) == pytest.approx(z, abs=1e-9)


def test_loss_inverse_rejects_a_non_positive_target() -> None:
    with pytest.raises(ValueError, match="positive"):
        unit_normal_loss_inverse(0.0)


def test_loss_inverse_widens_its_bracket_for_a_tiny_target() -> None:
    """A demanding fill rate needs a large z, which a fixed bracket would silently truncate."""
    z = unit_normal_loss_inverse(1e-12)
    assert z > 6.0
    assert unit_normal_loss(z) == pytest.approx(1e-12, rel=1e-6)


def test_empirical_quantile_and_its_guards() -> None:
    assert empirical_quantile([1.0, 2.0, 3.0, 4.0], 0.5) == pytest.approx(2.5)
    with pytest.raises(ValueError, match="empty"):
        empirical_quantile([], 0.5)
    with pytest.raises(ValueError, match="between 0 and 1"):
        empirical_quantile([1.0, 2.0], 1.5)
