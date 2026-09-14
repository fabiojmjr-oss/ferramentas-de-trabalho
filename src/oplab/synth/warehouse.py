"""Pick-face layout and the current slotting assignment.

The layout modelled here is the most common one in distribution: **parallel picking aisles
entered from a single cross-aisle, with one dock at one end of that cross-aisle**. Travel to a
location is therefore the walk along the cross-aisle to the right aisle, plus the walk into the
aisle to the right bay.

Two simplifications are deliberate and are what separate this from the simulation in a later
wave:

* **One location per SKU.** No forward-and-reserve split, no multi-location storage, no
  replenishment. A real operation slots fast movers into a forward pick area fed from bulk, and
  that changes the arithmetic.
* **No routing.** Travel is measured as distance-weighted picks, not as a route. That quantity
  is proportional to real travel only under return routing, where the picker collects one line
  and comes back. Under batch picking with an S-shape or largest-gap route the relationship
  still holds in direction but not in magnitude.

Both assumptions overstate the benefit of re-slotting. They are stated here so that any figure
produced from this model is read as a direction and an order of magnitude, not as a business
case.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import SynthConfig

AISLE_PITCH_M = 3.0
BAY_PITCH_M = 1.2
LOCATION_CAPACITY_M3 = 1.2

# Vertical access converted to equivalent walking distance. Level 2 is the golden zone at waist
# height and costs nothing extra; level 1 requires bending; levels 3 and above require a lift
# truck, which is why the penalty jumps rather than growing smoothly.
LEVEL_PENALTY_M: dict[int, float] = {1: 2.0, 2: 0.0, 3: 6.0, 4: 14.0}
DEFAULT_LEVEL_PENALTY_M = 18.0


def generate_layout(cfg: SynthConfig) -> pd.DataFrame:
    """Build the pick-face layout.

    The layout is deterministic: it is a building, not a random draw, so it consumes no random
    numbers and depends only on the configured dimensions.

    Args:
        cfg: Generation parameters. ``aisles``, ``bays_per_aisle`` and ``levels`` set the shape.

    Returns:
        One row per pick face with ``location``, ``aisle``, ``bay``, ``level``, ``distance_m``
        (horizontal walk from the dock), ``level_penalty_m``, ``effective_distance_m`` and
        ``capacity_m3``.
    """
    aisle, bay, level = (
        arr.reshape(-1)
        for arr in np.meshgrid(
            np.arange(1, cfg.aisles + 1),
            np.arange(1, cfg.bays_per_aisle + 1),
            np.arange(1, cfg.levels + 1),
            indexing="ij",
        )
    )

    distance_m = (aisle - 1) * AISLE_PITCH_M + (bay - 0.5) * BAY_PITCH_M
    penalty = np.array([LEVEL_PENALTY_M.get(int(lv), DEFAULT_LEVEL_PENALTY_M) for lv in level])

    layout = pd.DataFrame(
        {
            "location": [
                f"{a:02d}-{b:02d}-{lv}" for a, b, lv in zip(aisle, bay, level, strict=True)
            ],
            "aisle": aisle,
            "bay": bay,
            "level": level,
            "distance_m": np.round(distance_m, 2),
            "level_penalty_m": penalty,
            "effective_distance_m": np.round(distance_m + penalty, 2),
            "capacity_m3": LOCATION_CAPACITY_M3,
        }
    )
    return layout.sort_values("effective_distance_m", ignore_index=True)


def generate_assignment(
    catalog: pd.DataFrame, layout: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Assign every SKU to a pick face at random, as the current state.

    Random placement is not a straw man. It is what an operation ends up with when items are
    slotted where there was space on the day they first arrived and nothing ever re-slots them,
    which is the normal condition of a warehouse that has no slotting discipline. It is the
    baseline any re-slotting proposal has to beat, and the honest one.

    Args:
        catalog: SKU master, including ``case_volume_m3``.
        layout: Pick faces from :func:`generate_layout`.
        rng: Seeded generator.

    Returns:
        One row per SKU with ``sku`` and ``location``.

    Raises:
        ValueError: If there are fewer pick faces than SKUs.
    """
    if len(layout) < len(catalog):
        raise ValueError(
            f"{len(layout)} pick faces for {len(catalog)} SKUs; each SKU needs its own location"
        )

    chosen = rng.choice(layout["location"].to_numpy(), size=len(catalog), replace=False)
    return pd.DataFrame({"sku": catalog["sku"].to_numpy(), "location": chosen})
