"""
LAM+ Core QC — setup_shortcut.py
Generates the app icon and creates a desktop shortcut for iniciar.py,
automatically detecting the operating system (Windows or Ubuntu/Linux).

Usage:
    python setup_shortcut.py
"""

import os
import platform
import stat
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOGO_PNG = os.path.join(BASE_DIR, "assets", "lamplus_logo.png")
LOGO_ICO = os.path.join(BASE_DIR, "assets", "lamplus_logo.ico")
TARGET_SCRIPT = os.path.join(BASE_DIR, "iniciar.py")
SHORTCUT_NAME = "LAM+ Core QC"
APP_DESCRIPTION = "LAM+ Core QC — Avaatech XRF Core Scanner"

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def convert_logo_to_ico():
    """Converts assets/lamplus_logo.png into assets/lamplus_logo.ico (used on Windows)."""
    from PIL import Image

    if not os.path.isfile(LOGO_PNG):
        raise FileNotFoundError(f"Logo not found: {LOGO_PNG}")

    img = Image.open(LOGO_PNG).convert("RGBA")
    img.save(LOGO_ICO, format="ICO", sizes=ICO_SIZES)
    print(f"Icon generated: {LOGO_ICO}")


def find_venv_python_windows():
    candidate = os.path.join(BASE_DIR, ".venv", "Scripts", "python.exe")
    return candidate if os.path.isfile(candidate) else "python.exe"


def find_venv_python_linux():
    candidate = os.path.join(BASE_DIR, ".venv", "bin", "python")
    return candidate if os.path.isfile(candidate) else "python3"


# ============================================================
# WINDOWS
# ============================================================

def create_shortcut_windows():
    """Creates a .lnk shortcut on the desktop, pointing to iniciar.py via pywin32."""
    try:
        import win32com.client
    except ImportError:
        print(
            "pywin32 is not installed — cannot create the .lnk shortcut on "
            "Windows.\n"
            "Install the dependency (already listed in requirements.txt) and "
            "try again:\n\n"
            "    .venv\\Scripts\\pip install pywin32\n"
        )
        sys.exit(1)

    if not os.path.isfile(TARGET_SCRIPT):
        raise FileNotFoundError(f"Startup script not found: {TARGET_SCRIPT}")
    if not os.path.isfile(LOGO_ICO):
        raise FileNotFoundError(f"Icon not found: {LOGO_ICO}")

    python_exe = find_venv_python_windows()

    shell = win32com.client.Dispatch("WScript.Shell")
    desktop = shell.SpecialFolders("Desktop")
    shortcut_path = os.path.join(desktop, f"{SHORTCUT_NAME}.lnk")

    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = python_exe
    shortcut.Arguments = f'"{TARGET_SCRIPT}"'
    shortcut.WorkingDirectory = BASE_DIR
    shortcut.IconLocation = LOGO_ICO
    shortcut.Description = APP_DESCRIPTION
    shortcut.Save()

    print(f"Shortcut created: {shortcut_path}")


# ============================================================
# UBUNTU / LINUX
# ============================================================

def build_desktop_entry():
    python_exe = find_venv_python_linux()
    exec_cmd = f'"{python_exe}" "{TARGET_SCRIPT}"'

    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={SHORTCUT_NAME}\n"
        f"Comment={APP_DESCRIPTION}\n"
        f"Exec={exec_cmd}\n"
        f"Icon={LOGO_PNG}\n"
        f"Path={BASE_DIR}\n"
        "Terminal=true\n"
        "Categories=Science;\n"
    )


def _write_desktop_file(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    st = os.stat(path)
    os.chmod(path, st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def create_shortcut_linux():
    """Creates a .desktop entry in the applications menu and another on the user's Desktop."""
    if not os.path.isfile(TARGET_SCRIPT):
        raise FileNotFoundError(f"Startup script not found: {TARGET_SCRIPT}")
    if not os.path.isfile(LOGO_PNG):
        raise FileNotFoundError(f"Logo not found: {LOGO_PNG}")

    content = build_desktop_entry()
    filename = "lamplus-core-qc.desktop"

    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)
    apps_path = os.path.join(apps_dir, filename)
    _write_desktop_file(apps_path, content)
    print(f"Application shortcut created: {apps_path}")

    # Some distros use ~/Desktop, others ~/.local/Desktop — tries both,
    # in order, and uses the first one that already exists.
    for desktop_dir in (os.path.expanduser("~/Desktop"), os.path.expanduser("~/.local/Desktop")):
        if os.path.isdir(desktop_dir):
            desktop_path = os.path.join(desktop_dir, filename)
            _write_desktop_file(desktop_path, content)
            print(f"Desktop shortcut created: {desktop_path}")
            break
    else:
        print(
            "Desktop directory not found (~/Desktop or ~/.local/Desktop), "
            "skipping desktop shortcut."
        )


# ============================================================
# MAIN
# ============================================================

def main():
    system = platform.system()

    if system == "Windows":
        convert_logo_to_ico()
        create_shortcut_windows()
    elif system == "Linux":
        create_shortcut_linux()
    else:
        raise RuntimeError(f"Unsupported operating system: {system}")


if __name__ == "__main__":
    main()
