# Desenvolvimento — LAM+ Core QC V2

## 1. Objetivo da V2

A V2 será uma implementação mais simples, modular e auditável do controle de
qualidade de aquisição de dados do Avaatech XRF Core Scanner.

A prioridade desta versão é:

- manter o foco no controle de qualidade da aquisição;
- reduzir o número de opções configuráveis;
- diminuir o acoplamento entre leitura, cálculo, interface e exportação;
- produzir código mais fácil de compreender e testar;
- oferecer uma saída direta e rastreável;
- simplificar a manutenção.

A V2 começa com um núcleo pequeno e bem definido. Funcionalidades adicionais
só deverão ser consideradas depois que esse núcleo estiver estabilizado,
testado com dados reais e documentado.

## 1.1 O que este app faz (estado atual)

Além do núcleo QC1–QC5 descrito na seção 3, a interface (`qc_avaatech.py`) e
os módulos de apoio (`i18n.py`, `qc_audit.py`, `qc_reports.py`) já
implementam:

- **Interface bilíngue EN/PT.** Seletor de idioma na sidebar
  (`i18n.SUPPORTED_LANGS`); todas as strings da interface, mensagens de
  validação e resumo (`summary.txt`) vêm de `src/locales/en.json` /
  `src/locales/pt.json` via `i18n.load`. Chave ausente na tradução nunca
  quebra a interface — cai para o valor em EN.
- **Mensagens de validação traduzidas.** `qc_io.check_columns` recebe o
  dict de strings já carregado (não importa `i18n.py` diretamente — ver
  decisão em 4.4) e usa exclusivamente as chaves `validation_*` para
  erros/avisos de colunas obrigatórias, ausência de `Rep0` e fallback de
  coluna de profundidade.
- **Auditoria em SQLite com toggle na sidebar.** `qc_audit.py` registra
  uma linha por aba/energia processada com sucesso em `data/audit.db`
  (operador, arquivo + MD5, commit git, versão do pipeline, distribuição
  de QF, avisos, tempo de execução). O registro só acontece quando o
  toggle "Enable audit log" está ativo — **desligado por padrão** (ver
  decisão em 4.4). Com o toggle ligado, uma aba "Histórico" aparece,
  consultando `qc_audit.query_runs` com filtro por arquivo/operador.
- **Degradação graciosa em ambiente web/hospedado.** Falhas ao
  registrar (`register_run`) ou consultar (`query_runs`) a auditoria —
  ex. `data/` somente leitura ou efêmero em Streamlit Community Cloud —
  são capturadas e nunca aparecem como erro/traceback ao usuário; caem no
  mesmo aviso amigável exibido quando simplesmente não há execuções
  registradas ainda.
- **Sumário visual por energia.** Cards de métricas (`n(Rep0)`,
  QF0–QF3, INDETERMINATE), barra de distribuição de QF colorida (HTML via
  `st.html`, já que `st.progress` não suporta cor por segmento), tabela de
  contagem ALERT/CRITICAL por módulo (QC1–QC5) e lista de profundidades
  com `Review = YES` (causa principal + evidências). Usa `st.tabs` por
  energia quando o arquivo tem múltiplas abas.
- **`summary.txt` bilíngue.** `qc_reports.format_summary_text` monta o
  resumo para download inteiramente a partir de `strings["summary_*"]`
  (i18n) — baixar com EN selecionado produz texto em inglês; com PT,
  inteiramente em português, incluindo o sufixo do nome do arquivo
  (`_summary`/`_resumo`).
- **Campo "Operador" opcional na sidebar**, texto livre, registrado em
  cada execução de auditoria.
- **Documentação dos módulos QC1–QC5 e QF na sidebar.** `src/docs/`
  contém um arquivo Markdown por módulo (`QC1_instrument_stability.md`
  .. `QC5_replicates.md`) mais `QF_quality_flags.md`; a sidebar exibe
  esse conteúdo via expander "Protocol Reference"
  (`_render_protocol_reference`), com `st.selectbox` para escolher o
  módulo. O conteúdo dos docs é sempre em inglês (fonte técnica única),
  independente do idioma da interface — só o label do expander e do
  seletor são traduzidos.
- **Botão de feedback por email na sidebar.** `_render_feedback_button`
  monta um `st.link_button` com URL `mailto:` (`_feedback_mailto_url`)
  para os destinatários fixos `andrebelem@id.uff.br` e
  `ivenancio@id.uff.br` (`FEEDBACK_RECIPIENTS`), com assunto e corpo
  pré-preenchidos vindos do i18n (`feedback_subject`/`feedback_body`),
  para o operador reportar problemas ou sugestões sem sair da interface.

## 2. Relação com `LEGACY/`

`LEGACY/` preserva a implementação estável anterior, sua documentação técnica,
suas decisões metodológicas e seu histórico de validações. Ela serve para
consulta, comparação de resultados e recuperação do comportamento anterior.

A V2 pode consultar conceitos, regras e trechos da implementação legada durante
o desenvolvimento. Entretanto:

- a V2 não pode importar módulos de `LEGACY/` em runtime;
- `LEGACY/` é referência, não dependência;
- nenhum caminho da V2 deve apontar para recursos internos de `LEGACY/`;
- qualquer comportamento reaproveitado deve ser implementado explicitamente
  na V2;
- testes da V2 devem conseguir executar sem adicionar `LEGACY/` ao
  `PYTHONPATH`.

Essa separação permite evoluir a nova arquitetura sem alterar o comportamento
histórico preservado.

## 3. Escopo funcional inicial

O núcleo inicial seguirá uma proposta simplificada baseada no protocolo do
Igor:

- **QC1 — Instrument Stability:** estabilidade instrumental;
- **QC2 — Coherent Scatter:** avaliação do espalhamento coerente;
- **QC3 — Incoherent Scatter:** avaliação do espalhamento incoerente;
- **QC4 — Rolling QC:** detecção de anomalias locais;
- **QC5 — Replicates:** avaliação da reprodutibilidade entre réplicas;
- atribuição de QF por contagem dos estados dos módulos;
- processamento de workbooks multi-energia;
- exportação dos resultados em Excel;
- geração de resumo simples.

O núcleo inicial não incluirá PCA. Também não oferecerá múltiplas filosofias
concorrentes para cálculo de QF nem excesso de opções metodológicas na
interface.

## 4. Princípios de implementação

### 4.1 Organização

- Manter uma única fonte de verdade para configurações, limiares e estados.
- Preferir funções pequenas, com entradas e saídas explícitas.
- Separar leitura, validação, cálculo, classificação e exportação.
- Evitar estado global mutável e dependências implícitas da interface.
- Cobrir as regras científicas e os casos de borda com testes automatizados.

### 4.2 Dados faltantes e aplicabilidade

- Emitir mensagens claras quando dados obrigatórios estiverem ausentes.
- Nunca tratar `NaN` como estado OK.
- Representar dados indeterminados separadamente dos estados QF0–QF3.
- Tratar módulos não aplicáveis a uma energia como neutros, sem confundi-los
  com dados críticos ausentes.
- Tornar explícito quais módulos e variáveis participaram da classificação.

### 4.3 Integridade e rastreabilidade

- Não alterar automaticamente as colunas ou os valores originais.
- Acrescentar resultados de QC de forma identificável.
- Registrar a causa principal e as evidências que sustentam cada flag.
- Documentar decisões metodológicas e mudanças de comportamento.
- Manter resultados reproduzíveis para uma mesma entrada e configuração.

### 4.4 Decisões registradas (i18n e auditoria)

- **Auditoria desligada por padrão** (`audit_enabled = False` em
  `qc_avaatech.main`). Motivo: em ambientes hospedados/efêmeros (ex.
  Streamlit Community Cloud), `data/` pode ser somente leitura ou não
  persistir entre sessões, além de não fazer sentido gravar
  automaticamente sem consentimento explícito do operador. Quem quiser
  rastreabilidade local liga o toggle na sidebar; com o toggle desligado,
  a aba "Histórico" nem é criada.
- **EN como idioma padrão** (`i18n.DEFAULT_LANG = "en"`, primeiro em
  `i18n.SUPPORTED_LANGS`). Motivo: consistência com a literatura e o
  protocolo QC internacionais e com colaborações fora do Brasil; PT
  continua disponível como alternativa completa (toda chave existe nos
  dois locales, com fallback para EN se faltar).
- **`qc_io.check_columns` recebe o dict de strings do i18n já resolvido
  pelo chamador**, em vez de importar `i18n.py` diretamente. Motivo:
  mantém `qc_io.py` livre de dependência de interface/idioma — quem
  decide o idioma é a camada de UI (`qc_avaatech.py`), preservando o
  contrato do módulo (ver cabeçalho de `qc_io.py`: "não contém lógica de
  interface").

## 5. Estrutura proposta

Estrutura atual em `src/`:

```text
qc_core.py
qc_config.py
qc_io.py
qc_reports.py
qc_avaatech.py
qc_audit.py
i18n.py
locales/
    en.json
    pt.json
tests/
```

Responsabilidades:

- `qc_config.py`: energias, variáveis, limiares e estados;
- `qc_io.py`: leitura do workbook, detecção de energia e validação estrutural;
- `qc_core.py`: cálculos QC1–QC5 e integração dos estados;
- `qc_reports.py`: Excel e resumo simples;
- `qc_avaatech.py`: interface mínima;
- `qc_audit.py`: trilha de auditoria em SQLite (`data/audit.db`);
- `i18n.py`: carregamento das strings de interface a partir de
  `locales/en.json`/`locales/pt.json`, com fallback para EN;
- `locales/`: arquivos de tradução EN/PT usados por `i18n.py`;
- `tests/`: testes unitários, sintéticos e de integração.

`LEGACY/` não tem um `qc_config.py` separado: todas as constantes
(`DEPTH_COL`, `ENERGY_PARAMETERS`, pesos do QI, limiares etc.) vivem
embutidas no topo de `LEGACY/qc_core.py`. O `qc_config.py` da V2 não é,
portanto, um port direto de um arquivo homônimo em `LEGACY/` — é uma
extração deliberada dessas constantes para um módulo próprio, consolidando
numa única fonte de verdade o que antes estava disperso dentro do núcleo de
cálculo. `i18n.py`, `qc_audit.py` e `locales/` não faziam parte da proposta
original desta seção — foram acrescentados depois da estabilização do
núcleo (ver seção 1.1 e seção 8).

Uma mudança nessa estrutura deve preservar a separação de responsabilidades.

## 6. Contrato da V2

A V2 deverá:

1. ler workbooks exportados pelo Avaatech;
2. detectar a energia de cada aba suportada;
3. validar as colunas necessárias para aquela energia;
4. selecionar as medições `Rep0`;
5. usar réplicas adicionais quando estiverem disponíveis;
6. devolver um estado explícito para cada módulo QC aplicável;
7. produzir QF0, QF1, QF2 ou QF3 por contagem dos estados;
8. marcar dados indeterminados em uma categoria separada;
9. registrar causa principal e evidências de apoio;
10. exportar os resultados sem alterar as colunas originais.

Entradas inválidas devem produzir mensagens acionáveis. A ausência legítima de
um módulo em determinada energia não deve penalizar o resultado, enquanto a
ausência de um dado obrigatório não pode resultar em OK.

## 7. Validação

A V2 foi validada contra:

- os arquivos reais já usados para validar a versão em `LEGACY/`;
- resultados esperados definidos antes da implementação;
- casos sintéticos que isolam cada regra;
- testes de regressão para os achados críticos C1 e C2.

O teste de C1 (`test_qc5_regression_c1_matches_by_spectrum_and_coredepth_not_composite_depth`)
garante que as réplicas sejam associadas por uma chave física válida
(`Spectrum` + `CoreDepth`), sem depender de profundidades ausentes em `Rep1`
ou `Rep2`.

O teste de C2 (`test_qc_integrate.py`) garante que um dado crítico ausente
nunca seja classificado como OK, independentemente da regra de agregação —
inclusive de ponta a ponta em `run_qc`.

Também existem testes multi-energia
(`test_multi_energy_file_icce3_has_three_independent_sheets`), testes de
dados malformados e uma comparação documentada entre os resultados da V2 e os
resultados históricos (`test_qc_core_vs_legacy.py`), com as diferenças
deliberadas justificadas ali e em `TODO.md`.

O pipeline foi validado contra os 7 arquivos reais em `data/` sem falhas. A
suíte de testes da V2 tem 194 testes, todos passando.

## 8. Fora do escopo inicial

Ficam fora do núcleo inicial:

- PCA;
- clustering;
- distância de Mahalanobis;
- relatório PDF complexo;
- múltiplos modos de QF;
- opções avançadas de rolling;
- interface excessivamente configurável;
- empacotamento sofisticado antes da estabilização do núcleo.

Esses itens poderão ser reavaliados após a conclusão dos critérios da primeira
versão funcional, sem criar dependência de runtime com `LEGACY/`.

Após a estabilização do núcleo QC1–QC5, os seguintes itens — não previstos
nesta seção originalmente — foram incorporados: suporte bilíngue EN/PT
(`i18n.py`, `src/locales/`), trilha de auditoria em SQLite (`qc_audit.py`,
desligada por padrão), sumário visual por energia na interface e degradação
graciosa da auditoria em ambiente web/hospedado (ver seção 1.1).

