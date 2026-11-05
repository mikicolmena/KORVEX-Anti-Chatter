"""Arranque de la aplicación: instancia única, ventana y bandeja."""

import getpass
import platform
import sys

from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

from . import APP_NAME, INSTANCE_SERVER, ORG_NAME, __version__


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
    sock.write(b"WAKE_UP")
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
            return None

    def on_connection():
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: (s.readAll() == b"WAKE_UP" and on_wake()))
            sock.disconnected.connect(sock.deleteLater)

    server.newConnection.connect(on_connection)
    return server


def main():
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
        return 0

    from .gui import MainWindow
    window = MainWindow()
    window.instance_server = _listen(name, window.show_window)   # mantener la referencia viva

    start_hidden = "--minimized" in sys.argv or window.settings.value("start_minimized", False, type=bool)
    if not (start_hidden and window.tray_available()):
        window.show()
    window.start_filter()

    return app.exec()
