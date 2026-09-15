"""Assembly of a complete synthetic dataset."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import numpy as np
import pandas as pd

from .catalog import generate_catalog
from .config import SynthConfig
from .costs import generate_cost_ledger
from .counts import generate_cycle_counts
from .deliveries import generate_deliveries
from .demand import generate_demand
from .events import generate_order_events
from .inbound import generate_receipts
from .outbound import generate_order_lines
from .process import generate_subgroups
from .procurement import generate_purchase_orders
from .warehouse import generate_assignment, generate_layout


@dataclass(frozen=True)
class Dataset:
    """The tables every example in this repository is built on."""

    config: SynthConfig
    catalog: pd.DataFrame
    demand: pd.DataFrame
    order_lines: pd.DataFrame
    receipts: pd.DataFrame
    cycle_counts: pd.DataFrame
    subgroups: pd.DataFrame
    layout: pd.DataFrame
    assignment: pd.DataFrame
    deliveries: pd.DataFrame
    cost_ledger: pd.DataFrame
    purchase_orders: pd.DataFrame
    order_events: pd.DataFrame

    @property
    def tables(self) -> dict[str, pd.DataFrame]:
        """Frames keyed by table name, excluding the configuration."""
        return {
            f.name: getattr(self, f.name)
            for f in fields(self)
            if f.name != "config" and isinstance(getattr(self, f.name), pd.DataFrame)
        }

    def summary(self) -> pd.DataFrame:
        """Row and column counts per table, for a quick sanity check."""
        return pd.DataFrame(
            [
                {"table": name, "rows": len(df), "columns": df.shape[1]}
                for name, df in self.tables.items()
            ]
        )

    def to_csv(self, directory: str | Path) -> dict[str, Path]:
        """Write every table to ``directory`` as CSV and return the paths written."""
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        written: dict[str, Path] = {}
        for name, df in self.tables.items():
            path = target / f"{name}.csv"
            df.to_csv(path, index=False)
            written[name] = path
        return written


def generate_dataset(config: SynthConfig | None = None) -> Dataset:
    """Generate the full dataset from a single seed.

    One generator instance is threaded through every step, so the whole dataset is
    reproducible from ``config.seed`` alone: the same seed yields byte-identical tables on
    any machine with the same library versions.

    Args:
        config: Generation parameters. Defaults to :class:`SynthConfig`.

    Returns:
        A :class:`Dataset` holding the catalogue, demand, order lines, receipts, cycle counts,
        process measurements, pick-face layout, current slotting assignment, cost ledger,
        delivery stops, replenishment orders and the fulfilment event log.
    """
    cfg = config or SynthConfig()
    rng = np.random.default_rng(cfg.seed)

    catalog = generate_catalog(cfg, rng)
    demand = generate_demand(cfg, catalog, rng)
    order_lines = generate_order_lines(cfg, demand, rng)
    receipts = generate_receipts(cfg, rng)
    cycle_counts = generate_cycle_counts(cfg, catalog, rng)
    subgroups = generate_subgroups(rng)
    # Layout and assignment are generated last on purpose: appending a step to the end of the
    # stream leaves every earlier table byte-identical, so published figures keep reproducing.
    layout = generate_layout(cfg)
    assignment = generate_assignment(catalog, layout, rng)
    # Geography before money: freight depends on how far the delivery is, so the delivery
    # table has to exist before the ledger can be derived from it.
    deliveries = generate_deliveries(cfg, order_lines, catalog, rng)
    cost_ledger = generate_cost_ledger(cfg, deliveries, rng)
    # Appended after the ledger for the same reason as the layout: every table above keeps
    # reproducing byte for byte, so no figure published before this step moved.
    purchase_orders = generate_purchase_orders(cfg, catalog, rng)
    order_events = generate_order_events(cfg, order_lines, rng)

    return Dataset(
        config=cfg,
        catalog=catalog,
        demand=demand,
        order_lines=order_lines,
        receipts=receipts,
        cycle_counts=cycle_counts,
        subgroups=subgroups,
        layout=layout,
        assignment=assignment,
        deliveries=deliveries,
        cost_ledger=cost_ledger,
        purchase_orders=purchase_orders,
        order_events=order_events,
    )
