"""The distribution centre model.

Two flows share a shift calendar and nothing else, which is a modelling choice worth stating:
put-away operators and pickers are separate pools here. In an operation that cross-deploys
labour between inbound and outbound, the constraint moves differently and this model will
overstate how binding each one is on its own.

Inbound
    Truck arrives, waits for the yard to open, takes a dock, is unloaded, releases the dock.
    Put-away then happens from the staging area without holding the dock.

Outbound
    Orders are released to the floor in waves, picked, then checked and packed.

Outbound loading and dispatch are out of scope. So is replenishment from bulk to the pick
face, which in a real operation competes with picking for the same aisles.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import numpy as np
import simpy

from .config import SimConfig
from .shift import hours_until_open, perform
from .tracking import TrackedResource

MINUTES_PER_HOUR = 60.0
APPOINTMENT_DEVIATION_MEAN_MIN = 15.0
APPOINTMENT_DEVIATION_SD_MIN = 40.0


def _lognormal(rng: np.random.Generator, mean: float, cv: float) -> float:
    """Draw a positive service time with the given mean and coefficient of variation.

    Lognormal rather than normal because a task time cannot be negative, and rather than
    exponential because real task times have a mode: unloading a pallet is never instant.
    """
    if mean <= 0.0:
        return 0.0
    if cv <= 0.0:
        return mean
    sigma = np.sqrt(np.log(1.0 + cv**2))
    mu = np.log(mean) - 0.5 * sigma**2
    return float(rng.lognormal(mu, sigma))


class Recorder:
    """Collects completed entities and counts the ones that were created.

    The two counts must be compared. An over-committed configuration does not report a large
    number, it reports a backlog: orders released that never got picked before the horizon
    ended. Averaging cycle time over only the completed orders in that situation produces a
    reassuring figure computed from a biased sample, which is the most dangerous output a
    capacity model can give.
    """

    def __init__(self) -> None:
        self.trucks: list[dict[str, float]] = []
        self.orders: list[dict[str, float]] = []
        self.trucks_created = 0
        self.orders_created = 0


class Resources:
    """The five tracked resources of the model."""

    def __init__(self, env: simpy.Environment, config: SimConfig) -> None:
        self.inbound_dock = TrackedResource(
            env, config, "inbound_dock", config.staffed(config.inbound_docks)
        )
        self.unloading = TrackedResource(env, config, "unloading", config.staffed(config.unloaders))
        self.putaway = TrackedResource(
            env, config, "putaway", config.staffed(config.putaway_operators)
        )
        self.picking = TrackedResource(env, config, "picking", config.staffed(config.pickers))
        self.checking = TrackedResource(env, config, "checking", config.staffed(config.checkers))

    def all(self) -> list[TrackedResource]:
        return [self.inbound_dock, self.unloading, self.putaway, self.picking, self.checking]

    def reset(self) -> None:
        for resource in self.all():
            resource.reset()


def _truck(
    env: simpy.Environment,
    config: SimConfig,
    rng: np.random.Generator,
    resources: Resources,
    recorder: Recorder,
    appointment: float,
    pallets: int,
) -> Generator[Any, None, None]:
    """One inbound truck, from arrival to put-away complete."""
    record: dict[str, float] = {
        "appointment": appointment,
        "arrival": env.now,
        "pallets": float(pallets),
    }

    # Trucks wait in the yard until the operation opens; the dock is not consumed meanwhile.
    yield env.timeout(hours_until_open(env.now, config))

    dock = yield from resources.inbound_dock.acquire()
    record["dock_in"] = env.now
    try:
        unloader = yield from resources.unloading.acquire()
        record["unload_start"] = env.now
        try:
            work = _lognormal(
                rng, pallets * config.unload_min_per_pallet / MINUTES_PER_HOUR, config.service_cv
            )
            yield from perform(env, config, work)
        finally:
            resources.unloading.release(unloader)
        record["unload_end"] = env.now
    finally:
        resources.inbound_dock.release(dock)

    operator = yield from resources.putaway.acquire()
    try:
        work = _lognormal(
            rng, pallets * config.putaway_min_per_pallet / MINUTES_PER_HOUR, config.service_cv
        )
        yield from perform(env, config, work)
    finally:
        resources.putaway.release(operator)
    record["putaway_end"] = env.now

    recorder.trucks.append(record)


def _order(
    env: simpy.Environment,
    config: SimConfig,
    rng: np.random.Generator,
    resources: Resources,
    recorder: Recorder,
    lines: int,
) -> Generator[Any, None, None]:
    """One outbound order, from release to packed."""
    record: dict[str, float] = {"released": env.now, "lines": float(lines)}

    yield env.timeout(hours_until_open(env.now, config))

    picker = yield from resources.picking.acquire()
    record["pick_start"] = env.now
    try:
        work = _lognormal(
            rng,
            (config.pick_setup_min_per_order + lines * config.pick_min_per_line) / MINUTES_PER_HOUR,
            config.service_cv,
        )
        yield from perform(env, config, work)
    finally:
        resources.picking.release(picker)
    record["pick_end"] = env.now

    checker = yield from resources.checking.acquire()
    record["check_start"] = env.now
    try:
        work = _lognormal(
            rng,
            (config.check_min_per_order + lines * config.check_min_per_line) / MINUTES_PER_HOUR,
            config.service_cv,
        )
        yield from perform(env, config, work)
    finally:
        resources.checking.release(checker)
    record["check_end"] = env.now

    recorder.orders.append(record)


def _inbound_source(
    env: simpy.Environment,
    config: SimConfig,
    rng: np.random.Generator,
    resources: Resources,
    recorder: Recorder,
) -> Generator[Any, None, None]:
    """Book inbound appointments across each shift and release the trucks."""
    for day in range(config.days):
        count = int(rng.poisson(config.trucks_per_day))
        if count > 0:
            slots = np.linspace(0.0, config.shift_hours, count, endpoint=False)
            deviation = (
                rng.normal(APPOINTMENT_DEVIATION_MEAN_MIN, APPOINTMENT_DEVIATION_SD_MIN, count)
                / MINUTES_PER_HOUR
            )
            for slot, drift in zip(slots, deviation, strict=True):
                appointment = day * 24.0 + config.shift_start_h + float(slot)
                arrival = max(appointment + float(drift), env.now)
                pallets = max(1, int(rng.poisson(config.pallets_per_truck)))
                yield env.timeout(max(0.0, arrival - env.now))
                recorder.trucks_created += 1
                env.process(_truck(env, config, rng, resources, recorder, appointment, pallets))
        yield env.timeout(max(0.0, (day + 1) * 24.0 - env.now))


def _outbound_source(
    env: simpy.Environment,
    config: SimConfig,
    rng: np.random.Generator,
    resources: Resources,
    recorder: Recorder,
) -> Generator[Any, None, None]:
    """Release outbound orders in waves across each shift."""
    for day in range(config.days):
        count = int(rng.poisson(config.orders_per_day))
        per_wave = np.full(config.release_waves, count // config.release_waves)
        per_wave[: count % config.release_waves] += 1
        wave_spacing = config.shift_hours / config.release_waves

        for wave, wave_count in enumerate(per_wave):
            release = day * 24.0 + config.shift_start_h + wave * wave_spacing
            yield env.timeout(max(0.0, release - env.now))
            for _ in range(int(wave_count)):
                lines = max(1, int(rng.poisson(config.lines_per_order)))
                recorder.orders_created += 1
                env.process(_order(env, config, rng, resources, recorder, lines))
        yield env.timeout(max(0.0, (day + 1) * 24.0 - env.now))


def _warmup(
    env: simpy.Environment, config: SimConfig, resources: Resources
) -> Generator[Any, None, None]:
    """Reset resource statistics once the warm-up transient has passed."""
    yield env.timeout(config.warmup_days * 24.0)
    resources.reset()
