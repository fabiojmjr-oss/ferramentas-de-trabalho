"""Replication and scenario comparison.

The property under test is discipline rather than arithmetic: a stochastic model must not
report a point estimate as an answer, and must not declare a winner on overlapping intervals.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from oplab.simulation import SimConfig, compare_scenarios, replicate


def test_replicate_reports_an_interval_around_every_metric(small: SimConfig) -> None:
    summary = replicate(small, replications=4).set_index("metric")

    assert (summary["replications"] == 4).all()
    assert (summary["ci_low"] <= summary["mean"]).all()
    assert (summary["mean"] <= summary["ci_high"]).all()
    for metric in ("order_cycle_mean_h", "backlog_share", "utilisation_picking"):
        assert metric in summary.index


def test_more_replications_narrow_the_interval(small: SimConfig) -> None:
    """The interval must shrink roughly with the square root of the replication count.

    This is the reason a single run cannot support a capital decision: with one sample there is
    no interval at all, and two configurations that differ only by noise look different.
    """
    few = replicate(small, replications=3).set_index("metric")
    many = replicate(small, replications=12).set_index("metric")
    assert (
        many.loc["order_cycle_mean_h", "half_width"] < few.loc["order_cycle_mean_h", "half_width"]
    )


def test_a_deterministic_model_has_no_spread(small: SimConfig) -> None:
    """With the seed fixed and dispersion removed, replications still differ only by seed.

    Each replication uses a different seed, so arrival counts still vary; what must not vary is
    the model's response to a fixed input. Setting service_cv to zero removes service-time
    variability and the interval narrows accordingly.
    """
    variable = replicate(small, replications=4).set_index("metric")
    steady = replicate(replace(small, service_cv=0.0), replications=4).set_index("metric")
    assert steady.loc["order_cycle_mean_h", "std"] < variable.loc["order_cycle_mean_h", "std"]


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"replications": 1}, "at least 2 replications"),
        ({"confidence": 1.0}, "confidence must be between"),
        ({"confidence": 0.0}, "confidence must be between"),
    ],
)
def test_replicate_validates_its_arguments(
    small: SimConfig, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        replicate(small, **kwargs)  # type: ignore[arg-type]


def test_the_base_is_always_included_and_never_distinguishable(small: SimConfig) -> None:
    table = compare_scenarios(small, {"more pickers": {"pickers": 8}}, replications=3).set_index(
        "scenario"
    )

    assert "base" in table.index
    assert table.loc["base", "change_vs_base"] == pytest.approx(0.0)
    assert not bool(table.loc["base", "distinguishable"])


def test_a_change_with_no_effect_is_reported_as_indistinguishable(small: SimConfig) -> None:
    """Inbound and outbound share no resource in this model, so an inbound change cannot move
    an outbound metric. The comparison must say so rather than report the noise as a result."""
    table = compare_scenarios(
        small,
        {"more docks": {"inbound_docks": small.inbound_docks + 4}},
        metric="order_cycle_mean_h",
        replications=3,
    ).set_index("scenario")

    assert not bool(table.loc["more docks", "distinguishable"])
    assert table.loc["more docks", "mean"] == pytest.approx(table.loc["base", "mean"])


def test_a_real_improvement_is_distinguishable(small: SimConfig) -> None:
    congested = replace(small, orders_per_day=240.0, release_waves=1)
    table = compare_scenarios(
        congested, {"level the release": {"release_waves": 8}}, replications=4
    ).set_index("scenario")

    assert table.loc["level the release", "mean"] < table.loc["base", "mean"]
    assert bool(table.loc["level the release", "distinguishable"])


def test_scenarios_are_ranked_best_first(small: SimConfig) -> None:
    table = compare_scenarios(
        small,
        {"waves": {"release_waves": 6}, "pickers": {"pickers": 10}},
        replications=3,
    )
    assert table["mean"].is_monotonic_increasing


def test_an_unknown_field_is_refused(small: SimConfig) -> None:
    with pytest.raises(KeyError, match="unknown field"):
        compare_scenarios(small, {"typo": {"pickerz": 20}}, replications=2)


def test_an_unknown_metric_is_refused(small: SimConfig) -> None:
    with pytest.raises(KeyError, match="unknown metric"):
        compare_scenarios(small, {"a": {"pickers": 6}}, metric="profit", replications=2)


def test_backlog_is_carried_into_the_comparison(small: SimConfig) -> None:
    """A scenario that cannot keep up must be visible as a backlog, not only as a cycle time."""
    table = compare_scenarios(
        replace(small, orders_per_day=600.0),
        {"starve checking": {"checkers": 1}},
        replications=3,
    ).set_index("scenario")

    assert table.loc["starve checking", "backlog_share"] > table.loc["base", "backlog_share"]
    assert table.loc["starve checking", "backlog_share"] > 0.1
