# oplab.slotting — ABC-XYZ classification and pick-face slotting

**EN** · [Português](#português)

Answers two questions: which items deserve which policy, and what the current pick-face layout
costs in travel.

## The finding this module was built to produce

On the bundled synthetic warehouse — 400 SKUs, 82,650 picks over a year, 2,400 pick faces —
three sensible ranking rules were compared against the current random placement:

| Strategy | Mean distance per pick | Change |
| --- | --- | --- |
| By popularity (picks) | 17.11 m | −67.2% |
| By revenue | 17.34 m | −66.7% |
| By cube-per-order index | 18.00 m | −65.5% |
| Current (as received) | 52.11 m | — |

**Every rule recovers roughly two thirds of the travel. The spread between the best and the
worst rule is 1.7 percentage points.** The decision worth money is whether to re-slot at all;
the choice of algorithm is a rounding error next to it. A project scoped around the optimiser
is optimising the wrong variable — and that is the opposite of how slotting software is sold.

## Two results reported rather than buried

**Ranking by revenue nearly matches ranking by picks** on this assortment, because the two
rankings correlate at 0.88. Revenue is a usable proxy for velocity *here*. It stops being one
wherever price and pick frequency diverge, and that has to be checked, not assumed.

**The cube-per-order index comes last, and that is correct.** With one face per SKU and uniform
face capacity, every item consumes the same space, so cube carries no information about the
objective and pricing it in only adds noise. Under those assumptions ranking by picks is
provably optimal. COI earns its keep when items span several faces or faces differ in size —
the regime the capacity simulation of a later wave models. The sophisticated rule is kept, and
kept losing, because the condition under which it wins is the useful thing to know.

## Why XYZ, and the detail that decides whether it means anything

ABC ranks items by how much they matter; XYZ by how predictable they are. An A item with
erratic demand and an A item with stable demand carry the same revenue and need opposite
policies. On the bundled data, **18 of 87 class A items are not stable and they carry 19.1% of
class A value** — an ABC-only exercise gives all of them the policy designed for the
predictable ones, and that is where the service failures come from.

The coefficient of variation must be computed over **every period in the horizon, including the
periods with no demand**. An item selling 40 units once a quarter has a CV of zero if only its
selling weeks are averaged, and lands in X — the most stable class — when it is the least
predictable thing in the assortment. `demand_profile` reindexes onto the full period grid
before computing anything.

## Usage

```python
from oplab.slotting import abc_xyz, demand_profile, pick_counts, reslot, compare_strategies
from oplab.synth import generate_dataset

dataset = generate_dataset()
picks = pick_counts(dataset.order_lines, site="CD-SP")
classified = abc_xyz(demand_profile(dataset.demand, dataset.catalog, period="W"))

plan = reslot(-picks, dataset.layout, cube=dataset.catalog.set_index("sku")["case_volume_m3"])
print(
    compare_strategies(
        picks,
        dataset.layout,
        {"current": dataset.assignment, "reslotted": plan},
        baseline="current",
    )
)
```

Full walkthrough: [`examples/04_slotting.py`](../../../examples/04_slotting.py).

## Assumptions and limitations

The objective is **distance-weighted picks**, not a route. That figure is proportional to real
walking distance only under return routing, where a picker collects one line and comes back.
Under batch picking with an S-shape or largest-gap route the constant of proportionality
changes and is not constant across orders. **Quote the percentage change, not the metres**: the
routing constant largely cancels in the ratio and does not cancel in the level.

Beyond that:

- **One location per SKU.** No forward-and-reserve split, no multi-location storage, no
  replenishment. A real operation slots fast movers into a forward pick area fed from bulk, and
  that changes the arithmetic.
- **A single dock and parallel aisles.** Travel is the walk along one cross-aisle plus the walk
  into the aisle. A cross-docking or flow-through layout with opposed docks needs a different
  distance function.
- **No congestion.** Concentrating picks into the near aisles creates queueing that this model
  cannot see, which means the reported gain is an upper bound.
- **No move cost.** The plan does not price the labour of physically re-slotting, which is what
  decides whether a proposal is worth executing this quarter or at the next layout change.

Every one of these overstates the benefit. They are listed so that a figure from this module is
read as a direction and an order of magnitude, not as a business case.

---

## Português

Responde a duas perguntas: quais itens merecem qual política, e quanto o endereçamento atual
custa em deslocamento.

### O achado que este módulo foi construído para produzir

No armazém sintético embutido — 400 SKUs, 82.650 coletas no ano, 2.400 faces de picking — três
regras razoáveis de ordenação foram comparadas contra a alocação aleatória atual:

| Estratégia | Distância média por coleta | Variação |
| --- | --- | --- |
| Por popularidade (coletas) | 17,11 m | −67,2% |
| Por receita | 17,34 m | −66,7% |
| Por índice cube-per-order | 18,00 m | −65,5% |
| Atual (como recebido) | 52,11 m | — |

**Toda regra recupera cerca de dois terços do deslocamento. A diferença entre a melhor e a pior
regra é de 1,7 ponto percentual.** A decisão que vale dinheiro é *reendereçar ou não*; a escolha
do algoritmo é erro de arredondamento diante disso. Projeto escopado em torno do otimizador está
otimizando a variável errada — e é o oposto de como software de slotting é vendido.

### Dois resultados reportados em vez de escondidos

**Ordenar por receita quase empata com ordenar por coletas** neste sortimento, porque as duas
ordenações correlacionam a 0,88. Receita é um proxy utilizável de velocidade *aqui*. Deixa de
ser onde preço e frequência de coleta divergem, e isso tem de ser verificado, não presumido.

**O índice cube-per-order fica em último, e está correto.** Com uma face por SKU e capacidade
uniforme, todo item consome o mesmo espaço, logo o cubo não carrega informação sobre a função
objetivo e precificá-lo só adiciona ruído. Sob essas premissas, ordenar por coletas é
provadamente ótimo. O COI se paga quando itens ocupam várias faces ou as faces têm tamanhos
diferentes — o regime que a simulação de capacidade de uma onda posterior modela. A regra
sofisticada foi mantida, e mantida perdendo, porque a condição sob a qual ela ganha é o que
vale saber.

### Por que XYZ, e o detalhe que decide se isso significa algo

ABC ordena itens por quanto importam; XYZ por quão previsíveis são. Um item A com demanda
errática e um item A com demanda estável têm a mesma receita e pedem políticas opostas. Nos
dados embutidos, **18 de 87 itens classe A não são estáveis e carregam 19,1% do valor da classe
A** — um exercício só de ABC dá a todos eles a política desenhada para os previsíveis, e é daí
que vêm as falhas de serviço.

O coeficiente de variação tem de ser calculado sobre **todos os períodos do horizonte, inclusive
os sem demanda**. Um item que vende 40 unidades uma vez por trimestre tem CV zero se apenas suas
semanas de venda forem consideradas, e cai em X — a classe mais estável — quando é a coisa menos
previsível do sortimento. `demand_profile` reindexa sobre a grade completa de períodos antes de
calcular qualquer coisa.

### Premissas e limitações

A função objetivo é **coletas ponderadas por distância**, não uma rota. Esse número é
proporcional à distância real caminhada apenas sob roteirização de ida e volta. Sob picking por
lote com rota em S ou de maior vão, a constante de proporcionalidade muda e não é constante
entre pedidos. **Cite a variação percentual, não os metros**: a constante de roteirização se
cancela na razão e não se cancela no nível.

Além disso: uma localização por SKU (sem separação forward/reserve nem reabastecimento); doca
única com corredores paralelos; nenhum efeito de congestionamento (concentrar coletas nos
corredores próximos cria fila que este modelo não vê); e nenhum custo de movimentação para
executar o reendereçamento. Todas essas premissas **superestimam** o benefício, e estão listadas
para que qualquer número daqui seja lido como direção e ordem de grandeza, não como caso de
negócio.
