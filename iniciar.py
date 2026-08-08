"""
LAM+ Core QC — iniciar.py
Starts the Streamlit app (V2, src/qc_avaatech.py) using the streamlit
executable from the local .venv, on Windows or Ubuntu/Linux.

Usage:
    python iniciar.py
"""

import os
import platform
import shutil
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_FILE = os.path.join(BASE_DIR, "src", "qc_avaatech.py")


def find_venv_streamlit():
    """Returns the path to the .venv streamlit executable, if it exists."""
    if platform.system() == "Windows":
        candidate = os.path.join(BASE_DIR, ".venv", "Scripts", "streamlit.exe")
    else:
        candidate = os.path.join(BASE_DIR, ".venv", "bin", "streamlit")

    if os.path.isfile(candidate):
        return candidate
    return None


def find_streamlit_on_path():
    """Fallback: looks for a streamlit already installed on the system PATH."""
    return shutil.which("streamlit")


def main():
    if not os.path.isfile(APP_FILE):
        print(f"App file not found: {APP_FILE}")
        sys.exit(1)

    streamlit_exe = find_venv_streamlit() or find_streamlit_on_path()

    if streamlit_exe is None:
        print(
            "Could not find Streamlit.\n"
            "Check that the virtual environment (.venv) was created and the "
            "dependencies installed:\n\n"
            "    python -m venv .venv\n"
            "    .venv\\Scripts\\pip install -r requirements.txt   (Windows)\n"
            "    .venv/bin/pip install -r requirements.txt         (Linux)\n\n"
            "Or install Streamlit in the system Python:\n"
            "    pip install streamlit"
        )
        sys.exit(1)

    cmd = [streamlit_exe, "run", APP_FILE]
    print(f"Starting LAM+ Core QC ({platform.system()})...")
    print(" ".join(cmd))

    subprocess.run(cmd, cwd=BASE_DIR)


if __name__ == "__main__":
    main()
