"""Running the model properly, and comparing configurations.

One run of a stochastic simulation is a sample of size one. Reporting its output as "the
answer" is the most common defect in home-made capacity studies, and it is not a small one:
with a resource near saturation, two runs of the same configuration with different seeds can
differ by a factor of two on mean waiting time. A number without an interval around it cannot
support a capital decision, because there is no way to tell a real difference between two
options from the noise in the estimate.

So :func:`replicate` runs the configuration several times with independent seeds and reports a
confidence interval, and :func:`compare_scenarios` refuses to declare a winner on overlapping
intervals - it reports the overlap instead.
"""

from __future__ import annotations

from dataclasses import replace
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd
import simpy

from .._pandas import as_float
from .config import SimConfig
from .model import Recorder, Resources, _inbound_source, _outbound_source, _warmup
from .results import SimResult

_NORMAL = NormalDist()
DEFAULT_REPLICATIONS = 8
DEFAULT_CONFIDENCE = 0.95


def run_once(config: SimConfig | None = None) -> SimResult:
    """Run one replication.

    Args:
        config: Model parameters. Defaults to :class:`SimConfig`.

    Returns:
        A :class:`SimResult` with the warm-up already excluded.
    """
    cfg = config or SimConfig()
    rng = np.random.default_rng(cfg.seed)
    env = simpy.Environment()

    resources = Resources(env, cfg)
    recorder = Recorder()

    env.process(_inbound_source(env, cfg, rng, resources, recorder))
    env.process(_outbound_source(env, cfg, rng, resources, recorder))
    if cfg.warmup_days > 0:
        env.process(_warmup(env, cfg, resources))

    env.run(until=cfg.days * 24.0)

    statistics = pd.DataFrame(
        [{"resource": resource.name, **resource.statistics()} for resource in resources.all()]
    )

    measurement_start = cfg.warmup_days * 24.0
    trucks = pd.DataFrame(recorder.trucks)
    orders = pd.DataFrame(recorder.orders)
    if not trucks.empty:
        trucks = trucks.loc[trucks["arrival"] >= measurement_start].reset_index(drop=True)
    if not orders.empty:
        orders = orders.loc[orders["released"] >= measurement_start].reset_index(drop=True)

    # Releases in the measured window, counted independently of whether they finished.
    released_orders = _released_in_window(cfg, recorder.orders_created)
    released_trucks = _released_in_window(cfg, recorder.trucks_created)

    return SimResult(
        config=cfg,
        resources=statistics,
        trucks=trucks,
        orders=orders,
        trucks_released=released_trucks,
        orders_released=released_orders,
    )


def _released_in_window(config: SimConfig, created_total: int) -> int:
    """Entities created during the measured days.

    Releases are spread evenly across days by construction, so the measured share is the
    measured share of days. Counting them from the records instead would exclude exactly the
    entities that never finished, which is the population the backlog check needs.
    """
    if config.days == 0:
        return 0
    return int(round(created_total * config.measured_days / config.days))


def replicate(
    config: SimConfig | None = None,
    replications: int = DEFAULT_REPLICATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
) -> pd.DataFrame:
    """Run a configuration several times and summarise with confidence intervals.

    Args:
        config: Base configuration. Each replication uses ``config.seed + i``.
        replications: Number of independent runs. Below four, the interval is too wide to be
            informative; the function still runs but the interval will say so.
        confidence: Confidence level for the interval.

    Returns:
        One row per metric with ``mean``, ``std``, ``ci_low``, ``ci_high``, ``half_width`` and
        ``replications``.

    Note:
        The interval is a normal approximation on the replication mean. For a quantity bounded
        at zero and estimated close to it - a backlog share of a fraction of a percent, say -
        the lower bound can come out negative. That is not clamped, because the impossible
        bound is the honest signal: it says the estimate is imprecise relative to its own
        magnitude, and clamping it to zero would hide exactly that.

    Raises:
        ValueError: If ``replications`` is below two or ``confidence`` is not in (0, 1).
    """
    if replications < 2:
        raise ValueError("at least 2 replications are needed to estimate an interval")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")

    cfg = config or SimConfig()
    rows = [
        _metrics(run_once(replace(cfg, seed=cfg.seed + index))) for index in range(replications)
    ]
    samples = pd.DataFrame(rows)

    z = _NORMAL.inv_cdf(0.5 + confidence / 2.0)
    mean = samples.mean()
    std = samples.std(ddof=1)
    half_width = z * std / np.sqrt(replications)

    summary = pd.DataFrame(
        {
            "mean": mean,
            "std": std,
            "ci_low": mean - half_width,
            "ci_high": mean + half_width,
            "half_width": half_width,
            "replications": replications,
        }
    )
    return summary.reset_index(names="metric")


def _metrics(result: SimResult) -> dict[str, float]:
    """The handful of numbers a capacity decision actually turns on."""
    orders = result.order_flow().set_index("stage")
    trucks = result.truck_flow().set_index("stage")
    utilisation = result.resources.set_index("resource")["utilisation"]
    bottleneck = result.bottleneck()

    metrics = {
        "order_cycle_mean_h": as_float(orders.loc["total_cycle_h", "mean_h"]),
        "order_cycle_p95_h": as_float(orders.loc["total_cycle_h", "p95_h"]),
        "wait_for_checker_mean_h": as_float(orders.loc["wait_for_checker_h", "mean_h"]),
        "truck_dwell_mean_h": as_float(trucks.loc["truck_dwell_h", "mean_h"]),
        "truck_dwell_p95_h": as_float(trucks.loc["truck_dwell_h", "p95_h"]),
        "dock_to_stock_p95_h": as_float(trucks.loc["dock_to_stock_h", "p95_h"]),
        "orders_packed_per_day": as_float(result.throughput()["orders_packed_per_day"]),
        "backlog_share": float(result.backlog_share),
        "bottleneck_wait_h": as_float(bottleneck["total_wait_h"]),
    }
    metrics.update({f"utilisation_{name}": float(value) for name, value in utilisation.items()})
    return metrics


def compare_scenarios(
    base: SimConfig,
    scenarios: dict[str, dict[str, Any]],
    metric: str = "order_cycle_mean_h",
    replications: int = DEFAULT_REPLICATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
) -> pd.DataFrame:
    """Evaluate several changes to a configuration on the same metric.

    Args:
        base: The configuration to change.
        scenarios: Named overrides, each a mapping of :class:`SimConfig` field to value. The
            base itself is always included as ``"base"``.
        metric: Metric from :func:`replicate` to rank on.
        replications: Replications per scenario.
        confidence: Confidence level.

    Returns:
        One row per scenario with the metric's mean and interval, the change against the base,
        and ``distinguishable`` - whether the interval is separated from the base's. A scenario
        whose interval overlaps the base has not been shown to do anything, however different
        the point estimate looks.

    Raises:
        KeyError: If a scenario names a field that does not exist, or ``metric`` is unknown.
    """
    valid_fields = set(SimConfig.__dataclass_fields__)
    for name, overrides in scenarios.items():
        unknown = set(overrides) - valid_fields
        if unknown:
            raise KeyError(f"scenario {name!r} sets unknown field(s) {sorted(unknown)}")

    all_scenarios: dict[str, dict[str, Any]] = {"base": {}, **scenarios}
    rows = []
    for name, overrides in all_scenarios.items():
        summary = replicate(
            replace(base, **overrides), replications=replications, confidence=confidence
        ).set_index("metric")
        if metric not in summary.index:
            raise KeyError(f"unknown metric {metric!r}; available: {sorted(summary.index)}")
        row = summary.loc[metric]
        rows.append(
            {
                "scenario": name,
                "mean": as_float(row["mean"]),
                "ci_low": as_float(row["ci_low"]),
                "ci_high": as_float(row["ci_high"]),
                "backlog_share": as_float(summary.loc["backlog_share", "mean"]),
            }
        )

    table = pd.DataFrame(rows).set_index("scenario")
    base_row = table.loc["base"]
    table["change_vs_base"] = table["mean"] / base_row["mean"] - 1.0
    # Non-overlapping intervals are the weakest defensible claim of a real difference.
    table["distinguishable"] = (table["ci_high"] < base_row["ci_low"]) | (
        table["ci_low"] > base_row["ci_high"]
    )
    table.loc["base", "distinguishable"] = False
    return table.sort_values("mean").reset_index()
