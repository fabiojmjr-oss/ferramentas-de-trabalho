"""Capability and performance indices."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.spc import capability, capability_from_subgroups, sigma_within_from_subgroups

# Mean 100 exactly; sample standard deviation sqrt(10/4) = 1.5811.
CENTRED = pd.Series([98.0, 99.0, 100.0, 101.0, 102.0])


def test_centred_process_indices_match_the_hand_calculation() -> None:
    result = capability(CENTRED, lsl=94.0, usl=106.0, sigma_within=1.0)

    assert result.mean == pytest.approx(100.0)
    assert result.sigma_overall == pytest.approx(np.sqrt(2.5))
    assert result.cp == pytest.approx(2.0)
    assert result.cpk == pytest.approx(2.0), "a centred process has Cpk equal to Cp"
    assert result.pp == pytest.approx(6.0 / (3 * np.sqrt(2.5)))
    assert result.ppk == pytest.approx(result.pp)
    assert result.target == pytest.approx(100.0), "target defaults to the spec midpoint"


def test_off_centre_process_loses_cpk_but_keeps_cp() -> None:
    shifted = CENTRED + 2.0  # mean 102
    result = capability(shifted, lsl=94.0, usl=106.0, sigma_within=1.0)

    assert result.cp == pytest.approx(2.0), "Cp is blind to centring"
    assert result.cpu == pytest.approx(4.0 / 3.0)
    assert result.cpl == pytest.approx(8.0 / 3.0)
    assert result.cpk == pytest.approx(4.0 / 3.0), "Cpk takes the worse side"
    assert result.cpk < result.cp


def test_one_sided_specification_leaves_cp_and_pp_undefined() -> None:
    result = capability(CENTRED, usl=106.0, sigma_within=1.0)

    assert np.isnan(result.cp)
    assert np.isnan(result.pp)
    assert np.isnan(result.cpl)
    assert result.cpk == pytest.approx(result.cpu)
    assert result.cpk == pytest.approx(2.0)
    assert result.target is None


def test_gap_between_cpk_and_ppk_reveals_uncontrolled_drift() -> None:
    result = capability(CENTRED, lsl=94.0, usl=106.0, sigma_within=0.5)
    assert result.cpk > result.ppk, "short-term sigma below overall sigma implies drift"


def test_expected_defects_and_sigma_level_are_consistent() -> None:
    result = capability(CENTRED, lsl=94.0, usl=106.0, sigma_within=1.0)
    assert 0.0 < result.expected_ppm < 1e6
    assert result.sigma_level > 3.0


def test_normality_warning_fires_on_a_skewed_series() -> None:
    rng = np.random.default_rng(5)
    skewed = pd.Series(rng.exponential(2.0, size=500))
    result = capability(skewed, usl=20.0, sigma_within=2.0)
    assert result.normality_warning is not None
    assert "expected_ppm" in result.normality_warning


def test_no_warning_on_a_normal_series() -> None:
    rng = np.random.default_rng(5)
    result = capability(pd.Series(rng.normal(100.0, 1.0, size=500)), lsl=94.0, usl=106.0)
    assert result.normality_warning is None


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({}, "at least one specification limit"),
        ({"lsl": 106.0, "usl": 94.0}, "must be below"),
    ],
)
def test_specification_limits_are_validated(kwargs: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        capability(CENTRED, **kwargs)


def test_too_few_observations_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 2 observations"):
        capability(pd.Series([100.0]), usl=106.0)


def test_within_sigma_from_subgroups_uses_the_average_range() -> None:
    data = pd.DataFrame(
        {
            "subgroup": np.repeat([1, 2, 3], 5),
            "value": np.tile([1.0, 2.0, 3.0, 4.0, 5.0], 3),
        }
    )
    # Every range is 4, so the estimate is 4 / d2(5).
    assert sigma_within_from_subgroups(data, "value", "subgroup") == pytest.approx(4 / 2.326)


def test_within_sigma_rejects_ragged_subgroups() -> None:
    data = pd.DataFrame({"subgroup": [1, 1, 2], "value": [1.0, 2.0, 3.0]})
    with pytest.raises(ValueError, match="constant subgroup size"):
        sigma_within_from_subgroups(data, "value", "subgroup")


def test_subgroup_entry_point_separates_short_from_long_term(dataset) -> None:  # type: ignore[no-untyped-def]
    """On the generated data the injected shift must show up as Cpk above Ppk."""
    result = capability_from_subgroups(dataset.subgroups, lsl=492.0, usl=508.0)
    assert result.sigma_within < result.sigma_overall
    assert result.cpk > result.ppk
    assert result.to_series()["n"] == len(dataset.subgroups)
