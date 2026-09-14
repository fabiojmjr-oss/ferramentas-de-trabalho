# oplab.variance — cost and revenue variance decomposition

**EN** · [Português](#português)

Answers the question a performance review opens with: *why did this move, and who owns each
part of it?*

## The finding this module was built to produce

On the bundled cost ledger — 87,000 orders over a year, first half against second — cost per
order rose 20.7%. The decomposition is exact either way, and the segmentation decides the
answer:

| Effect | Segmented by site and order size | With channel added |
| --- | --- | --- |
| Rate | **+15.61 (99.1%)** | +11.67 (74.1%) |
| Mix | +0.14 (0.9%) | **+4.08 (25.9%)** |
| Total | +15.75 | +15.75 |

**The movement is identical. The attribution is not.** Omit the channel dimension and 99% of
the rise reads as operational. Add it and a quarter of the rise is mix — the
direct-to-consumer share grew through the year, and a home delivery costs nearly twice as much
per stop as a store delivery. That is a commercial and network decision arriving inside an
operational indicator.

**An omitted dimension does not disappear. It reappears inside the rate effect and is
attributed to whoever owns the rate.** That is the single most common way a cost review blames
the wrong function, and it is invisible because the arithmetic reconciles perfectly either way.

## The total is the wrong question

Total operating cost rose 28.1%, and 22% of that increase was volume — the same business got
bigger. A review that stops at the total treats growth as a cost problem.

Which is why the module has two entry points:

| Function | Question | Effects |
| --- | --- | --- |
| `price_volume_mix` | Why did the **total** move? | volume, mix, rate, new, discontinued |
| `unit_value_bridge` | Why did the **per-unit** metric move? | rate, mix |

## Volume cannot move a per-unit metric

The per-unit bridge has exactly two terms, and that is a fact about the arithmetic rather than
a modelling choice:

```
V1/Q1 − V0/Q0  =  Σ s1 × (r1 − r0)   +   Σ (s1 − s0) × r0
                  rate                   mix
```

So *"cost per order rose but volume grew"* is not an explanation. Growth alone is incapable of
moving a per-unit figure. Either the rates moved inside the segments, or the mix moved between
them.

⚠️ **The one real caveat.** That holds for the segment rates *as observed*. Where there is
operating leverage — fixed cost spread over a larger base — growth lowers the observed rate
inside each segment, so a volume effect is real but hiding inside the rate term. Separating it
needs a fixed and variable cost split, which this module does not attempt. With material fixed
cost, read the rate effect as *"rate net of volume dilution"* and say so out loud.

## Where mix lives, and where it does not

Per segment the split is unambiguous and exact:

```
V1 − V0  =  r0 × (q1 − q0)   +   q1 × (r1 − r0)
            quantity effect      rate effect
```

Volume and mix are the two halves of the **aggregate** quantity effect: volume is what
proportional growth would have produced, mix is the rest. **Mix does not exist per segment** —
it is by construction a statement about how segments moved relative to each other. So the
module reports quantity and rate per segment, and splits out mix only in the total. A tool
that prints a per-segment "mix" column is computing something it cannot define.

## Segments present in only one period

Most spreadsheet decompositions have no home for a launched or discontinued segment and
silently fold it into mix, which is how a product launch gets reported as an operational
deterioration. Here they get their own effects, `new` and `discontinued`.

The per-unit bridge cannot do that — a share-weighted identity has no spare term — so it
applies one stated **convention**: a new segment's mix effect is priced at the base-period
average rate, treating its arrival as mix-neutral and sending its whole departure from the
average into the rate effect. `BridgeResult.new_quantity_share` reports how much of current
quantity rests on that convention, and it is worth a glance before quoting the split.

## Exactness is the point

The effects sum to the change with **no residual** — 2.8e-14 on the bundled ledger, and asserted
on every test case. A decomposition with a plug line is not a decomposition, it is an
allocation with a plug line, and the plug is where disagreements go to hide. `waterfall()`
raises rather than draw bars that do not land on the closing total.

## Usage

```python
from oplab.synth import generate_dataset
from oplab.variance import unit_value_bridge, contribution_pareto, waterfall

ledger = generate_dataset().cost_ledger.assign(quantity=1.0)
h1 = ledger[ledger["month"] <= "2025-06"]
h2 = ledger[ledger["month"] > "2025-06"]

bridge = unit_value_bridge(
    h1, h2, key=["site", "channel", "size_band"], quantity="quantity", value="total_brl"
)
print(bridge.summary())
print(contribution_pareto(bridge, top=10))
print(waterfall(bridge))
```

Full walkthrough: [`examples/05_cost_variance.py`](../../../examples/05_cost_variance.py).

## Assumptions and limitations

- **The segmentation is the analysis.** Mix can only be seen along a dimension you segment by,
  so a decomposition finding no mix effect may simply be segmented on the wrong thing. This is
  the module's main warning and it is not something the code can check for you.
- **No fixed and variable split**, so operating leverage hides inside the rate effect, as above.
- **Two periods at a time.** There is no trend decomposition, no seasonal adjustment, and no
  statistical test of whether a movement exceeds normal variation — for that, chart it with
  `oplab.spc` before decomposing it. A decomposition of common-cause noise will produce
  confident-looking effects that mean nothing.
- **Rates are derived as value over quantity**, so a segment with quantity but no value, or the
  reverse, is refused rather than imputed.

---

## Português

Responde à pergunta com que uma reunião de resultado começa: *por que isso mudou, e quem
responde por cada parte?*

### O achado que este módulo foi construído para produzir

No razão de custos embutido — 87.000 pedidos em um ano, primeiro semestre contra segundo — o
custo por pedido subiu 20,7%. A decomposição é exata nos dois casos, e a segmentação decide a
resposta:

| Efeito | Segmentado por unidade e tamanho | Com canal adicionado |
| --- | --- | --- |
| Taxa | **+15,61 (99,1%)** | +11,67 (74,1%) |
| Mix | +0,14 (0,9%) | **+4,08 (25,9%)** |
| Total | +15,75 | +15,75 |

**O movimento é idêntico. A atribuição não é.** Omita a dimensão canal e 99% da alta lê como
operacional. Inclua-a e um quarto da alta é mix — a participação do canal direto ao consumidor
cresceu no ano, e uma entrega residencial custa quase o dobro por parada que uma entrega em
loja. É decisão comercial e de rede chegando dentro de um indicador operacional.

**Uma dimensão omitida não desaparece. Ela reaparece dentro do efeito taxa e é atribuída a quem
responde pela taxa.** É a forma mais comum de uma análise de custo culpar a área errada, e é
invisível porque a aritmética fecha perfeitamente nos dois casos.

### O total é a pergunta errada

O custo operacional total subiu 28,1%, e 22% desse aumento foi volume — o mesmo negócio ficou
maior. Uma análise que para no total trata crescimento como problema de custo.

Por isso o módulo tem duas portas de entrada: `price_volume_mix` (por que o **total** mudou:
volume, mix, taxa, novos, descontinuados) e `unit_value_bridge` (por que a métrica **por
unidade** mudou: taxa e mix).

### Volume não pode mover uma métrica por unidade

A ponte por unidade tem exatamente dois termos, e isso é um fato da aritmética, não uma escolha
de modelagem:

```
V1/Q1 − V0/Q0  =  Σ s1 × (r1 − r0)   +   Σ (s1 − s0) × r0
                  taxa                   mix
```

Logo *"o custo por pedido subiu, mas o volume cresceu"* não é explicação. Crescimento sozinho é
incapaz de mover um número por unidade.

⚠️ **A única ressalva real.** Isso vale para as taxas dos segmentos *como observadas*. Onde há
alavancagem operacional — custo fixo diluído sobre base maior — o crescimento reduz a taxa
observada dentro de cada segmento, então existe um efeito volume escondido dentro do termo de
taxa. Separá-lo exige abertura entre custo fixo e variável, que este módulo não faz. Com custo
fixo material, leia o efeito taxa como *"taxa líquida de diluição por volume"* e diga isso.

### Onde o mix existe, e onde não existe

Por segmento a separação é exata: `V1 − V0 = r0 × (q1 − q0) + q1 × (r1 − r0)`, ou seja efeito
quantidade mais efeito taxa. Volume e mix são as duas metades do efeito quantidade **agregado**:
volume é o que o crescimento proporcional teria produzido, mix é o resto. **Mix não existe por
segmento** — é por construção uma afirmação sobre como os segmentos se moveram uns em relação
aos outros. Ferramenta que imprime uma coluna "mix" por segmento está calculando algo que não
consegue definir.

### Exatidão é o ponto

Os efeitos somam à variação **sem resíduo** — 2,8e-14 no razão embutido, e verificado em todos
os casos de teste. Decomposição com linha de ajuste não é decomposição, é rateio com linha de
ajuste, e é no ajuste que as discordâncias se escondem. `waterfall()` levanta erro em vez de
desenhar barras que não fecham no total final.

### Premissas e limitações

- **A segmentação é a análise.** Mix só é visível na dimensão pela qual você segmenta.
- **Sem abertura fixo/variável**, então alavancagem operacional se esconde no efeito taxa.
- **Dois períodos por vez.** Não há decomposição de tendência, ajuste sazonal, nem teste
  estatístico de se o movimento excede a variação normal — para isso, carte com `oplab.spc`
  antes de decompor. Decompor ruído de causa comum produz efeitos de aparência confiante que
  não significam nada.
- **Taxas são derivadas de valor sobre quantidade**, então um segmento com quantidade e sem
  valor, ou o inverso, é recusado em vez de imputado.
