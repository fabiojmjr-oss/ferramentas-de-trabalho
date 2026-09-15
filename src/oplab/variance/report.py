"""Turning a decomposition into the two artefacts a review actually uses."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .bridge import BridgeResult
from .pvm import PVMResult


def contribution_pareto(result: PVMResult | BridgeResult, top: int = 10) -> pd.DataFrame:
    """Rank segments by how much of the movement they explain.

    Ranking is by **absolute** contribution, because offsetting movements are the finding, not
    noise: a total that barely moved while one segment deteriorated by the same amount another
    improved is a managed operation or a lucky one, and the two look identical in the total.

    Args:
        result: A decomposition or bridge.
        top: Number of segments to return.

    Returns:
        The top segments with their contribution, its share of the total absolute movement, and
        the cumulative share.

    Raises:
        ValueError: If ``top`` is not positive.
    """
    if top < 1:
        raise ValueError("top must be positive")

    detail = result.detail.copy()
    detail["abs_contribution"] = detail["contribution"].abs()
    total_absolute = float(detail["abs_contribution"].sum())

    ranked = detail.sort_values("abs_contribution", ascending=False)
    ranked["share_of_movement"] = (
        ranked["abs_contribution"] / total_absolute if total_absolute else np.nan
    )
    ranked["cumulative_share"] = ranked["share_of_movement"].cumsum()

    columns = ["contribution", "share_of_movement", "cumulative_share"]
    extra = [c for c in ("quantity_effect", "rate_effect", "mix_effect", "presence") if c in ranked]
    return ranked[columns + extra].head(top)


def waterfall(result: PVMResult | BridgeResult) -> pd.DataFrame:
    """Lay a decomposition out as a waterfall, ready to plot or paste.

    Args:
        result: A decomposition or bridge.

    Returns:
        Frame with ``label``, ``value``, ``start``, ``end`` and ``kind`` (``"total"`` for the
        two anchor bars, ``"effect"`` for the bridging ones). Zero-valued effects are kept, so
        that "mix explained none of it" stays visible instead of disappearing from the chart.
    """
    if isinstance(result, PVMResult):
        opening, closing = result.base_total, result.current_total
        open_label, close_label = f"{result.value} base", f"{result.value} current"
    else:
        opening, closing = result.base_rate, result.current_rate
        open_label, close_label = "rate base", "rate current"

    rows = [{"label": open_label, "value": opening, "start": 0.0, "end": opening, "kind": "total"}]
    running = opening
    for label, value in result.effects.items():
        rows.append(
            {
                "label": str(label),
                "value": float(value),
                "start": running,
                "end": running + float(value),
                "kind": "effect",
            }
        )
        running += float(value)
    rows.append(
        {"label": close_label, "value": closing, "start": 0.0, "end": closing, "kind": "total"}
    )

    frame = pd.DataFrame(rows)
    # The bars must land on the closing total; if they do not, the decomposition is broken.
    if not np.isclose(running, closing, rtol=1e-9, atol=1e-6):
        raise ValueError(
            f"effects sum to {running:.6f} but the closing total is {closing:.6f}; "
            "the decomposition does not reconcile"
        )
    return frame
