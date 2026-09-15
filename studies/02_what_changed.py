"""Something changed. What, and what do I do on Monday?

Run:
    python studies/02_what_changed.py

Study 01 asks what to fund: a comparison between candidates, decided by pricing each one. This
study asks the opposite kind of question. Three signals are on the slide at the Monday review, the
room wants to act on all three, and the work is to establish which of them are real, which are
artefacts of measurement, and whether any two of them are even about the same thing.

The answer here is that **almost nothing on the slide supports an action**, and each refusal is
backed by a measurement rather than by caution. That is the harder discipline: reacting to a
signal that is not one is not neutral, it moves a stable process and is the thing control charts
were invented to prevent.
"""

from __future__ import annotations

import pandas as pd

from oplab.kpi import otif, service_sensitivity
from oplab.mining import waiting_ranked
from oplab.spc import (
    capability_from_subgroups,
    overdispersion_ratio,
    p_chart,
    xbar_r_chart,
)
from oplab.synth import generate_dataset

ALL_RULES = tuple(range(1, 9))
BASELINE = slice(0, 40)
LSL, USL = 495.0, 505.0


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    dataset = generate_dataset()

    print("THE SLIDE AT THE MONDAY REVIEW")
    print("   1. October OTIF was 78.1% - the worst month of the year.")
    print("   2. December recovered to 80.0% - the best month of the year.")
    print("   3. The process measurement is out of control.")
    print("   The room wants a recovery plan for October, a lesson learned from December,")
    print("   and a root cause for the process. Three actions, one meeting.")

    monthly = _monthly(dataset)
    print("\n" + "=" * 96)
    print("CHECK 1 - IS OCTOBER A SIGNAL?")
    print("=" * 96)
    october = _check_october(monthly, dataset)

    print("\n" + "=" * 96)
    print("CHECK 2 - IS DECEMBER A RECOVERY?")
    print("=" * 96)
    _check_december(dataset, monthly)

    print("\n" + "=" * 96)
    print("CHECK 3 - IS THE PROCESS SIGNAL REAL?")
    print("=" * 96)
    shift = _check_process(dataset)

    print("\n" + "=" * 96)
    print("CHECK 4 - ARE SIGNALS 1 AND 3 ABOUT THE SAME THING?")
    print("=" * 96)
    _check_window(dataset, monthly)

    print("\n" + "=" * 96)
    print("WHAT TO DO ON MONDAY")
    print("=" * 96)
    _decide(dataset, october, shift)


def _monthly(dataset: object) -> pd.DataFrame:
    """OTIF per month under the standard policy, with the failure count the p-chart needs."""
    lines = dataset.order_lines.copy()
    lines["month"] = pd.to_datetime(lines["order_ts"]).dt.to_period("M").astype(str)
    served = lines.loc[lines["status"] != "cancelled"]
    table = served.groupby("month").agg(lines=("line_id", "size"))
    table["otif"] = otif(served, by="month")
    table["failures"] = ((1.0 - table["otif"]) * table["lines"]).round().astype(int)
    return table


def _check_october(monthly: pd.DataFrame, dataset: object) -> dict[str, float]:
    chart = p_chart(monthly["failures"], monthly["lines"], rules=ALL_RULES)
    ratio = overdispersion_ratio(chart)
    worst = str(monthly["otif"].idxmin())
    annual_range = float(monthly["otif"].max() - monthly["otif"].min())

    print(monthly.round(4).to_string())
    worst_z = float(chart.violations.query("label == @worst")["z"].max())
    print(f"\n   The p-chart flags {worst}: {worst_z:.2f} sigma, rule 1. So the signal is real -")
    print("   and two things about the chart that produced it are not.")

    print(
        f"\n   First, the limits are absurdly tight. The upper limit sits between"
        f" {chart.ucl.min():.4f} and {chart.ucl.max():.4f}"
    )
    print(
        f"   across the months - about"
        f" {(chart.ucl.max() - chart.center) * 100:.1f} points above a centre of"
        f" {chart.center:.4f}, on {monthly['lines'].mean():,.0f} lines a"
    )
    print("   month. At that sample size any real-world month registers as a signal, because the")
    print("   chart is answering 'is this the same binomial process?' and nobody believes it is.")

    print(
        f"\n   Second, the overdispersion ratio is {ratio:.3f}. A p-chart assumes independent"
        " trials, and"
    )
    print("   lines within an order are not independent - one late truck fails every line on it.")
    print(
        f"   The true spread is {ratio:.2f} times the binomial assumption, so the correct sigma"
        f" is {ratio**0.5:.2f}"
    )
    print(
        f"   times wider and the adjusted signal is {worst_z / ratio**0.5:.2f} sigma. Still a"
        " signal, and no longer"
    )
    print("   a figure anybody should quote as computed.")

    conventions = service_sensitivity(dataset.order_lines)
    convention_range = float(conventions["otif"].max() - conventions["otif"].min())
    print(
        f"\n   And the scale settles it. The whole year moves"
        f" {annual_range * 100:.2f} points month to month. The same"
    )
    print(
        f"   order book moves {convention_range * 100:.2f} points on convention alone -"
        f" {convention_range / annual_range:.1f} times as much, with no"
    )
    print("   change to the operation at all.")
    print(
        f"\n   VERDICT: real, and smaller than the measurement. A recovery plan for a"
        f" {annual_range * 100:.1f}-point"
    )
    print("   move, on a chart whose own assumption is violated, is tampering with a stable")
    print("   process. Fix the unit of analysis first; there is nothing to recover yet.")
    return {"annual_range": annual_range, "convention_range": convention_range, "ratio": ratio}


def _check_december(dataset: object, monthly: pd.DataFrame) -> None:
    lines = dataset.order_lines.copy()
    lines["month"] = pd.to_datetime(lines["order_ts"]).dt.to_period("M").astype(str)
    status = lines.groupby("month")["status"].value_counts().unstack(fill_value=0)
    print(status.to_string())

    december = status.index[-1]
    open_lines = int(status.loc[december, "in_transit"] + status.loc[december, "open"])
    best = str(monthly["otif"].idxmax())
    print(
        f"\n   {december} is the only month with lines that have no outcome yet:"
        f" {open_lines:,} of them,"
    )
    print(
        f"   {open_lines / status.loc[december].sum():.1%} of the month. Under the standard policy"
        " they are excluded from"
    )
    print("   the denominator rather than counted as failures - which is defensible, and is why")
    print(f"   {best} reads as the best month of the year.")
    print("\n   VERDICT: not a recovery. It is the horizon ending mid-flight. The month with the")
    print("   most unresolved lines cannot also be the best month; one of those two statements")
    print("   is an artefact, and it is the second. A lesson learned from December would be a")
    print("   lesson learned from a censoring rule.")


def _check_process(dataset: object) -> dict[str, float]:
    clean, ranges = xbar_r_chart(dataset.subgroups, baseline=BASELINE, rules=ALL_RULES)
    contaminated, _ = xbar_r_chart(dataset.subgroups, rules=ALL_RULES)
    first = clean.violations.query("position >= 40").sort_values("position").iloc[0]

    print(
        pd.DataFrame(
            {
                "limits estimated from": ["the first 40 subgroups", "all 60 subgroups"],
                "centre": [clean.center, contaminated.center],
                "half_width": [
                    float(clean.ucl.iloc[0] - clean.center),
                    float(contaminated.ucl.iloc[0] - contaminated.center),
                ],
                "signals_in_the_stable_first_40": [
                    int(clean.out_of_control.iloc[:40].sum()),
                    int(contaminated.out_of_control.iloc[:40].sum()),
                ],
                "signals_total": [
                    int(clean.out_of_control.sum()),
                    int(contaminated.out_of_control.sum()),
                ],
            }
        )
        .round(4)
        .to_string(index=False)
    )
    print(
        f"\n   With a clean baseline the shift is found at subgroup {int(first['label'])},"
        f" at {first['z']:.2f} sigma on rule {int(first['rule'])}."
    )
    print(
        f"   The R chart is quiet ({int(ranges.out_of_control.sum())} signals), so the spread"
        " did not change -"
    )
    print("   only the centre moved, which is what a mean shift looks like.")
    print(
        f"\n   Estimated from all 60 subgroups instead, the same chart produces"
        f" {int(contaminated.out_of_control.iloc[:40].sum())} signals in the"
    )
    print(
        f"   stable first 40, against {int(clean.out_of_control.iloc[:40].sum())}. The shift pulls"
        " the centre it is supposed to be measured"
    )
    print("   against, so the stable period starts failing and the real event stops standing out.")

    capability = capability_from_subgroups(dataset.subgroups, lsl=LSL, usl=USL)
    print(
        f"\n   Capability against {LSL:.0f}-{USL:.0f}: Cp {capability.cp:.3f}, Cpk"
        f" {capability.cpk:.3f}, Pp {capability.pp:.3f}, Ppk {capability.ppk:.3f}."
    )
    print("   Cp reads on the within-subgroup spread and Pp on the whole series, so the gap")
    print("   between them is the shift showing up as if it were incapability.")
    print(
        f"\n   VERDICT: real, locatable and unexplained. Subgroup {int(first['label'])} is where to"
        " start, and the"
    )
    print("   investigation is a capability question with its own window - not a service one.")
    return {
        "shift_at": float(first["label"]),
        "z": float(first["z"]),
        "false_clean": float(clean.out_of_control.iloc[:40].sum()),
        "false_contaminated": float(contaminated.out_of_control.iloc[:40].sum()),
    }


def _check_window(dataset: object, monthly: pd.DataFrame) -> None:
    stamps = dataset.subgroups.groupby("subgroup")["timestamp"].min()
    start, end = pd.Timestamp(stamps.iloc[0]), pd.Timestamp(stamps.iloc[-1])
    span_h = (end - start).total_seconds() / 3600.0

    print(
        f"   Process chart:  {len(stamps)} subgroups from {start:%Y-%m-%d %H:%M} to"
        f" {end:%Y-%m-%d %H:%M}"
    )
    print(f"                   a window of {span_h:.0f} hours - {span_h / 24:.1f} days in June.")
    print(
        f"   Service number: {len(monthly)} monthly points from {monthly.index[0]} to"
        f" {monthly.index[-1]} - a full year."
    )
    print("\n   This is the check nobody runs, and it disposes of the meeting's central instinct.")
    print(
        f"   The two signals on the same slide do not observe the same window: one is"
        f" {span_h / 24:.1f} days"
    )
    print("   in June, the other is twelve months. October is not inside the process")
    print("   chart's window at all. Any story connecting them is not weakly supported - it is")
    print("   unfalsifiable by construction, because no measurement in either series could")
    print("   confirm or refute it.")
    print("\n   VERDICT: not comparable. Two real signals, no relationship available.")


def _decide(dataset: object, october: dict[str, float], shift: dict[str, float]) -> None:
    waiting = waiting_ranked(dataset.order_events).head(4)
    actions = pd.DataFrame(
        [
            {
                "signal": "October OTIF at 78.1%",
                "status": "real, below the noise floor of the definition",
                "action": "none - agree the convention first",
            },
            {
                "signal": "December recovery to 80.0%",
                "status": "artefact of censoring",
                "action": "none - correct the report",
            },
            {
                "signal": "Process out of control",
                "status": f"real, at subgroup {int(shift['shift_at'])}",
                "action": "investigate, as a capability question",
            },
            {
                "signal": "Signals 1 and 3 related",
                "status": "not comparable - windows do not overlap",
                "action": "none - withdraw the hypothesis",
            },
        ]
    )
    print(actions.to_string(index=False))

    print("\n   One investigation, two corrections to the reporting, and no recovery plan. That")
    print("   is the output, and it is worth more than a plan would be. Three of the four items")
    print("   on the slide could not have supported an action: one would have moved a process")
    print("   that is behaving, one would have institutionalised a censoring rule as a practice,")
    print("   and one was a hypothesis no measurement in either series could test.")
    print(
        f"\n   The measurement that makes this defensible is the scale. The service number moves"
        f"\n   {october['convention_range'] * 100:.1f} points on convention against"
        f" {october['annual_range'] * 100:.1f} points on the operation -"
        f" {october['convention_range'] / october['annual_range']:.1f} times. Until that is"
    )
    print("   settled, the monthly series is not a management instrument, and the review is")
    print("   discussing the denominator without knowing it.")

    print("\n   Where to look when there is something to look at:")
    print(waiting.round(4).to_string(index=False))
    print(
        f"\n   {waiting['share_of_waiting'].sum():.0%} of all waiting in the fulfilment log sits"
        " after four handovers."
    )
    print("   That is the standing target, available whether or not a signal fires this month -")
    print("   and unlike everything on the slide, it does not need a signal to justify it.")


if __name__ == "__main__":
    main()
