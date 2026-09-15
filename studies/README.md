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
