# oplab.inventory — what a point of service level costs, and which lever buys it

**EN** · [Português](#português)

The deliverable is one chart: safety stock capital against service level, priced per point. Around
it are the four measurements that decide whether the chart is honest — because the usual version
is built on a lead time from a contract, a service definition nobody agreed, and a formula whose
promise is never checked against what the policy delivers.

No extra dependency: `pip install -e .` The three normal functions this needs are implemented in
`oplab.inventory.normal` and tested against published tables.

## Finding 1: sizing on the contract misses 58% of the stock the service level needs

Every supplier delivers close to its quoted mean, which is why the contract is never questioned:

| Supplier | Quoted | Realised mean | Realised sd | CV | Skew | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| FORN-REGIONAL | 5.0 | 5.22 | 1.03 | 0.20 | 1.74 | 6.93 |
| FORN-NACIONAL | 7.0 | 7.77 | **3.56** | **0.46** | 3.55 | 13.10 |
| FORN-CONTRATO | 12.0 | 12.17 | 1.58 | 0.13 | 0.99 | 14.82 |
| FORN-IMPORT | 30.0 | 31.68 | 4.85 | 0.15 | 5.58 | 36.88 |

The quote says nothing about the column that sizes the buffer. Using it sets lead-time
variability to zero, and on 191 regular SKUs at a 95% cycle service level:

| Supplier | SKUs | Required capital (BRL) | Sized on the quote | Understated by |
| --- | --- | --- | --- | --- |
| FORN-NACIONAL | 68 | 82,181 | 38,781 | **52.8%** |
| FORN-IMPORT | 32 | 37,971 | 23,049 | 39.3% |
| FORN-CONTRATO | 36 | 39,574 | 32,375 | 18.2% |
| FORN-REGIONAL | 55 | 32,579 | 27,318 | 16.1% |
| **Network** | **191** | **192,305** | **121,522** | **36.8%** |

**The plan is not slightly optimistic; it is missing 58% of the stock the service level needs**
(192,305 / 121,522). The gap is invisible in review because both numbers come out of the same
formula — the only difference is which lead time went into it, and one of the two was never
measured.

Every lead-time distribution is also right skewed, with skewness from 1.0 to 5.6. The normal
approximation behind the formula is being asked to cover a tail it does not have, which is what
Finding 4 turns into a decision.

## Finding 2: whether lead time or demand is the lever has a closed form

The combined variance is `(L + R) · sd_d² + mu_d² · sd_L²`. Dividing through by `mu_d²` shows that
lead-time variability dominates exactly when

    CV_L² · L > CV_d²

Rearranged, lead time dominates on every item whose demand CV is **below** `sqrt(CV_L² · L)` —
one threshold per supplier, and a steady item is therefore the one whose buffer is decided by the
supplier rather than by the forecast:

| Supplier | Crossover demand CV | Actual mean demand CV | Lead-time variance share | Lead time dominates on |
| --- | --- | --- | --- | --- |
| FORN-REGIONAL | 0.452 | 0.777 | 27% | **0% of SKUs** |
| FORN-CONTRATO | 0.452 | 0.756 | 28% | **0% of SKUs** |
| FORN-IMPORT | 0.861 | 0.733 | 58% | **94% of SKUs** |
| FORN-NACIONAL | 1.277 | 0.757 | 74% | **97% of SKUs** |

Demand CV sits near 0.76 across the assortment — above two of the thresholds and below the other
two — so the answer is not a property of the items at all: **lead time is the lever for two
suppliers and demand is the lever for the other two**, and the split across the 50% of SKUs where
lead time dominates is fully explained by who ships them.

That is worth more than the usual blanket claim in either direction. "Lead-time variability
dominates safety stock" is true often enough to be repeated and false often enough to mislead;
the condition above says which case you are in, from two numbers you already have, without
simulating anything.

## Finding 3: the shorter lead time can need the larger buffer

The same item, quoted from each of the four suppliers, at a 95% cycle service level:

| Supplier | Lead days | sd lead days | Safety units | Pipeline units | Total units |
| --- | --- | --- | --- | --- | --- |
| FORN-REGIONAL | 5.2 | 1.0 | 67.1 | 124.7 | 191.8 |
| FORN-NACIONAL | 7.8 | 3.6 | **154.4** | 185.9 | 340.3 |
| FORN-CONTRATO | 12.2 | 1.6 | **102.5** | 291.1 | 393.6 |
| FORN-IMPORT | 31.7 | 4.8 | 231.7 | 757.7 | 989.4 |

**FORN-CONTRATO takes 57% longer and needs 34% less safety stock**, because its lead time is 2.3
times tighter. A sourcing decision made on quoted lead time alone gets the buffer backwards.

The honest qualification is in the last column: **total inventory does not invert.** Pipeline
stock scales with the mean lead time and dominates the comparison, so FORN-NACIONAL still holds
less inventory overall. Safety stock and total inventory are different questions with different
answers, and both are real — the mistake is answering one of them and reporting the other.

## Finding 4: the same 99% commitment, sized two ways, differs by 82%

| Reading | z | Safety units | Capital (BRL) | Implied fill rate | Implied cycle service |
| --- | --- | --- | --- | --- | --- |
| As cycle service | 2.326 | 327.7 | 1,838 | 0.9993 | 0.9900 |
| As fill rate | 1.279 | 180.2 | 1,011 | 0.9900 | 0.8996 |

**Sizing a fill-rate commitment as a cycle-service one buys 82% more stock than the commitment
requires.** Neither row is wrong. Cycle service counts cycles, fill rate counts units, and a
shortfall late in a cycle costs few units — so fill rate is always the kinder number, and a policy
set to 99% cycle service delivers a 99.93% fill rate it was never asked for.

The conversion between them needs the order quantity, which is why no fudge factor exists: a
larger order spreads the same expected shortfall over more units, so the same safety stock buys a
higher fill rate. `z_for_cycle_service` and `z_for_fill_rate` are deliberately separate functions
with different signatures, and the second one will not run without a quantity.

## Finding 5: the price of a point rises elevenfold, and the top of the curve buys nothing

| Cycle service target | Safety capital (BRL) | Capital per point | Achieved cycle service | Achieved fill rate |
| --- | --- | --- | --- | --- |
| 80.0% | 665 | — | 0.8920 | 0.9829 |
| 90.0% | 1,013 | 34.76 | 0.9469 | 0.9892 |
| 95.0% | 1,300 | 57.42 | 0.9625 | 0.9917 |
| 98.0% | 1,623 | 107.70 | 0.9825 | 0.9944 |
| 99.0% | 1,838 | 215.41 | 0.9855 | 0.9950 |
| 99.5% | 2,035 | 394.28 | 0.9862 | 0.9955 |

A point of cycle service costs BRL 34.76 at the bottom of the curve and BRL 394.28 at the top —
**eleven times as much** — because the normal tail thins. That convexity is the argument for
differentiating service by item rather than setting one target for the assortment: the same
capital buys far more service spent where service is cheap.

**The top of the curve is worse than convex.** Going from 99.0% to 99.5% costs 11% more capital
and delivers **+0.07%** of measured cycle service. The promise keeps rising and the outcome stops
following, because what remains is the skewed tail of the lead time and a normal buffer is an
expensive way to cover it.

## Finding 6: the cheapest point of service is not on the curve

Two levers on the same item at a 99% target:

| Lever | Safety units | Change |
| --- | --- | --- |
| As measured | 327.7 | — |
| The entire forecasting headroom (0.8% off demand sd) | 326.8 | **−0.26%** |
| Supplier's lead-time tail capped at its own p95 | 249.9 | **−23.7%** |

The forecasting headroom is not a guess: it is the measured gap between the best of seven methods
and a one-line seasonal rule on this data, from
[`oplab.forecast`](../forecast/README.md). Spending all of it releases 0.26% of the buffer.
Capping the worst 5% of one supplier's deliveries releases 23.7% — **a factor of 92** — and the
effort is not comparable either: one requires beating a naive rule across the assortment, the
other requires one conversation about the tail of one supplier's delivery record.

And it is not a trade. Simulated on resampled demand and the capped lead times, the smaller
policy holds 23.7% less safety stock and still measures **0.9886** cycle service against the 99%
promise. Reliability is the cheaper input, and it is bought upstream rather than held.

## Finding 7: demand variability is the wrong input when a forecast drives replenishment

The safety-stock formula above buffers against the standard deviation of **demand**. That is the
right quantity only when the replenishment target is the long-run mean. When it is a **forecast**,
the quantity to buffer is the standard deviation of the **forecast error** — and the two are not
interchangeable in a known direction:

| Basis | Safety units | σ | Change |
| --- | --- | --- | --- |
| Demand variability | 231.69 | 140.86 | — |
| Forecast error | 225.45 | 137.00 | **−2.7%** |

On this item the forecast is marginally sharper than the demand spread, so the buffer falls by 2.7%.
Across the assortment the median ratio of forecast-error spread to demand spread is **1.0019** and
the forecast reduces the buffer on **47%** of series — so sizing on demand variability is neither
conservative nor wrong here, it is simply arbitrary. Which direction it errs in is a measurement
nobody takes, and `compare_sizing_bases` takes it.

**A biased forecast is a separate cost that no safety factor covers.** Raising `z` widens a window
that is in the wrong place. The worst under-forecast in the assortment runs at −13.27 units a day,
which charges **103.2 units of permanent stock — 32% on top of a 321-unit buffer** — held purely to
compensate a forecast that is wrong in one direction. The remedy is to fix the forecast; the charge
is what it costs until someone does.

And the average bias is the one statistic that cannot size it. Croston's mean bias is +0.47 units a
day while it under-forecasts 28% of series by −0.67; SBA's mean bias is +0.005, near zero, and it
under-forecasts **52%** of series. Inventory is held per item, so a centred average is not a
centred forecast. This is the additivity from [`oplab.forecast`](../forecast/README.md) arriving as
a cost rather than as an observation.

## Usage

```python
from oplab.inventory import fit_demand, fit_lead_time, service_curve, z_for_cycle_service
from oplab.synth import generate_dataset

dataset = generate_dataset()
orders = dataset.purchase_orders
lead = fit_lead_time(orders["lead_days"].to_numpy(), quoted=7.0)
demand = fit_demand([12, 0, 31, 8, 19, 22, 0, 14])  # per period, zeros included

print(service_curve(demand, lead, order_quantity=560.0, unit_cost=12.0))
print(z_for_cycle_service(0.95))
```

Full walkthrough: [`examples/10_inventory_policy.py`](../../../examples/10_inventory_policy.py).

## Assumptions and limitations

- **Unmet demand is lost, not backordered.** That is right for a distribution centre serving
  retail or e-commerce and wrong for a spare-parts operation with a captive customer. It is the
  pessimistic assumption for fill rate, and changing it changes every achieved figure above.
- **The simulation has a warm-up, and it is not optional.** On a one-year horizon the same policy
  on the same data measured between **89.3% and 97.3%** cycle service depending only on whether
  it started full, at the reorder point, or empty. A warm-up of two replenishment cycles
  collapses that near-eight-point spread to 1.2 points. This was found while building the module, and the
  artefact was believable in both directions — which is exactly why `warmup` defaults to a
  computed value rather than to zero.
- **Demand is resampled independently across periods.** That keeps the zeros and the skew of the
  real series but destroys autocorrelation, so a run of high-demand days is less likely in the
  simulation than in the operation. Achieved service here is therefore mildly optimistic; a block
  bootstrap would be the fix and is not implemented.
- **One SKU, one location, one supplier.** There is no multi-echelon allocation, no transshipment,
  no substitution between items, and no shared capacity. Each of those makes the network position
  smaller than the sum of the single-item positions, so the totals here are an upper bound.
- **The forecast-error sizing inherits the backtest's window.** `error_sd` and `error_bias` come
  from a rolling-origin backtest, so they describe the forecast's behaviour over that window and
  assume it carries forward. A forecast whose error changes regime — a new supplier, a range
  change, a promotion calendar that shifts — invalidates the sizing in a way this module cannot
  detect.
- **The formula assumes normality twice over** — demand over the protection interval and the lead
  time itself. The first is defensible on a fast mover by the central limit theorem and
  indefensible on an intermittent one. This module does not size intermittent items; on the sparse
  half of the assortment the honest answer is the availability decision named in
  [`oplab.forecast`](../forecast/README.md), not a safety stock.
- **The lead-time sample is the supplier's, not the item's.** Pooling across a supplier's orders
  buys enough observations to estimate a variance and assumes every item that supplier ships
  behaves the same way. On a supplier with a mixed portfolio that is wrong in a direction this
  module cannot detect.
- **EOQ is included and should mostly be ignored.** On a low-value item here it recommends 70 days
  of cover, because the holding cost per unit is small next to a fixed ordering cost nobody
  measures. Total cost is flat enough near the optimum that anything within 20% of it costs under
  2% more, which is the real reason the formula's precision is not worth arguing about.

---

## Português

O entregável é um gráfico: capital em estoque de segurança contra nível de serviço, com preço por
ponto. Em volta dele estão as quatro medições que decidem se o gráfico é honesto — porque a versão
usual é construída sobre um lead time de contrato, uma definição de serviço que ninguém acordou, e
uma fórmula cuja promessa nunca é confrontada com o que a política entrega.

### Achado 1: dimensionar pelo contrato deixa de fora 58% do estoque que o serviço exige

Todo fornecedor entrega perto da média cotada, e é por isso que o contrato nunca é questionado:

| Fornecedor | Cotado | Média real | Desvio real | CV | Assimetria | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| FORN-REGIONAL | 5,0 | 5,22 | 1,03 | 0,20 | 1,74 | 6,93 |
| FORN-NACIONAL | 7,0 | 7,77 | **3,56** | **0,46** | 3,55 | 13,10 |
| FORN-CONTRATO | 12,0 | 12,17 | 1,58 | 0,13 | 0,99 | 14,82 |
| FORN-IMPORT | 30,0 | 31,68 | 4,85 | 0,15 | 5,58 | 36,88 |

A cotação não diz nada sobre a coluna que dimensiona o pulmão. Usá-la zera a variabilidade do lead
time. Em 191 SKUs regulares, a 95% de nível de serviço de ciclo:

| Fornecedor | SKUs | Capital exigido (BRL) | Dimensionado pela cotação | Subestimado em |
| --- | --- | --- | --- | --- |
| FORN-NACIONAL | 68 | 82.181 | 38.781 | **52,8%** |
| FORN-IMPORT | 32 | 37.971 | 23.049 | 39,3% |
| FORN-CONTRATO | 36 | 39.574 | 32.375 | 18,2% |
| FORN-REGIONAL | 55 | 32.579 | 27.318 | 16,1% |
| **Rede** | **191** | **192.305** | **121.522** | **36,8%** |

**O plano não é levemente otimista; falta 58% do estoque que o nível de serviço exige.** A lacuna
é invisível em reunião porque os dois números saem da mesma fórmula — a única diferença é qual lead
time entrou nela, e um dos dois nunca foi medido.

### Achado 2: se o lever é lead time ou demanda tem forma fechada

A variância combinada é `(L + R) · sd_d² + mu_d² · sd_L²`. Dividindo por `mu_d²`, a variabilidade
do lead time domina exatamente quando `CV_L² · L > CV_d²` — ou seja, em todo item cujo CV de
demanda esteja **abaixo** de `sqrt(CV_L² · L)`, um limiar por fornecedor:

| Fornecedor | CV de demanda de cruzamento | CV médio real | Parcela da variância do lead time | Lead time domina em |
| --- | --- | --- | --- | --- |
| FORN-REGIONAL | 0,452 | 0,777 | 27% | **0% dos SKUs** |
| FORN-CONTRATO | 0,452 | 0,756 | 28% | **0% dos SKUs** |
| FORN-IMPORT | 0,861 | 0,733 | 58% | **94% dos SKUs** |
| FORN-NACIONAL | 1,277 | 0,757 | 74% | **97% dos SKUs** |

O CV de demanda fica perto de 0,76 em todo o sortimento — acima de dois limiares e abaixo dos
outros dois —, então a resposta não é propriedade dos itens: **lead time é o lever para dois fornecedores e demanda é o lever para os outros dois**, e a
divisão nos 50% de SKUs em que o lead time domina é integralmente explicada por quem embarca.

"Variabilidade de lead time domina o estoque de segurança" é verdade com frequência suficiente
para ser repetida e falsa com frequência suficiente para enganar; a condição acima diz em qual
caso você está, a partir de dois números que você já tem, sem simular nada.

### Achado 3: o lead time menor pode exigir o pulmão maior

O mesmo item, cotado com os quatro fornecedores, a 95% de serviço de ciclo:

| Fornecedor | Lead (dias) | Desvio | Segurança (un) | Em trânsito (un) | Total (un) |
| --- | --- | --- | --- | --- | --- |
| FORN-REGIONAL | 5,2 | 1,0 | 67,1 | 124,7 | 191,8 |
| FORN-NACIONAL | 7,8 | 3,6 | **154,4** | 185,9 | 340,3 |
| FORN-CONTRATO | 12,2 | 1,6 | **102,5** | 291,1 | 393,6 |
| FORN-IMPORT | 31,7 | 4,8 | 231,7 | 757,7 | 989,4 |

**O FORN-CONTRATO leva 57% mais tempo e exige 34% menos estoque de segurança**, porque seu lead
time é 2,3 vezes mais apertado. Decisão de sourcing feita só pelo lead time cotado inverte o
pulmão.

A qualificação honesta está na última coluna: **o estoque total não inverte.** O estoque em
trânsito escala com a média e domina a comparação. Estoque de segurança e estoque total são
perguntas diferentes com respostas diferentes — o erro é responder uma e reportar a outra.

### Achado 4: o mesmo compromisso de 99%, dimensionado de dois modos, difere em 82%

| Leitura | z | Segurança (un) | Capital (BRL) | Fill rate implícito | Serviço de ciclo implícito |
| --- | --- | --- | --- | --- | --- |
| Como serviço de ciclo | 2,326 | 327,7 | 1.838 | 0,9993 | 0,9900 |
| Como fill rate | 1,279 | 180,2 | 1.011 | 0,9900 | 0,8996 |

**Dimensionar um compromisso de fill rate como serviço de ciclo compra 82% mais estoque do que o
compromisso exige.** Nenhuma das linhas está errada. Serviço de ciclo conta ciclos, fill rate
conta unidades, e falta no fim do ciclo custa poucas unidades — então o fill rate é sempre o número
mais generoso, e a política de 99% de ciclo entrega 99,93% de fill rate que ninguém pediu.

A conversão entre os dois exige a quantidade de pedido, e é por isso que não existe fator de
correção: pedido maior espalha a mesma falta esperada por mais unidades.

### Achado 5: o preço do ponto sobe onze vezes, e o topo da curva não compra nada

| Meta de serviço de ciclo | Capital (BRL) | Capital por ponto | Serviço de ciclo obtido | Fill rate obtido |
| --- | --- | --- | --- | --- |
| 80,0% | 665 | — | 0,8920 | 0,9829 |
| 90,0% | 1.013 | 34,76 | 0,9469 | 0,9892 |
| 95,0% | 1.300 | 57,42 | 0,9625 | 0,9917 |
| 98,0% | 1.623 | 107,70 | 0,9825 | 0,9944 |
| 99,0% | 1.838 | 215,41 | 0,9855 | 0,9950 |
| 99,5% | 2.035 | 394,28 | 0,9862 | 0,9955 |

Um ponto custa BRL 34,76 na base da curva e BRL 394,28 no topo — **onze vezes mais** — porque a
cauda normal afina. Essa convexidade é o argumento para diferenciar serviço por item em vez de
definir uma meta única: o mesmo capital compra muito mais serviço onde serviço é barato.

**O topo da curva é pior que convexo.** De 99,0% para 99,5% custa 11% mais capital e entrega
**+0,07%** de serviço de ciclo medido. A promessa continua subindo e o resultado para de seguir,
porque o que resta é a cauda assimétrica do lead time e um pulmão normal é forma caríssima de
cobri-la.

### Achado 6: o ponto de serviço mais barato não está na curva

| Lever | Segurança (un) | Variação |
| --- | --- | --- |
| Como medido | 327,7 | — |
| Todo o ganho de previsão disponível (0,8% do desvio da demanda) | 326,8 | **−0,26%** |
| Cauda do fornecedor cortada no próprio p95 | 249,9 | **−23,7%** |

O ganho de previsão não é chute: é a diferença medida entre o melhor de sete métodos e uma regra
sazonal de uma linha nestes dados, em [`oplab.forecast`](../forecast/README.md). Gastá-lo por
inteiro libera 0,26% do pulmão. Cortar os 5% piores de um fornecedor libera 23,7% — **fator de
92** — e o esforço também não é comparável: um exige superar uma regra naive em todo o sortimento,
o outro exige uma conversa sobre a cauda do histórico de um fornecedor.

E não é troca. Simulada com demanda reamostrada e os lead times cortados, a política menor mantém
23,7% menos estoque de segurança e ainda mede **0,9886** de serviço de ciclo contra a promessa de
99%. Confiabilidade é o insumo mais barato, e se compra a montante em vez de se manter em estoque.

### Achado 7: variabilidade da demanda é o insumo errado quando uma previsão comanda a reposição

A fórmula acima amortece o desvio padrão da **demanda**. Essa é a grandeza correta apenas quando o
alvo de reposição é a média de longo prazo. Quando é uma **previsão**, a grandeza a amortecer é o
desvio padrão do **erro da previsão** — e as duas não são intercambiáveis numa direção conhecida:

| Base | Segurança (un) | σ | Variação |
| --- | --- | --- | --- |
| Variabilidade da demanda | 231,69 | 140,86 | — |
| Erro da previsão | 225,45 | 137,00 | **−2,7%** |

Neste item a previsão é marginalmente mais apertada que o desvio da demanda, então o pulmão cai
2,7%. No sortimento, a razão mediana entre desvio do erro e desvio da demanda é **1,0019** e a
previsão reduz o pulmão em **47%** das séries — então dimensionar pela variabilidade da demanda não
é conservador nem errado aqui, é simplesmente arbitrário. Para que lado ele erra é uma medição que
ninguém faz, e o `compare_sizing_bases` faz.

**Previsão viesada é custo separado que nenhum fator de segurança cobre.** Elevar `z` alarga uma
janela que está no lugar errado. O pior sub-dimensionamento do sortimento roda a −13,27 unidades/dia,
o que cobra **103,2 unidades de estoque permanente — 32% sobre um pulmão de 321 unidades** — mantidas
só para compensar uma previsão errada numa direção. O remédio é corrigir a previsão; a cobrança é o
que ela custa até alguém corrigir.

E o viés médio é a única estatística que não serve para dimensionar. O viés médio do Croston é +0,47
unidade/dia enquanto ele sub-dimensiona 28% das séries em −0,67; o do SBA é +0,005, quase zero, e ele
sub-dimensiona **52%** das séries. Estoque é mantido por item, então média centrada não é previsão
centrada. É a aditividade de [`oplab.forecast`](../forecast/README.md) chegando como custo em vez de
observação.

### Premissas e limitações

- **A demanda não atendida é perdida, não pedido em carteira.** Correto para CD de varejo ou
  e-commerce, errado para peças de reposição com cliente cativo. É a premissa pessimista para fill
  rate, e mudá-la muda todo número obtido acima.
- **A simulação tem warm-up, e ele não é opcional.** Em horizonte de um ano a mesma política nos
  mesmos dados mediu entre **89,3% e 97,3%** de serviço de ciclo dependendo apenas de ter começado
  cheia, no ponto de pedido ou vazia. Warm-up de dois ciclos reduz essa amplitude de quase oito
  pontos para 1,2 ponto. Foi descoberto construindo o módulo, e o artefato era crível nas duas direções — por
  isso `warmup` tem valor calculado por padrão, não zero.
- **A demanda é reamostrada independentemente entre períodos.** Preserva os zeros e a assimetria da
  série real mas destrói a autocorrelação, então uma sequência de dias fortes é menos provável na
  simulação que na operação. O serviço obtido aqui é, portanto, levemente otimista.
- **Um SKU, um local, um fornecedor.** Não há alocação multi-eco, transferência entre unidades,
  substituição entre itens nem capacidade compartilhada. Cada um deles torna a posição da rede
  menor que a soma das posições individuais, então os totais aqui são limite superior.
- **O dimensionamento pelo erro de previsão herda a janela do backtest.** `error_sd` e `error_bias`
  vêm de um backtest de origem móvel, então descrevem o comportamento da previsão naquela janela e
  presumem que ele se mantém. Previsão cujo erro muda de regime invalida o dimensionamento de um
  jeito que este módulo não detecta.
- **A fórmula assume normalidade duas vezes** — demanda no intervalo de proteção e o próprio lead
  time. A primeira é defensável num item de alto giro pelo teorema central do limite e
  indefensável num intermitente. Este módulo não dimensiona itens intermitentes; na metade esparsa
  do sortimento a resposta honesta é a decisão de disponibilidade apontada em
  [`oplab.forecast`](../forecast/README.md).
- **A amostra de lead time é do fornecedor, não do item.** Agrupar por fornecedor dá observações
  suficientes para estimar variância e assume que todo item que ele embarca se comporta igual.
- **O EOQ está incluído e deve ser em geral ignorado.** Num item de baixo valor aqui ele recomenda
  70 dias de cobertura, porque o custo de manter por unidade é pequeno diante de um custo fixo de
  pedido que ninguém mede. O custo total é plano perto do ótimo — qualquer quantidade dentro de 20%
  custa menos de 2% mais —, e essa é a razão real pela qual a precisão da fórmula não merece
  discussão.
