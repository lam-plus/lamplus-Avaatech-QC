"""
LAM+ Core QC — installer/build_exe.py
Executa o PyInstaller com os parâmetros corretos para gerar o executável
a partir de lamplus_qc.spec. Funciona em Windows e Ubuntu (gera um binário
nativo da plataforma onde for executado — PyInstaller não faz cross-build).

Uso:
    python installer/build_exe.py

Pré-requisito: dependências instaladas no .venv do projeto, incluindo
pyinstaller (ver requirements.txt — `pip install pyinstaller`).
"""

import os
import platform
import subprocess
import sys

INSTALLER_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(INSTALLER_DIR)
SPEC_FILE = os.path.join(INSTALLER_DIR, "lamplus_qc.spec")


def find_venv_python():
    """Retorna o caminho do python do .venv para o SO atual, se existir."""
    if platform.system() == "Windows":
        candidate = os.path.join(PROJECT_DIR, ".venv", "Scripts", "python.exe")
    else:
        candidate = os.path.join(PROJECT_DIR, ".venv", "bin", "python")

    if os.path.isfile(candidate):
        return candidate
    return None


def check_pyinstaller(python_exe):
    result = subprocess.run(
        [python_exe, "-m", "PyInstaller", "--version"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print("ERRO: PyInstaller não encontrado no ambiente Python usado.")
        print("Instale com: pip install pyinstaller (ver requirements.txt)")
        sys.exit(1)
    print(f"PyInstaller {result.stdout.strip()} encontrado.")


def main():
    python_exe = find_venv_python() or sys.executable
    print(f"Usando Python: {python_exe} ({platform.system()})")

    check_pyinstaller(python_exe)

    cmd = [
        python_exe, "-m", "PyInstaller",
        SPEC_FILE,
        "--noconfirm",   # sobrescreve dist/ e build/ sem perguntar
        "--clean",       # limpa cache do PyInstaller antes de rodar
        "--distpath", os.path.join(INSTALLER_DIR, "dist"),
        "--workpath", os.path.join(INSTALLER_DIR, "build"),
    ]

    print("Executando:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=INSTALLER_DIR)

    if result.returncode != 0:
        print("Build falhou — ver mensagens de erro do PyInstaller acima.")
        sys.exit(result.returncode)

    exe_name = "LAM_Core_QC.exe" if platform.system() == "Windows" else "LAM_Core_QC"
    exe_path = os.path.join(INSTALLER_DIR, "dist", exe_name)
    print(f"\nBuild concluído. Executável em: {exe_path}")


if __name__ == "__main__":
    main()
