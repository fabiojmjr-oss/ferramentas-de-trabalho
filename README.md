# oplab — operations analytics toolkit

[![ci](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Logistics indicators, statistical process control, pick-face slotting, cost variance
decomposition, discrete-event capacity simulation, vehicle routing, and the synthetic supply
chain data to exercise all of it. Python, tested, typed.

**[Leia em português →](README.pt-BR.md)**

---

## Why this exists

Most operational reporting problems are not calculation problems. The arithmetic behind OTIF,
fill rate and inventory accuracy is trivial; what decides whether the number is right is a set
of conventions that are almost never written down — whether the promise is an instant or a
date, whether a cancelled line belongs in the denominator, whether accuracy counts locations
or units.

This repository takes the position that those conventions belong in code, with tests, where
they can be argued about and audited. Each function exposes its choices as arguments, and where
a metric has more than one legitimate definition it returns all of them rather than picking
one silently.

## Modules

| Module | The question it answers | Docs |
| --- | --- | --- |
| `oplab.synth` | What data do I test against without exposing a real operation? | [`DISCLAIMER.md`](DISCLAIMER.md) |
| `oplab.kpi` | What is the service level, and how much of it is definition? | — |
| `oplab.spc` | Did the process change, and is it capable of the specification? | — |
| `oplab.slotting` | Which items deserve which policy, and what does the layout cost? | [README](src/oplab/slotting/README.md) |
| `oplab.variance` | Why did cost per order move, and who owns each part of it? | [README](src/oplab/variance/README.md) |
| `oplab.simulation` | Where is the constraint, and what does relieving it buy? | [README](src/oplab/simulation/README.md) |
| `oplab.routing` | What does a delivery cost, and which decisions can the model settle? | [README](src/oplab/routing/README.md) |
| `oplab.benchmark` | Which site is underperforming once size and geography are held constant? | [README](src/oplab/benchmark/README.md) |
| `oplab.forecast` | Does the forecast beat doing nothing, and how would you know? | [README](src/oplab/forecast/README.md) |
| `oplab.inventory` | What does a point of service level cost, and which lever buys it? | [README](src/oplab/inventory/README.md) |
| `oplab.mining` | What does the process do, as opposed to what the flowchart says? | [README](src/oplab/mining/README.md) |

Build sequence and selection rule in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Install

```bash
git clone https://github.com/fabiojmjr-oss/ferramentas-de-trabalho.git
cd ferramentas-de-trabalho
make install
make check
```

## Thirty seconds

```python
from oplab.kpi import service_sensitivity
from oplab.synth import generate_dataset

dataset = generate_dataset()  # reproducible from the seed alone
print(service_sensitivity(dataset.order_lines))  # one order book, four conventions
```

---

## Twelve things it demonstrates

### 1. A sixteen-point service spread with no change to the operation

`examples/01_service_definition.py` measures one order book — 290,918 lines over a year across
four sites — under four reporting conventions:

| Convention | OTIF | On time | In full | Lines in scope |
| --- | --- | --- | --- | --- |
| Undelivered lines counted as failures | 76.0% | 78.5% | 92.6% | 287,352 |
| Undelivered lines excluded *(default)* | 79.4% | 82.0% | 96.7% | 275,163 |
| One day of grace on the promise | 91.5% | 94.6% | 96.7% | 275,163 |
| Grace plus a 5% quantity tolerance | 91.6% | 94.6% | 96.7% | 275,163 |

Nothing about the operation differs between those rows. The 15.6-point spread is definition,
and it is usually wider than the improvement being negotiated in the room.

It also reorders the network. CD-SP is second on the strict convention and first once a day of
grace is allowed; CD-RJ goes the other way. A target set before the definition is settled is
not a target.

And on the same data, fill rate is 98.3% per unit, 96.7% per line, and 90.0% per order. All
three are correct. Quoting one without naming the basis is how two functions report different
service levels from the same extract and neither is wrong.

### 2. Control limits are not the thing a contaminated baseline breaks

It is widely repeated that fitting control limits to a period containing the disturbance
inflates them until the disturbance sits inside. On an X-bar and R chart that is false, and the
reason matters: the limit half-width is `A2 × R̄`, built from **within-subgroup** range, and a
shift in the process mean between subgroups leaves that range untouched.

Measured on a series with a 1.6σ shift injected at subgroup 43:

| | Limits from the stable phase | Limits from the whole series |
| --- | --- | --- |
| Centre line | 499.72 | 500.67 |
| Limit half-width | 2.930 | 2.728 |
| Signals in the stable phase | 0 | 14 |

The centre line moves by nearly five times as much as the half-width does, and it is dragged
towards the disturbed period — which manufactures fourteen signals in a period that was stable
and dates the change wrongly. A wrong date sends the investigation to the wrong shift, the
wrong batch and the wrong cause.

Limits do inflate when sigma is estimated from the standard deviation of the plotted points
instead of within-subgroup variation. That is a different error, and no function here commits
it.

### 3. A quarter of all signals produced by the wrong unit of analysis

A p chart of late deliveries at one site, same period, same chart type, differing only in what
counts as one trial:

| Unit of analysis | n per day | Days signalled | Overdispersion |
| --- | --- | --- | --- |
| Order line | 80–295 | 95 of 359 | 2.12 |
| Order | 25–89 | 4 of 359 | 1.01 |

Every line of an order rides the same vehicle, so one late truck produces a dozen correlated
failures. The binomial model behind the p chart assumes independent trials, observed variation
comes out at 2.12× what it predicts, and 26% of days signal — every one of them an artefact.
At order level the ratio is 1.01 and the signal rate falls to the expected false-alarm rate.

`oplab.spc.overdispersion_ratio` reports this, and it is worth checking before any signal is
investigated.

### 4. In slotting, the algorithm is a rounding error

Three ranking rules against the current random placement of 400 SKUs over 2,400 pick faces:

| Strategy | Mean distance per pick | Change |
| --- | --- | --- |
| By popularity (picks) | 17.11 m | −67.2% |
| By revenue | 17.34 m | −66.7% |
| By cube-per-order index | 18.00 m | −65.5% |
| Current (as received) | 52.11 m | — |

Every rule recovers about two thirds of the travel, and the spread between the best and the
worst rule is 1.7 points. **The decision worth money is whether to re-slot at all; the choice of
algorithm is a rounding error next to it** — the opposite of how slotting software is sold.

The cube-per-order index coming last is correct rather than a defect: with one face per SKU and
uniform capacity, every item consumes the same space, so cube carries no information about the
objective. Details, and the condition under which COI does win, in the
[module README](src/oplab/slotting/README.md).

The classification behind it earns its own finding: 18 of 87 class A items are not stable, and
they carry 19.1% of class A value. An ABC-only exercise hands all of them the policy designed
for predictable demand, and that is where the service failures come from.

### 5. The same cost movement, attributed two different ways

Cost per order rose 13.7% over the year on the bundled ledger. The decomposition is exact
either way, and the segmentation decides the answer:

| Effect | Segmented by site and order size | With channel added |
| --- | --- | --- |
| Rate | **+11.55 (98.2%)** | +9.20 (78.2%) |
| Mix | +0.21 (1.8%) | **+2.57 (21.8%)** |
| Total | +11.77 | +11.77 |

The movement is identical. The attribution is not. Omit the channel dimension and 98% of the
rise reads as operational; add it and a fifth is mix, because the direct-to-consumer share grew
and a home delivery costs nearly twice as much per stop as a store delivery.

**An omitted dimension does not disappear. It reappears inside the rate effect and is
attributed to whoever owns the rate** — and it is invisible, because the arithmetic reconciles
to under 1e-13 either way.

Two more things fall out of the same module. Total cost rose 20.7%, of which 30% was volume —
the same business got bigger, which is not a cost problem. And a per-unit metric cannot move
through volume at all: the bridge has exactly two terms by construction, so *"cost per order
rose but volume grew"* is not an explanation. Details, including the operating-leverage caveat
that qualifies it, in the [module README](src/oplab/variance/README.md).

### 6. The capacity spreadsheet is right, and still points at the wrong decision

Utilisation is conserved, so dividing mean work by mean capacity computes it correctly. The
simulated figures match the spreadsheet to within a point. And they decide nothing:

| Resource | Utilisation | Total waiting caused |
| --- | --- | --- |
| Picking (18 people) | 77.9% | **26,425 h** |
| Checking (5 stations) | 95.3% | 9,622 h |

**Utilisation ranks nothing.** Picking sits at a comfortable load and causes nearly three times
the waiting of the resource at 95%, because orders are released in two waves and every order
queues behind half a day's work the moment it arrives. That is a release policy, not a capacity
shortfall, and no utilisation figure separates the two.

What that does to the investment case, over six replications at 95% confidence:

| Scenario | Cycle time | Change | Distinguishable |
| --- | --- | --- | --- |
| **Release in 8 waves instead of 2** | 0.82 h | **−61.7%** | Yes |
| +2 checking stations | 1.68 h | −22.0% | Yes |
| Shift 8 h to 10 h | 2.02 h | −6.1% | Yes |
| +2 inbound doors | 2.15 h | 0.0% | **No** |
| +4 pickers | 2.17 h | +0.7% | **No** |

The free operational change recovers 2.8 times what the best paid option does. And four more
pickers — the intuitive move, aimed at the longest queue and the largest team — **cannot be
shown to do anything**: its interval overlaps the base, and it moved the wrong way. Without the
interval, that point estimate would have been reported as a result.

Details, including why an inbound investment provably cannot move an outbound metric in this
model, in the [module README](src/oplab/simulation/README.md).

### 7. A model that refuses to answer the question

Routing 74 deliveries from one depot, under four search budgets:

| Search budget | Vehicles | Cost per delivery |
| --- | --- | --- |
| 20 solutions | 7 | 44.08 |
| 120 | 5 | 36.88 |
| 300 | **5** | **36.11** |

Against a carrier quoting 42.00 per delivery, **the conclusion flips with how hard the solver
was allowed to look.** A cheap solve says buy the service; a thorough one says run the fleet.
The fleet size moves with the budget too, from seven vehicles to five — a tender decided on a
cheap solve would have bought two vans it did not need.

**So the model cannot settle make-or-buy at this price, and saying so is the output.** What it
does settle, by a margin no assumption threatens: the truck is the wrong vehicle for this
profile, at 68% more per delivery.

Two more results from the same module. Cost per delivery falls 27% when the same territory
carries four times the customers — **density, not distance, governs last-mile cost**, and the
curve is replicated with intervals because a single draw per point made it non-monotonic. And
the delivery windows cost 3.8% rather than the much larger premium a smaller budget reported,
because **an under-searched solve exaggerates the cost of every constraint it prices**.

Details, including why a travel-based lower bound on fleet size is not a bound at all, in the
[module README](src/oplab/routing/README.md).

### 8. A third of the cost gap between sites is postcodes

The four sites do not serve the same territory: 36% of one site's deliveries fall inside 10 km,
against 10% for another. Indirect standardisation asks what the rest of the network would spend
on each site's own distance profile:

| Site | Crude cost per order | Standardised | Ratio |
| --- | --- | --- | --- |
| CD-PE | 119.00 | 110.32 | 1.20 |
| CD-SP | 75.28 | 81.85 | 0.89 |

**CD-PE reads 58% more expensive than CD-SP crude, and 35% once the distance profile is held
constant** — 35% of the headline gap is geography rather than performance. The first number
sets a target nobody can hit; the second is arguable on its merits.

Two more results, both about the method rather than the network. Under 2,000 random weightings
of a four-metric scorecard, **the ranking between sites is a fact and the ranking between one
site's own months is theatre**: 2 of 4 sites can change rank against 12 of 12 months, where the
widest swing is ten places. Same tool, opposite verdicts, and you cannot tell which case you
are in without measuring it.

And DEA — the method everyone reaches for — needs at least twelve units for this measure set
and the network has four. The symptom is not that everyone comes out efficient; it is that the
**returns-to-scale choice moves the worst site by 27 points**, most of which is a penalty for
being small rather than a measure of how it is run.

Details in the [module README](src/oplab/benchmark/README.md).

---

### 9. The metric in the target cannot be computed on the data it is quoted for

MAPE is the accuracy metric in most planning targets because it reads as a percentage. On this
assortment it is defined on 58.4% of period-observations and on **1.0% of series without a
single gap** — division by a zero actual is undefined, and on intermittent demand zero is the
modal actual. Every reported MAPE is therefore an average over a filtered subset, and the filter
removes exactly the items that are hard to plan. It is asymmetric in the expensive direction too:
forecasting five against an actual of one scores 400%, forecasting zero scores 100%, so a model
tuned on MAPE learns to forecast low.

With a scale-free metric the comparison can be made, and it produces three results a business
case has to survive. Seven methods, rolling origin, against a one-line seasonal rule:

| Segment | Series | Best method | MASE | Beats the rule by | Wins on |
| --- | --- | --- | --- | --- | --- |
| Regular (≤50% empty periods) | 260 | SBA | 0.9417 | **0.8%** | 54% of series |
| Sparse (>50% empty periods) | 140 | TSB | **1.0890** | 6.5% | 61% of series |

**The headroom on the forecastable half is 0.8% and a coin-flip win rate** — a proposal
promising a large accuracy gain here is promising something the data does not contain. **On the
sparse half nothing reaches MASE < 1.0**, so no method beats that series' own naive benchmark
and the honest plan is an availability decision rather than a forecast. And **the leader changes
between the halves**: one model for the whole assortment is wrong on half of it by construction.

The fourth result is the one that costs money quietly. Scoring the same forecast per item-site
and at network total:

| Level | Series | MASE | Bias |
| --- | --- | --- | --- |
| Per SKU and site | 1,599 | 1.1605 | −0.0367 |
| Network total | 1 | 0.8480 | **−58.6667** |

Mean bias per series −0.036690 × 1,599 series = −58.6667, which is the bias of the total to the
last digit. **Aggregation shrinks error by 27% and leaves bias untouched**, because bias is
additive and error is not. A headline accuracy figure is almost always an aggregate's figure; a
bias too small to argue about on one item is the same bias, undiminished, on the warehouse.

Details in the [module README](src/oplab/forecast/README.md).

---

### 10. The service level in the contract is priced with a lead time nobody measured

Safety stock is sized against two variances: demand per period and replenishment lead time. The
first is estimated from data; the second is almost always taken from the supplier's quoted lead
time, which sets its variability to zero. Every supplier here delivers close to its quoted **mean**,
which is why the contract is never challenged — and says nothing about the spread:

| Supplier | Quoted | Realised mean | Realised sd | CV |
| --- | --- | --- | --- | --- |
| FORN-NACIONAL | 7.0 | 7.77 | 3.56 | **0.46** |
| FORN-CONTRATO | 12.0 | 12.17 | 1.58 | **0.13** |

Across 191 regular SKUs at a 95% cycle service level the requirement is **BRL 192,305**. Sized on
the quoted lead times it comes to BRL 121,522 — **the plan is missing 58% of the stock the service
level needs**, and the gap is invisible because both numbers come out of the same formula.

Three consequences follow, each of which reverses a common instinct.

**Which variance is the lever has a closed form.** Lead-time variability dominates exactly when
`CV_L² · L > CV_d²`, so there is one demand-CV threshold per supplier — 0.45, 0.45, 0.86, 1.28
here. Demand CV sits near 0.76 across the assortment, so lead time is the lever for two suppliers
and demand is the lever for the other two. The question "is it lead time or forecast accuracy?"
has no general answer, and two numbers you already have settle it per supplier.

**The shorter lead time can need the larger buffer.** FORN-CONTRATO takes 57% longer than
FORN-NACIONAL and needs **34% less** safety stock, because its lead time is 2.3 times tighter. The
honest qualification: total inventory does not invert, because pipeline stock scales with the mean.

**A 99% commitment sized as cycle service costs 82% more than the same commitment sized as fill
rate** — 328 units against 180. Neither is wrong; they count different things, and the conversion
needs the order quantity, which is why no fudge factor exists.

The deliverable is the curve, and it prices the argument rather than settling it by authority: a
point of cycle service costs BRL 34.76 at the bottom and BRL 394.28 at the top, eleven times as
much. **The top of the curve buys nothing measurable** — 99.0% to 99.5% costs 11% more capital and
delivers +0.07% of simulated cycle service, because what remains is the lead time's skewed tail.

And the cheapest point of service is not on the curve at all. Spending the *entire* forecasting
headroom from finding 9 releases 0.26% of the buffer. Capping one supplier's worst 5% of
deliveries releases 23.7% — **a factor of 92** — and the smaller policy still measures 98.9%
cycle service against a 99% promise.

Details in the [module README](src/oplab/inventory/README.md).

---

### 11. A conformance score of 97.8% on a process that 61% of cases follow

A value stream map drawn in a workshop is a set of estimates with a consensus attached. Derived
from a 38,735-event fulfilment log instead, it disagrees in four ways.

**Flow efficiency is 3.10%, and the number usually quoted is 6.53%.** Of 43.21 hours of mean lead
time, 40.39 are waiting and 2.82 are working — but only 1.34 of those working hours advance the
order. **53% of all working time is credit checks, quality checks and repacks**: work by any measure
of activity, waste by any measure of value. Counting it as value flatters the headline without
anybody lying, which is why the value-adding set is a required argument here with no default.

**The step with the longest touch time is not the step that holds the lead time.** Credit Hold takes
6.34 hours and holds 6.4% of all waiting. Ship takes three minutes and holds 35.7%, because it runs
3,911 times rather than 426. A workshop is right about which step feels slow and wrong about which
one costs; four handovers hold three quarters of the waiting, and nothing outside them is worth a
project.

**35 paths and 4 routes are different facts.** The documented path covers 61.1% of cases, which is
usually read as chaos — while four paths cover 80% of the volume, which means the process is
standardisable and the rest is exceptions. A variant count alone cannot tell those two situations
apart, so `variant_coverage` returns both.

**And the conformance metric is the finding, not the answer.** A containment test scores
**97.8%** — and `1 − 89/4000` is exactly that, where 89 is the number of cancelled cases. It rejects
nothing else, because it permits inserted steps, so it is blind to the **1,467 cases that reached
delivery by a route nobody documented**. A conformance score near one is evidence about the measure,
not about the process.

What the exceptions cost is the part a sponsor can act on:

| Group | Cases | Mean lead time | Flow efficiency |
| --- | --- | --- | --- |
| Follows the documented path | 2,444 | 30.94 h | 4.42% |
| Deviates | 1,556 | **62.49 h** | **2.07%** |

A deviating case takes twice as long *and* is proportionally worse, not simply longer.

Details in the [module README](src/oplab/mining/README.md).

---

### 12. The metric that ranks a forecast is not the metric that sizes its stock

Findings 9 and 10 each stand alone and were built separately. Connecting them exposes that neither
answers the question replenishment actually asks. `oplab.forecast` ranks forecasts on MASE;
`oplab.inventory` sized safety stock on the variability of demand. Both are defensible, and both
are answering a different question from *how much buffer does this forecast need?*

**MASE is built on absolute error, and a buffer has to cover the tail.** Scored both ways against a
forecast of the training mean:

| Model | MASE | MAE vs mean | Error sd vs mean |
| --- | --- | --- | --- |
| mean | 0.9415 | — | — |
| sba | 0.9417 | +2.8% | +0.8% |
| seasonal_naive | 0.9496 | +4.8% | **+24.9%** |

`seasonal_naive` reads **0.9% behind the leader on MASE and a quarter worse** on the quantity a
buffer is sized from — the error spread exposes 5.1 times what absolute error shows. Ranking on one
metric and then sizing stock on another is two decisions taken on two definitions of better.

**And a forecast of the training mean has the lowest error spread of the seven**, so on this data
nothing reduces the inventory buffer. The median ratio of forecast-error spread to demand spread is
1.0019; the forecast reduces the buffer on 47% of series and enlarges it on the rest. That reconciles
with finding 9 rather than contradicting it: MASE measures against the *naive* rule, where SBA won
by 0.8%, and inventory measures against the *mean*, where there is nothing to win.

Two consequences follow.

**A biased forecast is a cost no safety factor covers**, because raising `z` widens a window that
is in the wrong place. The worst under-forecast runs at −13.27 units a day and charges **103.2 units
of permanent stock, 32% on top of a 321-unit buffer.** And the average bias cannot size it: SBA's
mean bias is +0.005 — near zero — while it under-forecasts **52% of series.** Inventory is held per
item, so a centred average is not a centred forecast.

**A per-horizon error table can be a seasonality table wearing a horizon label.** Step 4's error
averages +8.08 and varies by only 1.03 across nine origins, against a systematic spread of −3.88 to
+8.08 between steps — the pattern reproduces at every origin, so it is the backtest's geometry, not
noise. Origins 28 periods apart with a season of 7 pin every horizon step to one weekday.
`horizon_profile` now returns a `phase_locked` flag. The square-root rule does not apply here
either: `sqrt(h)` describes a cumulative total, and the measured column runs 0.77 to 1.35 while
`sqrt(step)` runs 1.00 to 2.65.

Details in [`oplab.forecast`](src/oplab/forecast/README.md) and
[`oplab.inventory`](src/oplab/inventory/README.md).

---

## Examples

Twelve runnable scripts, each self-contained and each printing the reasoning behind its figures
rather than only the figures. Every one of them is executed by the test suite.

| Script | The question it works through |
| --- | --- |
| [`01_service_definition.py`](examples/01_service_definition.py) | How much of a service number is definition rather than performance |
| [`02_process_control.py`](examples/02_process_control.py) | Chart the process before judging it capable |
| [`03_network_diagnostic.py`](examples/03_network_diagnostic.py) | A one-page diagnostic of a four-site network |
| [`04_slotting.py`](examples/04_slotting.py) | What the current slotting costs, and how much is recoverable |
| [`05_cost_variance.py`](examples/05_cost_variance.py) | Why cost per order moved, and who owns each part of it |
| [`06_capacity_simulation.py`](examples/06_capacity_simulation.py) | Where the constraint is, and what relieving it buys |
| [`07_routing.py`](examples/07_routing.py) | What a delivery costs, and which decisions the model can settle |
| [`08_multi_site_benchmark.py`](examples/08_multi_site_benchmark.py) | Which site underperforms once size and geography are held constant |
| [`09_forecast_baseline.py`](examples/09_forecast_baseline.py) | Whether the forecast beats doing nothing, and how you would know |
| [`10_inventory_policy.py`](examples/10_inventory_policy.py) | What a point of service level costs, and which lever buys it |
| [`11_process_mining.py`](examples/11_process_mining.py) | What the process does, against what the flowchart says |
| [`12_forecast_error_to_stock.py`](examples/12_forecast_error_to_stock.py) | Whether forecasting reduces the stock you have to hold |

---

## Studies

`examples/` has one script per module. A **study** takes one decision and uses whichever modules
can price the parts of it, in the order the decision has to be taken rather than the order the
tools were built.

| Study | The decision it takes |
| --- | --- |
| [`01_where_to_spend.py`](studies/01_where_to_spend.py) | Four funding candidates, one budget: which are worth the money once each is priced on the same data? |
| [`02_what_changed.py`](studies/02_what_changed.py) | Three signals on a Monday slide: which are real, which are artefacts of measurement, and is any action justified? |
| [`03_audit_a_proposal.py`](studies/03_audit_a_proposal.py) | A vendor proposal with four workstreams and 18% on the cover: can any of it be reproduced on this operation's data? |
| [`04_commit_to_a_promise.py`](studies/04_commit_to_a_promise.py) | A customer wants 99% fill rate with penalties: what is actually being signed, and at what cost? |
| [`05_decide_before_you_know.py`](studies/05_decide_before_you_know.py) | A supplier failed and the expedite window shuts at noon: of four analyses, which could change what we do? |

Study 01 declines two of the four on measurement rather than on budget, narrows the two it funds,
and finds that the largest item is not on the list — 35% of the cost gap the brief opens with is
geography, and the service number itself moves 15.6 points on convention alone.

Study 02 asks the opposite kind of question and reaches an opposite kind of answer: **one
investigation, two corrections to the reporting, and no recovery plan.** Three of the four items on
the slide could not support an action, and one of them — the instinct to connect a service month to
a process shift — turns out to be untestable, because the process chart covers 2.5 days in June and
the service number covers twelve months. Two real signals, no relationship available.

Study 03 audits somebody else's claim instead of the operation's own, and **none of the four
workstreams it examines is simply true or simply false**: one is understated and needs no vendor,
one has roughly the right number attached to the wrong mechanism, one cannot be verified by the
class of model that produced it — this repository's routing module included — and one points in the
right direction at the wrong part of the problem. A flat rejection would have been wrong on three
lines out of four.

Study 04 is the only one where the operation makes a claim rather than examining one, and it finds
that **all four of the largest items in a service negotiation are wording decisions**: the same
order book delivers 90.03% or 98.26% depending on the fill-rate basis named, the same promise costs
82% more in stock depending on which service definition it means, and one policy sized for 99%
breaches a 99% cycle-service clause while clearing a 99% fill-rate clause. Its recommendation is to
write the definitions down rather than exploit them — a definitional advantage the counterparty has
not understood is a dispute with a delay on it.

Study 05 has a clock, which the other four do not, and the triage inverts the agenda. The decision
being argued about — which of 64 affected SKUs to air-freight — comes to **one SKU worth BRL 202**,
against BRL 41,893 of exposure it recovers half a percent of. The two factors that decide the
outcome are nobody's action item: the length of the outage (**26.96x**) and the demand estimate
(**8.04x**), while the air rate and customs fee the requested optimisation is built on move the
exposure by exactly nothing. So the highest-value act available at 07:00 is a phone call, which no
module here produces. The decision still ships, because blanket action only overtakes acceptance at
95 days of outage — outside every scenario on offer. **The value of information is bounded by the
value of the decision it informs**, and that bound is computable before the analysis.

See [`studies/README.md`](studies/README.md) for what the form has to do and what it cannot show.

---

## Design principles

**Validate at the boundary.** Every public KPI function checks its input against a contract in
`oplab.kpi.schemas` and reports every problem in one pass. A service number computed on a
malformed extract is worse than no number, because it is reported with the same confidence as
a correct one.

**Quantify the trade-off instead of asserting it.** The false-alarm rates of the Nelson rule
sets — 1 in 420 points for rule 1 alone, 1 in 70 for the practical set, 1 in 42 for all eight
— are measured in `tests/spc/test_rules.py::test_false_alarm_rates`, not quoted from memory.

**Return every legitimate definition.** Three fill rate bases, three inventory accuracy
definitions, Cpk beside Ppk. The gap between them is usually the finding.

**Report the result that contradicts the pitch.** The cube-per-order index loses to plain
popularity here, and the module says so and explains why, rather than quietly dropping the
comparison.

**Reconcile exactly or fail.** Variance effects sum to the movement with no residual, and
`waterfall()` raises rather than draw bars that miss the closing total. A decomposition with a
plug line is an allocation with a plug line, and the plug is where disagreements hide.

**Never report a stochastic point estimate as an answer.** Simulation results carry confidence
intervals, and a scenario whose interval overlaps the base is reported as indistinguishable
rather than as a small improvement.

**Refuse the questions the model cannot answer.** A routing cost carries the search time limit
it was produced under, and where a comparison falls inside that sensitivity the documented
answer is that the model does not decide it.

**Test against hand calculations.** Control chart limits are checked against `A2`, `D3` and
`D4` from the published tables on subgroups whose ranges are exact by construction. Service
metrics are checked against a six-line fixture whose expected values were derived by hand. A
metric tested only against its own implementation tests nothing.

**No real data, ever.** Every table comes from `oplab.synth` with a fixed seed. See
[`DISCLAIMER.md`](DISCLAIMER.md).

**The README is under test.** Every figure quoted above is asserted in
`tests/test_readme_claims.py`, and the example scripts are executed there too. Any change that
moves one of these numbers breaks the build rather than leaving the text quietly wrong.

## Limitations

Stated plainly, because the gaps matter as much as the coverage:

- The synthetic generator produces **plausible** data, not calibrated data. It is built to
  exercise the analytics and to make examples reproducible. No figure in this repository should
  be read as the performance of any real operation.
- Capability indices assume approximate normality. `oplab.spc.capability` reports skewness and
  kurtosis and warns when the assumption is doubtful, but it does not implement non-normal
  capability methods. Logistics durations are usually right skewed, so this matters more here
  than in manufacturing.
- Slotting measures distance-weighted picks, not routes, and assumes one location per SKU with
  no congestion and no move cost. Every one of those assumptions overstates the benefit; see
  the [module README](src/oplab/slotting/README.md) for the full list and for why the
  percentage change is quotable and the metres are not.
- Attribute charts assume independent trials. `overdispersion_ratio` detects the violation but
  the library does not yet offer a Laney p′ chart or another overdispersion-robust alternative.
- Variance decomposition is only as good as its segmentation — mix is invisible along a
  dimension you do not segment by — and it does not split fixed from variable cost, so
  operating leverage hides inside the rate effect. It also compares two periods with no test of
  whether the movement exceeds normal variation; chart it with `oplab.spc` first.
- The capacity simulation keeps inbound and outbound labour in separate pools, holds a resource
  across the shift break, and leaves loading, replenishment and travel distance out of scope.
  See the [module README](src/oplab/simulation/README.md); the first assumption in particular
  understates the value of cross-deploying people.
- Routing uses straight-line distance scaled by an assumed circuity factor and a single average
  speed, one order per stop, one vehicle type per solve, one deterministic day, and no proof of
  optimality. The scenario *ranking* survives all of that; the absolute costs do not, and the
  ranking itself can invert at a small search budget. See the
  [module README](src/oplab/routing/README.md).
- Benchmarking can only remove mix along a dimension you stratify by, adjusts without
  explaining, and its DEA is deterministic with no error bars. See the
  [module README](src/oplab/benchmark/README.md).
- The forecasting module is a measurement harness with baselines, not a model library: seven
  one-line rules, no ETS or ARIMA, no exogenous regressors and no prediction intervals. A
  serious model belongs in the same harness, compared on the same table. See the
  [module README](src/oplab/forecast/README.md).
- The inventory lab is single-echelon and single-supplier per item, resamples demand without
  autocorrelation, assumes lost sales rather than backorders, and does not size intermittent
  items at all. Its simulation needs a warm-up, and the warm-up is the finding: without one
  the same policy measured between 89.3% and 97.3% cycle service on identical data. See the
  [module README](src/oplab/inventory/README.md).
- Process mining here discovers a directly-follows graph, which records what followed what and
  cannot express a choice, a parallel split or a loop boundary; its conformance check is a
  subsequence test rather than an alignment, and finding 11 is partly a statement about that
  limit. See the [module README](src/oplab/mining/README.md).

## Development

```bash
make install    # editable install with the dev tools
make check      # lint, format, types and the fast suite - what gates a push
make check-all  # the above plus every documented figure re-derived
make claims     # re-derive every number quoted in a README
```

**566 tests, 96% statement coverage, split by cost.** 541 of them run in about twenty-five
seconds — under a minute for the whole `make check` sequence with the linters, the type check and
coverage — and that is what a push is gated on. The remaining 25 re-solve the routing problems,
re-replicate the simulations, re-run the forecast backtests and the inventory policy runs, and
execute all twelve examples and all five studies to verify every figure quoted above; they take
about eleven minutes (10m55s with study 05 added, against 10m18s and 10m19s before it).
They do not depend on the interpreter version, so CI runs the fast gate across Python 3.10 and 3.12
and the figure verification once.

That figure doubled in wave 8, and not because a study was added: pinning the routing search-budget
sweep costs eight vehicle-routing solves, about ninety seconds, on every run. Buying the correction
of a published claim cost that much CI time permanently, which is the right trade against leaving
the wrong prose standing, but it is a trade rather than a free improvement.

`make check` exists because the alternative failed twice: running the linter but forgetting the
formatter, and running a locally installed tool older than the one CI installs. Both turned a
correct change into a red build, so the linters are pinned to a compatible release and the
whole sequence lives in one target.

## License

MIT. See [`LICENSE`](LICENSE).
