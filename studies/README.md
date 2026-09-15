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
