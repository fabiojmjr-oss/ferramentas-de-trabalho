# oplab.routing — vehicle routing with time windows

**EN** · [Português](#português)

Prices a day of deliveries, and answers three questions about it: what density is worth, what
the delivery windows cost, and whether to run the fleet or buy the service.

Built on OR-Tools. Install the extra: `pip install -e ".[routing]"`.

## The finding this module was built to produce

It is a refusal. Routing 74 deliveries from one depot:

| Option | Vehicles | Cost per delivery |
| --- | --- | --- |
| Own van | 5 | **38.50** |
| Third-party carrier at 42.00 | — | 42.00 |
| Own truck | 5 | 64.21 |

The van beats the carrier by 3.50 per delivery, an 8.3% advantage — at the search budget used
for that table. Give the solver a cheaper budget and the van costs 53.29, and the carrier wins
comfortably.

**The conclusion flips with how hard the solver was allowed to look.** A cheap solve says buy
the service; a thorough one says run the fleet. The make-or-buy gap is a quarter of the spread
the search budget alone produces, so **this model does not settle make-or-buy at this price**,
and saying so is the output. Reporting an 8% advantage as a finding — from a heuristic that
never proved optimality, on straight-line distances scaled by an assumed circuity factor, for
one Wednesday in June — would be a number with a decision attached to it and nothing
underneath.

What the model does settle, by a margin no assumption threatens: the truck is the wrong vehicle
for this profile, at 67% more per delivery.

## "Optimal" is not what comes back

| Search budget | Vehicles | Cost per delivery |
| --- | --- | --- |
| 20 solutions | 8 | 53.29 |
| 60 | 8 | 50.76 |
| 120 | 6 | 42.17 |
| 300 | **5** | **38.50** |

OR-Tools runs a construction heuristic and then local search until its budget runs out. It does
not prove optimality, and for a problem of any size the answer is not optimal. Note what
changed down the rows: not only the cost, by 27.7%, but **the fleet size**, from eight vehicles
to five. A tender decided on a cheap solve would have bought three vans it did not need.

**The budget is a solution count, not a stopwatch.** A wall-clock limit makes the answer depend
on the machine and on what else that machine is doing: the same problem under CPU contention
explores less and returns a worse — and different — plan. That is unacceptable for a figure
going into a tender, and it surfaced here as a test that passed alone and failed inside the
full suite. Counting accepted solutions instead makes the result reproducible anywhere; a
wall-clock cap remains only so a pathological instance cannot hang, and a solution that hits it
reports `hit_time_cap`.

## Density, not distance

| Stops in the territory | Km per delivery | Cost per delivery |
| --- | --- | --- |
| 18 | 15.82 | 53.22 |
| 37 | 16.01 | 48.21 |
| 74 | 12.54 | **38.50** |

Same territory throughout — the stops are a random subsample of the same day, so the area never
changes, only how many customers sit in it. Four times the density is **28% lower cost per
delivery**.

Nothing about the distances changed. Drop density governs cost per delivery in last-mile
distribution far more than distance does, which is why a growing territory can get cheaper per
drop while a shrinking one gets more expensive without any rate moving — and why a route tender
priced off average distance misprices both.

## What the windows cost, and a correction

| Case | Vehicles | Cost per delivery |
| --- | --- | --- |
| Windows enforced | 5 | 38.50 |
| Windows opened to the full day | 5 | 37.68 |

The commercial promise costs **2.2%, and no extra vehicle**.

That figure is a correction, and the correction is the more useful finding. Under a smaller
search budget the same comparison came out at 8.8% and one extra van. The reason is not noise:
**an under-searched solve exaggerates the cost of every constraint it prices**, because the
heuristic struggles more with the constrained problem than with the open one, so the penalty it
reports is partly its own failure to find the good constrained plan. Anyone pricing what a
service promise costs by routing with and without it should check that both sides had enough
budget to be solved properly.

What survives the correction is the mechanism. Windows fragment routes in a way capacity does
not — a van with two thirds of its payload free still has to return to the depot, because it
cannot reach the next window in time — and on this day the payload bound is three vehicles
against the five actually used, so capacity is nowhere near binding.

## Diagnose before you blame the solver

An infeasible solve says nothing about why, and the reason is usually not the routing. `diagnose`
finds stops that no route can serve — a round trip longer than the driver shift, a window that
closes before a vehicle can arrive, a consignment heavier than the van. One such stop makes the
whole day infeasible however good the algorithm is, and fixing it is a renegotiation rather than
an optimisation.

`fleet_lower_bounds` reports only the two bounds that are **valid**: payload has to be carried
and time at the door has to be spent, and neither can be shared between vehicles. There is
deliberately no travel-based bound, and the omission is a correction. Summing the outbound leg
to every stop and dividing by the shift looks like a bound and is not one — it assumes each stop
needs its own round trip, when a route visiting twelve stops drives the radius once and
amortises it. That figure came out at seven vehicles for a day the solver routes with five: a
"lower bound" above the achieved solution. The amount by which routing beats it *is* the density
effect above.

## Cost, not distance, is the objective

Fixed cost for each vehicle actually used, plus a rate per kilometre. Distance and vehicle count
are reported as outcomes, not optimised as targets, because minimising either answers a
different question — and a tender evaluated on kilometres can select the more expensive bid. On
the four-stop test case the distinction is exact: four separate round trips cost 560, one
vehicle going round them costs 225, and a solver given only a distance objective is indifferent
between using one vehicle and four.

## Usage

```python
from oplab.routing import one_day, diagnose, solve, density_curve, window_cost, VAN
from oplab.synth import generate_dataset

problem = one_day(generate_dataset().deliveries, "CD-SP", "2025-06-11")
print(problem.profile())
print(diagnose(problem, VAN))  # before solving

solution = solve(problem, VAN, time_limit_s=10)
print(solution.headline())  # carries the time limit
print(density_curve(problem, VAN))
print(window_cost(problem, VAN))
```

Full walkthrough: [`examples/07_routing.py`](../../../examples/07_routing.py).

## Assumptions and limitations

- **Road distance is straight-line distance times 1.35.** Real distance comes from a routing
  engine over a real network. The factor is in the range commonly quoted for urban networks and
  it is an assumption, not a measurement.
- **One average speed** stands in for a network where an urban arc and a motorway arc differ by
  a factor of three. This makes the *ranking* of scenarios reliable — every scenario pays the
  same optimistic travel times — and the absolute hours unreliable.
- **One order is one stop.** No consolidation of several orders going to the same customer,
  which would lower cost per delivery.
- **One vehicle type per solve.** A mixed fleet chosen jointly is a different and harder
  problem; `compare_fleets` prices homogeneous fleets against each other, which is not the same
  as optimising a mix.
- **One day, deterministic.** No traffic variability, no failed deliveries, no reattempts, and
  no driver breaks. The capacity simulation in `oplab.simulation` is where variability lives;
  this module is a planning tool, not an operational one.
- **No proof of optimality**, as above. Always report the search budget.

---

## Português

Precifica um dia de entregas e responde a três perguntas sobre ele: quanto vale densidade,
quanto custam as janelas de entrega, e frota própria ou terceirizada.

Construído sobre OR-Tools. Instale o extra: `pip install -e ".[routing]"`.

### O achado que este módulo foi construído para produzir

É uma recusa. Roteirizando 74 entregas de um depósito:

| Opção | Veículos | Custo por entrega |
| --- | --- | --- |
| Van própria | 5 | **38,50** |
| Transportadora a 42,00 | — | 42,00 |
| Caminhão próprio | 5 | 64,21 |

A van vence a transportadora por R$ 3,50 por entrega — vantagem de 8,3% — *no orçamento de
busca usado nessa tabela*. Dê ao solver um orçamento mais barato e a van custa R$ 53,29, e a
transportadora ganha com folga.

**A conclusão se inverte conforme o quanto o solver teve permissão de procurar.** Um solve
barato diz terceirize; um minucioso diz opere a frota. A diferença entre as opções é um quarto
da amplitude que o orçamento de busca sozinho produz, então **este modelo não decide frota
própria versus terceirizada nesse preço**, e dizer isso *é* o resultado. Reportar uma vantagem
de 8% como achado — a partir de uma heurística que nunca provou otimalidade, sobre distâncias em
linha reta multiplicadas por um fator de circuidade presumido, para uma quarta-feira de junho —
seria um número com uma decisão pendurada nele e nada por baixo.

O que o modelo decide, por margem que nenhuma premissa ameaça: o caminhão é o veículo errado
para este perfil, a 67% mais por entrega.

### "Ótimo" não é o que volta

| Orçamento de busca | Veículos | Custo por entrega |
| --- | --- | --- |
| 20 soluções | 8 | 53,29 |
| 60 | 8 | 50,76 |
| 120 | 6 | 42,17 |
| 300 | **5** | **38,50** |

O que mudou ao longo das linhas não foi só o custo, em 27,7%: foi **o tamanho da frota**, de oito
veículos para cinco. Uma concorrência decidida com um solve barato teria comprado três vans
desnecessárias.

**O orçamento é contagem de soluções, não cronômetro.** Limite de tempo de parede faz a resposta
depender da máquina e do que mais ela está fazendo: o mesmo problema sob contenção de CPU explora
menos e devolve um plano pior — e diferente. Isso é inaceitável num número que vai para
concorrência, e apareceu aqui como um teste que passava isolado e falhava na suíte completa.
Contar soluções aceitas torna o resultado reproduzível em qualquer lugar.

### Densidade, não distância

| Paradas no território | Km por entrega | Custo por entrega |
| --- | --- | --- |
| 18 | 15,82 | 53,22 |
| 37 | 16,01 | 48,21 |
| 74 | 12,54 | **38,50** |

Mesmo território em todas as linhas — as paradas são subamostra aleatória do mesmo dia, então a
área nunca muda, só quantos clientes há nela. Quatro vezes a densidade são **28% menos custo por
entrega**.

Nada nas distâncias mudou. Densidade de entrega governa o custo por entrega na última milha
muito mais que distância — por isso um território em crescimento pode ficar mais barato por
parada enquanto um em retração fica mais caro, sem nenhuma tarifa se mover.

### Quanto custam as janelas, e uma correção

| Caso | Veículos | Custo por entrega |
| --- | --- | --- |
| Janelas respeitadas | 5 | 38,50 |
| Janelas abertas ao dia todo | 5 | 37,68 |

A promessa comercial custa **2,2%, e nenhum veículo extra**.

Esse número é uma correção, e a correção é o achado mais útil. Com orçamento de busca menor, a
mesma comparação dava 8,8% e uma van extra. O motivo não é ruído: **um solve com busca
insuficiente exagera o custo de toda restrição que ele precifica**, porque a heurística sofre
mais com o problema restrito que com o aberto, então a penalidade reportada é em parte o próprio
fracasso dela. Quem precifica o custo de uma promessa de serviço roteirizando com e sem ela
precisa conferir se os dois lados tiveram orçamento para ser resolvidos de verdade.

O que sobrevive à correção é o mecanismo: janelas fragmentam rotas de um jeito que capacidade
não — uma van com dois terços da carga livre ainda tem de voltar ao depósito, porque não alcança
a próxima janela a tempo — e neste dia o limite por carga é três veículos contra cinco usados.

### Diagnostique antes de culpar o solver

`diagnose` encontra paradas que nenhuma rota atende — ida e volta maior que a jornada, janela que
fecha antes de qualquer veículo chegar, carga acima da capacidade. Uma única parada assim torna o
dia inteiro infactível por melhor que seja o algoritmo, e resolver isso é renegociação, não
otimização.

`fleet_lower_bounds` reporta apenas os dois limites **válidos**: carga tem de ser transportada e
tempo na porta tem de ser gasto, e nenhum dos dois se compartilha entre veículos. Não há limite
baseado em deslocamento, de propósito, e a omissão é uma correção: somar a perna de ida de cada
parada e dividir pela jornada *parece* limite e não é — pressupõe que cada parada exige ida e
volta própria, quando uma rota com doze paradas percorre o raio uma vez e o amortiza. Esse número
dava sete veículos para um dia que o solver resolve com cinco: um "limite inferior" acima da
solução. O quanto a roteirização o supera **é** o efeito de densidade acima.

### Premissas e limitações

- **Distância rodoviária é distância em linha reta vezes 1,35.** Distância real vem de motor de
  roteirização sobre malha real. O fator está na faixa usualmente citada para malha urbana e é
  premissa, não medição.
- **Uma velocidade média** substitui uma malha onde arco urbano e rodovia diferem por fator três.
  Isso torna a *ordenação* de cenários confiável e as horas absolutas não confiáveis.
- **Um pedido é uma parada** — sem consolidação de pedidos para o mesmo cliente, que reduziria o
  custo por entrega.
- **Um tipo de veículo por solve.** Frota mista escolhida conjuntamente é problema diferente e
  mais difícil; `compare_fleets` precifica frotas homogêneas uma contra a outra, o que não é
  otimizar um mix.
- **Um dia, determinístico.** Sem variabilidade de tráfego, sem entrega não realizada, sem
  reentrega, sem pausa de motorista. Variabilidade vive em `oplab.simulation`; este módulo é
  ferramenta de planejamento, não de operação.
- **Sem prova de otimalidade.** Sempre reporte o orçamento de busca.
