# TODO — Análise Crítica do Repositório

**Data da análise:** 2026-06-28
**Escopo:** `qc_core.py`, `qc_avaatech.py`, `report_pdf.py`, `i18n.py`, `locales/pt.json`, `locales/en.json`
**Metodologia:** leitura linha a linha + execução do pipeline contra o arquivo real `data/exemplo_dados_consolidados.xlsx` para confirmar hipóteses com dados de produção.

> Nada foi implementado ainda. Este documento é só o levantamento.

---

## 🔴 Achados críticos confirmados empiricamente

Estes dois itens não são hipóteses — foram reproduzidos rodando `run_qc()` sobre o arquivo de exemplo do próprio repositório.

### ✅ C1. QC5 (Réplicas) estava completamente inoperante com dados reais — RESOLVIDO (2026-06-28)

- **Arquivo/linha (na época do achado — ver `qc_core.py:246` para a localização atual após refatorações posteriores):** `qc_replicates`
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
| 1.1 | ~~`qc_core.py` (`calculate_rpd`)~~ | ✅ **Resolvido em 2026-07-28** (incorporado do protocolo v4.2 do Igor — ver `DEVELOPMENT.md`, seção "Protocolo v4.2"). `mean == 0` agora retorna `NaN` explicitamente antes da divisão, em vez de propagar `inf` para `Mean_RPD`. Validado: `calculate_rpd([10, -10])` e `calculate_rpd([0, 0, 0])` retornam `NaN`; pipeline completo rodado contra `data/exemplo_dados_consolidados.xlsx` com `-W error::RuntimeWarning` sem levantar warning, distribuição de QF idêntica à anterior (`{0:208, 2:45, 3:17}`) — sem regressão. | — |
| 1.2 | ~~`qc_core.py` (`qc_pca`)~~ | ✅ **Resolvido em 2026-06-28** junto com o item 2.2: `qc_pca` agora valida `len(pca_elements) >= MIN_PCA_ELEMENTS` e `len(rep0) >= MIN_PCA_ROWS` antes de chamar `PCA`; se insuficiente, pula QC6 (PC1/PC2/Mahalanobis ficam NaN) em vez de lançar `ValueError`. | — |
| 1.3 | ~~`qc_core.py` (`qc_pca`)~~ | ✅ **Resolvido em 2026-06-28**: `np.linalg.inv(cov)` trocado por `np.linalg.pinv(cov)`. | — |
| 1.4 | `qc_core.py:350-354` (`compute_scores`) | Réplica ausente (`Mean_RPD` NaN) é tratada como nota 100 (perfeita) — ver achado **C1**. Isso é uma escolha de design questionável mesmo fora do bug de casamento de profundidade: penalizar pela ausência do dado seria mais conservador para um pipeline de QC. | Discutir com o time se a ausência de réplica deveria reduzir o `Score_Replica` (ex.: nota neutra ~60-70) em vez de nota máxima. |
| 1.5 | ~~`qc_core.py` (`compute_flags`)~~ | ✅ **Resolvido em 2026-06-28** (ver seção 8.1, "Progresso adicional"). Critérios de flag são avaliados com `max(qf, ...)`, então um único z-score pontualmente alto (entre 2 e 3) já força `QF=2` mesmo que o `QI` agregado esteja alto (≥80) — isso continua intencional (defesa em profundidade), mas agora é detectado e explicado: `is_pointwise_flag(rep0)` identifica essas linhas, e `add_pointwise_flag_notes` expõe a explicação traduzida (coluna `Pointwise_Flag_Note`, visível na tabela da UI e no `.xlsx`), usando as causas já registradas em `QF_Causes`. `report_pdf.py` também marca esses casos no PDF (ícone "⚠" + nota de rodapé). | — |

---

## 2. Gaps no pipeline QC (edge cases não tratados)

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 2.1 | `qc_core.py:509` (`run_qc`) | Se `run_qc()` for chamado sem passar primeiro por `check_file()` (uso direto do módulo como biblioteca, fora do Streamlit) e não houver nenhuma linha `Rep0`, `rep0` fica vazio e os módulos seguintes falham com erros pouco informativos. | Adicionar uma guarda no início de `run_qc` que valida `len(rep0) > 0` e levanta uma exceção clara. |
| 2.2 | ~~`qc_core.py` (`check_file`, `qc_pca`, `compute_scores`)~~ | ✅ **Resolvido em 2026-06-28.** Decisão tomada: em vez de `check_file` bloquear com erro (sugestão original), o pipeline **degrada graciosamente** — consistente com o fallback que QC5 (réplicas) já usava antes desta correção. Novas constantes `MIN_PCA_ELEMENTS=2`/`MIN_PCA_ROWS=3`; `qc_pca` pula QC6 com PC1/PC2/Mahalanobis=NaN quando insuficiente; `compute_scores` aplica `Score_PCA=100` (neutro, mesmo padrão de `Score_Replica`) quando `Mahalanobis` está todo nulo; `check_file` emite **warnings** bilíngues dedicados (`pca_unavailable`, `pca_too_few_rows`) cobrindo zero/poucos elementos e poucas linhas Rep0; `qc_avaatech.py` mostra `st.info` na aba PCA em vez de um gráfico vazio sem explicação. Validado com arquivo real (sem regressão) + 3 cenários sintéticos (0 elementos, 1 elemento, 2 linhas Rep0) — nenhum gera exceção, QI permanece computável em todos. | — |
| 2.3 | `qc_core.py:235-243` (`qc_rolling`) | `ROLLING_WINDOW = 5` é fixo e não escalado pela densidade de amostragem do core. Um core amostrado a cada 1mm vs. a cada 10mm terá uma janela de suavização com significado físico muito diferente. | Tornar a janela configurável na UI, ou derivá-la do espaçamento médio de `DEPTH_COL`. |
| 2.4 | `qc_core.py:356-360` (`compute_scores`) | Percentis 95/99 de Mahalanobis calculados sobre o próprio dataset, sem mínimo de amostras. Com poucos pontos (ex.: < 20), os percentis 95/99 são estatisticamente pouco confiáveis (a posição exata do percentil quase não tem amostras de suporte). | Adicionar um aviso quando `len(rep0)` for pequeno (ex.: < 30), alertando que os limiares de Mahalanobis podem não ser robustos. |
| 2.5 | `qc_core.py` (geral) | Nenhuma checagem de plausibilidade física dos valores (ex.: `Throughput`, áreas de contagem negativas, que são fisicamente impossíveis para XRF). | Adicionar checagem opcional de range plausível por variável em `check_file` (warning, não erro). |
| 2.6 | `qc_core.py:196-199` (`check_file`) | `n_zero` conta linhas com `Throughput` zero/nulo em **todo o `df`**, não apenas em `Rep0` (que é o subconjunto efetivamente usado pelo pipeline). A mensagem não esclarece o escopo, podendo confundir o usuário sobre se o problema afeta os dados realmente processados. | Restringir a contagem ao subconjunto `Rep0`, ou esclarecer no texto da mensagem que a contagem é sobre todas as réplicas. |

---

## 3. Robustez (dados faltantes, colunas inesperadas, arquivos malformados)

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 3.1 | `qc_avaatech.py:190` | `pd.read_excel(uploaded)` não especifica `sheet_name`; se o workbook do Avaatech tiver múltiplas planilhas, só a primeira é lida silenciosamente, sem aviso. | Detectar múltiplas sheets e, se houver mais de uma, perguntar ao usuário qual usar (ou avisar qual foi escolhida). |
| 3.2 | `qc_core.py:156-207` (`check_file`) | Não há validação de **dtype** das colunas críticas (`DEPTH_COL`, `Throughput`, etc.). Se o Excel trouxer essas colunas como texto (comum quando há separador decimal `,` em locale PT-BR, ou células mistas), o pipeline falha mais adiante com erros do pandas/sklearn pouco relacionados à causa raiz. | Adicionar verificação de tipo numérico para as colunas em `REQUIRED_COLUMNS` + `ELEMENTS_PCA`/`ELEMENTS_REPLICATES`, com erro claro indicando qual coluna está com tipo inesperado. |
| 3.3 | `qc_core.py:177-179` (`check_file`) | A comparação `"Rep0" not in df[REPLICATE_COL].values` é sensível a espaços/maiúsculas (ex.: `"Rep0 "` ou `"REP0"` não seria reconhecido, gerando erro confuso de "Rep0 não encontrado" mesmo que o dado exista). | Normalizar a coluna (`.str.strip()`) antes da comparação, ou comparar de forma case-insensitive com aviso se normalização foi necessária. |
| 3.4 | `qc_avaatech.py:182` | Upload aceita apenas `.xlsx` (`type=["xlsx"]`). Scanners Avaatech/usuários podem exportar `.xls` ou `.csv`. | Avaliar suporte a `.xls`/`.csv` ou ao menos deixar a limitação explícita na mensagem de upload. |
| 3.5 | `qc_core.py` (geral) | Nenhum limite de tamanho/linhas é validado antes de rodar o pipeline. Arquivos muito grandes podem travar a UI (relacionado à seção de performance, item 5.1/5.2). | Adicionar um aviso ou limite configurável de linhas antes de rodar QC completo. |

---

## 4. Inconsistências entre `qc_core.py` e o frontend

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 4.1 | ~~`qc_core.py` (`qc_rolling`/`compute_scores`/`compute_flags`)~~ | ✅ **Resolvido em 2026-06-28** (revisado no mesmo dia — ver nota abaixo). **Implementação:** nova constante `ROLLING_VARS`; `compute_scores(rep0, combine_rolling_vars=False)` calcula `rep0["Rolling_z"] = max(\|Throughput_delta_z\|, \|Rh-La Area_delta_z\|, \|Rh-La-Inc Area_delta_z\|)` quando `combine_rolling_vars=True` — o máximo, não a média, porque um problema físico real tende a aparecer com força em pelo menos uma das três, e usar a média diluiria esse sinal. `compute_flags` passou a usar `rep0["Rolling_z"]` em vez do literal `"Rh-La-Inc Area_delta_z"`. **Decisão final de default (revisada em 2026-06-28, depois da primeira implementação ter combinado por padrão):** `combine_rolling_vars=False` é o **default** — QC4 considera só `Rh-La-Inc Area` por padrão, porque é o dado espectral real medido naquele ponto; Throughput e Rh-Lα são parâmetros instrumentais secundários (não o sinal espectral em si). Combinar as três é **opt-in** via checkbox na sidebar (default desmarcado), para quem quiser sensibilidade ampliada a problemas físicos de medição às custas de também reagir a deriva instrumental não necessariamente refletida no dado espectral. README atualizado para documentar esse default e a motivação. | — |
| — | *(discussão de design)* | Antes de decidir a implementação, foi avaliada e descartada a ideia de 3 checkboxes independentes (um por variável). Motivo: (1) combinações sem resposta clara (ex. as três desmarcadas ao mesmo tempo); (2) é uma decisão **metodológica** sobre a fórmula do QC4 — deveria ser a mesma para todos os usuários/sessões, não um toggle ad-hoc por clique, diferente do checkbox de C2 (que é genuinamente uma escolha de cautela por sessão); (3) risco de um usuário desmarcar sem querer a única variável que sustentava o score, zerando o módulo silenciosamente. | — |
| 4.2 | `qc_core.py:543` / `qc_avaatech.py:212` | `run_qc()` retorna `pca_elements` (quais colunas foram efetivamente usadas na PCA), mas o frontend recebe essa lista e nunca a exibe — o usuário não sabe quais elementos entraram na PCA nem quando algum foi descartado por ausência de coluna. | Mostrar `pca_elements` na aba PCA (ex.: caption listando os elementos usados), aproveitando o dado que já existe. |
| 4.3 | `locales/pt.json:3` e `locales/en.json:3` | A versão `"v2.1"` está hardcoded e duplicada dentro do `app_title` em **dois** arquivos JSON. Bump de versão exige editar os dois arquivos de tradução em sincronia — fonte de divergência. | Extrair a versão para uma constante única (ex. `__version__` em `qc_core.py` ou um `VERSION` em `i18n.py`) e interpolar no template (`"app_title": "LAM+ Core QC v{version}"`). |
| 4.4 | `qc_avaatech.py:192,220` | `T["read_error"].format(error=e)` e `T["qc_error"].format(error=e)` traduzem apenas o prefixo da mensagem; o texto da exceção (`str(e)`) vem das bibliotecas (pandas/sklearn) sempre em inglês, mesmo com `lang="pt"` selecionado. Resultado: mensagens de erro mistas PT/EN. | Mapear as exceções mais comuns (arquivo corrompido, coluna ausente, etc.) para mensagens próprias e traduzidas em vez de expor `str(e)` cru; manter o texto técnico original apenas em um expander/"detalhes técnicos" opcional. |
| 4.5 | `qc_avaatech.py:137` vs. `i18n.py:18` | A lista de idiomas suportados existe em dois lugares: `SUPPORTED_LANGS` em `i18n.py` e `LANG_OPTIONS` em `qc_avaatech.py`. Adicionar um novo idioma exige tocar nos dois arquivos (+ criar o JSON), sem nenhuma validação cruzada. | Gerar `LANG_OPTIONS` dinamicamente a partir de `i18n.SUPPORTED_LANGS` (+ um nome de exibição por idioma, também vindo do JSON, ex. `"language_name": "Português"`), eliminando a duplicação. |
| 4.6 | ~~`qc_avaatech.py:265`~~ | ✅ **Resolvido em 2026-06-28.** `st.dataframe(rep0[display_cols], ...)` exibe os nomes de coluna originais do Avaatech (`"CompositeDepth (mm)"`, `"Rh-La Area"`, etc.), que não são traduzidos — inconsistente com o resto da UI à primeira vista, mas é intencional. Documentado explicitamente em `CLAUDE.md` (descrição de `qc_avaatech.py`: "nomes de coluna originais do instrumento não traduzidos"), deixando de ser uma exceção implícita. | — |

---

## 5. Melhorias de performance

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 5.1 | `qc_core.py:401-460` (`compute_flags`) | Loop Python com `rep0.iterrows()` — reconstrói uma `Series` por linha, O(n) em Python puro em vez de vetorizado. Para cores longos (milhares de linhas), é o principal candidato a lentidão. | Vetorizar com máscaras booleanas (`(rep0[z_cols].abs() > 2).any(axis=1)`, etc.) e combinar com `np.select`/`np.where` em vez de loop. |
| 5.2 | ~~`qc_core.py:171-189` (`qc_replicates`)~~ | ✅ **Resolvido em 2026-06-28** como parte da correção do achado **C1**: a função agora usa `df.groupby(REPLICATE_KEY_COLS)` em vez de iterar e refiltrar o `df` a cada profundidade. | — |
| 5.3 | `qc_core.py:299` (`qc_pca`) | `[mahalanobis(row, center, inv_cov) for row in pcs]` chama a função do scipy linha a linha em Python puro. | Vetorizar via álgebra matricial: `d = np.sqrt(np.einsum('ij,jk,ik->i', diff, inv_cov, diff))` onde `diff = pcs - center`. |
| 5.4 | `qc_avaatech.py:198,212` (`check_file`/`run_qc` no corpo principal do script) | Streamlit reexecuta o script inteiro a cada interação (ex.: trocar o idioma no seletor da sidebar). Isso recalcula `check_file` e `run_qc` do zero mesmo quando o arquivo enviado não mudou — desperdício de CPU para arquivos grandes. | Envolver a leitura do Excel e `run_qc()` com `@st.cache_data` (chave = hash do arquivo enviado), recalculando só quando o upload mudar, não quando o idioma mudar. |
| 5.5 | `qc_avaatech.py:37-113` (funções `plot_*`) | Figuras matplotlib são recriadas do zero a cada rerun do Streamlit, mesmo sem mudança nos dados. | Combinar com o cache do item 5.4: já que `rep0` fica estável entre reruns de troca de idioma, as figuras (exceto textos/títulos) poderiam ser cacheadas por dados + idioma. |

---

## 6. Qualidade do código (legibilidade, organização, docstrings)

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 6.1 | `qc_core.py` (todo o arquivo) | Nenhuma função tem type hints, apesar de o código ser uma biblioteca importável (`from qc_core import check_file, run_qc`, conforme o próprio docstring do módulo sugere). | Adicionar type hints (`pd.DataFrame`, `tuple[list[str], list[str]]`, etc.) para melhorar suporte de IDE e detecção precoce de erros. |
| 6.2 | `qc_core.py:339-394, 401-460` (`compute_scores`, `compute_flags`) | **Parcialmente resolvido.** Números mágicos ainda espalhados inline: limiares `2`, `3`, `40`, percentis `95`/`99`. `ROLLING_WINDOW`, `QI_WEIGHTS` e, **desde 2026-06-28** (item 8.6), `QI_THRESHOLD_OK = 80` já são constantes nomeadas no bloco `CONFIGURAÇÕES` — essa parte da sugestão original já foi implementada. | Promover os limiares restantes a constantes nomeadas (ex. `Z_THRESHOLD_ATTENTION = 2`, `Z_THRESHOLD_REJECT = 3`, `QI_THRESHOLD_REJECT = 40`), facilitando ajuste e leitura. |
| 6.3 | `qc_core.py:401-407` (docstring de `compute_flags`) e `locales/*.json` (`plot_qf_labels`) | O mapeamento QF 0-3 → significado existe em dois lugares com fontes de verdade diferentes: comentário no docstring (`"0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado"`) e arrays de tradução. Se alguém alterar a semântica de um flag, é fácil esquecer de atualizar um dos dois lugares. | Centralizar o mapeamento QF→significado em uma constante Python (ex. `QF_LABELS = {0: "qf_ok", 1: "qf_attention", ...}`) referenciada tanto no código quanto nas chaves de tradução. |
| 6.4 | repositório (geral) | Não há nenhum diretório `tests/` nem suíte automatizada — toda validação até aqui (incluindo os achados **C1**/**C2** deste documento) foi manual, via execução ad-hoc. | Criar testes unitários para `qc_core.py` cobrindo: dados com NaN em colunas críticas, ausência total de colunas PCA, replicas não casáveis por profundidade, RPD com média zero, dataset com 1 linha. |
| 6.5 | `requirements.txt` | Dependências sem pin de versão (`pandas`, `numpy`, etc., sem `==` ou `>=`). Isso é um risco de reprodutibilidade — uma atualização de `scikit-learn` ou `pandas` pode mudar comportamento (ex. APIs de `PCA`, `mahalanobis`) sem aviso. | Fixar ao menos versões mínimas testadas (`pandas>=2.0,<3`, etc.), e considerar um `requirements-lock.txt` ou `pyproject.toml` com versões exatas para reprodutibilidade total. |
| 6.6 | `qc_avaatech.py` (corpo principal, linhas 121-219) | Lógica de interface roda inteiramente no nível de módulo (padrão comum em Streamlit, mas mistura definição de funções com execução imperativa no mesmo arquivo, sem nenhuma função `main()`). | Não é incomum em apps Streamlit pequenos, mas para um app que já cresceu (i18n, múltiplos plots, export) vale considerar encapsular o corpo em uma função `main()` chamada por `if __name__ == "__main__":`, facilitando testes futuros de fluxo. |

---

## 7. Gaps na cobertura bilíngue

| # | Arquivo:linha | Problema | Sugestão |
|---|---|---|---|
| 7.1 | `qc_avaatech.py:192,220` (já citado em 4.4) | Texto de exceções de bibliotecas externas (pandas/sklearn) nunca é traduzido, mesmo quando `lang="en"`/`"pt"` é selecionado — é a maior lacuna bilíngue real do app hoje. | Ver sugestão do item 4.4 (mapear exceções comuns para mensagens próprias e traduzidas). |
| 7.2 | `qc_avaatech.py:271` | Nome do arquivo de saída (`file_name="LAM_CoreQC_Output.xlsx"`) e nome da aba do Excel (`sheet_name="LAM_CoreQC"`, em `qc_avaatech.py:123`) são hardcoded em código, fora do sistema de i18n — não é exatamente "string não traduzida visível ao usuário na UI", mas é uma string fixa em inglês mesmo com PT selecionado. | Avaliar se vale localizar o nome do arquivo exportado (ex. `LAM_CoreQC_Saida.xlsx` em PT) ou documentar que nomes de arquivo são intencionalmente mantidos em um padrão único. |
| 7.3 | `i18n.py` (todo o arquivo) | Não há nenhuma validação de que `locales/pt.json` e `locales/en.json` possuem exatamente o mesmo conjunto de chaves. Hoje eles estão sincronizados, mas nada impede uma futura edição de adicionar uma chave em um idioma e esquecer o outro — o erro só apareceria em runtime como `KeyError`, possivelmente em produção. | Adicionar uma checagem (idealmente em teste automatizado, ver item 6.4) que compara `set(TEXTS["pt"].keys()) == set(TEXTS["en"].keys())` e o mesmo para `CHECK_MESSAGES`, falhando o build/CI se divergirem. |
| 7.4 | `qc_avaatech.py:137` | O rótulo do seletor de idioma (`"Português"`, `"English"`) está hardcoded no código Python, não no JSON de locale — ironicamente, o próprio seletor de idioma não vem do sistema de i18n. | Mover os nomes de exibição dos idiomas para dentro de cada `locales/<lang>.json` (ex. chave `"language_name"`), permitindo que a lista de idiomas seja construída dinamicamente (ver também item 4.5). |

---

## 8. Funcionalidades planejadas (ainda não implementadas)

Itens combinados com o usuário mas que ainda não foram codificados — registrados aqui para não se perderem entre sessões.

### 8.1 Exportação de relatório em PDF por testemunho

Hoje a única saída além da tela é o `.xlsx` (`to_excel_bytes`, `qc_avaatech.py`), com todas as linhas `Rep0` misturadas, sem distinção por testemunho. Plano combinado em 2026-06-28:

- **Granularidade:** agrupar por **testemunho**, não por valor exato de `Spectrum`. `Spectrum` mistura nome do testemunho + seção (ex. `"lontra-T01"`..`"lontra-T06"` são 6 seções de **um** testemunho "lontra", com profundidades compostas contínuas) — confirmado no arquivo de exemplo. Precisa de uma função (`qc_core.py`) que extraia o nome do testemunho a partir do prefixo de `Spectrum` (ex. regex `^(.+?)-T\d+$`, com fallback para o próprio `Spectrum` se não casar o padrão) e agrupe as seções antes de gerar o PDF. **Ainda não implementado.**
- **Biblioteca:** `matplotlib.backends.backend_pdf.PdfPages` — zero dependência nova (matplotlib já está no `requirements.txt`).
- **Conteúdo do PDF:** capa (logo, nome do testemunho, profundidade composta, nº de medições, data/hora, modos de QC usados — `strict_missing_data`/`combine_rolling_vars`, para reprodutibilidade) + uma página por gráfico de diagnóstico + página de "Intervalos Problemáticos" (✅ **implementada em 2026-06-28**, ver abaixo) em vez de listar ponto a ponto. **Capa e páginas de gráfico ainda não implementadas** — só a página de intervalos existe até agora.
- **UI:** seletor de testemunho + opção "Todos" (gera `.zip` com um PDF por testemunho), botão de download ao lado do `.xlsx`, geração só no clique. **Ainda não implementado** — `report_pdf.py` existe como módulo, mas não está conectado a `qc_avaatech.py` ainda.
- Módulo `report_pdf.py` **criado em 2026-06-28**, separado de `qc_core.py` (que continua sem dependência de relatório/UI) e de `qc_avaatech.py`.

**Progresso até agora (2026-06-28) — página "Intervalos Problemáticos":**
- `qc_core.py`: `compute_flags` passou a rastrear **por que** cada linha foi flagrada — nova coluna `rep0["QF_Causes"]` (string com códigos `CAUSE_*` separados por `;`, vazia se `QF<2`). Resolve também parte da lacuna de explicabilidade já anotada antes nesta seção (nenhuma explicação de qual critério disparou o flag). Novos códigos: `CAUSE_THROUGHPUT`, `CAUSE_RH_LA`, `CAUSE_RH_LA_INC`, `CAUSE_ROLLING`, `CAUSE_PCA`, `CAUSE_QI_LOW`, `CAUSE_MISSING_DATA`. `QF_PLOT_ORDER` movido de `qc_avaatech.py` para `qc_core.py` (era duplicação de fonte de verdade — `report_pdf.py` também precisa dele para traduzir QF→label).
- `report_pdf.py`: `detect_intervals(rep0, min_gap=20)` agrupa medidas consecutivas com `QF >= 2` (inclui `QF_INDETERMINATE`) em clusters contíguos, tolerando gaps de até `min_gap` mm; cada intervalo retorna profundidade início/fim, nº de medidas, QF máximo, e o conjunto de causas únicas. `build_problem_intervals_page(intervals, T)` renderiza a tabela como página matplotlib, traduzindo QF e causas via `locales/*.json`.
- Validado contra `data/exemplo_dados_consolidados.xlsx`: 37 intervalos detectados, causas corretas por linha, e um caso sintético com `QF_INDETERMINATE` no meio de um cluster (label "ND-Indeterminado" exibido corretamente, não o número `9` cru).
- Novas chaves em `locales/pt.json`/`en.json`: `report_intervals_title/empty/depth_start/depth_end/n_points/qf_max/causes`, `cause_throughput/rh_la/rh_la_inc/rolling/pca/qi_low/missing_data`.

**Progresso adicional (2026-06-28) — aviso de "flag pontual" (QF>=2 mas QI>=80):**
- `qc_core.py`: nova constante `QI_THRESHOLD_OK = 80` (extraída do literal mágico que já existia em `compute_flags`, reusado também aqui — resolve uma pontinha do item 6.2). `is_pointwise_flag(rep0)` identifica linhas onde `QF` é 2/3 mas `QI >= QI_THRESHOLD_OK` — ou seja, o flag veio de um critério pontual (z-score ou Mahalanobis) e não do QI agregado; `QF_INDETERMINATE` é excluído de propósito (motivo ali é dado faltante, não critério pontual). `format_causes(causes, T)` traduz códigos `CAUSE_*` para texto (movido de um helper privado que existia em `report_pdf.py`, agora compartilhado). `add_pointwise_flag_notes(rep0, lang="pt")` adiciona `rep0["Pointwise_Flag_Note"]` com a explicação traduzida, vazia para as demais linhas.
- `qc_avaatech.py`: chama `add_pointwise_flag_notes` logo após `run_qc`, então a coluna nova aparece automaticamente na tabela exibida (`st.dataframe`) e no `.xlsx` exportado (`to_excel_bytes`), sem código extra em nenhum dos dois.
- `report_pdf.py`: `detect_intervals` agora também calcula `has_pointwise_flag` por intervalo (usa `qc_core.is_pointwise_flag`); `build_problem_intervals_page` marca esses intervalos com um ícone "⚠" junto ao QF máximo e adiciona uma nota de rodapé na página (só aparece se houver pelo menos 1 intervalo marcado).
- Validado: 72 medidas pontuais identificadas no arquivo real, notas traduzidas corretamente em PT/EN com causas e QI formatados, vazias para as demais linhas; 34 dos 37 intervalos detectados marcados como pontuais; sem regressão na distribuição de QF.
- Novas chaves: `pointwise_flag_note`, `pdf_pointwise_footnote` em `locales/pt.json`/`en.json`.

### 8.2 Campo "Operador" no formulário da UI

Pedido em 2026-06-28: adicionar um campo de texto na interface (`qc_avaatech.py`, ex. na sidebar, próximo aos checkboxes de QC) para o usuário informar o **nome do operador** responsável pela análise. Esse valor deve aparecer na capa do relatório PDF (item 8.1) para rastreabilidade — quem rodou o QC e gerou aquele relatório específico.

### 8.3 Campo "Comentários/Observações" no formulário da UI

Pedido em 2026-06-28: adicionar um campo de texto livre (ex. `st.text_area`) onde o operador possa registrar observações sobre a sessão de QC (condições da medição, ressalvas, contexto da amostra, etc.). O conteúdo desse campo também deve ser incluído no relatório PDF (item 8.1), provavelmente na página de capa ou numa página dedicada de observações.

Ambos os campos (8.2/8.3) são só para compor o PDF — não alteram o cálculo do QC em si, e precisam de chaves novas em `locales/pt.json`/`en.json` (label dos campos, placeholder, texto do cabeçalho no PDF).

### 8.4 Melhorar a PCA (QC6): vetores e clusters

Pedido em 2026-06-28 (`qc_core.py` `qc_pca` / `qc_avaatech.py` `plot_pca`): enriquecer a PCA atual (hoje só `PC1`/`PC2` + distância de Mahalanobis, ver resumo de parâmetros já levantado nesta conversa) com:

- **Vetores (loadings/biplot):** desenhar no gráfico de PCA as setas dos *loadings* de cada elemento de `ELEMENTS_PCA` sobre PC1/PC2 (de `pca.components_`, já disponível via sklearn — `qc_pca` já guarda o objeto `pca` localmente, só não o retorna hoje), mostrando quais elementos mais influenciam cada componente. Precisa decidir: escala das setas (normalizada vs. proporcional à variância explicada) e se mostra todos os elementos ou só os de maior contribuição (pode poluir o gráfico com 10 elementos).
- **Clusters:** agrupar as medições no espaço PC1/PC2 (ex. K-means ou clustering hierárquico) para identificar agrupamentos geoquímicos, coloridos no scatter em vez de (ou além de) colorir por distância de Mahalanobis. Precisa decidir: método de clustering, número de clusters (fixo vs. escolhido automaticamente, ex. silhouette score), e se os clusters entram só na visualização ou também influenciam `Score_PCA`/`QF` de alguma forma.

Ainda não implementado — só registrado aqui. Antes de codificar, vale discutir separadamente as decisões de método/parâmetros de cada parte (vetores e clusters), como já foi feito para os outros itens desta seção.

### 8.5 Seletor de coluna de profundidade exibida (CompositeDepth vs. CoreDepth) — ✅ implementado em 2026-06-28

Pedido e implementado em 2026-06-28: `qc_avaatech.py` ganhou um seletor na sidebar (`DEPTH_DISPLAY_COL`) para escolher entre `CompositeDepth (mm)` (padrão, `qc_core.DEPTH_COL`) e `CoreDepth` (`qc_core.CORE_DEPTH_COL`, nova constante) como coluna de profundidade no eixo X dos gráficos, na tabela exibida e no relatório PDF. **Puramente de exibição — não afeta nenhum cálculo do pipeline**; `REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]` em `qc_core.py` permanece inalterado (continua correto para o casamento interno de réplicas, propósito diferente do seletor).

- `qc_core.py`: nova constante `CORE_DEPTH_COL = "CoreDepth"`, independente de `REPLICATE_KEY_COLS` (mesmo literal "CoreDepth", propósitos diferentes — documentado em comentário para não confundir os dois).
- `qc_avaatech.py`: todas as funções `plot_*` passaram a receber `depth_col=DEPTH_COL` (default mantém compatibilidade); a tabela exibida (`st.dataframe`) reordena as colunas para colocar `DEPTH_DISPLAY_COL` primeiro (sem alterar a ordem das linhas nem o `.xlsx` exportado, que continua com `rep0` original intacto).
- `report_pdf.py`: `detect_intervals(rep0, min_gap=20, depth_col=DEPTH_COL)` e `build_problem_intervals_page(intervals, T, depth_col=DEPTH_COL)` ganharam o parâmetro. **Detalhe de correção importante:** a ordenação e a decisão de gap (`> min_gap`) usam **sempre** `qc_core.DEPTH_COL` (contínua/monotônica), nunca `depth_col` — usar `CoreDepth` (que reinicia a cada seção) para essa decisão misturaria/mascararia transições de seção como "gap pequeno" (diferença ficaria negativa, nunca disparando um novo cluster). `depth_col` só é usado para os valores `depth_start`/`depth_end` efetivamente exibidos.
- **Limitação conhecida, documentada em código e no tooltip do seletor:** num testemunho com múltiplas seções, um intervalo que cruze uma transição de seção pode reportar `depth_end < depth_start` quando `depth_col=CoreDepth` (confirmado no arquivo de exemplo: 2 dos 37 intervalos). É puramente cosmético — a contagem de intervalos e as causas agregadas são idênticas entre os dois modos (validado).
- Cabeçalhos da tabela de intervalos no PDF (`report_intervals_depth_start`/`_end`) passaram a ser templates com `{label}` (ex. "Início (CompositeDepth, mm)"), preenchido com o nome técnico curto da coluna escolhida.
- Novas chaves em `locales/pt.json`/`en.json`: `depth_display_label/composite/core/help`.
- Validado: gráficos e páginas de PDF renderizam sem erro nos dois modos; `detect_intervals` produz a mesma contagem de intervalos (37) e mesmas causas com `CompositeDepth` e `CoreDepth`; `REPLICATE_KEY_COLS` confirmado intocado linha por linha; app Streamlit testado de ponta a ponta (HTTP 200).

### 8.6 PCA (QC6) sempre diagnóstica, mas opcional no critério de QF — ✅ implementado em 2026-06-28

Pedido em 2026-06-28. Inicialmente registrado só como ideia de Roadmap no README; depois, no mesmo dia, decidido implementar de fato (não só documentar).

- `qc_core.py`: novo parâmetro `include_pca_in_qf` (default `False`) em `compute_scores`, `compute_flags` e `run_qc`. Quando `False`: `Score_PCA` continua **sempre calculado** (PCA permanece diagnóstico, sempre visível na aba correspondente), mas é excluído da soma ponderada do `QI` — o peso de `QI_WEIGHTS["Score_PCA"]` (0.05) é removido e os pesos restantes são renormalizados para somar 1.0 (`0.25/0.95, 0.15/0.95, 0.20/0.95, 0.20/0.95, 0.15/0.95`). **Detalhe importante:** só mexer no peso do QI não bastava — `compute_flags` também tem uma checagem **direta** de `Mahalanobis > p95/p99` que dispara `QF=2/3` independente do QI; essa checagem (e o registro de `CAUSE_PCA`) agora só roda quando `include_pca_in_qf=True`, senão a PCA continuaria influenciando o QF por um caminho paralelo mesmo com peso zero no QI.
- `qc_avaatech.py`: 3º checkbox na sidebar (`include_pca_qf_label`, default desmarcado), passado a `run_qc`.
- Novas chaves em `locales/pt.json`/`en.json`: `include_pca_qf_label`, `include_pca_qf_help`.
- **Validado** contra `data/exemplo_dados_consolidados.xlsx`: `include_pca_in_qf=True` reproduz exatamente a distribuição de QF anterior a esta mudança (`{0:201, 2:49, 3:20}`); default novo (`False`) dá `{0:208, 2:45, 3:17}` (menos linhas flagradas, já que o critério direto de Mahalanobis para de disparar); `Score_PCA` confirmado sempre calculado em ambos os modos; pesos renormalizados confirmados somando 1.0. App Streamlit testado de ponta a ponta (HTTP 200).
- README atualizado: nova seção "About QC6 (PCA)" (espelhando "About QC4"), e o item de Roadmap correspondente foi reescrito para focar no que **ainda falta** (biplot/clustering — ver 8.4/abaixo), já que a desacoplagem do QF deixou de ser "planejada" e passou a ser o comportamento real.

### 8.7 Seletor de modo de QF: QI ponderado (atual) vs. contagem de módulos reprovados (planejado)

Pedido em 2026-06-28, registrado no README ("Roadmap") — **ainda não implementado**. Hoje só existe um algoritmo de `QF` (`compute_flags`: limiares de `QI` + critérios pontuais de z-score/Mahalanobis). A ideia é um segundo modo alternativo, baseado em contagem simples de módulos que "reprovaram" (em vez do QI ponderado) — um critério mais transparente e menos compensatório (hoje um módulo muito bom pode "compensar" outro ruim no QI agregado; contagem de reprovações não compensaria). Modo QI ponderado continuaria sendo o default; contagem de módulos seria opt-in.

### 8.8 Empacotamento como executável standalone (PyInstaller) — ✅ implementado em 2026-06-29

Pedido e implementado em 2026-06-29: diretório `installer/` empacota o app como executável standalone (Windows `.exe` / binário Linux), sem exigir Python/`.venv` na máquina de destino.

- `installer/launcher.py` — entry point real do PyInstaller. `qc_avaatech.py` é um script Streamlit (roda via `streamlit run`, não como script Python comum), então não pode ser o entry point direto — o launcher invoca `streamlit.web.cli` programaticamente, apontando para a cópia de `qc_avaatech.py` empacotada. Desliga o file watcher do Streamlit (`--server.fileWatcherType=none`) — sem isso, apareceu em teste um `RuntimeError: dictionary changed size during iteration` (race condition conhecida do watcher); também não faz sentido vigiar arquivo-fonte num executável congelado.
- `installer/lamplus_qc.spec` — usa `collect_all()` para `streamlit`/`scipy`/`sklearn`/`matplotlib` (dependências dinâmicas invisíveis à análise estática, já que o launcher nunca importa `qc_avaatech.py`/`qc_core.py` diretamente). Copia `qc_avaatech.py`, `qc_core.py`, `report_pdf.py`, `i18n.py`, `locales/` e `assets/` como dados brutos, espelhando a estrutura relativa do repo (por isso os caminhos via `__file__` em `qc_avaatech.py`/`i18n.py` funcionam sem alteração no código da aplicação). Ícone: `assets/lamplus_logo.ico`. **Bug real encontrado e corrigido durante a validação:** Python via conda/miniforge no Windows guarda DLLs nativas (`ffi-8.dll`, tcl/tk, sqlite3, bz2, expat) em `<python>/Library/bin/` em vez de `DLLs/`, onde o PyInstaller procura por padrão — o primeiro build gerava um `.exe` que crashava com `DLL load failed... _ctypes`. Corrigido localizando essas DLLs via `sys.base_prefix` no `.spec` (sem efeito em Python "oficial" do python.org).
- `installer/build_exe.py` — detecta SO, usa o Python do `.venv`, roda o PyInstaller com os parâmetros corretos.
- `installer/README_BUILD.md` — instruções de build Windows/Ubuntu + avisos conhecidos.
- **`.gitignore`**: `installer/dist/`, `installer/build/`, `installer/__pycache__/`, `*.exe`, `*.spec.bak`. **`requirements.txt`**: `pyinstaller` comentado como dependência só de build.
- **Validado de ponta a ponta no Windows em 2026-06-29:** build completo executado de fato (não só revisão de código) — executável onefile gerado (~150MB em `installer/dist/LAM_Core_QC.exe`), executado, servidor Streamlit sobe e responde HTTP 200 em `localhost:8501`, sem erros no log após a correção do file watcher e da DLL. **Não testado no Ubuntu** (sem ambiente disponível na sessão).
- **O `.exe` gerado nunca é commitado** — distribuição é via **GitHub Releases**, não via git.

---

## 9. Protocolo v4.2 (Igor) — itens priorizados de incorporação

**Origem:** análise comparativa entre o protocolo v4.2 e o pipeline atual, feita em 2026-07-28. Texto completo do protocolo + tabela-síntese com todas as classificações (INCORPORAR/MODIFICAR/MANTER/DESCARTAR) e as notas de cada item estão em `DEVELOPMENT.md`, seção "Protocolo v4.2 — Análise e Roadmap de Incorporação".

### Itens prontos para implementação, na ordem sugerida

| Ordem | Item | Descrição |
|---|---|---|
| a | ~~Correção `calculate_rpd` (`mean==0` → `NaN`)~~ | ✅ **Implementado em 2026-07-28** — ver item 1.1 acima. |
| b | ~~Argônio (`Ar-Ka Area`) em QC1 e QC4~~ | ✅ **Implementado em 2026-07-28.** Nova constante `ARGON_COL = "Ar-Ka Area"`. `qc_throughput` (QC1) agora combina Throughput + Argônio via `rep0["Instrument_z"]` = o z-score de maior magnitude absoluta entre os dois, linha a linha ("pior dos dois" — um problema de vedação/atmosfera pode aparecer só no Argônio sem derrubar o Throughput, e vice-versa); `Throughput_z`/`Argon_z` continuam disponíveis individualmente como diagnóstico. `Score_Throughput` (`compute_scores`) e o critério pontual de QF (`compute_flags`) passaram a usar `Instrument_z`; nova causa `CAUSE_ARGON` atribuída dinamicamente conforme qual dos dois z-scores foi o pior. `ROLLING_VARS` ganhou `Ar-Ka Area` como quarta variável (só usada quando `combine_rolling_vars=True`, comportamento default inalterado); `qc_rolling` agora ignora graciosamente qualquer variável de `ROLLING_VARS` ausente do arquivo (mesmo padrão de degradação de `qc_pca`/`qc_replicates`) — **importante para quando a estrutura multi-energia (30/50 kV, sem Argônio) for suportada** (item 10 da análise em `DEVELOPMENT.md`, ainda em aberto). Nova chave `cause_argon` em `locales/pt.json`/`en.json`. **Validado** contra `data/exemplo_dados_consolidados.xlsx`: distribuição de QF (default, `combine_rolling_vars=False`) passa de `{0:208, 2:45, 3:17}` para `{0:199, 1:1, 2:42, 3:28}` (20 linhas onde o Argônio é o pior dos dois, 11 delas cruzando o limiar de flag; QF=3 sobe de 17→28 — regressão esperada, não um bug: o Argônio estava sendo 100% ignorado antes); com `combine_rolling_vars=True`, `{0:174, 2:79, 3:17}` → `{0:155, 2:87, 3:28}`. Testado também removendo a coluna `Ar-Ka Area` do arquivo: `check_file` não gera erro, `Argon_z` fica `NaN`/`Instrument_z` cai de volta para `Throughput_z` puro, e a distribuição de QF reproduz exatamente o baseline anterior à mudança (`{0:208, 2:45, 3:17}`) — sem regressão para arquivos sem Argônio. Rodado com `-W error::RuntimeWarning`, sem warnings. |
| c | ~~Coloração verde/amarelo/vermelho no `.xlsx` exportado~~ | ✅ **Implementado em 2026-07-28.** `to_excel_bytes` (`qc_avaatech.py`) ganhou parâmetro `original_columns` (recebe `df_raw.columns`, o arquivo bruto antes do pipeline); colunas ausentes desse conjunto (= adicionadas por `run_qc`/`compute_scores`/`compute_flags`/`add_pointwise_flag_notes`) recebem `openpyxl.PatternFill` célula a célula via `_qc_cell_fill` — verde (`C6EFCE`) para QF=0/"OK"/"NO", amarelo (`FFF2CC`) para QF=1/"WARNING", vermelho (`F4CCCC`) para QF∈{2,3}/"CRITICAL"/"YES". Colunas originais do Avaatech nunca são tocadas (comparação por nome de coluna, não por posição). **Divergência deliberada do `reports.py` do apêndice** (`DEVELOPMENT.md`): lá o `color(cell)` roda sobre a planilha inteira comparando `cell.value` contra os literais 0/1/2/3 sem restrição de coluna — nesta base, `QF` é um int (não string `"QF0"`/`"QF1"`/...) e várias colunas numéricas contínuas adicionadas pelo pipeline (`Score_Replica`, `Score_PCA`, RPD, z-scores) legitimamente assumem os valores 0, 1, 2 ou 3 sem relação nenhuma com severidade (ex.: `Score_Replica=0` é o pior score possível, não "OK"). Por isso o match numérico 0/1/2/3 foi restrito à coluna `QF` especificamente; o match textual ("OK"/"WARNING"/"CRITICAL"/"YES"/"NO") continua valendo em qualquer coluna QC, já que nenhuma coluna numérica pode colidir com uma string. `QF_INDETERMINATE` (9) não está na especificação do item (c) e fica sem preenchimento — comportamento intencional, não pendência. Validado contra `data/exemplo_dados_consolidados.xlsx`: 199 células QF=0→verde, 1 célula QF=1→amarelo, 42 QF=2 + 28 QF=3→vermelho (mesma distribuição do item b); confirmado que colunas originais (ex. `Throughput`) não recebem preenchimento e que `Score_Replica=0` não é colorido. |
| d | ~~Labels "Coherent Scatter"/"Incoherent Scatter" como chaves i18n~~ | ✅ **Implementado em 2026-07-28.** `plot_rh1_title`/`plot_rh2_title` em `locales/pt.json`/`en.json` passaram a incluir o nome conceitual do v4.2 junto ao nome técnico da variável: PT `"QC2 — Espalhamento Coerente (Rh-Lα)"`/`"QC3 — Espalhamento Incoerente (Rh-Lα-Inc)"`, EN `"QC2 — Coherent Scatter (Rh-Lα)"`/`"QC3 — Incoherent Scatter (Rh-Lα-Inc)"`. Lógica de `qc_rh_la`/`qc_rh_la_inc` em `qc_core.py` intocada — mudança é só de label de exibição, consumida via `T["plot_rh1_title"]`/`T["plot_rh2_title"]` em `qc_avaatech.py:55` (sem string hardcoded em `.py`). **Consistência verificada nos demais QCs:** QC1 tinha a mesma lacuna — título ainda dizia só "Throughput" mesmo após o protocolo v4.2 (item b, já incorporado em 2026-07-28) ter passado a combinar Throughput+Argônio sob o nome conceitual "Instrument Stability"; `plot_throughput_title` corrigido para `"QC1 — Estabilidade do Instrumento (Throughput)"`/`"QC1 — Instrument Stability (Throughput)"` pelo mesmo motivo. QC4 (`"QC4 — Rolling QC (Rh-Lα-Inc)"`) e QC5 (`"QC5 — Réplicas/Replicates (Mean RPD)"`) já usavam a nomenclatura conceitual do v4.2 ("Rolling QC"/"Replicates") — nenhuma mudança necessária. `tab_rh` (aba combinada QC2+QC3) e as chaves `cause_rh_la`/`cause_rh_la_inc` foram deixadas com o nome técnico curto (mesmo padrão já usado por `cause_throughput`/`cause_argon`) — fora do escopo pontual pedido ("respectivamente" mapeia 1:1 para os dois títulos de QC2/QC3, não para a aba combinada nem para as causas). Validado: `set(TEXTS["pt"].keys()) == set(TEXTS["en"].keys())` (paridade de chaves mantida), JSON válido nos dois arquivos, nenhuma outra referência hardcoded às strings antigas no repositório. |
| e | Modo de QF por contagem de módulos reprovados (opt-in) | Implementa o item 8.7 já registrado abaixo — segundo modo de cálculo de QF (contagem de ALERT/CRITICAL por módulo, especificação do v4.2), como alternativa opt-in ao QI ponderado atual (que continua default). **Atenção:** a lógica de NaN→estado deve produzir indeterminado (`QF_INDETERMINATE`), nunca "OK" — não repetir o bug do achado C2, que o v4.2 original reintroduz (`classify_z`/`classify_rolling` tratam NaN como OK). |

### Bloqueados até decisão do time

Estes itens do v4.2 têm mérito mas tensionam com decisões de design já tomadas e documentadas — **não implementar sem alinhamento explícito com Igor/equipe**:

- **Persistência temporal no QC4** (exigir ≥2 pontos consecutivos ou 2 pontos numa janela de 3 antes de emitir ALERT) — conflita com a decisão registrada no item 1.5 acima, de considerar um único z-score pontual alto como flag legítimo ("defesa em profundidade"), hoje só explicado via `is_pointwise_flag`/`Pointwise_Flag_Note` em vez de suprimido.
- **Estrutura multi-energia** (abas 10/30/50 kV, parâmetros por energia) — depende de confirmação se os arquivos reais do LAM+ chegam com múltiplas abas de energia ou se isso é cenário futuro/outro equipamento. O arquivo de exemplo atual só tem uma aba (`10kv`).
- **Exportar réplicas brutas (Rep1/Rep2) junto no `.xlsx`** — hoje o export contém só o subconjunto `rep0` filtrado; preservar as réplicas brutas mudaria o escopo do que o arquivo exportado representa.

---

## Resumo de prioridade sugerida

1. ~~**C1**~~ e ~~**C2**~~ ✅ ambos resolvidos (2026-06-28) — os dois riscos de integridade científica dos resultados (réplicas não casadas e dado faltante mascarado como "OK") estão corrigidos e validados contra dados reais.
2. ~~**2.2** / **1.2** / **1.3**~~ ✅ resolvidos (2026-06-28) — QC6 (PCA) degrada graciosamente (score neutro + warning bilíngue) em vez de travar o pipeline quando faltam elementos/linhas; matriz de covariância usa `pinv`.
3. ~~**4.1**~~ ✅ resolvido (2026-06-28) — QC4 considera só Rh-La-Inc Area por padrão (dado espectral real); combinar as três variáveis (máximo dos `\|delta_z\|`) é opt-in via checkbox. README atualizado.
4. ~~**8.6**~~ ✅ resolvido (2026-06-28) — PCA (QC6) é só diagnóstico por padrão, não entra no QI/QF; checkbox opt-in reativa os dois caminhos (peso no QI + checagem direta de Mahalanobis em `compute_flags`). README atualizado ("About QC6").
5. ~~**8.8**~~ ✅ resolvido (2026-06-29) — empacotamento standalone via PyInstaller (`installer/`), testado de ponta a ponta no Windows; `.exe` nunca commitado, distribuição via GitHub Releases.
6. Demais itens são robustez/performance/qualidade incrementais, sem risco de resultado incorreto.
7. **Seção 9** (protocolo v4.2 do Igor) registra os próximos itens priorizados a implementar (a-e) e os que estão bloqueados até decisão do time — ver acima.
