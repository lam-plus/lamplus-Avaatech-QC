# Desenvolvimento — LAM+ Core QC

Este documento descreve a implementação atual do **LAM+ Core QC**, registra as decisões metodológicas que orientam o código e preserva o histórico técnico de correções e validações. O arquivo `TODO.md` deve conter apenas pendências, decisões em aberto e próximos passos.

---

## 1. Visão geral

O LAM+ Core QC é um pipeline de controle de qualidade para dados exportados pelo **Avaatech XRF Core Scanner**. O sistema recebe arquivos Excel com uma ou mais abas de energia, executa módulos estatísticos independentes de QC, calcula indicadores por medição, produz diagnósticos gráficos e exporta os resultados anotados.

O aplicativo foi desenvolvido para uso no **LAM+ — Laboratório de Análise Multiespectral e Inteligência Artificial para Sedimentos, UFF**.

### 1.1 Objetivo científico

O pipeline busca responder:

> **A medição foi adquirida de forma tecnicamente confiável?**

Ele não deve interpretar se uma composição geoquímica é ambientalmente comum ou incomum. Mudanças sedimentológicas reais, eventos abruptos, cinzas, turbiditos, sapropéis e outras assinaturas geoquímicas legítimas não devem ser automaticamente confundidas com erro instrumental.

Nenhum dado é eliminado automaticamente. Os flags indicam níveis de revisão recomendada.

---

## 2. Arquitetura atual

### 2.1 Módulos principais

- `qc_core.py`  
  Biblioteca central, sem dependência de Streamlit. Contém leitura de workbooks, validação, módulos estatísticos, scores, Quality Index, Quality Flags e explicabilidade.

- `qc_avaatech.py`  
  Interface Streamlit. Faz upload, seleção de opções, processamento por aba/energia, gráficos, tabela e exportação Excel.

- `report_pdf.py`  
  Componentes de relatório PDF. Atualmente inclui detecção e apresentação de intervalos problemáticos; o relatório completo ainda não está integrado à UI.

- `i18n.py`  
  Carregador das traduções.

- `locales/pt.json` e `locales/en.json`  
  Textos da interface e mensagens de validação. Português é o idioma padrão.

- `iniciar.py`  
  Launcher multiplataforma.

- `setup_shortcut.py`  
  Criação opcional de atalho no Windows ou Linux.

- `installer/`  
  Empacotamento standalone com PyInstaller.

### 2.2 Princípios de organização

- `qc_core.py` deve permanecer independente de UI.
- Nomes de colunas do Avaatech são preservados literalmente.
- Strings de interface ficam em `locales/*.json`.
- O Python do `.venv` deve ser usado em execução, teste e instalação.
- Resultados devem ser validados contra arquivos reais antes de uma mudança ser considerada concluída.
- Executáveis gerados não são versionados; a distribuição ocorre por GitHub Releases.

---

## 3. Entrada de dados e estrutura multi-energia

O sistema aceita:

- arquivo de aba única;
- workbook com abas `10kV`, `30kV` e opcionalmente `50kV`.

A energia é detectada pelo nome da aba, de forma case-insensitive.

### 3.1 Configuração por energia

| Energia | Throughput | Argônio | Coerente | Incoerente |
|---|---|---|---|---|
| 10 kV | `Throughput` | `Ar-Ka Area` | `Rh-La Area` | `Rh-La-Inc Area` |
| 30 kV | `Throughput` | não aplicável | `Rh-Ka-Coh Area` | `Rh-Ka-Inc Area` |
| 50 kV | `Throughput` | não aplicável | não aplicável | não aplicável |

Módulos estruturalmente ausentes em uma energia não são tratados como dados faltantes. Eles recebem comportamento neutro e seus pesos são removidos do QI com renormalização.

### 3.2 Profundidade

A coluna preferencial é:

```text
CompositeDepth (mm)
```

Quando ela não existe, o pipeline usa:

```text
CoreDepth
```

como fallback.

Esse fallback é seguro apenas para testemunhos de seção única. Em testemunhos multi-seção, `CoreDepth` reinicia em cada seção e não representa uma profundidade contínua global.

### 3.3 Réplicas

O processamento principal usa `Rep0`. O casamento entre réplicas é feito pela chave:

```python
["Spectrum", "CoreDepth"]
```

Essa escolha é deliberada. `CompositeDepth (mm)` costuma estar preenchido apenas em `Rep0`, enquanto `CoreDepth` permanece disponível nas demais réplicas.

---

## 4. Módulos de controle de qualidade

### 4.1 QC1 — Instrument Stability

Avalia estabilidade instrumental.

- Em 10 kV: combina `Throughput` e `Ar-Ka Area`.
- Em 30 e 50 kV: usa `Throughput`.

Para cada linha, `Instrument_z` recebe o z-score robusto de maior magnitude absoluta entre Throughput e Argônio. Assim, um problema detectado por apenas um dos dois parâmetros não é mascarado.

As colunas individuais permanecem disponíveis:

- `Throughput_z`
- `Argon_z`
- `Instrument_z`

### 4.2 QC2 — Coherent Scatter

Avalia a geometria de aquisição.

- 10 kV: `Rh-La Area`
- 30 kV: `Rh-Ka-Coh Area`
- 50 kV: não aplicável

### 4.3 QC3 — Incoherent Scatter

Avalia mudanças na interação entre o feixe e a matriz física.

- 10 kV: `Rh-La-Inc Area`
- 30 kV: `Rh-Ka-Inc Area`
- 50 kV: não aplicável

### 4.4 QC4 — Rolling QC

Detecta anomalias locais comparando cada ponto com sua vizinhança.

Procedimento:

1. média móvel centrada;
2. diferença entre o ponto e a média local;
3. z-score robusto da diferença.

A janela padrão é de cinco pontos.

#### Comportamento padrão

Por padrão, o score usa a variável incoerente da energia:

- `Rh-La-Inc Area` em 10 kV;
- `Rh-Ka-Inc Area` em 30 kV;
- fallback para parâmetros disponíveis em 50 kV.

#### Combinação de variáveis

A opção `combine_rolling_vars=True` usa o maior valor absoluto entre os deltas-z disponíveis. É uma opção mais sensível, mas pode reagir também a deriva instrumental que não afete diretamente o sinal espectral.

#### Persistência temporal

A opção `use_rolling_persistence=True` exige persistência da anomalia:

- pelo menos dois pontos acima do limiar;
- dentro de uma janela centrada de três medidas.

O comportamento padrão permanece desligado para preservar a filosofia de defesa em profundidade, na qual um ponto isolado pode ser relevante.

### 4.5 QC5 — Réplicas

Avalia reprodutibilidade por **Relative Percent Difference (RPD)**.

Elementos considerados, quando disponíveis:

- Al
- Si
- K
- Ca
- Ti
- Fe

A função retorna `NaN` quando:

- há menos de duas medidas;
- a média é zero;
- não há elementos utilizáveis.

### 4.6 QC6 — PCA e Mahalanobis

Executa PCA sobre os elementos disponíveis e calcula a distância de Mahalanobis.

O módulo:

- requer ao menos dois elementos;
- requer ao menos três linhas;
- usa `np.linalg.pinv` para maior robustez;
- degrada graciosamente quando não pode ser calculado.

A PCA é sempre produzida como diagnóstico, mas por padrão não influencia QI/QF. A opção `include_pca_in_qf=True` ativa:

- o peso da PCA no QI;
- os critérios diretos de Mahalanobis no QF.

---

## 5. Quality Index e Quality Flags

### 5.1 Quality Index

O QI é uma combinação ponderada dos scores disponíveis.

Pesos nominais:

| Score | Peso |
|---|---:|
| Instrument Stability | 0,25 |
| Coherent Scatter | 0,15 |
| Incoherent Scatter | 0,20 |
| Rolling QC | 0,20 |
| Réplicas | 0,15 |
| PCA | 0,05 |

Quando um módulo é estruturalmente inaplicável, seu peso é removido e os demais pesos são renormalizados.

### 5.2 Dados faltantes

Linhas com dados críticos ausentes recebem:

```text
QF = 9
```

Esse código representa **Indeterminado**, não OK e não rejeição.

A opção `strict_missing_data` controla apenas o QI:

- `True`: QI fica `NaN`;
- `False`: QI é recalculado com os módulos disponíveis.

O QF permanece 9 em ambos os modos.

### 5.3 Modo ponderado

É o modo padrão. Combina:

- QI contínuo;
- critérios pontuais de z-score;
- Mahalanobis, quando ativada;
- defesa em profundidade.

Um critério pontual pode elevar o QF mesmo quando o QI agregado permanece alto.

### 5.4 Modo por contagem

A opção `use_count_mode=True` implementa a filosofia do protocolo v4.2.

Cada módulo é classificado como:

- OK
- ALERT
- CRITICAL

Regra final:

| QF | Critério |
|---|---|
| QF0 | nenhum ALERT e nenhum CRITICAL |
| QF1 | um ALERT |
| QF2 | dois ou três ALERTs, ou um CRITICAL |
| QF3 | dois ou mais CRITICALs, ou quatro ou mais ALERTs |

NaN crítico nunca é tratado como OK; continua produzindo QF 9.

### 5.5 Explicabilidade

O pipeline registra causas em `QF_Causes`, incluindo:

- throughput;
- argônio;
- espalhamento coerente;
- espalhamento incoerente;
- rolling;
- réplica;
- PCA;
- QI baixo;
- dado faltante.

Flags pontuais com QI alto recebem uma nota traduzida em `Pointwise_Flag_Note`.

---

## 6. Interface e produtos

### 6.1 Interface Streamlit

A interface oferece:

- idioma PT/EN;
- seleção da profundidade exibida;
- política de dados faltantes;
- combinação de variáveis no rolling;
- inclusão da PCA no QF;
- modo de QF ponderado ou por contagem;
- persistência temporal no rolling;
- seleção de aba/energia;
- gráficos diagnósticos;
- tabela completa;
- download do workbook processado.

### 6.2 Exportação Excel

O Excel de saída:

- preserva uma aba por energia;
- mantém as colunas originais;
- acrescenta colunas de QC;
- aplica cor apenas às colunas adicionadas pelo pipeline.

Cores:

- verde: OK / QF0 / NO;
- amarelo: WARNING / QF1;
- vermelho: CRITICAL / QF2 / QF3 / YES.

`QF_INDETERMINATE = 9` permanece sem preenchimento específico.

Atualmente, o export contém o subconjunto `Rep0`; a decisão sobre preservar Rep1/Rep2 continua aberta.

### 6.3 PDF

`report_pdf.py` implementa:

- agrupamento de pontos QF ≥ 2 em intervalos;
- causas agregadas;
- QF máximo;
- indicação de flag pontual;
- tabela traduzida.

A ordenação dos intervalos usa sempre a profundidade composta interna. A coluna escolhida para exibição altera apenas os valores apresentados.

O relatório completo por testemunho, com capa, gráficos e integração na UI, permanece pendente.

---

## 7. Internacionalização

O aplicativo usa:

```text
locales/pt.json
locales/en.json
```

Português é o idioma padrão.

Mensagens de validação são carregadas por `CHECK_MESSAGES`; os demais textos por `TEXTS`.

Os nomes de colunas do instrumento não são traduzidos, por decisão de rastreabilidade e compatibilidade técnica.

---

## 8. Empacotamento standalone

O diretório `installer/` permite gerar:

- `.exe` no Windows;
- binário equivalente no Linux.

O entry point é `installer/launcher.py`, que chama o Streamlit programaticamente.

O build Windows foi validado de ponta a ponta em 2026-06-29:

- executável onefile;
- aproximadamente 150 MB;
- servidor Streamlit respondendo HTTP 200;
- dependências dinâmicas incluídas;
- correção para DLLs de ambientes conda/miniforge;
- file watcher desativado.

O build Linux ainda não foi validado.

Executáveis e diretórios de build não são versionados.

---

# Histórico de achados e validações

## 9. Achados críticos

### 9.1 C1 — QC5 inoperante com dados reais

**Data:** 2026-06-28  
**Status:** resolvido.

#### Problema

O algoritmo casava réplicas usando `CompositeDepth (mm)`. No arquivo real, essa coluna estava preenchida apenas em `Rep0`; em Rep1/Rep2 permanecia nula.

Consequências:

- nenhum grupo de réplicas era encontrado;
- `Mean_RPD` ficava `NaN` em todas as linhas;
- `Score_Replica` recebia 100 por fallback;
- QC5 contribuía com 15% do QI como nota perfeita, silenciosamente.

#### Investigação

`CoreDepth`, combinado com `Spectrum`, identifica corretamente a posição física e permanece preenchido nas réplicas.

#### Correção

- criação de `REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]`;
- validação das duas colunas;
- agrupamento por `groupby`;
- merge pela mesma chave.

#### Validação

No arquivo de exemplo:

- 12 posições com réplicas foram recuperadas;
- `Mean_RPD` passou a conter valores entre 0,70% e 5,03%;
- `Score_Replica` passou a variar de aproximadamente 79,9 a 100.

A política para posições sem réplica continua sendo uma decisão metodológica em aberto.

### 9.2 C2 — Dados faltantes classificados como OK

**Data:** 2026-06-28  
**Status:** resolvido.

#### Problema

Comparações com NaN retornavam falso e o fluxo terminava em QF0. Uma linha com dado crítico faltante podia ser rotulada como OK.

#### Correção

- criação de `QF_INDETERMINATE = 9`;
- identificação de dados críticos faltantes antes das regras de QF;
- separação entre política de QI restritiva/flexível e o flag indeterminado;
- suporte visual na UI.

#### Validação

Cinco NaNs sintéticos em `Throughput` produziram QF9 em ambos os modos de QI. Nenhuma linha caiu em QF0.

---

## 10. Correções e decisões implementadas

### 10.1 RPD com média zero

`calculate_rpd` passou a retornar `NaN` quando a média é zero, evitando `inf` e warnings numéricos.

Validado com:

```python
calculate_rpd([10, -10])
calculate_rpd([0, 0, 0])
```

### 10.2 PCA insuficiente

A PCA deixa de lançar exceção quando faltam elementos ou linhas.

- mínimo de dois elementos;
- mínimo de três linhas;
- score neutro;
- warning bilíngue;
- `pinv` para covariância quase singular.

### 10.3 Flag pontual

Critérios pontuais continuam podendo elevar o QF apesar de QI ≥ 80. Esses casos agora são identificados e explicados na tabela e no PDF.

### 10.4 Leitura multi-aba

A leitura silenciosa apenas da primeira aba foi substituída por `read_workbook`, com processamento independente de cada energia.

### 10.5 Fallback de profundidade

`CompositeDepth (mm)` deixou de ser obrigatório. Quando ausente, `CoreDepth` é usado e um warning é emitido.

A limitação para testemunhos multi-seção é explicitamente documentada.

### 10.6 Rolling combinado

Foi implementada uma opção para usar o maior `|delta_z|` entre as variáveis disponíveis.

Decisão de default:

- variável incoerente sozinha;
- combinação apenas por opt-in.

Foi rejeitada a alternativa de checkboxes independentes por variável, para evitar combinações metodologicamente inconsistentes.

### 10.7 Profundidade exibida

A UI permite alternar entre `CompositeDepth (mm)` e `CoreDepth` apenas para exibição.

A escolha não altera cálculos nem agrupamento de réplicas.

### 10.8 PCA diagnóstica

A PCA passou a ser diagnóstica por padrão e opcional no QI/QF.

Validação no arquivo de exemplo:

- PCA incluída: `{0:201, 2:49, 3:20}`;
- PCA excluída: `{0:208, 2:45, 3:17}`.

### 10.9 Modo por contagem

O modo de contagem do protocolo v4.2 foi implementado como opt-in.

Validação no arquivo de exemplo:

- modo ponderado: `{0:199, 1:1, 2:42, 3:28}`;
- modo por contagem: `{0:229, 1:20, 2:21}`;
- contagem com PCA: `{0:218, 1:26, 2:26}`.

### 10.10 Argônio em QC1 e QC4

A integração do Argônio alterou a distribuição esperada de QF porque um parâmetro antes ignorado passou a contribuir para o QC.

Validação:

- antes: `{0:208, 2:45, 3:17}`;
- depois: `{0:199, 1:1, 2:42, 3:28}`.

Sem `Ar-Ka Area`, o pipeline reproduz o comportamento anterior.

### 10.11 Coloração do Excel

A coloração foi restringida às colunas de QC para evitar colisões com valores numéricos 0–3 em scores contínuos.

### 10.12 Persistência no rolling

A persistência foi implementada como opt-in.

Durante o desenvolvimento, uma primeira versão zerava também pontos normais. O erro foi corrigido para zerar apenas:

```python
anomaly & ~persistent
```

### 10.13 Estrutura multi-energia

A implementação foi validada contra workbooks reais.

Resultados de referência para `Dados Consolidados-ICCE3.xlsx`:

| Energia | QF ponderado |
|---|---|
| 10 kV | `{0:49,2:7,3:9}` |
| 30 kV | `{0:38,2:17,3:10}` |
| 50 kV | `{0:46,2:10,3:9}` |

Em 50 kV:

- QC2/QC3 ficam neutros;
- seus pesos são excluídos;
- QI permanece computável.

---

## 11. Protocolo v4.2 de Igor Oliveira

O protocolo v4.2 consolidou cinco módulos instrumentais:

1. Instrument Stability;
2. Coherent Scatter;
3. Incoherent Scatter;
4. Rolling QC;
5. Replicates.

Contribuições incorporadas:

- Argônio no QC1;
- mapeamento por energia;
- persistência opcional;
- thresholds discretos no modo de contagem;
- QF por contagem;
- coloração do Excel;
- tratamento explícito de RPD com média zero.

Elementos não portados literalmente:

- casamento de réplicas por profundidade exata, porque reproduzia o bug C1;
- NaN tratado como OK, porque reproduzia o bug C2;
- substituição da arquitetura atual pelo script batch do apêndice;
- combinação obrigatória de todas as variáveis no rolling.

Decisões preservadas da implementação anterior:

- arquitetura `qc_core.py` + frontend Streamlit;
- i18n;
- PCA diagnóstica;
- QF9 indeterminado;
- seletor de profundidade exibida;
- explicabilidade por linha;
- PDF de intervalos.

---

## 12. Validação em lote com arquivos reais

**Data:** 2026-07-28.

O pipeline foi executado com os defaults:

- QI ponderado;
- `combine_rolling_vars=False`;
- `use_rolling_persistence=False`;
- PCA fora do QF.

Foram processadas 16 abas em seis arquivos, sem falha de `check_file` ou exceção em `run_qc`.

| Arquivo | Energia | n(Rep0) | Distribuição de QF |
|---|---|---:|---|
| Dados Consolidados-ICCE3.xlsx | 10/30/50 kV | 65/65/65 | `{0:49,2:7,3:9}` / `{0:38,2:17,3:10}` / `{0:46,2:10,3:9}` |
| Dados Consolidados-Itatiaia.xlsx | 10/30 kV | 77/77 | `{0:64,2:12,3:1}` / `{0:58,2:13,3:6}` |
| Dados Consolidados-OP42GC4.xlsx | 10/30/50 kV | 557/557/557 | `{0:427,2:63,3:67}` / `{0:413,2:81,3:63}` / `{0:424,2:77,3:56}` |
| Dados Consolidados-dgl1905.xlsx | 10/30/50 kV | 10518/10518/10518 | `{0:7608,1:20,2:1712,3:1178}` / `{0:8743,1:55,2:1118,3:602}` / `{0:8805,1:502,2:744,3:467}` |
| Dados Consolidados-trigoskoe.xlsx | 10/30 kV | 96/96 | `{0:73,1:1,2:13,3:9}` / `{0:74,1:2,2:16,3:4}` |
| Dados ConsolidadosICCE10.xlsx | 10/30/50 kV | 88/88/88 | `{0:59,2:14,3:15}` / `{0:72,2:8,3:8}` / `{0:67,2:14,3:7}` |

### 12.1 Avisos observados

- fallback de profundidade composta para `CoreDepth`;
- ausência esperada de elementos em algumas energias;
- Throughput zero ou nulo em ICCE3 e OP42GC4.

### 12.2 Alerta dgl1905

As três abas de `Dados Consolidados-dgl1905.xlsx` apresentam 9.311 profundidades duplicadas entre 10.518 linhas Rep0.

Hipótese principal:

- arquivo multi-seção;
- ausência de `CompositeDepth (mm)`;
- fallback para `CoreDepth`;
- reinício de `CoreDepth` em cada seção.

Esse arquivo deve ser investigado antes de usar os intervalos ou distribuições de QF como resultado definitivo.

### 12.3 PDFs gerados

Foram gerados PDFs em `data/reports/` para:

- ICCE3;
- Itatiaia;
- OP42GC4;
- dgl1905;
- trigoskoe;
- ICCE10.

Cada PDF contém os seis diagnósticos por aba e a página de intervalos problemáticos. A geração foi feita por script ad-hoc não versionado.

---

## 13. Estado atual

O pipeline atual oferece:

- suporte multi-energia;
- cinco módulos instrumentais;
- PCA diagnóstica;
- dois modos de QF;
- tratamento explícito de NaN;
- explicabilidade por causa;
- exportação Excel colorida;
- interface bilíngue;
- processamento independente por aba;
- empacotamento standalone no Windows;
- validação em lote com arquivos reais.

Pendências, decisões em aberto e próximos passos devem permanecer exclusivamente em `TODO.md`.
