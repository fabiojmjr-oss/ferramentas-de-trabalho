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
| 8 | Process mining | `oplab.mining` | What does the process actually do, as opposed to the flowchart? | 4 — done |
| 9 | Forecast baseline | `oplab.forecast` | Does this forecast beat seasonal naive, measured honestly? | 4 — done |
| 10 | Inventory policy lab | `oplab.inventory` | What does each point of service level cost in working capital? | 4 — done |

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

Wave 3 is closed. Wave 4 is closed: the generator and all ten tools are built. Wave 5 deepens
rather than adds - the tool list is complete, and what is left is the connections between the
tools, which is where the mistakes were hiding.

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

**Process mining** *(complete — [module README](../src/oplab/mining/README.md))*. From an event log
to a discovered process map, cycle time per transition, rework loops, and lead time against
value-added time — a value stream map generated from data rather than from sticky notes.

It needed a second new generator table, for a reason worth recording. A discovered map is only
worth drawing if the log contains paths nobody documented, and none of the existing tables has any:
`order_lines` and `receipts` are milestone columns in a fixed order, so every case follows the same
sequence and the discovered map is a picture of the flowchart. `generate_order_events` produces the
branches instead — credit holds, shortages that return to allocation, quality checks that fail and
loop, address corrections, failed deliveries — with explicit probabilities, so the discovery can be
checked against what was generated. It also records a start *and* a completion per event, because
without both, work cannot be separated from wait and flow efficiency is not computable. Like the
purchase orders, it is appended at the end of the generator and changed no figure above it.

Four results, one of them about a metric rather than about the process:

- **Flow efficiency is 3.10% where the usually quoted busy share is 6.53%.** The gap is 1.48 hours
  of credit checks, quality checks and repacks: 53% of all working time exists only because
  something went wrong earlier.
- **The step with the longest touch time holds 6.4% of the waiting; a three-minute step holds
  35.7%**, because it runs 3,911 times rather than 426. A workshop ranks by how slow a step feels
  and the log ranks by hours contributed.
- **35 paths and 4 routes are different facts.** The documented path covers 61.1% of cases, and four
  paths cover 80% of the volume, so the process is standardisable and the tail is exceptions — a
  distinction a variant count on its own cannot make.
- **A containment conformance score reads 97.8% on a process 61.1% of cases follow**, and
  `1 − 89/4000` is exactly that figure, where 89 is the cancellations. The measure permits inserted
  steps, so it is blind to 1,467 cases that finished by an undocumented route. That is a statement
  about the measure this module uses, and it is in the module docstring rather than a footnote.

The deviating cases take 2.0 times the lead time of conforming ones *and* have worse flow
efficiency, which is the business case: a variant count says the process is not standard and invites
an argument about whether that matters; this says what the non-standard cases cost.

**Forecast baseline** *(complete — [module README](../src/oplab/forecast/README.md))*.
Rolling-origin backtesting against naive, seasonal naive, moving average, drift, Croston, SBA and
TSB, with scale-free error metrics — MASE and RMSSE, not MAPE. The position being taken is that a
forecast project without an honest baseline is unmeasurable, and most of them do not have one.

Two deliberate departures from the plan. **ETS, ARIMA and gradient boosting were dropped, and
`statsforecast` with them.** The measured headroom on the forecastable half of this assortment is
0.8% over a one-line rule with a 54% per-series win rate, so adding a heavier model would have
produced a second number inside the same noise band and implied a precision the data does not
support. What the module ships instead is the harness: any model, including those three, can be
passed into `backtest_panel` and appear on the same table. Keeping the dependency surface at
numpy and pandas was a side benefit, not the reason.

Three findings came out of building it, none of them planned. **One year of weekly data cannot
support an annual seasonal baseline and nothing warns you** — `seasonal_naive` silently falls
back to `naive` when the history is shorter than a season and every scaled metric returns `nan`,
which is how a report ends up with a number under a heading that is false. That produced
`season_feasibility()`, which is the check that belongs before any model is fitted. **The leader
changes between the regular and sparse segments** (SBA and TSB respectively), so the best model
is a property of the segment rather than of the assortment. And **bias is additive under
aggregation where error is not**: mean bias per series times 1,599 series equals the bias of the
network total to the last digit, while MASE improves 27% at total level. That last one is the
result with the largest inventory consequence and it is the one least often stated.

**Inventory policy lab** *(complete — [module README](../src/oplab/inventory/README.md))*.
Safety stock from demand *and* lead-time variability, `(s,Q)` against `(R,S)`, Monte Carlo
simulation of stockout and fill rate, and the working-capital-per-service-point curve as the
deliverable.

It needed a new table in the generator. Inbound receipts describe dock-to-stock, which is a
warehouse interval; an inventory policy needs the supplier lead time, from order placed to stock
receivable, and the two are routinely confused because the warehouse owns the data for the first
and nobody owns the data for the second. `generate_purchase_orders` is appended at the end of the
generator for the same reason the layout is, so every table and every published figure above it
keeps reproducing byte for byte. Its supplier profiles hold one property deliberately: mean lead
time and lead-time variability are uncorrelated, because if short lead times came bundled with low
variability every comparison would rank suppliers the same way on either property and the whole
point would be unobservable.

Four results, plus one that is a limitation rather than a result:

- **Sizing on the quoted lead time misses 58% of the stock the service level needs** (BRL 192,305
  against BRL 121,522 over 191 SKUs). The gap is invisible in review because both figures come
  out of the same formula.
- **Which variance is the lever has a closed form**: lead-time variability dominates when
  `CV_L² · L > CV_d²`, so there is one demand-CV threshold per supplier. It is the lever for two
  of these four suppliers and not for the other two, so the usual blanket claim in either
  direction is wrong half the time.
- **The shorter lead time can need the larger buffer** — 57% longer and 34% less safety stock —
  while total inventory does not invert, because pipeline stock scales with the mean.
- **A 99% commitment sized as cycle service costs 82% more than the same commitment sized as fill
  rate**, and the cheapest point of service is not on the curve at all: the entire forecasting
  headroom from tool 9 releases 0.26% of the buffer while capping one supplier's worst 5% of
  deliveries releases 23.7%.

The limitation is the one worth recording. The first simulation results were an artefact: on a
one-year horizon the same policy on the same data measured between 89.3% and 97.3% cycle service
depending only on whether it opened full, at the reorder point, or empty. A horizon that short
contains few replenishment cycles, so the opening assumption is a large share of the sample. A
warm-up of two cycles collapses the spread to 1.2 points. It was believable in both directions,
which is what made it dangerous, so `warmup` defaults to a computed value rather than to zero and
the range is asserted in the claim tests.


## Wave 5 — connections

The tool count stops at ten on purpose. What wave 5 does instead is join modules that were built
separately and check whether they agree, which turned out to be the most productive thing in the
project so far: the first connection attempted found an error in work that had already shipped.

**Forecast error to safety stock** *(complete — [`oplab.forecast`](../src/oplab/forecast/README.md),
[`oplab.inventory`](../src/oplab/inventory/README.md))*.

`oplab.forecast` ranked forecasts on MASE. `oplab.inventory` sized safety stock on the standard
deviation of demand. Each is defensible alone and **together they are incoherent**: if replenishment
is driven by a forecast, the quantity to buffer is the error of that forecast, and sizing on demand
variability silently assumes the forecast is the long-run mean. That was a real defect in shipped
code, found by asking the two modules the same question rather than by reading either of them.

The fix added `error_profile`, `horizon_profile`, `prediction_interval` and `interval_coverage` to
`oplab.forecast`, and `safety_stock_from_forecast_error` and `compare_sizing_bases` to
`oplab.inventory`. Four results came out of it:

- **The metric that ranks a forecast is not the metric that sizes its stock.** `seasonal_naive`
  reads 0.9% behind the leader on MASE and 24.9% worse on error spread — the quantity a buffer is
  sized from. MASE is built on absolute error and a buffer has to cover the tail, so the spread
  exposes 5.1 times what absolute error shows.
- **A forecast of the training mean has the lowest error spread of the seven**, so on this data
  nothing reduces the inventory buffer. Median ratio of forecast-error spread to demand spread:
  1.0019. This reconciles with wave 4 rather than contradicting it — MASE measures against the
  naive rule, inventory measures against the mean.
- **A biased forecast is a cost no safety factor covers**, at 103.2 units of permanent stock (32%
  of the buffer) on the worst under-forecast — and the average bias cannot size it, because SBA's
  near-zero mean bias coexists with under-forecasting 52% of series.
- **A per-horizon error table is a seasonality table when origins are a whole number of seasons
  apart.** Step 4's error averages +8.08 and varies by 1.03 across nine origins: the pattern
  reproduces every time, so it is geometry rather than noise. `horizon_profile` now returns a
  `phase_locked` flag. The square-root rule also does not apply to a per-period error, only to a
  cumulative one — which is why the sizing multiplies error *variance* by the protection interval
  instead of reading a growth rate off that table.

Two of my own hypotheses about that last finding were wrong before the third was right, and both
are recorded in the module README rather than tidied away: a `step=25` run failed to disprove the
phase-lock explanation, and a shared-demand-shock explanation was ruled out by reading the
generator. What settled it was measuring the mean error per origin and per step and seeing the
between-origin spread come out an order of magnitude below the between-step spread.

**An integrated study** *(complete — [`studies/README.md`](../studies/README.md))*. A new artefact
type, and the directory is separate from `examples/` because the form is different. An example has
one script per module, each answering the question that module was built for. A study takes **one
decision** and uses whichever modules can price the parts of it, in the order the decision has to be
taken rather than the order the tools were built.

`studies/01_where_to_spend.py` takes a brief as it arrives — *CD-PE has the worst service and the
highest cost per order, fix it* — with four funding candidates, each with a sponsor. It checks the
brief before pricing anything, prices all four on the same data, and reaches verdicts:

- **Re-slot the pick face: fund**, but decline the algorithm study the sponsor asked for. The best
  rule recovers 70% of the travel at CD-PE and the three rules sit 2.6 points apart.
- **Buy a forecasting system: decline.** Of eight methods scored the lowest error spread belongs to
  a forecast of the training mean, which is what the inventory formula already assumes.
- **Standardise the order process: fund, scoped** to the four handovers holding 75% of the waiting,
  rather than to 35 process variants.
- **Hold more safety stock: decline as asked, act on the cause.** The current plan is already 37%
  short because it sizes on the contract, and capping one supplier's worst 5% of deliveries releases
  16% of the assortment's buffer while improving service.

The result worth the form: **the largest item is not on the list of candidates.** 35% of the cost
gap the brief opens with is geography, and the service number moves 15.6 points on convention alone.
Neither is fixed by spending money, and neither would have been found by pricing the candidates
first. The study ends by naming the one measurement that would overturn its own conclusion, which is
the difference between a conclusion and a position.

**Wave 5 is closed.**

## Wave 6 — the other question

Wave 5 ended with a study that prices candidates. This wave adds its opposite, because a library
that only supports investment cases supports half the job.

**A diagnostic study** *(complete — [`studies/02_what_changed.py`](../studies/02_what_changed.py))*.
Three signals on a Monday slide: October OTIF the worst month of the year, December the best, and
the process measurement out of control. The room wants three actions. The study establishes which
signals are real, which are artefacts of measurement, and whether any two of them are about the
same thing.

The output is **one investigation, two corrections to the reporting, and no recovery plan** — a
conclusion that has to be held to a higher standard than one recommending spend, because the cost
of being wrong about *not* acting lands on nobody's budget. Each refusal rests on a figure:

- **October is a real signal on a chart that cannot be quoted as computed.** The p-chart flags it
  at 5.04 sigma, and the overdispersion ratio is 1.787 — lines within an order are not independent
  trials, so the correct sigma is 1.34 times wider and the adjusted signal is 3.77. Still a signal.
  What settles it is scale: 1.88 points of month-to-month range against **15.57 points of
  definitional spread**, 8.3 times as much. A recovery plan for a move smaller than the measurement
  convention is tampering.
- **December's recovery is censoring.** It is the only month with unresolved lines — 1,636 of them,
  6.3% of the month — excluded from the denominator under the standard policy. The month with the
  most lines that have no outcome cannot also be the best month.
- **The process shift is real, and only visible from a clean baseline.** Subgroup 43 at 3.96 sigma,
  with a quiet range chart, so the centre moved and the spread did not. Limits estimated from all
  60 subgroups instead give 14 signals in the stable first 40 against 2.
- **The two signals cannot be related, and this is the check nobody runs.** The process chart
  covers 60 hourly subgroups across 2.5 days in June; the service number is monthly across a year.
  October is not inside the chart's window at all, so any story connecting them is unfalsifiable by
  construction rather than merely weak.

The last one is the finding that justifies building the study. It was not the finding expected: the
design assumed the process shift would sit near the service month and the work would be untangling
a plausible causal story. The windows turned out not to overlap, which is a better result and a
more common failure — two signals reported on the same slide that share no observation period.

**Wave 6 is closed.**

## Wave 7 — reasoning about somebody else's claim

Studies 01 and 02 both reason about the operation's own material: one prices candidates the
operation put forward, the other sifts signals its own reporting produced. Neither covers the case
that arrives most often in practice — a proposal from outside, with a number on the cover.

**An audit study** *(complete —
[`studies/03_audit_a_proposal.py`](../studies/03_audit_a_proposal.py))*. A vendor proposal with
four workstreams and an 18% saving claimed. The reasoning is adversarial reproduction: for each
claim, can it be recovered from this operation's data, and what would have to be true for it to
hold?

**None of the four claims is simply true and none is simply false**, which is why the form earns
its place — a flat rejection would have been wrong on three lines out of four, and accepting the
deck would have been wrong on all four:

- **Slotting, 30% of pick travel: understated and self-serviceable.** 70% is available at CD-PE
  and the three ranking rules sit 2.6 points apart, so the prize belongs to re-slotting at all
  rather than to the optimiser. The vendor undersells the benefit and oversells their share of it.
- **Forecasting, 20% of inventory: roughly the right number, attached to the wrong mechanism.**
  The lowest error spread of the models scored belongs to a forecast of the training mean, and the
  ratio of forecast-error spread to demand spread is 1.0019 — there is nothing to buy. About 16% of
  the buffer does exist, released by capping one supplier's worst 5% of deliveries. Agreeing the
  number and disagreeing about the cause is the worst available outcome, because the programme gets
  paid for a result it did not produce and the real lever stays unpulled.
- **Routing, 15% of freight: unverifiable by the class of model that produced it.** Baselining on a
  cheap solve and reporting a thorough one is a saving of **18.1%** from changing nothing about the
  operation, and the fleet size moves from seven vehicles to five. That exceeds the claim it is
  asked to verify.
- **Automation, 25% of cycle time: right direction, wrong part.** Working time is 6.5% of the lead
  time, so automating every step to zero cuts less than a third of the claim. The 25% is in the
  40.4 hours of waiting, three quarters of which sits after four handovers — different work, and
  different suppliers.

The third verdict is the one that matters for the credibility of the other three. **This
repository's routing module is the same class of model as the one behind the vendor's number, and is
subject to the same artefact.** The refusal is therefore not an accusation, and an audit that finds
nothing wrong with its own method is not an audit. What can be asked for instead is a measurable
commitment on an agreed basket of days, baselined on the operation's own routes, with both sides'
search budget on the record.

**Wave 7 is closed.** The three studies now cover the three shapes a decision takes: pricing your
own candidates, sifting your own signals, and reproducing somebody else's claim.

## Wave 8 — reasoning about a claim you will be held to

The first three studies all examine a claim that already exists. None of them covers the position
an operation is actually in when a contract is on the table: **making** the claim, with penalties
attached. Being wrong there is not an analytical error, it is a penalty payment.

**A commitment study** *(complete —
[`studies/04_commit_to_a_promise.py`](../studies/04_commit_to_a_promise.py))*. A customer asks for
99% fill rate, a 24-hour delivery window and penalties for breach. Sign it, or counter?

**The four largest items on the table are wording decisions, not operational ones.** That is the
finding, and it is uncomfortable, because a year of operational programmes in this repository moves
service by less than the definitional spread does for free:

- **Which 99%?** The same order book delivers 98.26% on a unit basis, 96.71% on a line basis and
  90.03% on an order basis — 8.2 points between defensible readings of identical words. The
  delivery half is worse: the OTIF conventions span 15.6 points with no change to the operation. A
  clause that says "99% fill rate, 24-hour window" and nothing else has not specified anything; it
  has deferred the specification to whoever writes the first report, and that is settled later by
  whoever is losing.
- **The same promise, priced two ways.** Read as cycle service, 99% costs 327.7 units and BRL
  1,838 of safety stock; read as fill rate, 180.2 units and BRL 1,011 — **+81.8% of working
  capital for the same number and the same word.** The customer almost certainly means fill rate,
  and fill rate is the cheaper commitment; volunteering the expensive reading is a self-inflicted
  cost that also weakens the negotiation on price.
- **Sizing for a level is not delivering it.** A policy sized for 99% cycle service is measured at
  98.55% — 0.45 points short, and a penalty clause pays on what was delivered. The same policy
  delivers 99.50% on fill rate, clearing the identical number with 0.50 points to spare. One
  policy, two contracts, one breach and one comfortable margin. And the last half-point is the
  expensive one: 394.28 of capital per point at 99.5% against 107.70 at 98%.
- **What the window costs, and how sure we are.** 3.79% of freight at a search budget allowed to
  look properly — but see below.

**The window check falsified a claim this repository had already published.**
`src/oplab/routing/README.md` said an under-searched solve *exaggerates* the cost of every
constraint it prices, at "nearly three times the premium and one extra van". Sweeping the budget
gives −1.70% at 20 solutions, +2.89% at 60, +4.66% at 120 and +3.79% at 300: not three times
anything, not monotone, and negative at the cheap end. A negative premium is impossible between two
optima — the open problem is the constrained one with a restriction removed, so its optimum cannot
be higher — which makes the negative row proof that at least one solve is nowhere near optimal.
**The premium is a difference between two errors, not a measurement with a bias**, and until both
sides are searched properly it has no reliable sign. Both language sections of the routing README
were corrected and the sweep is now pinned in `test_routing_tables`.

That is the argument for the form. The wrong claim survived a wave of review inside a module
README; it did not survive the first study that had to quote it to a customer.

**The recommendation is to write the definitions down rather than to exploit them.** A definitional
advantage the counterparty has not understood is a dispute with a delay on it, and the delay ends
at the first penalty invoice with the relationship as collateral. The asymmetry is also symmetric:
the customer can find a stricter reading as easily as we can find a kinder one, and the party who
wrote nothing down has no answer either way.

**Wave 8 is closed.** The four studies now cover the four positions a decision is taken from:
pricing your own candidates, sifting your own signals, reproducing somebody else's claim, and
making a claim you will be held to.

## Wave 9 — reasoning when the clock runs out first

The four studies before this one share an assumption that is invisible until it is named: that the
analysis can be finished before the decision is taken. That assumption is what makes them studies
rather than Mondays.

**A triage study** *(complete —
[`studies/05_decide_before_you_know.py`](../studies/05_decide_before_you_know.py))*. A supplier's
inbound failed over the weekend; 64 SKUs are affected; the airline's cut-off is noon. Four analyses
are on the table and there is time for one. The reasoning is **boundary first, measurement
second**: for each question, not "what is the answer?" but "what would the answer have to be to
change what I do?"

**The triage inverts the agenda.**

- **The decision being argued about is worth BRL 202.** Air freight is charged by weight and the
  shortfall it avoids is worth a margin on cost, so eligibility is a pure value-density test —
  `margin x unit_cost > air_rate x weight` — which demand does not enter. Value density across the
  affected range spans 1.76 to 250.29 BRL/kg, a factor of 142, and 3 of 64 SKUs clear the 62.5
  BRL/kg threshold. Of those, one clears the fixed customs cost per line. Against BRL 41,893 of
  exposure, the whole action space recovers **0.48%**. Blanket action costs BRL 311,853, of which
  BRL 76,800 is customs before a kilo flies.
- **The two factors that decide the outcome are nobody's action item.** Moving one factor at a
  time: the length of the outage swings exposure **26.96x**, the demand estimate **8.04x**, gross
  margin 2.40x, quoted-versus-realised lead time 1.14x, lead-time variability 1.01x. The air rate
  and the customs fee — the two numbers the requested optimisation is built on — move it by
  **exactly nothing**, because they price the response and not the loss. Sweeping the air rate
  reorders the eligible list from 16 SKUs to 2 while leaving the exposure bit-identical.
- **The highest-value act available at 07:00 is a phone call**, and no module in this repository
  produces it. That is the honest limitation of a toolkit rather than a gap for a better model to
  fill.
- **The decision ships without the number that dominates it**, because the unknown never reaches
  the boundary: blanket action overtakes acceptance only at **95 days** of outage — solved by
  search rather than read off the table — which is outside every scenario on offer. The reversal
  trigger is written down in advance, so reversing is a rule rather than a second argument.

**Two of the study's own predictions were wrong**, and both are recorded in the script where they
failed rather than quietly removed:

- I expected the demand forecast to be decision-irrelevant, with an argument: demand cancels out of
  the density test, so it cannot change which SKUs are eligible. The argument is correct and the
  conclusion drawn from it was false. Demand cancels from the *selection* and dominates the
  *exposure*. Selection was the question I had solved, so it was the question I let stand in for
  the decision — which is the specific failure mode this study is about.
- I expected the realised lead time to be the cheap decisive measurement. FORN-IMPORT quotes 30
  days, realises 31.68, with skew 5.58 and a p95 of 36.88 — exactly the tail this repository was
  built to find. It moves the exposure by 1.14x. The tail is real and it is not what is at stake
  once a shipment has already failed: 21 days of delay swamp 1.7 days of optimism in a quote.

The framework the study ends on is **the value of information is bounded by the value of the
decision it informs**, computable before the analysis from the action space alone. At any
defensible loaded rate, the half-day optimisation everyone wanted costs more than the BRL 202
decision it improves — and nobody checked the cap before assigning the work.

**Wave 9 is closed.** The five studies now cover four positions a decision is reasoned from and,
in this one, the constraint that decides which reasoning is affordable at all.

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
- **One branch and one pull request per wave**, titled for the decision it delivers rather than for
  its first commit. The pull request states what was built, what it demonstrates, how it is
  verified and what is deliberately out of scope — the history is part of what the repository
  shows, not bookkeeping around it.
- Every figure quoted in any README is asserted in `tests/test_readme_claims.py`. A change that
  moves a published number breaks the build instead of leaving the text quietly wrong.
