"""Selección del backend de teclado según la plataforma."""

import platform

from ..i18n import tr


class BackendError(Exception):
    """Error al iniciar el backend, con un mensaje listo para el usuario."""


def get_backend_class():
    system = platform.system()
    if system == "Linux":
        try:
            from .linux_evdev import LinuxBackend
        except ImportError as e:
            raise BackendError(tr("err_missing_evdev")) from e
        return LinuxBackend
    if system == "Windows":
        from .windows_hook import WindowsBackend
        return WindowsBackend
    raise BackendError(tr("err_unsupported"))
