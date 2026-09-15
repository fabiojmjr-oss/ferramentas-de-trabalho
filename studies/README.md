# Studies — one decision, end to end

**EN** · [Português](#português)

The `examples/` directory has one script per module: each answers the question that module was built
for. A study does the opposite. It takes **one decision** and uses whichever modules can price the
parts of it, in the order the decision has to be taken rather than in the order the tools were
built.

That order is the point. A library of analytics invites the question *what can I measure?* A
decision starts from *what am I about to spend money on, and is the brief right?* — and those two
questions produce different work. The studies here are written for the second.

| Study | The decision it takes |
| --- | --- |
| [`01_where_to_spend.py`](01_where_to_spend.py) | Four funding candidates, one budget: which are worth the money once each is priced on the same data? |
| [`02_what_changed.py`](02_what_changed.py) | Three signals on a Monday slide: which are real, which are artefacts of measurement, and is any action justified? |
| [`03_audit_a_proposal.py`](03_audit_a_proposal.py) | A vendor proposal with four workstreams and 18% on the cover: can any of it be reproduced on this operation's data? |
| [`04_commit_to_a_promise.py`](04_commit_to_a_promise.py) | A customer wants 99% fill rate with penalties: what is actually being signed, and at what cost? |
| [`05_decide_before_you_know.py`](05_decide_before_you_know.py) | A supplier failed and the expedite window shuts at noon: of four analyses, which could change what we do? |

The set is deliberate. Study 01 asks *what should I fund?* — a comparison, decided by pricing
candidates. Study 02 asks *what changed?* — an elimination, decided by establishing which signals
survive scrutiny. Those are the two questions an operations lead actually faces, and they require
opposite reasoning: the first prices alternatives, the second discards hypotheses.

Study 02 ends with **one investigation, two corrections to the reporting, and no recovery plan.**
That is the harder output to defend and the more valuable one: reacting to a signal that is not one
is not neutral, it moves a stable process. Every refusal there is backed by a measurement rather
than by caution.

Study 03 reasons about material the operation did not produce, which is a third shape again:
adversarial reproduction. **None of the four claims it audits is simply true and none is simply
false** — one is understated and needs no vendor, one has roughly the right number attached to the
wrong mechanism, one cannot be verified by the class of model that produced it, and one points in
the right direction at the wrong part of the problem. A flat rejection would have been wrong on
three lines out of four.

The third verdict is where that study turns on its own tooling: this repository's routing module is
the same class of model as the one behind the vendor's number, and is subject to the same artefact.
**An audit that finds nothing wrong with its own method is not an audit**, and saying so is what
makes the other three verdicts worth reading.

Study 04 is the fourth shape and the only one where the operation **makes** a claim rather than
examining one. Being wrong there is not an analytical error, it is a penalty payment, and the
measurements say something uncomfortable: **all four of the largest items on the table are wording
decisions rather than operational ones.** The same order book delivers 90.03% or 98.26% depending
on the fill-rate basis named; the same promise costs 82% more in stock depending on which service
definition it means; and one policy sized for 99% breaches a 99% cycle-service clause while
clearing a 99% fill-rate clause with half a point to spare.

The recommendation there is to write the definitions down rather than to exploit them, and the
reason is not decorum. A definitional advantage the counterparty has not understood is a dispute
with a delay on it, and the asymmetry runs both ways — the customer can find a stricter reading as
easily as the supplier can find a kinder one.

That study also produced a correction to published work. Pricing the delivery window across four
search budgets returned a **negative** premium at the cheapest one, which cannot be true of two
optima, and falsified a prose claim in
[`oplab.routing`](../src/oplab/routing/README.md) that an under-searched solve *exaggerates* the
cost of every constraint it prices. The premium is a difference between two errors, and it has no
reliable sign until both sides are searched properly. It was found with the number already on its
way to a customer.

Study 05 breaks the assumption the other four share: that the analysis can be finished before the
decision is taken. It has a clock — five hours until the expedite window shuts — and the reasoning
runs **boundary first, measurement second.** For each question on the table, not "what is the
answer?" but "what would the answer have to be to change what I do?"

The triage inverts the agenda. The decision being argued about — which of 64 affected SKUs to
air-freight — comes to **one SKU worth BRL 202**, against **BRL 41,893** of exposure it can recover
half a percent of. The two factors that decide the outcome are in nobody's action item: the length
of the outage (a **26.96x** swing in exposure) and the demand estimate (**8.04x**). The air rate and
the customs fee, which are the two numbers the requested optimisation is built on, move the exposure
by **exactly nothing** — sweeping the air rate reorders the eligible list from 16 SKUs to 2 while
leaving the exposure bit-identical, because those parameters price the response and not the loss.

So the highest-value act available at 07:00 is a **phone call**, and no module here produces it.
That is the honest limitation of a toolkit rather than a gap for a better model to fill.

The decision still ships, because the unknown never reaches the boundary: blanket action only
overtakes acceptance at **95 days** of outage — solved, not read off the table — which is outside
every scenario on offer. Under a clock, that is the useful shape of an answer: not an estimate of
the unknown, but a demonstration that it does not cross the line, plus the value at which it would,
written down in advance so the reversal is a rule rather than a second argument.

**Two of the study's own predictions were wrong**, and both are recorded where they failed. Demand
cancels exactly out of the eligibility test, and the conclusion drawn from that — that the forecast
was decision-irrelevant — was false: it cancels from the *selection* and dominates the *exposure*.
And the realised-versus-quoted lead time, the tail this repository was built to find (quoted 30
days, realised 31.68, skew 5.58, p95 36.88), moves the exposure by 1.14x: real, and not what is at
stake once a shipment has already failed.

The framework the study ends on is **the value of information is bounded by the value of the
decision it informs** — computable before the analysis, from the action space alone, and the one
calculation a Monday morning never includes.

## What a study has to do

- **Check the brief before pricing anything.** Two of the modules exist to establish whether a
  reported gap is real: `oplab.kpi` shows how much of a service number is convention, and
  `oplab.benchmark` shows how much of a cost gap is territory. Running them after the candidates
  have been priced is running them too late.
- **Price every candidate on the same data**, so the comparison is between measurements rather than
  between sponsors' confidence.
- **Reach a verdict, including the declines**, and say what each verdict rests on.
- **Say what would change it.** A conclusion that cannot be overturned by a measurement is not a
  conclusion, it is a position. Study 01 ends by naming the one ratio to re-run before the next
  budget round.

Every study is executed by the test suite and every figure it quotes is asserted, on the same terms
as the module READMEs.

## Limitations of the form

A study is a worked example on synthetic data, not a case study. It shows how the decision would be
reasoned and what the modules can and cannot settle; it cannot show that the conclusion generalises,
because the operation it reasons about does not exist. The figures are reproducible from
`seed=42` and are not evidence about any real network. See [`../DISCLAIMER.md`](../DISCLAIMER.md).

---

## Português

O diretório `examples/` tem um script por módulo: cada um responde à pergunta para a qual aquele
módulo foi construído. Um estudo faz o oposto. Ele toma **uma decisão** e usa os módulos que
conseguem precificar as partes dela, na ordem em que a decisão tem de ser tomada — não na ordem em
que as ferramentas foram construídas.

Essa ordem é o ponto. Uma biblioteca de análise convida à pergunta *o que eu consigo medir?* Uma
decisão parte de *no que estou prestes a gastar dinheiro, e o brief está certo?* — e essas duas
perguntas produzem trabalhos diferentes. Os estudos aqui são escritos para a segunda.

| Estudo | A decisão que ele toma |
| --- | --- |
| [`01_where_to_spend.py`](01_where_to_spend.py) | Quatro candidatos a investimento, um orçamento: quais valem o dinheiro, uma vez precificados nos mesmos dados? |
| [`02_what_changed.py`](02_what_changed.py) | Três sinais num slide de segunda-feira: quais são reais, quais são artefato de medição, e alguma ação se justifica? |
| [`03_audit_a_proposal.py`](03_audit_a_proposal.py) | Uma proposta de fornecedor com quatro frentes e 18% na capa: alguma parte dela se reproduz nos dados desta operação? |
| [`04_commit_to_a_promise.py`](04_commit_to_a_promise.py) | Um cliente quer 99% de fill rate com penalidade: o que está sendo assinado de fato, e a que custo? |
| [`05_decide_before_you_know.py`](05_decide_before_you_know.py) | Um fornecedor falhou e a janela de expedição fecha ao meio-dia: das quatro análises, qual pode mudar o que fazemos? |

O conjunto é deliberado. O estudo 01 pergunta *no que devo investir?* — comparação, decidida
precificando candidatos. O estudo 02 pergunta *o que mudou?* — eliminação, decidida estabelecendo
quais sinais sobrevivem ao escrutínio. São as duas perguntas que um gestor de operações realmente
enfrenta, e exigem raciocínios opostos: o primeiro precifica alternativas, o segundo descarta
hipóteses.

O estudo 02 termina com **uma investigação, duas correções de relatório e nenhum plano de
recuperação.** É a saída mais difícil de defender e a mais valiosa: reagir a um sinal que não é
sinal não é neutro, move um processo estável. Toda recusa ali está apoiada numa medição, não em
cautela.

O estudo 03 raciocina sobre material que a operação não produziu, uma terceira forma: reprodução
adversarial. **Nenhuma das quatro alegações auditadas é simplesmente verdadeira e nenhuma é
simplesmente falsa** — uma está subdimensionada e não precisa do fornecedor, uma tem
aproximadamente o número certo atribuído ao mecanismo errado, uma não é verificável pela classe de
modelo que a produziu, e uma aponta na direção certa para a parte errada do problema. Recusa
sumária erraria em três linhas de quatro.

O terceiro veredito é onde aquele estudo se vira contra o próprio ferramental: o módulo de
roteirização deste repositório é da mesma classe de modelo que produziu o número do fornecedor, e
está sujeito ao mesmo artefato. **Auditoria que não encontra nada de errado no próprio método não é
auditoria**, e dizer isso é o que torna os outros três vereditos legíveis.

O estudo 04 é a quarta forma e a única em que a operação **faz** uma afirmação em vez de examinar
uma. Errar ali não é erro analítico, é pagamento de multa — e as medições dizem algo incômodo:
**os quatro maiores itens da mesa são decisões de redação, não de capacidade operacional.** O mesmo
livro de pedidos entrega 90,03% ou 98,26% conforme a base de fill rate nomeada; a mesma promessa
custa 82% mais em estoque conforme a definição de serviço que ela significa; e uma política
dimensionada para 99% descumpre uma cláusula de 99% de serviço de ciclo enquanto cumpre uma de 99%
de fill rate com meio ponto de margem.

A recomendação ali é escrever as definições, não explorá-las, e a razão não é etiqueta. Vantagem
definicional que a contraparte não entendeu é disputa com atraso embutido, e a assimetria corre nos
dois sentidos.

Esse estudo também produziu uma correção em trabalho publicado. Precificar a janela de entrega em
quatro orçamentos de busca devolveu prêmio **negativo** no mais baixo, o que não pode ser verdade
para dois ótimos, e falsificou uma afirmação em
[`oplab.routing`](../src/oplab/routing/README.md) de que um solve com busca insuficiente *exagera*
o custo de toda restrição que precifica. O prêmio é uma diferença entre dois erros, e não tem sinal
confiável até que os dois lados sejam pesquisados de verdade.

O estudo 05 quebra a premissa que os outros quatro compartilham: que a análise termina antes da
decisão. Ele tem relógio — cinco horas até a janela de expedição fechar — e o raciocínio corre
**fronteira primeiro, medição depois.** Para cada pergunta na mesa, não "qual é a resposta?" e sim
"qual a resposta teria de ser para mudar o que eu faço?"

A triagem inverte a agenda. A decisão em discussão — quais dos 64 SKUs afetados mandar por aéreo —
dá **um SKU, valendo BRL 202**, contra **BRL 41.893** de exposição da qual ela recupera meio por
cento. Os dois fatores que decidem o resultado não são ação de ninguém: a duração da falha (giro de
**26,96x** na exposição) e a estimativa de demanda (**8,04x**). A tarifa aérea e o desembaraço, os
dois números sobre os quais a otimização pedida é construída, movem a exposição em **exatamente
nada** — varrer a tarifa reordena a lista de elegíveis de 16 SKUs para 2 e deixa a exposição
idêntica, porque esses parâmetros precificam a resposta, não a perda.

Ou seja: o ato de maior valor disponível às 07:00 é um **telefonema**, e nenhum módulo daqui o
produz. Essa é a limitação honesta de um conjunto de ferramentas, não uma lacuna a ser preenchida
por um modelo melhor.

A decisão sai mesmo assim, porque o desconhecido nunca alcança a fronteira: agir em tudo só supera
aceitar a perda a **95 dias** de falha — resolvido, não lido da tabela — o que está fora de todo
cenário em discussão. Sob relógio, essa é a forma útil de uma resposta: não uma estimativa do
desconhecido, mas a demonstração de que ele não cruza a linha, mais o valor em que cruzaria, escrito
de antemão para que a reversão seja regra e não uma segunda discussão.

**Duas previsões do próprio estudo estavam erradas**, e as duas ficam registradas onde falharam. A
demanda cancela exatamente do teste de elegibilidade, e a conclusão tirada disso — que a previsão
era irrelevante para a decisão — era falsa: ela cancela da *seleção* e domina a *exposição*. E o
lead time realizado contra o cotado, a cauda que este repositório foi feito para achar (cotado 30
dias, realizado 31,68, skew 5,58, p95 36,88), move a exposição em 1,14x: real, e não é o que está em
jogo depois que um embarque já falhou.

O modelo com que o estudo termina: **o valor da informação é limitado pelo valor da decisão que ela
informa** — calculável antes da análise, a partir do espaço de ações, e a única conta que uma
segunda-feira nunca inclui.

### O que um estudo tem de fazer

- **Checar o brief antes de precificar qualquer coisa.** Dois dos módulos existem para estabelecer
  se uma lacuna reportada é real: o `oplab.kpi` mostra quanto de um número de serviço é convenção, e
  o `oplab.benchmark` mostra quanto de uma diferença de custo é território. Rodá-los depois de
  precificar os candidatos é rodá-los tarde demais.
- **Precificar todo candidato nos mesmos dados**, para que a comparação seja entre medições e não
  entre a confiança dos patrocinadores.
- **Chegar a um veredito, inclusive as recusas**, e dizer no que cada veredito se apoia.
- **Dizer o que mudaria a conclusão.** Conclusão que não pode ser derrubada por uma medição não é
  conclusão, é posição. O estudo 01 termina nomeando a razão a re-medir antes do próximo ciclo
  orçamentário.

Todo estudo é executado pela suíte de testes e toda figura que ele cita é asserida, nos mesmos
termos dos READMEs de módulo.

### Limitações da forma

Um estudo é exemplo trabalhado sobre dados sintéticos, não um case. Mostra como a decisão seria
raciocinada e o que os módulos conseguem e não conseguem fechar; não mostra que a conclusão
generaliza, porque a operação sobre a qual ele raciocina não existe. As figuras são reprodutíveis a
partir de `seed=42` e não são evidência sobre nenhuma rede real. Ver
[`../DISCLAIMER.md`](../DISCLAIMER.md).
