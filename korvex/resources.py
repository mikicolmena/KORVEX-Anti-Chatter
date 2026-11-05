"""Localización del logo (código fuente, PyInstaller y paquete .deb)."""

import os

_HERE = os.path.dirname(os.path.abspath(__file__))

_CANDIDATES = (
    os.path.join(_HERE, "assets", "korvex-antichatter.png"),        # 256 px, va con el paquete
    "/usr/share/icons/hicolor/256x256/apps/korvex-antichatter.png",
)


def logo_path():
    for candidate in _CANDIDATES:
        if os.path.exists(candidate):
            return candidate
    return None
