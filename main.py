import sys
import os
import ctypes
import time

try:
    import keyboard
except ImportError:
    print("Faltan librerías. Instala: pip install keyboard PyQt6")
    sys.exit()

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QSpinBox, QSystemTrayIcon, QMenu, QStyle, 
                             QFrame, QDialog, QCheckBox, QComboBox)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QSettings
from PyQt6.QtGui import QFont, QAction, QIcon, QPixmap
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

# ============================================================================
# DIÁLOGO DE CIERRE
# ============================================================================
class CloseActionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("KORVEX Anti-Chatter")
        self.setFixedSize(350, 160)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("""
            QDialog { background-color: #1e1e1e; border: 2px solid #3e3e42; border-radius: 10px; }
            QLabel { color: white; font-family: 'Segoe UI'; }
            QPushButton { background-color: #2d2d30; color: white; border: 1px solid #555; padding: 8px; border-radius: 5px; font-weight: bold; }
            QPushButton:hover { background-color: #3e3e42; border: 1px solid #00aaff; }
            QCheckBox { color: #aaa; }
            QCheckBox::indicator { width: 15px; height: 15px; background: #2d2d30; border: 1px solid #555; }
            QCheckBox::indicator:checked { background: #00aaff; }
        """)

        layout = QVBoxLayout(self)
        
        lbl_title = QLabel("¿Qué deseas hacer?")
        lbl_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #00aaff;")
        layout.addWidget(lbl_title)

        lbl_desc = QLabel("La protección de teclado se detendrá si cierras la app.")
        layout.addWidget(lbl_desc)

        self.chk_remember = QCheckBox("Recordar mi elección y no volver a preguntar")
        layout.addWidget(self.chk_remember)

        btn_layout = QHBoxLayout()
        self.btn_minimize = QPushButton("Minimizar a la Bandeja")
        self.btn_exit = QPushButton("Salir del programa")
        
        self.btn_minimize.clicked.connect(lambda: self.done(1)) 
        self.btn_exit.clicked.connect(lambda: self.done(2))     
        
        btn_layout.addWidget(self.btn_minimize)
        btn_layout.addWidget(self.btn_exit)
        layout.addLayout(btn_layout)

# ============================================================================
# NÚCLEO DEL FILTRO
# ============================================================================
class AntiChatterCore(QObject):
    bounce_caught = pyqtSignal(str, int)
    
    def __init__(self):
        super().__init__()
        self.active = False
        self.threshold = 0.050
        self.ultimos_tiempos = {}
        self.bloqueos_totales = 0
        self.ignorar = ['backspace', 'enter', 'tab', 'shift', 'ctrl', 'alt', 'left', 'right', 'up', 'down', 'esc']
        self._hook = None

    def set_threshold(self, ms):
        self.threshold = ms / 1000.0

    def start(self):
        if not self.active:
            self.ultimos_tiempos.clear()
            self._hook = keyboard.hook(self.filtro)
            self.active = True

    def stop(self):
        if self.active:
            if self._hook:
                try: keyboard.unhook(self._hook)
                except: pass
                self._hook = None
            self.active = False

    def filtro(self, evento):
        if not self.active: return
        if evento.event_type == keyboard.KEY_DOWN:
            tecla = evento.name
            if tecla in self.ignorar: return

            ahora = time.time()
            if tecla in self.ultimos_tiempos:
                delta = ahora - self.ultimos_tiempos[tecla]
                if delta < self.threshold:
                    self.bloqueos_totales += 1
                    keyboard.press_and_release('backspace')
                    self.bounce_caught.emit(tecla, self.bloqueos_totales)
                    return 
            self.ultimos_tiempos[tecla] = ahora

# ============================================================================
# VENTANA PRINCIPAL
# ============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KORVEX Anti-Chatter")
        self.setFixedSize(380, 310) 
        
        self.settings = QSettings("Korvex", "AntiChatter")
        
        self.server = QLocalServer(self)
        self.server.removeServer("KorvexAntiChatterServer")
        self.server.listen("KorvexAntiChatterServer")
        self.server.newConnection.connect(self.wake_up)
        
        self.core = AntiChatterCore()
        self.core.bounce_caught.connect(self.on_bounce_caught)
        
        # Estilos KORVEX
        self.setStyleSheet("""
            QMainWindow { background-color: #1e1e1e; }
            QLabel { color: white; }
            QFrame#MainFrame { background-color: #252526; border-radius: 10px; border: 1px solid #3e3e42; }
            QPushButton#BtnToggle { border-radius: 5px; font-weight: bold; font-size: 14px; padding: 10px; }
            QSpinBox { background: #2d2d30; color: #00aaff; border: 1px solid #3e3e42; padding: 5px; border-radius: 5px; font-weight: bold; font-size: 16px; }
            QSpinBox::up-button, QSpinBox::down-button { width: 20px; }
            QComboBox { background: #2d2d30; border: 1px solid #3e3e42; padding: 5px; color: white; border-radius: 5px; min-width: 140px; font-size: 12px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #2d2d30; color: white; selection-background-color: #00aaff; border: 1px solid #3e3e42; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        frame = QFrame()
        frame.setObjectName("MainFrame")
        frame_layout = QVBoxLayout(frame)
        
        # --- CARGA DEL LOGO (Estilo Korvex Studio) ---
        header_layout = QHBoxLayout()
        lbl_logo = QLabel()
        
        if getattr(sys, 'frozen', False): 
            base_path = sys._MEIPASS
        else: 
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        logo_path = os.path.join(base_path, "KorvexLogo.ico")
        
        if os.path.exists(logo_path):
            icon = QIcon(logo_path)
            self.setWindowIcon(icon)
            
            pixmap = QPixmap(logo_path)
            if not pixmap.isNull():
                scaled_pixmap = pixmap.scaledToHeight(35, Qt.TransformationMode.SmoothTransformation)
                lbl_logo.setPixmap(scaled_pixmap)
                lbl_logo.setStyleSheet("border: none; background: transparent;")
        else:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
            self.setWindowIcon(icon)
            lbl_logo.setText("🛡️")
            lbl_logo.setStyleSheet("font-size: 24px; border: none; background: transparent;")

        self.setup_tray_icon(icon)
        
        lbl_title = QLabel("KORVEX ANTI-CHATTER")
        lbl_title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        lbl_title.setStyleSheet("color: #00aaff; letter-spacing: 1px;")
        
        header_layout.addStretch()
        header_layout.addWidget(lbl_logo)
        header_layout.addWidget(lbl_title)
        header_layout.addStretch()
        frame_layout.addLayout(header_layout)

        # --- FILA 1: MILISEGUNDOS ---
        row_ms = QHBoxLayout()
        lbl_ms = QLabel("Umbral de bloqueo:")
        self.spin_ms = QSpinBox()
        self.spin_ms.setRange(10, 200)
        
        last_ms = self.settings.value("threshold_ms", 50, type=int)
        self.spin_ms.setValue(last_ms)
        self.core.set_threshold(last_ms)
        self.spin_ms.setSuffix(" ms")
        self.spin_ms.valueChanged.connect(self.on_ms_changed)
        
        row_ms.addWidget(lbl_ms)
        row_ms.addStretch()
        row_ms.addWidget(self.spin_ms)
        frame_layout.addLayout(row_ms)

        # --- FILA 2: ACCIÓN AL CERRAR ---
        row_close = QHBoxLayout()
        lbl_close = QLabel("Acción al cerrar (X):")
        self.combo_close = QComboBox()
        self.combo_close.addItems(["Preguntar", "Minimizar a bandeja", "Salir del programa"])
        
        saved_action = self.settings.value("close_action", "ask")
        if saved_action == "minimize":
            self.combo_close.setCurrentIndex(1)
        elif saved_action == "exit":
            self.combo_close.setCurrentIndex(2)
        else:
            self.combo_close.setCurrentIndex(0)
            
        self.combo_close.currentIndexChanged.connect(self.on_close_action_changed)

        row_close.addWidget(lbl_close)
        row_close.addStretch()
        row_close.addWidget(self.combo_close)
        frame_layout.addLayout(row_close)

        # --- BOTÓN INICIAR ---
        self.btn_toggle = QPushButton("INICIAR FILTRO")
        self.btn_toggle.setObjectName("BtnToggle")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle_filter)
        self.update_btn_style(False)
        frame_layout.addWidget(self.btn_toggle)

        # --- ESTADÍSTICAS ---
        self.lbl_stats = QLabel("Rebotes evitados: 0")
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_stats.setStyleSheet("color: #888; font-size: 11px;")
        frame_layout.addWidget(self.lbl_stats)

        main_layout.addWidget(frame)
        self.toggle_filter()

    def on_close_action_changed(self, index):
        if index == 0: self.settings.setValue("close_action", "ask")
        elif index == 1: self.settings.setValue("close_action", "minimize")
        elif index == 2: self.settings.setValue("close_action", "exit")

    def wake_up(self):
        socket = self.server.nextPendingConnection()
        socket.waitForReadyRead()
        if socket.readAll() == b"WAKE_UP":
            self.showNormal()
            self.activateWindow()

    def on_ms_changed(self, val):
        self.core.set_threshold(val)
        self.settings.setValue("threshold_ms", val)

    def update_btn_style(self, active):
        if active:
            self.btn_toggle.setText("FILTRO ACTIVO (PAUSAR)")
            self.btn_toggle.setStyleSheet("background-color: #27ae60; color: white; border: 1px solid #2ecc71;")
        else:
            self.btn_toggle.setText("FILTRO PAUSADO (INICIAR)")
            self.btn_toggle.setStyleSheet("background-color: #c0392b; color: white; border: 1px solid #e74c3c;")

    def toggle_filter(self):
        if self.core.active:
            self.core.stop()
            self.update_btn_style(False)
        else:
            self.core.start()
            self.update_btn_style(True)

    def on_bounce_caught(self, tecla, total):
        self.lbl_stats.setText(f"Último bloqueo: '{tecla.upper()}' | Rebotes evitados: {total}")
        self.lbl_stats.setStyleSheet("color: #e74c3c; font-size: 11px; font-weight: bold;")
        QApplication.processEvents()
        time.sleep(0.05)
        self.lbl_stats.setStyleSheet("color: #888; font-size: 11px;")

    def setup_tray_icon(self, icon):
        self.tray_icon = QSystemTrayIcon(icon, self)
        self.tray_icon.setToolTip("KORVEX Anti-Chatter")
        tray_menu = QMenu(self)
        tray_menu.setStyleSheet("QMenu { background: #252526; color: white; border: 1px solid #555; } QMenu::item:selected { background: #00aaff; }")
        
        action_show = QAction("Mostrar interfaz", self)
        action_show.triggered.connect(self.showNormal)
        
        action_quit = QAction("Cerrar del todo", self)
        action_quit.triggered.connect(lambda: self.force_quit())
        
        tray_menu.addAction(action_show)
        tray_menu.addSeparator()
        tray_menu.addAction(action_quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.tray_icon_activated)
        self.tray_icon.show()

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def force_quit(self):
        self.core.stop()
        QApplication.instance().quit()

    def closeEvent(self, event):
        close_action = self.settings.value("close_action", "ask")
        
        if close_action == "minimize":
            event.ignore()
            self.hide()
            self.tray_icon.showMessage("KORVEX Anti-Chatter", "Protegiendo en segundo plano.", QSystemTrayIcon.MessageIcon.Information, 1500)
        elif close_action == "exit":
            self.force_quit()
        else:
            dialog = CloseActionDialog(self)
            result = dialog.exec()
            
            if result == 0:
                event.ignore()
                return
                
            if dialog.chk_remember.isChecked():
                if result == 1: 
                    self.settings.setValue("close_action", "minimize")
                    self.combo_close.setCurrentIndex(1) 
                if result == 2: 
                    self.settings.setValue("close_action", "exit")
                    self.combo_close.setCurrentIndex(2) 
                
            if result == 1:
                event.ignore()
                self.hide()
                self.tray_icon.showMessage("KORVEX Anti-Chatter", "Protegiendo en segundo plano.", QSystemTrayIcon.MessageIcon.Information, 1500)
            elif result == 2:
                self.force_quit()

if __name__ == "__main__":
    myappid = 'korvex.studio.antichatter.v1'
    try: ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelId(myappid)
    except: pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    socket = QLocalSocket()
    socket.connectToServer("KorvexAntiChatterServer")
    if socket.waitForConnected(500):
        socket.write(b"WAKE_UP")
        socket.waitForBytesWritten(500)
        socket.disconnectFromServer()
        sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())