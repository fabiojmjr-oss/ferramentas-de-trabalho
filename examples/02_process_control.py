"""Chart the process before judging it capable.

Run:
    python examples/02_process_control.py

The measurement series carries a mean shift injected at subgroup 43. The script works through
four things in order: the range chart stays in control while the mean moves; limits estimated
on the disturbed period mis-date the change; the Cpk-to-Ppk gap identifies the problem as one
of control rather than of variation; and a service p chart signals on a quarter of all days
until the unit of analysis is corrected.
"""

from __future__ import annotations

import pandas as pd

from oplab.spc import (
    ALL_RULES,
    capability_from_subgroups,
    overdispersion_ratio,
    p_chart,
    xbar_r_chart,
)
from oplab.synth import generate_dataset


def main() -> None:
    pd.set_option("display.width", 140)

    dataset = generate_dataset()
    subgroups = dataset.subgroups

    print("1. Read the range chart first")
    print("   If dispersion is unstable, the X-bar limits are built on a quantity that has no")
    print("   single value, and any conclusion about the mean is unsafe.")
    xbar, ranges = xbar_r_chart(subgroups, baseline=slice(0, 40), rules=ALL_RULES)
    print(f"\n   {ranges.summary()['signals']:.0f} signal(s) on the R chart")
    print(f"   {xbar.summary()['signals']:.0f} signal(s) on the X-bar chart")

    print("\n2. Where the chart dates the change")
    first = xbar.violations.query("position >= 40").head(3)
    print(first[["rule", "description", "label", "z"]].to_string(index=False))

    print("\n3. Baseline choice: same limits, different centre line")
    whole_series, _ = xbar_r_chart(subgroups, rules=ALL_RULES)
    comparison = pd.DataFrame(
        {
            "limits from stable phase": [
                xbar.center,
                float(xbar.ucl.iloc[0] - xbar.center),
                int(xbar.out_of_control.iloc[:40].sum()),
            ],
            "limits from whole series": [
                whole_series.center,
                float(whole_series.ucl.iloc[0] - whole_series.center),
                int(whole_series.out_of_control.iloc[:40].sum()),
            ],
        },
        index=["centre line", "limit half-width", "signals in the stable phase"],
    )
    print(comparison.round(3).to_string())
    print("\n   The half-width barely moves: it comes from within-subgroup range, which a mean")
    print("   shift does not touch. What moves is the centre line, and it manufactures")
    print("   signals in a period that was actually stable.")

    print("\n4. Capability, computed only now that the process is charted")
    cap = capability_from_subgroups(subgroups, lsl=492.0, usl=508.0)
    headline = cap.to_series()[
        ["mean", "sigma_within", "sigma_overall", "cp", "cpk", "pp", "ppk", "expected_ppm"]
    ]
    print(headline.round(4).to_string())
    print(f"\n   Cpk {cap.cpk:.2f} against Ppk {cap.ppk:.2f}.")
    print("   Short-term capability is adequate and long-term performance is not, so the gap")
    print("   is a control problem - the process is not held where it can run - and not a")
    print("   variation-reduction problem. Different intervention, different owner.")
    if cap.normality_warning:
        print(f"\n   Caveat: {cap.normality_warning}")

    print("\n5. The right chart, and the right unit of analysis")
    lines = dataset.order_lines
    delivered = lines.loc[(lines["status"] == "delivered") & (lines["site"] == "CD-SP")].copy()
    delivered["late"] = delivered["delivered_ts"] > delivered["promised_ts"]
    delivered["day"] = delivered["delivered_ts"].dt.normalize()

    # Line level: every line of an order rides the same vehicle, so one late truck produces a
    # dozen correlated failures and the trials are not independent.
    per_line = (
        delivered.groupby("day").agg(total=("line_id", "size"), late=("late", "sum")).iloc[3:-3]
    )
    line_chart = p_chart(per_line["late"], per_line["total"].astype(float))

    # Order level: one transit draw per order, which is the independent event.
    orders = delivered.groupby("order_id").agg(day=("day", "first"), late=("late", "max"))
    per_order = orders.groupby("day").agg(total=("late", "size"), late=("late", "sum")).iloc[3:-3]
    order_chart = p_chart(per_order["late"], per_order["total"].astype(float))

    diagnosis = pd.DataFrame(
        {
            "unit of analysis": ["order line", "order"],
            "n per day": [
                f"{int(per_line['total'].min())}-{int(per_line['total'].max())}",
                f"{int(per_order['total'].min())}-{int(per_order['total'].max())}",
            ],
            "days signalled": [
                f"{int(line_chart.out_of_control.sum())} of {len(per_line)}",
                f"{int(order_chart.out_of_control.sum())} of {len(per_order)}",
            ],
            "overdispersion": [
                round(overdispersion_ratio(line_chart), 2),
                round(overdispersion_ratio(order_chart), 2),
            ],
        }
    )
    print(diagnosis.to_string(index=False))
    print("\n   Same operation, same period, same chart type. At line level the observed")
    print("   variation is roughly twice what the binomial model predicts, so a quarter of all")
    print("   days signal and every one of those signals is an artefact of the unit of")
    print("   analysis. At order level the ratio is 1.0 and the signal rate collapses to the")
    print("   expected false-alarm rate. Check overdispersion before investigating a signal.")
    low = float((order_chart.ucl - order_chart.center).min())
    high = float((order_chart.ucl - order_chart.center).max())
    print("\n   The limits also move with the denominator, which is the reason to use a p")
    print(f"   chart at all: the half-width ranges from {low:.4f} to {high:.4f} across the")
    print("   period. An individuals chart would hold it constant and treat a Sunday and a")
    print("   Wednesday as equally informative.")


if __name__ == "__main__":
    main()
