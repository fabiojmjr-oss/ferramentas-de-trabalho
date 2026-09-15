"""How much of a service number is definition rather than performance.

Run:
    python examples/01_service_definition.py

The same order book is measured four ways. Nothing about the operation changes between the
rows - only the reporting conventions. The spread between the best and the worst reading is
usually wider than the improvement a steering committee is debating, which is why the
definition has to be settled before the target.
"""

from __future__ import annotations

import pandas as pd

from oplab.kpi import ServicePolicy, fill_rate, otif, service_sensitivity
from oplab.synth import generate_dataset


def main() -> None:
    pd.set_option("display.width", 140)
    pd.set_option("display.max_columns", 20)

    dataset = generate_dataset()
    lines = dataset.order_lines

    print("Order lines:", f"{len(lines):,}")
    print("Statuses:")
    print(lines["status"].value_counts().to_string())

    print("\n1. The same data under four reporting conventions")
    sensitivity = service_sensitivity(lines)
    print(
        sensitivity[["policy", "otif", "on_time", "in_full", "lines_in_scope"]]
        .round(4)
        .to_string(index=False)
    )
    spread = sensitivity["otif"].max() - sensitivity["otif"].min()
    print(f"\n   Spread attributable to definition alone: {spread:.1%}")

    print("\n2. Fill rate on three bases, one order book")
    for basis in ("unit", "line", "order"):
        print(f"   {basis:>6}: {float(fill_rate(lines, basis=basis)):.4f}")
    print("   Quoting one of these without naming the basis is how two functions report")
    print("   different service levels from the same extract and both are right.")

    print("\n3. OTIF by site, under the default policy")
    print(otif(lines, by="site").round(4).sort_values().to_string())

    print("\n4. What the ranking does when the convention changes")
    comparison = pd.DataFrame(
        {
            "strict": otif(lines, ServicePolicy(open_treatment="fail"), by="site"),
            "standard": otif(lines, by="site"),
            "grace_1day": otif(lines, ServicePolicy(grace_minutes=1440), by="site"),
        }
    ).round(4)
    comparison["rank_strict"] = comparison["strict"].rank(ascending=False).astype(int)
    comparison["rank_grace"] = comparison["grace_1day"].rank(ascending=False).astype(int)
    print(comparison.to_string())


if __name__ == "__main__":
    main()
