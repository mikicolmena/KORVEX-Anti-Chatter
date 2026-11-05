"""Autoarranque con el sistema (Windows: registro Run, Linux: XDG autostart).

El estado real se lee siempre del sistema, no de la configuración guardada.
"""

import os
import platform
import shlex
import sys

from . import APP_ID, APP_NAME

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_LINUX_LAUNCHER = "/usr/bin/korvex-antichatter"


def _launch_args():
    if getattr(sys, "frozen", False):
        return [sys.executable]
    if platform.system() == "Linux" and os.path.exists(_LINUX_LAUNCHER) \
            and os.path.abspath(__file__).startswith("/usr/share/korvex-antichatter/"):
        return [_LINUX_LAUNCHER]
    main_py = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "main.py")
    return [sys.executable, main_py]


def _windows_command():
    return " ".join(f'"{a}"' for a in _launch_args())


def _linux_desktop_path():
    config = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(config, "autostart", f"{APP_ID}.desktop")


def is_enabled():
    system = platform.system()
    if system == "Windows":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
                winreg.QueryValueEx(key, APP_ID)
            return True
        except OSError:
            return False
    if system == "Linux":
        return os.path.exists(_linux_desktop_path())
    return False


def set_enabled(enable):
    """Activa o desactiva el autoarranque. Lanza OSError si falla."""
    system = platform.system()
    if system == "Windows":
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enable:
                winreg.SetValueEx(key, APP_ID, 0, winreg.REG_SZ, _windows_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_ID)
                except FileNotFoundError:
                    pass
    elif system == "Linux":
        path = _linux_desktop_path()
        if enable:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            exec_line = " ".join(shlex.quote(a) for a in _launch_args())
            with open(path, "w", encoding="utf-8") as f:
                f.write(
                    "[Desktop Entry]\n"
                    "Type=Application\n"
                    f"Name={APP_NAME}\n"
                    f"Comment={APP_NAME}\n"
                    f"Exec={exec_line}\n"
                    "Icon=korvex-antichatter\n"
                    "Terminal=false\n"
                    "X-GNOME-Autostart-enabled=true\n"
                )
        elif os.path.exists(path):
            os.remove(path)


def refresh():
    """Si está activado, reescribe la entrada para que apunte al ejecutable actual."""
    try:
        if is_enabled():
            set_enabled(True)
    except OSError:
        pass
