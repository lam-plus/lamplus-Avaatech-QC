"""
LAM+ Core QC — installer/launcher.py
Ponto de entrada real do executável gerado pelo PyInstaller.

qc_avaatech.py é um script Streamlit — não pode ser o entry point do
PyInstaller diretamente, porque precisa rodar dentro do servidor do
Streamlit (`streamlit run`), não como um script Python comum. Este launcher
invoca o CLI do Streamlit programaticamente, apontando para a cópia de
qc_avaatech.py empacotada como dado bruto (ver lamplus_qc.spec) — por isso
os imports de qc_avaatech.py/qc_core.py (pandas, numpy, sklearn, etc.) não
aparecem aqui: a análise estática do PyInstaller não os veria de qualquer
forma, daí HIDDEN_IMPORTS no .spec.
"""

import os
import sys

from streamlit.web import cli as stcli


def _resolve_app_path():
    """Caminho de qc_avaatech.py dentro do bundle (frozen) ou do repo (dev)."""
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(base_dir, "qc_avaatech.py")
    if os.path.isfile(candidate):
        return candidate
    # Fallback para execução não-empacotada (python installer/launcher.py),
    # útil para testar o launcher sem gerar o executável.
    return os.path.join(os.path.dirname(base_dir), "qc_avaatech.py")


def main():
    app_path = _resolve_app_path()
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.headless=false",
        # Sem hot-reload: não há "arquivo-fonte" a vigiar num executável
        # congelado, e o watcher do Streamlit tem uma race condition
        # conhecida (RuntimeError: dictionary changed size during
        # iteration) que aparece em alguns ambientes — desligar evita o erro
        # e é a escolha certa para um build de produção de qualquer forma.
        "--server.fileWatcherType=none",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
