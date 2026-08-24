import sys
import os
import platform
import time
import ctypes  # Añadido para Windows AppUserModelID

try:
    import keyboard
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                                 QLabel, QPushButton, QSpinBox, QSystemTrayIcon, QMenu, QStyle, 
                                 QFrame, QDialog, QCheckBox, QComboBox)
    from PyQt6.QtCore import Qt, QObject, pyqtSignal, QSettings, QTimer
    from PyQt6.QtGui import QFont, QAction, QIcon, QPixmap
    from PyQt6.QtNetwork import QLocalServer, QLocalSocket
except ImportError as e:
    print(f"Faltan librerías: {e}. Instala: pip install keyboard PyQt6")
    sys.exit()

# ============================================================================
# FUNCIONES DEL SISTEMA OPERATIVO (AUTOSTART MULTIPLATAFORMA CORREGIDO)
# ============================================================================
def get_real_user_linux():
    """ Detecta el usuario real y su Home en Linux incluso bajo sudo/pkexec """
    import pwd
    uid = os.environ.get('PKEXEC_UID') or os.environ.get('SUDO_UID')
    if uid:
        try:
            pw = pwd.getpwuid(int(uid))
            return pw.pw_name, pw.pw_dir
        except Exception:
            pass
    return os.environ.get('USER'), os.path.expanduser("~")

def set_autostart(enable):
    app_name = "KorvexAntiChatter"
    
    if getattr(sys, 'frozen', False):
        exec_path = sys.executable
    else:
        exec_path = f"{sys.executable} \"{os.path.abspath(__file__)}\""

    if platform.system() == "Windows":
        import winreg
        key = winreg.HKEY_CURRENT_USER
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        try:
            registry_key = winreg.OpenKey(key, key_path, 0, winreg.KEY_WRITE)
            if enable:
                winreg.SetValueEx(registry_key, app_name, 0, winreg.REG_SZ, exec_path)
            else:
                try: winreg.DeleteValue(registry_key, app_name)
                except FileNotFoundError: pass
            winreg.CloseKey(registry_key)
        except Exception as e:
            print(f"Error autostart Windows: {e}")

    elif platform.system() == "Linux":
        # CORRECCIÓN: Obtener el Home del usuario real, no de root
        username, user_home = get_real_user_linux()
        autostart_dir = os.path.join(user_home, ".config", "autostart")
        
        if not os.path.exists(autostart_dir):
            try:
                os.makedirs(autostart_dir)
                uid = os.environ.get('PKEXEC_UID') or os.environ.get('SUDO_UID')
                if uid: os.chown(autostart_dir, int(uid), -1)
            except Exception: pass
        
        desktop_file_path = os.path.join(autostart_dir, f"{app_name}.desktop")
        
        if enable:
            # NOTA: Para que el arranque sea realmente invisible, se necesita una regla sudoers NOPASSWD.
            # Aquí se usa 'sudo -E' solo si el binario está en /usr/local/bin, asumiendo que la regla existe.
            # Si no, se ejecutará el comando normal y puede pedir contraseña.
            if exec_path == "/usr/local/bin/KorvexAntiChatter":
                exec_command = "sudo -E /usr/local/bin/KorvexAntiChatter"
            else:
                exec_command = exec_path

            desktop_content = f"""[Desktop Entry]
Type=Application
Exec={exec_command}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name={app_name}
Comment=Korvex Anti-Chatter
Icon=KorvexLogo
"""
            try:
                with open(desktop_file_path, "w") as f:
                    f.write(desktop_content)
                # Asegurar que el archivo pertenece al usuario, no a root
                uid = os.environ.get('PKEXEC_UID') or os.environ.get('SUDO_UID')
                if uid: os.chown(desktop_file_path, int(uid), -1)
            except Exception as e:
                print(f"Error escribiendo autostart Linux: {e}")
        else:
            if os.path.exists(desktop_file_path):
                try: os.remove(desktop_file_path)
                except Exception: pass

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
# NÚCLEO DEL FILTRO (Motor V3 - GAP Logic de Alta Precisión)
# ============================================================================
class AntiChatterCore(QObject):
    bounce_caught = pyqtSignal(str, int)
    
    def __init__(self):
        super().__init__()
        self.active = False
        self.threshold = 0.050
        self.threshold_space = 0.120 
        self.bloqueos_totales = 0
        self._hook = None
        self.last_up_time = {}   
        self.key_is_down = {}    

    def set_threshold(self, ms): self.threshold = ms / 1000.0
    def set_threshold_space(self, ms): self.threshold_space = ms / 1000.0

    def start(self):
        if not self.active:
            self.last_up_time.clear()
            self.key_is_down.clear()
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
        tecla = evento.name
        
        if len(tecla) > 1 and tecla != 'space': return
        ahora = time.perf_counter()

        if evento.event_type == keyboard.KEY_UP:
            self.key_is_down[tecla] = False
            self.last_up_time[tecla] = ahora
            return

        if evento.event_type == keyboard.KEY_DOWN:
            if self.key_is_down.get(tecla, False) == True: return
            self.key_is_down[tecla] = True
            
            ultimo_up = self.last_up_time.get(tecla, 0)
            if ultimo_up == 0: return

            delta = ahora - ultimo_up
            umbral_actual = self.threshold_space if tecla == 'space' else self.threshold

            if delta < umbral_actual:
                self.bloqueos_totales += 1
                keyboard.press_and_release('backspace')
                self.bounce_caught.emit(tecla, self.bloqueos_totales)
                return

# ============================================================================
# VENTANA PRINCIPAL
# ============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KORVEX Anti-Chatter")
        self.setFixedSize(380, 400) 
        
        self.settings = QSettings("Korvex", "AntiChatter")
        
        self.server = QLocalServer(self)
        self.server.removeServer("KorvexAntiChatterServer")
        # Comprobar si se pudo escuchar, si no, salir
        if not self.server.listen("KorvexAntiChatterServer"):
            sys.exit(0)  # Ya hay una instancia corriendo, no debería pasar por el socket de detección
        self.server.newConnection.connect(self.wake_up)
        
        self.core = AntiChatterCore()
        self.core.bounce_caught.connect(self.on_bounce_caught)
        
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
            QCheckBox { color: white; font-size: 12px; }
            QCheckBox::indicator { width: 15px; height: 15px; background: #2d2d30; border: 1px solid #555; }
            QCheckBox::indicator:checked { background: #00aaff; }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        frame = QFrame()
        frame.setObjectName("MainFrame")
        frame_layout = QVBoxLayout(frame)
        
        # --- CARGA DEL LOGO MULTIPLATAFORMA ---
        header_layout = QHBoxLayout()
        lbl_logo = QLabel()
        
        if getattr(sys, 'frozen', False): 
            base_path = sys._MEIPASS
        else: 
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        logo_path = os.path.join(base_path, "KorvexLogo.png")
        if not os.path.exists(logo_path):
            logo_path = os.path.join(base_path, "KorvexLogo.ico")
            
        # MEJORA: Si no se encuentra localmente y estamos en Linux, buscar en la ruta del sistema
        if not os.path.exists(logo_path) and platform.system() == "Linux":
            if os.path.exists("/usr/share/pixmaps/KorvexLogo.png"):
                logo_path = "/usr/share/pixmaps/KorvexLogo.png"
        
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

        # --- FILA 1: MILISEGUNDOS GENERALES ---
        row_ms = QHBoxLayout()
        lbl_ms = QLabel("Umbral Letras:")
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

        # --- FILA 2: MILISEGUNDOS DEL ESPACIO ---
        row_ms_space = QHBoxLayout()
        lbl_ms_space = QLabel("Umbral Espacio:")
        lbl_ms_space.setStyleSheet("color: #aaa;")
        self.spin_ms_space = QSpinBox()
        self.spin_ms_space.setRange(10, 300) 
        last_ms_space = self.settings.value("threshold_space_ms", 120, type=int)
        self.spin_ms_space.setValue(last_ms_space)
        self.core.set_threshold_space(last_ms_space)
        self.spin_ms_space.setSuffix(" ms")
        self.spin_ms_space.valueChanged.connect(self.on_ms_space_changed)
        
        row_ms_space.addWidget(lbl_ms_space)
        row_ms_space.addStretch()
        row_ms_space.addWidget(self.spin_ms_space)
        frame_layout.addLayout(row_ms_space)

        # --- FILA 3: ACCIÓN AL CERRAR ---
        row_close = QHBoxLayout()
        lbl_close = QLabel("Acción al cerrar:")
        self.combo_close = QComboBox()
        self.combo_close.addItems(["Preguntar", "Minimizar a bandeja", "Salir del programa"])
        
        saved_action = self.settings.value("close_action", "ask")
        if saved_action == "minimize": self.combo_close.setCurrentIndex(1)
        elif saved_action == "exit": self.combo_close.setCurrentIndex(2)
        else: self.combo_close.setCurrentIndex(0)
            
        self.combo_close.currentIndexChanged.connect(self.on_close_action_changed)
        row_close.addWidget(lbl_close)
        row_close.addStretch()
        row_close.addWidget(self.combo_close)
        frame_layout.addLayout(row_close)

        # --- FILA 4: CHECKBOXES ---
        chk_layout = QVBoxLayout()
        
        self.chk_autostart = QCheckBox("Iniciar automáticamente con el sistema")
        is_autostart = self.settings.value("autostart_enabled", False, type=bool)
        self.chk_autostart.setChecked(is_autostart)
        self.chk_autostart.toggled.connect(self.on_autostart_toggled)
        
        self.chk_start_minimized = QCheckBox("Arrancar escondido en la bandeja")
        is_minimized = self.settings.value("start_minimized", False, type=bool)
        self.chk_start_minimized.setChecked(is_minimized)
        self.chk_start_minimized.toggled.connect(lambda v: self.settings.setValue("start_minimized", v))

        chk_layout.addWidget(self.chk_autostart)
        chk_layout.addWidget(self.chk_start_minimized)
        frame_layout.addLayout(chk_layout)

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

    def on_autostart_toggled(self, checked):
        self.settings.setValue("autostart_enabled", checked)
        set_autostart(checked)

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
        
    def on_ms_space_changed(self, val):
        self.core.set_threshold_space(val)
        self.settings.setValue("threshold_space_ms", val)

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
        # Usar QTimer en lugar de time.sleep para no bloquear la UI
        QTimer.singleShot(100, lambda: self.lbl_stats.setStyleSheet("color: #888; font-size: 11px;"))

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
        # Mostrar el icono solo si hay bandeja disponible
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        else:
            print("Advertencia: No hay bandeja del sistema disponible. La ventana permanecerá abierta.")

    def tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.showNormal()
                self.activateWindow()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def force_quit(self):
        self.core.stop()
        QApplication.instance().quit()

    def closeEvent(self, event):
        close_action = self.settings.value("close_action", "ask")
        
        if close_action == "minimize":
            # Si no hay bandeja, no ocultar, salir directamente
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self.force_quit()
                return
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
                if not QSystemTrayIcon.isSystemTrayAvailable():
                    self.force_quit()
                    return
                event.ignore()
                self.hide()
                self.tray_icon.showMessage("KORVEX Anti-Chatter", "Protegiendo en segundo plano.", QSystemTrayIcon.MessageIcon.Information, 1500)
            elif result == 2:
                self.force_quit()

if __name__ == "__main__":
    # --- ESCUDO DE PRIVILEGIOS (LINUX AUTO-SUDO) ---
    if platform.system() == "Linux" and os.geteuid() != 0:
        print("KORVEX: Solicitando permisos de superusuario para interactuar con el hardware...")
        env_vars = []
        for var in ['DISPLAY', 'XAUTHORITY', 'WAYLAND_DISPLAY']:
            if var in os.environ:
                env_vars.append(f"{var}={os.environ[var]}")
        
        executable = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)
        
        args = ["pkexec", "env"] + env_vars
        if getattr(sys, 'frozen', False):
            args.append(executable)
        else:
            args.extend([sys.executable, executable])
        args.extend(sys.argv[1:])
        
        try:
            os.execvp("pkexec", args)
        except Exception as e:
            print("Error al pedir permisos:", e)
            sys.exit(1)

    # --- SOLO PARA WINDOWS (Agrupar icono en la barra) ---
    if platform.system() == "Windows":
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
    
    # LÓGICA DE ARRANQUE ESCONDIDO
    if not window.settings.value("start_minimized", False, type=bool):
        window.show()
        
    sys.exit(app.exec())