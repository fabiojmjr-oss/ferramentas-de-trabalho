"""A one-page diagnostic of a four-site network.

Run:
    python examples/03_network_diagnostic.py

The question this answers is the one a regional manager actually has on Monday morning: which
site needs attention, and for what. It is deliberately not a scorecard. A ranking says who is
last; a diagnostic says which lever to pull, and the two rarely point at the same action.
"""

from __future__ import annotations

import pandas as pd

from oplab.kpi import (
    appointment_adherence,
    dock_to_stock,
    inventory_record_accuracy,
    order_cycle_time,
    otif,
)
from oplab.synth import generate_dataset


def main() -> None:
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 30)

    dataset = generate_dataset()
    lines = dataset.order_lines

    service = pd.DataFrame({"otif": otif(lines, by="site")})

    cycle = order_cycle_time(lines, by="site")
    internal = cycle.query("stage == 'internal_h'").set_index("site")
    transit = cycle.query("stage == 'transit_h'").set_index("site")
    service["internal_p50_h"] = internal["p50"]
    service["transit_p50_h"] = transit["p50"]
    # The tail is what the customer complains about, and the mean hides it.
    service["transit_p95_h"] = transit["p95"]
    service["transit_tail_ratio"] = transit["p95"] / transit["p50"]

    inbound = dock_to_stock(dataset.receipts).query("stage == 'dock_to_stock_h'").set_index("site")
    service["dock_to_stock_p50_h"] = inbound["p50"]
    service["dock_to_stock_p95_h"] = inbound["p95"]

    accuracy = inventory_record_accuracy(
        dataset.cycle_counts, unit_cost=dataset.catalog.set_index("sku")["unit_cost"]
    ).set_index("site")
    service["inventory_accuracy"] = accuracy["location_accuracy"]
    service["inventory_exposure"] = accuracy["abs_variance_value"]

    table = service.sort_values("otif")
    print("Network diagnostic")
    print(table.round(3).to_string())

    print("\nWhere each site's service loss actually sits")
    for site in table.index:
        row = table.loc[site]
        drivers = []
        if row["transit_tail_ratio"] > 2.0:
            drivers.append(f"transport tail (p95 is {row['transit_tail_ratio']:.1f}x the median)")
        if row["dock_to_stock_p50_h"] > 10.0:
            drivers.append(f"put-away backlog ({row['dock_to_stock_p50_h']:.1f} h to stock)")
        if row["inventory_accuracy"] < 0.96:
            drivers.append(f"record accuracy ({row['inventory_accuracy']:.1%} of locations)")
        verdict = "; ".join(drivers) if drivers else "no single dominant driver"
        print(f"  {site}  OTIF {row['otif']:.1%}  ->  {verdict}")

    print("\nInbound carrier adherence, network-wide")
    print(appointment_adherence(dataset.receipts).round(3).to_string(index=False))
    print("\n  Carrier performance is a network-level lever, not a site-level one: the worst")
    print("  carrier degrades every site it serves, so fixing it at one site fixes nothing.")
    print("  This is the distinction between a site problem and a network problem, and it is")
    print("  the one most regional scorecards cannot make.")


if __name__ == "__main__":
    main()
