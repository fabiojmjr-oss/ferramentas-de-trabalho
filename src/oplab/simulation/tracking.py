"""Instrumenting a resource.

SimPy does not collect statistics, and the statistics are the point. Two are collected here:

**Utilisation**, defined as work performed over capacity available. Both halves of that
fraction count only open hours. Getting either half wrong produces a number that is not a
utilisation at all: divide by wall-clock time and every resource on a single shift looks idle;
count held-but-closed time as work and the figure exceeds 100%, because a task interrupted by
the shift break keeps its resource overnight.

**Time held while closed**, reported separately. For a dock that is the real quantity - a
trailer parked on a door overnight is detention, and it is not available at opening. For labour
it is an artefact of the model holding a resource across an interruption, and is reported so
that artefact stays visible rather than contaminating the utilisation.

**Waiting time**, per acquisition. This is what ranks constraints. Utilisation says how busy a
resource is; total waiting time says how much the rest of the operation paid for it, and the
two do not always point at the same resource.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import numpy as np
import simpy

from .config import SimConfig
from .shift import open_hours_in_window


class TrackedResource:
    """A SimPy resource that records its own utilisation and waiting times.

    Attributes:
        name: Resource name, used in reports.
        capacity: Number of parallel servers.
    """

    def __init__(self, env: simpy.Environment, config: SimConfig, name: str, capacity: int) -> None:
        if capacity < 1:
            raise ValueError(f"{name}: capacity must be at least 1")
        self.name = name
        self.capacity = capacity
        self._env = env
        self._config = config
        self._resource = simpy.Resource(env, capacity=capacity)
        self._waits: list[float] = []
        self._busy_area = 0.0
        self._closed_area = 0.0
        self._in_use = 0
        self._last_change = env.now
        self._window_start = env.now

    def _accumulate(self) -> None:
        """Integrate occupancy since the last change, splitting open from closed time."""
        now = self._env.now
        if self._in_use and now > self._last_change:
            elapsed = now - self._last_change
            open_hours = open_hours_in_window(self._last_change, now, self._config)
            self._busy_area += self._in_use * open_hours
            self._closed_area += self._in_use * (elapsed - open_hours)
        self._last_change = now

    def acquire(self) -> Generator[Any, None, simpy.resources.resource.Request]:
        """Request the resource, recording how long the wait was.

        Use as ``request = yield from resource.acquire()``.
        """
        request = self._resource.request()
        queued_at = self._env.now
        yield request
        self._waits.append(self._env.now - queued_at)
        self._accumulate()
        self._in_use += 1
        return request

    def release(self, request: simpy.resources.resource.Request) -> None:
        """Release a previously acquired request."""
        self._accumulate()
        self._in_use -= 1
        self._resource.release(request)

    def reset(self) -> None:
        """Discard statistics collected so far and restart the measurement window.

        Called at the end of the warm-up. A simulation that starts empty reports a shorter
        queue than the operation ever has, and that transient contaminates every average.
        """
        self._accumulate()
        self._waits.clear()
        self._busy_area = 0.0
        self._closed_area = 0.0
        self._window_start = self._env.now

    def statistics(self) -> dict[str, float]:
        """Utilisation and waiting time over the measurement window.

        Returns:
            ``capacity``, ``utilisation``, ``held_while_closed_h``, ``acquisitions``,
            ``mean_wait_h``, ``p90_wait_h``, ``max_wait_h`` and ``total_wait_h``.
        """
        self._accumulate()
        open_hours = open_hours_in_window(self._window_start, self._env.now, self._config)
        waits = np.asarray(self._waits, dtype=float)
        capacity_hours = self.capacity * open_hours
        return {
            "capacity": float(self.capacity),
            "utilisation": self._busy_area / capacity_hours if capacity_hours else float("nan"),
            "held_while_closed_h": self._closed_area,
            "acquisitions": float(waits.size),
            "mean_wait_h": float(waits.mean()) if waits.size else 0.0,
            "p90_wait_h": float(np.quantile(waits, 0.9)) if waits.size else 0.0,
            "max_wait_h": float(waits.max()) if waits.size else 0.0,
            "total_wait_h": float(waits.sum()),
        }
