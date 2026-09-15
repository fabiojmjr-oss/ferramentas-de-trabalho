# oplab.benchmark — comparing sites of different size and geography

**EN** · [Português](#português)

Answers the question a regional review opens with, and refuses the two ways it is usually
answered badly: *which site is actually underperforming, once size and geography are held
constant?*

Requires the linear solver from OR-Tools: `pip install -e ".[benchmark]"`.

## Finding 1: a third of the cost gap is postcodes

The four sites do not serve the same territory. 36% of one site's deliveries fall inside 10 km;
another site has 10%:

| Site | 0–10 km | 10–25 km | 25–50 km | 50+ km |
| --- | --- | --- | --- | --- |
| CD-SP | 36.4% | 40.8% | 11.8% | 10.9% |
| CD-RJ | 26.3% | 45.2% | 13.3% | 15.2% |
| CD-RS | 15.3% | 42.0% | 22.6% | 20.0% |
| CD-PE | 9.8% | 34.1% | 31.0% | 25.1% |

Indirect standardisation asks what the **rest of the network** would spend on each site's own
distance profile, and reports the ratio:

| Site | Crude cost per order | Standardised | Ratio | Mix effect |
| --- | --- | --- | --- | --- |
| CD-PE | 119.00 | 110.32 | 1.20 | −8.68 |
| CD-RS | 97.86 | 93.13 | 1.01 | −4.73 |
| CD-RJ | 83.34 | 85.48 | 0.93 | +2.13 |
| CD-SP | 75.28 | 81.85 | 0.89 | +6.57 |

**CD-PE reads 58% more expensive than CD-SP crude, and 35% once the distance profile is held
constant.** The spread between best and worst falls from 43.72 to 28.47, so **35% of the
headline gap is geography rather than performance**. The first number sets a target nobody can
hit; the second is arguable on its merits.

The technique comes from epidemiology, where comparing crude mortality between regions of
different age structure is the textbook error. The structure of the problem in a distribution
network is identical and the technique is almost never used there — the argument goes to "our
mix is harder" and stays there.

**One detail decides whether the ratio means what it appears to.** By default a unit is part of
its own benchmark, and on a network of four that is 25% of the reference: a site 20% more
expensive than its peers in every stratum scores 1.02 rather than 1.20, because its own cost
drags the standard towards it. `exclude_self=True` compares each unit against the rest. On a
large network the difference is negligible; on a small one it is most of the signal.

## Finding 2: the same method, opposite conclusions

Under 2,000 random weightings of a four-metric scorecard:

| Comparison | Units whose rank can move | Widest swing | Verdict |
| --- | --- | --- | --- |
| The four sites | 2 of 4 | 1 place | The ranking is a fact |
| One site, month by month | **12 of 12** | **10 places** | The ranking is theatre |

Between sites, one is first under 97% of weightings and the bottom two cannot move at all —
they are worse on every dimension, so no weighting can rescue them. The argument about weights
is not worth having.

Between months at the same site, **every month's rank depends on the weighting** and one month
can come out first or near-last on identical data. Any best-month award there is a weighting
artefact.

Same tool, same method, opposite answers — **and you cannot tell which case you are in without
measuring it.** A scorecard that combines indicators has to weight them, the weights are agreed
in a meeting rather than derived from anything, and the ranking they produce is then discussed
as though it were a measurement.

## Finding 3: the network is too small for DEA, and the modelling choice proves it

DEA measures relative efficiency across several inputs and outputs without needing a price for
any of them, by letting each unit choose the weights that flatter it most. That construction is
its strength and its trap: every measure adds a degree of freedom units can use to excuse
themselves, so the literature asks for `n >= 3 x (m + s)` and `n >= m x s`.

Four sites with two inputs and two outputs needs twelve units and has four:

| Model | On the frontier | Worst site |
| --- | --- | --- |
| Constant returns (CCR) | 50% | 0.626 |
| Variable returns (BCC) | 75% | 0.895 |

Weak discrimination either way. But the more useful symptom is that the **modelling choice
moves the worst site by 27 points** — and most of that is a penalty for being small rather than
a measure of how it is run. On a network whose site sizes are a deliberate design decision,
charging a site for its size is measuring the wrong thing, and reporting only the constant-
returns number tells the smallest site it is 37% inefficient when most of that is being small.

Raising the unit count is the way out. Forty-eight site-months clear the threshold:

| Model | On the frontier | CD-PE mean | CD-SP mean |
| --- | --- | --- | --- |
| Constant returns | 8.3% | 0.621 | 0.983 |
| Variable returns | 18.8% | 0.837 | 0.986 |

It costs interpretation: a site-month is efficient relative to other site-months including its
own, so the result is about consistency over time as much as about the site.

## Usage

```python
from oplab.benchmark import indirect_standardisation, peer_z_scores, rank_stability
from oplab.synth import generate_dataset

ledger = generate_dataset().cost_ledger
# ... band the deliveries by distance, aggregate by site and band ...
print(indirect_standardisation(aggregated, "site", "band", "cost", "deliveries", exclude_self=True))
```

Full walkthrough: [`examples/08_multi_site_benchmark.py`](../../../examples/08_multi_site_benchmark.py).

## Assumptions and limitations

- **The stratum is the analysis.** Mix can only be removed along a dimension you stratify by,
  and the choice is not neutral. Stratifying by distance band removes geography and leaves the
  stop-cost difference, which is a real question; stratifying by something the sites do not
  differ on removes nothing, and on this data order size band is exactly that — a null result
  worth reporting, because it kills the mix defence on that dimension.
- **Standardisation adjusts, it does not explain.** A ratio of 1.20 says a site spends 20% more
  than the rest of the network would on its profile. It does not say why, and it will absorb a
  genuinely different input price along with genuinely worse performance.
- **Peer z-scores assume the peer group is comparable.** Standardising across groups that are
  not comparable reintroduces exactly the bias normalisation was meant to remove.
- **Rank stability samples weightings, not metrics.** It says how much of the ranking the
  weighting decides. It says nothing about whether the metrics are the right ones, or whether
  one of them is measured badly — and a badly measured metric will be given weight in every
  draw.
- **DEA is deterministic and has no error bars.** A single outlier defines the frontier for
  everyone compared against it, and there is no test of whether a score differs from one by
  more than noise. Bootstrapped DEA exists; this module does not implement it.

---

## Português

Responde à pergunta com que uma reunião regional começa, e recusa as duas formas como ela é
normalmente mal respondida: *qual unidade está de fato com desempenho abaixo, uma vez
neutralizados porte e geografia?*

### Achado 1: um terço da diferença de custo é CEP

As quatro unidades não atendem o mesmo território. 36% das entregas de uma ficam dentro de
10 km; de outra, 10%:

| Unidade | 0–10 km | 10–25 km | 25–50 km | 50+ km |
| --- | --- | --- | --- | --- |
| CD-SP | 36,4% | 40,8% | 11,8% | 10,9% |
| CD-RJ | 26,3% | 45,2% | 13,3% | 15,2% |
| CD-RS | 15,3% | 42,0% | 22,6% | 20,0% |
| CD-PE | 9,8% | 34,1% | 31,0% | 25,1% |

A padronização indireta pergunta quanto **o resto da rede** gastaria no perfil de distância de
cada unidade:

| Unidade | Custo bruto por pedido | Padronizado | Razão | Efeito mix |
| --- | --- | --- | --- | --- |
| CD-PE | 119,00 | 110,32 | 1,20 | −8,68 |
| CD-RS | 97,86 | 93,13 | 1,01 | −4,73 |
| CD-RJ | 83,34 | 85,48 | 0,93 | +2,13 |
| CD-SP | 75,28 | 81,85 | 0,89 | +6,57 |

**O CD-PE lê 58% mais caro que o CD-SP no bruto, e 35% quando o perfil de distância é
neutralizado.** A amplitude entre melhor e pior cai de 43,72 para 28,47, então **35% da
diferença de manchete é geografia, não desempenho**. O primeiro número define meta que ninguém
alcança; o segundo é discutível pelo mérito.

A técnica vem da epidemiologia, onde comparar mortalidade bruta entre regiões de estrutura
etária diferente é o erro de manual. A estrutura do problema numa rede de distribuição é
idêntica e a técnica quase nunca é usada lá — a discussão vai para "nosso mix é mais difícil" e
fica.

**Um detalhe decide se a razão significa o que parece.** Por padrão a unidade faz parte do
próprio benchmark, e numa rede de quatro isso é 25% da referência: uma unidade 20% mais cara que
as pares em todo estrato pontua 1,02 em vez de 1,20, porque o próprio custo dela puxa o padrão.
`exclude_self=True` compara cada unidade contra as demais.

### Achado 2: o mesmo método, conclusões opostas

Sob 2.000 ponderações aleatórias de um scorecard de quatro métricas:

| Comparação | Unidades cujo rank pode mudar | Maior oscilação | Veredito |
| --- | --- | --- | --- |
| As quatro unidades | 2 de 4 | 1 posição | O ranking é fato |
| Uma unidade, mês a mês | **12 de 12** | **10 posições** | O ranking é teatro |

Entre unidades, uma é primeira em 97% das ponderações e as duas últimas não se movem: são
piores em toda dimensão. A discussão sobre pesos não vale a pena.

Entre meses da mesma unidade, **o rank de todo mês depende da ponderação** e um mês pode sair
primeiro ou quase último com dados idênticos. Prêmio de melhor mês ali é artefato de peso.

Mesma ferramenta, mesmo método, respostas opostas — **e não há como saber em qual caso você está
sem medir.**

### Achado 3: a rede é pequena demais para DEA, e a escolha de modelo prova

Quatro unidades com dois insumos e dois produtos exigem doze e têm quatro:

| Modelo | Na fronteira | Pior unidade |
| --- | --- | --- |
| Retornos constantes (CCR) | 50% | 0,626 |
| Retornos variáveis (BCC) | 75% | 0,895 |

Discriminação fraca nos dois casos. Mas o sintoma mais útil é que a **escolha de modelo move a
pior unidade em 27 pontos** — e a maior parte disso é penalidade por ser pequena, não medida de
como é operada. Numa rede cujos portes são decisão deliberada de desenho, cobrar de uma unidade
o próprio tamanho é medir a coisa errada, e reportar só o número de retornos constantes diz à
menor unidade que ela é 37% ineficiente quando a maior parte disso é ser pequena.

Elevar a contagem de unidades é a saída. Quarenta e oito unidades-mês passam do limiar: 8,3% na
fronteira sob retornos constantes, 18,8% sob variáveis. O custo é de interpretação — uma
unidade-mês é eficiente em relação a outras unidades-mês, inclusive as dela própria, então o
resultado é tanto sobre consistência no tempo quanto sobre a unidade.

### Premissas e limitações

- **O estrato é a análise.** Mix só é removível na dimensão pela qual você estratifica. Nestes
  dados, faixa de tamanho de pedido não difere entre unidades — resultado nulo que vale
  reportar, porque mata a defesa do mix naquela dimensão.
- **Padronizar ajusta, não explica.** Razão de 1,20 diz que a unidade gasta 20% mais que o resto
  da rede gastaria no perfil dela. Não diz por quê, e vai absorver diferença legítima de preço
  de insumo junto com desempenho pior.
- **Estabilidade de ranking amostra pesos, não métricas.** Não diz se as métricas são as certas,
  nem se alguma está mal medida — e métrica mal medida recebe peso em todo sorteio.
- **DEA é determinístico e não tem barra de erro.** Um único ponto atípico define a fronteira
  para todos, e não há teste de se um escore difere de um por mais que ruído. DEA com bootstrap
  existe; este módulo não o implementa.
