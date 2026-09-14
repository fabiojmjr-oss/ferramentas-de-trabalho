"""Turning a list of deliveries into a routing problem.

The matrices are built here rather than fetched, and two assumptions are baked into them. Both
are stated because every absolute cost this module produces inherits them:

**Road distance is Euclidean distance times a circuity factor.** Real road distance comes from
a routing engine over a real network. The factor used by the generator, 1.35, is in the range
commonly quoted for urban networks, but it is an assumption, not a measurement.

**One average speed.** A single figure stands in for a network where an urban arc and a
motorway arc differ by a factor of three. That makes the *ranking* of scenarios reliable - all
of them pay the same optimistic travel times - and the absolute hours unreliable.

Neither assumption is a reason not to use the model. Both are reasons to quote the comparison
between scenarios rather than the level.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_SPEED_KMH = 28.0
DEFAULT_CIRCUITY = 1.35
REQUIRED_COLUMNS: tuple[str, ...] = (
    "x_km",
    "y_km",
    "weight_kg",
    "service_min",
    "window_start_h",
    "window_end_h",
)


@dataclass(frozen=True)
class DeliveryProblem:
    """A day of deliveries from one depot.

    Attributes:
        stops: One row per stop, in solver order. Node 0 is the depot; stop ``i`` is node
            ``i + 1``.
        distance_km: Symmetric ``(n+1, n+1)`` road distance matrix including the depot.
        travel_min: Travel time matrix in minutes, derived from ``distance_km`` and the speed.
        speed_kmh: Average road speed assumed.
        circuity: Factor applied to straight-line distance.
        day_start_h: Hour the operation may dispatch.
        day_end_h: Hour every vehicle must be back.
    """

    stops: pd.DataFrame
    distance_km: np.ndarray
    travel_min: np.ndarray
    speed_kmh: float
    circuity: float
    day_start_h: float
    day_end_h: float

    @property
    def n_stops(self) -> int:
        return len(self.stops)

    @property
    def total_weight_kg(self) -> float:
        return float(self.stops["weight_kg"].sum())

    @property
    def total_service_min(self) -> float:
        return float(self.stops["service_min"].sum())

    def profile(self) -> pd.Series:
        """The shape of the problem, before any solving.

        Worth reading first. A problem whose total service time already exceeds the fleet's
        available hours cannot be solved by better routing, and the solver will simply report
        it infeasible without saying why.
        """
        radial = self.distance_km[0, 1:]
        return pd.Series(
            {
                "stops": float(self.n_stops),
                "weight_kg": self.total_weight_kg,
                "service_h": self.total_service_min / 60.0,
                "median_radius_km": float(np.median(radial)),
                "p90_radius_km": float(np.quantile(radial, 0.9)),
                "max_radius_km": float(radial.max()),
                "windowed_share": float(
                    (
                        self.stops["window_end_h"] - self.stops["window_start_h"]
                        < self.day_end_h - self.day_start_h - 1e-9
                    ).mean()
                ),
            }
        )


def build_problem(
    deliveries: pd.DataFrame,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    circuity: float = DEFAULT_CIRCUITY,
    day_start_h: float = 8.0,
    day_end_h: float = 18.0,
    open_windows: bool = False,
) -> DeliveryProblem:
    """Build the matrices for one day of deliveries from one depot.

    Args:
        deliveries: Stops with the columns in :data:`REQUIRED_COLUMNS`. Coordinates are in
            kilometres relative to the depot, which sits at the origin.
        speed_kmh: Average road speed.
        circuity: Factor applied to straight-line distance to approximate road distance.
        day_start_h: Earliest dispatch.
        day_end_h: Latest return.
        open_windows: Replace every stop's time window with the full working day. Use it to
            price what the windows themselves cost, which is usually more than capacity does.

    Returns:
        A :class:`DeliveryProblem`.

    Raises:
        KeyError: If a required column is missing.
        ValueError: If the frame is empty, or a parameter is out of range.
    """
    missing = [column for column in REQUIRED_COLUMNS if column not in deliveries.columns]
    if missing:
        raise KeyError(f"deliveries is missing column(s) {missing}")
    if deliveries.empty:
        raise ValueError("deliveries is empty")
    if speed_kmh <= 0 or circuity < 1.0:
        raise ValueError("speed_kmh must be positive and circuity at least 1")
    if day_end_h <= day_start_h:
        raise ValueError("day_end_h must be after day_start_h")

    stops = deliveries.reset_index(drop=True).copy()
    if open_windows:
        stops["window_start_h"] = day_start_h
        stops["window_end_h"] = day_end_h

    outside = (stops["window_start_h"] < day_start_h - 1e-9) | (
        stops["window_end_h"] > day_end_h + 1e-9
    )
    if bool(outside.any()):
        raise ValueError(
            f"{int(outside.sum())} stop(s) have a window outside the working day; widen the day "
            "or clip the windows before building the problem"
        )

    # Node 0 is the depot at the origin.
    x = np.concatenate([[0.0], stops["x_km"].to_numpy(dtype=float)])
    y = np.concatenate([[0.0], stops["y_km"].to_numpy(dtype=float)])
    distance_km = np.hypot(x[:, None] - x[None, :], y[:, None] - y[None, :]) * circuity
    np.fill_diagonal(distance_km, 0.0)
    travel_min = distance_km / speed_kmh * 60.0

    return DeliveryProblem(
        stops=stops,
        distance_km=distance_km,
        travel_min=travel_min,
        speed_kmh=speed_kmh,
        circuity=circuity,
        day_start_h=day_start_h,
        day_end_h=day_end_h,
    )


def one_day(
    deliveries: pd.DataFrame,
    site: str,
    date: str,
    channel: str | None = None,
    limit: int | None = None,
    **kwargs: object,
) -> DeliveryProblem:
    """Select one site's deliveries on one date and build the problem.

    Args:
        deliveries: The full delivery table.
        site: Site code.
        date: Delivery date, as a string pandas can parse.
        channel: Optional channel filter, for example ``"d2c"``.
        limit: Optional cap on the number of stops, taken nearest-first. Use it to build a
            smaller problem for a quick run, not to make a result look better.
        **kwargs: Passed to :func:`build_problem`.

    Returns:
        A :class:`DeliveryProblem`.

    Raises:
        ValueError: If the selection is empty.
    """
    selected = deliveries.loc[
        (deliveries["site"].astype(str) == site)
        & (pd.to_datetime(deliveries["order_date"]) == pd.Timestamp(date))
    ]
    if channel is not None:
        selected = selected.loc[selected["channel"].astype(str) == channel]
    if selected.empty:
        raise ValueError(f"no deliveries for site {site!r} on {date!r}")
    if limit is not None:
        selected = selected.nsmallest(limit, "distance_km")
    return build_problem(selected, **kwargs)  # type: ignore[arg-type]
