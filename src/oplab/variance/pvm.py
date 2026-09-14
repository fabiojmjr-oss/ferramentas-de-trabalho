"""Price-volume-mix decomposition of a change in a total.

A total built as quantity times rate can move for four distinguishable reasons, and they have
different owners:

``volume``
    The same business got bigger or smaller. Nobody did anything to the operation.
``mix``
    The composition shifted towards segments that cost more, or earn more. A commercial or
    demand-side movement, not an operational one.
``rate``
    The cost or price per unit changed inside the segments. This is the one the operation owns.
``new`` / ``discontinued``
    Segments that exist in only one of the two periods. Most spreadsheet decompositions have no
    home for these and silently dump them into mix, which is how a product launch gets reported
    as an operational deterioration.

The decomposition here is exact: the four effects sum to the total change with no residual, and
that is asserted in the tests. A decomposition with a plug line is not a decomposition.

**The identity.** Per segment the split is unambiguous::

    V1 - V0 = r0 x (q1 - q0)   +   q1 x (r1 - r0)
              quantity effect      rate effect

Volume and mix are then the two halves of the aggregate quantity effect: volume is what
proportional growth would have produced, mix is the rest. **Mix does not exist per segment** -
it is by construction a statement about how segments moved relative to each other - which is
why this module reports quantity and rate per segment, and splits out mix only in the total.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

EFFECT_ORDER: tuple[str, ...] = ("volume", "mix", "rate", "new", "discontinued")


@dataclass(frozen=True)
class PVMResult:
    """Outcome of a price-volume-mix decomposition.

    Attributes:
        base_total: Total value in the base period.
        current_total: Total value in the current period.
        effects: The five effects, in reporting order. They sum to ``delta``.
        detail: One row per segment with base and current quantity, value and rate, the
            per-segment quantity and rate effects, the total contribution, and ``presence``
            (``"both"``, ``"new"`` or ``"discontinued"``).
        quantity: Name of the quantity column, for labelling.
        value: Name of the value column, for labelling.
    """

    base_total: float
    current_total: float
    effects: pd.Series
    detail: pd.DataFrame
    quantity: str
    value: str

    @property
    def delta(self) -> float:
        """Total change in value."""
        return self.current_total - self.base_total

    @property
    def relative_delta(self) -> float:
        """Total change as a share of the base total."""
        return self.delta / self.base_total if self.base_total else float("nan")

    @property
    def reconciliation_error(self) -> float:
        """Difference between the summed effects and the actual change.

        Should be zero up to floating point. Anything else is a defect, not a rounding
        convention.
        """
        return float(self.effects.sum() - self.delta)

    def summary(self) -> pd.DataFrame:
        """The effects with their share of the base total, ready to read out."""
        frame = self.effects.rename("value").to_frame()
        frame["share_of_base"] = frame["value"] / self.base_total if self.base_total else np.nan
        frame["share_of_delta"] = frame["value"] / self.delta if self.delta else np.nan
        return frame


def _aggregate(
    frame: pd.DataFrame, keys: list[str], quantity: str, value: str, suffix: str
) -> pd.DataFrame:
    for column in [*keys, quantity, value]:
        if column not in frame.columns:
            raise KeyError(f"frame has no column {column!r}")
    grouped = frame.groupby(keys, observed=True)[[quantity, value]].sum()
    grouped.columns = [f"{quantity}{suffix}", f"{value}{suffix}"]
    return grouped


def price_volume_mix(
    base: pd.DataFrame,
    current: pd.DataFrame,
    key: str | Sequence[str],
    quantity: str = "quantity",
    value: str = "value",
) -> PVMResult:
    """Decompose the change in a total between two periods.

    Args:
        base: Rows for the base period. Aggregated by ``key`` before decomposing, so
            transaction-level input is fine.
        current: Rows for the current period.
        key: Segment column(s). The segmentation is the analysis: mix can only be seen along
            dimensions you segment by, so a decomposition that finds no mix effect may simply
            be segmented on the wrong thing.
        quantity: Column holding the quantity, for example orders or units.
        value: Column holding the value, for example cost or revenue.

    Returns:
        A :class:`PVMResult` whose effects sum exactly to the change.

    Raises:
        KeyError: If a named column is missing.
        ValueError: If either period is empty, or a segment has value but no quantity.
    """
    keys = [key] if isinstance(key, str) else list(key)
    if base.empty or current.empty:
        raise ValueError("both periods must contain rows")

    joined = _aggregate(base, keys, quantity, value, "_base").join(
        _aggregate(current, keys, quantity, value, "_current"), how="outer"
    )
    q0 = joined[f"{quantity}_base"]
    v0 = joined[f"{value}_base"]
    q1 = joined[f"{quantity}_current"]
    v1 = joined[f"{value}_current"]

    in_base = q0.notna() & (q0 != 0)
    in_current = q1.notna() & (q1 != 0)
    if (v0.notna() & ~in_base & (v0 != 0)).any() or (v1.notna() & ~in_current & (v1 != 0)).any():
        raise ValueError("a segment has value but no quantity; the implied rate is undefined")

    q0 = q0.fillna(0.0)
    v0 = v0.fillna(0.0)
    q1 = q1.fillna(0.0)
    v1 = v1.fillna(0.0)

    both = in_base & in_current
    new = in_current & ~in_base
    discontinued = in_base & ~in_current

    r0 = (v0 / q0).where(in_base)
    r1 = (v1 / q1).where(in_current)

    # Per segment, exactly two effects. Segments present in only one period contribute their
    # whole value instead: there is no rate to compare against.
    quantity_effect = (r0 * (q1 - q0)).where(both, other=0.0)
    rate_effect = (q1 * (r1 - r0)).where(both, other=0.0)

    base_common = float(v0[both].sum())
    q0_common = float(q0[both].sum())
    q1_common = float(q1[both].sum())
    mean_rate_base = base_common / q0_common if q0_common else 0.0

    volume = (q1_common - q0_common) * mean_rate_base
    total_quantity_effect = float(quantity_effect.sum())
    # Mix is the residual of the quantity effect after proportional growth, which is what makes
    # it an aggregate quantity rather than a per-segment one.
    mix = total_quantity_effect - volume

    effects = pd.Series(
        {
            "volume": volume,
            "mix": mix,
            "rate": float(rate_effect.sum()),
            "new": float(v1[new].sum()),
            "discontinued": -float(v0[discontinued].sum()),
        }
    ).reindex(list(EFFECT_ORDER))

    presence = pd.Series("both", index=joined.index, dtype="object")
    presence[new] = "new"
    presence[discontinued] = "discontinued"

    detail = pd.DataFrame(
        {
            f"{quantity}_base": q0,
            f"{value}_base": v0,
            "rate_base": r0,
            f"{quantity}_current": q1,
            f"{value}_current": v1,
            "rate_current": r1,
            "quantity_effect": quantity_effect,
            "rate_effect": rate_effect,
            "presence": presence,
        }
    )
    detail["contribution"] = np.where(
        presence == "both",
        detail["quantity_effect"] + detail["rate_effect"],
        detail[f"{value}_current"] - detail[f"{value}_base"],
    )

    return PVMResult(
        base_total=float(v0.sum()),
        current_total=float(v1.sum()),
        effects=effects,
        detail=detail.sort_values("contribution", key=abs, ascending=False),
        quantity=quantity,
        value=value,
    )
