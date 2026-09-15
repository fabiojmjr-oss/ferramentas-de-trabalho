# oplab.simulation — discrete-event simulation of a distribution centre

**EN** · [Português](#português)

Answers the question a static capacity spreadsheet cannot: **where is the constraint, and what
does relieving it buy?**

## The finding this module was built to produce

The uncomfortable version. On the bundled operation — 900 orders and 24 inbound trucks a day on
a single eight-hour shift — the spreadsheet's utilisation figures are **correct**:

| Resource | Spreadsheet | Simulated | Mean wait | Total waiting caused |
| --- | --- | --- | --- | --- |
| Inbound dock (4) | 61.2% | 61.6% | 0.32 h | 153 h |
| Unloading (4) | 61.2% | 61.6% | 0.00 h | 0 h |
| Put-away (6) | 46.7% | 46.7% | 0.00 h | 1 h |
| Picking (18) | 78.3% | 77.9% | 1.49 h | **26,425 h** |
| Checking (5) | 96.0% | 95.3% | 0.54 h | 9,622 h |

Utilisation is conserved, so dividing mean work by mean capacity computes it correctly. The
spreadsheet is not wrong about arithmetic — it is answering a question nobody asked.

**Utilisation ranks nothing.** Picking sits at 78% and causes nearly three times the waiting of
checking at 95%. Orders are released to the pick face in two waves, so every order queues
behind half a day's work the moment it arrives. That is a release policy, not a capacity
shortfall, and no utilisation figure can tell the two apart.

## What that does to the investment decision

Five options, six replications each, 95% confidence, ranked on mean order cycle time:

| Scenario | Cycle time | Change | Distinguishable from base |
| --- | --- | --- | --- |
| **Release in 8 waves instead of 2** | 0.82 h | **−61.7%** | Yes |
| +2 checking stations | 1.68 h | −22.0% | Yes |
| Shift 8 h to 10 h | 2.02 h | −6.1% | Yes |
| Base | 2.15 h | — | — |
| +2 inbound doors | 2.15 h | 0.0% | **No** |
| +4 pickers | 2.17 h | +0.7% | **No** |

**The free operational change recovers 2.8 times what the best paid option does.** Levelling
the release costs nothing and needs no approval, and it beats adding 40% to the checking team.

**Four more pickers cannot be shown to do anything.** That is the intuitive move — aimed at the
resource with the longest queue and the largest team — and its confidence interval overlaps the
base. Without the interval, its point estimate would have been reported as a result. It moved
the wrong way.

Two more inbound doors change the outbound cycle time by exactly zero, and in this model
*provably* must: inbound and outbound share no resource, so an inbound investment is
arithmetically incapable of moving an outbound metric. In an operation that cross-deploys
labour between the two, it would — which is a limitation of this model, stated below.

## One run is a sample of one

Reporting a single run as "the answer" is the most common defect in home-made capacity studies,
and near saturation two runs of the same configuration with different seeds can differ by half
on mean waiting time. So `replicate` runs independent seeds and reports an interval, and
`compare_scenarios` refuses to declare a winner on overlapping intervals — it reports the
overlap in a `distinguishable` column instead.

The interval also does quieter work. At four replications the ten-hour shift is *not*
distinguishable from the base; at six it is. The effect was always there; four runs were not
enough to see it. A study that reports one run has no way of knowing which situation it is in.

## Detention is invisible to utilisation

Inbound docks run at 62%, which reads as ample. They also spend 768 hours over 20 days occupied
while the operation is closed — trailers parked on a door waiting for the next shift. That is
detention, it is what the carrier bills for, and no utilisation figure contains it.
`held_while_closed_h` reports it separately, and for labour resources the same column exposes a
modelling artefact rather than a cost: see the limitations.

## Usage

```python
from oplab.simulation import SimConfig, run_once, replicate, compare_scenarios

config = SimConfig()
result = run_once(config)
print(result.capacity_review())  # the spreadsheet answer beside what it omits
print(result.utilisation_ranks_nothing())
print(result.bottleneck())

print(replicate(config, replications=6))  # with intervals
print(compare_scenarios(config, {"release in 8 waves": {"release_waves": 8}}))
```

Full walkthrough: [`examples/06_capacity_simulation.py`](../../../examples/06_capacity_simulation.py).

Install the extra: `pip install -e ".[simulation]"`.

## Assumptions and limitations

- **Inbound and outbound share no labour.** Put-away operators and pickers are separate pools.
  In an operation that cross-deploys between the two, the constraint moves differently and this
  model overstates how binding each pool is on its own — and understates the value of
  flexibility.
- **A task interrupted by the shift break keeps its resource overnight.** For a dock that is
  correct: the trailer is parked on it. For labour it is an artefact, which is why held-while-
  closed time is reported separately rather than folded into utilisation.
- **Absenteeism is a deterministic haircut** on staffing. Day-to-day variation in who shows up
  is not modelled, and that variation is a real source of the bad days.
- **Out of scope:** outbound loading and dispatch, replenishment from bulk to the pick face
  (which competes with picking for the same aisles), travel distance inside the pick area (see
  `oplab.slotting`), and any shift crossing midnight.
- **Confidence intervals are a normal approximation** on the replication mean, so a quantity
  bounded at zero and estimated near it can produce a negative lower bound. It is not clamped:
  the impossible bound is the honest signal that the estimate is imprecise relative to its own
  magnitude.
- **Service times are lognormal** with a single configurable coefficient of variation. Real task
  times are often bimodal — a normal pick and an exception — and a single distribution cannot
  represent that.

---

## Português

Responde à pergunta que uma planilha estática de capacidade não responde: **onde está a
restrição, e o que aliviá-la compra?**

### O achado que este módulo foi construído para produzir

A versão desconfortável. Na operação embutida — 900 pedidos e 24 caminhões de recebimento por
dia, em um turno único de oito horas — os números de utilização da planilha estão **corretos**:

| Recurso | Planilha | Simulado | Espera média | Espera total causada |
| --- | --- | --- | --- | --- |
| Doca de recebimento (4) | 61,2% | 61,6% | 0,32 h | 153 h |
| Descarga (4) | 61,2% | 61,6% | 0,00 h | 0 h |
| Armazenagem (6) | 46,7% | 46,7% | 0,00 h | 1 h |
| Separação (18) | 78,3% | 77,9% | 1,49 h | **26.425 h** |
| Conferência (5) | 96,0% | 95,3% | 0,54 h | 9.622 h |

Utilização é conservada, então dividir trabalho médio por capacidade média a calcula
corretamente. A planilha não erra a aritmética — ela responde a uma pergunta que ninguém fez.

**Utilização não ordena nada.** A separação está a 78% e causa quase três vezes a espera da
conferência a 95%. Os pedidos são liberados à área de picking em duas ondas, então cada pedido
entra na fila atrás de meio dia de trabalho no instante em que chega. Isso é política de
liberação, não falta de capacidade, e nenhum índice de utilização distingue os dois.

### O que isso faz com a decisão de investimento

Cinco opções, seis replicações cada, 95% de confiança, ordenadas por tempo de ciclo médio:

| Cenário | Tempo de ciclo | Variação | Distinguível da base |
| --- | --- | --- | --- |
| **Liberar em 8 ondas em vez de 2** | 0,82 h | **−61,7%** | Sim |
| +2 postos de conferência | 1,68 h | −22,0% | Sim |
| Turno de 8 h para 10 h | 2,02 h | −6,1% | Sim |
| Base | 2,15 h | — | — |
| +2 docas de recebimento | 2,15 h | 0,0% | **Não** |
| +4 separadores | 2,17 h | +0,7% | **Não** |

**A mudança operacional gratuita recupera 2,8 vezes o que a melhor opção paga recupera.**
Nivelar a liberação não custa nada e não precisa de aprovação, e supera acrescentar 40% à
equipe de conferência.

**Quatro separadores a mais não demonstram efeito algum.** É o movimento intuitivo — dirigido ao
recurso com a maior fila e a maior equipe — e o intervalo de confiança dele se sobrepõe ao da
base. Sem o intervalo, a estimativa pontual teria sido reportada como resultado. Ela se moveu
para o lado errado.

### Uma rodada é uma amostra de um

Reportar uma rodada única como "a resposta" é o defeito mais comum em estudos de capacidade
caseiros, e perto da saturação duas rodadas da mesma configuração com sementes diferentes podem
divergir pela metade na espera média. Por isso `replicate` roda sementes independentes e reporta
intervalo, e `compare_scenarios` recusa declarar vencedor com intervalos sobrepostos.

O intervalo também trabalha em silêncio. Com quatro replicações, o turno de dez horas **não** é
distinguível da base; com seis, é. O efeito sempre esteve lá; quatro rodadas não bastavam para
vê-lo. Um estudo que reporta uma rodada não tem como saber em qual situação está.

### Detenção é invisível à utilização

As docas de recebimento operam a 62%, o que lê como folgado. Elas também passam 768 horas em 20
dias ocupadas com a operação fechada — carretas paradas na doca esperando o próximo turno. Isso
é detenção, é o que a transportadora cobra, e nenhum índice de utilização contém isso.

### Premissas e limitações

- **Recebimento e expedição não compartilham mão de obra.** Em operação que realoca pessoal
  entre os dois, a restrição se move de outro jeito e este modelo superestima quanto cada pool
  restringe isoladamente — e subestima o valor da flexibilidade.
- **Tarefa interrompida pela parada de turno mantém o recurso retido a noite toda.** Para doca
  isso é correto (a carreta está estacionada nela). Para mão de obra é artefato, e é por isso que
  o tempo retido com a operação fechada é reportado separadamente, não somado à utilização.
- **Absenteísmo é desconto determinístico** sobre o efetivo; a variação diária de quem falta não
  é modelada — e é dela que vêm os dias ruins.
- **Fora de escopo:** carregamento e expedição, reabastecimento do bulk para a face de picking
  (que disputa os mesmos corredores com a separação), distância percorrida dentro da área de
  picking (ver `oplab.slotting`), e qualquer turno que atravesse a meia-noite.
- **Intervalos de confiança são aproximação normal**, então grandeza limitada em zero e estimada
  perto dele pode produzir limite inferior negativo. Não é truncado: o limite impossível é o
  sinal honesto de que a estimativa é imprecisa em relação à própria magnitude.
