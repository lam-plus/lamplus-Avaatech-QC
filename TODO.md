# TODO — LAM+ Core QC V2

Este arquivo contém somente o trabalho da V2 simplificada. O histórico e as
pendências da versão anterior estão em `LEGACY/TODO.md`.

## 1. Definições iniciais

- [x] Confirmar o escopo da V2.
- [x] Confirmar os módulos QC1–QC5.
- [x] Confirmar as regras de QF por contagem.
- [x] Confirmar o tratamento de QF indeterminado.
- [x] Confirmar o formato de saída.
- [x] Confirmar a estrutura de arquivos. (Etapa 1 — `qc_config.py`, `qc_io.py`,
      `qc_core.py`, `qc_reports.py`, `qc_avaatech.py`, `tests/` criados em `src/`
      com contratos/assinaturas, sem lógica científica ainda.)

## 2. Núcleo do pipeline

- [x] Criar a leitura multi-energia. (Etapa 2 — `qc_io.read_workbook`: lê
      todas as abas, detecta a energia pelo nome via `detect_energy` e
      ignora abas de nome desconhecido sem falhar o arquivo inteiro.)
- [x] Validar as colunas exigidas por energia. (Etapa 2 —
      `qc_io.check_columns`: colunas obrigatórias por energia via
      `ENERGY_VARIABLES`, com `errors`/`warnings` acionáveis; QC2/QC3 não
      exigidos quando a energia não os mede, ex. 50 kV.)
- [x] Selecionar as medições `Rep0`. (Etapa 2 — `qc_io.select_rep0`;
      réplicas adicionais detectadas por `qc_io.detect_replicates`.)
- [x] Implementar QC1 — Instrument Stability. (Etapa 3 —
      `qc_core.qc_instrument_stability`: z-score robusto de Throughput
      combinado com Argônio pelo "pior dos dois"; Throughput ausente por
      linha vira `QCState.INDETERMINATE`, nunca OK.)
- [x] Implementar QC2 — Coherent Scatter. (Etapa 3 —
      `qc_core.qc_coherent_scatter`; `NOT_APPLICABLE` em 50 kV via
      `ENERGY_VARIABLES["coherent"] is None`.)
- [x] Implementar QC3 — Incoherent Scatter. (Etapa 3 —
      `qc_core.qc_incoherent_scatter`, mesma estrutura de QC2.)
- [x] Implementar QC4 — Rolling QC. (Etapa 4 — `qc_core.qc_rolling`:
      média móvel centrada (`ROLLING_WINDOW`, `min_periods=1`) só da
      variável incoerente da energia; `NOT_APPLICABLE` em 50 kV; só
      OK/ALERT, sem CRITICAL; NaN na variável bruta vira `INDETERMINATE`.
      Persistência da LEGACY (`use_rolling_persistence`) não foi portada.)
- [x] Implementar QC5 — Replicates. (Etapa 4 — `qc_core.qc_replicates`:
      casamento por `Spectrum`+`CoreDepth` via `groupby`, nunca por
      `CompositeDepth` (achado C1); `calculate_rpd` idêntico à LEGACY
      (média zero → NaN, achado 1.1). Decisão confirmada com o usuário:
      posição sem réplica adicional → `QCState.NOT_APPLICABLE` — diverge
      deliberadamente da LEGACY, que usa OK; valores de `Mean_RPD` em si
      são idênticos, ver `test_qc_core_vs_legacy.py`.)
- [x] Integrar os estados dos módulos. (Etapa 5 —
      `qc_core.compute_module_states`: dict por linha
      `QCModule -> QCState`, a partir das colunas `QC1_State..QC5_State`
      já calculadas pelos módulos individuais.)
- [x] Calcular QF por contagem. (Etapa 5 — `qc_core.integrate_qc`: QF0
      sem alerta, QF1 = 1 ALERT, QF2 = 2-3 ALERTs ou 1 CRITICAL, QF3 = 2+
      CRITICALs ou 4+ ALERTs (protocolo v4.2, tabela do plano-de-acao.md).
      NOT_APPLICABLE nunca conta. INDETERMINATE em QC1/QC2/QC3
      (`MANDATORY_MODULES`) força `QualityFlag.INDETERMINATE`
      incondicionalmente, nunca QF0 (achado C2); INDETERMINATE em QC4/QC5
      (`OPTIONAL_MODULES`) não penaliza, só vira evidência — decisão
      confirmada com o usuário: QC4 é opcional porque sua única fonte de
      NaN é a mesma coluna bruta que já torna QC3 indeterminado na mesma
      linha, sem cobertura perdida. Coluna `Review`: YES para QF2, QF3 e
      INDETERMINATE (decisão confirmada: indeterminado também precisa de
      revisão humana), NO para QF0/QF1. Distribuição de QF comparada
      contra a LEGACY (modo de contagem, `use_count_mode=True`) em
      arquivos reais 10 kV/30 kV — bate exatamente; 50 kV diverge de
      propósito no QC4 (ver `test_qc_core_vs_legacy.py`).)
- [x] Registrar a causa principal e as evidências. (Etapa 5 —
      `integrate_qc` preenche `QF_Cause` (módulo de estado mais grave,
      desempate por ordem QC1..QC5; QC1 usa a causa já calculada por
      linha em `QC1_Cause` — throughput vs. argônio) e `QF_Evidence`
      (demais módulos em ALERT/CRITICAL, mais módulos opcionais
      INDETERMINATE marcados como `"{modulo}:indeterminate"`).)

## 3. Robustez

- [x] Impedir que `NaN` seja classificado como OK. (Etapa 3 —
      QC1/QC2/QC3 usam `QCState.INDETERMINATE`, distinto de OK, quando o
      dado crítico da linha está ausente; `classify_zscore` levanta
      `ValueError` se chamado com NaN. Etapa 5 — `integrate_qc` propaga
      isso para `QualityFlag.INDETERMINATE`, nunca QF0, ver achado C2
      abaixo.)
- [x] Testar a ausência de `Rep0`. (Etapa 2 — `test_qc_io.py`:
      `check_columns`/`select_rep0` reportam erro acionável, sem exceção
      não tratada.)
- [x] Testar a ausência de réplicas adicionais. (Etapa 2 —
      `detect_replicates`/`select_rep0` funcionam normalmente só com Rep0;
      ausência de Rep1/Rep2 não é erro estrutural.)
- [x] Testar média zero no cálculo de RPD. (Etapa 4 —
      `test_calculate_rpd_nan_when_mean_is_zero`/
      `test_qc5_zero_mean_element_does_not_block_other_valid_elements`:
      vira NaN, nunca infinito; um elemento com média zero não derruba o
      RPD médio se outro elemento for computável.)
- [x] Testar módulos não aplicáveis a uma energia. (Etapa 3 —
      `test_qc_core.py`: QC2/QC3 em 50 kV retornam `QCState.NOT_APPLICABLE`
      em 100% das linhas, distinto de `INDETERMINATE`.)
- [x] Testar workbook com abas inesperadas. (Etapa 2 —
      `read_workbook` move para `skipped` sem falhar o arquivo.)
- [ ] Testar tipos de dados inválidos.

## 4. Saída

- [x] Exportar resultados em Excel. (Etapa 6 —
      `qc_reports.build_excel_report`: uma aba de saída por aba processada,
      preservando o nome original da aba.)
- [x] Preservar as colunas originais. (Etapa 6 — colunas originais do
      instrumento copiadas intactas e na ordem original; colunas QC
      (`QC_EXPORT_COLUMNS`) só são acrescentadas ao final, nunca
      substituem/alteram as originais.)
- [x] Adicionar colunas de QC. (Etapa 6 — `QC1_State..QC5_State`,
      `QF_Cause`, `QF_Evidence`, `QualityFlag` (rótulo textual de `QF` via
      `format_quality_flag`: "QF0".."QF3"/"INDETERMINATE") e `Review`.
      Saída deliberadamente reduzida a este conjunto — colunas
      intermediárias do cálculo (z-scores, `Mean_RPD`,
      `QC_Module_States`, contagens) ficam só no `rep0` interno de
      `qc_core.run_qc`, não no Excel de saída, para manter a saída
      "direta e rastreável" (DEVELOPMENT.md 4.1). Coloração condicional
      verde/amarelo/vermelho restrita às colunas QC, nunca nas originais
      — verificado inclusive quando uma coluna original tem valores que
      coincidem textualmente com um estado QC.)
- [x] Adicionar uma aba de intervalos sinalizados. (Etapa 6 — aba
      "Flagged_Intervals": todas as linhas `Review="YES"` de todas as
      abas processadas, concatenadas e identificadas por `Sheet`/`Energy`.)
- [x] Gerar um resumo simples. (Etapa 6 — `qc_reports.build_summary` +
      `format_summary_text`: nome do arquivo; por energia, `n(Rep0)`,
      distribuição QF0-QF3/INDETERMINATE e contagem de ALERT/CRITICAL por
      módulo (abas com a mesma energia são agregadas juntas); lista de
      profundidades com `Review=YES` com causa principal e evidências.)

## 5. Interface mínima

- [x] Implementar upload de arquivo. (Etapa 6 — `qc_avaatech.py`:
      `st.file_uploader` para o workbook `.xlsx`.)
- [x] Implementar seleção do arquivo de entrada. (Etapa 6 — não há
      seleção adicional além do upload: `qc_io.read_workbook` já detecta
      todas as abas/energias do arquivo enviado, sem seletor de aba
      separado — mantém a interface simples, ver DEVELOPMENT.md 4.1.)
- [x] Executar o processamento. (Etapa 6 — `check_columns` roda por aba
      antes do botão "Executar QC" ficar disponível: erros bloqueiam
      aquela aba (nunca entra no pipeline), avisos aparecem mas não
      impedem; `run_qc` só roda para as abas validadas, ao clicar no
      botão. Resultado guardado em `st.session_state` para sobreviver aos
      reruns disparados pelos botões de download.)
- [x] Exibir um resumo dos resultados. (Etapa 6 — métricas por energia
      (`n(Rep0)`, QF0-QF3, INDETERMINATE) via `st.metric` + tabela
      completa (`st.dataframe`) por aba processada.)
- [x] Disponibilizar o download. (Etapa 6 — dois `st.download_button`:
      Excel de saída (`qc_reports.build_excel_report`) e resumo em texto
      (`qc_reports.format_summary_text`).)
- [x] Manter opções avançadas fora da interface inicial. (Etapa 6 — sem
      PCA, sem seletor de modo de QF, sem checkboxes de configuração;
      único controle interativo é o upload + o botão "Executar QC".)

## 6. Testes

- [x] Criar testes unitários. (Etapa 6 — `test_qc_reports.py`: colunas
      originais preservadas intactas e na ordem original; colunas QC
      presentes e corretas ao final da aba; coloração restrita às colunas
      QC (nunca nas originais, mesmo com valores coincidentes tipo
      "OK"/"ALERT"/"CRITICAL" numa coluna original); aba
      "Flagged_Intervals" com só as linhas `Review="YES"` de todas as
      abas; `build_summary`/`format_summary_text` com os campos
      esperados. Suíte completa da V2 com 175 testes, todos passando;
      validado também de ponta a ponta contra
      `data/Dados Consolidados-ICCE3.xlsx` (real, 3 energias) e via
      `streamlit run qc_avaatech.py` (servidor sobe e responde HTTP 200).)
- [x] Criar teste de regressão para C1. (Etapa 4 —
      `test_qc5_regression_c1_matches_by_spectrum_and_coredepth_not_composite_depth`:
      réplicas com `CompositeDepth (mm)` ausente/NaN em Rep1 ainda casam
      corretamente via `Spectrum`+`CoreDepth`.)
- [x] Criar teste de regressão para C2. (Etapa 5 —
      `test_qc_integrate.py`:
      `test_mandatory_module_indeterminate_forces_qf_indeterminate`/
      `test_mandatory_indeterminate_never_becomes_qf0_even_with_nothing_else_flagged`
      no nível de `integrate_qc`, e `test_run_qc_end_to_end_synthetic_10kv`
      confirmando que Throughput ausente sobrevive ao pipeline completo de
      `run_qc` como `QualityFlag.INDETERMINATE`, nunca QF0.)
- [ ] Criar testes multi-energia.
- [x] Comparar os resultados com arquivos reais. (Etapas 3-5 —
      `test_qc_core_vs_legacy.py`: QC1-QC5 reproduzem numericamente
      `qc_throughput`/`qc_rh_la`/`qc_rh_la_inc`/`qc_rolling`/
      `qc_replicates` da LEGACY em 10/30/50 kV (inclusive `Mean_RPD`),
      carregando `LEGACY/qc_core.py` só dentro do teste, sem deixar
      `LEGACY/` no `sys.path` nem colidir com o `qc_core` da V2. Etapa 5 —
      distribuição de QF (`run_qc` vs. LEGACY `run_qc(use_count_mode=True,
      strict_missing_data=False)`) bate exatamente em 10 kV/30 kV;
      divergência documentada e isolada em 50 kV (QC4 cai em
      `NOT_APPLICABLE` na V2, mas a LEGACY usa Throughput como substituto
      via modo combinado — simplificação deliberada, não bug).)
- [ ] Executar um benchmark básico.

## 7. Auditoria, i18n e sumário visual

- [x] Implementar suporte bilíngue EN/PT na interface. (`i18n.py`:
      `i18n.load` carrega `src/locales/en.json`/`pt.json`; EN é o padrão
      (`DEFAULT_LANG`) e primeiro em `SUPPORTED_LANGS`; chave ausente na
      tradução cai para EN, nunca `KeyError`. Seletor de idioma na
      sidebar via `qc_avaatech._select_language`, ver DEVELOPMENT.md 1.1
      e 4.4.)
- [x] Traduzir as mensagens de validação. (`qc_io.check_columns` passou a
      receber o dict de strings do i18n já carregado pelo chamador —
      chaves `validation_missing_columns`, `validation_no_depth_column`,
      `validation_depth_fallback`, `validation_no_rep0` — em vez de texto
      hardcoded; decisão de não importar `i18n.py` em `qc_io.py`
      registrada em DEVELOPMENT.md 4.4.)
- [x] Implementar trilha de auditoria em SQLite. (`qc_audit.py`:
      `init_db`, `register_run` e `query_runs` sobre `data/audit.db`
      (tabela `runs`) — uma linha por aba/energia processada com sucesso,
      com operador, arquivo + MD5, commit git, versão do pipeline
      (`PIPELINE_VERSION`), distribuição de QF, avisos e tempo de
      execução.)
- [x] Adicionar toggle de auditoria na sidebar, desligado por padrão.
      (`qc_avaatech.main`: checkbox "Enable audit log" com
      `value=False`; decisão e motivo registrados em DEVELOPMENT.md 4.4.)
- [x] Adicionar aba "Histórico" com filtro por arquivo/operador.
      (`qc_avaatech._render_history_tab`: consulta `qc_audit.query_runs`
      com filtros de texto por arquivo/operador e limite configurável;
      aba só existe quando o toggle de auditoria está ligado.)
- [x] Implementar degradação graciosa da auditoria em ambientes
      hospedados. (`_render_history_tab`/`_render_processing_tab`:
      exceções de `register_run`/`query_runs` — ex. `data/` somente
      leitura ou efêmero — são capturadas e nunca chegam ao usuário como
      erro/traceback; caem no mesmo aviso amigável de "nenhuma execução
      registrada ainda".)
- [x] Adicionar sumário visual por energia. (`qc_avaatech._render_visual_summary`
      /`_render_energy_visual_summary`: cards de métricas, barra de
      distribuição de QF em HTML (`_qf_distribution_bar_html`, colorida
      por QF0–QF3/INDETERMINATE), tabela de ALERT/CRITICAL por módulo
      QC1–QC5 e lista de profundidades com `Review=YES`; usa `st.tabs`
      por energia quando o arquivo tem múltiplas abas.)
- [x] Gerar `summary.txt` bilíngue. (`qc_reports.format_summary_text`
      passou a receber o dict de strings do i18n e monta todo o texto a
      partir das chaves `summary_*` — nenhum texto hardcoded; nome do
      arquivo baixado usa o sufixo traduzido
      `download_summary_file_suffix` (`_summary`/`_resumo`).)
- [x] Adicionar campo "Operador" opcional na sidebar, registrado em cada
      execução de auditoria. (`qc_avaatech.main`: `st.sidebar.text_input`
      repassado a `register_run` como `operador`.)
- [x] Corrigir uso de `use_container_width` para `width="stretch"`.
      (Verificado em 2026-08-07: nenhuma ocorrência de
      `use_container_width` em `src/`; todos os `st.dataframe` já usam
      `width="stretch"`. Item já resolvido no código atual — mantido
      aqui como registro, não como pendência.)

## 8. Próximos itens planejados

- [x] Documentar os 5 módulos QC (QC1–QC5) como referência consultável na
      sidebar: criar `src/docs/` com o conteúdo (um arquivo por módulo ou
      um único texto estruturado) e um `st.expander`/seção na sidebar de
      `qc_avaatech.py` que exiba essa documentação sem sair da interface.
      (`src/docs/QC1_instrument_stability.md`..`QC5_replicates.md` +
      `QF_quality_flags.md`; expander "Protocol Reference" na sidebar via
      `_render_protocol_reference`, com `st.selectbox` por módulo;
      conteúdo sempre em inglês, independente do idioma da interface — só
      o label do expander/seletor é traduzido.)
- [x] Adicionar botão de feedback por email na sidebar (ex. `mailto:`
      com link/botão, ou pequeno formulário) para o operador reportar
      problemas ou sugestões diretamente da interface.
      (`_render_feedback_button`/`_feedback_mailto_url`: `st.link_button`
      com `mailto:` para `andrebelem@id.uff.br` e `ivenancio@id.uff.br`
      via `FEEDBACK_RECIPIENTS`, assunto/corpo pré-preenchidos vindos do
      i18n.)
- [ ] Criar atalho de desktop para Windows e Ubuntu equivalente ao
      `LEGACY/setup_shortcut.py` (detecção automática do SO, ícone
      convertido de `assets/lamplus_logo.png`, atalho apontando para o
      Python do `.venv` quando existir), adaptado para o ponto de entrada
      da V2 (`streamlit run src/qc_avaatech.py`).

## 9. Critérios de conclusão da V2 inicial

- [x] Todos os testes passam.
- [x] Os resultados são reproduzíveis.
- [x] O código é independente de `LEGACY/` em runtime.
- [x] A documentação está atualizada.
- [x] A V2 executa com sucesso nos arquivos reais selecionados.
- [x] Não há regressões críticas conhecidas.

