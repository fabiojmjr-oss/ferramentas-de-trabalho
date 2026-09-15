"""Parameters of the distribution centre model.

The defaults are calibrated to make one point that a static capacity spreadsheet cannot make.
Work out the deterministic load and you get this, on a single eight-hour shift:

=====================  =================  =============
Resource               Work per day       Utilisation
=====================  =================  =============
Pickers (18)           6,768 min          78%
Checking (5)           2,304 min          **96%**
Inbound docks (4)      1,176 dock-min     61%
Unloading (4)          1,176 min          61%
Put-away (6)           1,344 min          47%
=====================  =================  =============

The headcount is concentrated in picking, picking looks comfortable, and a capacity review
that reads that table concludes the operation has room. It does not. The five-person checking
team is at 96%, and a queue at 96% utilisation is not 20% worse than a queue at 78% - it is
several times worse, because waiting time grows with the reciprocal of idle capacity rather
than with load. That non-linearity is the whole reason to simulate rather than divide.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimConfig:
    """Configuration of one simulated distribution centre.

    Time is measured in hours throughout. Work only progresses while the operation is open, so
    a task that cannot finish before the shift ends resumes the next morning - which is what
    makes a longer shift a genuine lever rather than a rescaling.

    Attributes:
        seed: Seed for this replication.
        days: Days to simulate, including the warm-up.
        warmup_days: Days discarded before statistics start. A simulation that starts empty
            reports a shorter queue than the operation ever has; discarding the transient is
            not optional.
        shift_start_h: Hour of day the operation opens.
        shift_hours: Hours open per day. Must not cross midnight, so
            ``shift_start_h + shift_hours <= 24``. Set to 24 for continuous operation.
        absenteeism: Fraction of each team assumed absent. Applied as a deterministic haircut
            on staffing; day-to-day variation in who shows up is not modelled.
        trucks_per_day: Mean inbound appointments per day.
        pallets_per_truck: Mean pallets per inbound truck.
        inbound_docks: Inbound dock doors. A dock is held from the moment a truck is let in
            until unloading finishes.
        unloaders: Unloading teams.
        unload_min_per_pallet: Unloading minutes per pallet.
        putaway_operators: Put-away operators. Put-away happens after the dock is released.
        putaway_min_per_pallet: Put-away minutes per pallet.
        orders_per_day: Mean outbound orders per day.
        lines_per_order: Mean lines per outbound order.
        release_waves: Number of releases per shift. Orders arrive at the pick face in waves,
            which is how most operations actually run - and wave count is a free lever, unlike
            headcount and doors.
        pickers: Pickers.
        pick_setup_min_per_order: Fixed picking minutes per order, independent of line count.
        pick_min_per_line: Picking minutes per line.
        checkers: Checking and packing stations.
        check_min_per_order: Fixed checking minutes per order.
        check_min_per_line: Checking minutes per line.
        service_cv: Coefficient of variation of every service time. Task times are drawn
            lognormal with this dispersion; setting it to zero makes the model deterministic,
            which is useful for tests and wrong for planning.
    """

    seed: int = 42
    days: int = 24
    warmup_days: int = 4

    shift_start_h: float = 6.0
    shift_hours: float = 8.0
    absenteeism: float = 0.0

    trucks_per_day: float = 24.0
    pallets_per_truck: float = 14.0
    inbound_docks: int = 4
    unloaders: int = 4
    unload_min_per_pallet: float = 3.5
    putaway_operators: int = 6
    putaway_min_per_pallet: float = 4.0

    orders_per_day: float = 900.0
    lines_per_order: float = 3.2
    release_waves: int = 2
    pickers: int = 18
    pick_setup_min_per_order: float = 4.0
    pick_min_per_line: float = 1.1
    checkers: int = 5
    check_min_per_order: float = 1.6
    check_min_per_line: float = 0.3

    service_cv: float = 0.35

    def __post_init__(self) -> None:
        if self.days < 1:
            raise ValueError("days must be at least 1")
        if not 0 <= self.warmup_days < self.days:
            raise ValueError("warmup_days must be non-negative and shorter than days")
        if not 0.0 <= self.shift_start_h < 24.0:
            raise ValueError("shift_start_h must be within a day")
        if not 0.0 < self.shift_hours <= 24.0:
            raise ValueError("shift_hours must be positive and at most 24")
        if self.shift_hours < 24.0 and self.shift_start_h + self.shift_hours > 24.0:
            raise ValueError(
                "the shift must not cross midnight: shift_start_h + shift_hours must be <= 24"
            )
        if not 0.0 <= self.absenteeism < 1.0:
            raise ValueError("absenteeism must be a fraction below 1")
        if self.release_waves < 1:
            raise ValueError("release_waves must be at least 1")
        if self.service_cv < 0.0:
            raise ValueError("service_cv cannot be negative")
        for name in ("inbound_docks", "unloaders", "putaway_operators", "pickers", "checkers"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")

    def staffed(self, headcount: int) -> int:
        """Effective capacity after the absenteeism haircut, never below one."""
        return max(1, round(headcount * (1.0 - self.absenteeism)))

    @property
    def measured_days(self) -> int:
        """Days of statistics collected, after the warm-up."""
        return self.days - self.warmup_days

    def static_utilisation(self) -> dict[str, float]:
        """Deterministic utilisation per resource, as a capacity spreadsheet would compute it.

        This is the number the model exists to contradict. It divides mean work by mean
        capacity and is therefore blind to queueing, to variability, and to the fact that work
        arriving late in a shift waits overnight. It is exposed so the two can be printed side
        by side.
        """
        shift_minutes = self.shift_hours * 60.0
        pallets = self.trucks_per_day * self.pallets_per_truck
        unload_minutes = pallets * self.unload_min_per_pallet
        dock_minutes = unload_minutes  # a dock is held for the duration of unloading
        pick_minutes = self.orders_per_day * (
            self.pick_setup_min_per_order + self.lines_per_order * self.pick_min_per_line
        )
        check_minutes = self.orders_per_day * (
            self.check_min_per_order + self.lines_per_order * self.check_min_per_line
        )
        return {
            "inbound_dock": dock_minutes / (self.staffed(self.inbound_docks) * shift_minutes),
            "unloading": unload_minutes / (self.staffed(self.unloaders) * shift_minutes),
            "putaway": pallets
            * self.putaway_min_per_pallet
            / (self.staffed(self.putaway_operators) * shift_minutes),
            "picking": pick_minutes / (self.staffed(self.pickers) * shift_minutes),
            "checking": check_minutes / (self.staffed(self.checkers) * shift_minutes),
        }
