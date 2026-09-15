"""The cost ledger fixture."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from oplab.synth import size_band


def test_size_band_edges() -> None:
    bands = size_band(pd.Series([1, 2, 4, 5, 50]))
    assert list(bands) == ["1 line", "2-4 lines", "2-4 lines", "5+ lines", "5+ lines"]


def test_one_row_per_order(dataset) -> None:  # type: ignore[no-untyped-def]
    ledger = dataset.cost_ledger
    assert ledger["order_id"].is_unique
    assert len(ledger) == dataset.order_lines["order_id"].nunique()


def test_costs_are_positive_and_add_up(dataset) -> None:  # type: ignore[no-untyped-def]
    ledger = dataset.cost_ledger
    for column in ("freight_brl", "handling_brl", "total_brl"):
        assert (ledger[column] > 0).all()
    assert np.allclose(
        ledger["total_brl"], ledger["freight_brl"] + ledger["handling_brl"], atol=0.02
    )


def test_order_composition_matches_the_order_book(dataset) -> None:  # type: ignore[no-untyped-def]
    lines = dataset.order_lines.groupby("order_id", observed=True).agg(
        lines=("line_id", "size"), units=("qty_ordered", "sum")
    )
    ledger = dataset.cost_ledger.set_index("order_id")
    joined = ledger.join(lines, rsuffix="_book")
    assert (joined["lines"] == joined["lines_book"]).all()
    assert (joined["units"] == joined["units_book"]).all()


def test_remote_sites_cost_more_per_order(dataset) -> None:  # type: ignore[no-untyped-def]
    by_site = dataset.cost_ledger.groupby("site", observed=True)["total_brl"].mean()
    assert by_site["CD-PE"] > by_site["CD-SP"]


def test_consumer_delivery_costs_more_than_store_delivery(dataset) -> None:  # type: ignore[no-untyped-def]
    by_channel = dataset.cost_ledger.groupby("channel", observed=True)["total_brl"].mean()
    assert by_channel["d2c"] > by_channel["store"]


def test_the_three_injected_movements_are_present(dataset) -> None:  # type: ignore[no-untyped-def]
    """The ledger must contain a rate move, a local rate move and a mix move.

    Without all three, a decomposition has nothing to separate and the tool cannot be
    demonstrated - or trusted.
    """
    ledger = dataset.cost_ledger.copy()
    ledger["half"] = (
        pd.to_datetime(ledger["order_date"]).dt.dayofyear > dataset.config.days / 2
    ).map({False: "H1", True: "H2"})

    # A rate movement everywhere: freight per kilogram rises with the fuel index.
    freight_per_kg = ledger.groupby("half", observed=True).apply(
        lambda g: g["freight_brl"].sum() / g["weight_kg"].sum(), include_groups=False
    )
    assert freight_per_kg["H2"] > freight_per_kg["H1"] * 1.02

    # A local rate movement: handling per line rises at one site only.
    handling = ledger.groupby(["site", "half"], observed=True).apply(
        lambda g: g["handling_brl"].sum() / g["lines"].sum(), include_groups=False
    )
    drift = handling["CD-PE"]["H2"] / handling["CD-PE"]["H1"]
    steady = handling["CD-SP"]["H2"] / handling["CD-SP"]["H1"]
    assert drift > steady * 1.05

    # A mix movement: the consumer channel grows materially.
    share = ledger.groupby("half", observed=True)["channel"].apply(lambda s: (s == "d2c").mean())
    assert share["H2"] > share["H1"] * 1.5


def test_ledger_is_reproducible() -> None:
    from oplab.synth import SynthConfig, generate_dataset

    config = SynthConfig(days=35, n_skus=25)
    pd.testing.assert_frame_equal(
        generate_dataset(config).cost_ledger, generate_dataset(config).cost_ledger
    )


def test_ledger_appears_in_the_dataset_tables(dataset) -> None:  # type: ignore[no-untyped-def]
    assert "cost_ledger" in dataset.tables
    assert pytest.approx(dataset.cost_ledger["total_brl"].sum(), rel=1e-9) == float(
        dataset.tables["cost_ledger"]["total_brl"].sum()
    )
