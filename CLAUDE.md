# CLAUDE.md — LAM+ Core QC (Avaatech XRF Core Scanner)

Contexto para sessões do Claude Code neste repositório. Leia isto antes de propor mudanças — ele documenta o que o projeto faz, como os arquivos se conectam, e decisões/limitações já conhecidas.

## O que é este projeto

Pipeline de **Controle de Qualidade (QC)** para dados exportados pelo scanner de sedimentos por fluorescência de raios-X (XRF) **Avaatech**, desenvolvido no **LAM+** (Laboratório de Análise Multiespectral e IA para Sedimentos, UFF). O usuário faz upload de um `.xlsx` exportado pelo scanner; o app roda 6 módulos estatísticos de QC, calcula um **Quality Index (QI)** e um **Quality Flag (QF)** por medição, mostra gráficos de diagnóstico e permite baixar o resultado anotado em `.xlsx`.

Frontend é **Streamlit**. Não há backend/banco de dados — tudo roda local, em memória, por sessão.

## Estrutura de arquivos

```
qc_core.py              # Lógica pura do pipeline QC (sem Streamlit) — importável como lib
qc_avaatech.py          # Frontend Streamlit — único ponto de entrada da UI
report_pdf.py           # Geração de relatório PDF (parcial — ver TODO.md item 8.1)
i18n.py                 # Carregador de traduções (lê locales/*.json)
locales/
  pt.json               # Strings PT (idioma padrão)
  en.json               # Strings EN
iniciar.py              # Launcher multiplataforma (Windows/Linux) — roda streamlit via venv
setup_shortcut.py       # Gera ícone + cria atalho de desktop (.lnk no Windows, .desktop no Linux)
assets/
  lamplus_logo.png      # Logo original
  lamplus_logo.ico       # Gerado por setup_shortcut.py (não editar manualmente)
data/
  exemplo_dados_consolidados.xlsx   # Arquivo de exemplo real, usado para testes manuais
installer/               # Empacotamento como executável standalone (PyInstaller) — ver seção própria abaixo
  launcher.py            # Entry point real do PyInstaller — invoca o Streamlit CLI apontando para a cópia empacotada de qc_avaatech.py
  lamplus_qc.spec        # Spec file: collect_all (streamlit/scipy/sklearn/matplotlib), datas (qc_*.py/i18n.py/locales//assets/), ícone lamplus_logo.ico
  build_exe.py           # Roda o PyInstaller com os parâmetros corretos, em Windows e Ubuntu
  README_BUILD.md        # Como gerar o executável + avisos/limitações conhecidas
  dist/, build/          # Gerados pelo build — gitignored, NUNCA versionar o .exe (distribuir via GitHub Releases)
requirements.txt        # Dependências Python (pywin32 só Windows via marker de ambiente; pyinstaller comentado, só build)
README.md               # Overview do projeto (inglês, "público")
DEVELOPMENT.md          # Explicação do app + notas de decisões datadas (ex. i18n)
INSTALL.md              # Guia de instalação para Ubuntu
TODO.md                 # Levantamento de bugs/gaps encontrados em auditoria (2026-06-28) — ver antes de "corrigir" algo, pode já estar documentado lá
.venv/                  # Ambiente virtual local (gitignored) — SEMPRE use este venv, nunca o Python global
```

Não existem testes automatizados (`tests/`) nem CI configurado neste repositório — ver `TODO.md` item 6.4.

## Descrição de cada módulo

### `qc_core.py` — pipeline de QC (sem dependência de UI)

Importa `CHECK_MESSAGES` de `i18n.py` para mensagens bilíngues de validação. Constantes de configuração no topo do arquivo: `DEPTH_COL = "CompositeDepth (mm)"`, `REPLICATE_COL = "Replicate Nr Count"`, `ROLLING_WINDOW = 5`, `REQUIRED_COLUMNS`, `ELEMENTS_PCA`, `ELEMENTS_REPLICATES`. `CORE_DEPTH_COL = "CoreDepth"` (desde 2026-06-28) é uma constante **independente** de `REPLICATE_KEY_COLS` — mesmo literal "CoreDepth", propósito diferente: só para a opção de exibição (eixo X/tabela/PDF) em `qc_avaatech.py`/`report_pdf.py`, nunca usada em cálculo. **Não confundir os dois nem tentar "unificar" — são conceitos diferentes que coincidem no nome da coluna.**

Funções estatísticas de base:
- `robust_zscore(x)` — z-score robusto via MAD (mediana de desvios absolutos).
- `score_from_z(z)` — converte z-score em score 0–100.
- `calculate_rpd(values)` — Relative Percent Difference entre réplicas.

Validação:
- `check_file(df, lang="pt")` — valida estrutura do DataFrame **antes** de rodar o pipeline. Retorna `(errors, warnings)`. `errors` não-vazio bloqueia execução no frontend; `warnings` só avisa. Mensagens vêm de `CHECK_MESSAGES[key][lang]` (i18n.py), com templates `.format(**kwargs)`.

Módulos QC individuais (cada um recebe/retorna um DataFrame `rep0`, o subconjunto filtrado para `Replicate Nr Count == "Rep0"`):
- `qc_throughput` (QC1), `qc_rh_la` (QC2), `qc_rh_la_inc` (QC3) — z-score robusto pontual.
- `qc_rolling` (QC4) — média móvel (`ROLLING_WINDOW`) + delta + z-score do delta, para `ROLLING_VARS` (`Throughput`, `Rh-La Area`, `Rh-La-Inc Area`). **Resolvido em 2026-06-28** (`TODO.md` item 4.1, revisado no mesmo dia): por padrão (`combine_rolling_vars=False`), `compute_scores` usa só `Rh-La-Inc Area_delta_z` — é o dado espectral real medido; Throughput/Rh-Lα são parâmetros instrumentais secundários. Opt-in (`combine_rolling_vars=True`) combina as três via `rep0["Rolling_z"] = max(|delta_z|)`, já que um problema físico de medição (rachadura, bolha de ar, transição seco/úmido) tende a reagir em pelo menos uma das três simultaneamente — mais sensível, às custas de também reagir a deriva instrumental não necessariamente no dado espectral. Ver README.md ("About QC4") para a justificativa física completa.
- `qc_replicates` (QC5) — casa réplicas pela chave `REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]` (não por `DEPTH_COL`) e calcula RPD médio via `df.groupby(REPLICATE_KEY_COLS)`. **Corrigido em 2026-06-28** (`TODO.md` achado C1): `CompositeDepth (mm)` só é preenchido na primeira passada e fica nulo em `Rep1`/`Rep2`, então o casamento original por `DEPTH_COL` falhava para 100% das linhas no arquivo de exemplo. `CoreDepth` nunca é nulo e identifica a posição física junto com `Spectrum` — ambos agora fazem parte de `REQUIRED_COLUMNS`.
- `qc_pca` (QC6) — PCA (2 componentes) sobre `ELEMENTS_PCA` presentes + distância de Mahalanobis (via `np.linalg.pinv`, mais robusto a matriz quase-singular). **Corrigido em 2026-06-28** (`TODO.md` itens 1.2/1.3/2.2): se `len(pca_elements) < MIN_PCA_ELEMENTS` (2) ou `len(rep0) < MIN_PCA_ROWS` (3), QC6 é pulada — `PC1`/`PC2`/`Mahalanobis` ficam `NaN` em vez de lançar `ValueError`. `compute_scores` detecta isso e aplica `Score_PCA=100` (neutro, mesmo padrão de `Score_Replica`), mantendo o `QI` computável; `check_file` avisa com antecedência (`pca_unavailable`/`pca_too_few_rows`). Decisão de produto: degradar graciosamente em vez de bloquear, para não invalidar QC1-QC5 só por falta de um módulo de 5% de peso. **Desde 2026-06-28** (`TODO.md` item 8.6), `Score_PCA`/`Mahalanobis` são sempre calculados (PCA permanece diagnóstico, sempre visível na aba), mas só contribuem para `QI`/`QF` quando `include_pca_in_qf=True` (default `False` — ver `compute_scores`/`compute_flags`). README ("About QC6") documenta a motivação.

Agregação:
- `compute_scores(rep0, strict_missing_data=True, combine_rolling_vars=False, include_pca_in_qf=False)` — combina os scores individuais em `QI` via `QI_WEIGHTS` (pesos nomeados: 0.25/0.15/0.20/0.20/0.15/0.05) e calcula percentis 95/99 de Mahalanobis. `strict_missing_data` controla como o `QI` é tratado quando algum score é `NaN`: restritivo (padrão) → `QI=NaN` (qualquer score ausente invalida a linha); flexível → `QI` recalculado só com os módulos disponíveis, redistribuindo os pesos. `combine_rolling_vars` controla o `Score_Rolling`/`rep0["Rolling_z"]` do QC4: padrão (`False`) → só `Rh-La-Inc Area_delta_z` (dado espectral real); opt-in (`True`) → maior `|delta_z|` entre `ROLLING_VARS`. `include_pca_in_qf` controla se `Score_PCA` entra na soma ponderada do `QI`: padrão (`False`) → excluído, pesos restantes renormalizados para somar 1.0; opt-in (`True`) → volta com peso nominal 0.05. `Score_PCA` em si é sempre calculado independente desse parâmetro (PCA continua diagnóstico).
- `compute_flags(rep0, p95, p99, include_pca_in_qf=False)` — atribui `QF` (0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado, `QF_INDETERMINATE`=9=indeterminado) via loop `iterrows()` (não vetorizado — `TODO.md` item 5.1, ainda pendente). **Corrigido em 2026-06-28** (`TODO.md` achado C2): antes, comparações com `NaN` em Python retornavam `False` e uma linha com dado crítico faltante (`CRITICAL_INPUT_COLS` = `Throughput`/`Rh-La Area`/`Rh-La-Inc Area`) acabava com `QF=0` por fallthrough. Agora `is_indeterminate = rep0[CRITICAL_INPUT_COLS].isna().any(axis=1) | rep0["QI"].isna()` é calculado **antes** do loop e força `QF=QF_INDETERMINATE` incondicionalmente — nunca cai em `QF=0`. O flag indeterminado é sempre atribuído independente de `strict_missing_data`; esse parâmetro só afeta se o `QI` da linha fica `NaN` ou uma estimativa "best effort". A checagem de deriva do QC4 usa `row["Rolling_z"]` (já calculado em `compute_scores`), não mais um literal de coluna fixo. **Desde 2026-06-28**, também preenche `rep0["QF_Causes"]` (string com códigos `CAUSE_*` separados por `;`, ex. `"throughput;rolling"`) — registra por que cada linha foi flagrada, consumido por `report_pdf.detect_intervals`. `QF_PLOT_ORDER` (mapa QF→posição visual 0-4) também mora em `qc_core.py`, não em `qc_avaatech.py` — importado por quem precisar exibir QF numa escala ordenada (UI e relatório). **Desde 2026-06-28** (item 8.6), a checagem direta de `Mahalanobis > p95/p99` (que dispara `QF=2/3` independente do `QI`) só roda quando `include_pca_in_qf=True` — só mexer no peso do `QI` não bastaria para desacoplar a PCA do QF, já que esse critério pontual é um caminho paralelo.
- `is_pointwise_flag(rep0)` — `bool` por linha: `True` quando `QF` é 2/3 mas `QI >= QI_THRESHOLD_OK` (80) — ou seja, o flag veio de um critério pontual (z-score/Mahalanobis), não do QI agregado. Exclui `QF_INDETERMINATE` (motivo ali é dado faltante). Usado por `qc_avaatech.py` (via `add_pointwise_flag_notes`) e por `report_pdf.detect_intervals`.
- `format_causes(causes, T)` — traduz uma coleção de códigos `CAUSE_*` para texto (`T` = dict de traduções, ex. `TEXTS[lang]`). Compartilhado entre `qc_core.add_pointwise_flag_notes` e `report_pdf.build_problem_intervals_page`.
- `add_pointwise_flag_notes(rep0, lang="pt")` — adiciona `rep0["Pointwise_Flag_Note"]`: para linhas com `is_pointwise_flag`, uma explicação traduzida usando `QF_Causes`; vazia para as demais. Chamado em `qc_avaatech.py` logo após `run_qc`, então a coluna aparece automaticamente na tabela exibida e no `.xlsx` exportado.
- `run_qc(df, strict_missing_data=True, combine_rolling_vars=False, include_pca_in_qf=False)` — orquestra o pipeline completo, retorna `(rep0, p95, p99, pca_elements)`.

### `qc_avaatech.py` — frontend Streamlit

Único arquivo de UI. Importa de `qc_core` (`CORE_DEPTH_COL`, `DEPTH_COL`, `QF_INDETERMINATE`, `QF_PLOT_ORDER`, `add_pointwise_flag_notes`, `check_file`, `run_qc`) e de `i18n` (`TEXTS`, `DEFAULT_LANG`). Define `QF_COLORS` no topo do arquivo (cor de cada QF no gráfico de barras; `QF_PLOT_ORDER` mora em `qc_core.py`, não aqui). Quatro controles na sidebar: seletor `DEPTH_DISPLAY_COL` (`T["depth_display_label"]`, default `DEPTH_COL`/CompositeDepth — **puramente de exibição**, ver `qc_core.CORE_DEPTH_COL`) e três checkboxes que controlam `compute_scores`/`compute_flags`: `strict_missing_data` (default `True`), `combine_rolling_vars` (default `False` — QC4 considera só Rh-Lα-Inc por padrão; combinar as 3 variáveis é opt-in) e `include_pca_in_qf` (default `False` — PCA é só diagnóstico, não entra no QI/QF por padrão; opt-in reativa). Estrutura:
- Funções `plot_*(rep0, T, depth_col=DEPTH_COL)` — uma por aba de diagnóstico (Throughput, Rh-Lα/Rh-Lα-Inc, Rolling, Réplicas, PCA, QI/QF). `depth_col` é repassado como `DEPTH_DISPLAY_COL` na chamada — só muda o eixo X, nunca o cálculo.
- `to_excel_bytes(df)` — serializa o resultado para download (sempre com `rep0` original, sem a reordenação de colunas usada na tabela exibida).
- Corpo principal roda no nível de módulo (padrão Streamlit): `st.set_page_config` → seletor de idioma → seletor de profundidade exibida → checkboxes de QC → upload → `check_file` → `run_qc` + `add_pointwise_flag_notes` → resumo em métricas → 6 abas de gráficos → tabela completa (`st.dataframe`, colunas reordenadas com `DEPTH_DISPLAY_COL` primeiro; nomes de coluna originais do instrumento não traduzidos) → botão de download.
- **Não há `@st.cache_data`** em `check_file`/`run_qc` — toda interação na UI (incluindo trocar o idioma) reexecuta o pipeline inteiro do zero (`TODO.md` item 5.4).

### `i18n.py` — carregador de traduções

Lê `locales/pt.json` e `locales/en.json` em `_RAW` no import do módulo. Expõe:
- `TEXTS[lang][key]` — todas as strings de UI (tudo no JSON exceto a chave `"check"`).
- `CHECK_MESSAGES[key][lang]` — mensagens de `check_file`, vindas da subchave `"check"` de cada JSON.
- `DEFAULT_LANG = "pt"`, `SUPPORTED_LANGS = ["pt", "en"]`.

Para adicionar um novo idioma: criar `locales/<lang>.json` com as mesmas chaves de `pt.json` (incluindo o bloco `"check"`), adicionar `<lang>` a `SUPPORTED_LANGS` em `i18n.py`, e adicionar a entrada em `LANG_OPTIONS` em `qc_avaatech.py` (essa duplicação de "idiomas suportados" entre dois arquivos é uma dívida técnica conhecida — `TODO.md` item 4.5). **Não há validação automática de que os JSONs têm as mesmas chaves** — `TODO.md` item 7.3.

### `locales/pt.json` / `locales/en.json`

JSON plano de string→string (+ um array `plot_qf_labels` e um objeto `"check"` aninhado com os templates de `check_file`). PT é a fonte de verdade/idioma padrão; ao adicionar uma string nova na UI, adicionar a chave nos **dois** arquivos.

### `report_pdf.py`

Módulo de geração de relatório PDF — criado em 2026-06-28, ainda **parcial** (ver `TODO.md` item 8.1 para o que falta: capa, páginas de gráfico, integração com `qc_avaatech.py`, agrupamento por testemunho). Sem dependência de Streamlit, igual a `qc_core.py`. Hoje contém:
- `detect_intervals(rep0, min_gap=20, depth_col=DEPTH_COL)` — agrupa medidas consecutivas com `QF >= 2` (inclui `QF_INDETERMINATE`) em intervalos de profundidade contíguos, tolerando gaps de até `min_gap` mm entre pontos do mesmo cluster. Cada intervalo retorna `depth_start`/`depth_end`/`n_points`/`qf_max`/`causes` (set de códigos `CAUSE_*`, lidos de `rep0["QF_Causes"]`) e `has_pointwise_flag` (`True` se alguma medida do intervalo veio de `qc_core.is_pointwise_flag` — flag por critério pontual, não pelo QI agregado). **Importante (desde 2026-06-28):** a ordenação e a decisão de gap usam **sempre** `qc_core.DEPTH_COL` (contínua/monotônica) — nunca `depth_col` —, porque `CORE_DEPTH_COL` reinicia a cada seção do testemunho e misturaria/mascararia transições de seção se usado para essa decisão; `depth_col` só define os valores `depth_start`/`depth_end` exibidos. Limitação conhecida: num intervalo que cruze uma transição de seção, `depth_end` pode aparecer menor que `depth_start` quando `depth_col=CORE_DEPTH_COL` (puramente cosmético — não afeta a contagem/causas dos intervalos, validado contra o arquivo de exemplo).
- `build_problem_intervals_page(intervals, T, depth_col=DEPTH_COL)` — renderiza esses intervalos como uma página matplotlib (tabela), em vez de listar linha a linha; traduz QF (via `QF_PLOT_ORDER`/`T["plot_qf_labels"]`) e causas (via `qc_core.format_causes`) usando o dicionário de idioma `T` passado. Cabeçalhos de profundidade (`T["report_intervals_depth_start"/"_end"]`) são templates com `{label}`, preenchidos com o nome técnico curto da coluna (`CompositeDepth`/`CoreDepth`) via `_DEPTH_COL_SHORT_NAMES`. Intervalos com `has_pointwise_flag=True` recebem um ícone "⚠" junto ao QF máximo, e a página ganha uma nota de rodapé (`T["pdf_pointwise_footnote"]`) explicando o porquê — só aparece se houver pelo menos um intervalo marcado.

### `iniciar.py`

Launcher multiplataforma. Detecta SO via `platform.system()`, localiza o Python do `.venv` (`Scripts/python.exe` no Windows, `bin/python` no Linux) e executa `python -m streamlit run qc_avaatech.py`. Faz fallback para `sys.executable` se o `.venv` não existir. Substituiu o antigo `iniciar.bat` (Windows-only, removido).

### `setup_shortcut.py`

Cria atalho de desktop, com lógica por SO em `main()`:
- **Windows**: gera `assets/lamplus_logo.ico` a partir do `.png` (Pillow) e cria `LAM+ Core QC.lnk` no Desktop via `pywin32` (`win32com.client`), apontando para o Python do venv com `iniciar.py` como argumento.
- **Linux**: cria um `.desktop` (usa o `.png` direto, sem precisar de `.ico`) em `~/.local/share/applications/` e replica em `~/Desktop/`, com permissão de execução.

Roda só quando o usuário pede explicitamente — **não execute este script automaticamente**, pois ele cria/altera arquivos fora do repositório (Desktop do usuário). Sempre confirme antes de rodar de fato (já houve confirmação explícita pedida em sessões anteriores).

### `installer/` — empacotamento como executável standalone (PyInstaller)

Criado em 2026-06-29 para distribuir o app sem exigir Python/`.venv` na máquina de destino. `qc_avaatech.py` é um script Streamlit (roda via `streamlit run`, não como script Python comum), então o entry point do PyInstaller não pode ser ele direto:

- `launcher.py` — entry point real. Invoca `streamlit.web.cli` programaticamente, apontando para a cópia de `qc_avaatech.py` empacotada (resolve o caminho via `sys._MEIPASS` quando "frozen"). Desliga o file watcher do Streamlit (`--server.fileWatcherType=none`) — não há "arquivo-fonte" a vigiar num executável congelado, e o watcher tem uma race condition conhecida que aparece em alguns ambientes.
- `lamplus_qc.spec` — como o launcher nunca importa `qc_avaatech.py`/`qc_core.py` diretamente (só manda o Streamlit rodar o arquivo por caminho), a análise estática do PyInstaller não vê os imports desses módulos (pandas, numpy, sklearn, scipy, matplotlib, openpyxl, PIL) — por isso ficam em `hiddenimports`, e `collect_all()` traz datas/binaries/hiddenimports de `streamlit`/`scipy`/`sklearn`/`matplotlib` (libs com submódulos/assets carregados dinamicamente). Copia `qc_avaatech.py`, `qc_core.py`, `report_pdf.py`, `i18n.py`, `locales/` e `assets/` como dados brutos, espelhando a estrutura relativa do repo — por isso os caminhos baseados em `__file__` em `qc_avaatech.py`/`i18n.py` funcionam sem nenhuma alteração no código da aplicação. Ícone: `assets/lamplus_logo.ico`. Também localiza e inclui (via `sys.base_prefix`) DLLs nativas que instalações conda/miniforge no Windows guardam em `Library/bin/` em vez de `DLLs/` (`ffi-8.dll`, tcl/tk, sqlite3, bz2, expat) — sem isso o executável falha em runtime com `DLL load failed... _ctypes`; em Python "oficial" (python.org) esse bloco não encontra nada e não tem efeito.
- `build_exe.py` — detecta SO, usa o Python do `.venv`, roda `python -m PyInstaller installer/lamplus_qc.spec` com os parâmetros corretos (`--distpath`/`--workpath` dentro de `installer/`).
- `README_BUILD.md` — instruções de build Windows/Ubuntu e avisos conhecidos.

**Validado de ponta a ponta no Windows em 2026-06-29:** build completo executado (executável onefile, ~150MB em `installer/dist/LAM_Core_QC.exe`), executável rodado de fato — servidor Streamlit sobe e responde HTTP 200 em `localhost:8501`, sem erros no log. **Não testado no Ubuntu ainda** (sem ambiente disponível na sessão em que foi criado) — PyInstaller não faz cross-build, então cada plataforma precisa gerar seu próprio executável rodando `build_exe.py` localmente.

**O `.exe` gerado nunca é commitado no repositório** — `installer/dist/` e `installer/build/` estão no `.gitignore` (junto com `*.exe` e `*.spec.bak`, mais genéricos). Distribuição do executável é via **GitHub Releases** (anexar o binário gerado a um release), não via git.

## Convenções adotadas

- **Comentários, docstrings e mensagens de commit em Português**; identificadores de código (nomes de função/variável) em inglês. Strings de UI vivem nos `locales/*.json`, nunca hardcoded em `.py`.
- **PT é o idioma padrão** em toda a aplicação (`DEFAULT_LANG = "pt"` em `i18n.py`); EN é a alternativa via seletor na sidebar.
- Nomes de colunas do DataFrame seguem exatamente os nomes exportados pelo instrumento Avaatech (ex. `"CompositeDepth (mm)"`, `"Rh-La Area"`) — não renomear essas colunas, pois `qc_core.py` depende dos literais exatos.
- `qc_core.py` não importa Streamlit nem nada de UI — deve continuar sendo uma lib pura, testável/usável fora do app (`from qc_core import check_file, run_qc`).
- Mensagens de erro/warning de `check_file` são templates com `.format(**kwargs)` (`{cols}`, `{n}`, `{col}`, `{els}`) — ao adicionar uma nova checagem, seguir esse padrão (chave em `CHECK_MESSAGES`, função `msg(key, **kwargs)`).
- Sempre usar o `.venv` do projeto para rodar/instalar — nunca Python global. No Windows, o interpretador é `.venv/Scripts/python.exe`; no Linux, `.venv/bin/python`.
- `pywin32` no `requirements.txt` tem marcador de ambiente (`; sys_platform == "win32"`) para não quebrar `pip install` no Ubuntu — manter esse padrão para qualquer dependência específica de SO.
- Scripts utilitários (`iniciar.py`, `setup_shortcut.py`) detectam o SO via `platform.system()` e devem continuar funcionando em Windows **e** Ubuntu — qualquer mudança neles precisa considerar as duas plataformas.
- Antes de declarar algo "corrigido" ou "implementado", valide executando contra `data/exemplo_dados_consolidados.xlsx` (dados reais, já revelou bugs que dados sintéticos não revelariam — ver `TODO.md` achado C1).
- `TODO.md` é o registro vivo de bugs/gaps conhecidos e não corrigidos — consulte antes de assumir que algo é um problema novo, e atualize/remova entradas lá quando corrigidas.
- **Nunca versionar o executável gerado** (`installer/dist/*.exe` ou equivalente Linux) — fica de fora do git via `.gitignore`. Distribuição é via **GitHub Releases**, anexando o binário ao release, não via commit.

## Permissões automáticas (.venv e arquivos do projeto)

Sempre permitido sem necessidade de confirmação adicional:
- Executar comandos via o Python do `.venv` do projeto (`.venv/Scripts/python.exe` no Windows, `.venv/bin/python` no Linux), incluindo `-c`, `-m py_compile`, `-m pip install -r requirements.txt`, e execução de scripts do repositório (`iniciar.py`, `setup_shortcut.py`, etc.).
- `pip install`/atualização de dependências, mas **somente dentro do `.venv`** — nunca instalar pacotes globalmente.
- Ler, criar e modificar arquivos dentro deste repositório.

Restrições (pedir confirmação antes):
- Não modificar arquivos fora da pasta do repositório.
- Ações que escrevem fora do repo mesmo que disparadas por script do projeto — ex. `setup_shortcut.py` cria um atalho no Desktop do usuário (Windows) ou em `~/.local/share/applications`/`~/Desktop` (Linux): **sempre confirmar com o usuário antes de executar esse script de fato**, mesmo que o código já esteja pronto/testado.
- Não instalar pacotes globalmente; não usar `--no-verify`/pular hooks; não fazer `git push --force` ou operações destrutivas de git sem pedido explícito.

## Limitações e bugs conhecidos (resumo — detalhes em `TODO.md`)

1. ~~QC5 (réplicas) não funciona com o arquivo de exemplo real~~ — **corrigido em 2026-06-28** (achado C1): casamento agora usa `REPLICATE_KEY_COLS = ["Spectrum", "CoreDepth"]` em vez de `DEPTH_COL`.
2. ~~Linhas com dado faltante podiam receber `QF=0` (OK)~~ — **corrigido em 2026-06-28** (achado C2): novo `QF_INDETERMINATE=9` sempre atribuído a linhas com `CRITICAL_INPUT_COLS` faltante; checkbox `strict_missing_data` na sidebar controla só o cálculo do `QI` dessas linhas (NaN vs. best-effort), nunca a detecção/flag.
3. ~~QC6 (PCA) quebrava sem mensagem amigável~~ — **corrigido em 2026-06-28**: degrada graciosamente (score neutro + warning bilíngue) em vez de travar.
4. ~~QC4 (rolling) calculava deltas para 3 variáveis mas só usava 1 no score/flag final~~ — **corrigido em 2026-06-28**: por padrão considera só Rh-Lα-Inc (dado espectral real); combinar as três (`combine_rolling_vars=True`) é opt-in; README atualizado.
5. Sem testes automatizados; sem cache Streamlit (`st.cache_data`) — todo rerun da UI reprocessa o arquivo inteiro.

Esses itens **não devem ser corrigidos silenciosamente** numa tarefa não relacionada — se notar um deles enquanto trabalha em outra coisa, mencione mas não corrija de surpresa, a menos que o pedido do usuário seja justamente essa correção.
