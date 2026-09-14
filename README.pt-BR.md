# oplab — ferramentas de análise operacional

[![ci](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Indicadores logísticos, controle estatístico de processo, endereçamento de picking e os dados
sintéticos de cadeia de suprimentos para exercitar tudo isso. Python, com testes e tipagem.

**[Read in English →](README.md)**

---

## Por que isso existe

A maior parte dos problemas de reporte operacional não é problema de cálculo. A aritmética por
trás de OTIF, fill rate e acuracidade de estoque é trivial; o que decide se o número está certo
é um conjunto de convenções que quase nunca está escrito — se a promessa é um instante ou uma
data, se uma linha cancelada pertence ao denominador, se acuracidade conta endereços ou peças.

Este repositório parte da posição de que essas convenções pertencem ao código, com teste, onde
possam ser discutidas e auditadas. Cada função expõe suas escolhas como argumento, e onde um
indicador tem mais de uma definição legítima, todas são devolvidas em vez de uma ser escolhida
em silêncio.

## Módulos

| Módulo | A pergunta que responde | Docs |
| --- | --- | --- |
| `oplab.synth` | Contra que dado eu testo sem expor uma operação real? | [`DISCLAIMER.md`](DISCLAIMER.md) |
| `oplab.kpi` | Qual é o nível de serviço, e quanto dele é definição? | — |
| `oplab.spc` | O processo mudou, e ele é capaz de atender à especificação? | — |
| `oplab.slotting` | Quais itens merecem qual política, e quanto o layout custa? | [README](src/oplab/slotting/README.md) |

Mais seis ferramentas estão planejadas. Sequência e regra de seleção em
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Instalação

```bash
git clone https://github.com/fabiojmjr-oss/ferramentas-de-trabalho.git
cd ferramentas-de-trabalho
pip install -e ".[dev]"
pytest
```

## Trinta segundos

```python
from oplab.kpi import service_sensitivity
from oplab.synth import generate_dataset

dataset = generate_dataset()                      # reprodutível a partir da semente
print(service_sensitivity(dataset.order_lines))   # uma carteira, quatro convenções
```

---

## Quatro coisas que isso demonstra

### 1. Dezesseis pontos de nível de serviço sem mexer na operação

`examples/01_service_definition.py` mede uma única carteira — 290.918 linhas ao longo de um ano
em quatro unidades — sob quatro convenções de reporte:

| Convenção | OTIF | No prazo | Completo | Linhas no escopo |
| --- | --- | --- | --- | --- |
| Linhas não entregues contam como falha | 76,0% | 78,5% | 92,6% | 287.352 |
| Linhas não entregues excluídas *(padrão)* | 79,4% | 82,0% | 96,7% | 275.163 |
| Um dia de tolerância no prazo | 91,5% | 94,6% | 96,7% | 275.163 |
| Tolerância de prazo mais 5% de quantidade | 91,6% | 94,6% | 96,7% | 275.163 |

Nada na operação muda entre essas linhas. A amplitude de 15,6 pontos é definição — e costuma
ser maior que a melhoria que está sendo negociada na sala.

Ela também reordena a rede. O CD-SP é segundo na convenção estrita e primeiro quando se admite
um dia de tolerância; o CD-RJ faz o caminho inverso. Meta definida antes da definição não é
meta.

E no mesmo dado, o fill rate é 98,3% por peça, 96,7% por linha e 90,0% por pedido. Os três
estão corretos. Citar um sem nomear a base é como duas áreas reportam níveis de serviço
diferentes a partir do mesmo extrato sem que nenhuma esteja errada.

### 2. Limite de controle não é o que uma base contaminada quebra

Repete-se com frequência que ajustar limites de controle sobre um período que já contém o
distúrbio infla os limites até o distúrbio caber dentro deles. Em carta X-barra/R isso é falso,
e o motivo importa: a semiamplitude do limite é `A2 × R̄`, construída a partir da amplitude
**intra-subgrupo**, e um deslocamento da média entre subgrupos não altera essa amplitude.

Medido em uma série com deslocamento de 1,6σ injetado no subgrupo 43:

| | Limites da fase estável | Limites da série completa |
| --- | --- | --- |
| Linha central | 499,72 | 500,67 |
| Semiamplitude do limite | 2,930 | 2,728 |
| Sinais na fase estável | 0 | 14 |

A linha central se desloca quase cinco vezes mais que a semiamplitude, e é puxada para o
período perturbado — o que fabrica quatorze sinais num período que estava estável e data a
mudança errado. Data errada manda a investigação para o turno errado, o lote errado e a causa
errada.

Os limites realmente inflam quando o sigma é estimado pelo desvio-padrão dos pontos plotados em
vez da variação intra-subgrupo. Esse é outro erro, e nenhuma função daqui o comete.

### 3. Um quarto dos sinais produzido pela unidade de análise errada

Carta p de entregas em atraso em uma unidade, mesmo período, mesmo tipo de carta, variando
apenas o que conta como um ensaio:

| Unidade de análise | n por dia | Dias sinalizados | Superdispersão |
| --- | --- | --- | --- |
| Linha de pedido | 80–295 | 95 de 359 | 2,12 |
| Pedido | 25–89 | 4 de 359 | 1,01 |

Todas as linhas de um pedido viajam no mesmo veículo, então um caminhão atrasado produz uma
dúzia de falhas correlacionadas. O modelo binomial por trás da carta p pressupõe ensaios
independentes, a variação observada sai 2,12x maior que a prevista, e 26% dos dias sinalizam —
todos eles artefato. No nível de pedido a razão é 1,01 e a taxa de sinal cai para a taxa de
falso alarme esperada.

`oplab.spc.overdispersion_ratio` reporta isso, e vale checar antes de investigar qualquer sinal.

### 4. Em endereçamento, o algoritmo é erro de arredondamento

Três regras de ordenação contra a alocação aleatória atual de 400 SKUs em 2.400 faces de
picking:

| Estratégia | Distância média por coleta | Variação |
| --- | --- | --- |
| Por popularidade (coletas) | 17,11 m | −67,2% |
| Por receita | 17,34 m | −66,7% |
| Por índice cube-per-order | 18,00 m | −65,5% |
| Atual (como recebido) | 52,11 m | — |

Toda regra recupera cerca de dois terços do deslocamento, e a diferença entre a melhor e a pior
é de 1,7 ponto. **A decisão que vale dinheiro é reendereçar ou não; a escolha do algoritmo é
erro de arredondamento diante disso** — o oposto de como software de slotting é vendido.

O índice cube-per-order ficar em último está correto, não é defeito: com uma face por SKU e
capacidade uniforme, todo item consome o mesmo espaço, logo o cubo não carrega informação sobre
a função objetivo. Detalhes, e a condição sob a qual o COI de fato ganha, no
[README do módulo](src/oplab/slotting/README.md).

A classificação por trás disso rende o próprio achado: 18 de 87 itens classe A não são estáveis
e carregam 19,1% do valor da classe A. Um exercício só de ABC entrega a todos eles a política
desenhada para demanda previsível, e é daí que vêm as falhas de serviço.

---

## Princípios de projeto

**Validar na fronteira.** Toda função pública de KPI confere a entrada contra um contrato em
`oplab.kpi.schemas` e reporta todos os problemas de uma vez. Um número de serviço calculado
sobre extrato malformado é pior que nenhum número, porque é reportado com a mesma confiança de
um correto.

**Quantificar o trade-off em vez de afirmá-lo.** As taxas de falso alarme dos conjuntos de
regras de Nelson — 1 em 420 pontos só com a regra 1, 1 em 70 no conjunto prático, 1 em 42 com
as oito — são medidas em `tests/spc/test_rules.py::test_false_alarm_rates`, não citadas de
memória.

**Devolver toda definição legítima.** Três bases de fill rate, três definições de acuracidade
de estoque, Cpk ao lado de Ppk. A diferença entre elas costuma ser o achado.

**Reportar o resultado que contraria o discurso.** O índice cube-per-order perde para
popularidade simples aqui, e o módulo diz isso e explica por quê, em vez de descartar a
comparação em silêncio.

**Testar contra cálculo feito à mão.** Os limites das cartas são conferidos contra `A2`, `D3` e
`D4` das tabelas publicadas, em subgrupos cuja amplitude é exata por construção. Os indicadores
de serviço são conferidos contra um fixture de seis linhas cujos valores esperados foram
derivados à mão. Indicador testado apenas contra a própria implementação não testa nada.

**Nenhum dado real, em nenhuma hipótese.** Toda tabela vem de `oplab.synth` com semente fixa.
Ver [`DISCLAIMER.md`](DISCLAIMER.md).

**O README está sob teste.** Todo número citado acima é verificado em
`tests/test_readme_claims.py`, e os scripts de exemplo também são executados lá. Qualquer
mudança que mova um desses números quebra o build em vez de deixar o texto silenciosamente
errado.

## Limitações

Ditas com clareza, porque as lacunas importam tanto quanto a cobertura:

- O gerador sintético produz dado **plausível**, não calibrado. Foi construído para exercitar a
  análise e tornar os exemplos reprodutíveis. Nenhum número deste repositório deve ser lido
  como desempenho de operação real.
- Índices de capacidade pressupõem normalidade aproximada. `oplab.spc.capability` reporta
  assimetria e curtose e avisa quando a premissa é duvidosa, mas não implementa métodos de
  capacidade para distribuições não normais. Durações logísticas são tipicamente assimétricas à
  direita, então isso pesa mais aqui do que na manufatura.
- O endereçamento mede coletas ponderadas por distância, não rotas, e pressupõe uma localização
  por SKU, sem congestionamento e sem custo de movimentação. Todas essas premissas superestimam
  o benefício; ver o [README do módulo](src/oplab/slotting/README.md) para a lista completa e
  para o motivo pelo qual a variação percentual é citável e os metros não são.
- Cartas por atributo pressupõem ensaios independentes. `overdispersion_ratio` detecta a
  violação, mas a biblioteca ainda não oferece carta p′ de Laney nem outra alternativa robusta
  a superdispersão.
- Ainda não há previsão de demanda, otimização ou simulação. São as ondas 3 e 4 do
  [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Desenvolvimento

```bash
ruff check . && ruff format --check .   # lint e formatação
mypy                                    # verificação de tipos
pytest --cov                            # 173 testes, 93% de cobertura de statements
```

A CI roda os quatro em Python 3.10 e 3.12.

## Licença

MIT. Ver [`LICENSE`](LICENSE).
