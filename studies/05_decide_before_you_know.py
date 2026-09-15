"""A supplier failed over the weekend. The expedite window closes at noon. What do you measure?

Run:
    python studies/05_decide_before_you_know.py

The four studies before this one all assume the analysis can be finished before the decision is
taken. That assumption is what makes them studies rather than Mondays. This one has a clock: five
hours, four analyses on the table, and no possibility of doing all of them.

The reasoning is **decision boundary first, measurement second**. For each question someone wants
answered, the question to ask is not "what is the answer?" but "what would the answer have to be
to change what I do?" A question whose plausible range does not cross that boundary cannot earn
the clock, however interesting it is.

Applied here, the triage inverts the agenda. The decision being argued about - which SKUs to
air-freight - is worth BRL 202. The number that decides the outcome moves by 27x and is not in
this repository's data at all: it is how long the supplier is actually down, and the highest-value
analysis available at 07:00 on Monday is a phone call.

Two of this study's own predictions were wrong, and both are recorded below where they failed,
because a method for deciding under time pressure that only reports its successes is not a method.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from oplab.forecast import BASELINES, backtest_panel, error_profile, to_panel
from oplab.inventory import (
    fit_demand,
    fit_lead_time,
    safety_stock,
    z_for_cycle_service,
)
from oplab.inventory.normal import unit_normal_loss
from oplab.synth import generate_dataset

SUPPLIER = "FORN-IMPORT"
SERVICE = 0.95
DELAY_DAYS = 21.0
AIR_BRL_PER_KG = 25.0
MARGIN_ON_COST = 0.40
CUSTOMS_PER_LINE = 1200.0
DOWN_DAYS = (7, 14, 21, 30, 45, 60, 90)


def main() -> None:
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    dataset = generate_dataset()
    items, lead = _affected(dataset)

    print("THE SITUATION")
    print("   Monday, 07:00. Over the weekend the freight forwarder confirmed that the inbound")
    print(f"   from {SUPPLIER} did not sail. {len(items)} SKUs are affected. The airline's")
    print("   cut-off for a Wednesday arrival is noon today, so the expedite decision expires in")
    print("   five hours.")
    print("\n   Four analyses are on the table and there is time for one, maybe two:")
    print("     1. Re-forecast demand for the affected range            (half a day)")
    print("     2. Optimise which SKUs to air-freight                   (half a day)")
    print("     3. Measure the realised lead time instead of the quoted (two hours)")
    print("     4. Simulate whether the DC can receive an air shipment  (one day)")
    print("\n   The question is not which is most interesting. It is which one could change what")
    print("   we do by noon.")

    print("\n" + "=" * 96)
    print("CHECK 1 - WHAT IS ACTUALLY ON THE TABLE")
    print("=" * 96)
    action = _check_action_space(items, lead)

    print("\n" + "=" * 96)
    print("CHECK 2 - WHAT MOVES THE NUMBER NOBODY IS ARGUING ABOUT")
    print("=" * 96)
    sensitivity = _check_sensitivity(items, lead)

    print("\n" + "=" * 96)
    print("CHECK 3 - TRIAGE: VALUE PER MINUTE OF A CLOCK THAT RUNS OUT AT NOON")
    print("=" * 96)
    band = _check_triage(dataset, items, lead, sensitivity)

    print("\n" + "=" * 96)
    print("CHECK 4 - WHAT YOU DECIDE WITHOUT KNOWING, AND WHAT REVERSES IT")
    print("=" * 96)
    trigger = _check_trigger(items, lead, action)

    print("\n" + "=" * 96)
    print("WHAT TO DO BY NOON")
    print("=" * 96)
    _decide(action, trigger, band)


def _affected(dataset: object) -> tuple[pd.DataFrame, object]:
    """The affected range, its current position, and the supplier's realised lead time."""
    orders = dataset.purchase_orders
    group = orders.loc[orders["supplier"] == SUPPLIER]
    lead = fit_lead_time(
        group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
    )
    catalog = dataset.catalog.set_index("sku")
    panel = to_panel(dataset.demand, freq="D", key=("sku",))
    z = z_for_cycle_service(SERVICE)

    rows = []
    for sku in sorted(group["sku"].unique()):
        if sku not in panel.columns:
            continue
        profile = fit_demand(panel[sku].to_numpy())
        if profile.mean <= 0.0:
            continue
        sized = safety_stock(profile, lead, z)
        rows.append(
            {
                "sku": sku,
                "unit_cost": float(catalog.loc[sku, "unit_cost"]),
                "weight_kg": float(catalog.loc[sku, "unit_weight_kg"]),
                "demand_mean": profile.mean,
                "demand_sd": profile.sd,
                # The position the standing policy leaves us in, not a position invented for the
                # emergency: the reorder point it was already sized to hold.
                "reorder_point": profile.mean * lead.quoted + sized.units,
            }
        )
    return pd.DataFrame(rows).set_index("sku"), lead


def _shortfall(
    items: pd.DataFrame,
    lead: object,
    delay: float,
    demand_scale: float = 1.0,
    lead_base: float | None = None,
    lead_sd: float | None = None,
) -> pd.Series:
    """Expected units short per SKU once the failed shipment pushes arrival out by ``delay``."""
    base = lead.quoted if lead_base is None else lead_base
    sd_lead = lead.sd if lead_sd is None else lead_sd
    horizon = base + delay
    mean = items["demand_mean"] * demand_scale
    spread = items["demand_sd"] * demand_scale
    demand_over_lead = mean * horizon
    sigma = np.sqrt(horizon * spread**2 + mean**2 * sd_lead**2)
    z = (items["reorder_point"] - demand_over_lead) / sigma
    return sigma * z.map(unit_normal_loss)


def _exposure(items: pd.DataFrame, lead: object, **kwargs: float) -> float:
    """Lost margin across the affected range, which is what the failure costs if nothing is done."""
    margin = kwargs.pop("margin", MARGIN_ON_COST)
    return float((margin * items["unit_cost"] * _shortfall(items, lead, **kwargs)).sum())


def _check_action_space(items: pd.DataFrame, lead: object) -> dict[str, float]:
    """The expedite boundary, derived before anything is measured."""
    print("   Air freight is charged by weight and the shortfall it avoids is worth a margin on")
    print("   cost, so expediting one SKU pays when")
    print("\n       (margin x unit_cost - air_rate x weight) x expected_shortfall  >  customs")
    print("\n   Two things follow from the algebra alone, before a single number is measured.")
    print("   **The bracket has to be positive or no volume can rescue the line** - that is a")
    print("   pure value-density test, and demand does not appear in it. Only once a SKU clears")
    print("   density does its volume decide whether it also clears the fixed cost.")

    shortfall = _shortfall(items, lead, DELAY_DAYS)
    gain = MARGIN_ON_COST * items["unit_cost"] - AIR_BRL_PER_KG * items["weight_kg"]
    density = items["unit_cost"] / items["weight_kg"]
    net = gain * shortfall - CUSTOMS_PER_LINE

    clears_density = gain > 0
    table = pd.DataFrame(
        {
            "density_brl_per_kg": density,
            "gain_per_unit": gain,
            "expected_short": shortfall,
            "volume_needed": np.where(gain > 0, CUSTOMS_PER_LINE / gain.where(gain > 0), np.inf),
            "net_brl": net,
        }
    ).loc[clears_density]

    print(
        f"\n   Density threshold is air_rate / margin ="
        f" {AIR_BRL_PER_KG / MARGIN_ON_COST:.1f} BRL/kg."
        f" Value density across the affected range spans"
    )
    print(
        f"   {density.min():.2f} to {density.max():.2f} BRL/kg - a factor of"
        f" {density.max() / density.min():.0f} - and"
        f" **{int(clears_density.sum())} of {len(items)} SKUs clear it**."
    )
    print("\n   Of those, the volume test:")
    print(table.sort_values("net_brl", ascending=False).round(2).to_string())

    worth = table.loc[table["net_brl"] > 0]
    exposure = _exposure(items, lead, delay=DELAY_DAYS)
    blanket = float((CUSTOMS_PER_LINE + AIR_BRL_PER_KG * items["weight_kg"] * shortfall).sum())

    print(
        f"\n   So the entire action space is {len(worth)} SKU, worth **BRL"
        f" {float(worth['net_brl'].sum()):.0f}**."
    )
    print(
        f"   Expediting the whole affected range instead costs BRL {blanket:,.0f}, of which BRL"
        f" {CUSTOMS_PER_LINE * len(items):,.0f} is"
    )
    print("   customs clearance before a single kilo flies - the fixed cost per line, not the")
    print("   freight, is what makes blanket action unaffordable.")
    print(
        f"\n   Against that, doing nothing costs **BRL {exposure:,.0f}** of lost margin. The"
        " decision that has"
    )
    print(
        f"   consumed the weekend can recover {float(worth['net_brl'].sum()) / exposure:.2%} of"
        " the number it is a response to."
    )
    return {
        "expedite": float(len(worth)),
        "net": float(worth["net_brl"].sum()),
        "exposure": exposure,
        "blanket": blanket,
        "clears_density": float(clears_density.sum()),
        "density_span": float(density.max() / density.min()),
    }


def _check_sensitivity(items: pd.DataFrame, lead: object) -> pd.DataFrame:
    """One factor at a time against the exposure, which is the number that actually matters."""
    base = _exposure(items, lead, delay=DELAY_DAYS)
    cases = [
        (
            "how long the supplier is down (7 vs 45 days)",
            _exposure(items, lead, delay=7.0),
            _exposure(items, lead, delay=45.0),
            "a phone call",
        ),
        (
            "the demand estimate (-20% vs +20%)",
            _exposure(items, lead, delay=DELAY_DAYS, demand_scale=0.8),
            _exposure(items, lead, delay=DELAY_DAYS, demand_scale=1.2),
            "half a day",
        ),
        (
            "gross margin (25% vs 60%)",
            _exposure(items, lead, delay=DELAY_DAYS, margin=0.25),
            _exposure(items, lead, delay=DELAY_DAYS, margin=0.60),
            "ask finance",
        ),
        (
            "lead time, quoted vs realised",
            _exposure(items, lead, delay=DELAY_DAYS, lead_base=lead.quoted),
            _exposure(items, lead, delay=DELAY_DAYS, lead_base=float(lead.mean)),
            "two hours",
        ),
        (
            "lead-time variability (none vs realised)",
            _exposure(items, lead, delay=DELAY_DAYS, lead_sd=0.0),
            _exposure(items, lead, delay=DELAY_DAYS, lead_sd=float(lead.sd)),
            "two hours",
        ),
        ("the air freight rate (12 vs 45 BRL/kg)", base, base, "already known"),
        ("customs per line (300 vs 1200)", base, base, "already known"),
    ]
    table = pd.DataFrame(
        [
            {
                "factor": name,
                "exposure_low": low,
                "exposure_high": high,
                "swing": max(low, high) / min(low, high),
                "cost_to_resolve": cost,
            }
            for name, low, high, cost in cases
        ]
    ).sort_values("swing", ascending=False)

    print(f"   Exposure at the base case is BRL {base:,.0f}. Moving one factor at a time:")
    print(table.round(2).to_string(index=False))

    print("\n   **The two factors that decide the outcome are not in the argument.** How long the")
    print("   supplier is down moves the exposure by a factor of 27; the demand estimate by 8.")
    print("   The air rate and the customs fee - the two numbers the expedite optimisation is")
    print("   built on - move it by exactly nothing, because they price the response, not the")
    print("   loss.")
    print("\n   That last row is the whole point of separating the boundary from the measurement.")
    print("   An optimisation over parameters that cannot move the objective is not a small")
    print("   contribution to the decision; it is zero, and it costs half of the clock.")
    return table


def _check_triage(
    dataset: object, items: pd.DataFrame, lead: object, sensitivity: pd.DataFrame
) -> float:
    """Two of this study's own predictions, and how the measurement settled them."""
    print("   Ranking the four analyses by what they could move per minute spent. The swings are")
    print("   read off the table above rather than retyped, so a shift in the data cannot leave")
    print("   this ranking asserting a multiple the measurement no longer supports:")
    swing = dict(zip(sensitivity["factor"], sensitivity["swing"], strict=True))
    outage = swing["how long the supplier is down (7 vs 45 days)"]
    demand = swing["the demand estimate (-20% vs +20%)"]
    quoted = swing["lead time, quoted vs realised"]
    priced = swing["the air freight rate (12 vs 45 BRL/kg)"]
    print(
        pd.DataFrame(
            [
                {
                    "analysis": "phone the supplier for a return date",
                    "clock": "5 min",
                    "moves exposure": f"{outage:.2f}x",
                    "verdict": "do it first",
                },
                {
                    "analysis": "bound the demand estimate",
                    "clock": "1 h",
                    "moves exposure": f"{demand:.2f}x",
                    "verdict": "do it second",
                },
                {
                    "analysis": "optimise the expedite list",
                    "clock": "half a day",
                    "moves exposure": f"{priced:.2f}x",
                    "verdict": "already done, above, in one table",
                },
                {
                    "analysis": "realised vs quoted lead time",
                    "clock": "2 h",
                    "moves exposure": f"{quoted:.2f}x",
                    "verdict": "a policy question, not a Monday one",
                },
                {
                    "analysis": "simulate DC receiving capacity",
                    "clock": "1 day",
                    "moves exposure": "not on this axis",
                    "verdict": "arithmetic answers it",
                },
            ]
        ).to_string(index=False)
    )

    print("\n   **Two predictions this study got wrong.**")
    print("\n   First, I expected the demand forecast to be decision-irrelevant, and had an")
    print("   argument for it: demand cancels out of the density test, so it cannot change which")
    print("   SKUs are eligible. That argument is correct and the conclusion drawn from it was")
    print(
        f"   not. Demand cancels from the *selection* and dominates the *exposure* - an"
        f" {demand:.2f}x swing,"
    )
    print("   second only to the supplier's return date. Selection was the question I had solved,")
    print("   so it was the question I let stand in for the decision.")

    print("\n   Second, I expected the realised lead time to be the cheap decisive measurement:")
    print(
        f"   {SUPPLIER} quotes {lead.quoted:.0f} days, realises {lead.mean:.2f}, with skew"
        f" {lead.skew:.2f} and a p95 of"
    )
    print(
        f"   {lead.quantile(0.95):.2f} - a tail the quote hides, and exactly the sort of thing"
        " this repository"
    )
    print(
        f"   was built to find. It moves the exposure by {quoted:.2f}x. The tail is real and it is"
    )
    print("   simply not what is at stake once a shipment has already failed: the 21 days of")
    print("   delay swamp the 1.7 days of optimism in the quote.")

    print("\n   The demand bound is worth one hour rather than half a day, and this repository's")
    print("   own backtest is why:")
    whole = to_panel(dataset.demand, freq="D", key=("sku",))
    panel = whole.loc[:, [s for s in items.index if s in whole.columns]]
    regular = panel.loc[:, (panel == 0).mean() <= 0.3]
    results = backtest_panel(
        regular,
        {"seasonal_naive": BASELINES["seasonal_naive"]},
        horizon=7,
        step=28,
        min_train=120,
        season=7,
    )
    profile = error_profile(results, "seasonal_naive")
    relative = float(
        (profile["mae"] / items.loc[profile["series"], "demand_mean"].to_numpy()).median()
    )
    print(
        f"   Across {regular.shape[1]} of the affected series the median absolute error is"
        f" {relative:.1%} of mean daily"
    )
    print(
        f"   demand, and the median ratio of error spread to demand spread is"
        f" {float(profile['sd_ratio'].median()):.4f}."
    )
    print("   So the plus-or-minus 20% swept above is not a pessimistic band, it is an optimistic")
    print("   one, and the 8x is a floor rather than an estimate. Half a day of modelling would")
    print("   narrow a band this wide by very little - but stating the band at all, which takes")
    print("   an hour, changes whether the exposure is reported as a number or as a range. Those")
    print("   are different conversations with the same commercial director.")
    return relative


def _check_trigger(items: pd.DataFrame, lead: object, action: dict[str, float]) -> dict[str, float]:
    """The decision is taken without the dominant input, so it ships with its own reversal rule."""
    rows = [
        {
            "supplier down (days)": days,
            "exposure_brl": _exposure(items, lead, delay=float(days)),
            "blanket_cost_brl": action["blanket"],
            "blanket_justified": _exposure(items, lead, delay=float(days)) > action["blanket"],
        }
        for days in DOWN_DAYS
    ]
    table = pd.DataFrame(rows)
    print(table.round(0).to_string(index=False))

    # Solved rather than asserted: the smallest whole day at which doing everything beats
    # accepting the loss. An earlier draft wrote 95 from reading the table, which is the habit
    # this repository exists to break.
    crossing = next(
        (
            float(day)
            for day in range(1, 366)
            if _exposure(items, lead, delay=float(day)) > action["blanket"]
        ),
        float("nan"),
    )
    print(
        f"\n   The exposure only overtakes blanket action at {crossing:.0f} days down, which is"
        " outside any"
    )
    print("   scenario the forwarder has put on the table. **That is what makes the decision")
    print("   safe to take without the number that dominates it**: across the entire plausible")
    print("   range of the unknown, the action does not change. Selective expedite is the whole")
    print("   action space whether the supplier is out for one week or for two months.")
    print("\n   Which is the useful form of an answer under time pressure. Not an estimate of the")
    print("   unknown, but a demonstration that the unknown does not reach the boundary - and,")
    print("   where it would, the value it would have to reach, written down in advance so that")
    print("   the reversal is a rule rather than a second argument.")
    print(
        "\n   So the trigger is dated, not conditional on judgement: if the confirmed return"
        " date puts the"
    )
    print(
        f"   outage past {crossing:.0f} days, blanket expedite is back on the table and this"
        " analysis is void. Below"
    )
    print("   that, no new information about the outage changes what we do today.")
    return {"crossing_days": crossing, "exposure_at_90": _exposure(items, lead, delay=90.0)}


def _decide(action: dict[str, float], trigger: dict[str, float], band: float) -> None:
    print(
        pd.DataFrame(
            [
                {
                    "by": "07:15",
                    "action": "phone the forwarder for a confirmed return date",
                    "because": "27x swing, five minutes, not in our data",
                },
                {
                    "by": "08:30",
                    "action": "state the exposure as a range, not a number",
                    "because": f"the demand band is +/-{band:.0%}, not +/-20%",
                },
                {
                    "by": "11:00",
                    "action": f"expedite {action['expedite']:.0f} SKU and accept the rest",
                    "because": f"the whole action space is BRL {action['net']:.0f}",
                },
                {
                    "by": "11:30",
                    "action": f"log the reversal trigger at {trigger['crossing_days']:.0f} days",
                    "because": "makes the reversal a rule, not a second argument",
                },
                {
                    "by": "noon",
                    "action": "cancel the other three analyses",
                    "because": "none can move the objective before the window shuts",
                },
            ]
        ).to_string(index=False)
    )

    print("\n   The uncomfortable part is the arithmetic on the analyst's time. The expedite")
    print(
        f"   optimisation everyone wanted decides BRL {action['net']:.0f} and costs half a day."
        " At any"
    )
    print("   defensible loaded rate for the person who would run it, the analysis costs more")
    print("   than the decision it improves. It is not that the work is wrong; it is that the")
    print("   stake caps what the work can be worth, and nobody checked the cap before")
    print("   assigning the work.")

    print("\n   **The value of information is bounded by the value of the decision it informs.**")
    print("   That bound is computable before the analysis, from the action space alone, and it")
    print("   is the one calculation a Monday morning never includes. The four studies before")
    print("   this one all had time to measure first and decide after. The order is reversed")
    print("   here, and reversing it is what exposes an agenda in which the two dominant factors")
    print("   were nobody's action item.")

    print("\n   What this study cannot show. The dominant input is a phone call, and no module in")
    print("   this repository produces it - which is the honest limitation of a toolkit rather")
    print("   than a gap to be filled by a better model. A repository of analytical tools whose")
    print("   fifth study concludes that the highest-value act available is a conversation is")
    print("   reporting a real property of operational decisions under a clock, not a failure of")
    print("   its own coverage.")

    print("\n   What would change this. The exposure is dominated by the outage length because")
    print("   the standing policy was sized for a 30-day quoted lead time with no allowance for")
    print("   a missed sailing. An operation holding a sourcing alternative for this range would")
    print("   see the 27x collapse, and then the expedite list - genuinely - would be the")
    print("   decision. That is a question about the supply base, answerable in a quarter, and")
    print("   it is the one worth taking away from a Monday that was never going to be won.")


if __name__ == "__main__":
    main()
