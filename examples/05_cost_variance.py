"""Why cost per order moved, and who owns each part of it.

Run:
    python examples/05_cost_variance.py

The script answers the question a performance review actually opens with, and then shows the
failure mode that makes most answers to it wrong: an omitted segmentation dimension does not
disappear, it reappears inside the rate effect and is attributed to whoever owns the rate.
"""

from __future__ import annotations

import pandas as pd

from oplab.synth import generate_dataset
from oplab.variance import (
    contribution_pareto,
    price_volume_mix,
    unit_value_bridge,
    waterfall,
)


def main() -> None:
    pd.set_option("display.width", 170)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    ledger = dataset.cost_ledger.copy()
    ledger["quantity"] = 1.0  # one order per row
    ledger["half"] = (
        (pd.to_datetime(ledger["order_date"]).dt.month > 6)
        .map({False: "H1", True: "H2"})
        .astype(str)
    )
    base = ledger.loc[ledger["half"] == "H1"]
    current = ledger.loc[ledger["half"] == "H2"]

    segmentation = ["site", "channel", "size_band"]

    print("1. The total, which is the wrong question")
    total = price_volume_mix(
        base, current, key=segmentation, quantity="quantity", value="total_brl"
    )
    print(
        f"   Operating cost {total.base_total / 1e6:.2f}M to {total.current_total / 1e6:.2f}M BRL,"
        f" {total.relative_delta:+.1%}"
    )
    print(total.summary().round(2).to_string())
    volume_share = total.effects["volume"] / total.delta
    print(f"\n   {volume_share:.0%} of the increase is volume: the same business got bigger. That")
    print("   is not a cost problem, and a review that stops at the total will treat it as one.")

    print("\n2. The right question: cost per order")
    bridge = unit_value_bridge(
        base, current, key=segmentation, quantity="quantity", value="total_brl"
    )
    print(
        f"   {bridge.base_rate:.2f} to {bridge.current_rate:.2f} BRL per order,"
        f" {bridge.relative_delta:+.1%}"
    )
    print(bridge.summary().round(4).to_string())
    print(f"   reconciliation error: {bridge.reconciliation_error:.2e}")
    print("\n   Volume does not appear, and cannot: growth alone is arithmetically incapable of")
    print("   moving a per-unit metric. Either the rates moved inside the segments, or the mix")
    print("   moved between them.")

    print("\n3. The failure mode: what an omitted dimension does")
    without_channel = unit_value_bridge(
        base,
        current,
        key=["site", "size_band"],
        quantity="quantity",
        value="total_brl",
    )
    comparison = pd.DataFrame(
        {
            "segmented by site and size": without_channel.effects,
            "with channel added": bridge.effects,
        }
    )
    comparison.loc["total"] = comparison.sum()
    print(comparison.round(4).to_string())
    hidden = bridge.effects["mix"] - without_channel.effects["mix"]
    print(
        f"\n   The movement is identical either way: {bridge.delta:+.2f} BRL per order. But"
        f" {hidden:.2f} BRL"
    )
    print("   of it moves from 'rate' to 'mix' the moment the channel dimension is added -")
    print(
        f"   {without_channel.effects['rate'] / without_channel.delta:.0%} of the rise looks"
        " operational without it, and"
    )
    print(f"   {bridge.effects['rate'] / bridge.delta:.0%} with it.")
    print("\n   The direct-to-consumer share grew over the year, and a home delivery costs")
    print("   nearly twice as much per stop as a store delivery. That is a commercial and")
    print("   network decision showing up in an operational indicator. Segment for it or the")
    print("   warehouse gets the blame for it.")

    print("\n4. Where the remaining movement actually sits")
    print(contribution_pareto(bridge, top=6).round(4).to_string())
    print("\n   Ranked by absolute contribution, because offsetting movements are the finding:")
    print("   a flat total can hide one segment deteriorating by exactly what another gained.")

    print("\n5. The waterfall, per order")
    print(waterfall(bridge).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
