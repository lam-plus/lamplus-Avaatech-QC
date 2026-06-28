"""
LAM+ Core QC — iniciar.py
Inicia o app Streamlit usando o Python do .venv local, em Windows ou Ubuntu/Linux.

Uso:
    python iniciar.py
"""

import os
import platform
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_FILE = os.path.join(BASE_DIR, "qc_avaatech.py")


def find_venv_python():
    """Retorna o caminho do python do .venv para o SO atual, se existir."""
    if platform.system() == "Windows":
        candidate = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    else:
        candidate = os.path.join(BASE_DIR, ".venv", "bin", "python")

    if os.path.isfile(candidate):
        return candidate
    return None


def main():
    python_exe = find_venv_python() or sys.executable

    cmd = [python_exe, "-m", "streamlit", "run", APP_FILE]
    print(f"Iniciando LAM+ Core QC ({platform.system()})...")
    print(" ".join(cmd))

    subprocess.run(cmd, cwd=BASE_DIR)


if __name__ == "__main__":
    main()
