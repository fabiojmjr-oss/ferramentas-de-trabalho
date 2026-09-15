# oplab.mining — the value stream map, derived rather than drawn

**EN** · [Português](#português)

A value stream map drawn in a workshop is a set of estimates with a consensus attached. The same
map derived from an event log is a measurement, and on this data it disagrees with the workshop in
four specific ways.

No extra dependency and no process-mining library: `pip install -e .` The directly-follows graph is
a group-by, and conformance here is a subsequence test whose limits are stated below.

## Finding 1: the log decides what can be asked, and two defects are invisible downstream

| Log | Cases | Events | Separates work from wait |
| --- | --- | --- | --- |
| Fulfilment event log | 4,000 | 38,735 | **yes** |
| The same orders as a wide milestone table | 4,000 | 252,883 | **no** |

Two properties have to hold before any figure below means anything, and neither produces an error
when it fails.

**The case identifier has to be the case.** If the identifier is the order but the log has one row
per line, every multi-line order appears to loop through picking repeatedly — which inflates
exactly the rework figure the exercise was commissioned to find.

**Every event needs a start and a completion.** With one timestamp per milestone, the duration of
an activity cannot be separated from the wait before the next one, so flow efficiency is not
computable and every improvement target defaults to the touch time — the small half. That is the
shape operational data usually arrives in, and the second row above is the same orders reshaped
from `order_lines`: a perfectly good log for a handover analysis and no basis at all for a
value-stream one. `profile_log` reports this rather than letting a number be computed from it.

## Finding 2: 35 paths and 4 routes, and the two facts point opposite ways

| Measure | Value |
| --- | --- |
| Distinct paths in the log | 35 |
| Share of cases on the documented path | **61.1%** |
| Paths needed to cover 80% of cases | **4** |

These two are routinely collapsed into one conclusion. A path count in the tens is presented as
evidence that the process is out of control; the coverage figure says **four routes carry four
fifths of the volume**, so the process is standardisable and the rest is exceptions.

A variant count on its own cannot distinguish a process with a hundred paths where six carry the
volume from one where sixty do, and those are different problems with different remedies. The pair
is the finding, which is why `variant_coverage` returns both numbers and the top path's share.

## Finding 3: flow efficiency is 3.1%, and half of the working time is not work

| | Hours | Share of lead time |
| --- | --- | --- |
| Lead time | 43.21 | 100% |
| Working | 2.82 | 6.53% |
| Waiting | 40.39 | **93.47%** |
| Value adding | 1.34 | **3.10%** |

The figure usually quoted is the busy share, 6.53%. Flow efficiency is 3.10%, and the gap is 1.48
hours of credit checks, quality checks and repacks: **53% of all working time exists only because
something went wrong earlier.**

That third category is the one that matters politically. Inspection and correction are work by any
measure of activity and waste by any measure of value, so counting them as value-adding flatters
the result without anybody lying. `flow_efficiency` therefore takes the value-adding set as a
required argument with no default, and refuses a name that does not appear in the log — a typo
there would deflate the answer invisibly.

## Finding 4: the step that takes longest is not the step that costs most

| Activity | Executions | Waiting hours after it | Share of all waiting | Cumulative |
| --- | --- | --- | --- | --- |
| Ship | 3,911 | 57,715 | **35.7%** | 35.7% |
| Stock Shortage | 553 | 23,379 | 14.5% | 50.2% |
| Load | 3,911 | 22,399 | 13.9% | 64.1% |
| Allocate Stock | 4,464 | 18,347 | 11.4% | 75.4% |
| Credit Hold | 426 | 10,313 | 6.4% | 81.8% |

**Credit Hold has the longest touch time in the log — 6.34 hours — and holds 6.4% of all waiting.
Ship takes 3 minutes and holds 35.7%**, because it runs 3,911 times rather than 426.

A workshop nominates the step that feels slow, and it is not wrong about which step is slow. It is
wrong about which step holds the lead time, because a rare expensive step costs less in total than
a quick universal one. The cumulative column is the shortlist: **four handovers hold three quarters
of the waiting**, and nothing outside them is worth a project.

## Finding 5: a conformance figure of 97.8% on a process 61% of cases follow

| Measure | Value |
| --- | --- |
| Containment fitness | **0.9778** |
| Cases that are the documented process and nothing else | **0.6110** |

The first number is close to useless here, and it is worth seeing exactly why. A containment test
accepts a case that performs every documented step in order *plus* anything else, so the only cases
it rejects are the 89 that were cancelled and never reached delivery — and `1 − 89/4000 = 0.9778`
is the fitness to four decimals. **It is blind to the 1,467 cases that reached the end by a route
nobody documented.**

A conformance score near one is therefore not evidence of a standard process; it is evidence that
insertions are permitted by the measure. This module reports both numbers for that reason, and the
limitation of its own measure is in the module docstring rather than in a footnote.

What the deviations are, and what they cost:

| Activity | Kind | Cases | Share |
| --- | --- | --- | --- |
| Stock Shortage | inserted | 553 | 13.8% |
| Allocate Stock | repeated | 553 | 13.8% |
| Credit Hold | inserted | 426 | 10.7% |
| Quality Check | repeated | 364 | 9.1% |
| Repack | inserted | 364 | 9.1% |

| Group | Cases | Mean lead h | Mean work h | Mean wait h | Flow efficiency |
| --- | --- | --- | --- | --- | --- |
| Follows the documented path | 2,444 | 30.94 | 1.70 | 29.24 | 4.42% |
| Deviates | 1,556 | **62.49** | 4.58 | 57.90 | **2.07%** |

**A deviating case takes 2.0 times as long, and its flow efficiency is worse rather than equal** —
proportionally more of its longer lead time is spent waiting, so it is not simply a longer run
through the same process.

That pair of rows is the business case. A variant count says the process is not standard, which
invites an argument about whether that matters. This says what the non-standard cases cost, which
is a question a sponsor can answer.

## Usage

```python
from oplab.mining import flow_efficiency, profile_log, variant_coverage, waiting_ranked
from oplab.synth import VALUE_ADDING, generate_dataset

log = generate_dataset().order_events
print(profile_log(log).separates_work_from_wait)  # check before concluding
print(variant_coverage(log, target=0.8))  # (4, 35, 0.611)
print(flow_efficiency(log, VALUE_ADDING).flow_efficiency)
print(waiting_ranked(log).head())
```

Full walkthrough: [`examples/11_process_mining.py`](../../../examples/11_process_mining.py).

## Assumptions and limitations

- **Conformance here is a subsequence test, not an alignment.** It cannot detect two documented
  steps performed in the wrong order when both appear in the right relative positions somewhere in
  the trace, and it says nothing about concurrency. For a sequential fulfilment process that is the
  right tool; for a process with genuine parallelism it is not, and the alternative is an aligner
  this module does not implement. Finding 5 is partly a statement about that limit.
- **The directly-follows graph is not a process model.** It records which activity followed which,
  which is not the same as which activity *may* follow which. It cannot express a choice, a
  parallel split, or a loop boundary, and inferring any of those from edge frequencies is a
  judgement the graph does not make for you.
- **No filter is applied, and that is deliberate.** A discovered graph on a real log has a long
  tail of edges traversed once or twice, and drawing all of them produces the picture people call
  spaghetti — which then gets used as evidence that the process is chaotic when it is mostly
  evidence that nobody filtered. Every edge carries its frequency share so the filter is a decision
  with a number attached.
- **Rework is counted as a repeated activity in a case**, which conflates a genuine loop with a
  step legitimately performed twice on different items. On a case granularity coarser than the real
  case this measure is not merely noisy, it is wrong, and `profile_log` is the check.
- **The value-adding set is a judgement, and it is the largest single lever on the headline
  figure.** Quality Check is excluded here on the grounds that inspection is the cost of not
  getting it right the first time. That is defensible and it is a choice; moving it changes flow
  efficiency by more than any process improvement in this analysis would.
- **The deviating group includes the cancellations**, which end early and therefore read short:
  62.49 hours with them, 64.05 without. The published figure is the conservative one, and the
  grouping is deliberate — a cancelled order is a case that left the documented path, and
  excluding it would remove the cheapest deviations from a comparison about what deviating
  costs.
- **Lead time is measured from the first event to the last**, so a case still in progress at the end
  of the log is truncated and reads short. `case_times` reports the first and last activity of every
  case so those can be identified rather than averaged in.
- **Waiting is attributed to the activity before it.** That is the useful attribution for finding a
  handover to fix, and it is not a claim about which team owns the delay — the wait after picking
  may belong entirely to the next step's queue.

---

## Português

Um mapa de fluxo de valor desenhado em workshop é um conjunto de estimativas com consenso
anexado. O mesmo mapa derivado de um log de eventos é uma medição, e nestes dados discorda do
workshop em quatro pontos específicos.

### Achado 1: o log decide o que pode ser perguntado, e dois defeitos são invisíveis depois

| Log | Casos | Eventos | Separa trabalho de espera |
| --- | --- | --- | --- |
| Log de eventos de atendimento | 4.000 | 38.735 | **sim** |
| Os mesmos pedidos como tabela larga de marcos | 4.000 | 252.883 | **não** |

**O identificador de caso tem de ser o caso.** Se o identificador é o pedido mas o log tem uma
linha por item, todo pedido multi-item parece passar por picking várias vezes — o que infla
exatamente a medida de retrabalho que motivou o trabalho.

**Todo evento precisa de início e fim.** Com um único timestamp por marco, a duração da atividade
não se separa da espera até a próxima, então a eficiência de fluxo não é calculável e todo alvo de
melhoria recai sobre o tempo de toque — a metade pequena. É a forma em que dado operacional chega,
e a segunda linha acima são os mesmos pedidos remodelados a partir de `order_lines`: log perfeito
para análise de passagens e base nenhuma para mapa de fluxo de valor.

### Achado 2: 35 caminhos e 4 rotas, e os dois fatos apontam para lados opostos

| Medida | Valor |
| --- | --- |
| Caminhos distintos no log | 35 |
| Parcela de casos no caminho documentado | **61,1%** |
| Caminhos necessários para cobrir 80% dos casos | **4** |

Os dois são rotineiramente colapsados numa conclusão. Contagem de caminhos na casa das dezenas é
apresentada como prova de processo fora de controle; a cobertura diz que **quatro rotas carregam
quatro quintos do volume**, então o processo é padronizável e o resto é exceção.

Contagem de variantes sozinha não distingue um processo com cem caminhos em que seis carregam o
volume de um em que sessenta carregam — problemas diferentes com remédios diferentes.

### Achado 3: a eficiência de fluxo é 3,1%, e metade do tempo de trabalho não é trabalho

| | Horas | Parcela do lead time |
| --- | --- | --- |
| Lead time | 43,21 | 100% |
| Trabalhando | 2,82 | 6,53% |
| Esperando | 40,39 | **93,47%** |
| Agregando valor | 1,34 | **3,10%** |

O número usualmente citado é a parcela ocupada, 6,53%. A eficiência de fluxo é 3,10%, e a diferença
é 1,48 hora de análise de crédito, inspeção e reembalagem: **53% de todo o tempo de trabalho existe
só porque algo deu errado antes.**

Inspeção e correção são trabalho por qualquer medida de atividade e desperdício por qualquer medida
de valor, então contá-las como valor embeleza o resultado sem ninguém mentir. Por isso
`flow_efficiency` exige o conjunto de atividades que agregam valor como argumento, sem padrão, e
recusa um nome que não exista no log.

### Achado 4: o passo mais demorado não é o passo mais caro

| Atividade | Execuções | Horas de espera depois | Parcela da espera | Acumulado |
| --- | --- | --- | --- | --- |
| Ship | 3.911 | 57.715 | **35,7%** | 35,7% |
| Stock Shortage | 553 | 23.379 | 14,5% | 50,2% |
| Load | 3.911 | 22.399 | 13,9% | 64,1% |
| Allocate Stock | 4.464 | 18.347 | 11,4% | 75,4% |
| Credit Hold | 426 | 10.313 | 6,4% | 81,8% |

**O Credit Hold tem o maior tempo de toque do log — 6,34 horas — e detém 6,4% de toda a espera. O
Ship leva 3 minutos e detém 35,7%**, porque roda 3.911 vezes e não 426.

O workshop indica o passo que *parece* lento, e não erra sobre qual é lento. Erra sobre qual detém
o lead time, porque passo raro e caro custa menos no total que passo rápido e universal. A coluna
acumulada é a lista curta: **quatro passagens detêm três quartos da espera**.

### Achado 5: conformidade de 97,8% num processo que 61% dos casos seguem

| Medida | Valor |
| --- | --- |
| Fitness por contenção | **0,9778** |
| Casos que são o processo documentado e nada mais | **0,6110** |

O primeiro número é quase inútil aqui, e vale ver por quê. Um teste de contenção aceita o caso que
executa todo passo documentado em ordem *mais* qualquer outra coisa, então os únicos casos que ele
rejeita são os 89 cancelados que nunca chegaram à entrega — e `1 − 89/4000 = 0,9778` é o fitness
com quatro decimais. **Ele é cego aos 1.467 casos que chegaram ao fim por rota que ninguém
documentou.**

Escore de conformidade perto de um não é prova de processo padronizado; é prova de que a medida
permite inserções.

| Grupo | Casos | Lead médio (h) | Trabalho (h) | Espera (h) | Eficiência de fluxo |
| --- | --- | --- | --- | --- | --- |
| Segue o caminho documentado | 2.444 | 30,94 | 1,70 | 29,24 | 4,42% |
| Desvia | 1.556 | **62,49** | 4,58 | 57,90 | **2,07%** |

**Um caso que desvia leva 2,0 vezes mais tempo, e sua eficiência de fluxo é pior, não igual** —
proporcionalmente mais do lead time maior é espera. Esse par de linhas é o business case: contagem
de variantes diz que o processo não é padrão, o que convida a discutir se isso importa; isto diz
quanto os casos fora do padrão custam.

### Premissas e limitações

- **Conformidade aqui é teste de subsequência, não alinhamento.** Não detecta dois passos
  documentados executados na ordem errada quando ambos aparecem nas posições relativas corretas em
  algum ponto do trace, e não diz nada sobre concorrência. Para processo sequencial é a ferramenta
  certa; para processo com paralelismo real não é. O achado 5 é em parte uma afirmação sobre esse
  limite.
- **O grafo de sucessão direta não é um modelo de processo.** Registra qual atividade seguiu qual,
  o que não é o mesmo que qual *pode* seguir qual. Não expressa escolha, divisão paralela nem
  fronteira de laço.
- **Nenhum filtro é aplicado, e isso é deliberado.** Grafo descoberto em log real tem cauda longa
  de arestas percorridas uma ou duas vezes, e desenhar todas produz a figura que chamam de
  espaguete — depois usada como prova de que o processo é caótico quando é sobretudo prova de que
  ninguém filtrou. Toda aresta traz sua parcela de frequência.
- **Retrabalho é contado como atividade repetida no caso**, o que confunde laço genuíno com passo
  legitimamente executado duas vezes em itens diferentes. Com granularidade de caso mais grossa que
  o caso real, essa medida não é apenas ruidosa, é errada.
- **O conjunto que agrega valor é julgamento, e é a maior alavanca sobre o número de manchete.** O
  Quality Check está fora aqui porque inspeção é o custo de não acertar na primeira. É defensável e
  é escolha; movê-lo muda a eficiência de fluxo mais que qualquer melhoria de processo nesta
  análise.
- **O grupo que desvia inclui os cancelamentos**, que terminam cedo e por isso leem curto: 62,49
  horas com eles, 64,05 sem. O número publicado é o conservador, e o agrupamento é deliberado —
  pedido cancelado é caso que saiu do caminho documentado, e excluí-lo removeria os desvios mais
  baratos de uma comparação sobre quanto desviar custa.
- **Lead time é medido do primeiro ao último evento**, então caso em andamento no fim do log fica
  truncado e lê curto. `case_times` reporta primeira e última atividade de cada caso para que
  possam ser identificados em vez de entrarem na média.
- **A espera é atribuída à atividade anterior a ela.** É a atribuição útil para achar a passagem a
  corrigir, e não é afirmação sobre qual equipe é dona do atraso.
