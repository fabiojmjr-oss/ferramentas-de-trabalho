"""Every figure quoted in the README, asserted against the code that produces it.

A README is documentation until it carries numbers, at which point it is a claim. These tests
make the claims fail loudly rather than drift: any change to the generator, to a definition or
to a chart that moves one of these figures breaks the build and forces the text to be updated
with it.

The tests use the default :class:`SynthConfig`, which is what the README and the example
scripts use. Generating it costs a few seconds, so they are marked ``slow``.
"""

from __future__ import annotations

import pytest

from oplab.kpi import fill_rate, otif, service_sensitivity
from oplab.spc import capability_from_subgroups, overdispersion_ratio, p_chart, xbar_r_chart
from oplab.synth import Dataset, generate_dataset

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def full() -> Dataset:
    return generate_dataset()


def test_order_book_size(full: Dataset) -> None:
    assert len(full.order_lines) == 300_718


def test_service_spread_table(full: Dataset) -> None:
    """README: 76.1% to 91.7% OTIF, a 15.6-point spread, on one order book."""
    table = service_sensitivity(full.order_lines).set_index("policy")

    expected = {
        "strict": (0.761, 0.786, 0.926, 296_962),
        "standard": (0.794, 0.821, 0.967, 284_412),
        "grace_1day": (0.916, 0.947, 0.967, 284_412),
        "tolerant_5pct": (0.917, 0.947, 0.967, 284_412),
    }
    for policy, (otif_value, on_time, in_full, in_scope) in expected.items():
        row = table.loc[policy]
        assert row["otif"] == pytest.approx(otif_value, abs=5e-4)
        assert row["on_time"] == pytest.approx(on_time, abs=5e-4)
        assert row["in_full"] == pytest.approx(in_full, abs=5e-4)
        assert int(row["lines_in_scope"]) == in_scope

    spread = table["otif"].max() - table["otif"].min()
    assert spread == pytest.approx(0.156, abs=5e-4)


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
    """README: 98.4% per unit, 96.7% per line, 90.0% per order."""
    assert float(fill_rate(full.order_lines, "unit")) == pytest.approx(0.984, abs=5e-4)
    assert float(fill_rate(full.order_lines, "line")) == pytest.approx(0.967, abs=5e-4)
    assert float(fill_rate(full.order_lines, "order")) == pytest.approx(0.900, abs=5e-4)


def test_baseline_table(full: Dataset) -> None:
    """README: centre line moves from 499.95 to 500.91; half-width stays near 2.7."""
    stable, _ = xbar_r_chart(full.subgroups, baseline=slice(0, 40))
    whole, _ = xbar_r_chart(full.subgroups)

    assert stable.center == pytest.approx(499.95, abs=5e-3)
    assert whole.center == pytest.approx(500.91, abs=5e-3)
    assert float(stable.ucl.iloc[0] - stable.center) == pytest.approx(2.764, abs=5e-4)
    assert float(whole.ucl.iloc[0] - whole.center) == pytest.approx(2.676, abs=5e-4)
    assert int(stable.out_of_control.iloc[:40].sum()) == 1
    assert int(whole.out_of_control.iloc[:40].sum()) == 12


def test_capability_gap(full: Dataset) -> None:
    """README and example 2: Cpk 1.19 against Ppk 0.97."""
    result = capability_from_subgroups(full.subgroups, lsl=492.0, usl=508.0)
    assert result.cpk == pytest.approx(1.19, abs=5e-3)
    assert result.ppk == pytest.approx(0.97, abs=5e-3)


def test_overdispersion_table(full: Dataset) -> None:
    """README: 2.12 and 98 of 359 days per line; 1.01 and 7 of 359 per order."""
    lines = full.order_lines
    delivered = lines.loc[(lines["status"] == "delivered") & (lines["site"] == "CD-SP")].copy()
    delivered["late"] = delivered["delivered_ts"] > delivered["promised_ts"]
    delivered["day"] = delivered["delivered_ts"].dt.normalize()

    per_line = (
        delivered.groupby("day").agg(total=("line_id", "size"), late=("late", "sum")).iloc[3:-3]
    )
    line_chart = p_chart(per_line["late"], per_line["total"].astype(float))
    assert len(per_line) == 359
    assert int(per_line["total"].min()) == 91
    assert int(per_line["total"].max()) == 300
    assert int(line_chart.out_of_control.sum()) == 98
    assert overdispersion_ratio(line_chart) == pytest.approx(2.12, abs=5e-3)

    orders = delivered.groupby("order_id").agg(day=("day", "first"), late=("late", "max"))
    per_order = orders.groupby("day").agg(total=("late", "size"), late=("late", "sum")).iloc[3:-3]
    order_chart = p_chart(per_order["late"], per_order["total"].astype(float))
    assert int(per_order["total"].min()) == 30
    assert int(per_order["total"].max()) == 93
    assert int(order_chart.out_of_control.sum()) == 7
    assert overdispersion_ratio(order_chart) == pytest.approx(1.01, abs=5e-3)


def test_carrier_adherence_is_reported_in_full(full: Dataset) -> None:
    """Example 3 claims own fleet at 89.5% and the worst carrier at 18.8%."""
    from oplab.kpi import appointment_adherence

    result = appointment_adherence(full.receipts).set_index("carrier")
    assert result.loc["FROTA-PROPRIA", "on_time"] == pytest.approx(0.895, abs=5e-4)
    assert result.loc["TRANSP-C", "on_time"] == pytest.approx(0.188, abs=5e-4)


def test_examples_run_without_error() -> None:
    """The three example scripts are part of the deliverable; a broken one is a broken README."""
    import runpy
    import sys
    from io import StringIO
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    scripts = sorted((root / "examples").glob("*.py"))
    assert len(scripts) == 3

    for script in scripts:
        captured, sys.stdout = sys.stdout, StringIO()
        try:
            runpy.run_path(str(script), run_name="__main__")
        finally:
            output = sys.stdout.getvalue()
            sys.stdout = captured
        assert output.strip(), f"{script.name} printed nothing"
