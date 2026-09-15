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

## Finding 5: the metric that ranks a forecast is not the metric that sizes its stock

MASE is built on absolute error. A buffer is not: it has to cover the tail, so a fat-tailed
forecast costs stock out of proportion to its MAE. Scoring the same backtest both ways, against a
forecast of the training mean:

| Model | MASE | Median MAE | Median error sd | MAE vs mean | Error sd vs mean |
| --- | --- | --- | --- | --- | --- |
| mean | 0.9415 | 2.6419 | **3.2762** | — | — |
| sba | 0.9417 | 2.7147 | 3.3007 | +2.8% | +0.8% |
| tsb | 0.9455 | 2.7116 | 3.2945 | +2.6% | +0.6% |
| croston | 0.9483 | 2.7417 | 3.3046 | +3.8% | +0.9% |
| seasonal_naive | 0.9496 | 2.7698 | 4.0904 | **+4.8%** | **+24.9%** |
| naive | 1.6015 | 4.6508 | 5.6971 | +76.0% | +73.9% |

**`seasonal_naive` reads 0.9% behind the leader on MASE and a quarter worse on the quantity a
buffer is sized from** — the error spread exposes 5.1 times what the absolute error shows. Ranking
on MASE and then sizing stock is two decisions taken on two different definitions of better.

The second result in that table is blunter. **A forecast of the training mean has the lowest error
spread of the seven, so nothing here reduces the inventory buffer.** The median ratio of
forecast-error spread to demand spread is 1.0019, and the forecast reduces the buffer on 47% of
series and enlarges it on the rest. That is not a defect of the methods; it is the measurement that
says what forecasting is worth on this data, and it belongs in a business case rather than after
one. `error_profile` reports the ratio per series for exactly that reason.

## Finding 6: a per-horizon error table can be a seasonality table wearing a horizon label

| Step | Bias | Error sd | sd vs step 1 | `sqrt(step)` | `phase_locked` |
| --- | --- | --- | --- | --- | --- |
| 1 | −2.65 | 10.42 | 1.00 | 1.00 | true |
| 2 | −0.86 | 8.04 | 0.77 | 1.41 | true |
| 3 | +4.25 | 8.98 | 0.86 | 1.73 | true |
| 4 | **+8.08** | **14.08** | 1.35 | 2.00 | true |
| 7 | −3.88 | 12.89 | 1.24 | 2.65 | true |

Step 4's error averages +8.08 and varies by only 1.03 across the nine origins, against a systematic
spread of −3.88 to +8.08 between steps. **The pattern reproduces at every origin, so it is not
sampling noise** — it is the backtest's own geometry. Origins are 28 periods apart and the season is
7, so every horizon step lands on the same phase of the week, every time; step 4 is always the same
weekday, and a flat forecast carries that weekday's deviation as a constant error. The column reads
as a horizon effect and is a seasonal one. `horizon_profile` takes the step and the season and
returns a `phase_locked` flag rather than leaving it to be noticed.

**And the square-root rule does not belong in this table at all.** `sqrt(h)` describes the error of
a *cumulative* total, or of a random walk. The per-period error of a flat forecast on a stationary
series does not grow — the measured column runs 0.77 to 1.35 while `sqrt(step)` runs 1.00 to 2.65.
Inventory needs the cumulative quantity, which is why
[`oplab.inventory`](../inventory/README.md) multiplies the error *variance* by the protection
interval instead of reading a growth rate off here.

The intervals carry the same asymmetry. A nominal 95% normal interval covers 96.9% at step 3 — too
wide, not too narrow — and misses 2.9% below against 0.2% above. A symmetric interval on a skewed
error distribution is wrong twice over: it holds stock it does not need, and it misses on the side
that causes stockouts.

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
- **The prediction intervals are in-sample.** They are quantiles of the residuals they are then
  scored against, so `empirical_coverage` sits at its nominal level almost by construction and is
  not out-of-sample validation. The row that carries information is the normal one, fitted to two
  moments of the same residuals and still missing asymmetrically. A genuinely held-out interval
  needs a second split this module does not make.
- **The error profile is measured on the backtest window, and the demand benchmark with it.**
  `demand_sd` is the spread of the actuals in that window, so the ratio compares the forecast
  against the best possible *constant* forecast — one that knew the window's mean in advance. That
  makes the benchmark slightly generous to the mean strategy, and the finding that nothing beats it
  correspondingly stronger.

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

### Achado 5: a métrica que ranqueia a previsão não é a que dimensiona o estoque

O MASE é construído sobre erro absoluto. Um pulmão não é: ele tem de cobrir a cauda, então previsão
de cauda gorda custa estoque fora de proporção ao seu MAE. Medindo o mesmo backtest das duas
formas, contra uma previsão da média de treino:

| Modelo | MASE | MAE mediano | Desvio do erro | MAE vs média | Desvio vs média |
| --- | --- | --- | --- | --- | --- |
| mean | 0,9415 | 2,6419 | **3,2762** | — | — |
| sba | 0,9417 | 2,7147 | 3,3007 | +2,8% | +0,8% |
| tsb | 0,9455 | 2,7116 | 3,2945 | +2,6% | +0,6% |
| croston | 0,9483 | 2,7417 | 3,3046 | +3,8% | +0,9% |
| seasonal_naive | 0,9496 | 2,7698 | 4,0904 | **+4,8%** | **+24,9%** |
| naive | 1,6015 | 4,6508 | 5,6971 | +76,0% | +73,9% |

**O `seasonal_naive` lê 0,9% atrás do líder no MASE e um quarto pior na grandeza da qual um pulmão
é dimensionado** — o desvio do erro expõe 5,1 vezes o que o erro absoluto mostra. Ranquear por MASE
e depois dimensionar estoque são duas decisões tomadas sobre duas definições diferentes de melhor.

O segundo resultado da tabela é mais direto. **Uma previsão da média de treino tem o menor desvio de
erro entre as sete, então nada aqui reduz o pulmão de estoque.** A razão mediana entre o desvio do
erro de previsão e o desvio da demanda é 1,0019, e a previsão reduz o pulmão em 47% das séries e o
aumenta no resto. Não é defeito dos métodos; é a medição que diz quanto prever vale nestes dados, e
pertence ao business case, não a depois dele.

### Achado 6: uma tabela de erro por horizonte pode ser uma tabela de sazonalidade com rótulo errado

| Passo | Viés | Desvio | Desvio vs passo 1 | `sqrt(passo)` | `phase_locked` |
| --- | --- | --- | --- | --- | --- |
| 1 | −2,65 | 10,42 | 1,00 | 1,00 | true |
| 2 | −0,86 | 8,04 | 0,77 | 1,41 | true |
| 3 | +4,25 | 8,98 | 0,86 | 1,73 | true |
| 4 | **+8,08** | **14,08** | 1,35 | 2,00 | true |
| 7 | −3,88 | 12,89 | 1,24 | 2,65 | true |

O erro do passo 4 tem média +8,08 e varia só 1,03 entre as nove origens, contra amplitude
sistemática de −3,88 a +8,08 entre passos. **O padrão se reproduz em toda origem, então não é ruído
de amostragem** — é a geometria do próprio backtest. As origens estão a 28 períodos e a
sazonalidade é 7, então todo passo do horizonte cai na mesma fase da semana, sempre; o passo 4 é
sempre o mesmo dia da semana, e uma previsão plana carrega o desvio daquele dia como erro constante.
A coluna lê como efeito de horizonte e é efeito sazonal. O `horizon_profile` recebe o passo e a
sazonalidade e devolve um sinalizador `phase_locked` em vez de deixar isso para ser notado.

**E a regra da raiz quadrada não pertence a esta tabela.** `sqrt(h)` descreve o erro de um *total
acumulado*, ou de um passeio aleatório. O erro por período de uma previsão plana sobre série
estacionária não cresce — a coluna medida vai de 0,77 a 1,35 enquanto `sqrt(passo)` vai de 1,00 a
2,65. Estoque precisa da grandeza acumulada, e é por isso que
[`oplab.inventory`](../inventory/README.md) multiplica a *variância* do erro pelo intervalo de
proteção em vez de ler uma taxa de crescimento daqui.

Os intervalos carregam a mesma assimetria. Um intervalo normal nominal de 95% cobre 96,9% no passo 3
— largo demais, não estreito demais — e erra 2,9% abaixo contra 0,2% acima. Intervalo simétrico
sobre distribuição de erro assimétrica erra duas vezes: mantém estoque que não precisa, e erra do
lado que causa falta.

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
- **Os intervalos de previsão são in-sample.** São quantis dos resíduos contra os quais são então
  medidos, então a `empirical_coverage` fica no nível nominal quase por construção e não é validação
  fora da amostra. A linha que informa é a normal, ajustada a dois momentos dos mesmos resíduos e
  ainda assim errando assimetricamente.
- **O perfil de erro é medido na janela do backtest, e o benchmark de demanda junto.** O
  `demand_sd` é o desvio dos realizados naquela janela, então a razão compara a previsão contra a
  melhor previsão *constante* possível — uma que conhecia a média da janela de antemão. Isso torna o
  benchmark levemente generoso com a estratégia da média, e o achado de que nada a supera
  correspondentemente mais forte.
