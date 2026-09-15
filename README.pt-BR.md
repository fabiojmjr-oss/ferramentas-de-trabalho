# oplab — ferramentas de análise operacional

[![ci](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Indicadores logísticos, controle estatístico de processo, endereçamento de picking, decomposição
de variação de custo, simulação de capacidade por eventos discretos, roteirização de veículos e
os dados sintéticos de cadeia de suprimentos para exercitar tudo isso. Python, com testes e
tipagem.

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
| `oplab.variance` | Por que o custo por pedido mudou, e quem responde por cada parte? | [README](src/oplab/variance/README.md) |
| `oplab.simulation` | Onde está a restrição, e o que aliviá-la compra? | [README](src/oplab/simulation/README.md) |
| `oplab.routing` | Quanto custa uma entrega, e quais decisões o modelo consegue fechar? | [README](src/oplab/routing/README.md) |
| `oplab.benchmark` | Qual unidade está abaixo, neutralizados porte e geografia? | [README](src/oplab/benchmark/README.md) |
| `oplab.forecast` | A previsão supera não fazer nada, e como você saberia? | [README](src/oplab/forecast/README.md) |
| `oplab.inventory` | Quanto custa um ponto de nível de serviço, e qual lever o compra? | [README](src/oplab/inventory/README.md) |
| `oplab.mining` | O que o processo faz, em oposição ao que o fluxograma diz? | [README](src/oplab/mining/README.md) |

Sequência de construção e regra de seleção em
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Instalação

```bash
git clone https://github.com/fabiojmjr-oss/ferramentas-de-trabalho.git
cd ferramentas-de-trabalho
make install
make check
```

## Trinta segundos

```python
from oplab.kpi import service_sensitivity
from oplab.synth import generate_dataset

dataset = generate_dataset()  # reprodutível a partir da semente
print(service_sensitivity(dataset.order_lines))  # uma carteira, quatro convenções
```

---

## Doze coisas que isso demonstra

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

### 5. O mesmo movimento de custo, atribuído de duas formas diferentes

O custo por pedido subiu 13,7% no ano no razão embutido. A decomposição é exata nos dois casos,
e a segmentação decide a resposta:

| Efeito | Segmentado por unidade e tamanho | Com canal adicionado |
| --- | --- | --- |
| Taxa | **+11,55 (98,2%)** | +9,20 (78,2%) |
| Mix | +0,21 (1,8%) | **+2,57 (21,8%)** |
| Total | +11,77 | +11,77 |

O movimento é idêntico. A atribuição não é. Omita a dimensão canal e 98% da alta lê como
operacional; inclua-a e um quinto é mix, porque a participação do canal direto ao consumidor
cresceu e uma entrega residencial custa quase o dobro por parada que uma entrega em loja.

**Uma dimensão omitida não desaparece. Ela reaparece dentro do efeito taxa e é atribuída a quem
responde pela taxa** — e é invisível, porque a aritmética fecha abaixo de 1e-13 nos dois casos.

Duas outras coisas saem do mesmo módulo. O custo total subiu 20,7%, dos quais 30% foram volume
— o mesmo negócio ficou maior, o que não é problema de custo. E uma métrica por unidade não pode
se mover por volume: a ponte tem exatamente dois termos por construção, então *"o custo por
pedido subiu, mas o volume cresceu"* não é explicação. Detalhes, inclusive a ressalva de
alavancagem operacional que qualifica isso, no [README do módulo](src/oplab/variance/README.md).

### 6. A planilha de capacidade está certa, e ainda aponta a decisão errada

Utilização é conservada, então dividir trabalho médio por capacidade média a calcula
corretamente. Os números simulados batem com a planilha dentro de um ponto. E não decidem nada:

| Recurso | Utilização | Espera total causada |
| --- | --- | --- |
| Separação (18 pessoas) | 77,9% | **26.425 h** |
| Conferência (5 postos) | 95,3% | 9.622 h |

**Utilização não ordena nada.** A separação está em carga folgada e causa quase três vezes a
espera do recurso a 95%, porque os pedidos são liberados em duas ondas e cada pedido entra na
fila atrás de meio dia de trabalho no instante em que chega. Isso é política de liberação, não
falta de capacidade, e nenhum índice de utilização separa os dois.

O que isso faz com o caso de investimento, em seis replicações a 95% de confiança:

| Cenário | Tempo de ciclo | Variação | Distinguível |
| --- | --- | --- | --- |
| **Liberar em 8 ondas em vez de 2** | 0,82 h | **−61,7%** | Sim |
| +2 postos de conferência | 1,68 h | −22,0% | Sim |
| Turno de 8 h para 10 h | 2,02 h | −6,1% | Sim |
| +2 docas de recebimento | 2,15 h | 0,0% | **Não** |
| +4 separadores | 2,17 h | +0,7% | **Não** |

A mudança operacional gratuita recupera 2,8 vezes o que a melhor opção paga recupera. E quatro
separadores a mais — o movimento intuitivo, dirigido à maior fila e à maior equipe — **não
demonstram efeito algum**: o intervalo se sobrepõe ao da base, e o ponto se moveu para o lado
errado. Sem o intervalo, essa estimativa pontual teria sido reportada como resultado.

Detalhes, inclusive por que um investimento em recebimento comprovadamente não pode mover um
indicador de expedição neste modelo, no [README do módulo](src/oplab/simulation/README.md).

### 7. Um modelo que se recusa a responder a pergunta

Roteirizando 74 entregas de um depósito, sob quatro orçamentos de busca:

| Orçamento de busca | Veículos | Custo por entrega |
| --- | --- | --- |
| 20 soluções | 7 | 44,08 |
| 120 | 5 | 36,88 |
| 300 | **5** | **36,11** |

Contra uma transportadora cotando R$ 42,00 por entrega, **a conclusão se inverte conforme o
quanto o solver teve permissão de procurar.** Um solve barato diz terceirize; um minucioso diz
opere a frota. O tamanho da frota também se move com o orçamento, de sete veículos para cinco —
uma concorrência decidida com solve barato teria comprado duas vans desnecessárias.

**Logo o modelo não decide frota própria versus terceirizada nesse preço, e dizer isso é o
resultado.** O que ele decide, por margem que nenhuma premissa ameaça: o caminhão é o veículo
errado para este perfil, a 68% mais por entrega.

Dois outros resultados do mesmo módulo. O custo por entrega cai 27% quando o mesmo território
carrega quatro vezes mais clientes — **densidade, não distância, governa o custo da última
milha** — e a curva é replicada com intervalos porque um único sorteio por ponto a deixava não
monotônica. E as janelas de entrega custam 3,8%, não o prêmio bem maior que um orçamento menor
reportava, porque **um solve com busca insuficiente exagera o custo de toda restrição que ele
precifica**.

Detalhes, inclusive por que um limite inferior de frota baseado em deslocamento não é limite
algum, no [README do módulo](src/oplab/routing/README.md).

### 8. Um terço da diferença de custo entre unidades é CEP

As quatro unidades não atendem o mesmo território: 36% das entregas de uma ficam dentro de
10 km, contra 10% de outra. A padronização indireta pergunta quanto o resto da rede gastaria no
perfil de distância de cada uma:

| Unidade | Custo bruto por pedido | Padronizado | Razão |
| --- | --- | --- | --- |
| CD-PE | 119,00 | 110,32 | 1,20 |
| CD-SP | 75,28 | 81,85 | 0,89 |

**O CD-PE lê 58% mais caro que o CD-SP no bruto, e 35% quando o perfil de distância é
neutralizado** — 35% da diferença de manchete é geografia, não desempenho. O primeiro número
define meta que ninguém alcança; o segundo é discutível pelo mérito.

Dois outros resultados, ambos sobre o método e não sobre a rede. Sob 2.000 ponderações
aleatórias de um scorecard de quatro métricas, **o ranking entre unidades é fato e o ranking
entre os meses de uma mesma unidade é teatro**: 2 de 4 unidades podem mudar de posição contra 12
de 12 meses, onde a maior oscilação é de dez posições. Mesma ferramenta, vereditos opostos, e
não há como saber em qual caso você está sem medir.

E o DEA — o método que todo mundo procura — exige pelo menos doze unidades para esse conjunto de
medidas e a rede tem quatro. O sintoma não é que todos saem eficientes; é que a **escolha de
retornos de escala move a pior unidade em 27 pontos**, a maior parte penalidade por ser pequena
e não medida de como é operada.

Detalhes no [README do módulo](src/oplab/benchmark/README.md).

---

### 9. A métrica que está na meta não pode ser calculada nos dados para os quais é citada

O MAPE é a métrica de acuracidade da maioria das metas de planejamento porque lê como
percentual. Neste sortimento ele é definido em 58,4% das observações período a período e em
**1,0% das séries sem um único período faltante** — divisão por realizado zero é indefinida, e em
demanda intermitente zero é o realizado mais frequente. Todo MAPE reportado é, portanto, média
sobre subconjunto filtrado, e o filtro remove justamente os itens difíceis de planejar. É também
assimétrico na direção caríssima: prever cinco contra realizado de um dá 400%, prever zero dá
100% — modelo calibrado em MAPE aprende a prever baixo.

Com métrica livre de escala a comparação é possível, e produz três resultados que um business
case precisa sobreviver. Sete métodos, origem móvel, contra uma regra sazonal de uma linha:

| Segmento | Séries | Melhor método | MASE | Supera a regra em | Vence em |
| --- | --- | --- | --- | --- | --- |
| Regulares (≤50% de períodos vazios) | 260 | SBA | 0,9417 | **0,8%** | 54% das séries |
| Esparsas (>50% de períodos vazios) | 140 | TSB | **1,0890** | 6,5% | 61% das séries |

**O ganho disponível na metade previsível é de 0,8% com taxa de vitória de cara ou coroa** —
proposta que promete grande ganho de acuracidade aqui promete algo que os dados não contêm. **Na
metade esparsa nada chega a MASE < 1,0**, então nenhum método supera o benchmark naive da própria
série e o plano honesto é decisão de disponibilidade, não previsão. E **o líder muda entre as
metades**: um modelo para todo o sortimento erra em metade dele por construção.

O quarto resultado é o que custa dinheiro em silêncio. A mesma previsão, medida por item-unidade
e no total da rede:

| Nível | Séries | MASE | Viés |
| --- | --- | --- | --- |
| Por SKU e unidade | 1.599 | 1,1605 | −0,0367 |
| Total da rede | 1 | 0,8480 | **−58,6667** |

Viés médio por série −0,036690 × 1.599 séries = −58,6667, que é o viés do total até o último
dígito. **Agregar encolhe o erro em 27% e não toca no viés**, porque viés é aditivo e erro não é.
Manchete de acuracidade é quase sempre número de um agregado; viés pequeno demais para discutir
num item é o mesmo viés, sem diminuição, no armazém.

Detalhes no [README do módulo](src/oplab/forecast/README.md).

---

### 10. O nível de serviço do contrato é precificado com um lead time que ninguém mediu

Estoque de segurança é dimensionado contra duas variâncias: demanda por período e lead time de
reposição. A primeira é estimada dos dados; a segunda quase sempre vem do lead time cotado pelo
fornecedor, o que zera sua variabilidade. Todo fornecedor aqui entrega perto da **média** cotada —
por isso o contrato nunca é questionado — e a cotação não diz nada sobre a dispersão:

| Fornecedor | Cotado | Média real | Desvio real | CV |
| --- | --- | --- | --- | --- |
| FORN-NACIONAL | 7,0 | 7,77 | 3,56 | **0,46** |
| FORN-CONTRATO | 12,0 | 12,17 | 1,58 | **0,13** |

Em 191 SKUs regulares a 95% de nível de serviço de ciclo, a exigência é de **BRL 192.305**.
Dimensionado pelos lead times cotados dá BRL 121.522 — **falta ao plano 58% do estoque que o nível
de serviço exige**, e a lacuna é invisível porque os dois números saem da mesma fórmula.

Três consequências, cada uma revertendo um instinto comum.

**Qual variância é o lever tem forma fechada.** A variabilidade do lead time domina exatamente
quando `CV_L² · L > CV_d²`, então há um limiar de CV de demanda por fornecedor — 0,45, 0,45, 0,86 e
1,28 aqui. O CV de demanda fica perto de 0,76 no sortimento, então lead time é o lever para dois
fornecedores e demanda é o lever para os outros dois. A pergunta "é lead time ou acuracidade de
previsão?" não tem resposta geral, e dois números que você já tem a resolvem por fornecedor.

**O lead time menor pode exigir o pulmão maior.** O FORN-CONTRATO leva 57% mais tempo e exige
**34% menos** estoque de segurança, porque seu lead time é 2,3 vezes mais apertado. A qualificação
honesta: o estoque total não inverte, porque o estoque em trânsito escala com a média.

**Um compromisso de 99% dimensionado como serviço de ciclo custa 82% mais que o mesmo compromisso
dimensionado como fill rate** — 328 unidades contra 180. Nenhum está errado; contam coisas
diferentes, e a conversão exige a quantidade de pedido, razão pela qual não existe fator de
correção.

O entregável é a curva, e ela precifica a discussão em vez de encerrá-la por autoridade: um ponto
de serviço de ciclo custa BRL 34,76 na base e BRL 394,28 no topo, onze vezes mais. **O topo da
curva não compra nada mensurável** — de 99,0% para 99,5% custa 11% mais capital e entrega +0,07% de
serviço de ciclo simulado, porque o que resta é a cauda assimétrica do lead time.

E o ponto de serviço mais barato não está na curva. Gastar *todo* o ganho de previsão do achado 9
libera 0,26% do pulmão. Cortar os 5% piores de entregas de um fornecedor libera 23,7% — **fator de
92** — e a política menor ainda mede 98,9% de serviço de ciclo contra a promessa de 99%.

Detalhes no [README do módulo](src/oplab/inventory/README.md).

---

### 11. Conformidade de 97,8% num processo que 61% dos casos seguem

Um mapa de fluxo de valor desenhado em workshop é um conjunto de estimativas com consenso anexado.
Derivado de um log de atendimento com 38.735 eventos, discorda em quatro pontos.

**A eficiência de fluxo é 3,10%, e o número usualmente citado é 6,53%.** De 43,21 horas de lead time
médio, 40,39 são espera e 2,82 são trabalho — mas só 1,34 hora de trabalho avança o pedido. **53% de
todo o tempo de trabalho é análise de crédito, inspeção e reembalagem**: trabalho por qualquer
medida de atividade, desperdício por qualquer medida de valor. Contar isso como valor embeleza a
manchete sem ninguém mentir, e por isso o conjunto que agrega valor é argumento obrigatório aqui.

**O passo com maior tempo de toque não é o passo que detém o lead time.** O Credit Hold leva 6,34
horas e detém 6,4% de toda a espera. O Ship leva três minutos e detém 35,7%, porque roda 3.911 vezes
e não 426. O workshop acerta qual passo *parece* lento e erra qual custa; quatro passagens detêm três
quartos da espera, e nada fora delas merece um projeto.

**35 caminhos e 4 rotas são fatos diferentes.** O caminho documentado cobre 61,1% dos casos, o que
normalmente é lido como caos — enquanto quatro caminhos cobrem 80% do volume, o que significa que o
processo é padronizável e o resto é exceção. Contagem de variantes sozinha não distingue as duas
situações, então `variant_coverage` devolve as duas.

**E a métrica de conformidade é o achado, não a resposta.** Um teste de contenção pontua **97,8%** —
e `1 − 89/4000` é exatamente isso, onde 89 é o número de casos cancelados. Ele não rejeita mais nada,
porque permite passos inseridos, então é cego aos **1.467 casos que chegaram à entrega por rota que
ninguém documentou**. Escore de conformidade perto de um é evidência sobre a medida, não sobre o
processo.

O que as exceções custam é a parte sobre a qual um patrocinador pode agir:

| Grupo | Casos | Lead time médio | Eficiência de fluxo |
| --- | --- | --- | --- |
| Segue o caminho documentado | 2.444 | 30,94 h | 4,42% |
| Desvia | 1.556 | **62,49 h** | **2,07%** |

Um caso que desvia leva o dobro do tempo *e* é proporcionalmente pior, não apenas mais longo.

Detalhes no [README do módulo](src/oplab/mining/README.md).

---

### 12. A métrica que ranqueia a previsão não é a que dimensiona o estoque

Os achados 9 e 10 se sustentam sozinhos e foram construídos separados. Conectá-los expõe que nenhum
dos dois responde à pergunta que a reposição de fato faz. O `oplab.forecast` ranqueia previsões por
MASE; o `oplab.inventory` dimensionava estoque de segurança pela variabilidade da demanda. Ambos são
defensáveis, e ambos respondem a uma pergunta diferente de *quanto pulmão esta previsão precisa?*

**O MASE é construído sobre erro absoluto, e um pulmão tem de cobrir a cauda.** Medindo das duas
formas contra uma previsão da média de treino:

| Modelo | MASE | MAE vs média | Desvio do erro vs média |
| --- | --- | --- | --- |
| mean | 0,9415 | — | — |
| sba | 0,9417 | +2,8% | +0,8% |
| seasonal_naive | 0,9496 | +4,8% | **+24,9%** |

O `seasonal_naive` lê **0,9% atrás do líder no MASE e um quarto pior** na grandeza da qual um pulmão
é dimensionado — o desvio do erro expõe 5,1 vezes o que o erro absoluto mostra. Ranquear por uma
métrica e dimensionar estoque por outra são duas decisões sobre duas definições de melhor.

**E uma previsão da média de treino tem o menor desvio de erro entre as sete**, então nestes dados
nada reduz o pulmão de estoque. A razão mediana entre desvio do erro e desvio da demanda é 1,0019; a
previsão reduz o pulmão em 47% das séries e o aumenta no resto. Isso reconcilia com o achado 9 em
vez de contradizê-lo: o MASE mede contra a regra *naive*, onde o SBA ganhava 0,8%, e o estoque mede
contra a *média*, onde não há nada a ganhar.

Duas consequências.

**Previsão viesada é custo que nenhum fator de segurança cobre**, porque elevar `z` alarga uma janela
que está no lugar errado. O pior sub-dimensionamento roda a −13,27 unidades/dia e cobra **103,2
unidades de estoque permanente, 32% sobre um pulmão de 321 unidades.** E o viés médio não serve para
dimensionar: o do SBA é +0,005 — quase zero — enquanto ele sub-dimensiona **52% das séries.** Estoque
é mantido por item, então média centrada não é previsão centrada.

**Uma tabela de erro por horizonte pode ser uma tabela de sazonalidade com rótulo errado.** O erro do
passo 4 tem média +8,08 e varia só 1,03 entre nove origens, contra amplitude sistemática de −3,88 a
+8,08 entre passos — o padrão se reproduz em toda origem, então é geometria do backtest, não ruído.
Origens a 28 períodos com sazonalidade 7 travam todo passo num dia da semana. O `horizon_profile`
agora devolve um sinalizador `phase_locked`. A regra da raiz quadrada também não se aplica aqui:
`sqrt(h)` descreve total acumulado, e a coluna medida vai de 0,77 a 1,35 enquanto `sqrt(passo)` vai
de 1,00 a 2,65.

Detalhes em [`oplab.forecast`](src/oplab/forecast/README.md) e
[`oplab.inventory`](src/oplab/inventory/README.md).

---

## Exemplos

Doze scripts executáveis, cada um autocontido e cada um imprimindo o raciocínio por trás dos seus
números, não apenas os números. Todos são executados pela suíte de testes.

| Script | A pergunta que ele percorre |
| --- | --- |
| [`01_service_definition.py`](examples/01_service_definition.py) | Quanto de um número de serviço é definição, não desempenho |
| [`02_process_control.py`](examples/02_process_control.py) | Carte o processo antes de julgá-lo capaz |
| [`03_network_diagnostic.py`](examples/03_network_diagnostic.py) | Um diagnóstico de uma página de uma rede de quatro unidades |
| [`04_slotting.py`](examples/04_slotting.py) | Quanto o endereçamento atual custa, e quanto é recuperável |
| [`05_cost_variance.py`](examples/05_cost_variance.py) | Por que o custo por pedido mudou, e quem responde por cada parte |
| [`06_capacity_simulation.py`](examples/06_capacity_simulation.py) | Onde está a restrição, e o que aliviá-la compra |
| [`07_routing.py`](examples/07_routing.py) | Quanto custa uma entrega, e quais decisões o modelo fecha |
| [`08_multi_site_benchmark.py`](examples/08_multi_site_benchmark.py) | Qual unidade está abaixo, neutralizados porte e geografia |
| [`09_forecast_baseline.py`](examples/09_forecast_baseline.py) | Se a previsão supera não fazer nada, e como você saberia |
| [`10_inventory_policy.py`](examples/10_inventory_policy.py) | Quanto custa um ponto de nível de serviço, e qual lever o compra |
| [`11_process_mining.py`](examples/11_process_mining.py) | O que o processo faz, contra o que o fluxograma diz |
| [`12_forecast_error_to_stock.py`](examples/12_forecast_error_to_stock.py) | Se prever reduz o estoque que você tem de manter |

---

## Estudos

O `examples/` tem um script por módulo. Um **estudo** toma uma decisão e usa os módulos que
conseguem precificar as partes dela, na ordem em que a decisão tem de ser tomada — não na ordem em
que as ferramentas foram construídas.

| Estudo | A decisão que ele toma |
| --- | --- |
| [`01_where_to_spend.py`](studies/01_where_to_spend.py) | Quatro candidatos a investimento, um orçamento: quais valem o dinheiro, uma vez precificados nos mesmos dados? |
| [`02_what_changed.py`](studies/02_what_changed.py) | Três sinais num slide de segunda-feira: quais são reais, quais são artefato de medição, e alguma ação se justifica? |
| [`03_audit_a_proposal.py`](studies/03_audit_a_proposal.py) | Uma proposta de fornecedor com quatro frentes e 18% na capa: alguma parte dela se reproduz nos dados desta operação? |
| [`04_commit_to_a_promise.py`](studies/04_commit_to_a_promise.py) | Um cliente quer 99% de fill rate com penalidade: o que está sendo assinado de fato, e a que custo? |

O estudo 01 recusa dois dos quatro por medição, não por orçamento, estreita os dois que aprova, e
descobre que o maior item não está na lista — 35% da diferença de custo com que o brief abre é
geografia, e o próprio número de serviço se move 15,6 pontos só por convenção.

O estudo 02 faz o tipo oposto de pergunta e chega ao tipo oposto de resposta: **uma investigação,
duas correções de relatório e nenhum plano de recuperação.** Três dos quatro itens do slide não
sustentavam ação, e um deles — o instinto de conectar um mês de serviço a um desvio de processo —
é intestável, porque a carta de controle cobre 2,5 dias em junho e o número de serviço cobre doze
meses. Dois sinais reais, nenhuma relação disponível.

O estudo 03 audita a alegação de um terceiro em vez do material próprio, e **nenhuma das quatro
frentes examinadas é simplesmente verdadeira ou simplesmente falsa**: uma está subdimensionada e
não precisa do fornecedor, uma tem aproximadamente o número certo atribuído ao mecanismo errado,
uma não é verificável pela classe de modelo que a produziu — inclusive o módulo de roteirização
deste repositório — e uma aponta na direção certa para a parte errada do problema. Recusa sumária
erraria em três linhas de quatro.

O estudo 04 é o único em que a operação faz uma afirmação em vez de examinar uma, e descobre que
**os quatro maiores itens de uma negociação de serviço são decisões de redação**: o mesmo livro de
pedidos entrega 90,03% ou 98,26% conforme a base de fill rate nomeada, a mesma promessa custa 82%
mais em estoque conforme a definição de serviço, e uma política dimensionada para 99% descumpre uma
cláusula de 99% de serviço de ciclo enquanto cumpre uma de 99% de fill rate. A recomendação é
escrever as definições, não explorá-las.

Ver [`studies/README.md`](studies/README.md) para o que a forma tem de fazer e o que ela não
consegue mostrar.

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

**Fechar exatamente ou falhar.** Os efeitos de variação somam ao movimento sem resíduo, e
`waterfall()` levanta erro em vez de desenhar barras que não fecham no total final.
Decomposição com linha de ajuste é rateio com linha de ajuste, e é no ajuste que as
discordâncias se escondem.

**Nunca reportar estimativa pontual estocástica como resposta.** Resultados de simulação vêm com
intervalo de confiança, e cenário cujo intervalo se sobrepõe ao da base é reportado como
indistinguível, não como melhoria pequena.

**Recusar as perguntas que o modelo não responde.** Um custo de roteirização carrega o orçamento
de busca sob o qual foi produzido, e onde a conclusão se inverte dentro dessa faixa a resposta
documentada é que o modelo não decide. O orçamento é contagem reproduzível de soluções, não
cronômetro, porque limite de tempo de parede faz a resposta depender da máquina.

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
- A decomposição de variação é tão boa quanto sua segmentação — mix é invisível em dimensão
  pela qual você não segmenta — e não separa custo fixo de variável, então alavancagem
  operacional se esconde no efeito taxa. Também compara dois períodos sem testar se o movimento
  excede a variação normal; carte com `oplab.spc` antes.
- A simulação de capacidade mantém mão de obra de recebimento e expedição em pools separados,
  retém recurso durante a parada de turno, e deixa carregamento, reabastecimento e distância
  percorrida fora de escopo. Ver o [README do módulo](src/oplab/simulation/README.md); a
  primeira premissa em especial subestima o valor de realocar pessoal entre as áreas.
- A roteirização usa distância em linha reta multiplicada por um fator de circuidade presumido e
  uma velocidade média única, um pedido por parada, um tipo de veículo por solve, um dia
  determinístico, e sem prova de otimalidade. A *ordenação* de cenários sobrevive a tudo isso; os
  custos absolutos não, e a própria ordenação pode se inverter com orçamento de busca pequeno.
  Ver o [README do módulo](src/oplab/routing/README.md).
- O benchmarking só remove mix na dimensão pela qual você estratifica, ajusta sem explicar, e
  seu DEA é determinístico sem barra de erro. Ver o
  [README do módulo](src/oplab/benchmark/README.md).
- O módulo de previsão é harness de medição com baselines, não biblioteca de modelos: sete
  regras de uma linha, sem ETS ou ARIMA, sem regressor exógeno e sem intervalo de previsão. Um
  modelo sério pertence ao mesmo harness, comparado na mesma tabela. Ver o
  [README do módulo](src/oplab/forecast/README.md).
- O laboratório de estoque é de eco único e um fornecedor por item, reamostra demanda sem
  autocorrelação, assume venda perdida em vez de carteira, e não dimensiona itens
  intermitentes. A simulação precisa de warm-up, e o warm-up é o achado: sem ele a mesma
  política mediu entre 89,3% e 97,3% de serviço de ciclo nos mesmos dados. Ver o
  [README do módulo](src/oplab/inventory/README.md).
- O process mining aqui descobre um grafo de sucessão direta, que registra o que seguiu o quê e
  não expressa escolha, divisão paralela nem fronteira de laço; sua checagem de conformidade é
  teste de subsequência, não alinhamento, e o achado 11 é em parte uma afirmação sobre esse
  limite. Ver o [README do módulo](src/oplab/mining/README.md).

## Desenvolvimento

```bash
make install    # instalação editável com as ferramentas de desenvolvimento
make check      # lint, formatação, tipos e a suíte rápida - o que barra um push
make check-all  # o acima mais toda figura documentada re-derivada
make claims     # re-deriva todo número citado em um README
```

**565 testes, 96% de cobertura de statements, separados por custo.** 541 deles rodam em cerca de
vinte e cinco segundos — menos de um minuto para a sequência inteira do `make check`, com os
linters, a checagem de tipos e a cobertura — e é o que barra um push. Os 24 restantes re-resolvem
os problemas de roteirização, re-replicam as simulações, re-rodam os backtests de previsão e as
políticas de estoque, e executam os doze exemplos e os quatro estudos para verificar toda figura
citada acima; levam cerca de dez minutos (10m18s e 10m19s nas duas execuções mais recentes), e não
dependem da versão do interpretador — então a CI roda o portão rápido em Python 3.10 e 3.12 e a
verificação de figuras uma vez.

Esse número dobrou na onda 8, e não por causa de um estudo novo: fixar a varredura de orçamento de
busca da roteirização custa oito solves de roteirização de veículos, cerca de noventa segundos, em
toda execução. Comprar a correção de uma afirmação publicada custou esse tempo de CI de forma
permanente — troca certa contra deixar a prosa errada de pé, mas uma troca, não uma melhoria de
graça.

O `make check` existe porque a alternativa falhou duas vezes: rodar o linter e esquecer o
formatador, e rodar uma ferramenta local mais antiga que a instalada pela CI. As duas
transformaram uma mudança correta em build vermelho, então os linters estão fixados em release
compatível e a sequência inteira vive em um único alvo.

## Licença

MIT. Ver [`LICENSE`](LICENSE).
