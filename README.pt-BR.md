# oplab — ferramentas de análise operacional

[![ci](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Indicadores logísticos, controle estatístico de processo e os dados sintéticos de cadeia de
suprimentos para exercitar os dois. Python, com testes e tipagem.

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

## O que tem aqui

| Módulo | A pergunta que responde | Situação |
| --- | --- | --- |
| `oplab.synth` | Contra que dado eu testo sem expor uma operação real? | Disponível |
| `oplab.kpi` | Qual é o nível de serviço, e quanto dele é definição? | Disponível |
| `oplab.spc` | O processo mudou, e ele é capaz de atender à especificação? | Disponível |

Sequência completa de construção em [`docs/ROADMAP.md`](docs/ROADMAP.md).

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

dataset = generate_dataset()  # reprodutível a partir da semente
print(service_sensitivity(dataset.order_lines))  # uma carteira, quatro convenções
```

---

## Três coisas que isso demonstra

### 1. Dezesseis pontos de nível de serviço sem mexer na operação

`examples/01_service_definition.py` mede uma única carteira — 300.718 linhas ao longo de um ano
em quatro unidades — sob quatro convenções de reporte:

| Convenção | OTIF | No prazo | Completo | Linhas no escopo |
| --- | --- | --- | --- | --- |
| Linhas não entregues contam como falha | 76,1% | 78,6% | 92,6% | 296.962 |
| Linhas não entregues excluídas *(padrão)* | 79,4% | 82,1% | 96,7% | 284.412 |
| Um dia de tolerância no prazo | 91,6% | 94,7% | 96,7% | 284.412 |
| Tolerância de prazo mais 5% de quantidade | 91,7% | 94,7% | 96,7% | 284.412 |

Nada na operação muda entre essas linhas. A amplitude de 15,6 pontos é definição — e costuma
ser maior que a melhoria que está sendo negociada na sala.

Ela também reordena a rede. O CD-SP é segundo na convenção estrita e primeiro quando se admite
um dia de tolerância; o CD-RJ faz o caminho inverso. Meta definida antes da definição não é
meta.

E no mesmo dado, o fill rate é 98,4% por peça, 96,7% por linha e 90,0% por pedido. Os três
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
| Linha central | 499,95 | 500,91 |
| Semiamplitude do limite | 2,764 | 2,676 |
| Sinais na fase estável | 1 | 12 |

A semiamplitude praticamente não se move. O que se desloca é a **linha central**, puxada para o
período perturbado — o que fabrica doze sinais num período que estava estável e data a mudança
errado. E data errada manda a investigação para o turno errado, o lote errado e a causa errada.

Os limites realmente inflam quando o sigma é estimado pelo desvio-padrão dos pontos plotados em
vez da variação intra-subgrupo. Esse é outro erro, e nenhuma função daqui o comete.

### 3. Um quarto dos sinais produzido pela unidade de análise errada

Carta p de entregas em atraso em uma unidade, mesmo período, mesmo tipo de carta, variando
apenas o que conta como um ensaio:

| Unidade de análise | n por dia | Dias sinalizados | Superdispersão |
| --- | --- | --- | --- |
| Linha de pedido | 91–300 | 98 de 359 | 2,12 |
| Pedido | 30–93 | 7 de 359 | 1,01 |

Todas as linhas de um pedido viajam no mesmo veículo, então um caminhão atrasado produz uma
dúzia de falhas correlacionadas. O modelo binomial por trás da carta p pressupõe ensaios
independentes, a variação observada sai 2,12x maior que a prevista, e 27% dos dias sinalizam —
todos eles artefato. No nível de pedido a razão é 1,01 e a taxa de sinal cai para a taxa de
falso alarme esperada.

`oplab.spc.overdispersion_ratio` reporta isso, e vale checar antes de investigar qualquer sinal.

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

**Testar contra cálculo feito à mão.** Os limites das cartas são conferidos contra `A2`, `D3` e
`D4` das tabelas publicadas, em subgrupos cuja amplitude é exata por construção. Os indicadores
de serviço são conferidos contra um fixture de seis linhas cujos valores esperados foram
derivados à mão. Indicador testado apenas contra a própria implementação não testa nada.

**Nenhum dado real, em nenhuma hipótese.** Toda tabela vem de `oplab.synth` com semente fixa.
Ver [`DISCLAIMER.md`](DISCLAIMER.md).

## Limitações

Ditas com clareza, porque as lacunas importam tanto quanto a cobertura:

- O gerador sintético produz dado **plausível**, não calibrado. Foi construído para exercitar a
  análise e tornar os exemplos reprodutíveis. Nenhum número deste repositório deve ser lido
  como desempenho de operação real.
- Índices de capacidade pressupõem normalidade aproximada. `oplab.spc.capability` reporta
  assimetria e curtose e avisa quando a premissa é duvidosa, mas não implementa métodos de
  capacidade para distribuições não normais. Durações logísticas são tipicamente assimétricas à
  direita, então isso pesa mais aqui do que na manufatura.
- Ainda não há previsão de demanda, otimização ou simulação. São as ondas 2 a 4 do
  [`docs/ROADMAP.md`](docs/ROADMAP.md).
- Cartas por atributo pressupõem ensaios independentes. `overdispersion_ratio` detecta a
  violação, mas a biblioteca ainda não oferece carta p′ de Laney nem outra alternativa robusta
  a superdispersão.

## Desenvolvimento

```bash
ruff check . && ruff format --check .   # lint e formatação
mypy                                    # verificação de tipos
pytest --cov                            # 131 testes, 94% de cobertura de statements
```

A CI roda os quatro em Python 3.10 e 3.12.

## Licença

MIT. Ver [`LICENSE`](LICENSE).
