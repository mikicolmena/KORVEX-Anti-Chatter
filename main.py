#!/usr/bin/env python3
"""Punto de entrada de KORVEX Anti-Chatter."""

import sys

try:
    from PyQt6 import QtWidgets
except ImportError:
    QtWidgets = None

if QtWidgets is None:
    sys.stderr.write(
        "Falta PyQt6 / PyQt6 is missing.\n"
        "  Linux:   sudo apt install python3-pyqt6 python3-evdev\n"
        "  Windows: pip install PyQt6\n")
    sys.exit(1)

from korvex.app import main

if __name__ == "__main__":
    sys.exit(main())
