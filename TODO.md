# TODO — LAM+ Core QC V2

Este arquivo contém somente o trabalho da V2 simplificada. O histórico e as
pendências da versão anterior estão em `LEGACY/TODO.md`.

## 1. Definições iniciais

- [ ] Confirmar o escopo da V2.
- [ ] Confirmar os módulos QC1–QC5.
- [ ] Confirmar as regras de QF por contagem.
- [ ] Confirmar o tratamento de QF indeterminado.
- [ ] Confirmar o formato de saída.
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

- [ ] Exportar resultados em Excel.
- [ ] Preservar as colunas originais.
- [ ] Adicionar colunas de QC.
- [ ] Adicionar uma aba de intervalos sinalizados.
- [ ] Gerar um resumo simples.

## 5. Interface mínima

- [ ] Implementar upload de arquivo.
- [ ] Implementar seleção do arquivo de entrada.
- [ ] Executar o processamento.
- [ ] Exibir um resumo dos resultados.
- [ ] Disponibilizar o download.
- [ ] Manter opções avançadas fora da interface inicial.

## 6. Testes

- [ ] Criar testes unitários.
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

## 7. Critérios de conclusão da V2 inicial

- [ ] Todos os testes passam.
- [ ] Os resultados são reproduzíveis.
- [ ] O código é independente de `LEGACY/` em runtime.
- [ ] A documentação está atualizada.
- [ ] A V2 executa com sucesso nos arquivos reais selecionados.
- [ ] Não há regressões críticas conhecidas.

