"""Composite scoring and rank stability."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.benchmark import composite_index, peer_z_scores, rank_stability

METRICS = ["service", "cost"]
DIRECTION = {"service": True, "cost": False}


@pytest.fixture
def two_metrics() -> pd.DataFrame:
    """Four units where service and cost disagree, so the weighting decides the ranking.

    A is best on service and worst on cost; D is the reverse. No weighting can make both of
    them first, and every weighting makes one of them first - which is exactly the situation a
    scorecard hides.
    """
    return pd.DataFrame(
        {
            "site": ["A", "B", "C", "D"],
            "service": [0.95, 0.85, 0.75, 0.65],
            "cost": [100.0, 90.0, 80.0, 70.0],
        }
    )


def test_direction_is_applied_so_higher_is_always_better(two_metrics: pd.DataFrame) -> None:
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site").set_index("site")

    # A has the best service and the worst cost, so its two z-scores must have opposite signs.
    assert scores.loc["A", "z_service"] > 0
    assert scores.loc["A", "z_cost"] < 0
    assert scores.loc["D", "z_service"] < 0
    assert scores.loc["D", "z_cost"] > 0


def test_z_scores_are_centred_and_scaled(two_metrics: pd.DataFrame) -> None:
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site")
    for metric in METRICS:
        assert scores[f"z_{metric}"].mean() == pytest.approx(0.0, abs=1e-9)
        assert abs(scores[f"z_{metric}"].std(ddof=1)) == pytest.approx(1.0, abs=1e-9)


def test_an_undeclared_direction_is_refused(two_metrics: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="no direction declared"):
        peer_z_scores(two_metrics, METRICS, {"service": True}, unit="site")


def test_a_missing_column_is_reported(two_metrics: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="margin"):
        peer_z_scores(two_metrics, ["margin"], {"margin": True}, unit="site")


def test_peer_groups_standardise_within_group() -> None:
    frame = pd.DataFrame(
        {
            "site": ["A", "B", "C", "D"],
            "region": ["north", "north", "south", "south"],
            "service": [0.9, 0.8, 0.5, 0.4],
            "cost": [100.0, 90.0, 80.0, 70.0],
        }
    )
    scores = peer_z_scores(frame, METRICS, DIRECTION, unit="site", group="region").set_index("site")
    # Within its own region A and C are both the better performer on service, so both score
    # positively even though C is worse than A in absolute terms.
    assert scores.loc["A", "z_service"] > 0
    assert scores.loc["C", "z_service"] > 0


def test_the_weighting_decides_the_winner(two_metrics: pd.DataFrame) -> None:
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site")

    service_heavy = composite_index(scores, METRICS, {"service": 0.9, "cost": 0.1}, unit="site")
    cost_heavy = composite_index(scores, METRICS, {"service": 0.1, "cost": 0.9}, unit="site")

    assert service_heavy.iloc[0]["site"] == "A"
    assert cost_heavy.iloc[0]["site"] == "D"


def test_equal_weights_are_a_choice_not_a_default(two_metrics: pd.DataFrame) -> None:
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site")
    equal = composite_index(scores, METRICS, unit="site")
    # The two metrics are exactly opposed here, so equal weights make every unit identical.
    assert equal["composite"].std(ddof=1) == pytest.approx(0.0, abs=1e-9)


def test_composite_requires_standardised_columns(two_metrics: pd.DataFrame) -> None:
    with pytest.raises(KeyError, match="run peer_z_scores first"):
        composite_index(two_metrics, METRICS, unit="site")


def test_weights_must_sum_to_something(two_metrics: pd.DataFrame) -> None:
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site")
    with pytest.raises(ValueError, match="positive value"):
        composite_index(scores, METRICS, {"service": 0.0, "cost": 0.0}, unit="site")


def test_rank_stability_exposes_a_weighting_dependent_ranking(
    two_metrics: pd.DataFrame,
) -> None:
    """With two opposed metrics, every unit's rank depends on the weighting."""
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site")
    stability = rank_stability(scores, METRICS, unit="site", draws=500).set_index("site")

    assert (stability["best_rank"] < stability["worst_rank"]).all()
    assert stability.loc["A", "best_rank"] == 1
    assert stability.loc["D", "best_rank"] == 1
    assert stability["share_first"].sum() == pytest.approx(1.0)


def test_rank_stability_reports_a_dominated_unit_as_locked() -> None:
    """When one unit is best on every metric, no weighting can move it."""
    frame = pd.DataFrame(
        {
            "site": ["best", "middle", "worst"],
            "service": [0.95, 0.85, 0.75],
            "cost": [70.0, 80.0, 90.0],
        }
    )
    scores = peer_z_scores(frame, METRICS, DIRECTION, unit="site")
    stability = rank_stability(scores, METRICS, unit="site", draws=300).set_index("site")

    assert stability.loc["best", "share_first"] == pytest.approx(1.0)
    assert stability.loc["best", "best_rank"] == stability.loc["best", "worst_rank"] == 1
    assert stability.loc["worst", "share_last"] == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({"draws": 0}, "draws must be positive"), ({"concentration": 0.0}, "concentration")],
)
def test_rank_stability_validates_its_arguments(
    two_metrics: pd.DataFrame, kwargs: dict[str, float], message: str
) -> None:
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site")
    with pytest.raises(ValueError, match=message):
        rank_stability(scores, METRICS, unit="site", **kwargs)  # type: ignore[arg-type]


def test_rank_stability_is_reproducible(two_metrics: pd.DataFrame) -> None:
    scores = peer_z_scores(two_metrics, METRICS, DIRECTION, unit="site")
    first = rank_stability(scores, METRICS, unit="site", draws=200)
    second = rank_stability(scores, METRICS, unit="site", draws=200)
    pd.testing.assert_frame_equal(first, second)
