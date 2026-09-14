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
| 4 | Variance decomposer | `oplab.variance` | Why did cost per order move, and who owns the delta? | 2 — done |
| 5 | DC capacity simulation | `oplab.simulation` | Where is the constraint, and what does relieving it buy? | 3 — done |
| 6 | Route optimiser | `oplab.routing` | What does a delivery cost under each fleet scenario? | 3 — done |
| 7 | Multi-site benchmark | `oplab.benchmark` | Which site is genuinely underperforming once size and mix are held constant? | 4 — done |
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

**Variance decomposer** *(complete — [module README](../src/oplab/variance/README.md))*.
Price-volume-mix on totals, a two-term exact bridge on per-unit metrics, an absolute-contribution
Pareto and a waterfall. Both decompositions reconcile with no residual, which is asserted rather
than assumed.

The finding it produced was not the one planned. Cost per order rose 20.7%, and the split
between "operational" and "commercial" depends entirely on the segmentation: omitting the
channel dimension reports 99% of the rise as rate, and adding it moves a quarter of it to mix.
An omitted dimension does not vanish - it reappears inside the rate effect and is charged to
whoever owns the rate, invisibly, because the arithmetic reconciles either way. The module leads
with that warning rather than with the formulas.

Wave 2 is complete.

## Wave 3 — the depth piece

Two anchors, built in sequence rather than in parallel. Two projects at 60% completion signal
worse than one at 100%. Both are complete; wave 3 is closed.

**DC capacity simulation** *(complete — [module README](../src/oplab/simulation/README.md))*.
Discrete-event model of receiving, put-away, picking and checking, with queues, a shift
calendar and replicated runs reporting confidence intervals.

The answer to "more docks, more pickers, or an extra shift?" turned out to be "none of those".
The spreadsheet's utilisation figures are correct and decide nothing: picking at 78% causes
nearly three times the waiting of checking at 95%, because orders are released in two waves.
Levelling the release recovers 2.8 times what the best paid option does and costs nothing, and
four more pickers - the intuitive move - cannot be shown to do anything at all. That last
finding only exists because scenarios are compared on intervals rather than point estimates.

Building it also produced an instructive bug. Utilisation came out above 100%, which is
impossible, because a task interrupted by the shift break keeps its resource overnight and that
held time was being divided by open hours only. The fix was conceptual rather than arithmetic:
utilisation is work performed over capacity available, both counting open hours only, and time
held while closed is a separate metric - which for a dock is trailer detention, a real cost that
no utilisation figure contains.

**Route optimiser** *(complete — [module README](../src/oplab/routing/README.md))*. Vehicle
routing with time windows and capacity on OR-Tools, with a scenario comparator covering own
fleet against third party, the cost of the delivery windows, and density against cost per drop.
Multiple depots were dropped from scope: each site routes independently, which is what the data
supports.

The headline result is a refusal. Against a carrier at 42.00 per delivery, the own fleet costs
53.29 at a small search budget and 38.50 at a larger one - so the conclusion itself flips with
how hard the solver looked, and the documented answer is that the model does not settle
make-or-buy at this price. What it does decide, by a margin no assumption threatens: the truck
is the wrong vehicle for this profile.

Three mistakes are recorded in the module rather than quietly fixed.

The vehicle count offered to the solver was bounded using service time only, which ignores
travel; on a territory with a hundred-kilometre radius that reported a feasible day as
infeasible - the worst kind of bug, because it looks like a finding.

A travel-based lower bound on fleet size turned out not to be a bound at all: it came out above
the achieved solution, because a route amortises the radius across its stops. The amount by
which routing beats that figure is exactly the density effect the module measures.

And the search budget was a wall-clock limit, which made results depend on machine load - a
claim test passed alone and failed inside the full suite. The budget is now a reproducible
solution count. Fixing it also corrected a published finding: the delivery windows cost 2.2%,
not the 8.8% the under-searched solve reported, because a heuristic given too little budget
struggles more with the constrained problem than with the open one and therefore overstates the
cost of every constraint priced with it.

Wave 3 is closed. Wave 4 is in progress: the multi-site benchmark is done.

## Wave 4 — differentiation

**Multi-site benchmark** *(complete — [module README](../src/oplab/benchmark/README.md))*.
Scale normalisation, indirect standardisation, peer z-scores with rank-stability testing, and
DEA with a discrimination check.

Three findings, and two of them are about the method. A third of the cost-per-order gap between
the best and worst site is the distance profile they serve rather than how they are run: the
worst site reads 58% more expensive crude and 35% adjusted. Under random weightings the ranking
between sites turns out to be a fact while the ranking between one site's own months is a
weighting artefact - 2 of 4 against 12 of 12, with swings up to ten places. And DEA needs twelve
units for this measure set on a network of four, where the symptom is that the returns-to-scale
choice moves the worst site by 27 points, mostly as a penalty for being small.

Building it exposed a real incoherence in the generator, which is what a benchmarking tool is
supposed to do. Freight cost did not depend on delivery distance, because the ledger was
generated before the geography - so a distance existed that affected nothing and a freight cost
existed that ignored distance. The generator now derives cost from the delivery table, and each
site serves a territory of its own dispersion. Without both fixes there was no geographic
confound anywhere in the data and this module had nothing to demonstrate on.

It also needed a leave-one-out option that was not in the plan. Indirect standardisation
compares each unit against a benchmark it is part of, and on four sites that is a quarter of the
reference: a site 20% worse than its peers scores 1.02 rather than 1.20 because its own cost
drags the standard towards it.

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
