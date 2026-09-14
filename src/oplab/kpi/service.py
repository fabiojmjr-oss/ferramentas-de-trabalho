"""Service level indicators: on-time, in-full, OTIF and fill rate.

The formulas are trivial. What makes a service indicator right or wrong is the set of
decisions around them, and those decisions are usually undocumented:

* Is the promise an instant or a date? A commitment of "two days" is met at 23:59 of day two,
  not at the hour the order was captured.
* Does a partial delivery count as in-full? Some contracts allow a tolerance; most do not.
* Do cancelled lines belong in the denominator? Almost never - but they often do in practice,
  and they inflate the result whenever cancellations are correlated with stockouts.
* What happens to orders still open when the report runs? Excluding them inflates service.
  Failing them understates it. Both answers are defensible; silence is not.

:class:`ServicePolicy` makes each of those choices explicit, and
:func:`service_sensitivity` quantifies how much the reported number moves with them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .schemas import ORDER_LINES

OpenTreatment = Literal["exclude", "fail"]
FillBasis = Literal["unit", "line", "order"]

_SERVICE_COLUMNS = [
    "order_id",
    "line_id",
    "qty_ordered",
    "qty_delivered",
    "promised_ts",
    "delivered_ts",
    "status",
]


@dataclass(frozen=True)
class ServicePolicy:
    """The reporting conventions behind a service number.

    Attributes:
        grace_minutes: Tolerance added to the promise before a delivery counts as late.
        in_full_tolerance: Fraction of the ordered quantity that may be missing and still
            count as in-full. ``0.0`` requires the full quantity.
        excluded_statuses: Line statuses removed from the denominator entirely.
        open_treatment: What to do with lines that have not been delivered yet and are not
            excluded. ``"exclude"`` removes them from the denominator; ``"fail"`` counts them
            as a service failure.
    """

    grace_minutes: int = 0
    in_full_tolerance: float = 0.0
    excluded_statuses: tuple[str, ...] = ("cancelled",)
    open_treatment: OpenTreatment = "exclude"

    def __post_init__(self) -> None:
        if self.grace_minutes < 0:
            raise ValueError("grace_minutes cannot be negative")
        if not 0.0 <= self.in_full_tolerance < 1.0:
            raise ValueError("in_full_tolerance must be in [0, 1)")
        if self.open_treatment not in ("exclude", "fail"):
            raise ValueError("open_treatment must be 'exclude' or 'fail'")

    def describe(self) -> str:
        """One-line description suitable for a report footnote."""
        return (
            f"grace={self.grace_minutes}min, "
            f"in-full tolerance={self.in_full_tolerance:.1%}, "
            f"excluded={list(self.excluded_statuses)}, "
            f"undelivered lines {self.open_treatment}d"
        )


def line_service(lines: pd.DataFrame, policy: ServicePolicy | None = None) -> pd.DataFrame:
    """Evaluate each order line against a service policy.

    Args:
        lines: Order lines satisfying the ``order_lines`` contract.
        policy: Reporting conventions. Defaults to :class:`ServicePolicy`.

    Returns:
        ``lines`` with four columns appended:

        ``in_scope``
            Whether the line belongs in the denominator.
        ``on_time``
            Delivered no later than the promise plus grace. ``False`` for undelivered lines.
        ``in_full``
            Delivered quantity within tolerance of the ordered quantity.
        ``otif``
            ``on_time & in_full``.
    """
    pol = policy or ServicePolicy()
    ORDER_LINES.validate(lines, subset=_SERVICE_COLUMNS)

    out = lines.copy()
    status = out["status"].astype(str)
    delivered = out["delivered_ts"].notna()

    excluded = status.isin(pol.excluded_statuses)
    in_scope = ~excluded
    if pol.open_treatment == "exclude":
        in_scope &= delivered

    deadline = out["promised_ts"] + pd.Timedelta(minutes=pol.grace_minutes)
    on_time = delivered & (out["delivered_ts"] <= deadline)

    required = out["qty_ordered"] * (1.0 - pol.in_full_tolerance)
    in_full = delivered & (out["qty_delivered"] >= required)

    out["in_scope"] = in_scope
    out["on_time"] = on_time.where(in_scope, other=False)
    out["in_full"] = in_full.where(in_scope, other=False)
    out["otif"] = out["on_time"] & out["in_full"]
    return out


def _rate(evaluated: pd.DataFrame, flag: str, by: str | Sequence[str] | None) -> pd.Series | float:
    """Share of in-scope lines satisfying ``flag``, overall or by group."""
    scoped = evaluated.loc[evaluated["in_scope"]]
    if by is None:
        return float(scoped[flag].mean()) if len(scoped) else float("nan")
    keys = [by] if isinstance(by, str) else list(by)
    return scoped.groupby(keys, observed=True)[flag].mean().rename(flag)


def otif(
    lines: pd.DataFrame,
    policy: ServicePolicy | None = None,
    by: str | Sequence[str] | None = None,
) -> pd.Series | float:
    """On-time in-full, as a share of in-scope order lines."""
    return _rate(line_service(lines, policy), "otif", by)


def on_time_rate(
    lines: pd.DataFrame,
    policy: ServicePolicy | None = None,
    by: str | Sequence[str] | None = None,
) -> pd.Series | float:
    """Share of in-scope order lines delivered by the promise."""
    return _rate(line_service(lines, policy), "on_time", by)


def in_full_rate(
    lines: pd.DataFrame,
    policy: ServicePolicy | None = None,
    by: str | Sequence[str] | None = None,
) -> pd.Series | float:
    """Share of in-scope order lines delivered complete."""
    return _rate(line_service(lines, policy), "in_full", by)


def fill_rate(
    lines: pd.DataFrame,
    basis: FillBasis = "unit",
    policy: ServicePolicy | None = None,
    by: str | Sequence[str] | None = None,
) -> pd.Series | float:
    """Fill rate on one of three bases.

    The three answers differ on the same data, and quoting one without naming the basis is a
    common source of disagreement between commercial and operations reporting:

    ``"unit"``
        Units delivered divided by units ordered. The most forgiving: a 99% short on one large
        line is diluted by every other line.
    ``"line"``
        Share of lines delivered complete. Treats a one-unit line and a pallet line equally.
    ``"order"``
        Share of orders in which every line was complete. The strictest, and the one closest
        to what the customer experiences.

    Args:
        lines: Order lines satisfying the ``order_lines`` contract.
        basis: Aggregation basis, as above.
        policy: Reporting conventions.
        by: Optional grouping column(s). Ignored keys raise ``KeyError``.

    Returns:
        A float when ``by`` is ``None``, otherwise a Series indexed by group.
    """
    evaluated = line_service(lines, policy)
    scoped = evaluated.loc[evaluated["in_scope"]]
    keys = None if by is None else ([by] if isinstance(by, str) else list(by))

    if basis == "line":
        return _rate(evaluated, "in_full", by)

    if basis == "unit":
        if keys is None:
            ordered = float(scoped["qty_ordered"].sum())
            return float(scoped["qty_delivered"].sum()) / ordered if ordered else float("nan")
        grouped = scoped.groupby(keys, observed=True)[["qty_ordered", "qty_delivered"]].sum()
        return (grouped["qty_delivered"] / grouped["qty_ordered"]).rename("fill_rate")

    if basis == "order":
        # An order is complete only if every one of its in-scope lines is complete.
        order_keys = ["order_id"] if keys is None else [*keys, "order_id"]
        per_order = scoped.groupby(order_keys, observed=True)["in_full"].all()
        if keys is None:
            return float(per_order.mean()) if len(per_order) else float("nan")
        return per_order.groupby(keys, observed=True).mean().rename("fill_rate")

    raise ValueError(f"unknown basis {basis!r}; expected 'unit', 'line' or 'order'")


def service_sensitivity(
    lines: pd.DataFrame, policies: dict[str, ServicePolicy] | None = None
) -> pd.DataFrame:
    """Report OTIF under several policies side by side.

    This is the table to put in front of a steering committee before agreeing a service
    target. The spread between the rows is not measurement noise - it is the cost of leaving
    the definition implicit, and it is frequently wider than the improvement being debated.

    Args:
        lines: Order lines satisfying the ``order_lines`` contract.
        policies: Named policies to compare. Defaults to four common conventions.

    Returns:
        One row per policy with the resulting OTIF, its components, the in-scope line count
        and the policy description.
    """
    if policies is None:
        policies = {
            "strict": ServicePolicy(open_treatment="fail"),
            "standard": ServicePolicy(),
            "grace_1day": ServicePolicy(grace_minutes=24 * 60),
            "tolerant_5pct": ServicePolicy(grace_minutes=24 * 60, in_full_tolerance=0.05),
        }

    rows = []
    for name, pol in policies.items():
        evaluated = line_service(lines, pol)
        scoped = evaluated.loc[evaluated["in_scope"]]
        rows.append(
            {
                "policy": name,
                "otif": float(scoped["otif"].mean()) if len(scoped) else np.nan,
                "on_time": float(scoped["on_time"].mean()) if len(scoped) else np.nan,
                "in_full": float(scoped["in_full"].mean()) if len(scoped) else np.nan,
                "lines_in_scope": int(len(scoped)),
                "lines_excluded": int((~evaluated["in_scope"]).sum()),
                "definition": pol.describe(),
            }
        )
    return pd.DataFrame(rows)
