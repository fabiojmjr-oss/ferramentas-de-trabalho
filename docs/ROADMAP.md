# Roadmap

Ten tools, built in four waves. The sequence is deliberate: the foundation generates the data
every later tool consumes, and each wave is shippable on its own.

Selection rule — a tool earns a place only if it answers a question a regional operations lead
actually has, and if the answer would change a decision. Anything that is interesting but
decision-neutral is left out.

## Status

| # | Tool | Module | Question it answers | Wave |
| --- | --- | --- | --- | --- |
| 0 | Synthetic data generator | `oplab.synth` | What do I test against without exposing a real operation? | 1 — done |
| 1 | KPI engine | `oplab.kpi` | What is the service level, and how much of it is definition? | 1 — done |
| 2 | SPC toolkit | `oplab.spc` | Did the process change, and is it capable? | 1 — done |
| 3 | ABC-XYZ and slotting | `oplab.slotting` | Which items go where, and what does the current layout cost? | 2 — done |
| 4 | Variance decomposer | `oplab.variance` | Why did cost per order move, and who owns the delta? | 2 |
| 5 | DC capacity simulation | `oplab.simulation` | Where is the constraint, and what does relieving it buy? | 3 |
| 6 | Route optimiser | `oplab.routing` | What does a delivery cost under each fleet scenario? | 3 |
| 7 | Multi-site benchmark | `oplab.benchmark` | Which site is genuinely underperforming once size and mix are held constant? | 4 |
| 8 | Process mining | `oplab.mining` | What does the process actually do, as opposed to the flowchart? | 4 |
| 9 | Forecast baseline | `oplab.forecast` | Does this forecast beat seasonal naive, measured honestly? | 4 |
| 10 | Inventory policy lab | `oplab.inventory` | What does each point of service level cost in working capital? | 4 |

## Wave 1 — foundation *(complete)*

`synth`, `kpi`, `spc`.

Everything downstream needs data and needs trustworthy indicators to judge itself against.
Building these first also means no later tool has an excuse to invent its own definition of
OTIF.

## Wave 2 — visible results

**ABC-XYZ and slotting** *(complete — [module README](../src/oplab/slotting/README.md))*.
Delivered as planned, with one result that came out against expectation and was kept: three
sensible ranking rules all recover about two thirds of the travel, and the spread between them
is 1.7 points, so the fundable decision is whether to re-slot rather than which optimiser to
buy. The cube-per-order index finished last, which is correct under one-face-per-SKU with
uniform capacity, and the module explains the condition under which it wins instead.

Building it also exposed a design flaw in the generator worth recording: demand volatility had
been tied to the slow-moving tail, so every erratic item was low value by construction and an
ABC-XYZ analysis could never produce an AZ cell. Volatility is now drawn independently of
volume, via a per-SKU gamma shock held across the week. Fixing it moved every published figure,
which the README claim tests caught immediately - the reason those tests exist.

**Variance decomposer.** Price-volume-mix decomposition of a cost or revenue movement, with a
driver tree and an automated Pareto identifying which site, SKU or lane explains the delta.
Output is a waterfall. This is the tool that turns an hour of guessing in a performance review
into ten minutes of reading.

## Wave 3 — the depth piece

Two anchors, built in sequence rather than in parallel. Two projects at 60% completion signal
worse than one at 100%.

**DC capacity simulation.** Discrete-event model of receiving → put-away → picking →
checking → dispatch, with queues, shifts and absenteeism. Reports resource utilisation, vehicle
dwell time and the moving constraint. The point is the question a static capacity spreadsheet
cannot answer: more docks, more pickers, or an extra shift?

**Route optimiser.** Vehicle routing with time windows, capacity and multiple depots, with a
scenario comparator — own fleet against third party, one shift against two, delivery density
against cost per drop.

## Wave 4 — differentiation

**Multi-site benchmark.** Normalisation by size and mix, then data envelopment analysis for
relative efficiency across multiple inputs and outputs. Comparing sites of different scale
without normalisation produces a political ranking, not a technical one.

**Process mining.** From an event log to a discovered process map, cycle time per transition,
rework loops, and lead time against value-added time. A value stream map generated from data
rather than from sticky notes.

**Forecast baseline.** Rolling-origin backtesting that compares naive and seasonal-naive
against ETS, ARIMA and gradient boosting, with explicit handling of intermittent demand
(Croston, SBA, TSB) and scale-free error metrics — MASE and RMSSE, not MAPE. Built on
`statsforecast` rather than from scratch. The position being taken is that a forecast project
without an honest baseline is unmeasurable, and most of them do not have one.

**Inventory policy lab.** Safety stock from demand *and* lead time variability, comparing
`(s,Q)`, `(R,S)` and periodic review, with Monte Carlo simulation of stockout and fill rate.
The deliverable is the working-capital-per-service-point curve, which is the one chart a CFO
reads in five seconds.

## Cross-cutting

These are not tools and they matter more than an eleventh one:

- **Data contracts** at every entry point. Without them every tool above is brittle. Already in
  place for wave 1 (`oplab.kpi.schemas`) and extended as each module lands.
- **One synthetic generator** feeding everything, so tools compose and no example needs its own
  fixture. Already in place.
- **CI on every push** — lint, format, type check, test, coverage.
- **A standard README per tool**: business problem → decision it enables → three-line usage →
  result with a figure → assumptions and limitations. The limitations section is not optional.

## Conventions

- Code, docstrings and commits in English; README in English and Portuguese.
- Public functions are typed and have a docstring that states what the function decides on the
  caller's behalf.
- No tool ships without tests against hand-computed values, not only against its own output.
- No real operational data, ever. See [`../DISCLAIMER.md`](../DISCLAIMER.md).
