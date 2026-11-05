"""Arranque de la aplicación: instancia única, ventana y bandeja."""

import getpass
import logging
import os
import platform
import signal
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from . import APP_NAME, INSTANCE_SERVER, ORG_NAME, __version__, logs

log = logging.getLogger(__name__)

_WAKE = b"WAKE_UP"


def _server_name():
    # Un nombre por usuario: varios usuarios en la misma máquina no se bloquean entre sí.
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return f"{INSTANCE_SERVER}-{user}"


def _wake_existing_instance(name):
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(500):
        return False
    # En Wayland, el lanzador da un token de activación a ESTE proceso; se le pasa
    # a la instancia abierta para que el compositor le permita ponerse al frente.
    token = os.environ.get("XDG_ACTIVATION_TOKEN", "")
    sock.write(_WAKE + (b" " + token.encode() if token else b""))
    sock.waitForBytesWritten(500)
    sock.disconnectFromServer()
    return True


def _listen(name, on_wake):
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    if not server.listen(name):
        # Socket huérfano de una ejecución anterior que terminó mal
        # (ya sabemos que nadie responde en él).
        QLocalServer.removeServer(name)
        if not server.listen(name):
            log.warning("No se pudo crear el servidor de instancia única: %s", server.errorString())
            return None

    def on_data(sock):
        data = bytes(sock.readAll())
        if data.startswith(_WAKE):
            token = data[len(_WAKE):].strip().decode(errors="ignore")
            if token:
                os.environ["XDG_ACTIVATION_TOKEN"] = token   # Qt (Wayland) lo usa al activar
            on_wake()

    def on_connection():
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: on_data(s))
            sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_connection)
    return server


def main():
    logs.setup()

    if platform.system() == "Windows":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("korvex.studio.antichatter")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("io.github.mikicolmena.KorvexAntiChatter")
    app.setQuitOnLastWindowClosed(False)

    name = _server_name()
    if _wake_existing_instance(name):
        log.info("Ya había una instancia abierta; se le pide que se muestre")
        return 0

    from .gui import MainWindow
    window = MainWindow()
    window.instance_server = _listen(name, window.show_window)   # mantener la referencia viva

    # Apagado / cierre de sesión: cerrar sin preguntar y sin bloquear al sistema.
    app.commitDataRequest.connect(lambda _manager: window.prepare_session_end())
    app.aboutToQuit.connect(window.shutdown)

    # Ctrl+C en una terminal: Qt no deja a Python atender señales si no se le da paso.
    signal.signal(signal.SIGINT, lambda *_: window.force_quit())
    signal_timer = QTimer()
    signal_timer.timeout.connect(lambda: None)
    signal_timer.start(500)

    start_hidden = "--minimized" in sys.argv or window.settings.value("start_minimized", False, type=bool)
    if start_hidden and not window.tray_available():
        # Al iniciar sesión la bandeja puede tardar unos segundos en aparecer:
        # se espera un poco y, si no llega, se muestra la ventana.
        window.wait_for_tray(on_timeout=window.show)
    elif not start_hidden:
        window.show()
    window.start_filter()

    return app.exec()
