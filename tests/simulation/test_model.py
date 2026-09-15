"""The model and its instrumentation."""

from __future__ import annotations

import pytest
import simpy

from oplab.simulation import SimConfig, run_once
from oplab.simulation.shift import perform
from oplab.simulation.tracking import TrackedResource


def test_utilisation_counts_work_over_open_capacity() -> None:
    """Four hours of work on one server, on an eight-hour shift, is exactly 50%.

    The denominator is open hours, not wall-clock hours. Getting that wrong on a single-shift
    operation reports a third of the real figure.
    """
    config = SimConfig(shift_start_h=6.0, shift_hours=8.0, days=1, warmup_days=0)
    env = simpy.Environment()
    resource = TrackedResource(env, config, "station", 1)

    def task() -> object:
        yield env.timeout(6.0)
        request = yield from resource.acquire()
        yield from perform(env, config, 4.0)
        resource.release(request)

    env.process(task())
    env.run(until=24.0)

    statistics = resource.statistics()
    assert statistics["utilisation"] == pytest.approx(0.5)
    assert statistics["held_while_closed_h"] == pytest.approx(0.0)


def test_time_held_across_the_break_is_reported_separately() -> None:
    """A resource taken at 13:00 and held until 07:00 is closed for 16 of those hours.

    Counting that as work would put utilisation above 100%, which is how a model reports a
    number that cannot exist.
    """
    config = SimConfig(shift_start_h=6.0, shift_hours=8.0, days=2, warmup_days=0)
    env = simpy.Environment()
    resource = TrackedResource(env, config, "dock", 1)

    def task() -> object:
        yield env.timeout(13.0)
        request = yield from resource.acquire()
        yield from perform(env, config, 2.0)  # 1 hour today, 1 tomorrow
        resource.release(request)

    env.process(task())
    env.run(until=48.0)

    statistics = resource.statistics()
    assert statistics["utilisation"] <= 1.0
    assert statistics["held_while_closed_h"] == pytest.approx(16.0)


def test_waiting_time_is_recorded_per_acquisition() -> None:
    config = SimConfig(shift_hours=24.0, shift_start_h=0.0, days=1, warmup_days=0)
    env = simpy.Environment()
    resource = TrackedResource(env, config, "station", 1)

    def task(delay: float) -> object:
        yield env.timeout(delay)
        request = yield from resource.acquire()
        yield from perform(env, config, 2.0)
        resource.release(request)

    env.process(task(0.0))
    env.process(task(0.0))  # queues behind the first for two hours
    env.run(until=24.0)

    statistics = resource.statistics()
    assert statistics["acquisitions"] == 2
    assert statistics["max_wait_h"] == pytest.approx(2.0)
    assert statistics["total_wait_h"] == pytest.approx(2.0)


def test_capacity_below_one_is_refused() -> None:
    env = simpy.Environment()
    with pytest.raises(ValueError, match="capacity must be at least 1"):
        TrackedResource(env, SimConfig(), "broken", 0)


def test_the_same_seed_reproduces_the_run(small: SimConfig) -> None:
    first, second = run_once(small), run_once(small)
    assert first.resources.equals(second.resources)
    assert len(first.orders) == len(second.orders)


def test_a_different_seed_changes_the_run(small: SimConfig) -> None:
    from dataclasses import replace

    other = run_once(replace(small, seed=small.seed + 1))
    assert len(other.orders) != len(run_once(small).orders)


def test_utilisation_never_exceeds_one(small: SimConfig) -> None:
    result = run_once(small)
    assert (result.resources["utilisation"] <= 1.0).all()
    assert (result.resources["utilisation"] >= 0.0).all()


def test_the_warmup_is_excluded(small: SimConfig) -> None:
    result = run_once(small)
    measurement_start = small.warmup_days * 24.0
    assert (result.orders["released"] >= measurement_start).all()
    assert (result.trucks["arrival"] >= measurement_start).all()


def test_flow_stages_add_up_to_the_cycle_time(small: SimConfig) -> None:
    flow = run_once(small).order_flow().set_index("stage")
    parts = flow.loc[
        ["wait_for_picker_h", "picking_h", "wait_for_checker_h", "checking_h"], "mean_h"
    ].sum()
    assert parts == pytest.approx(flow.loc["total_cycle_h", "mean_h"], rel=1e-9)


def test_truck_stages_add_up_to_dwell(small: SimConfig) -> None:
    flow = run_once(small).truck_flow().set_index("stage")
    parts = flow.loc[["yard_wait_h", "unload_wait_h", "unloading_h"], "mean_h"].sum()
    assert parts == pytest.approx(flow.loc["truck_dwell_h", "mean_h"], rel=1e-9)


def test_an_overloaded_configuration_reports_a_backlog(small: SimConfig) -> None:
    """Halving checking capacity below the load must show up as unfinished work.

    An over-committed operation does not announce itself with a large cycle time. It
    accumulates a backlog, and any average taken over the orders that did finish is then
    computed on a biased sample.
    """
    from dataclasses import replace

    overloaded = replace(small, orders_per_day=600.0, checkers=1)
    result = run_once(overloaded)

    assert result.orders_unfinished > 0
    assert result.backlog_share > 0.1
    assert result.throughput()["orders_packed_per_day"] < 600.0


def test_a_feasible_configuration_clears_almost_everything(small: SimConfig) -> None:
    result = run_once(small)
    assert result.backlog_share < 0.05


def test_the_bottleneck_is_ranked_by_waiting_not_utilisation() -> None:
    """On the default operation the two orderings disagree, and that is the point.

    Picking sits at a comfortable load and is still where the operation waits most, because
    orders are released to it in waves. Managing to a utilisation target would send the
    investment to checking.
    """
    result = run_once(SimConfig())
    ranks = result.utilisation_ranks_nothing().set_index("resource")

    assert result.bottleneck()["resource"] == "picking"
    assert ranks.loc["picking", "utilisation"] < ranks.loc["checking", "utilisation"]
    assert ranks.loc["picking", "total_wait_h"] > ranks.loc["checking", "total_wait_h"]
    assert ranks["rank_disagreement"].max() > 0


def test_capacity_review_agrees_with_the_spreadsheet_on_utilisation() -> None:
    """Utilisation is conserved, so a spreadsheet gets it right - and still cannot decide."""
    review = run_once(SimConfig()).capacity_review().set_index("resource")
    for resource in review.index:
        assert review.loc[resource, "utilisation"] == pytest.approx(
            review.loc[resource, "static_utilisation"], abs=0.02
        )
    assert "total_wait_h" in review.columns


def test_bottleneck_requires_statistics() -> None:
    import pandas as pd

    from oplab.simulation.results import SimResult

    empty = SimResult(
        config=SimConfig(),
        resources=pd.DataFrame(),
        trucks=pd.DataFrame(),
        orders=pd.DataFrame(),
        trucks_released=0,
        orders_released=0,
    )
    with pytest.raises(ValueError, match="no resource statistics"):
        empty.bottleneck()
    assert empty.backlog_share == 0.0
