"""The replenishment history, and the property that makes the inventory module possible."""

from __future__ import annotations

import numpy as np

from oplab.synth import SUPPLIER_PROFILES, SynthConfig, generate_catalog, generate_purchase_orders


def orders():
    cfg = SynthConfig(days=365, n_skus=200)
    rng = np.random.default_rng(cfg.seed)
    catalog = generate_catalog(cfg, rng)
    return generate_purchase_orders(cfg, catalog, rng)


def test_every_order_has_a_positive_lead_time_and_a_known_supplier() -> None:
    frame = orders()
    assert not frame.empty
    assert (frame["lead_days"] >= 1.0).all()
    assert set(frame["supplier"]) <= set(SUPPLIER_PROFILES)
    assert (frame["received_date"] > frame["ordered_date"]).all()
    assert frame["po_id"].is_unique


def test_each_sku_is_sourced_from_exactly_one_supplier() -> None:
    """A per-SKU policy needs one lead-time distribution per SKU, not a network average."""
    frame = orders()
    assert (frame.groupby("sku")["supplier"].nunique() == 1).all()


def test_mean_lead_time_and_lead_time_variability_are_uncorrelated_by_design() -> None:
    """If short lead times came bundled with low variability there would be nothing to show.

    The shortest-mean supplier must not also be the tightest, or every safety-stock comparison
    would rank suppliers identically on either property and the finding that variability rather
    than the mean sizes safety stock would be unobservable.
    """
    frame = orders()
    stats = frame.groupby("supplier")["lead_days"].agg(["mean", "std"])
    stats["cv"] = stats["std"] / stats["mean"]
    by_mean = list(stats.sort_values("mean").index)
    by_cv = list(stats.sort_values("cv").index)
    assert by_mean != by_cv

    # Specifically: the supplier with the shortest realised lead time is not the most reliable.
    assert stats.loc[by_mean[0], "cv"] > stats.loc[by_cv[0], "cv"]


def test_realised_lead_times_are_right_skewed() -> None:
    """A normal safety-stock formula is being asked to cover a tail it does not have."""
    frame = orders()
    for _, group in frame.groupby("supplier"):
        values = group["lead_days"].to_numpy()
        centred = values - values.mean()
        skew = float(np.mean(centred**3) / values.std() ** 3)
        assert skew > 0.0


def test_the_quoted_lead_time_is_a_promise_rather_than_a_measurement() -> None:
    frame = orders()
    stats = frame.groupby("supplier").agg(
        quoted=("quoted_lead_days", "first"), realised=("lead_days", "mean")
    )
    assert (stats["realised"] >= stats["quoted"]).all()
    assert (stats["realised"] > stats["quoted"]).any()


def test_a_minority_of_orders_arrive_short() -> None:
    frame = orders()
    short = frame["qty_received"] < frame["qty_ordered"]
    assert 0.0 < short.mean() < 0.2
    assert (frame["qty_received"] >= 1).all()


def test_the_history_is_reproducible_from_the_seed() -> None:
    first, second = orders(), orders()
    assert first.equals(second)
