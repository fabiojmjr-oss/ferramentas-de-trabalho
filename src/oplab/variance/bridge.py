"""Bridging a change in a per-unit metric.

Executives ask about cost **per order**, not total cost. That is a different question and it
has a different answer, because a per-unit metric cannot move through volume at all::

    V1/Q1 - V0/Q0  =  SUM s1 x (r1 - r0)   +   SUM (s1 - s0) x r0
                      rate                     mix

where ``s`` is each segment's share of quantity and ``r`` its rate. Two terms, exact, and
volume is absent by construction. So "our cost per order rose but volume grew" is not an
explanation - growth alone cannot move a per-unit figure. Either the rate moved inside the
segments, or the mix moved between them.

**The one caveat, and it is a real one.** That statement holds for the segment rates as
observed. Where there is operating leverage - fixed cost spread over a larger base - growth
lowers the observed rate inside each segment, so the volume effect is real but it is hiding
inside the rate term. Separating it requires a fixed and variable split of cost, which this
module does not attempt. If the operation has material fixed cost, read the rate effect as
"rate net of any volume dilution" and say so.

**The one convention.** A segment present only in the current period has no base rate to
compare against. Its mix effect is priced at the **base-period average rate**, which treats
the arrival of a new segment as mix-neutral and puts the whole of its difference from the
average into the rate effect. That is a choice, not a law, so :class:`BridgeResult` reports
``new_quantity_share`` - how much of the current quantity rests on the convention - and it is
worth glancing at before quoting the split.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BridgeResult:
    """Outcome of a per-unit bridge.

    Attributes:
        base_rate: Value per unit in the base period.
        current_rate: Value per unit in the current period.
        effects: ``rate`` and ``mix``. They sum to ``delta``.
        detail: One row per segment with shares, rates and the two per-segment effects.
        new_quantity_share: Share of current quantity in segments absent from the base period,
            whose mix effect rests on the base-average-rate convention.
    """

    base_rate: float
    current_rate: float
    effects: pd.Series
    detail: pd.DataFrame
    new_quantity_share: float

    @property
    def delta(self) -> float:
        """Change in the per-unit metric."""
        return self.current_rate - self.base_rate

    @property
    def relative_delta(self) -> float:
        """Change as a share of the base rate."""
        return self.delta / self.base_rate if self.base_rate else float("nan")

    @property
    def reconciliation_error(self) -> float:
        """Difference between the summed effects and the actual change; should be zero."""
        return float(self.effects.sum() - self.delta)

    def summary(self) -> pd.DataFrame:
        """The two effects with their share of the base rate and of the movement."""
        frame = self.effects.rename("value").to_frame()
        frame["share_of_base"] = frame["value"] / self.base_rate if self.base_rate else np.nan
        frame["share_of_delta"] = frame["value"] / self.delta if self.delta else np.nan
        return frame


def unit_value_bridge(
    base: pd.DataFrame,
    current: pd.DataFrame,
    key: str | Sequence[str],
    quantity: str = "quantity",
    value: str = "value",
) -> BridgeResult:
    """Bridge the change in value per unit between two periods.

    Args:
        base: Rows for the base period, aggregated by ``key`` before bridging.
        current: Rows for the current period.
        key: Segment column(s).
        quantity: Column holding the quantity.
        value: Column holding the value.

    Returns:
        A :class:`BridgeResult` whose two effects sum exactly to the change in the per-unit
        metric.

    Raises:
        KeyError: If a named column is missing.
        ValueError: If either period is empty or has no quantity.
    """
    keys = [key] if isinstance(key, str) else list(key)
    if base.empty or current.empty:
        raise ValueError("both periods must contain rows")

    frames = []
    for frame, suffix in ((base, "_base"), (current, "_current")):
        for column in [*keys, quantity, value]:
            if column not in frame.columns:
                raise KeyError(f"frame has no column {column!r}")
        grouped = frame.groupby(keys, observed=True)[[quantity, value]].sum()
        grouped.columns = [f"{quantity}{suffix}", f"{value}{suffix}"]
        frames.append(grouped)

    joined = frames[0].join(frames[1], how="outer").fillna(0.0)
    q0 = joined[f"{quantity}_base"]
    v0 = joined[f"{value}_base"]
    q1 = joined[f"{quantity}_current"]
    v1 = joined[f"{value}_current"]

    total_q0 = float(q0.sum())
    total_q1 = float(q1.sum())
    if total_q0 <= 0 or total_q1 <= 0:
        raise ValueError("both periods must have positive total quantity")

    base_rate = float(v0.sum()) / total_q0
    current_rate = float(v1.sum()) / total_q1

    s0 = q0 / total_q0
    s1 = q1 / total_q1
    in_base = q0 > 0
    in_current = q1 > 0

    # A new segment has no base rate. Pricing its mix effect at the base average makes its
    # arrival mix-neutral and sends its whole departure from the average into the rate effect.
    rate_base = (v0 / q0).where(in_base, other=base_rate)
    rate_current = (v1 / q1).where(in_current, other=0.0)

    rate_effect = s1 * (rate_current - rate_base)
    rate_effect = rate_effect.where(in_current, other=0.0)
    mix_effect = (s1 - s0) * rate_base

    effects = pd.Series({"rate": float(rate_effect.sum()), "mix": float(mix_effect.sum())})

    detail = pd.DataFrame(
        {
            f"{quantity}_base": q0,
            "share_base": s0,
            "rate_base": (v0 / q0).where(in_base),
            f"{quantity}_current": q1,
            "share_current": s1,
            "rate_current": (v1 / q1).where(in_current),
            "rate_effect": rate_effect,
            "mix_effect": mix_effect,
        }
    )
    detail["contribution"] = detail["rate_effect"] + detail["mix_effect"]

    new_quantity = float(q1[in_current & ~in_base].sum())

    return BridgeResult(
        base_rate=base_rate,
        current_rate=current_rate,
        effects=effects,
        detail=detail.sort_values("contribution", key=abs, ascending=False),
        new_quantity_share=new_quantity / total_q1,
    )
