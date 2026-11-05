"""Registro de diagnóstico en un archivo pequeño y rotativo.

Por privacidad NUNCA se registra qué teclas se pulsan: solo el arranque, los
dispositivos capturados/liberados y los errores.

Ubicación:
  Linux:   $XDG_STATE_HOME/korvex-antichatter/korvex.log (~/.local/state/…)
  Windows: %LOCALAPPDATA%\\KorvexAntiChatter\\korvex.log
"""

import logging
import os
import platform
import sys
import threading
from logging.handlers import RotatingFileHandler

from . import __version__

_log_file = None


def log_dir():
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "KorvexAntiChatter")
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(base, "korvex-antichatter")


def log_file():
    return _log_file


def setup():
    global _log_file
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        os.makedirs(log_dir(), exist_ok=True)
        _log_file = os.path.join(log_dir(), "korvex.log")
        handler = RotatingFileHandler(_log_file, maxBytes=256 * 1024, backupCount=2, encoding="utf-8")
        handler.setFormatter(fmt)
        root.addHandler(handler)
    except OSError:
        _log_file = None
    if sys.stderr is not None:                       # en el .exe "windowed" no hay consola
        console = logging.StreamHandler()
        console.setFormatter(fmt)
        console.setLevel(logging.WARNING)
        root.addHandler(console)

    def excepthook(exc_type, exc, tb):
        logging.getLogger("korvex").critical("Excepción no controlada", exc_info=(exc_type, exc, tb))

    def thread_excepthook(args):
        logging.getLogger("korvex").critical("Excepción no controlada en el hilo %s", args.thread,
                                             exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook
    logging.getLogger("korvex").info("KORVEX Anti-Chatter %s en %s %s, Python %s",
                                     __version__, platform.system(), platform.release(),
                                     platform.python_version())
