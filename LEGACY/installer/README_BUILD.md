# Gerando o executável — LAM+ Core QC

Este diretório empacota o app Streamlit (`qc_avaatech.py`) como um executável
standalone via [PyInstaller](https://pyinstaller.org/), para distribuir sem
exigir Python/`.venv` instalado na máquina de destino.

## Arquivos

- `launcher.py` — ponto de entrada real do executável. `qc_avaatech.py` é um
  script Streamlit (roda via `streamlit run`, não como script Python comum),
  então não pode ser o entry point do PyInstaller diretamente — o launcher
  invoca o CLI do Streamlit programaticamente (`streamlit.web.cli`), apontando
  para a cópia de `qc_avaatech.py` empacotada dentro do executável.
- `lamplus_qc.spec` — spec file do PyInstaller. Resolve a particularidade de
  empacotar Streamlit: como o launcher nunca importa `qc_avaatech.py`/
  `qc_core.py` diretamente (só manda o Streamlit rodar o arquivo por
  caminho), a análise estática do PyInstaller não vê os imports desses
  módulos (pandas, numpy, sklearn, scipy, matplotlib, openpyxl, PIL) — por
  isso o `.spec` lista isso manualmente em `hiddenimports`, e usa
  `collect_all()` para `streamlit`/`scipy`/`sklearn`/`matplotlib` (essas
  libs têm assets/submódulos carregados dinamicamente que a análise
  estática sozinha não pega).
- `build_exe.py` — roda o PyInstaller com os parâmetros corretos (usa o
  Python do `.venv` do projeto, gera `dist/`/`build/` dentro de `installer/`).

## Por que `locales/`, `assets/` e os `.py` do projeto são copiados como dados brutos

O `.spec` copia `qc_avaatech.py`, `qc_core.py`, `report_pdf.py`, `i18n.py`,
`locales/` e `assets/` para a **raiz** do diretório temporário onde o
PyInstaller extrai o bundle em tempo de execução (`sys._MEIPASS`) —
espelhando exatamente a estrutura relativa que esses arquivos têm no
repositório. Isso importa porque `qc_avaatech.py` (`BASE_DIR`/`LOGO_PNG`) e
`i18n.py` (`LOCALES_DIR`) resolvem caminhos via `__file__`, e funcionam sem
nenhuma modificação no código da aplicação **desde que essa estrutura
relativa não seja alterada** no `.spec` (não troque os mapeamentos `"."` /
`"locales"` / `"assets"` sem entender por que estão assim).

## Build no Windows

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe installer\build_exe.py
```

Executável gerado em `installer\dist\LAM_Core_QC.exe` (arquivo único — o `.spec` empacota tudo em modo onefile, sem pasta intermediária).

## Build no Ubuntu

```bash
.venv/bin/python -m pip install pyinstaller
.venv/bin/python installer/build_exe.py
```

Executável gerado em `installer/dist/LAM_Core_QC` (arquivo único — o `.spec` empacota tudo em modo onefile, sem pasta intermediária).

> **PyInstaller não faz cross-build.** Rodar o build no Windows gera um
> `.exe` para Windows; rodar no Ubuntu gera um binário ELF para Linux. Para
> distribuir nas duas plataformas, rode `build_exe.py` em cada uma.

## Avisos e limitações conhecidas

- **Build é pesado e lento.** `scipy`/`scikit-learn`/`streamlit` têm muitas
  dependências binárias; a primeira execução do `build_exe.py` pode levar
  vários minutos e o executável final tende a ficar grande (centenas de MB).
- **`pyinstaller` não é dependência de runtime.** Está comentado em
  `requirements.txt` de propósito — só precisa estar instalado na máquina
  que *gera* o executável, nunca na máquina que só *executa* o app via
  `streamlit run qc_avaatech.py` ou `iniciar.py`.
- **Testado de ponta a ponta no Windows (2026-06-29):** build completo via
  `build_exe.py`, executável gerado (~150MB) e executado de fato — servidor
  Streamlit sobe corretamente e responde HTTP 200 em `localhost:8501`, sem
  erros no log. Não testado ainda no Ubuntu nesta sessão (sem ambiente
  disponível) — o `.spec`/`build_exe.py` foram escritos para funcionar nas
  duas plataformas, mas vale validar lá antes de distribuir.
- **DLLs nativas em Python via conda/miniforge:** se o `.venv` foi criado a
  partir de uma instalação conda/miniforge no Windows, `_ctypes` falha em
  runtime (`DLL load failed... ffi-8.dll`) porque algumas DLLs nativas
  (`libffi`, `tcl`/`tk`, `sqlite3`, `bz2`, `expat`) ficam em
  `<python>/Library/bin/` em vez de `DLLs/`, onde o PyInstaller procura por
  padrão. O `.spec` já localiza e inclui essas DLLs automaticamente via
  `sys.base_prefix` — em Python "oficial" (python.org) esse bloco não
  encontra nada e não tem efeito.
- Se o executável gerado falhar ao abrir com `ModuleNotFoundError`,
  normalmente o conserto é adicionar o módulo faltante a `hiddenimports` no
  `.spec` e rodar `build_exe.py` novamente.
- **Antivírus/SmartScreen no Windows** podem alertar sobre o `.exe` gerado
  (comum com executáveis PyInstaller não assinados) — não é necessariamente
  um problema real, mas pode exigir liberação manual ao distribuir.
