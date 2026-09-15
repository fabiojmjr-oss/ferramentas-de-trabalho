# oplab.forecast — the harness a forecasting proposal has to survive

**EN** · [Português](#português)

This is not a forecasting library. It is the set of checks that decide whether a forecasting
project is worth funding, plus reference implementations of the baselines it has to beat. The
most common defect in a demand-planning initiative is not a weak model — it is the absence of
anything to compare the model against, and a metric that cannot be computed on the data it is
quoted for.

No extra dependency: `pip install -e .`

## Finding 1: one year of weekly data cannot support a seasonal baseline, and nothing warns you

The default extract for an annual seasonality study is weekly buckets over a year. That is
53 periods:

| Grid | Periods | Season | Training window | Seasonal baseline | Scaled metrics |
| --- | --- | --- | --- | --- | --- |
| Weekly, annual season | 53 | 52 | 40 | **unavailable** | **all `nan`** |
| Daily, weekly season | 365 | 7 | 120 | available, 9 origins | available |

Every week of the year is observed exactly once, so there is no repetition either to learn a
seasonal profile from or to validate one against. The failure is not that it is hard — it is
that **nothing raises**. `seasonal_naive` falls back to `naive` when the history is shorter than
one season, every scaled metric returns `nan`, and the deck still has a number on the slide.

`season_feasibility(periods, season, min_train, horizon, step)` is the check that belongs before
any model is fitted. It answers three separate questions — is a season inside the training
window, are there at least two seasons to measure over, how many origins does the backtest
actually get — and returns them rather than a single boolean, because the three have different
remedies.

## Finding 2: MAPE is undefined on 99% of the assortment it is quoted for

MAPE is the metric in every planning target because it reads as a percentage. On this data:

| Basis | MAPE is defined on |
| --- | --- |
| Period-observations | 58.4% |
| Series with **no** undefined period | **1.0%** |
| Series with no defined period at all | 0 of 400 |

Division by a zero actual is undefined, and on intermittent demand zero is the modal actual.
**99% of SKUs have at least one period where MAPE does not exist**, so the reported figure is
always an average over a filtered subset — and the filter removes exactly the items that are
hard to plan.

It is also asymmetric in the expensive direction: forecasting five against an actual of one
scores 400%, forecasting zero against the same actual scores 100%. A model tuned on MAPE learns
to forecast low, which on a service item is the wrong side to be wrong on.

MASE and RMSSE scale the error by the in-sample naive error of the same series. They are defined
at zero, comparable across series, and a value below 1.0 has a fixed meaning: better than the
naive rule on that series' own history.

## Finding 3: the best model is a property of the segment, not of the assortment

Seven methods, rolling origin, 9 origins, horizon 7, against `seasonal_naive`:

**Regular series** (≤50% empty periods) — 260 series:

| Model | MASE | RMSSE | Bias | Relative MASE | Share of series beaten |
| --- | --- | --- | --- | --- | --- |
| sba | **0.9417** | 0.7886 | +0.0047 | 0.9917 | 54.2% |
| tsb | 0.9455 | 0.7902 | +0.4792 | 0.9956 | 51.5% |
| croston | 0.9483 | 0.7928 | +0.4735 | 0.9986 | 51.9% |
| seasonal_naive | 0.9496 | 0.9396 | +0.4394 | 1.0000 | — |
| moving_average | 1.0060 | 0.8484 | +0.8379 | 1.0593 | 38.1% |
| naive | 1.6015 | 1.5562 | +5.9861 | 1.6865 | 11.2% |
| drift | 1.6185 | 1.5760 | +6.0130 | 1.7044 | 10.0% |

**Sparse series** (>50% empty periods) — 140 series:

| Model | MASE | RMSSE | Bias | Relative MASE | Share of series beaten |
| --- | --- | --- | --- | --- | --- |
| tsb | **1.0890** | 0.7093 | +0.0045 | 0.9346 | 60.7% |
| sba | 1.1400 | 0.7053 | +0.0108 | 0.9783 | 52.9% |
| seasonal_naive | 1.1653 | 1.0780 | +0.0146 | 1.0000 | — |
| moving_average | 1.1661 | 0.7678 | +0.0240 | 1.0007 | 55.7% |
| croston | 1.1686 | 0.7068 | +0.0185 | 1.0029 | 50.0% |
| naive | 1.5393 | 1.1923 | +0.0899 | 1.3210 | 50.7% |
| drift | 1.5632 | 1.2052 | +0.0923 | 1.3415 | 50.0% |

Three things to take from the pair of tables.

**The headroom on the regular half is 0.8%.** The best of seven beats a one-line rule by
0.8% and wins on 54% of series — a coin flip. A proposal promising a large accuracy gain on this
data is promising something the data does not contain. That is not an argument against
forecasting; it is an argument for knowing the number before the business case is written.

**On the sparse half nothing reaches MASE < 1.0.** The best is 1.0890 — worse than the naive
benchmark it is scaled against, even though it is 6.5% better than the seasonal rule. On that
part of the assortment the honest plan is an availability decision (stock a position, or do not
carry the item) rather than a forecast.

**The leader changes between the halves.** TSB wins on sparse and loses on regular, because it
is the only method here that updates the demand *probability* in empty periods and so can notice
an item going quiet. Picking one model for the whole assortment means being wrong on one half of
it by construction.

And the bias column carries a separate result: **Croston's bias is +0.4735 units a day and
SBA's is +0.0047 — a 5% multiplicative correction removes 99% of it**, because the bias is
proportional to the rate, which is exactly what the Syntetos-Boylan correction was derived for.
A theoretical correction reproducing its claimed effect on data it never saw is the most
reassuring result in this module.

## Finding 4: aggregation shrinks error and leaves bias untouched

The same forecast, scored at item-site level and at network total:

| Level | Series | MASE | Bias |
| --- | --- | --- | --- |
| Per SKU and site | 1,599 | 1.1605 | −0.0367 |
| Network total | 1 | **0.8480** | **−58.6667** |

**Error:** the total scores 26.9% better relative to its own naive benchmark, because errors on
the parts partly cancel when summed. A headline "forecast accuracy" figure is almost always an
accuracy figure for an aggregate, and says close to nothing about whether any single item can be
replenished from it.

**Bias:** mean bias per series −0.036690 × 1,599 series = **−58.6667**, and the bias of the
total is −58.6667. Identical to the last digit, because bias is additive and error is not. A
bias too small to argue about on one item is the same bias, undiminished, on the warehouse — and
it compounds into inventory in one direction for as long as it runs.

## Usage

```python
from oplab.forecast import BASELINES, backtest_panel, season_feasibility, summarise, to_panel
from oplab.synth import generate_dataset

demand = generate_dataset().demand
panel = to_panel(demand, freq="D")

check = season_feasibility(periods=len(panel.index), season=7, min_train=120, horizon=7, step=28)
print(check.usable, check.origins)  # True 9

results = backtest_panel(panel, BASELINES, horizon=7, step=28, min_train=120, season=7)
print(summarise(results, panel, reference="seasonal_naive", season=7, min_train=120))
```

Full walkthrough: [`examples/09_forecast_baseline.py`](../../../examples/09_forecast_baseline.py).

## Assumptions and limitations

- **These are baselines, not a model library.** Seven one-line rules and the three intermittent-
  demand methods. There is no ETS, no ARIMA, no gradient boosting, and no exogenous regressor —
  the point of the module is the harness, and a serious model should be run through the same
  harness and compared on the same table.
- **A rolling origin is not a rolling refit.** Each origin refits the baselines from scratch on
  the history available at that origin, which is the correct protocol; it is still a single
  fixed-window evaluation, not a live re-forecast with the data revisions a real planning cycle
  has.
- **MASE and RMSSE are scaled by the in-sample naive error, so a series with no in-sample
  variation has no scale.** `summarise` reports `series_without_scale` rather than dropping them
  silently, because on a flat or near-flat series the denominator, not the model, decides the
  number.
- **The pooled mean across series is dominated by the noisiest series.** `beats_reference_share`
  is there because the pooled figure and the per-series win rate can point in different
  directions, and the second is the one an assortment decision needs.
- **The segment split is a threshold on zero share, and thresholds are arguable.** 50% empty
  periods is a convention, not a derived cut. The result that the leader changes across the cut
  is robust to moving it; the exact MASE values are not.
- **No prediction intervals.** Every method here returns a point forecast. Safety stock needs a
  distribution of forecast error, not a point — that is the neighbouring problem, and it lives in
  `oplab.inventory`.

---

## Português

Isto não é uma biblioteca de previsão. É o conjunto de verificações que decide se um projeto de
previsão vale o investimento, mais implementações de referência dos baselines que ele precisa
superar. O defeito mais comum numa iniciativa de planejamento de demanda não é um modelo fraco —
é a ausência de algo contra o que comparar o modelo, e uma métrica que não pode ser calculada nos
dados para os quais é citada.

### Achado 1: um ano de dados semanais não sustenta baseline sazonal, e nada avisa

O extrato padrão para estudar sazonalidade anual é bucket semanal ao longo de um ano. São 53
períodos:

| Grade | Períodos | Sazonalidade | Janela de treino | Baseline sazonal | Métricas escaladas |
| --- | --- | --- | --- | --- | --- |
| Semanal, sazonalidade anual | 53 | 52 | 40 | **indisponível** | **tudo `nan`** |
| Diária, sazonalidade semanal | 365 | 7 | 120 | disponível, 9 origens | disponível |

Cada semana do ano é observada uma única vez: não há repetição nem para aprender o perfil
sazonal nem para validá-lo. A falha não é ser difícil — é que **nada levanta erro**. O
`seasonal_naive` cai para `naive` quando o histórico é menor que uma sazonalidade, toda métrica
escalada retorna `nan`, e o slide continua com um número.

`season_feasibility()` é a checagem que pertence antes de qualquer modelo. Responde três
perguntas separadas — cabe uma sazonalidade na janela de treino, há pelo menos duas para medir,
quantas origens o backtest efetivamente ganha — e as devolve em vez de um booleano, porque as
três têm remédios diferentes.

### Achado 2: o MAPE é indefinido em 99% do sortimento para o qual é citado

| Base | MAPE definido em |
| --- | --- |
| Observações período a período | 58,4% |
| Séries **sem nenhum** período indefinido | **1,0%** |
| Séries sem nenhum período definido | 0 de 400 |

Divisão por realizado zero é indefinida, e em demanda intermitente zero é o realizado mais
frequente. **99% dos SKUs têm ao menos um período em que o MAPE não existe**, então o número
reportado é sempre média sobre subconjunto filtrado — e o filtro remove justamente os itens
difíceis de planejar.

É também assimétrico na direção caríssima: prever cinco contra realizado de um dá 400%, prever
zero contra o mesmo realizado dá 100%. Modelo calibrado em MAPE aprende a prever baixo, que em
item de serviço é o lado errado de errar.

MASE e RMSSE escalam o erro pelo erro naive in-sample da própria série: definidos no zero,
comparáveis entre séries, e abaixo de 1,0 significa melhor que a regra naive no histórico dela.

### Achado 3: o melhor modelo é propriedade do segmento, não do sortimento

Sete métodos, origem móvel, 9 origens, horizonte 7, contra `seasonal_naive`:

**Séries regulares** (≤50% de períodos vazios) — 260 séries:

| Modelo | MASE | RMSSE | Viés | MASE relativo | % de séries superadas |
| --- | --- | --- | --- | --- | --- |
| sba | **0,9417** | 0,7886 | +0,0047 | 0,9917 | 54,2% |
| tsb | 0,9455 | 0,7902 | +0,4792 | 0,9956 | 51,5% |
| croston | 0,9483 | 0,7928 | +0,4735 | 0,9986 | 51,9% |
| seasonal_naive | 0,9496 | 0,9396 | +0,4394 | 1,0000 | — |
| moving_average | 1,0060 | 0,8484 | +0,8379 | 1,0593 | 38,1% |
| naive | 1,6015 | 1,5562 | +5,9861 | 1,6865 | 11,2% |
| drift | 1,6185 | 1,5760 | +6,0130 | 1,7044 | 10,0% |

**Séries esparsas** (>50% de períodos vazios) — 140 séries:

| Modelo | MASE | RMSSE | Viés | MASE relativo | % de séries superadas |
| --- | --- | --- | --- | --- | --- |
| tsb | **1,0890** | 0,7093 | +0,0045 | 0,9346 | 60,7% |
| sba | 1,1400 | 0,7053 | +0,0108 | 0,9783 | 52,9% |
| seasonal_naive | 1,1653 | 1,0780 | +0,0146 | 1,0000 | — |
| moving_average | 1,1661 | 0,7678 | +0,0240 | 1,0007 | 55,7% |
| croston | 1,1686 | 0,7068 | +0,0185 | 1,0029 | 50,0% |
| naive | 1,5393 | 1,1923 | +0,0899 | 1,3210 | 50,7% |
| drift | 1,5632 | 1,2052 | +0,0923 | 1,3415 | 50,0% |

**O ganho disponível na metade regular é de 0,8%.** O melhor de sete supera uma regra de uma
linha em 0,8% e vence em 54% das séries — cara ou coroa. Proposta que promete grande ganho de
acuracidade nestes dados promete algo que os dados não contêm. Não é argumento contra prever; é
argumento para saber o número antes de escrever o business case.

**Na metade esparsa nada chega a MASE < 1,0.** O melhor é 1,0890 — pior que o benchmark naive
contra o qual é escalado, ainda que 6,5% melhor que a regra sazonal. Naquela parte do sortimento
o plano honesto é decisão de disponibilidade (posicionar estoque, ou não carregar o item), não
previsão.

**O líder muda entre as metades.** O TSB vence na esparsa e perde na regular, porque é o único
método aqui que atualiza a *probabilidade* de demanda nos períodos vazios e portanto percebe item
saindo de linha. Escolher um modelo para todo o sortimento é errar em metade dele por construção.

E a coluna de viés traz resultado separado: **o viés do Croston é +0,4735 unidade/dia e o do SBA
é +0,0047 — correção multiplicativa de 5% remove 99% dele**, porque o viés é proporcional à taxa,
que é exatamente para o que a correção de Syntetos-Boylan foi derivada.

### Achado 4: agregar encolhe o erro e não toca no viés

| Nível | Séries | MASE | Viés |
| --- | --- | --- | --- |
| Por SKU e unidade | 1.599 | 1,1605 | −0,0367 |
| Total da rede | 1 | **0,8480** | **−58,6667** |

**Erro:** o total pontua 26,9% melhor contra o próprio benchmark naive, porque os erros das
partes se cancelam parcialmente na soma. Manchete de "acuracidade de previsão" é quase sempre
acuracidade de um agregado, e diz quase nada sobre reabastecer um item.

**Viés:** viés médio por série −0,036690 × 1.599 séries = **−58,6667**, e o viés do total é
−58,6667. Idêntico até o último dígito, porque viés é aditivo e erro não é. Viés pequeno demais
para discutir num item é o mesmo viés, sem diminuição, no armazém — e acumula em estoque numa
única direção enquanto durar.

### Premissas e limitações

- **São baselines, não biblioteca de modelos.** Não há ETS, ARIMA, gradient boosting nem
  regressor exógeno — o objetivo é o harness, e um modelo sério deve passar pelo mesmo harness e
  ser comparado na mesma tabela.
- **Origem móvel não é refit contínuo.** Cada origem reajusta os baselines com o histórico
  daquela origem, que é o protocolo correto; ainda é avaliação de janela fixa, não re-previsão ao
  vivo com as revisões de dados de um ciclo real de planejamento.
- **MASE e RMSSE escalam pelo erro naive in-sample, então série sem variação in-sample não tem
  escala.** `summarise` reporta `series_without_scale` em vez de descartar em silêncio.
- **A média agrupada entre séries é dominada pelas séries mais ruidosas.** O
  `beats_reference_share` existe porque a média agrupada e a taxa de vitória por série podem
  apontar em direções diferentes, e a segunda é a que uma decisão de sortimento precisa.
- **O corte de segmento é um limiar sobre share de zeros, e limiar é discutível.** 50% é
  convenção, não corte derivado. O resultado de que o líder muda no corte é robusto a movê-lo; os
  valores exatos de MASE não são.
- **Não há intervalo de previsão.** Todo método aqui devolve previsão pontual. Estoque de
  segurança precisa da distribuição do erro, não do ponto — esse é o problema vizinho, e mora em
  `oplab.inventory`.
