"""Every figure quoted in the README, asserted against the code that produces it.

A README is documentation until it carries numbers, at which point it is a claim. These tests
make the claims fail loudly rather than drift: any change to the generator, to a definition or
to a chart that moves one of these figures breaks the build and forces the text to be updated
with it.

The tests use the default :class:`SynthConfig`, which is what the README and the example
scripts use. Generating it costs a few seconds, so they are marked ``slow``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.kpi import fill_rate, otif, service_sensitivity
from oplab.spc import capability_from_subgroups, overdispersion_ratio, p_chart, xbar_r_chart
from oplab.synth import Dataset, generate_dataset

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def full() -> Dataset:
    return generate_dataset()


def test_order_book_size(full: Dataset) -> None:
    assert len(full.order_lines) == 290_918


def test_service_spread_table(full: Dataset) -> None:
    """README: 76.0% to 91.6% OTIF, a 15.6-point spread, on one order book."""
    table = service_sensitivity(full.order_lines).set_index("policy")

    expected = {
        "strict": (0.7598, 0.7853, 0.9261, 287_352),
        "standard": (0.7935, 0.8201, 0.9671, 275_163),
        "grace_1day": (0.9152, 0.9460, 0.9671, 275_163),
        "tolerant_5pct": (0.9155, 0.9460, 0.9674, 275_163),
    }
    for policy, (otif_value, on_time, in_full, in_scope) in expected.items():
        row = table.loc[policy]
        assert row["otif"] == pytest.approx(otif_value, abs=5e-4)
        assert row["on_time"] == pytest.approx(on_time, abs=5e-4)
        assert row["in_full"] == pytest.approx(in_full, abs=5e-4)
        assert int(row["lines_in_scope"]) == in_scope

    spread = table["otif"].max() - table["otif"].min()
    assert spread == pytest.approx(0.1557, abs=5e-4)


def test_the_convention_reorders_the_network(full: Dataset) -> None:
    """README: CD-SP is second under the strict convention and first with a day of grace."""
    from oplab.kpi import ServicePolicy

    strict = otif(full.order_lines, ServicePolicy(open_treatment="fail"), by="site")
    generous = otif(full.order_lines, ServicePolicy(grace_minutes=1440), by="site")

    assert strict.rank(ascending=False)["CD-SP"] == 2
    assert generous.rank(ascending=False)["CD-SP"] == 1
    assert strict.rank(ascending=False)["CD-RJ"] == 1
    assert generous.rank(ascending=False)["CD-RJ"] == 2


def test_the_three_fill_rate_bases(full: Dataset) -> None:
    """README: 98.3% per unit, 96.7% per line, 90.0% per order."""
    assert float(fill_rate(full.order_lines, "unit")) == pytest.approx(0.9826, abs=5e-4)
    assert float(fill_rate(full.order_lines, "line")) == pytest.approx(0.9671, abs=5e-4)
    assert float(fill_rate(full.order_lines, "order")) == pytest.approx(0.9003, abs=5e-4)


def test_baseline_table(full: Dataset) -> None:
    """README: centre line moves 499.72 to 500.67 while the half-width changes by 7%."""
    stable, _ = xbar_r_chart(full.subgroups, baseline=slice(0, 40))
    whole, _ = xbar_r_chart(full.subgroups)

    assert stable.center == pytest.approx(499.72, abs=5e-3)
    assert whole.center == pytest.approx(500.67, abs=5e-3)

    stable_width = float(stable.ucl.iloc[0] - stable.center)
    whole_width = float(whole.ucl.iloc[0] - whole.center)
    assert stable_width == pytest.approx(2.930, abs=5e-4)
    assert whole_width == pytest.approx(2.728, abs=5e-4)
    # The centre line moves by nearly five times as much as the half-width does.
    assert abs(whole.center - stable.center) > 4 * abs(whole_width - stable_width)

    assert int(stable.out_of_control.iloc[:40].sum()) == 0
    assert int(whole.out_of_control.iloc[:40].sum()) == 14


def test_capability_gap(full: Dataset) -> None:
    """README and example 2: Cpk 1.20 against Ppk 0.96."""
    result = capability_from_subgroups(full.subgroups, lsl=492.0, usl=508.0)
    assert result.cpk == pytest.approx(1.203, abs=5e-3)
    assert result.ppk == pytest.approx(0.963, abs=5e-3)


def test_overdispersion_table(full: Dataset) -> None:
    """README: 2.12 and 95 of 359 days per line; 1.01 and 4 of 359 per order."""
    lines = full.order_lines
    delivered = lines.loc[(lines["status"] == "delivered") & (lines["site"] == "CD-SP")].copy()
    delivered["late"] = delivered["delivered_ts"] > delivered["promised_ts"]
    delivered["day"] = delivered["delivered_ts"].dt.normalize()

    per_line = (
        delivered.groupby("day").agg(total=("line_id", "size"), late=("late", "sum")).iloc[3:-3]
    )
    line_chart = p_chart(per_line["late"], per_line["total"].astype(float))
    assert len(per_line) == 359
    assert int(per_line["total"].min()) == 80
    assert int(per_line["total"].max()) == 295
    assert int(line_chart.out_of_control.sum()) == 95
    assert overdispersion_ratio(line_chart) == pytest.approx(2.122, abs=5e-3)

    orders = delivered.groupby("order_id").agg(day=("day", "first"), late=("late", "max"))
    per_order = orders.groupby("day").agg(total=("late", "size"), late=("late", "sum")).iloc[3:-3]
    order_chart = p_chart(per_order["late"], per_order["total"].astype(float))
    assert int(per_order["total"].min()) == 25
    assert int(per_order["total"].max()) == 89
    assert int(order_chart.out_of_control.sum()) == 4
    assert overdispersion_ratio(order_chart) == pytest.approx(1.011, abs=5e-3)


def test_carrier_adherence_is_reported_in_full(full: Dataset) -> None:
    """Example 3 claims own fleet at 89.6% and the worst carrier at 16.4%."""
    from oplab.kpi import appointment_adherence

    result = appointment_adherence(full.receipts).set_index("carrier")
    assert result.loc["FROTA-PROPRIA", "on_time"] == pytest.approx(0.8965, abs=5e-4)
    assert result.loc["TRANSP-C", "on_time"] == pytest.approx(0.1637, abs=5e-4)


def test_slotting_table(full: Dataset) -> None:
    """oplab/slotting/README.md: 52.11 m per pick today, and 17.11 to 18.00 after re-slotting."""
    from oplab.slotting import (
        abc_xyz,
        compare_strategies,
        cube_per_order_index,
        demand_profile,
        pick_counts,
        reslot,
        travel_by_class,
    )

    site = "CD-SP"
    demand = full.demand.loc[full.demand["site"].astype(str) == site]
    picks = pick_counts(full.order_lines, site=site)
    classified = abc_xyz(demand_profile(demand, full.catalog, period="W"))
    classified = classified.loc[classified.index.isin(picks.index)]
    cube = full.catalog.set_index("sku")["case_volume_m3"]

    assert int(picks.sum()) == 82_650

    a_class = classified.loc[classified["abc"] == "A"]
    unstable = a_class.loc[a_class["xyz"] != "X"]
    assert len(a_class) == 87
    assert len(unstable) == 18
    assert unstable["annual_value"].sum() / a_class["annual_value"].sum() == pytest.approx(
        0.191, abs=1e-3
    )

    # The diagnosis: class A is not closer to the dock than class C.
    by_class = travel_by_class(picks, full.assignment, full.layout, classified["abc"]).set_index(
        "class"
    )
    assert by_class.loc["A", "mean_distance_per_pick_m"] == pytest.approx(53.15, abs=5e-3)
    assert by_class.loc["C", "mean_distance_per_pick_m"] == pytest.approx(50.74, abs=5e-3)
    assert (
        by_class.loc["A", "mean_distance_per_pick_m"]
        > by_class.loc["C", "mean_distance_per_pick_m"]
    )

    strategies = {
        "current (as received)": full.assignment,
        "by revenue": reslot(-classified["annual_value"], full.layout, cube=cube),
        "by popularity": reslot(-picks, full.layout, cube=cube),
        "by cube-per-order index": reslot(
            cube_per_order_index(picks, cube), full.layout, cube=cube
        ),
    }
    table = compare_strategies(
        picks, full.layout, strategies, baseline="current (as received)"
    ).set_index("strategy")

    expected = {
        "current (as received)": (52.112, 0.0),
        "by popularity": (17.113, -0.672),
        "by revenue": (17.338, -0.667),
        "by cube-per-order index": (18.002, -0.654),
    }
    for strategy, (mean_distance, change) in expected.items():
        row = table.loc[strategy]
        assert row["mean_distance_per_pick_m"] == pytest.approx(mean_distance, abs=5e-3)
        assert row["change_vs_baseline"] == pytest.approx(change, abs=1e-3)

    # The headline: the spread between rules is an order of magnitude below the spread
    # between having a rule and having none.
    rules = table.drop(index="current (as received)")["change_vs_baseline"]
    assert (rules.max() - rules.min()) == pytest.approx(0.017, abs=1e-3)
    assert -rules.max() > 10 * (rules.max() - rules.min())

    # Revenue nearly matches popularity because the two rankings correlate at 0.88.
    correlation = picks.rank().corr(classified["annual_value"].reindex(picks.index).rank())
    assert float(correlation) == pytest.approx(0.88, abs=5e-3)


def test_variance_attribution_table(full: Dataset) -> None:
    """oplab/variance/README.md: the same 15.75 BRL move, attributed two different ways."""
    from oplab.variance import price_volume_mix, unit_value_bridge

    ledger = full.cost_ledger.copy()
    ledger["quantity"] = 1.0
    ledger["half"] = (
        (pd.to_datetime(ledger["order_date"]).dt.month > 6)
        .map({False: "H1", True: "H2"})
        .astype(str)
    )
    base = ledger.loc[ledger["half"] == "H1"]
    current = ledger.loc[ledger["half"] == "H2"]

    total = price_volume_mix(
        base, current, key=["site", "channel", "size_band"], quantity="quantity", value="total_brl"
    )
    assert total.relative_delta == pytest.approx(0.281, abs=1e-3)
    assert total.effects["volume"] / total.delta == pytest.approx(0.22, abs=5e-3)
    assert total.reconciliation_error == pytest.approx(0.0, abs=1e-6)

    with_channel = unit_value_bridge(
        base, current, key=["site", "channel", "size_band"], quantity="quantity", value="total_brl"
    )
    without_channel = unit_value_bridge(
        base, current, key=["site", "size_band"], quantity="quantity", value="total_brl"
    )

    assert with_channel.base_rate == pytest.approx(76.02, abs=5e-3)
    assert with_channel.current_rate == pytest.approx(91.77, abs=5e-3)
    assert with_channel.relative_delta == pytest.approx(0.207, abs=1e-3)

    # The movement is identical; only the attribution differs.
    assert without_channel.delta == pytest.approx(with_channel.delta, abs=1e-9)
    assert with_channel.delta == pytest.approx(15.749, abs=5e-3)

    assert without_channel.effects["rate"] == pytest.approx(15.610, abs=5e-3)
    assert without_channel.effects["mix"] == pytest.approx(0.139, abs=5e-3)
    assert with_channel.effects["rate"] == pytest.approx(11.665, abs=5e-3)
    assert with_channel.effects["mix"] == pytest.approx(4.084, abs=5e-3)

    assert without_channel.effects["rate"] / without_channel.delta == pytest.approx(0.991, abs=1e-3)
    assert with_channel.effects["rate"] / with_channel.delta == pytest.approx(0.741, abs=1e-3)

    # Both reconcile exactly, which is what makes the mis-attribution invisible.
    assert abs(with_channel.reconciliation_error) < 1e-9
    assert abs(without_channel.reconciliation_error) < 1e-9


def test_simulation_capacity_review() -> None:
    """oplab/simulation/README.md: the spreadsheet is right about utilisation and still wrong."""
    from oplab.simulation import SimConfig, run_once

    result = run_once(SimConfig())
    review = result.capacity_review().set_index("resource")

    expected = {
        "inbound_dock": (0.612, 0.616, 153.0),
        "unloading": (0.612, 0.616, 0.0),
        "putaway": (0.467, 0.467, 1.0),
        "picking": (0.783, 0.779, 26_425.0),
        "checking": (0.960, 0.953, 9_622.0),
    }
    for resource, (static, simulated, total_wait) in expected.items():
        row = review.loc[resource]
        assert row["static_utilisation"] == pytest.approx(static, abs=1e-3)
        assert row["utilisation"] == pytest.approx(simulated, abs=1e-3)
        assert row["total_wait_h"] == pytest.approx(total_wait, abs=1.0)

    # The headline: the busier resource is not the one the operation waits on.
    assert review.loc["picking", "utilisation"] < review.loc["checking", "utilisation"]
    assert review.loc["picking", "total_wait_h"] > 2.5 * review.loc["checking", "total_wait_h"]
    assert result.bottleneck()["resource"] == "picking"

    # Detention: docks read as ample and still hold trailers overnight.
    assert review.loc["inbound_dock", "utilisation"] == pytest.approx(0.616, abs=1e-3)
    assert review.loc["inbound_dock", "held_while_closed_h"] == pytest.approx(768.0, abs=1.0)


def test_simulation_scenario_table() -> None:
    """oplab/simulation/README.md: the free change beats every capital option by three times."""
    from oplab.simulation import SimConfig, compare_scenarios

    table = compare_scenarios(
        SimConfig(),
        {
            "+4 pickers": {"pickers": 22},
            "+2 checkers": {"checkers": 7},
            "+2 inbound docks": {"inbound_docks": 6},
            "shift 8h to 10h": {"shift_hours": 10.0},
            "release in 8 waves": {"release_waves": 8},
        },
        metric="order_cycle_mean_h",
        replications=6,
    ).set_index("scenario")

    expected = {
        "release in 8 waves": (0.824, -0.617, True),
        "+2 checkers": (1.678, -0.220, True),
        "shift 8h to 10h": (2.021, -0.061, True),
        "base": (2.152, 0.000, False),
        "+2 inbound docks": (2.152, 0.000, False),
        "+4 pickers": (2.166, 0.007, False),
    }
    for scenario, (mean, change, distinguishable) in expected.items():
        row = table.loc[scenario]
        assert row["mean"] == pytest.approx(mean, abs=5e-3)
        assert row["change_vs_base"] == pytest.approx(change, abs=1e-3)
        assert bool(row["distinguishable"]) is distinguishable

    # The free change recovers nearly three times what the best paid option does.
    waves = -table.loc["release in 8 waves", "change_vs_base"]
    checkers = -table.loc["+2 checkers", "change_vs_base"]
    assert waves / checkers == pytest.approx(2.8, abs=0.1)

    # An inbound investment provably cannot move an outbound metric in this model.
    assert table.loc["+2 inbound docks", "mean"] == pytest.approx(table.loc["base", "mean"])


def test_routing_tables(full: Dataset) -> None:
    """oplab/routing/README.md: the conclusion flips with the search budget, so the model
    refuses to settle make-or-buy."""
    from oplab.routing import (
        TRUCK,
        VAN,
        compare_fleets,
        density_curve,
        fleet_lower_bounds,
        one_day,
        quality_curve,
        window_cost,
    )

    problem = one_day(full.deliveries, "CD-SP", "2025-06-11")
    assert problem.n_stops == 74

    # Only the two valid bounds, and both below the fleet actually needed.
    bounds = fleet_lower_bounds(problem, VAN)
    assert set(bounds.index) == {"by_weight", "by_service_time", "binding"}
    assert bounds["by_weight"] == 3.0
    assert bounds["by_service_time"] == 2.0

    quality = quality_curve(problem, VAN).set_index("solution_limit")
    expected = {20: (8, 53.288), 60: (8, 50.760), 120: (6, 42.170), 300: (5, 38.502)}
    for limit, (vehicles, cost) in expected.items():
        assert quality.loc[limit, "vehicles_used"] == vehicles
        assert quality.loc[limit, "cost_per_delivery"] == pytest.approx(cost, abs=5e-3)
    assert not quality["hit_time_cap"].any(), "a capped run would not be reproducible"

    budget_spread = quality["cost_per_delivery"].max() - quality["cost_per_delivery"].min()
    assert budget_spread == pytest.approx(14.79, abs=5e-2)
    # The fleet size, not only the cost, moves with the budget.
    assert quality.loc[20, "vehicles_used"] - quality.loc[300, "vehicles_used"] == 3

    density = density_curve(problem, VAN, (0.25, 0.5, 1.0)).set_index("stops")
    assert density.loc[18, "cost_per_delivery"] == pytest.approx(53.218, abs=5e-3)
    assert density.loc[37, "cost_per_delivery"] == pytest.approx(48.214, abs=5e-3)
    assert density.loc[74, "cost_per_delivery"] == pytest.approx(38.502, abs=5e-3)
    assert density["cost_per_delivery"].is_monotonic_decreasing
    # Four times the density is 28% lower cost per delivery, in the same territory.
    assert 1 - density.loc[74, "cost_per_delivery"] / density.loc[18, "cost_per_delivery"] == (
        pytest.approx(0.277, abs=5e-3)
    )

    windows = window_cost(problem, VAN).set_index("case")
    assert windows.loc["windows enforced", "cost_per_delivery"] == pytest.approx(38.502, abs=5e-3)
    assert windows.loc["windows opened", "cost_per_delivery"] == pytest.approx(37.683, abs=5e-3)
    assert windows.loc["windows enforced", "premium_vs_open"] == pytest.approx(0.022, abs=1e-3)
    # Under a proper budget the windows cost no extra vehicle. An under-searched solve
    # reported 8.8% and one extra van, because the heuristic struggles more with the
    # constrained problem than with the open one - so a cheap solve exaggerates the cost of
    # every constraint.
    assert windows.loc["windows enforced", "vehicles_used"] == 5
    assert windows.loc["windows opened", "vehicles_used"] == 5

    fleets = compare_fleets(
        problem, {"van": VAN, "truck": TRUCK}, third_party_price_per_delivery=42.0
    ).set_index("option")
    assert fleets.loc["van", "cost_per_delivery"] == pytest.approx(38.502, abs=5e-3)
    assert fleets.loc["truck", "cost_per_delivery"] == pytest.approx(64.213, abs=5e-3)

    # The refusal: the conclusion itself flips with the search budget. A cheap solve says buy,
    # a thorough one says make, and the gap is a quarter of the budget spread.
    assert quality.loc[20, "cost_per_delivery"] > 42.0, "a cheap solve favours the carrier"
    assert quality.loc[300, "cost_per_delivery"] < 42.0, "a thorough one favours the fleet"
    make_or_buy_gap = 42.0 - float(fleets.loc["van", "cost_per_delivery"])
    assert make_or_buy_gap == pytest.approx(3.50, abs=5e-2)
    assert make_or_buy_gap < budget_spread / 3.0

    # What the model does settle, by a margin no assumption threatens.
    assert fleets.loc["truck", "cost_per_delivery"] / fleets.loc["van", "cost_per_delivery"] == (
        pytest.approx(1.67, abs=1e-2)
    )


def test_examples_run_without_error() -> None:
    """The three example scripts are part of the deliverable; a broken one is a broken README."""
    import runpy
    import sys
    from io import StringIO
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scripts = sorted((root / "examples").glob("*.py"))
    assert len(scripts) == 7

    for script in scripts:
        captured, sys.stdout = sys.stdout, StringIO()
        try:
            runpy.run_path(str(script), run_name="__main__")
        finally:
            output = sys.stdout.getvalue()
            sys.stdout = captured
        assert output.strip(), f"{script.name} printed nothing"
