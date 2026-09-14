"""The shift calendar.

Work stops when the operation closes. That sounds trivial and it is the difference between a
model that can evaluate a longer shift and one that cannot: a task with two hours left at
closing time does not finish two hours later, it finishes two hours into the next morning, and
everything queued behind it waits overnight too.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import simpy

from .config import SimConfig

EPSILON = 1e-9
NUDGE = 1e-6


def is_continuous(config: SimConfig) -> bool:
    """Whether the operation never closes."""
    return config.shift_hours >= 24.0


def hours_until_open(now: float, config: SimConfig) -> float:
    """Hours from ``now`` until the operation is open. Zero when it already is."""
    if is_continuous(config):
        return 0.0
    hour_of_day = now % 24.0
    start = config.shift_start_h
    end = start + config.shift_hours
    if hour_of_day < start:
        return start - hour_of_day
    if hour_of_day < end - EPSILON:
        return 0.0
    return 24.0 - hour_of_day + start


def open_hours_remaining(now: float, config: SimConfig) -> float:
    """Hours of open time left today from ``now``. Zero when the operation is closed."""
    if is_continuous(config):
        return float("inf")
    hour_of_day = now % 24.0
    start = config.shift_start_h
    end = start + config.shift_hours
    if hour_of_day < start or hour_of_day >= end:
        return 0.0
    return end - hour_of_day


def open_hours_in_window(start: float, end: float, config: SimConfig) -> float:
    """Total open hours between two absolute times.

    This is the denominator for utilisation. Dividing busy time by wall-clock time on a
    single-shift operation reports a third of the real figure and makes every resource look
    idle.
    """
    if end <= start:
        return 0.0
    if is_continuous(config):
        return end - start

    total = 0.0
    day = int(start // 24.0)
    while day * 24.0 < end:
        shift_open = day * 24.0 + config.shift_start_h
        shift_close = shift_open + config.shift_hours
        total += max(0.0, min(end, shift_close) - max(start, shift_open))
        day += 1
    return total


def perform(
    env: simpy.Environment, config: SimConfig, work_hours: float
) -> Generator[Any, None, None]:
    """Consume ``work_hours`` of effort, pausing while the operation is closed.

    Args:
        env: Simulation environment.
        config: Configuration supplying the shift calendar.
        work_hours: Effort required, in hours.

    Yields:
        Timeout events until the work is complete.
    """
    if work_hours < 0.0:
        raise ValueError("work_hours cannot be negative")

    remaining = work_hours
    while remaining > EPSILON:
        wait = hours_until_open(env.now, config)
        if wait > 0.0:
            yield env.timeout(wait)
        available = open_hours_remaining(env.now, config)
        if available <= EPSILON:
            # Floating point can land exactly on the closing instant; step past it so the next
            # iteration sees a closed operation and waits properly.
            yield env.timeout(NUDGE)
            continue
        chunk = min(remaining, available)
        yield env.timeout(chunk)
        remaining -= chunk
