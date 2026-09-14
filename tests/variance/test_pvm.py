"""Price-volume-mix decomposition.

Every expected value here was computed by hand from the fixtures, and the decisive property -
that the effects sum exactly to the change - is asserted on every case. A decomposition with a
residual is not a decomposition, it is an allocation with a plug line.
"""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.variance import (
    EFFECT_ORDER,
    contribution_pareto,
    price_volume_mix,
    unit_value_bridge,
    waterfall,
)


@pytest.fixture
def pure_mix_shift() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flat total quantity, volume shifting from the expensive segment to the cheap one.

    Base: A at 100 units and a rate of 10, B at 100 units and a rate of 20 - total 3,000.
    Current: A at 150 units and a rate of 11, B at 50 units and a rate of 22 - total 2,750.

    Total quantity is unchanged, so the volume effect must be exactly zero. By hand:
    mix is -500, rate is +250, and the total change is -250.
    """
    base = pd.DataFrame(
        {"segment": ["A", "B"], "quantity": [100.0, 100.0], "value": [1000.0, 2000.0]}
    )
    current = pd.DataFrame(
        {"segment": ["A", "B"], "quantity": [150.0, 50.0], "value": [1650.0, 1100.0]}
    )
    return base, current


def test_effects_match_the_hand_calculation(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    base, current = pure_mix_shift
    result = price_volume_mix(base, current, key="segment")

    assert result.base_total == pytest.approx(3000.0)
    assert result.current_total == pytest.approx(2750.0)
    assert result.delta == pytest.approx(-250.0)

    assert result.effects["volume"] == pytest.approx(0.0), "total quantity did not move"
    assert result.effects["mix"] == pytest.approx(-500.0)
    assert result.effects["rate"] == pytest.approx(250.0)
    assert result.effects["new"] == pytest.approx(0.0)
    assert result.effects["discontinued"] == pytest.approx(0.0)


def test_the_decomposition_reconciles_exactly(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    base, current = pure_mix_shift
    result = price_volume_mix(base, current, key="segment")
    assert result.reconciliation_error == pytest.approx(0.0, abs=1e-9)
    assert list(result.effects.index) == list(EFFECT_ORDER)


def test_per_segment_effects_are_quantity_and_rate(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    """Mix is an aggregate concept; per segment there are only two effects."""
    base, current = pure_mix_shift
    detail = price_volume_mix(base, current, key="segment").detail

    assert detail.loc["A", "quantity_effect"] == pytest.approx(500.0)
    assert detail.loc["B", "quantity_effect"] == pytest.approx(-1000.0)
    assert detail.loc["A", "rate_effect"] == pytest.approx(150.0)
    assert detail.loc["B", "rate_effect"] == pytest.approx(100.0)

    # Volume plus mix equals the summed quantity effect, by construction.
    result = price_volume_mix(base, current, key="segment")
    assert result.effects["volume"] + result.effects["mix"] == pytest.approx(
        detail["quantity_effect"].sum()
    )


def test_pure_volume_growth_produces_no_mix_or_rate() -> None:
    base = pd.DataFrame(
        {"segment": ["A", "B"], "quantity": [100.0, 100.0], "value": [1000.0, 2000.0]}
    )
    current = pd.DataFrame(
        {"segment": ["A", "B"], "quantity": [200.0, 200.0], "value": [2000.0, 4000.0]}
    )
    result = price_volume_mix(base, current, key="segment")

    assert result.effects["volume"] == pytest.approx(3000.0)
    assert result.effects["mix"] == pytest.approx(0.0)
    assert result.effects["rate"] == pytest.approx(0.0)


def test_new_and_discontinued_segments_get_their_own_effects() -> None:
    base = pd.DataFrame(
        {"segment": ["A", "GONE"], "quantity": [100.0, 50.0], "value": [1000.0, 500.0]}
    )
    current = pd.DataFrame(
        {"segment": ["A", "NEW"], "quantity": [100.0, 10.0], "value": [1000.0, 300.0]}
    )
    result = price_volume_mix(base, current, key="segment")

    assert result.effects["new"] == pytest.approx(300.0)
    assert result.effects["discontinued"] == pytest.approx(-500.0)
    assert result.effects["volume"] == pytest.approx(0.0)
    assert result.effects["mix"] == pytest.approx(0.0)
    assert result.effects["rate"] == pytest.approx(0.0)
    assert result.reconciliation_error == pytest.approx(0.0, abs=1e-9)

    presence = result.detail["presence"]
    assert presence["NEW"] == "new"
    assert presence["GONE"] == "discontinued"
    assert presence["A"] == "both"


def test_transaction_level_input_is_aggregated() -> None:
    base = pd.DataFrame(
        {"segment": ["A"] * 3, "quantity": [1.0, 1.0, 1.0], "value": [10.0, 10.0, 10.0]}
    )
    current = pd.DataFrame({"segment": ["A"] * 2, "quantity": [1.0, 1.0], "value": [20.0, 20.0]})
    result = price_volume_mix(base, current, key="segment")

    assert result.base_total == pytest.approx(30.0)
    assert result.detail.loc["A", "rate_base"] == pytest.approx(10.0)
    assert result.detail.loc["A", "rate_current"] == pytest.approx(20.0)


def test_multiple_key_columns_are_supported(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    base, current = pure_mix_shift
    base = base.assign(site="CD-SP")
    current = current.assign(site="CD-SP")
    result = price_volume_mix(base, current, key=["site", "segment"])
    assert result.reconciliation_error == pytest.approx(0.0, abs=1e-9)
    assert result.detail.index.nlevels == 2


@pytest.mark.parametrize("missing", ["segment", "quantity", "value"])
def test_missing_columns_are_reported(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame], missing: str
) -> None:
    base, current = pure_mix_shift
    with pytest.raises(KeyError, match=missing):
        price_volume_mix(base.drop(columns=[missing]), current, key="segment")


def test_empty_period_is_refused(pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    base, current = pure_mix_shift
    with pytest.raises(ValueError, match="both periods must contain rows"):
        price_volume_mix(base.iloc[:0], current, key="segment")


def test_value_without_quantity_is_refused() -> None:
    base = pd.DataFrame({"segment": ["A"], "quantity": [0.0], "value": [100.0]})
    current = pd.DataFrame({"segment": ["A"], "quantity": [1.0], "value": [10.0]})
    with pytest.raises(ValueError, match="implied rate is undefined"):
        price_volume_mix(base, current, key="segment")


def test_unit_bridge_matches_the_hand_calculation(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    """Per unit: rate +1.25, mix -2.50, total -1.25. Volume cannot appear."""
    base, current = pure_mix_shift
    bridge = unit_value_bridge(base, current, key="segment")

    assert bridge.base_rate == pytest.approx(15.0)
    assert bridge.current_rate == pytest.approx(13.75)
    assert bridge.effects["rate"] == pytest.approx(1.25)
    assert bridge.effects["mix"] == pytest.approx(-2.50)
    assert bridge.reconciliation_error == pytest.approx(0.0, abs=1e-9)
    assert set(bridge.effects.index) == {"rate", "mix"}


def test_growth_alone_cannot_move_a_per_unit_metric() -> None:
    base = pd.DataFrame(
        {"segment": ["A", "B"], "quantity": [100.0, 100.0], "value": [1000.0, 2000.0]}
    )
    current = base.assign(quantity=base["quantity"] * 3, value=base["value"] * 3)
    bridge = unit_value_bridge(base, current, key="segment")

    assert bridge.delta == pytest.approx(0.0)
    assert bridge.effects["rate"] == pytest.approx(0.0)
    assert bridge.effects["mix"] == pytest.approx(0.0)


def test_an_omitted_dimension_reappears_as_a_rate_effect() -> None:
    """The module's central warning, on a case where the arithmetic is exact.

    Two channels whose rates never change; only their shares move. Segmented by channel, the
    whole movement is mix and the rate effect is exactly zero. Collapse the channel dimension
    and the identical movement is reported as 100% rate - which in a review is attributed to
    whoever owns the rate.
    """
    base = pd.DataFrame(
        {"channel": ["store", "d2c"], "quantity": [90.0, 10.0], "value": [900.0, 200.0]}
    )
    current = pd.DataFrame(
        {"channel": ["store", "d2c"], "quantity": [50.0, 50.0], "value": [500.0, 1000.0]}
    )

    segmented = unit_value_bridge(base, current, key="channel")
    assert segmented.delta == pytest.approx(4.0)
    assert segmented.effects["mix"] == pytest.approx(4.0)
    assert segmented.effects["rate"] == pytest.approx(0.0)

    collapsed = unit_value_bridge(
        base.assign(channel="all"), current.assign(channel="all"), key="channel"
    )
    assert collapsed.delta == pytest.approx(4.0), "the movement itself is identical"
    assert collapsed.effects["rate"] == pytest.approx(4.0)
    assert collapsed.effects["mix"] == pytest.approx(0.0)


def test_a_new_segment_is_priced_at_the_base_average_rate() -> None:
    base = pd.DataFrame({"segment": ["A"], "quantity": [100.0], "value": [1000.0]})
    current = pd.DataFrame(
        {"segment": ["A", "NEW"], "quantity": [100.0, 100.0], "value": [1000.0, 3000.0]}
    )
    bridge = unit_value_bridge(base, current, key="segment")

    assert bridge.new_quantity_share == pytest.approx(0.5)
    # The new segment adds half the quantity at the base average rate, so mix is zero and its
    # whole departure from that average lands in rate.
    assert bridge.effects["mix"] == pytest.approx(0.0)
    assert bridge.effects["rate"] == pytest.approx(10.0)
    assert bridge.reconciliation_error == pytest.approx(0.0, abs=1e-9)


def test_unit_bridge_requires_positive_quantity() -> None:
    base = pd.DataFrame({"segment": ["A"], "quantity": [0.0], "value": [0.0]})
    current = pd.DataFrame({"segment": ["A"], "quantity": [1.0], "value": [10.0]})
    with pytest.raises(ValueError, match="positive total quantity"):
        unit_value_bridge(base, current, key="segment")


def test_pareto_ranks_by_absolute_contribution(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    base, current = pure_mix_shift
    ranked = contribution_pareto(price_volume_mix(base, current, key="segment"))

    # B contributes -900, A contributes +650; B ranks first despite the total falling.
    assert ranked.index[0] == "B"
    assert ranked.iloc[0]["contribution"] == pytest.approx(-900.0)
    assert ranked["cumulative_share"].iloc[-1] == pytest.approx(1.0)


def test_pareto_validates_top(pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame]) -> None:
    base, current = pure_mix_shift
    with pytest.raises(ValueError, match="top must be positive"):
        contribution_pareto(price_volume_mix(base, current, key="segment"), top=0)


def test_waterfall_bars_land_on_the_closing_total(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    base, current = pure_mix_shift
    result = price_volume_mix(base, current, key="segment")
    chart = waterfall(result)

    assert list(chart["kind"]) == ["total", *["effect"] * 5, "total"]
    assert chart.iloc[0]["end"] == pytest.approx(result.base_total)
    assert chart.iloc[-2]["end"] == pytest.approx(result.current_total)
    assert chart.iloc[-1]["end"] == pytest.approx(result.current_total)
    # Zero effects are kept, so "mix explained none of it" stays on the chart.
    assert len(chart) == 7


def test_waterfall_works_for_a_bridge(
    pure_mix_shift: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    base, current = pure_mix_shift
    chart = waterfall(unit_value_bridge(base, current, key="segment"))
    assert list(chart["label"]) == ["rate base", "rate", "mix", "rate current"]
    assert chart.iloc[-1]["end"] == pytest.approx(13.75)
