"""Data envelopment analysis and its dimensional trap."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.benchmark import dea, discrimination_check


@pytest.fixture
def three_units() -> pd.DataFrame:
    """Three units on one input and one output, with a known frontier.

    A turns 1 unit of input into 1 of output, B turns 2 into 2, and C turns 2 into 1. Under
    constant returns to scale A and B are both on the frontier and C is exactly half as
    efficient, which is arithmetic rather than opinion.
    """
    return pd.DataFrame(
        {
            "site": ["A", "B", "C"],
            "cost": [1.0, 2.0, 2.0],
            "orders": [1.0, 2.0, 1.0],
        }
    )


def test_efficiency_matches_the_hand_calculation(three_units: pd.DataFrame) -> None:
    result = dea(three_units, ["cost"], ["orders"]).set_index("site")

    assert result.loc["A", "efficiency"] == pytest.approx(1.0)
    assert result.loc["B", "efficiency"] == pytest.approx(1.0)
    assert result.loc["C", "efficiency"] == pytest.approx(0.5)
    assert result.loc["C", "slack_share"] == pytest.approx(0.5)


def test_the_frontier_flag_follows_the_score(three_units: pd.DataFrame) -> None:
    result = dea(three_units, ["cost"], ["orders"]).set_index("site")
    assert bool(result.loc["A", "on_frontier"])
    assert not bool(result.loc["C", "on_frontier"])


def test_an_inefficient_unit_names_its_peers(three_units: pd.DataFrame) -> None:
    result = dea(three_units, ["cost"], ["orders"]).set_index("site")
    assert result.loc["C", "n_peers"] >= 1
    assert "A" in result.loc["C", "peers"] or "B" in result.loc["C", "peers"]


def test_variable_returns_do_not_charge_a_unit_for_its_size() -> None:
    """A small unit with the best ratio is efficient under both models; scale only matters when
    the frontier is not a straight line through the origin."""
    frame = pd.DataFrame({"site": ["small", "large"], "cost": [1.0, 10.0], "orders": [2.0, 10.0]})
    crs = dea(frame, ["cost"], ["orders"], returns_to_scale="crs").set_index("site")
    vrs = dea(frame, ["cost"], ["orders"], returns_to_scale="vrs").set_index("site")

    assert crs.loc["small", "efficiency"] == pytest.approx(1.0)
    assert vrs.loc["small", "efficiency"] == pytest.approx(1.0)
    # Under constant returns the large unit is judged against the small one's ratio and loses;
    # under variable returns it sits on its own part of the frontier.
    assert crs.loc["large", "efficiency"] < vrs.loc["large", "efficiency"]
    assert vrs.loc["large", "efficiency"] == pytest.approx(1.0)


def test_an_unknown_model_is_refused(three_units: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="must be 'crs' or 'vrs'"):
        dea(three_units, ["cost"], ["orders"], returns_to_scale="irs")


def test_non_positive_values_are_refused(three_units: pd.DataFrame) -> None:
    broken = three_units.copy()
    broken.loc[0, "cost"] = 0.0
    with pytest.raises(ValueError, match="strictly positive"):
        dea(broken, ["cost"], ["orders"])


def test_a_missing_column_is_reported(three_units: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="staff"):
        dea(three_units, ["staff"], ["orders"])


@pytest.mark.parametrize(
    ("units", "inputs", "outputs", "adequate", "minimum"),
    [
        (4, 2, 2, False, 12),
        (12, 2, 2, True, 12),
        (48, 2, 2, True, 12),
        (20, 4, 5, False, 27),
        (9, 1, 1, True, 6),
    ],
)
def test_discrimination_rules_of_thumb(
    units: int, inputs: int, outputs: int, adequate: bool, minimum: int
) -> None:
    check = discrimination_check(units, inputs, outputs)
    assert check.minimum_units == minimum
    assert check.adequate is adequate
    assert check.message


def test_the_check_warns_before_the_scores_are_read() -> None:
    check = discrimination_check(4, 2, 2)
    assert not check.adequate
    assert "weak discrimination" in check.message
    assert "site-months" in check.message


def test_the_check_validates_its_counts() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        discrimination_check(0, 1, 1)


def test_a_small_network_barely_discriminates(dataset) -> None:  # type: ignore[no-untyped-def]
    """Four sites with four measures put most of the network on the frontier, and the
    returns-to-scale choice moves individual scores more than the data does."""
    from oplab.kpi import line_service

    ledger = dataset.cost_ledger
    lines = line_service(dataset.order_lines)
    scoped = lines.loc[lines["in_scope"]]

    cost = ledger.groupby("site", observed=True).agg(
        freight_brl=("freight_brl", "sum"), handling_brl=("handling_brl", "sum")
    )
    service = scoped.groupby("site", observed=True).agg(
        otif_lines=("otif", "sum"), units=("qty_delivered", "sum")
    )
    sites = cost.join(service).reset_index()
    sites["otif_lines"] = sites["otif_lines"].astype(float)

    check = discrimination_check(len(sites), 2, 2)
    assert not check.adequate

    crs = dea(sites, ["freight_brl", "handling_brl"], ["otif_lines", "units"])
    vrs = dea(
        sites,
        ["freight_brl", "handling_brl"],
        ["otif_lines", "units"],
        returns_to_scale="vrs",
    )
    assert vrs["on_frontier"].mean() >= 0.5
    assert vrs["on_frontier"].mean() >= crs["on_frontier"].mean()

    # The worst site's score moves by more than twenty points on the modelling choice alone.
    worst_crs = crs["efficiency"].min()
    worst_vrs = vrs["efficiency"].min()
    assert worst_vrs - worst_crs > 0.15
