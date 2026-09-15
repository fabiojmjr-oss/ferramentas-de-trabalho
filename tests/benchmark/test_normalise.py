"""Scale normalisation and indirect standardisation."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.benchmark import indirect_standardisation, scale_normalise


@pytest.fixture
def two_sites() -> pd.DataFrame:
    """Two sites with identical rates within each stratum and opposite mixes.

    Both sites cost 50 per short delivery and 150 per long one. Site A does 90 short and 10
    long; site B does 10 short and 90 long. Their crude cost per delivery differs by a factor
    of nearly three, and **neither is better run than the other** - the entire gap is mix. This
    is the case indirect standardisation has to collapse to nothing.
    """
    return pd.DataFrame(
        [
            {"site": "A", "band": "short", "cost": 90 * 50.0, "deliveries": 90},
            {"site": "A", "band": "long", "cost": 10 * 150.0, "deliveries": 10},
            {"site": "B", "band": "short", "cost": 10 * 50.0, "deliveries": 10},
            {"site": "B", "band": "long", "cost": 90 * 150.0, "deliveries": 90},
        ]
    )


def test_standardisation_removes_a_pure_mix_difference(two_sites: pd.DataFrame) -> None:
    result = indirect_standardisation(two_sites, "site", "band", "cost", "deliveries").set_index(
        "site"
    )

    # Crude: A pays 60 per delivery, B pays 140.
    assert result.loc["A", "crude_rate"] == pytest.approx(60.0)
    assert result.loc["B", "crude_rate"] == pytest.approx(140.0)

    # Standardised: both sit exactly on the network expectation, so the ratio is one and the
    # standardised rate is the network average of 100 for both.
    assert result.loc["A", "standardised_ratio"] == pytest.approx(1.0)
    assert result.loc["B", "standardised_ratio"] == pytest.approx(1.0)
    assert result.loc["A", "standardised_rate"] == pytest.approx(100.0)
    assert result.loc["B", "standardised_rate"] == pytest.approx(100.0)


def test_a_real_rate_difference_survives_standardisation(two_sites: pd.DataFrame) -> None:
    """Site B made 20% more expensive in every stratum must come out 20% worse - but only when
    it is compared against the rest of the network rather than against itself.

    With the benchmark including the unit, B's own inflated cost drags the standard towards it
    and the ratio reads 1.02 instead of 1.20. That compression is negligible on a large network
    and is most of the signal on a small one, which is what ``exclude_self`` is for.
    """
    worse = two_sites.copy()
    worse.loc[worse["site"] == "B", "cost"] *= 1.2

    included = indirect_standardisation(worse, "site", "band", "cost", "deliveries").set_index(
        "site"
    )
    excluded = indirect_standardisation(
        worse, "site", "band", "cost", "deliveries", exclude_self=True
    ).set_index("site")

    assert included.loc["B", "standardised_ratio"] == pytest.approx(1.022, abs=1e-3)
    assert excluded.loc["B", "standardised_ratio"] == pytest.approx(1.2, abs=1e-9)
    assert excluded.loc["A", "standardised_ratio"] == pytest.approx(1.0 / 1.2, abs=1e-9)
    assert excluded.loc["B", "standardised_ratio"] > included.loc["B", "standardised_ratio"]


def test_excluding_self_still_collapses_a_pure_mix_difference(two_sites: pd.DataFrame) -> None:
    result = indirect_standardisation(
        two_sites, "site", "band", "cost", "deliveries", exclude_self=True
    ).set_index("site")
    assert result.loc["A", "standardised_ratio"] == pytest.approx(1.0)
    assert result.loc["B", "standardised_ratio"] == pytest.approx(1.0)


def test_the_mix_effect_is_the_difference_between_crude_and_adjusted(
    two_sites: pd.DataFrame,
) -> None:
    result = indirect_standardisation(two_sites, "site", "band", "cost", "deliveries").set_index(
        "site"
    )
    for site in ("A", "B"):
        assert result.loc[site, "mix_effect"] == pytest.approx(
            result.loc[site, "standardised_rate"] - result.loc[site, "crude_rate"]
        )
    # A looks cheap because its mix is easy; the adjustment moves it the other way.
    assert result.loc["A", "mix_effect"] > 0
    assert result.loc["B", "mix_effect"] < 0


def test_exposure_and_observed_are_carried_through(two_sites: pd.DataFrame) -> None:
    result = indirect_standardisation(two_sites, "site", "band", "cost", "deliveries").set_index(
        "site"
    )
    assert result.loc["A", "exposure"] == 100
    assert result.loc["A", "observed"] == pytest.approx(6000.0)
    assert result["expected"].sum() == pytest.approx(result["observed"].sum())


@pytest.mark.parametrize("missing", ["site", "band", "cost", "deliveries"])
def test_missing_columns_are_reported(two_sites: pd.DataFrame, missing: str) -> None:
    with pytest.raises(KeyError, match=missing):
        indirect_standardisation(
            two_sites.drop(columns=[missing]), "site", "band", "cost", "deliveries"
        )


def test_an_empty_frame_is_refused(two_sites: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="observations is empty"):
        indirect_standardisation(two_sites.iloc[:0], "site", "band", "cost", "deliveries")


def test_scale_normalise_divides_by_size() -> None:
    frame = pd.DataFrame({"site": ["A", "B"], "cost": [1000.0, 500.0], "orders": [100, 25]})
    result = scale_normalise(frame, ["cost"], "orders")
    assert list(result["cost_per_unit"]) == [10.0, 20.0]


def test_scale_normalise_refuses_a_non_positive_scale() -> None:
    frame = pd.DataFrame({"site": ["A"], "cost": [1.0], "orders": [0]})
    with pytest.raises(ValueError, match="must be positive"):
        scale_normalise(frame, ["cost"], "orders")


def test_scale_normalise_reports_a_missing_column() -> None:
    frame = pd.DataFrame({"site": ["A"], "cost": [1.0]})
    with pytest.raises(KeyError, match="orders"):
        scale_normalise(frame, ["cost"], "orders")


def test_geography_explains_half_the_network_cost_gap(dataset) -> None:  # type: ignore[no-untyped-def]
    """On the generated network, more than half the cost-per-order spread is where the
    customers are rather than how the site is run."""
    ledger = dataset.cost_ledger.copy()
    ledger["band"] = pd.cut(
        ledger["distance_km"],
        [0, 10, 25, 50, float("inf")],
        labels=["0-10 km", "10-25 km", "25-50 km", "50+ km"],
    ).astype(str)
    aggregated = (
        ledger.groupby(["site", "band"], observed=True)
        .agg(cost=("total_brl", "sum"), deliveries=("order_id", "size"))
        .reset_index()
    )
    result = indirect_standardisation(aggregated, "site", "band", "cost", "deliveries")

    crude_spread = result["crude_rate"].max() - result["crude_rate"].min()
    adjusted_spread = result["standardised_rate"].max() - result["standardised_rate"].min()
    assert adjusted_spread < crude_spread
    assert 1 - adjusted_spread / crude_spread > 0.3
