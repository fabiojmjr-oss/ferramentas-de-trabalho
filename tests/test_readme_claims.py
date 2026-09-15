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
    """oplab/variance/README.md: the same 11.77 BRL move, attributed two different ways."""
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
    assert total.relative_delta == pytest.approx(0.2066, abs=1e-3)
    assert total.effects["volume"] / total.delta == pytest.approx(0.297, abs=5e-3)
    assert total.reconciliation_error == pytest.approx(0.0, abs=1e-6)

    with_channel = unit_value_bridge(
        base, current, key=["site", "channel", "size_band"], quantity="quantity", value="total_brl"
    )
    without_channel = unit_value_bridge(
        base, current, key=["site", "size_band"], quantity="quantity", value="total_brl"
    )

    assert with_channel.base_rate == pytest.approx(86.007, abs=5e-3)
    assert with_channel.current_rate == pytest.approx(97.772, abs=5e-3)
    assert with_channel.relative_delta == pytest.approx(0.1368, abs=1e-3)

    # The movement is identical; only the attribution differs.
    assert without_channel.delta == pytest.approx(with_channel.delta, abs=1e-9)
    assert with_channel.delta == pytest.approx(11.765, abs=5e-3)

    assert without_channel.effects["rate"] == pytest.approx(11.551, abs=5e-3)
    assert without_channel.effects["mix"] == pytest.approx(0.214, abs=5e-3)
    assert with_channel.effects["rate"] == pytest.approx(9.198, abs=5e-3)
    assert with_channel.effects["mix"] == pytest.approx(2.567, abs=5e-3)

    assert without_channel.effects["rate"] / without_channel.delta == pytest.approx(0.982, abs=1e-3)
    assert with_channel.effects["rate"] / with_channel.delta == pytest.approx(0.782, abs=1e-3)

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
    expected = {20: (7, 44.082), 60: (7, 42.126), 120: (5, 36.878), 300: (5, 36.113)}
    for limit, (vehicles, cost) in expected.items():
        assert quality.loc[limit, "vehicles_used"] == vehicles
        assert quality.loc[limit, "cost_per_delivery"] == pytest.approx(cost, abs=5e-3)
    assert not quality["hit_time_cap"].any(), "a capped run would not be reproducible"

    budget_spread = quality["cost_per_delivery"].max() - quality["cost_per_delivery"].min()
    assert budget_spread == pytest.approx(7.97, abs=5e-2)
    # The fleet size, not only the cost, moves with the budget.
    assert quality.loc[20, "vehicles_used"] - quality.loc[300, "vehicles_used"] == 2

    density = density_curve(problem, VAN, (0.25, 0.5, 1.0), replications=8).set_index("stops")
    assert density.loc[18, "cost_per_delivery"] == pytest.approx(49.684, abs=5e-3)
    assert density.loc[37, "cost_per_delivery"] == pytest.approx(43.282, abs=5e-3)
    assert density.loc[74, "cost_per_delivery"] == pytest.approx(36.113, abs=5e-3)
    assert density["cost_per_delivery"].is_monotonic_decreasing
    # Four times the density is 27% lower cost per delivery, in the same territory.
    assert 1 - density.loc[74, "cost_per_delivery"] / density.loc[18, "cost_per_delivery"] == (
        pytest.approx(0.273, abs=5e-3)
    )
    # The endpoints separate, so the direction is established. The intermediate step does not,
    # so its level is not - which is why the curve is replicated and reported with intervals.
    assert density.loc[18, "cost_ci_low"] > density.loc[74, "cost_ci_high"]
    assert density.loc[18, "cost_ci_low"] < density.loc[37, "cost_ci_high"]

    windows = window_cost(problem, VAN).set_index("case")
    assert windows.loc["windows enforced", "cost_per_delivery"] == pytest.approx(36.113, abs=5e-3)
    assert windows.loc["windows opened", "cost_per_delivery"] == pytest.approx(34.795, abs=5e-3)
    assert windows.loc["windows enforced", "premium_vs_open"] == pytest.approx(0.038, abs=1e-3)
    # Under a proper budget the windows cost no extra vehicle. An under-searched solve
    # reported one, because the heuristic struggles more with the constrained problem than
    # with the open one - so a cheap solve exaggerates the cost of every constraint.
    assert windows.loc["windows enforced", "vehicles_used"] == 5
    assert windows.loc["windows opened", "vehicles_used"] == 5

    fleets = compare_fleets(
        problem, {"van": VAN, "truck": TRUCK}, third_party_price_per_delivery=42.0
    ).set_index("option")
    assert fleets.loc["van", "cost_per_delivery"] == pytest.approx(36.113, abs=5e-3)
    assert fleets.loc["truck", "cost_per_delivery"] == pytest.approx(60.717, abs=5e-3)

    # The refusal: the conclusion itself flips with the search budget. A cheap solve says buy,
    # a thorough one says make, and the gap is smaller than the budget spread.
    assert quality.loc[20, "cost_per_delivery"] > 42.0, "a cheap solve favours the carrier"
    assert quality.loc[300, "cost_per_delivery"] < 42.0, "a thorough one favours the fleet"
    make_or_buy_gap = 42.0 - float(fleets.loc["van", "cost_per_delivery"])
    assert make_or_buy_gap == pytest.approx(5.89, abs=5e-2)
    assert make_or_buy_gap < budget_spread

    # What the model does settle, by a margin no assumption threatens.
    assert fleets.loc["truck", "cost_per_delivery"] / fleets.loc["van", "cost_per_delivery"] == (
        pytest.approx(1.68, abs=1e-2)
    )


def test_benchmark_tables(full: Dataset) -> None:
    """oplab/benchmark/README.md: a third of the cost gap is postcodes, and the same method
    gives opposite verdicts on two comparisons."""
    from oplab.benchmark import (
        dea,
        discrimination_check,
        indirect_standardisation,
        peer_z_scores,
        rank_stability,
    )
    from oplab.kpi import line_service

    ledger = full.cost_ledger.copy()
    ledger["band"] = pd.cut(
        ledger["distance_km"],
        [0.0, 10.0, 25.0, 50.0, float("inf")],
        labels=["0-10 km", "10-25 km", "25-50 km", "50+ km"],
    ).astype(str)

    # The territories genuinely differ, which is what makes the adjustment necessary.
    mix = ledger.groupby(["site", "band"], observed=True).size().unstack(fill_value=0)
    shares = mix.div(mix.sum(axis=1), axis=0)
    assert shares.loc["CD-SP", "0-10 km"] == pytest.approx(0.364, abs=5e-3)
    assert shares.loc["CD-PE", "0-10 km"] == pytest.approx(0.098, abs=5e-3)

    aggregated = (
        ledger.groupby(["site", "band"], observed=True)
        .agg(cost=("total_brl", "sum"), deliveries=("order_id", "size"))
        .reset_index()
    )
    standardised = indirect_standardisation(
        aggregated, "site", "band", "cost", "deliveries", exclude_self=True
    ).set_index("site")

    expected = {
        "CD-PE": (119.00, 110.32, 1.20),
        "CD-RS": (97.86, 93.13, 1.01),
        "CD-RJ": (83.34, 85.48, 0.93),
        "CD-SP": (75.28, 81.85, 0.89),
    }
    for site, (crude, adjusted, ratio) in expected.items():
        row = standardised.loc[site]
        assert row["crude_rate"] == pytest.approx(crude, abs=5e-2)
        assert row["standardised_rate"] == pytest.approx(adjusted, abs=5e-2)
        assert row["standardised_ratio"] == pytest.approx(ratio, abs=5e-3)

    crude_spread = standardised["crude_rate"].max() - standardised["crude_rate"].min()
    adjusted_spread = (
        standardised["standardised_rate"].max() - standardised["standardised_rate"].min()
    )
    assert crude_spread == pytest.approx(43.72, abs=5e-2)
    assert adjusted_spread == pytest.approx(28.47, abs=5e-2)
    assert 1 - adjusted_spread / crude_spread == pytest.approx(0.35, abs=5e-3)

    # 58% more expensive crude, 35% once the distance profile is held constant.
    crude_gap = standardised.loc["CD-PE", "crude_rate"] / standardised.loc["CD-SP", "crude_rate"]
    adjusted_gap = (
        standardised.loc["CD-PE", "standardised_rate"]
        / standardised.loc["CD-SP", "standardised_rate"]
    )
    assert crude_gap - 1 == pytest.approx(0.58, abs=5e-3)
    assert adjusted_gap - 1 == pytest.approx(0.35, abs=5e-3)

    # Between sites the ranking is a fact; between months at one site it is a weighting.
    lines = line_service(full.order_lines)
    scoped = lines.loc[lines["in_scope"]]
    from oplab.kpi import dock_to_stock, inventory_record_accuracy

    scorecard = pd.concat(
        [
            scoped.groupby("site", observed=True)["otif"].mean().rename("otif"),
            ledger.groupby("site", observed=True)["total_brl"].mean().rename("cost_per_order"),
            dock_to_stock(full.receipts)
            .query("stage == 'dock_to_stock_h'")
            .set_index("site")["p95"]
            .rename("dock_to_stock_p95_h"),
            inventory_record_accuracy(full.cycle_counts)
            .set_index("site")["location_accuracy"]
            .rename("inventory_accuracy"),
        ],
        axis=1,
    ).reset_index(names="site")
    metrics = ["otif", "cost_per_order", "dock_to_stock_p95_h", "inventory_accuracy"]
    direction = {
        "otif": True,
        "cost_per_order": False,
        "dock_to_stock_p95_h": False,
        "inventory_accuracy": True,
    }
    site_scores = peer_z_scores(scorecard, metrics, direction, unit="site")
    site_stability = rank_stability(site_scores, metrics, unit="site").set_index("site")
    assert site_stability.loc["CD-SP", "share_first"] == pytest.approx(0.973, abs=5e-3)
    assert site_stability.loc["CD-PE", "best_rank"] == site_stability.loc["CD-PE", "worst_rank"]
    assert site_stability.loc["CD-RS", "best_rank"] == site_stability.loc["CD-RS", "worst_rank"]
    movable_sites = int((site_stability["best_rank"] != site_stability["worst_rank"]).sum())
    assert movable_sites == 2

    # Month on month at one site the same method gives the opposite verdict.
    monthly = scoped.loc[scoped["site"].astype(str) == "CD-SP"].copy()
    monthly["month"] = monthly["order_ts"].dt.to_period("M").astype(str)
    site_ledger = ledger.loc[ledger["site"].astype(str) == "CD-SP"]
    month_frame = pd.concat(
        [
            monthly.groupby("month", observed=True)["otif"].mean().rename("otif"),
            site_ledger.groupby("month", observed=True)["total_brl"]
            .mean()
            .rename("cost_per_order"),
            site_ledger.groupby("month", observed=True)
            .apply(lambda g: g["handling_brl"].sum() / g["lines"].sum(), include_groups=False)
            .rename("handling_per_line"),
        ],
        axis=1,
    ).reset_index(names="month")
    month_metrics = ["otif", "cost_per_order", "handling_per_line"]
    month_direction = {"otif": True, "cost_per_order": False, "handling_per_line": False}
    month_stability = rank_stability(
        peer_z_scores(month_frame, month_metrics, month_direction, unit="month"),
        month_metrics,
        unit="month",
    )
    movable_months = int((month_stability["best_rank"] != month_stability["worst_rank"]).sum())
    assert movable_months == 12, "every month's rank is decided by the weighting"
    assert int((month_stability["worst_rank"] - month_stability["best_rank"]).max()) == 10

    # DEA on four sites cannot discriminate, and the modelling choice moves the worst site by
    # more than any real difference between units.
    inputs, outputs = ["freight_brl", "handling_brl"], ["otif_lines", "units"]
    cost = ledger.groupby("site", observed=True).agg(
        freight_brl=("freight_brl", "sum"), handling_brl=("handling_brl", "sum")
    )
    service = scoped.groupby("site", observed=True).agg(
        otif_lines=("otif", "sum"), units=("qty_delivered", "sum")
    )
    sites = cost.join(service).reset_index()
    sites["otif_lines"] = sites["otif_lines"].astype(float)

    assert not discrimination_check(len(sites), 2, 2).adequate
    crs = dea(sites, inputs, outputs).set_index("site")
    vrs = dea(sites, inputs, outputs, returns_to_scale="vrs").set_index("site")
    assert crs["on_frontier"].mean() == pytest.approx(0.50)
    assert vrs["on_frontier"].mean() == pytest.approx(0.75)
    assert crs.loc["CD-PE", "efficiency"] == pytest.approx(0.626, abs=5e-3)
    assert vrs.loc["CD-PE", "efficiency"] == pytest.approx(0.895, abs=5e-3)
    assert vrs.loc["CD-PE", "efficiency"] - crs.loc["CD-PE", "efficiency"] == pytest.approx(
        0.27, abs=5e-3
    )


def test_forecast_tables(full: Dataset) -> None:
    """oplab/forecast/README.md: the metric cannot be computed, the headroom is under a percent,
    the leader changes between segments, and bias survives aggregation intact."""
    from oplab.forecast import (
        BASELINES,
        INTERMITTENT,
        aggregate_panel,
        backtest_panel,
        mape_coverage,
        season_feasibility,
        summarise,
        to_panel,
    )

    site_demand = full.demand.loc[full.demand["site"].astype(str) == "CD-SP"]

    # One year of weekly data cannot support an annual season; a daily grid with season=7 can.
    weekly = to_panel(site_demand, freq="W", key=("sku",))
    assert weekly.shape[0] == 53
    assert not season_feasibility(weekly.shape[0], season=52, min_train=40).usable

    daily = to_panel(site_demand, freq="D", key=("sku",))
    assert daily.shape[0] == 365
    daily_check = season_feasibility(daily.shape[0], season=7, min_train=120, horizon=7, step=28)
    assert daily_check.usable
    assert daily_check.origins == 9

    # MAPE is defined on most period-observations and on almost no complete series.
    coverage = mape_coverage(daily.to_numpy())
    assert coverage.period_coverage == pytest.approx(0.584, abs=5e-3)
    assert coverage.series_coverage == pytest.approx(0.010, abs=5e-3)
    assert coverage.undefined_series == 0
    assert daily.shape[1] == 400

    zero_share = (daily == 0).mean()
    models = {**BASELINES, **INTERMITTENT}
    assert len(models) == 7
    kwargs = {"horizon": 7, "step": 28, "min_train": 120, "season": 7}

    regular = daily[zero_share[zero_share <= 0.5].index]
    sparse = daily[zero_share[zero_share > 0.5].index]
    assert regular.shape[1] == 260
    assert sparse.shape[1] == 140

    scored = {}
    for name, panel in {"regular": regular, "sparse": sparse}.items():
        results = backtest_panel(panel, models, **kwargs)
        assert results["origin"].nunique() == 9
        scored[name] = summarise(results, panel, min_train=120, season=7).set_index("model")

    # Every published row of both tables.
    expected = {
        "regular": {
            "sba": (0.9417, 0.7886, 0.0047, 0.9917, 0.5423),
            "tsb": (0.9455, 0.7902, 0.4792, 0.9956, 0.5154),
            "croston": (0.9483, 0.7928, 0.4735, 0.9986, 0.5192),
            "seasonal_naive": (0.9496, 0.9396, 0.4394, 1.0000, None),
            "moving_average": (1.0060, 0.8484, 0.8379, 1.0593, 0.3808),
            "naive": (1.6015, 1.5562, 5.9861, 1.6865, 0.1115),
            "drift": (1.6185, 1.5760, 6.0130, 1.7044, 0.1000),
        },
        "sparse": {
            "tsb": (1.0890, 0.7093, 0.0045, 0.9346, 0.6071),
            "sba": (1.1400, 0.7053, 0.0108, 0.9783, 0.5286),
            "seasonal_naive": (1.1653, 1.0780, 0.0146, 1.0000, None),
            "moving_average": (1.1661, 0.7678, 0.0240, 1.0007, 0.5571),
            "croston": (1.1686, 0.7068, 0.0185, 1.0029, 0.5000),
            "naive": (1.5393, 1.1923, 0.0899, 1.3210, 0.5071),
            "drift": (1.5632, 1.2052, 0.0923, 1.3415, 0.5000),
        },
    }
    for segment, rows in expected.items():
        summary = scored[segment]
        for model, (mase_, rmsse_, bias_, relative, share) in rows.items():
            row = summary.loc[model]
            assert row["mase"] == pytest.approx(mase_, abs=5e-4), (segment, model)
            assert row["rmsse"] == pytest.approx(rmsse_, abs=5e-4), (segment, model)
            assert row["bias"] == pytest.approx(bias_, abs=5e-4), (segment, model)
            assert row["relative_mase"] == pytest.approx(relative, abs=5e-4), (segment, model)
            if share is None:
                assert pd.isna(row["beats_reference_share"])
            else:
                assert row["beats_reference_share"] == pytest.approx(share, abs=5e-4)

    # The headroom on the regular half, and the floor on the sparse half.
    regular_summary = scored["regular"]
    best_regular = regular_summary["mase"].idxmin()
    assert best_regular == "sba"
    gain = (
        1
        - regular_summary.loc[best_regular, "mase"]
        / (regular_summary.loc["seasonal_naive", "mase"])
    )
    assert gain == pytest.approx(0.008, abs=5e-4)

    sparse_summary = scored["sparse"]
    assert sparse_summary["mase"].min() > 1.0
    assert sparse_summary["mase"].idxmin() == "tsb"
    assert 1 - sparse_summary.loc["tsb", "mase"] / sparse_summary.loc[
        "seasonal_naive", "mase"
    ] == pytest.approx(0.065, abs=5e-4)

    # The leader changes across the segment cut - that is the finding, not a rounding artefact.
    assert best_regular != sparse_summary["mase"].idxmin()

    # The 5% correction removes 99% of Croston's bias.
    croston_bias = regular_summary.loc["croston", "bias"]
    sba_bias = regular_summary.loc["sba", "bias"]
    assert 1 - abs(sba_bias) / abs(croston_bias) == pytest.approx(0.99, abs=5e-3)

    # Aggregation shrinks error by 27% and leaves bias exactly alone.
    panel = to_panel(full.demand, freq="D", key=("site", "sku"))
    total = aggregate_panel(panel)
    reference = {"seasonal_naive": BASELINES["seasonal_naive"]}
    assert panel.shape[1] == 1599

    fine = summarise(
        backtest_panel(panel, reference, **kwargs), panel, min_train=120, season=7
    ).set_index("model")
    coarse = summarise(
        backtest_panel(total, reference, **kwargs), total, min_train=120, season=7
    ).set_index("model")

    assert fine.loc["seasonal_naive", "mase"] == pytest.approx(1.1605, abs=5e-4)
    assert coarse.loc["seasonal_naive", "mase"] == pytest.approx(0.8480, abs=5e-4)
    assert 1 - coarse.loc["seasonal_naive", "mase"] / fine.loc["seasonal_naive", "mase"] == (
        pytest.approx(0.269, abs=5e-4)
    )

    per_series_bias = fine.loc["seasonal_naive", "bias"]
    assert per_series_bias == pytest.approx(-0.036690, abs=5e-7)
    assert per_series_bias * panel.shape[1] == pytest.approx(-58.6667, abs=5e-4)
    assert coarse.loc["seasonal_naive", "bias"] == pytest.approx(-58.6667, abs=5e-4)
    assert per_series_bias * panel.shape[1] == pytest.approx(
        coarse.loc["seasonal_naive", "bias"], abs=1e-8
    )


def test_inventory_tables(full: Dataset) -> None:
    """oplab/inventory/README.md: the contract understates the buffer, the lever has a closed
    form, the two service definitions differ by 82%, and the cheapest point is off the curve."""
    from dataclasses import replace

    import numpy as np

    from oplab.forecast import to_panel
    from oplab.inventory import (
        ContinuousReview,
        achieved_curve,
        expected_fill_rate,
        fit_demand,
        fit_lead_time,
        lead_time_by_supplier,
        reorder_point,
        safety_stock,
        simulate_policy,
        z_for_cycle_service,
        z_for_fill_rate,
    )
    from oplab.inventory.normal import norm_cdf

    orders = full.purchase_orders
    unit_cost = full.catalog.set_index("sku")["unit_cost"]
    panel = to_panel(
        full.demand.loc[full.demand["site"].astype(str) == "CD-SP"], freq="D", key=("sku",)
    )
    regular = panel.loc[:, (panel == 0).mean() <= 0.2]
    supplier_of = orders.drop_duplicates("sku").set_index("sku")["supplier"]
    lead_times = {
        name: fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        for name, group in orders.groupby("supplier")
    }
    z = z_for_cycle_service(0.95)

    # Finding 1, the supplier table: the quote tracks the mean and says nothing about the spread.
    table = lead_time_by_supplier(orders).set_index("supplier")
    expected_lead = {
        "FORN-REGIONAL": (5.0, 5.22, 1.03, 0.20, 1.74, 6.93),
        "FORN-NACIONAL": (7.0, 7.77, 3.56, 0.46, 3.55, 13.10),
        "FORN-CONTRATO": (12.0, 12.17, 1.58, 0.13, 0.99, 14.82),
        "FORN-IMPORT": (30.0, 31.68, 4.85, 0.15, 5.58, 36.88),
    }
    for supplier, (quoted, mean, sd, cv, skew, p95) in expected_lead.items():
        row = table.loc[supplier]
        assert row["quoted_lead_days"] == pytest.approx(quoted)
        assert row["mean_lead_days"] == pytest.approx(mean, abs=5e-3)
        assert row["sd_lead_days"] == pytest.approx(sd, abs=5e-3)
        assert row["cv_lead_days"] == pytest.approx(cv, abs=5e-3)
        assert row["skew_lead_days"] == pytest.approx(skew, abs=5e-3)
        assert row["p95_lead_days"] == pytest.approx(p95, abs=5e-3)
        # Every distribution is right skewed, which is what Finding 5 turns into a decision.
        assert row["skew_lead_days"] > 0.0

    # Finding 1, the money: sizing on the quote misses 58% of the requirement.
    rows = []
    for sku in regular.columns:
        supplier = supplier_of.get(sku)
        if supplier is None:
            continue
        demand = fit_demand(regular[sku].to_numpy())
        if demand.mean <= 0.0:
            continue
        profile = lead_times[supplier]
        realised = safety_stock(demand, profile, z)
        on_quote = safety_stock(demand, profile, z, use_quoted_lead_time=True)
        cost = float(unit_cost[sku])
        rows.append(
            {
                "sku": sku,
                "supplier": supplier,
                "demand_cv": demand.cv,
                "lead_share": realised.lead_time_share,
                "crossover_cv": float(np.sqrt(profile.cv**2 * profile.mean)),
                "capital": realised.units * cost,
                "capital_on_quote": on_quote.units * cost,
            }
        )
    sized = pd.DataFrame(rows)
    assert len(sized) == 191

    by_supplier = sized.groupby("supplier").agg(
        skus=("sku", "size"),
        capital=("capital", "sum"),
        on_quote=("capital_on_quote", "sum"),
        crossover=("crossover_cv", "first"),
        demand_cv=("demand_cv", "mean"),
        lead_share=("lead_share", "mean"),
        dominates=("lead_share", lambda s: float((s > 0.5).mean())),
    )
    expected_supplier = {
        "FORN-NACIONAL": (68, 82181, 38781, 0.5281, 1.277, 0.757, 0.741, 0.971),
        "FORN-IMPORT": (32, 37971, 23049, 0.3930, 0.861, 0.733, 0.585, 0.938),
        "FORN-CONTRATO": (36, 39574, 32375, 0.1819, 0.452, 0.756, 0.280, 0.000),
        "FORN-REGIONAL": (55, 32579, 27318, 0.1615, 0.452, 0.777, 0.272, 0.000),
    }
    for supplier, values in expected_supplier.items():
        skus, capital, quote, understated, crossover, cv_d, share, dominates = values
        row = by_supplier.loc[supplier]
        assert row["skus"] == skus
        assert row["capital"] == pytest.approx(capital, abs=1.0)
        assert row["on_quote"] == pytest.approx(quote, abs=1.0)
        assert 1 - row["on_quote"] / row["capital"] == pytest.approx(understated, abs=5e-4)
        assert row["crossover"] == pytest.approx(crossover, abs=5e-4)
        assert row["demand_cv"] == pytest.approx(cv_d, abs=5e-4)
        assert row["lead_share"] == pytest.approx(share, abs=5e-4)
        assert row["dominates"] == pytest.approx(dominates, abs=5e-4)

    total, on_quote = sized["capital"].sum(), sized["capital_on_quote"].sum()
    assert total == pytest.approx(192305, abs=1.0)
    assert on_quote == pytest.approx(121522, abs=1.0)
    assert 1 - on_quote / total == pytest.approx(0.368, abs=5e-4)
    assert total / on_quote - 1 == pytest.approx(0.58, abs=5e-3)
    assert (sized["lead_share"] > 0.5).mean() == pytest.approx(0.50, abs=5e-3)

    # Finding 2: the crossover condition is arithmetic, not a fitted rule.
    for supplier, profile in lead_times.items():
        crossover = float(np.sqrt(profile.cv**2 * profile.mean))
        group = sized.loc[sized["supplier"] == supplier]
        assert ((group["demand_cv"] < crossover) == (group["lead_share"] > 0.5)).all(), supplier

    # Finding 3: safety stock inverts against lead time, and total inventory does not.
    sku = regular.sum().sort_values(ascending=False).index[20]
    assert sku == "SKU-00345"
    demand = fit_demand(regular[sku].to_numpy())
    assert demand.mean == pytest.approx(23.9, abs=5e-2)
    assert demand.cv == pytest.approx(0.59, abs=5e-3)

    compared = {}
    for name, profile in lead_times.items():
        stock = safety_stock(demand, profile, z)
        compared[name] = (stock.units, demand.mean * profile.mean)
    expected_units = {
        "FORN-REGIONAL": (67.1, 124.7),
        "FORN-NACIONAL": (154.4, 185.9),
        "FORN-CONTRATO": (102.5, 291.1),
        "FORN-IMPORT": (231.7, 757.7),
    }
    for name, (safety, pipeline) in expected_units.items():
        assert compared[name][0] == pytest.approx(safety, abs=5e-2)
        assert compared[name][1] == pytest.approx(pipeline, abs=5e-2)

    fast, slow = "FORN-NACIONAL", "FORN-CONTRATO"
    fast_lead, slow_lead = lead_times[fast], lead_times[slow]
    assert slow_lead.mean / fast_lead.mean - 1 == pytest.approx(0.57, abs=5e-3)
    assert 1 - compared[slow][0] / compared[fast][0] == pytest.approx(0.34, abs=5e-3)
    assert fast_lead.sd / slow_lead.sd == pytest.approx(2.3, abs=5e-2)
    # Total inventory keeps the order the lead times imply - the honest qualification.
    assert sum(compared[fast]) < sum(compared[slow])

    # Finding 4: the same 99% sized two ways differs by 82%.
    profile = lead_times[supplier_of[sku]]
    assert supplier_of[sku] == "FORN-IMPORT"
    quantity = round(demand.mean * 28)
    sigma = safety_stock(demand, profile, 1.0).sigma
    as_cycle = safety_stock(demand, profile, z_for_cycle_service(0.99))
    z_fill = z_for_fill_rate(0.99, sigma, quantity)
    as_fill = safety_stock(demand, profile, z_fill)
    assert as_cycle.z == pytest.approx(2.326, abs=5e-4)
    assert z_fill == pytest.approx(1.279, abs=5e-4)
    assert as_cycle.units == pytest.approx(327.7, abs=5e-2)
    assert as_fill.units == pytest.approx(180.2, abs=5e-2)
    assert as_cycle.units / as_fill.units - 1 == pytest.approx(0.82, abs=5e-3)
    assert expected_fill_rate(as_cycle.z, sigma, quantity) == pytest.approx(0.9993, abs=5e-5)
    assert norm_cdf(z_fill) == pytest.approx(0.8996, abs=5e-5)

    # Finding 5: the price per point rises elevenfold and the last half-point buys 0.07%.
    curve = achieved_curve(
        demand,
        profile,
        quantity,
        float(unit_cost[sku]),
        regular[sku],
        periods=1095,
        replications=40,
    )
    expected_curve = {
        0.800: (665, float("nan"), 0.8920, 0.9829),
        0.900: (1013, 34.76, 0.9469, 0.9892),
        0.950: (1300, 57.42, 0.9625, 0.9917),
        0.980: (1623, 107.70, 0.9825, 0.9944),
        0.990: (1838, 215.41, 0.9855, 0.9950),
        0.995: (2035, 394.28, 0.9862, 0.9955),
    }
    indexed = curve.set_index("cycle_service_target")
    for target, (capital, per_point, cycle, fill) in expected_curve.items():
        row = indexed.loc[target]
        assert row["safety_capital"] == pytest.approx(capital, abs=1.0)
        if per_point != per_point:
            assert pd.isna(row["capital_per_point"])
        else:
            assert row["capital_per_point"] == pytest.approx(per_point, abs=5e-3)
        assert row["achieved_cycle_service"] == pytest.approx(cycle, abs=5e-5)
        assert row["achieved_fill_rate"] == pytest.approx(fill, abs=5e-5)

    per_point = curve["capital_per_point"].dropna()
    assert per_point.iloc[-1] / per_point.iloc[0] == pytest.approx(11.0, abs=0.5)
    top = curve.tail(2).reset_index(drop=True)
    assert top.loc[1, "safety_capital"] / top.loc[0, "safety_capital"] - 1 == pytest.approx(
        0.11, abs=5e-3
    )
    achieved_gain = top.loc[1, "achieved_cycle_service"] - top.loc[0, "achieved_cycle_service"]
    assert achieved_gain == pytest.approx(0.0007, abs=5e-5)

    # Finding 6: the reliability lever is 92 times the whole forecasting lever.
    z99 = z_for_cycle_service(0.99)
    base = safety_stock(demand, profile, z99).units
    forecast = safety_stock(replace(demand, sd=demand.sd * (1 - 0.008)), profile, z99).units
    capped_profile = fit_lead_time(
        np.minimum(profile.sample, profile.quantile(0.95)), quoted=profile.quoted
    )
    capped = safety_stock(demand, capped_profile, z99)
    assert base == pytest.approx(327.7, abs=5e-2)
    assert forecast == pytest.approx(326.8, abs=5e-2)
    assert capped.units == pytest.approx(249.9, abs=5e-2)
    gain_forecast = 1 - forecast / base
    gain_reliability = 1 - capped.units / base
    assert gain_forecast == pytest.approx(0.0026, abs=5e-5)
    assert gain_reliability == pytest.approx(0.237, abs=5e-4)
    assert gain_reliability / gain_forecast == pytest.approx(92.0, abs=0.5)

    # And the smaller policy still delivers, which is what makes it not a trade.
    achieved = simulate_policy(
        ContinuousReview(
            reorder_point=reorder_point(demand, capped_profile, capped), order_quantity=quantity
        ),
        regular[sku].to_numpy(dtype=float),
        capped_profile.sample,
        periods=1095,
        replications=40,
    ).summary()
    assert achieved["cycle_service"] == pytest.approx(0.9886, abs=5e-5)


def test_the_warmup_finding_reproduces(full: Dataset) -> None:
    """oplab/inventory/README.md: without a warm-up the same policy measures 89% to 97%.

    This is a limitation rather than a result, and it is asserted for the same reason as the
    results: it is the number that justifies a default, and a change that quietly made the
    default unnecessary should break the build rather than leave the text stale.
    """
    from oplab.forecast import to_panel
    from oplab.inventory import (
        ContinuousReview,
        fit_demand,
        fit_lead_time,
        reorder_point,
        safety_stock,
        simulate_policy,
        z_for_cycle_service,
    )

    orders = full.purchase_orders
    panel = to_panel(
        full.demand.loc[full.demand["site"].astype(str) == "CD-SP"], freq="D", key=("sku",)
    )
    regular = panel.loc[:, (panel == 0).mean() <= 0.2]
    sku = regular.sum().sort_values(ascending=False).index[20]
    supplier = orders.drop_duplicates("sku").set_index("sku")["supplier"][sku]
    profile = fit_lead_time(
        orders.loc[orders["supplier"] == supplier, "lead_days"].to_numpy(),
        quoted=float(orders.loc[orders["supplier"] == supplier, "quoted_lead_days"].iloc[0]),
    )
    demand = fit_demand(regular[sku].to_numpy())
    sized = safety_stock(demand, profile, z_for_cycle_service(0.95))
    policy = ContinuousReview(
        reorder_point=reorder_point(demand, profile, sized),
        order_quantity=round(demand.mean * 28),
    )

    def measure(opening: float | None, warmup: int | None) -> float:
        result = simulate_policy(
            policy,
            regular[sku].to_numpy(dtype=float),
            profile.sample,
            periods=365,
            replications=40,
            initial_stock=opening,
            warmup=warmup,
        )
        return float(result.summary()["cycle_service"])

    openings: list[float | None] = [None, float(policy.reorder_point), 0.0]
    without = [measure(opening, 0) for opening in openings]
    with_warmup = [measure(opening, None) for opening in openings]

    # The published range: 89% to 97% on identical data, decided by an unstated assumption.
    assert min(without) == pytest.approx(0.8933, abs=5e-4)
    assert max(without) == pytest.approx(0.9731, abs=5e-4)
    assert max(without) - min(without) == pytest.approx(0.0798, abs=5e-4)
    # The warm-up collapses it to under a point.
    assert max(with_warmup) - min(with_warmup) == pytest.approx(0.0118, abs=5e-4)


def test_mining_tables(full: Dataset) -> None:
    """oplab/mining/README.md: four routes carry four fifths of the volume, flow efficiency is
    3.1%, the slowest step is not the costliest, and a 97.8% conformance score is blind."""
    from oplab.mining import (
        activity_times,
        case_times,
        conformance,
        cost_of_deviation,
        deviations,
        directly_follows,
        flow_efficiency,
        profile_log,
        rework,
        to_event_log,
        variant_coverage,
        waiting_ranked,
    )
    from oplab.synth import HAPPY_PATH, VALUE_ADDING

    log = full.order_events

    # Finding 1: the log supports the analysis, and the wide milestone table does not.
    profile = profile_log(log)
    assert profile.cases == 4000
    assert profile.events == 38735
    assert profile.activities == 15
    assert profile.events_per_case == pytest.approx(9.68, abs=5e-3)
    assert profile.separates_work_from_wait

    milestones = to_event_log(
        full.order_lines.drop_duplicates("order_id"),
        "order_id",
        {"order_ts": "Order Received", "ship_ts": "Ship", "delivered_ts": "Deliver"},
    )
    flattened = profile_log(milestones)
    assert flattened.events == 252883
    assert not flattened.separates_work_from_wait

    # Finding 2: the variant count and the coverage point opposite ways, and both are reported.
    needed, total, top = variant_coverage(log, 0.8)
    assert (needed, total) == (4, 35)
    assert top == pytest.approx(0.611, abs=5e-4)

    # Finding 3: flow efficiency, and the half of the working time that is not work.
    efficiency = flow_efficiency(log, VALUE_ADDING)
    assert efficiency.lead_h == pytest.approx(43.21, abs=5e-3)
    assert efficiency.work_h == pytest.approx(2.82, abs=5e-3)
    assert efficiency.wait_h == pytest.approx(40.39, abs=5e-3)
    assert efficiency.value_adding_h == pytest.approx(1.34, abs=5e-3)
    assert efficiency.flow_efficiency == pytest.approx(0.0310, abs=5e-5)
    assert efficiency.busy_share == pytest.approx(0.0653, abs=5e-5)
    assert efficiency.wait_h / efficiency.lead_h == pytest.approx(0.9347, abs=5e-5)
    assert 1 - efficiency.value_adding_h / efficiency.work_h == pytest.approx(0.53, abs=5e-3)
    # The decomposition has to close, or one of the three numbers is measuring something else.
    assert efficiency.work_h + efficiency.wait_h == pytest.approx(efficiency.lead_h, abs=1e-9)

    # Finding 4: the waiting ranking, and the misdirection it corrects.
    ranked = waiting_ranked(log).set_index("activity")
    expected_waiting = {
        "Ship": (3911, 57715, 0.3572, 0.3572),
        "Stock Shortage": (553, 23379, 0.1447, 0.5020),
        "Load": (3911, 22399, 0.1386, 0.6406),
        "Allocate Stock": (4464, 18347, 0.1136, 0.7542),
        "Credit Hold": (426, 10313, 0.0638, 0.8180),
    }
    for activity, (runs, hours, share, cumulative) in expected_waiting.items():
        row = ranked.loc[activity]
        assert row["executions"] == runs
        assert row["total_wait_after_h"] == pytest.approx(hours, abs=1.0)
        assert row["share_of_waiting"] == pytest.approx(share, abs=5e-5)
        assert row["cumulative_share"] == pytest.approx(cumulative, abs=5e-5)

    durations = activity_times(log).set_index("activity")
    assert durations["mean_duration_h"].idxmax() == "Credit Hold"
    assert durations.loc["Credit Hold", "mean_duration_h"] == pytest.approx(6.34, abs=5e-3)
    assert durations.loc["Ship", "mean_duration_h"] == pytest.approx(0.052, abs=5e-4)
    # The slowest step holds a fourteenth of the waiting the quickest one does.
    assert (
        ranked.loc["Ship", "share_of_waiting"] > 5 * ranked.loc["Credit Hold", "share_of_waiting"]
    )

    # The handovers behind the ranking.
    graph = directly_follows(log).set_index(["source", "target"])
    assert graph.loc[("Ship", "Deliver"), "mean_handover_h"] == pytest.approx(14.844, abs=5e-3)
    assert graph.loc[("Stock Shortage", "Allocate Stock"), "mean_handover_h"] == pytest.approx(
        42.277, abs=5e-3
    )
    assert graph["share"].sum() == pytest.approx(1.0)

    # Finding 5: the fitness is exactly one minus the cancellation rate, and blind to the rest.
    result = conformance(log, HAPPY_PATH)
    assert result.cases == 4000
    assert result.conforming == 3911
    assert result.exact == 2444
    assert result.fitness == pytest.approx(0.9778, abs=5e-5)
    assert result.exact_share == pytest.approx(0.6110, abs=5e-5)
    cancelled = int((log["activity"] == "Cancel Order").sum())
    assert cancelled == 89
    assert result.fitness == pytest.approx(1 - cancelled / result.cases, abs=1e-12)
    assert result.conforming - result.exact == 1467

    deviation_table = deviations(log, HAPPY_PATH).set_index(["activity", "kind"])
    expected_deviations = {
        ("Stock Shortage", "inserted"): (553, 0.1383),
        ("Allocate Stock", "repeated"): (553, 0.1383),
        ("Credit Hold", "inserted"): (426, 0.1065),
        ("Quality Check", "repeated"): (364, 0.0910),
        ("Repack", "inserted"): (364, 0.0910),
    }
    for key, (cases, share) in expected_deviations.items():
        assert deviation_table.loc[key, "cases"] == cases, key
        assert deviation_table.loc[key, "share_of_cases"] == pytest.approx(share, abs=5e-5)

    rework_table = rework(log).set_index("activity")
    assert rework_table.loc["Quality Check", "mean_executions"] == pytest.approx(2.2308, abs=5e-5)
    assert rework_table.loc["Quality Check", "cases_affected"] == 364

    cost = cost_of_deviation(log, HAPPY_PATH, VALUE_ADDING).set_index("group")
    clean = cost.loc["follows the documented path"]
    dirty = cost.loc["deviates"]
    assert clean["cases"] == 2444
    assert dirty["cases"] == 1556
    assert clean["mean_lead_h"] == pytest.approx(30.94, abs=5e-3)
    assert dirty["mean_lead_h"] == pytest.approx(62.49, abs=5e-3)
    assert clean["mean_work_h"] == pytest.approx(1.70, abs=5e-3)
    assert dirty["mean_work_h"] == pytest.approx(4.58, abs=5e-3)
    assert clean["mean_wait_h"] == pytest.approx(29.24, abs=5e-3)
    assert dirty["mean_wait_h"] == pytest.approx(57.90, abs=5e-3)
    assert clean["flow_efficiency"] == pytest.approx(0.0442, abs=5e-5)
    assert dirty["flow_efficiency"] == pytest.approx(0.0207, abs=5e-5)
    assert dirty["mean_lead_h"] / clean["mean_lead_h"] == pytest.approx(2.0, abs=5e-2)
    # The deviating cases are proportionally worse, not just longer - that is the business case.
    assert dirty["flow_efficiency"] < clean["flow_efficiency"]

    # The deviating group includes the cancellations, which end early and make the figure
    # conservative. Asserted so the published caveat cannot drift from the data.
    times = case_times(log).set_index("case_id")
    cancelled_cases = set(log.loc[log["activity"] == "Cancel Order", "case_id"])
    traces = log.groupby("case_id", observed=True)["activity"].apply(tuple)
    deviating = {case for case, trace in traces.items() if trace != tuple(HAPPY_PATH)}
    assert times.loc[sorted(deviating), "lead_h"].mean() == pytest.approx(62.49, abs=5e-3)
    assert times.loc[sorted(deviating - cancelled_cases), "lead_h"].mean() == pytest.approx(
        64.05, abs=5e-3
    )


def test_forecast_error_to_stock_tables(full: Dataset) -> None:
    """oplab/forecast/README.md and oplab/inventory/README.md: the metric that ranks forecasts is
    not the metric that sizes stock, no method beats a training mean on this data, and a per-step
    error table is a seasonality table when the origins are a whole number of seasons apart."""
    import numpy as np

    from oplab.forecast import (
        BASELINES,
        INTERMITTENT,
        backtest_panel,
        error_profile,
        horizon_profile,
        interval_coverage,
        summarise,
        to_panel,
    )
    from oplab.inventory import (
        compare_sizing_bases,
        fit_demand,
        fit_lead_time,
        z_for_cycle_service,
    )

    def mean_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
        return np.full(horizon, float(np.mean(history)) if history.size else 0.0)

    panel = to_panel(
        full.demand.loc[full.demand["site"].astype(str) == "CD-SP"], freq="D", key=("sku",)
    )
    regular = panel.loc[:, (panel == 0).mean() <= 0.5]
    assert regular.shape[1] == 260

    models = {**BASELINES, **INTERMITTENT, "mean": mean_forecast}
    results = backtest_panel(regular, models, horizon=7, step=28, min_train=120, season=7)
    ranked = summarise(results, regular, min_train=120, season=7).set_index("model")

    # Finding 1: the two metrics rank the same winner and disagree on the order below it.
    expected = {
        "mean": (0.9415, 2.6419, 3.2762, 0.3462),
        "sba": (0.9417, 2.7147, 3.3007, 0.4731),
        "tsb": (0.9455, 2.7116, 3.2945, 0.4731),
        "croston": (0.9483, 2.7417, 3.3046, 0.4385),
        "seasonal_naive": (0.9496, 2.7698, 4.0904, 0.1885),
        "naive": (1.6015, 4.6508, 5.6971, 0.0500),
    }
    profiles = {}
    for model, (mase_, mae_, sd_, reduces) in expected.items():
        profile = error_profile(results, model)
        profiles[model] = profile
        assert ranked.loc[model, "mase"] == pytest.approx(mase_, abs=5e-4), model
        assert profile["mae"].median() == pytest.approx(mae_, abs=5e-4), model
        assert profile["sd"].median() == pytest.approx(sd_, abs=5e-4), model
        assert profile["reduces_buffer"].mean() == pytest.approx(reduces, abs=5e-4), model

    # A forecast of the training mean has the lowest error spread of the seven, so nothing here
    # reduces the buffer. That is the whole finding, and it is asserted rather than described.
    spreads = {model: float(profile["sd"].median()) for model, profile in profiles.items()}
    assert min(spreads, key=lambda m: spreads[m]) == "mean"
    assert ranked["mase"].idxmin() == "mean"

    # The mechanism: absolute error compresses what the spread exposes, by a factor of five.
    reference_mae = profiles["mean"]["mae"].median()
    reference_sd = profiles["mean"]["sd"].median()
    seasonal_mae = profiles["seasonal_naive"]["mae"].median() / reference_mae - 1
    seasonal_sd = profiles["seasonal_naive"]["sd"].median() / reference_sd - 1
    assert seasonal_mae == pytest.approx(0.0484, abs=5e-4)
    assert seasonal_sd == pytest.approx(0.2485, abs=5e-4)
    assert seasonal_sd / seasonal_mae == pytest.approx(5.1, abs=5e-2)
    # And MASE puts it under a point behind the leader on the same data.
    assert ranked.loc["seasonal_naive", "mase"] / ranked.loc["mean", "mase"] - 1 == pytest.approx(
        0.009, abs=5e-4
    )

    # Finding 2: the two sizings come to the same number, because the ratio is one.
    sba = profiles["sba"]
    assert sba["sd_ratio"].median() == pytest.approx(1.0019, abs=5e-4)
    assert sba["reduces_buffer"].mean() == pytest.approx(0.4731, abs=5e-4)

    orders = full.purchase_orders
    supplier_of = orders.drop_duplicates("sku").set_index("sku")["supplier"]
    lead_times = {
        name: fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        for name, group in orders.groupby("supplier")
    }
    z = z_for_cycle_service(0.95)
    sku = regular.sum().sort_values(ascending=False).index[20]
    assert sku == "SKU-00345"
    demand = fit_demand(regular[sku].to_numpy())
    indexed = sba.set_index("series")
    assert demand.sd == pytest.approx(14.21, abs=5e-3)
    assert indexed.loc[sku, "sd"] == pytest.approx(12.96, abs=5e-3)

    bases = compare_sizing_bases(
        demand,
        lead_times[supplier_of[sku]],
        error_sd=float(indexed.loc[sku, "sd"]),
        error_bias=float(indexed.loc[sku, "bias"]),
        z=z,
    ).set_index("basis")
    assert bases.loc["demand variability", "safety_units"] == pytest.approx(231.6882, abs=5e-4)
    assert bases.loc["forecast error", "safety_units"] == pytest.approx(225.4522, abs=5e-4)
    assert bases.loc["forecast error", "change_vs_demand"] == pytest.approx(-0.0269, abs=5e-4)

    # Finding 3: a near-zero average bias hides per-series bias in both directions.
    expected_bias = {
        "sba": (0.0047, 0.5231, -0.7224),
        "croston": (0.4735, 0.2846, -0.6673),
        "tsb": (0.4792, 0.2846, -0.6566),
    }
    for model, (mean_bias, under_share, bias_when_under) in expected_bias.items():
        profile = profiles[model]
        under = profile.loc[profile["bias"] < 0.0]
        assert profile["bias"].mean() == pytest.approx(mean_bias, abs=5e-4), model
        assert (profile["bias"] < 0.0).mean() == pytest.approx(under_share, abs=5e-4), model
        assert under["bias"].mean() == pytest.approx(bias_when_under, abs=5e-4), model
    # SBA's mean bias is near zero and it still under-forecasts more than half the assortment.
    assert abs(profiles["sba"]["bias"].mean()) < 0.01
    assert (profiles["sba"]["bias"] < 0.0).mean() > 0.5

    croston = profiles["croston"].set_index("series")
    worst = croston.loc[croston["bias"] < 0.0, "bias"].idxmin()
    assert worst == "SKU-00139"
    worst_demand = fit_demand(regular[worst].to_numpy())
    charged = compare_sizing_bases(
        worst_demand,
        lead_times[supplier_of[worst]],
        error_sd=float(croston.loc[worst, "sd"]),
        error_bias=float(croston.loc[worst, "bias"]),
        z=z,
    ).set_index("basis")
    charge = (
        charged.loc["forecast error", "safety_units"]
        - charged.loc["forecast error, bias uncorrected", "safety_units"]
    )
    uncorrected = charged.loc["forecast error, bias uncorrected", "safety_units"]
    assert croston.loc[worst, "bias"] == pytest.approx(-13.27, abs=5e-3)
    assert charge == pytest.approx(103.2, abs=5e-2)
    assert charge / uncorrected == pytest.approx(0.32, abs=5e-3)

    # Finding 4: the horizon table is phase-locked, and the pattern reproduces at every origin.
    profile = horizon_profile(results, "sba", step_between_origins=28, season=7)
    assert bool(profile["phase_locked"].all())
    indexed_steps = profile.set_index("step")
    assert indexed_steps.loc[1, "sd"] == pytest.approx(10.4237, abs=5e-4)
    assert indexed_steps.loc[4, "sd"] == pytest.approx(14.0836, abs=5e-4)
    assert indexed_steps.loc[4, "bias"] == pytest.approx(8.0844, abs=5e-4)
    # The square-root rule would ask for 2.0 at step 4 and the data gives 1.35.
    assert indexed_steps.loc[4, "sqrt_step"] == pytest.approx(2.0)
    assert indexed_steps.loc[4, "sd_vs_step_1"] == pytest.approx(1.3511, abs=5e-4)
    assert not profile["sd"].is_monotonic_increasing

    cells = (
        results.loc[results["model"] == "sba"]
        .assign(error=lambda f: f["forecast"] - f["actual"])
        .groupby(["origin", "step"])["error"]
        .mean()
        .unstack("step")
    )
    assert len(cells) == 9
    systematic = cells.mean()
    between = cells.std(ddof=1)
    # A systematic spread of eleven units between steps against about one unit between origins:
    # the pattern is the backtest's geometry, not sampling noise.
    assert systematic.max() == pytest.approx(8.08, abs=5e-3)
    assert systematic.min() == pytest.approx(-3.88, abs=5e-3)
    assert between.loc[4] == pytest.approx(1.03, abs=5e-3)
    assert between.max() < 1.5
    assert systematic.max() - systematic.min() > 7 * between.max()

    # And the normal interval over-covers while missing asymmetrically.
    coverage = interval_coverage(results, "sba", 0.95).set_index("step")
    assert coverage.loc[3, "normal_coverage"] == pytest.approx(0.9688, abs=5e-5)
    assert coverage.loc[3, "normal_below"] == pytest.approx(0.0295, abs=5e-5)
    assert coverage.loc[3, "normal_above"] == pytest.approx(0.0017, abs=5e-5)
    assert (coverage["normal_coverage"] > 0.95).all()
    assert coverage["empirical_coverage"].to_numpy() == pytest.approx(0.9496, abs=5e-5)


def test_study_one_reaches_the_verdicts_it_publishes(full: Dataset) -> None:
    """studies/README.md and the root README: two of four candidates are declined on measurement.

    A study is a chain of measurements ending in a decision, so the decision is what has to be
    asserted. Each of the four figures below is the one a verdict rests on; if any of them moves,
    the verdict may no longer follow and the study needs rewriting rather than renumbering.
    """
    import numpy as np

    from oplab.benchmark import indirect_standardisation
    from oplab.forecast import BASELINES, INTERMITTENT, backtest_panel, error_profile, to_panel
    from oplab.inventory import fit_demand, fit_lead_time, safety_stock, z_for_cycle_service
    from oplab.kpi import service_sensitivity
    from oplab.mining import conformance, cost_of_deviation, flow_efficiency, waiting_ranked
    from oplab.slotting import (
        abc_xyz,
        compare_strategies,
        cube_per_order_index,
        demand_profile,
        pick_counts,
        reslot,
    )
    from oplab.synth import HAPPY_PATH, VALUE_ADDING

    # Check 1: the service gap is partly definitional, at 15.6 points of spread.
    sensitivity = service_sensitivity(full.order_lines)
    spread = float(sensitivity["otif"].max() - sensitivity["otif"].min())
    assert spread == pytest.approx(0.156, abs=5e-4)

    # Check 2: 35% of the cost gap is geography, and CD-PE is still the worst site.
    ledger = full.cost_ledger.copy()
    ledger["band"] = pd.cut(
        ledger["distance_km"],
        [0.0, 10.0, 25.0, 50.0, float("inf")],
        labels=["0-10 km", "10-25 km", "25-50 km", "50+ km"],
    ).astype(str)
    aggregated = (
        ledger.groupby(["site", "band"], observed=True)
        .agg(cost=("total_brl", "sum"), deliveries=("order_id", "size"))
        .reset_index()
    )
    standardised = indirect_standardisation(
        aggregated, "site", "band", "cost", "deliveries", exclude_self=True
    ).set_index("site")
    crude = standardised["crude_rate"]
    adjusted = standardised["standardised_rate"]
    geography = 1 - (adjusted.max() - adjusted.min()) / (crude.max() - crude.min())
    assert geography == pytest.approx(0.35, abs=5e-3)
    assert crude.idxmax() == "CD-PE"
    assert adjusted.idxmax() == "CD-PE"
    assert crude.loc["CD-PE"] / crude.loc["CD-SP"] - 1 == pytest.approx(0.58, abs=5e-3)
    assert adjusted.loc["CD-PE"] / adjusted.loc["CD-SP"] - 1 == pytest.approx(0.35, abs=5e-3)

    # Candidate A: fund. 70% of the travel at CD-PE, and 2.6 points between the three rules.
    demand = full.demand.loc[full.demand["site"].astype(str) == "CD-PE"]
    picks = pick_counts(full.order_lines, site="CD-PE")
    classified = abc_xyz(demand_profile(demand, full.catalog, period="W"))
    classified = classified.loc[classified.index.isin(picks.index)]
    cube = full.catalog.set_index("sku")["case_volume_m3"]
    table = compare_strategies(
        picks,
        full.layout,
        {
            "current (as received)": full.assignment,
            "by revenue": reslot(-classified["annual_value"], full.layout, cube=cube),
            "by popularity": reslot(-picks, full.layout, cube=cube),
            "by cube-per-order index": reslot(
                cube_per_order_index(picks, cube), full.layout, cube=cube
            ),
        },
        baseline="current (as received)",
    )
    ranked = table.loc[table["strategy"] != "current (as received)"]
    best = ranked.loc[ranked["mean_distance_per_pick_m"].idxmin()]
    assert best["strategy"] == "by popularity"
    assert -best["change_vs_baseline"] == pytest.approx(0.70, abs=5e-3)
    rule_spread = ranked["change_vs_baseline"].max() - ranked["change_vs_baseline"].min()
    assert rule_spread == pytest.approx(0.026, abs=5e-4)

    # Candidate B: decline. A forecast of the training mean has the lowest error spread.
    panel = to_panel(
        full.demand.loc[full.demand["site"].astype(str) == "CD-SP"], freq="D", key=("sku",)
    )
    regular = panel.loc[:, (panel == 0).mean() <= 0.5]

    def mean_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
        return np.full(horizon, float(np.mean(history)) if history.size else 0.0)

    models = {**BASELINES, **INTERMITTENT, "mean": mean_forecast}
    assert len(models) == 8
    results = backtest_panel(regular, models, horizon=7, step=28, min_train=120, season=7)
    spreads = {name: float(error_profile(results, name)["sd"].median()) for name in models}
    assert min(spreads, key=lambda name: spreads[name]) == "mean"
    assert spreads["mean"] == pytest.approx(3.2762, abs=5e-4)

    # Candidate C: fund, scoped. Four handovers hold 75% of the waiting.
    log = full.order_events
    efficiency = flow_efficiency(log, VALUE_ADDING)
    assert efficiency.flow_efficiency == pytest.approx(0.0310, abs=5e-5)
    cost = cost_of_deviation(log, HAPPY_PATH, VALUE_ADDING).set_index("group")
    dirty, clean = cost.loc["deviates"], cost.loc["follows the documented path"]
    assert int(dirty["cases"]) == 1556
    assert dirty["mean_lead_h"] / clean["mean_lead_h"] == pytest.approx(2.0, abs=5e-2)
    assert conformance(log, HAPPY_PATH).exact_share == pytest.approx(0.611, abs=5e-4)
    top_four = waiting_ranked(log).head(4)
    assert top_four["share_of_waiting"].sum() == pytest.approx(0.754, abs=5e-4)
    assert list(top_four["activity"]) == ["Ship", "Stock Shortage", "Load", "Allocate Stock"]

    # Candidate D: decline as asked. The plan is 37% short, and the supplier fix releases 16%.
    orders = full.purchase_orders
    supplier_of = orders.drop_duplicates("sku").set_index("sku")["supplier"]
    lead_times = {
        name: fit_lead_time(
            group["lead_days"].to_numpy(), quoted=float(group["quoted_lead_days"].iloc[0])
        )
        for name, group in orders.groupby("supplier")
    }
    z = z_for_cycle_service(0.95)
    unit_cost = full.catalog.set_index("sku")["unit_cost"]
    tight_regular = panel.loc[:, (panel == 0).mean() <= 0.2]

    realised = on_quote = capped = 0.0
    for sku in tight_regular.columns:
        supplier = supplier_of.get(sku)
        if supplier is None:
            continue
        profile = fit_demand(tight_regular[sku].to_numpy())
        if profile.mean <= 0.0:
            continue
        lead = lead_times[supplier]
        cost_per_unit = float(unit_cost[sku])
        realised += safety_stock(profile, lead, z).units * cost_per_unit
        on_quote += safety_stock(profile, lead, z, use_quoted_lead_time=True).units * cost_per_unit
        tighter = fit_lead_time(np.minimum(lead.sample, lead.quantile(0.95)), quoted=lead.quoted)
        capped += safety_stock(profile, tighter, z).units * cost_per_unit

    assert on_quote == pytest.approx(121522, abs=1.0)
    assert realised == pytest.approx(192305, abs=1.0)
    assert capped == pytest.approx(162185, abs=1.0)
    assert 1 - on_quote / realised == pytest.approx(0.37, abs=5e-3)
    assert realised - capped == pytest.approx(30120, abs=1.0)
    assert 1 - capped / realised == pytest.approx(0.157, abs=5e-4)


def test_study_two_refuses_the_actions_it_publishes(full: Dataset) -> None:
    """studies/README.md and the root README: three of four slide items support no action.

    A study whose conclusion is "do not act" has to be held to a higher standard than one that
    recommends spending, because the cost of being wrong lands on nobody's budget. Each refusal
    below rests on a figure, and every figure is pinned here.
    """
    from oplab.kpi import otif, service_sensitivity
    from oplab.mining import waiting_ranked
    from oplab.spc import (
        capability_from_subgroups,
        overdispersion_ratio,
        p_chart,
        xbar_r_chart,
    )

    all_rules = tuple(range(1, 9))
    lines = full.order_lines.copy()
    lines["month"] = pd.to_datetime(lines["order_ts"]).dt.to_period("M").astype(str)
    served = lines.loc[lines["status"] != "cancelled"]
    monthly = served.groupby("month").agg(lines=("line_id", "size"))
    monthly["otif"] = otif(served, by="month")
    monthly["failures"] = ((1.0 - monthly["otif"]) * monthly["lines"]).round().astype(int)

    # Check 1: October is a signal, on a chart whose own assumption is violated.
    assert len(monthly) == 12
    assert monthly["otif"].idxmin() == "2025-10"
    assert monthly.loc["2025-10", "otif"] == pytest.approx(0.7808, abs=5e-5)
    assert monthly["otif"].idxmax() == "2025-12"
    assert monthly.loc["2025-12", "otif"] == pytest.approx(0.7996, abs=5e-5)

    chart = p_chart(monthly["failures"], monthly["lines"], rules=all_rules)
    assert int(chart.out_of_control.sum()) == 1
    assert bool(chart.out_of_control.loc["2025-10"])
    worst_z = float(chart.violations.query("label == '2025-10'")["z"].max())
    assert worst_z == pytest.approx(5.04, abs=5e-3)

    ratio = overdispersion_ratio(chart)
    assert ratio == pytest.approx(1.787, abs=5e-4)
    # The signal survives the adjustment, which is why the refusal rests on scale rather than
    # on dismissing it. Quoting the unadjusted figure is what the study refuses.
    assert worst_z / ratio**0.5 == pytest.approx(3.77, abs=5e-3)
    assert worst_z / ratio**0.5 > 3.0
    # Limits about 0.8 points wide on ~24,000 lines a month.
    assert (chart.ucl.max() - chart.center) * 100 == pytest.approx(0.8, abs=5e-2)
    assert monthly["lines"].mean() == pytest.approx(23946, abs=1.0)

    annual_range = float(monthly["otif"].max() - monthly["otif"].min())
    conventions = service_sensitivity(full.order_lines)
    convention_range = float(conventions["otif"].max() - conventions["otif"].min())
    assert annual_range * 100 == pytest.approx(1.88, abs=5e-3)
    assert convention_range * 100 == pytest.approx(15.57, abs=5e-3)
    assert convention_range / annual_range == pytest.approx(8.3, abs=5e-2)

    # Check 2: December's recovery is censoring. It is the only month with open lines.
    status = lines.groupby("month")["status"].value_counts().unstack(fill_value=0)
    unresolved = status["in_transit"] + status["open"]
    assert int(unresolved.loc["2025-12"]) == 1636
    assert int(unresolved.drop("2025-12").sum()) == 0
    assert unresolved.loc["2025-12"] / status.loc["2025-12"].sum() == pytest.approx(0.063, abs=5e-4)

    # Check 3: the process shift is real, locatable, and only visible from a clean baseline.
    clean, ranges = xbar_r_chart(full.subgroups, baseline=slice(0, 40), rules=all_rules)
    contaminated, _ = xbar_r_chart(full.subgroups, rules=all_rules)
    first = clean.violations.query("position >= 40").sort_values("position").iloc[0]
    assert int(first["label"]) == 43
    assert first["z"] == pytest.approx(3.96, abs=5e-3)
    assert int(first["rule"]) == 1
    # The range chart is quiet, so the spread did not change - only the centre moved.
    assert int(ranges.out_of_control.sum()) == 0
    assert clean.center == pytest.approx(499.7155, abs=5e-4)
    assert contaminated.center == pytest.approx(500.6674, abs=5e-4)
    assert int(clean.out_of_control.iloc[:40].sum()) == 2
    assert int(contaminated.out_of_control.iloc[:40].sum()) == 14

    capability = capability_from_subgroups(full.subgroups, lsl=495.0, usl=505.0)
    assert capability.cp == pytest.approx(0.820, abs=5e-4)
    assert capability.pp == pytest.approx(0.657, abs=5e-4)
    # Pp below Cp is the shift appearing as if it were incapability.
    assert capability.pp < capability.cp

    # Check 4: the two signals do not observe the same window, so no relationship is available.
    stamps = full.subgroups.groupby("subgroup")["timestamp"].min()
    span_h = (pd.Timestamp(stamps.iloc[-1]) - pd.Timestamp(stamps.iloc[0])).total_seconds() / 3600.0
    assert len(stamps) == 60
    assert span_h == pytest.approx(59.0, abs=0.5)
    assert span_h / 24 == pytest.approx(2.5, abs=5e-2)
    assert pd.Timestamp(stamps.iloc[0]).strftime("%Y-%m") == "2025-06"
    assert pd.Timestamp(stamps.iloc[-1]).strftime("%Y-%m") == "2025-06"
    # October is outside the process chart's window entirely.
    assert not (
        pd.Timestamp(stamps.iloc[0]) <= pd.Timestamp("2025-10-15") <= pd.Timestamp(stamps.iloc[-1])
    )

    # The standing target that needs no signal to justify it.
    waiting = waiting_ranked(full.order_events).head(4)
    assert waiting["share_of_waiting"].sum() == pytest.approx(0.754, abs=5e-4)


def test_examples_and_studies_run_without_error() -> None:
    """The runnable scripts are part of the deliverable; a broken one is a broken README."""
    import runpy
    import sys
    from io import StringIO
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scripts = sorted((root / "examples").glob("*.py")) + sorted((root / "studies").glob("*.py"))
    assert len(scripts) == 14

    for script in scripts:
        captured, sys.stdout = sys.stdout, StringIO()
        try:
            runpy.run_path(str(script), run_name="__main__")
        finally:
            output = sys.stdout.getvalue()
            sys.stdout = captured
        assert output.strip(), f"{script.name} printed nothing"
