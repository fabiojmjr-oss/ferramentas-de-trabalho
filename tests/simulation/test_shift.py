"""The shift calendar, on cases computed by hand.

Every expected value here is arithmetic a planner can check on paper. The shift logic is the
part of the model that makes a longer shift a real lever rather than a rescaling, so it is
tested directly rather than through the model's output.
"""

from __future__ import annotations

import pytest
import simpy

from oplab.simulation import (
    SimConfig,
    hours_until_open,
    open_hours_in_window,
    open_hours_remaining,
)
from oplab.simulation.shift import perform

# Open 06:00 to 14:00.
SHIFT = SimConfig(shift_start_h=6.0, shift_hours=8.0, days=4, warmup_days=0)
CONTINUOUS = SimConfig(shift_hours=24.0, shift_start_h=0.0, days=4, warmup_days=0)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (0.0, 6.0),  # midnight, opens in six hours
        (5.5, 0.5),
        (6.0, 0.0),  # open
        (13.9, 0.0),
        (14.0, 16.0),  # just closed, opens tomorrow at 06:00
        (20.0, 10.0),
        (30.0, 0.0),  # 06:00 on day two
    ],
)
def test_hours_until_open(now: float, expected: float) -> None:
    assert hours_until_open(now, SHIFT) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("now", "expected"),
    [(0.0, 0.0), (6.0, 8.0), (10.0, 4.0), (13.5, 0.5), (14.0, 0.0), (23.0, 0.0)],
)
def test_open_hours_remaining(now: float, expected: float) -> None:
    assert open_hours_remaining(now, SHIFT) == pytest.approx(expected)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (0.0, 24.0, 8.0),  # one full day
        (0.0, 48.0, 16.0),  # two
        (10.0, 12.0, 2.0),  # entirely inside the shift
        (0.0, 6.0, 0.0),  # entirely before it
        (13.0, 20.0, 1.0),  # straddling the close
        (20.0, 30.0, 0.0),  # overnight, opening exactly at the end
        (20.0, 31.0, 1.0),
        (12.0, 12.0, 0.0),  # empty window
        (12.0, 10.0, 0.0),  # reversed window
    ],
)
def test_open_hours_in_window(start: float, end: float, expected: float) -> None:
    assert open_hours_in_window(start, end, SHIFT) == pytest.approx(expected)


def test_a_continuous_operation_never_closes() -> None:
    assert hours_until_open(3.0, CONTINUOUS) == 0.0
    assert open_hours_remaining(3.0, CONTINUOUS) == float("inf")
    assert open_hours_in_window(0.0, 30.0, CONTINUOUS) == pytest.approx(30.0)


def test_work_pauses_overnight_and_resumes_at_opening() -> None:
    """Five hours of work starting at noon finishes at 09:00 the next day.

    Two hours fit before the 14:00 close; the remaining three run from 06:00, so the task
    completes at hour 33 of the simulation rather than hour 17. A model without this cannot
    evaluate a longer shift, because it never runs out of day.
    """
    env = simpy.Environment()
    finished: list[float] = []

    def task() -> object:
        yield env.timeout(12.0)
        yield from perform(env, SHIFT, 5.0)
        finished.append(env.now)

    env.process(task())
    env.run(until=96.0)

    assert finished == [pytest.approx(33.0)]


def test_work_starting_while_closed_waits_for_opening() -> None:
    env = simpy.Environment()
    finished: list[float] = []

    def task() -> object:
        yield env.timeout(2.0)  # 02:00, closed
        yield from perform(env, SHIFT, 1.0)
        finished.append(env.now)

    env.process(task())
    env.run(until=48.0)

    assert finished == [pytest.approx(7.0)]


def test_work_spanning_several_shifts_is_split_correctly() -> None:
    """Twenty hours of work on an eight-hour shift takes three days to finish."""
    env = simpy.Environment()
    finished: list[float] = []

    def task() -> object:
        yield env.timeout(6.0)
        yield from perform(env, SHIFT, 20.0)
        finished.append(env.now)

    env.process(task())
    env.run(until=200.0)

    # 8 hours on day one, 8 on day two, 4 on day three ending at 10:00 = 48 + 10.
    assert finished == [pytest.approx(58.0)]


def test_zero_work_completes_immediately() -> None:
    env = simpy.Environment()
    finished: list[float] = []

    def task() -> object:
        yield env.timeout(7.0)
        yield from perform(env, SHIFT, 0.0)
        finished.append(env.now)

    env.process(task())
    env.run(until=24.0)
    assert finished == [pytest.approx(7.0)]


def test_negative_work_is_refused() -> None:
    env = simpy.Environment()

    def task() -> object:
        yield from perform(env, SHIFT, -1.0)

    env.process(task())
    with pytest.raises(ValueError, match="cannot be negative"):
        env.run(until=1.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"days": 0}, "days must be at least 1"),
        ({"warmup_days": 30}, "warmup_days"),
        ({"shift_start_h": 25.0}, "shift_start_h"),
        ({"shift_hours": 0.0}, "shift_hours"),
        ({"shift_start_h": 20.0, "shift_hours": 8.0}, "must not cross midnight"),
        ({"absenteeism": 1.0}, "absenteeism"),
        ({"release_waves": 0}, "release_waves"),
        ({"service_cv": -0.1}, "service_cv"),
        ({"pickers": 0}, "pickers must be at least 1"),
    ],
)
def test_config_validation(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        SimConfig(**kwargs)  # type: ignore[arg-type]


def test_absenteeism_never_empties_a_team() -> None:
    config = SimConfig(absenteeism=0.95)
    assert config.staffed(4) == 1


def test_static_utilisation_matches_the_hand_calculation() -> None:
    """900 orders a day at 2.56 checking minutes each, against five stations on an 8h shift."""
    config = SimConfig()
    check_minutes = 900 * (1.6 + 3.2 * 0.3)
    assert config.static_utilisation()["checking"] == pytest.approx(check_minutes / (5 * 8 * 60))
    assert config.static_utilisation()["checking"] == pytest.approx(0.96)
