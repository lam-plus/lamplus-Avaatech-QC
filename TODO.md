# TODO — Análise Crítica do Repositório

**Data da análise:** 2026-06-28
**Escopo:** `qc_core.py`, `qc_avaatech.py`, `i18n.py`, `locales/pt.json`, `locales/en.json`
**Metodologia:** leitura linha a linha + execução do pipeline contra o arquivo real `data/exemplo_dados_consolidados.xlsx` para confirmar hipóteses com dados de produção.

> Nada foi implementado ainda. Este documento é só o levantamento.

---

## 🔴 Achados críticos confirmados empiricamente

Estes dois itens não são hipóteses — foram reproduzidos rodando `run_qc()` sobre o arquivo de exemplo do próprio repositório.

### ✅ C1. QC5 (Réplicas) estava completamente inoperante com dados reais — RESOLVIDO (2026-06-28)

- **Arquivo/linha:** `qc_core.py:171-189` (`qc_replicates`)
- **Problema:** a função casava réplicas por igualdade exata de `DEPTH_COL` entre todas as linhas do `df` bruto. No arquivo de exemplo, **100% das linhas `Rep1`/`Rep2` têm `CompositeDepth (mm)` = NaN** (apenas `Rep0` tem profundidade preenchida). Resultado: `len(subset) < 2` para todas as profundidades, nenhum RPD era calculado, e a coluna `Mean_RPD` final era `NaN` para **todas as 270 linhas** (confirmado: `Mean_RPD.dtype == object`, `count() == 0`).
- **Efeito em cascata:** em `compute_scores` (linha 223-227), `Mean_RPD` NaN era mapeado para `Score_Replica = 100` (nota perfeita) via `np.where(rep0["Mean_RPD"].isna(), 100, ...)`. Ou seja, o módulo QC5 — 15% do peso do QI — estava silenciosamente sempre dando nota máxima, sem nenhum aviso ao usuário. `check_file` não detectava essa situação porque só validava presença de colunas, não a capacidade real de casar réplicas.
- **Investigação:** `CoreDepth` (idêntico a `X Position-mm`) nunca é nulo, inclusive nas réplicas — só `CompositeDepth (mm)` (profundidade já "composta"/ajustada do testemunho) é calculado apenas uma vez, na primeira passada. Agrupar por `(Spectrum, CoreDepth)` reproduz exatamente os trios Rep0+Rep1+Rep2 esperados (12 grupos de tamanho 3 no arquivo de exemplo, batendo com as 24 linhas de profundidade nula encontradas).
- **Correção aplicada:** nova constante `REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]` em `qc_core.py`; `Spectrum`/`CoreDepth` adicionados a `REQUIRED_COLUMNS` (passam a ser obrigatórios e validados por `check_file` automaticamente); `qc_replicates` reescrita para agrupar via `df.groupby(REPLICATE_KEY_COLS)` em vez de iterar sobre `DEPTH_COL`, e o merge final usa a mesma chave composta.
- **Validação:** rodando contra `data/exemplo_dados_consolidados.xlsx`, `Mean_RPD` agora é `float64` com 12 valores reais (0.70%–5.03%) nas posições com réplica, e `Score_Replica` varia de 79.9 a 100 (em vez de ser sempre 100). As 258 posições sem réplica continuam corretamente como `NaN` → fallback de nota 100 (esse fallback em si é uma decisão de design separada, ver item 1.4 abaixo — não foi alterado nesta correção).

### ✅ C2. QI/QF mascaravam dados faltantes como "OK" — RESOLVIDO (2026-06-28)

- **Arquivo/linha:** `qc_core.py` (`compute_scores`, `compute_flags`, `run_qc`)
- **Problema:** se `Throughput`, `Rh-La Area`, `Rh-La-Inc Area` (ou os deltas de rolling) tivessem `NaN` em qualquer linha, `robust_zscore` propagava `NaN`, `score_from_z(NaN)` = `NaN`, e o `QI` ponderado final também virava `NaN`. Em `compute_flags`, todas as comparações (`abs(row[z_col]) > 2`, `row["QI"] < 40`, `row["QI"] < 80`) retornavam `False` quando o operando era `NaN` (semântica padrão do Python/NumPy). Como nenhuma condição "disparava", a linha permanecia com `qf = 0` — uma medição com dado faltante crítico era classificada como "OK".
- **Correção aplicada:**
  - Nova constante `CRITICAL_INPUT_COLS = ["Throughput", "Rh-La Area", "Rh-La-Inc Area"]` (QC1-QC3, sempre obrigatórias) e `QF_INDETERMINATE = 9`, um código de flag **distinto** de 0-3 — nunca confundido com "OK" nem com "ruim" (essas são categorias diferentes: "avaliei e está mau" vs. "não consegui avaliar").
  - `compute_flags` agora calcula `is_indeterminate = rep0[CRITICAL_INPUT_COLS].isna().any(axis=1) | rep0["QI"].isna()` **antes** do loop de regras existente; linhas indeterminadas recebem `QF_INDETERMINATE` incondicionalmente, nunca caem no fallthrough para `qf=0`.
  - Adicionado um **checkbox de política** (`strict_missing_data`, exposto na sidebar de `qc_avaatech.py`, default `True`/restritivo) que controla *apenas* o cálculo do `QI` para essas linhas — nunca a detecção/flag em si, que é sempre ativa:
    - **Restritivo** (`strict_missing_data=True`, padrão): `QI = scores @ weights` — qualquer score ausente invalida o `QI` da linha (fica `NaN`).
    - **Flexível** (`strict_missing_data=False`): `QI` é recalculado só com os módulos disponíveis, redistribuindo os pesos nominais (`QI_WEIGHTS`) entre eles — útil para visualizar uma estimativa "best effort" em vez de um campo vazio, mas a linha continua com `QF=9` em ambos os modos.
- **UI:** `qc_avaatech.py` ganhou a 5ª cor/posição no gráfico QI/QF (`QF_COLORS`/`QF_PLOT_ORDER`, cinza, plotada numa posição visual separada para não distorcer a escala de gravidade 0-3) e uma 5ª métrica no resumo (`metric_qf_indeterminate`). `locales/pt.json` e `locales/en.json` ganharam as chaves `strict_missing_label`, `strict_missing_help`, `metric_qf_indeterminate`, e `plot_qf_labels` passou a ter 5 entradas.
- **Validação:** testado com `data/exemplo_dados_consolidados.xlsx` (sem regressão — distribuição de QF idêntica à anterior, pois o arquivo não tem NaN em QC1-QC3) e com NaN sintético injetado em `Throughput` de 5 linhas: em ambos os modos as 5 linhas recebem `QF=9` (nunca `QF=0`); no modo restritivo `QI=NaN`, no flexível `QI` fica entre ~85-96 (recalculado com os 5 módulos restantes). App Streamlit testado de ponta a ponta (`streamlit run`, HTTP 200, sem erro de import/runtime).

---

## 1. Bugs e comportamentos inesperados

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 1.1 | `qc_core.py:75-81` (`calculate_rpd`) | Se `values.mean()` for 0 (ex.: valores positivos e negativos se cancelando, ou todos zero), a divisão produz `inf`, não `NaN`. Esse `inf` se propaga para `Mean_RPD` e gerou de fato um `RuntimeWarning: invalid value encountered in maximum` ao rodar o pipeline no arquivo de exemplo (em `compute_scores:226`, `np.maximum(0, 100 - Mean_RPD*4)`). | Tratar explicitamente `mean == 0` retornando `NaN` (ou um valor sentinela), e silenciar/registrar o warning com contexto em vez de deixá-lo vazar para o console do Streamlit. |
| 1.2 | ~~`qc_core.py` (`qc_pca`)~~ | ✅ **Resolvido em 2026-06-28** junto com o item 2.2: `qc_pca` agora valida `len(pca_elements) >= MIN_PCA_ELEMENTS` e `len(rep0) >= MIN_PCA_ROWS` antes de chamar `PCA`; se insuficiente, pula QC6 (PC1/PC2/Mahalanobis ficam NaN) em vez de lançar `ValueError`. | — |
| 1.3 | ~~`qc_core.py` (`qc_pca`)~~ | ✅ **Resolvido em 2026-06-28**: `np.linalg.inv(cov)` trocado por `np.linalg.pinv(cov)`. | — |
| 1.4 | `qc_core.py:223-227` (`compute_scores`) | Réplica ausente (`Mean_RPD` NaN) é tratada como nota 100 (perfeita) — ver achado **C1**. Isso é uma escolha de design questionável mesmo fora do bug de casamento de profundidade: penalizar pela ausência do dado seria mais conservador para um pipeline de QC. | Discutir com o time se a ausência de réplica deveria reduzir o `Score_Replica` (ex.: nota neutra ~60-70) em vez de nota máxima. |
| 1.5 | `qc_core.py:252-275` (`compute_flags`) | Critérios de flag são avaliados com `max(qf, ...)`, então um único z-score pontualmente alto (entre 2 e 3) já força `QF=2` mesmo que o `QI` agregado esteja alto (>80). Isso é provavelmente intencional (defesa em profundidade), mas não está documentado, e pode confundir usuários que veem `QI` alto com `QF=2`. | Documentar essa regra no docstring de `compute_flags` e/ou expor na UI uma explicação de "por que esta linha foi marcada" (qual critério disparou). |

---

## 2. Gaps no pipeline QC (edge cases não tratados)

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 2.1 | `qc_core.py:292` (`run_qc`) | Se `run_qc()` for chamado sem passar primeiro por `check_file()` (uso direto do módulo como biblioteca, fora do Streamlit) e não houver nenhuma linha `Rep0`, `rep0` fica vazio e os módulos seguintes falham com erros pouco informativos. | Adicionar uma guarda no início de `run_qc` que valida `len(rep0) > 0` e levanta uma exceção clara. |
| 2.2 | ~~`qc_core.py` (`check_file`, `qc_pca`, `compute_scores`)~~ | ✅ **Resolvido em 2026-06-28.** Decisão tomada: em vez de `check_file` bloquear com erro (sugestão original), o pipeline **degrada graciosamente** — consistente com o fallback que QC5 (réplicas) já usava antes desta correção. Novas constantes `MIN_PCA_ELEMENTS=2`/`MIN_PCA_ROWS=3`; `qc_pca` pula QC6 com PC1/PC2/Mahalanobis=NaN quando insuficiente; `compute_scores` aplica `Score_PCA=100` (neutro, mesmo padrão de `Score_Replica`) quando `Mahalanobis` está todo nulo; `check_file` emite **warnings** bilíngues dedicados (`pca_unavailable`, `pca_too_few_rows`) cobrindo zero/poucos elementos e poucas linhas Rep0; `qc_avaatech.py` mostra `st.info` na aba PCA em vez de um gráfico vazio sem explicação. Validado com arquivo real (sem regressão) + 3 cenários sintéticos (0 elementos, 1 elemento, 2 linhas Rep0) — nenhum gera exceção, QI permanece computável em todos. | — |
| 2.3 | `qc_core.py:160-168` (`qc_rolling`) | `ROLLING_WINDOW = 5` é fixo e não escalado pela densidade de amostragem do core. Um core amostrado a cada 1mm vs. a cada 10mm terá uma janela de suavização com significado físico muito diferente. | Tornar a janela configurável na UI, ou derivá-la do espaçamento médio de `DEPTH_COL`. |
| 2.4 | `qc_core.py:229-230` (`compute_scores`) | Percentis 95/99 de Mahalanobis calculados sobre o próprio dataset, sem mínimo de amostras. Com poucos pontos (ex.: < 20), os percentis 95/99 são estatisticamente pouco confiáveis (a posição exata do percentil quase não tem amostras de suporte). | Adicionar um aviso quando `len(rep0)` for pequeno (ex.: < 30), alertando que os limiares de Mahalanobis podem não ser robustos. |
| 2.5 | `qc_core.py` (geral) | Nenhuma checagem de plausibilidade física dos valores (ex.: `Throughput`, áreas de contagem negativas, que são fisicamente impossíveis para XRF). | Adicionar checagem opcional de range plausível por variável em `check_file` (warning, não erro). |
| 2.6 | `qc_core.py:118-122` (`check_file`) | `n_zero` conta linhas com `Throughput` zero/nulo em **todo o `df`**, não apenas em `Rep0` (que é o subconjunto efetivamente usado pelo pipeline). A mensagem não esclarece o escopo, podendo confundir o usuário sobre se o problema afeta os dados realmente processados. | Restringir a contagem ao subconjunto `Rep0`, ou esclarecer no texto da mensagem que a contagem é sobre todas as réplicas. |

---

## 3. Robustez (dados faltantes, colunas inesperadas, arquivos malformados)

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 3.1 | `qc_avaatech.py:147` | `pd.read_excel(uploaded)` não especifica `sheet_name`; se o workbook do Avaatech tiver múltiplas planilhas, só a primeira é lida silenciosamente, sem aviso. | Detectar múltiplas sheets e, se houver mais de uma, perguntar ao usuário qual usar (ou avisar qual foi escolhida). |
| 3.2 | `qc_core.py:88-132` (`check_file`) | Não há validação de **dtype** das colunas críticas (`DEPTH_COL`, `Throughput`, etc.). Se o Excel trouxer essas colunas como texto (comum quando há separador decimal `,` em locale PT-BR, ou células mistas), o pipeline falha mais adiante com erros do pandas/sklearn pouco relacionados à causa raiz. | Adicionar verificação de tipo numérico para as colunas em `REQUIRED_COLUMNS` + `ELEMENTS_PCA`/`ELEMENTS_REPLICATES`, com erro claro indicando qual coluna está com tipo inesperado. |
| 3.3 | `qc_core.py:101-103` (`check_file`) | A comparação `"Rep0" not in df[REPLICATE_COL].values` é sensível a espaços/maiúsculas (ex.: `"Rep0 "` ou `"REP0"` não seria reconhecido, gerando erro confuso de "Rep0 não encontrado" mesmo que o dado exista). | Normalizar a coluna (`.str.strip()`) antes da comparação, ou comparar de forma case-insensitive com aviso se normalização foi necessária. |
| 3.4 | `qc_avaatech.py:139` | Upload aceita apenas `.xlsx` (`type=["xlsx"]`). Scanners Avaatech/usuários podem exportar `.xls` ou `.csv`. | Avaliar suporte a `.xls`/`.csv` ou ao menos deixar a limitação explícita na mensagem de upload. |
| 3.5 | `qc_core.py` (geral) | Nenhum limite de tamanho/linhas é validado antes de rodar o pipeline. Arquivos muito grandes podem travar a UI (relacionado à seção de performance, item 5.1/5.2). | Adicionar um aviso ou limite configurável de linhas antes de rodar QC completo. |

---

## 4. Inconsistências entre `qc_core.py` e o frontend

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 4.1 | ~~`qc_core.py` (`qc_rolling`/`compute_scores`/`compute_flags`)~~ | ✅ **Resolvido em 2026-06-28.** Decisão tomada: opção (a) — combinar as três variáveis, e não (b) simplificar a documentação para refletir o comportamento legado. **Justificativa física:** Throughput (taxa de contagem total do detector) e Rh-Lα/Rh-Lα-Inc (espalhamento coerente/incoerente da linha do ânodo de Ródio do tubo) são indicadores instrumentais — não composição química — e tendem a reagir **simultaneamente** a um mesmo problema físico de medição (rachadura, bolha de ar, transição seco/úmido, deriva do detector): basta uma das três disparar para indicar problema. **Implementação:** nova constante `ROLLING_VARS`; `compute_scores(rep0, combine_rolling_vars=True)` (padrão) calcula `rep0["Rolling_z"] = max(\|Throughput_delta_z\|, \|Rh-La Area_delta_z\|, \|Rh-La-Inc Area_delta_z\|)` — o máximo, não a média, porque um problema físico real tende a aparecer com força em pelo menos uma das três, e usar a média diluiria esse sinal. `compute_flags` passou a usar `rep0["Rolling_z"]` em vez do literal `"Rh-La-Inc Area_delta_z"`. Quando `combine_rolling_vars=False`, reproduz exatamente o comportamento legado (`Rolling_z = \|Rh-La-Inc Area_delta_z\|`) — exposto como checkbox na sidebar (`qc_avaatech.py`, default ativado). | — |
| — | *(discussão de design)* | Antes de decidir a implementação, foi avaliada e descartada a ideia de 3 checkboxes independentes (um por variável). Motivo: (1) combinações sem resposta clara (ex. as três desmarcadas ao mesmo tempo); (2) é uma decisão **metodológica** sobre a fórmula do QC4 — deveria ser a mesma para todos os usuários/sessões, não um toggle ad-hoc por clique, diferente do checkbox de C2 (que é genuinamente uma escolha de cautela por sessão); (3) risco de um usuário desmarcar sem querer a única variável que sustentava o score, zerando o módulo silenciosamente. | — |
| 4.2 | `qc_core.py:300` / `qc_avaatech.py:169` | `run_qc()` retorna `pca_elements` (quais colunas foram efetivamente usadas na PCA), mas o frontend recebe essa lista e nunca a exibe — o usuário não sabe quais elementos entraram na PCA nem quando algum foi descartado por ausência de coluna. | Mostrar `pca_elements` na aba PCA (ex.: caption listando os elementos usados), aproveitando o dado que já existe. |
| 4.3 | `locales/pt.json:3` e `locales/en.json:3` | A versão `"v2.1"` está hardcoded e duplicada dentro do `app_title` em **dois** arquivos JSON. Bump de versão exige editar os dois arquivos de tradução em sincronia — fonte de divergência. | Extrair a versão para uma constante única (ex. `__version__` em `qc_core.py` ou um `VERSION` em `i18n.py`) e interpolar no template (`"app_title": "LAM+ Core QC v{version}"`). |
| 4.4 | `qc_avaatech.py:149,171` | `T["read_error"].format(error=e)` e `T["qc_error"].format(error=e)` traduzem apenas o prefixo da mensagem; o texto da exceção (`str(e)`) vem das bibliotecas (pandas/sklearn) sempre em inglês, mesmo com `lang="pt"` selecionado. Resultado: mensagens de erro mistas PT/EN. | Mapear as exceções mais comuns (arquivo corrompido, coluna ausente, etc.) para mensagens próprias e traduzidas em vez de expor `str(e)` cru; manter o texto técnico original apenas em um expander/"detalhes técnicos" opcional. |
| 4.5 | `qc_avaatech.py:127` vs. `i18n.py:18` | A lista de idiomas suportados existe em dois lugares: `SUPPORTED_LANGS` em `i18n.py` e `LANG_OPTIONS` em `qc_avaatech.py`. Adicionar um novo idioma exige tocar nos dois arquivos (+ criar o JSON), sem nenhuma validação cruzada. | Gerar `LANG_OPTIONS` dinamicamente a partir de `i18n.SUPPORTED_LANGS` (+ um nome de exibição por idioma, também vindo do JSON, ex. `"language_name": "Português"`), eliminando a duplicação. |
| 4.6 | `qc_avaatech.py:211` | `st.dataframe(rep0, ...)` exibe os nomes de coluna originais do Avaatech (`"CompositeDepth (mm)"`, `"Rh-La Area"`, etc.), que não são traduzidos — inconsistente com o resto da UI, que está integralmente localizada. | Ciente de que é provavelmente intencional (nomes técnicos de instrumento), mas vale documentar essa exceção deliberada em vez de deixar implícita. |

---

## 5. Melhorias de performance

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 5.1 | `qc_core.py:252-275` (`compute_flags`) | Loop Python com `rep0.iterrows()` — reconstrói uma `Series` por linha, O(n) em Python puro em vez de vetorizado. Para cores longos (milhares de linhas), é o principal candidato a lentidão. | Vetorizar com máscaras booleanas (`(rep0[z_cols].abs() > 2).any(axis=1)`, etc.) e combinar com `np.select`/`np.where` em vez de loop. |
| 5.2 | ~~`qc_core.py:171-189` (`qc_replicates`)~~ | ✅ **Resolvido em 2026-06-28** como parte da correção do achado **C1**: a função agora usa `df.groupby(REPLICATE_KEY_COLS)` em vez de iterar e refiltrar o `df` a cada profundidade. | — |
| 5.3 | `qc_core.py:206` (`qc_pca`) | `[mahalanobis(row, center, inv_cov) for row in pcs]` chama a função do scipy linha a linha em Python puro. | Vetorizar via álgebra matricial: `d = np.sqrt(np.einsum('ij,jk,ik->i', diff, inv_cov, diff))` onde `diff = pcs - center`. |
| 5.4 | `qc_avaatech.py:159,169` (`check_file`/`run_qc` no corpo principal do script) | Streamlit reexecuta o script inteiro a cada interação (ex.: trocar o idioma no seletor da sidebar). Isso recalcula `check_file` e `run_qc` do zero mesmo quando o arquivo enviado não mudou — desperdício de CPU para arquivos grandes. | Envolver a leitura do Excel e `run_qc()` com `@st.cache_data` (chave = hash do arquivo enviado), recalculando só quando o upload mudar, não quando o idioma mudar. |
| 5.5 | `qc_avaatech.py:27-103` (funções `plot_*`) | Figuras matplotlib são recriadas do zero a cada rerun do Streamlit, mesmo sem mudança nos dados. | Combinar com o cache do item 5.4: já que `rep0` fica estável entre reruns de troca de idioma, as figuras (exceto textos/títulos) poderiam ser cacheadas por dados + idioma. |

---

## 6. Qualidade do código (legibilidade, organização, docstrings)

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 6.1 | `qc_core.py` (todo o arquivo) | Nenhuma função tem type hints, apesar de o código ser uma biblioteca importável (`from qc_core import check_file, run_qc`, conforme o próprio docstring do módulo sugere). | Adicionar type hints (`pd.DataFrame`, `tuple[list[str], list[str]]`, etc.) para melhorar suporte de IDE e detecção precoce de erros. |
| 6.2 | `qc_core.py:236-243, 252-275` (`compute_scores`, `compute_flags`) | Números mágicos espalhados inline: pesos `0.25/0.15/0.20/0.20/0.15/0.05`, limiares `2`, `3`, `40`, `80`, percentis `95`/`99`. Só `ROLLING_WINDOW` é uma constante nomeada no topo do arquivo; o resto não. | Promover esses valores a constantes nomeadas no bloco `CONFIGURAÇÕES` (ex. `QI_WEIGHTS`, `Z_THRESHOLD_ATTENTION = 2`, `Z_THRESHOLD_REJECT = 3`, `QI_THRESHOLD_OK = 80`, `QI_THRESHOLD_REJECT = 40`), facilitando ajuste e leitura. |
| 6.3 | `qc_core.py:253` (docstring de `compute_flags`) e `locales/*.json` (`plot_qf_labels`) | O mapeamento QF 0-3 → significado existe em dois lugares com fontes de verdade diferentes: comentário no docstring (`"0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado"`) e arrays de tradução. Se alguém alterar a semântica de um flag, é fácil esquecer de atualizar um dos dois lugares. | Centralizar o mapeamento QF→significado em uma constante Python (ex. `QF_LABELS = {0: "qf_ok", 1: "qf_attention", ...}`) referenciada tanto no código quanto nas chaves de tradução. |
| 6.4 | repositório (geral) | Não há nenhum diretório `tests/` nem suíte automatizada — toda validação até aqui (incluindo os achados **C1**/**C2** deste documento) foi manual, via execução ad-hoc. | Criar testes unitários para `qc_core.py` cobrindo: dados com NaN em colunas críticas, ausência total de colunas PCA, replicas não casáveis por profundidade, RPD com média zero, dataset com 1 linha. |
| 6.5 | `requirements.txt` | Dependências sem pin de versão (`pandas`, `numpy`, etc., sem `==` ou `>=`). Isso é um risco de reprodutibilidade — uma atualização de `scikit-learn` ou `pandas` pode mudar comportamento (ex. APIs de `PCA`, `mahalanobis`) sem aviso. | Fixar ao menos versões mínimas testadas (`pandas>=2.0,<3`, etc.), e considerar um `requirements-lock.txt` ou `pyproject.toml` com versões exatas para reprodutibilidade total. |
| 6.6 | `qc_avaatech.py` (corpo principal, linhas 121-219) | Lógica de interface roda inteiramente no nível de módulo (padrão comum em Streamlit, mas mistura definição de funções com execução imperativa no mesmo arquivo, sem nenhuma função `main()`). | Não é incomum em apps Streamlit pequenos, mas para um app que já cresceu (i18n, múltiplos plots, export) vale considerar encapsular o corpo em uma função `main()` chamada por `if __name__ == "__main__":`, facilitando testes futuros de fluxo. |

---

## 7. Gaps na cobertura bilíngue

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 7.1 | `qc_avaatech.py:149,171` (já citado em 4.4) | Texto de exceções de bibliotecas externas (pandas/sklearn) nunca é traduzido, mesmo quando `lang="en"`/`"pt"` é selecionado — é a maior lacuna bilíngue real do app hoje. | Ver sugestão do item 4.4 (mapear exceções comuns para mensagens próprias e traduzidas). |
| 7.2 | `qc_avaatech.py:206,217` | Nome do arquivo de saída (`file_name="LAM_CoreQC_Output.xlsx"`) e nome da aba do Excel (`sheet_name="LAM_CoreQC"`, em `qc_avaatech.py:113`) são hardcoded em código, fora do sistema de i18n — não é exatamente "string não traduzida visível ao usuário na UI", mas é uma string fixa em inglês mesmo com PT selecionado. | Avaliar se vale localizar o nome do arquivo exportado (ex. `LAM_CoreQC_Saida.xlsx` em PT) ou documentar que nomes de arquivo são intencionalmente mantidos em um padrão único. |
| 7.3 | `i18n.py` (todo o arquivo) | Não há nenhuma validação de que `locales/pt.json` e `locales/en.json` possuem exatamente o mesmo conjunto de chaves. Hoje eles estão sincronizados, mas nada impede uma futura edição de adicionar uma chave em um idioma e esquecer o outro — o erro só apareceria em runtime como `KeyError`, possivelmente em produção. | Adicionar uma checagem (idealmente em teste automatizado, ver item 6.4) que compara `set(TEXTS["pt"].keys()) == set(TEXTS["en"].keys())` e o mesmo para `CHECK_MESSAGES`, falhando o build/CI se divergirem. |
| 7.4 | `qc_avaatech.py:127-132` | O rótulo do seletor de idioma (`"Português"`, `"English"`) está hardcoded no código Python, não no JSON de locale — ironicamente, o próprio seletor de idioma não vem do sistema de i18n. | Mover os nomes de exibição dos idiomas para dentro de cada `locales/<lang>.json` (ex. chave `"language_name"`), permitindo que a lista de idiomas seja construída dinamicamente (ver também item 4.5). |

---

## 8. Funcionalidades planejadas (ainda não implementadas)

Itens combinados com o usuário mas que ainda não foram codificados — registrados aqui para não se perderem entre sessões.

### 8.1 Exportação de relatório em PDF por testemunho

Hoje a única saída além da tela é o `.xlsx` (`to_excel_bytes`, `qc_avaatech.py`), com todas as linhas `Rep0` misturadas, sem distinção por testemunho. Plano combinado em 2026-06-28 (não implementado):

- **Granularidade:** agrupar por **testemunho**, não por valor exato de `Spectrum`. `Spectrum` mistura nome do testemunho + seção (ex. `"lontra-T01"`..`"lontra-T06"` são 6 seções de **um** testemunho "lontra", com profundidades compostas contínuas) — confirmado no arquivo de exemplo. Precisa de uma função (`qc_core.py`) que extraia o nome do testemunho a partir do prefixo de `Spectrum` (ex. regex `^(.+?)-T\d+$`, com fallback para o próprio `Spectrum` se não casar o padrão) e agrupe as seções antes de gerar o PDF.
- **Biblioteca:** `matplotlib.backends.backend_pdf.PdfPages` — zero dependência nova (matplotlib já está no `requirements.txt`), reaproveita os `plot_*()` já existentes como páginas do PDF.
- **Conteúdo do PDF:** capa (logo, nome do testemunho, profundidade composta, nº de medições, data/hora, modos de QC usados — `strict_missing_data`/`combine_rolling_vars`, para reprodutibilidade) + uma página por gráfico de diagnóstico + uma página de tabela só com linhas `QF` ∈ {2, 3, ND}.
- **UI:** seletor de testemunho + opção "Todos" (gera `.zip` com um PDF por testemunho), botão de download ao lado do `.xlsx`, geração só no clique.
- Módulo novo sugerido: `report_pdf.py`, separado de `qc_core.py` (que deve continuar sem dependência de relatório/UI) e de `qc_avaatech.py`.

### 8.2 Campo "Operador" no formulário da UI

Pedido em 2026-06-28: adicionar um campo de texto na interface (`qc_avaatech.py`, ex. na sidebar, próximo aos checkboxes de QC) para o usuário informar o **nome do operador** responsável pela análise. Esse valor deve aparecer na capa do relatório PDF (item 8.1) para rastreabilidade — quem rodou o QC e gerou aquele relatório específico.

### 8.3 Campo "Comentários/Observações" no formulário da UI

Pedido em 2026-06-28: adicionar um campo de texto livre (ex. `st.text_area`) onde o operador possa registrar observações sobre a sessão de QC (condições da medição, ressalvas, contexto da amostra, etc.). O conteúdo desse campo também deve ser incluído no relatório PDF (item 8.1), provavelmente na página de capa ou numa página dedicada de observações.

Ambos os campos (8.2/8.3) são só para compor o PDF — não alteram o cálculo do QC em si, e precisam de chaves novas em `locales/pt.json`/`en.json` (label dos campos, placeholder, texto do cabeçalho no PDF).

---

## Resumo de prioridade sugerida

1. ~~**C1**~~ e ~~**C2**~~ ✅ ambos resolvidos (2026-06-28) — os dois riscos de integridade científica dos resultados (réplicas não casadas e dado faltante mascarado como "OK") estão corrigidos e validados contra dados reais.
2. ~~**2.2** / **1.2** / **1.3**~~ ✅ resolvidos (2026-06-28) — QC6 (PCA) degrada graciosamente (score neutro + warning bilíngue) em vez de travar o pipeline quando faltam elementos/linhas; matriz de covariância usa `pinv`.
3. ~~**4.1**~~ ✅ resolvido (2026-06-28) — QC4 agora combina as três variáveis por padrão (máximo dos `\|delta_z\|`), com toggle para o comportamento legado; README atualizado para refletir o comportamento real.
4. Demais itens são robustez/performance/qualidade incrementais, sem risco de resultado incorreto.
