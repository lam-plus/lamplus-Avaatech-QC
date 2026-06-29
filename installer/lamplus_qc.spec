# -*- mode: python ; coding: utf-8 -*-
"""
LAM+ Core QC — lamplus_qc.spec
Spec file do PyInstaller para empacotar o app Streamlit como executável.

Uso (via PyInstaller direto):
    pyinstaller installer/lamplus_qc.spec --noconfirm

Uso recomendado (via build_exe.py, que chama isto internamente):
    python installer/build_exe.py

Particularidade de empacotar Streamlit: o "ponto de entrada" real do app
(launcher.py, abaixo) não importa qc_avaatech.py diretamente — ele manda o
Streamlit CLI (`stcli.main()`) rodar o arquivo pelo caminho. Isso significa
que a análise estática do PyInstaller NUNCA vê os imports de qc_avaatech.py/
qc_core.py/report_pdf.py (numpy, pandas, sklearn, scipy, matplotlib,
openpyxl, PIL) — por isso eles precisam ser listados manualmente em
HIDDEN_IMPORTS abaixo, e os próprios arquivos .py do projeto precisam ser
copiados como dados brutos (DATAS), não "compilados para dentro" do bundle.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all

block_cipher = None

# ============================================================
# CAMINHOS
# ============================================================

# Diretório do projeto (pai de installer/) — este .spec é executado com cwd
# variável dependendo de como o PyInstaller é chamado, então resolvemos a
# partir do próprio arquivo .spec.
INSTALLER_DIR = os.path.dirname(os.path.abspath(SPEC))
PROJECT_DIR = os.path.dirname(INSTALLER_DIR)

LAUNCHER_SCRIPT = os.path.join(INSTALLER_DIR, "launcher.py")
ICON_PATH = os.path.join(PROJECT_DIR, "assets", "lamplus_logo.ico")

# ============================================================
# DEPENDÊNCIAS COM ASSETS/IMPORTS DINÂMICOS
# ============================================================
# collect_all() traz datas + binaries + hiddenimports de uma vez — é o jeito
# robusto de empacotar libs que carregam submódulos dinamicamente (scipy/
# sklearn) ou que têm seus próprios assets estáticos (o frontend já
# compilado do Streamlit, em streamlit/static/).

datas = []
binaries = []
hiddenimports = []

for pkg in ["streamlit", "scipy", "sklearn", "matplotlib"]:
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

# Módulos importados só dentro de qc_avaatech.py/qc_core.py/report_pdf.py —
# invisíveis para a análise estática do PyInstaller porque esses arquivos
# são copiados como DATAS (ver abaixo), nunca importados pelo launcher.
hiddenimports += [
    "pandas",
    "numpy",
    "openpyxl",
    "PIL",
    "PIL.Image",
]

# ============================================================
# DLLs NATIVAS NÃO RESOLVIDAS AUTOMATICAMENTE (Python via conda/miniforge)
# ============================================================
# Em instalações conda/miniforge no Windows, algumas DLLs nativas (libffi,
# tcl/tk, sqlite3, bz2, expat) ficam em <python>/Library/bin/ em vez de
# DLLs/ (onde o detector de dependências do PyInstaller procura por padrão).
# Sem isso, o executável falha em runtime com "DLL load failed while
# importing _ctypes" (libffi é dependência de _ctypes, usado por matplotlib/
# tkinter mesmo sem GUI). Em Python "oficial" (python.org), essas DLLs já
# ficam onde o PyInstaller espera e este bloco simplesmente não encontra
# nada para adicionar (sem efeito, sem quebrar o build).
_CONDA_LIB_BIN = os.path.join(sys.base_prefix, "Library", "bin")
_CONDA_DLLS = ["ffi-8.dll", "libbz2.dll", "libexpat.dll", "sqlite3.dll", "tcl86t.dll", "tk86t.dll"]
for _dll in _CONDA_DLLS:
    _dll_path = os.path.join(_CONDA_LIB_BIN, _dll)
    if os.path.isfile(_dll_path):
        binaries.append((_dll_path, "."))

# ============================================================
# ARQUIVOS DO PROJETO (copiados como dados brutos, não analisados)
# ============================================================

datas += [
    (os.path.join(PROJECT_DIR, "qc_avaatech.py"), "."),
    (os.path.join(PROJECT_DIR, "qc_core.py"), "."),
    (os.path.join(PROJECT_DIR, "report_pdf.py"), "."),
    (os.path.join(PROJECT_DIR, "i18n.py"), "."),
    (os.path.join(PROJECT_DIR, "locales"), "locales"),
    (os.path.join(PROJECT_DIR, "assets"), "assets"),
]

# ============================================================
# ANÁLISE / BUNDLE
# ============================================================

a = Analysis(
    [LAUNCHER_SCRIPT],
    pathex=[PROJECT_DIR, INSTALLER_DIR],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="LAM_Core_QC",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if os.path.isfile(ICON_PATH) else None,
)
