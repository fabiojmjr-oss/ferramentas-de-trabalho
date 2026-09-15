"""Control chart constants against published tables."""

from __future__ import annotations

import pytest

from oplab.spc import a2, c4, d2, d3, d4, e2
from oplab.spc.constants import MAX_SUBGROUP, MIN_SUBGROUP


@pytest.mark.parametrize(
    ("n", "expected"),
    [(2, 1.880), (3, 1.023), (5, 0.577), (10, 0.308), (25, 0.153)],
)
def test_a2_matches_the_published_table(n: int, expected: float) -> None:
    assert a2(n) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("n", "expected"),
    [(2, 1.128), (3, 1.693), (5, 2.326), (10, 3.078), (25, 3.931)],
)
def test_d2_matches_the_published_table(n: int, expected: float) -> None:
    assert d2(n) == pytest.approx(expected)


@pytest.mark.parametrize(("n", "expected"), [(2, 3.267), (5, 2.114), (10, 1.777)])
def test_d4_matches_the_published_table(n: int, expected: float) -> None:
    assert d4(n) == pytest.approx(expected)


def test_d3_is_zero_below_subgroup_size_seven() -> None:
    assert all(d3(n) == 0.0 for n in range(2, 7))
    assert d3(7) > 0.0


@pytest.mark.parametrize(
    ("n", "expected"),
    [(2, 0.7979), (3, 0.8862), (5, 0.9400), (10, 0.9727), (25, 0.9896)],
)
def test_c4_closed_form_matches_the_published_table(n: int, expected: float) -> None:
    assert c4(n) == pytest.approx(expected, abs=5e-5)


def test_c4_approaches_one_as_the_subgroup_grows() -> None:
    assert c4(2) < c4(10) < c4(25) < 1.0


def test_e2_is_the_conventional_2_66() -> None:
    assert e2() == pytest.approx(2.66, abs=5e-3)


@pytest.mark.parametrize("n", [1, 0, -3, MAX_SUBGROUP + 1])
def test_untabulated_subgroup_sizes_are_rejected(n: int) -> None:
    with pytest.raises(ValueError):
        a2(n)


def test_c4_rejects_a_subgroup_of_one() -> None:
    with pytest.raises(ValueError, match="c4 requires"):
        c4(MIN_SUBGROUP - 1)
