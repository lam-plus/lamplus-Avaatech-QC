# CLAUDE.md — LAM+ Core QC (Avaatech XRF Core Scanner)

Contexto para sessões do Claude Code neste repositório. Leia isto antes de propor mudanças — ele documenta o que o projeto faz, como os arquivos se conectam, e decisões/limitações já conhecidas.

## O que é este projeto

Pipeline de **Controle de Qualidade (QC)** para dados exportados pelo scanner de sedimentos por fluorescência de raios-X (XRF) **Avaatech**, desenvolvido no **LAM+** (Laboratório de Análise Multiespectral e IA para Sedimentos, UFF). O usuário faz upload de um `.xlsx` exportado pelo scanner; o app roda 6 módulos estatísticos de QC, calcula um **Quality Index (QI)** e um **Quality Flag (QF)** por medição, mostra gráficos de diagnóstico e permite baixar o resultado anotado em `.xlsx`.

Frontend é **Streamlit**. Não há backend/banco de dados — tudo roda local, em memória, por sessão.

## Estrutura de arquivos

```
qc_core.py              # Lógica pura do pipeline QC (sem Streamlit) — importável como lib
qc_avaatech.py          # Frontend Streamlit — único ponto de entrada da UI
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
requirements.txt        # Dependências Python (pywin32 só Windows via marker de ambiente)
README.md               # Overview do projeto (inglês, "público")
DEVELOPMENT.md          # Explicação do app + notas de decisões datadas (ex. i18n)
INSTALL.md              # Guia de instalação para Ubuntu
TODO.md                 # Levantamento de bugs/gaps encontrados em auditoria (2026-06-28) — ver antes de "corrigir" algo, pode já estar documentado lá
.venv/                  # Ambiente virtual local (gitignored) — SEMPRE use este venv, nunca o Python global
```

Não existem testes automatizados (`tests/`) nem CI configurado neste repositório — ver `TODO.md` item 6.4.

## Descrição de cada módulo

### `qc_core.py` — pipeline de QC (sem dependência de UI)

Importa `CHECK_MESSAGES` de `i18n.py` para mensagens bilíngues de validação. Constantes de configuração no topo do arquivo: `DEPTH_COL = "CompositeDepth (mm)"`, `REPLICATE_COL = "Replicate Nr Count"`, `ROLLING_WINDOW = 5`, `REQUIRED_COLUMNS`, `ELEMENTS_PCA`, `ELEMENTS_REPLICATES`.

Funções estatísticas de base:
- `robust_zscore(x)` — z-score robusto via MAD (mediana de desvios absolutos).
- `score_from_z(z)` — converte z-score em score 0–100.
- `calculate_rpd(values)` — Relative Percent Difference entre réplicas.

Validação:
- `check_file(df, lang="pt")` — valida estrutura do DataFrame **antes** de rodar o pipeline. Retorna `(errors, warnings)`. `errors` não-vazio bloqueia execução no frontend; `warnings` só avisa. Mensagens vêm de `CHECK_MESSAGES[key][lang]` (i18n.py), com templates `.format(**kwargs)`.

Módulos QC individuais (cada um recebe/retorna um DataFrame `rep0`, o subconjunto filtrado para `Replicate Nr Count == "Rep0"`):
- `qc_throughput` (QC1), `qc_rh_la` (QC2), `qc_rh_la_inc` (QC3) — z-score robusto pontual.
- `qc_rolling` (QC4) — média móvel (`ROLLING_WINDOW`) + delta + z-score do delta, para `Throughput`, `Rh-La Area` e `Rh-La-Inc Area`. **Nota:** atualmente só a coluna `Rh-La-Inc Area_delta_z` é usada em `compute_scores`/`compute_flags` — as outras duas são calculadas mas não usadas no score final (ver `TODO.md` item 4.1, diverge do que o README documenta).
- `qc_replicates` (QC5) — casa réplicas por igualdade exata de `DEPTH_COL` e calcula RPD médio. **Atenção:** com o arquivo de exemplo real (`data/exemplo_dados_consolidados.xlsx`), esse casamento falha para 100% das linhas porque réplicas `Rep1`/`Rep2` têm `CompositeDepth (mm)` nulo — `Mean_RPD` fica `NaN` e é tratado como nota 100 (perfeita) em `compute_scores`. **Bug crítico conhecido, documentado em `TODO.md` achado C1.**
- `qc_pca` (QC6) — PCA (2 componentes) sobre `ELEMENTS_PCA` presentes + distância de Mahalanobis. Quebra se houver menos de 2 linhas ou menos de 2 colunas PCA disponíveis (sem tratamento de erro amigável — `TODO.md` item 1.2/2.2).

Agregação:
- `compute_scores(rep0)` — combina os scores individuais em `QI` (pesos fixos: 0.25/0.15/0.20/0.20/0.15/0.05) e calcula percentis 95/99 de Mahalanobis.
- `compute_flags(rep0, p95, p99)` — atribui `QF` (0=OK, 1=Atenção, 2=Suspeito, 3=Rejeitado) via loop `iterrows()` (não vetorizado — `TODO.md` item 5.1). **Atenção:** comparações com `NaN` em Python retornam `False`, então uma linha com dado crítico faltante pode acabar com `QF=0` em vez de ser flagrada — **bug crítico conhecido, `TODO.md` achado C2.**
- `run_qc(df)` — orquestra o pipeline completo, retorna `(rep0, p95, p99, pca_elements)`.

### `qc_avaatech.py` — frontend Streamlit

Único arquivo de UI. Importa de `qc_core` (`DEPTH_COL`, `check_file`, `run_qc`) e de `i18n` (`TEXTS`, `DEFAULT_LANG`). Estrutura:
- Funções `plot_*(rep0, T)` — uma por aba de diagnóstico (Throughput, Rh-Lα/Rh-Lα-Inc, Rolling, Réplicas, PCA, QI/QF). Recebem o dicionário de traduções `T` para textos/labels.
- `to_excel_bytes(df)` — serializa o resultado para download.
- Corpo principal roda no nível de módulo (padrão Streamlit): `st.set_page_config` → seletor de idioma na sidebar (`LANG_OPTIONS` hardcoded, ver nota i18n abaixo) → upload → `check_file` → `run_qc` → resumo em métricas → 6 abas de gráficos → tabela completa (`st.dataframe`, com nomes de coluna originais do instrumento, não traduzidos) → botão de download.
- **Não há `@st.cache_data`** em `check_file`/`run_qc` — toda interação na UI (incluindo trocar o idioma) reexecuta o pipeline inteiro do zero (`TODO.md` item 5.4).

### `i18n.py` — carregador de traduções

Lê `locales/pt.json` e `locales/en.json` em `_RAW` no import do módulo. Expõe:
- `TEXTS[lang][key]` — todas as strings de UI (tudo no JSON exceto a chave `"check"`).
- `CHECK_MESSAGES[key][lang]` — mensagens de `check_file`, vindas da subchave `"check"` de cada JSON.
- `DEFAULT_LANG = "pt"`, `SUPPORTED_LANGS = ["pt", "en"]`.

Para adicionar um novo idioma: criar `locales/<lang>.json` com as mesmas chaves de `pt.json` (incluindo o bloco `"check"`), adicionar `<lang>` a `SUPPORTED_LANGS` em `i18n.py`, e adicionar a entrada em `LANG_OPTIONS` em `qc_avaatech.py` (essa duplicação de "idiomas suportados" entre dois arquivos é uma dívida técnica conhecida — `TODO.md` item 4.5). **Não há validação automática de que os JSONs têm as mesmas chaves** — `TODO.md` item 7.3.

### `locales/pt.json` / `locales/en.json`

JSON plano de string→string (+ um array `plot_qf_labels` e um objeto `"check"` aninhado com os templates de `check_file`). PT é a fonte de verdade/idioma padrão; ao adicionar uma string nova na UI, adicionar a chave nos **dois** arquivos.

### `iniciar.py`

Launcher multiplataforma. Detecta SO via `platform.system()`, localiza o Python do `.venv` (`Scripts/python.exe` no Windows, `bin/python` no Linux) e executa `python -m streamlit run qc_avaatech.py`. Faz fallback para `sys.executable` se o `.venv` não existir. Substituiu o antigo `iniciar.bat` (Windows-only, removido).

### `setup_shortcut.py`

Cria atalho de desktop, com lógica por SO em `main()`:
- **Windows**: gera `assets/lamplus_logo.ico` a partir do `.png` (Pillow) e cria `LAM+ Core QC.lnk` no Desktop via `pywin32` (`win32com.client`), apontando para o Python do venv com `iniciar.py` como argumento.
- **Linux**: cria um `.desktop` (usa o `.png` direto, sem precisar de `.ico`) em `~/.local/share/applications/` e replica em `~/Desktop/`, com permissão de execução.

Roda só quando o usuário pede explicitamente — **não execute este script automaticamente**, pois ele cria/altera arquivos fora do repositório (Desktop do usuário). Sempre confirme antes de rodar de fato (já houve confirmação explícita pedida em sessões anteriores).

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

1. **QC5 (réplicas) não funciona com o arquivo de exemplo real** — casamento por profundidade exata falha; `Mean_RPD` vira `NaN` e é silenciosamente tratado como nota perfeita.
2. **Linhas com dado faltante podem receber `QF=0` (OK)** por causa da semântica de comparação com `NaN`.
3. QC6 (PCA) quebra sem mensagem amigável se houver poucas linhas ou nenhum elemento PCA disponível.
4. QC4 (rolling) calcula deltas para 3 variáveis mas só usa 1 no score/flag final — diverge do que o `README.md` documenta.
5. Sem testes automatizados; sem cache Streamlit (`st.cache_data`) — todo rerun da UI reprocessa o arquivo inteiro.

Esses itens **não devem ser corrigidos silenciosamente** numa tarefa não relacionada — se notar um deles enquanto trabalha em outra coisa, mencione mas não corrija de surpresa, a menos que o pedido do usuário seja justamente essa correção.
