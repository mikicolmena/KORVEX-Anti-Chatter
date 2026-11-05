"""Interfaz gráfica (PyQt6)."""

import json
import logging

from PyQt6.QtCore import QEvent, QObject, QSettings, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QFont, QIcon, QKeySequence, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
    QLayout, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
    QPushButton, QSpinBox, QStyle, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from . import APP_NAME, ORG_NAME, SETTINGS_APP, __version__, autostart, logs
from .backends import BackendError, get_backend_class
from .core import DebounceFilter
from .i18n import tr
from .resources import logo_path

log = logging.getLogger(__name__)

ACCENT = "#00aaff"

STYLE = f"""
    QMainWindow, QDialog {{ background-color: #1e1e1e; }}
    QLabel {{ color: white; }}
    QFrame#MainFrame {{ background-color: #252526; border-radius: 10px; border: 1px solid #3e3e42; }}
    QPushButton {{ background-color: #2d2d30; color: white; border: 1px solid #555; padding: 6px 10px; border-radius: 5px; }}
    QPushButton:hover {{ background-color: #3e3e42; border: 1px solid {ACCENT}; }}
    QPushButton#BtnToggle {{ border-radius: 5px; font-weight: bold; padding: 10px; }}
    QPushButton#LinkButton {{ background: transparent; border: none; color: #888; padding: 0; text-decoration: underline; }}
    QPushButton#LinkButton:hover {{ color: {ACCENT}; }}
    QToolTip {{ background-color: #2d2d30; color: white; border: 1px solid #555; padding: 4px; }}
    QSpinBox {{ background: #2d2d30; color: {ACCENT}; border: 1px solid #3e3e42; padding: 4px; border-radius: 5px; font-weight: bold; }}
    QComboBox {{ background: #2d2d30; border: 1px solid #3e3e42; padding: 4px 8px; color: white; border-radius: 5px; }}
    QComboBox QAbstractItemView {{ background-color: #2d2d30; color: white; selection-background-color: {ACCENT}; border: 1px solid #3e3e42; }}
    QCheckBox {{ color: white; }}
    QCheckBox::indicator, QListWidget::indicator {{ width: 14px; height: 14px; background: #2d2d30; border: 1px solid #777; }}
    QCheckBox::indicator:checked, QListWidget::indicator:checked {{ background: {ACCENT}; }}
    QListWidget {{ background: #2d2d30; color: white; border: 1px solid #3e3e42; border-radius: 5px; }}
    QListWidget::item:selected {{ background: #3e3e42; }}
    QMenu {{ background: #252526; color: white; border: 1px solid #555; }}
    QMenu::item:selected {{ background: {ACCENT}; }}
"""

_BTN_ON = "background-color: #27ae60; color: white; border: 1px solid #2ecc71;"
_BTN_OFF = "background-color: #c0392b; color: white; border: 1px solid #e74c3c;"
_STATS_IDLE = "color: #888;"
_STATS_FLASH = "color: #e74c3c; font-weight: bold;"


def _load_json(settings, key, default):
    try:
        value = json.loads(settings.value(key, "") or "null")
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


# =============================================================================
# Controlador: une el filtro, el backend y la configuración
# =============================================================================
class FilterController(QObject):
    bounce = pyqtSignal(int)            # código de tecla (emitido desde el hilo del backend)
    failed = pyqtSignal(str)            # error asíncrono del backend
    state_changed = pyqtSignal(bool)

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.active = False
        self.init_error = None
        try:
            self.backend_cls = get_backend_class()
        except BackendError as e:
            self.backend_cls = None
            self.init_error = str(e)
        cls = self.backend_cls
        self.filter = DebounceFilter(cls.MODIFIER_CODES if cls else (), cls.SPACE_CODE if cls else None)
        self.backend = cls(self.filter, self.bounce.emit, self.failed.emit) if cls else None
        self.failed.connect(self._on_failed)

        self.key_names = {int(k): v for k, v in _load_json(settings, "keys/names", {}).items()}
        self.counts = {int(k): int(v) for k, v in _load_json(settings, "stats/per_key", {}).items()}
        self.total = settings.value("stats/total", 0, type=int)

        self.filter.set_threshold_ms(settings.value("threshold_ms", 50, type=int))
        self.filter.set_threshold_space_ms(settings.value("threshold_space_ms", 120, type=int))
        self.filter.set_selection(settings.value("keys/filter_all", True, type=bool),
                                  _load_json(settings, "keys/selected", []))

    # --- control ---
    def start(self):
        if self.active:
            return
        if self.backend is None:
            raise BackendError(self.init_error)
        self.filter.reset()
        self.backend.start()
        self.active = True
        self.state_changed.emit(True)

    def stop(self):
        if not self.active:
            return
        self.backend.stop()
        self.active = False
        self.state_changed.emit(False)

    def _on_failed(self, message):
        self.stop()

    # --- datos ---
    def key_name(self, code):
        if code in self.key_names:
            return self.key_names[code]
        if self.backend_cls:
            return self.backend_cls.key_name(code)
        return str(code)

    def register_bounce(self, code):
        self.total += 1
        self.counts[code] = self.counts.get(code, 0) + 1
        self.settings.setValue("stats/total", self.total)
        self.settings.setValue("stats/per_key", json.dumps({str(k): v for k, v in self.counts.items()}))

    def forget_keys(self, codes):
        """Olvida el contador de las teclas quitadas de la lista."""
        for code in codes:
            self.counts.pop(code, None)
        self.settings.setValue("stats/per_key", json.dumps({str(k): v for k, v in self.counts.items()}))

    def reset_stats(self):
        self.total = 0
        self.counts.clear()
        self.settings.setValue("stats/total", 0)
        self.settings.setValue("stats/per_key", "{}")

    def set_threshold(self, ms, space=False):
        if space:
            self.filter.set_threshold_space_ms(ms)
            self.settings.setValue("threshold_space_ms", ms)
        else:
            self.filter.set_threshold_ms(ms)
            self.settings.setValue("threshold_ms", ms)

    def set_selection(self, filter_all, codes=None, names=None):
        codes = sorted(self.filter.selected if codes is None else codes)
        if names is not None:
            self.key_names = dict(names)
            self.settings.setValue("keys/names", json.dumps({str(k): v for k, v in self.key_names.items()}))
        self.filter.set_selection(filter_all, codes)
        self.settings.setValue("keys/filter_all", bool(filter_all))
        self.settings.setValue("keys/selected", json.dumps(codes))


# =============================================================================
# Diálogos
# =============================================================================
class CloseActionDialog(QDialog):
    CANCEL, MINIMIZE, EXIT = 0, 1, 2

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(APP_NAME)
        layout = QVBoxLayout(self)

        title = QLabel(tr("close_q_title"))
        font = title.font()
        font.setPointSizeF(font.pointSizeF() * 1.25)
        font.setBold(True)
        title.setFont(font)
        title.setStyleSheet(f"color: {ACCENT};")
        layout.addWidget(title)

        desc = QLabel(tr("close_q_desc"))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.chk_remember = QCheckBox(tr("close_q_remember"))
        layout.addWidget(self.chk_remember)

        buttons = QHBoxLayout()
        btn_min = QPushButton(tr("close_minimize"))
        btn_exit = QPushButton(tr("close_exit"))
        btn_cancel = QPushButton(tr("cancel"))
        btn_min.clicked.connect(lambda: self.done(self.MINIMIZE))
        btn_exit.clicked.connect(lambda: self.done(self.EXIT))
        btn_cancel.clicked.connect(lambda: self.done(self.CANCEL))
        btn_min.setDefault(True)
        for b in (btn_min, btn_exit, btn_cancel):
            buttons.addWidget(b)
        layout.addLayout(buttons)


class KeyCaptureDialog(QDialog):
    """Espera a que el usuario pulse una tecla y devuelve (código, nombre)."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.result_key = None
        self.setWindowTitle(tr("capture_title"))
        layout = QVBoxLayout(self)
        label = QLabel(tr("capture_msg"))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setMinimumWidth(280)
        layout.addWidget(label)
        cancel = QPushButton(tr("cancel"))
        cancel.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # que Espacio/Intro no lo activen
        cancel.clicked.connect(self.reject)
        layout.addWidget(cancel, alignment=Qt.AlignmentFlag.AlignCenter)

    def event(self, ev):
        # Interceptar antes de que Qt use Tab/Esc para el foco o para cerrar.
        if ev.type() == QEvent.Type.KeyPress and not ev.isAutoRepeat():
            code = self.controller.backend_cls.code_from_qt(ev.nativeScanCode()) \
                if self.controller.backend_cls else None
            if code is not None:
                text = ev.text()
                if text and text.isprintable() and not text.isspace():
                    name = text.upper()
                else:
                    name = QKeySequence(ev.key()).toString() or self.controller.key_name(code)
                self.result_key = (code, name)
                self.accept()
            return True
        return super().event(ev)


class KeysDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.names = dict(controller.key_names)
        self.removed = set()
        self.setWindowTitle(tr("keys_title"))
        self.setMinimumSize(360, 360)
        layout = QVBoxLayout(self)

        help_label = QLabel(tr("keys_help"))
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: #aaa;")
        layout.addWidget(help_label)

        self.list = QListWidget()
        layout.addWidget(self.list)
        selected = controller.filter.selected
        for code in sorted(set(selected) | set(controller.counts) | set(self.names),
                           key=lambda c: -controller.counts.get(c, 0)):
            self._add_item(code, code in selected)

        row = QHBoxLayout()
        btn_add = QPushButton(tr("keys_add"))
        btn_remove = QPushButton(tr("keys_remove"))
        btn_add.clicked.connect(self._capture)
        btn_remove.clicked.connect(self._remove)
        row.addWidget(btn_add)
        row.addWidget(btn_remove)
        row.addStretch()
        btn_ok = QPushButton(tr("ok"))
        btn_cancel = QPushButton(tr("cancel"))
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.setDefault(True)
        row.addWidget(btn_ok)
        row.addWidget(btn_cancel)
        layout.addLayout(row)

    def _label(self, code):
        name = self.names.get(code) or self.controller.key_name(code)
        return tr("keys_bounces", name=name, count=self.controller.counts.get(code, 0))

    def _find(self, code):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == code:
                return self.list.item(i)
        return None

    def _add_item(self, code, checked):
        item = QListWidgetItem(self._label(code))
        item.setData(Qt.ItemDataRole.UserRole, code)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.addItem(item)
        return item

    def _capture(self):
        dlg = KeyCaptureDialog(self.controller, self)
        if dlg.exec() and dlg.result_key:
            code, name = dlg.result_key
            self.names[code] = name
            self.removed.discard(code)
            item = self._find(code) or self._add_item(code, True)
            item.setText(self._label(code))
            item.setCheckState(Qt.CheckState.Checked)
            self.list.setCurrentItem(item)

    def _remove(self):
        for item in self.list.selectedItems():
            code = item.data(Qt.ItemDataRole.UserRole)
            self.names.pop(code, None)
            self.removed.add(code)
            self.list.takeItem(self.list.row(item))

    def selected_codes(self):
        codes = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                codes.append(item.data(Qt.ItemDataRole.UserRole))
        return codes


# =============================================================================
# Ventana principal
# =============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setStyleSheet(STYLE)
        self.settings = QSettings(ORG_NAME, SETTINGS_APP)
        self.controller = FilterController(self.settings)
        self.controller.bounce.connect(self.on_bounce)
        self.controller.failed.connect(self.show_error)
        self.controller.state_changed.connect(self.update_state)
        self._quitting = False

        path = logo_path()
        icon = QIcon(path) if path else self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(icon)
        QApplication.instance().setWindowIcon(icon)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)   # ajusta la ventana al contenido
        frame = QFrame()
        frame.setObjectName("MainFrame")
        frame.setMinimumWidth(400)
        form = QVBoxLayout(frame)
        form.setSpacing(10)
        main_layout.addWidget(frame)

        # --- cabecera ---
        header = QHBoxLayout()
        header.addStretch()
        lbl_logo = QLabel()
        pixmap = QPixmap(path) if path else QPixmap()
        if not pixmap.isNull():
            lbl_logo.setPixmap(pixmap.scaledToHeight(36, Qt.TransformationMode.SmoothTransformation))
        else:
            lbl_logo.setText("🛡️")
        header.addWidget(lbl_logo)
        lbl_title = QLabel(APP_NAME.upper())
        title_font = QFont(lbl_title.font())
        title_font.setPointSizeF(title_font.pointSizeF() * 1.4)
        title_font.setBold(True)
        lbl_title.setFont(title_font)
        lbl_title.setStyleSheet(f"color: {ACCENT}; letter-spacing: 1px;")
        header.addWidget(lbl_title)
        header.addStretch()
        form.addLayout(header)

        # --- umbrales ---
        self.spin_ms = self._spin(10, 200, self.settings.value("threshold_ms", 50, type=int))
        self.spin_ms.valueChanged.connect(lambda v: self.controller.set_threshold(v))
        form.addLayout(self._row(tr("threshold_letters"), self.spin_ms, tr("tip_threshold")))

        self.spin_space = self._spin(10, 300, self.settings.value("threshold_space_ms", 120, type=int))
        self.spin_space.valueChanged.connect(lambda v: self.controller.set_threshold(v, space=True))
        form.addLayout(self._row(tr("threshold_space"), self.spin_space, tr("tip_threshold_space")))

        # --- teclas a filtrar ---
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([tr("mode_all"), tr("mode_selected")])
        self.combo_mode.setCurrentIndex(0 if self.controller.filter.filter_all else 1)
        self.combo_mode.currentIndexChanged.connect(self.on_mode_changed)
        form.addLayout(self._row(tr("filter_mode"), self.combo_mode, tr("tip_mode")))
        self.btn_keys = QPushButton(tr("configure_keys"))
        self.btn_keys.clicked.connect(self.open_keys_dialog)
        self.btn_keys.setToolTip(tr("tip_keys"))
        keys_row = QHBoxLayout()
        keys_row.addStretch()
        keys_row.addWidget(self.btn_keys)
        form.addLayout(keys_row)

        # --- acción al cerrar ---
        self.combo_close = QComboBox()
        self.combo_close.addItems([tr("close_ask"), tr("close_minimize"), tr("close_exit")])
        self.combo_close.setCurrentIndex(
            {"minimize": 1, "exit": 2}.get(self.settings.value("close_action", "ask"), 0))
        self.combo_close.currentIndexChanged.connect(
            lambda i: self.settings.setValue("close_action", ("ask", "minimize", "exit")[i]))
        form.addLayout(self._row(tr("close_action"), self.combo_close))

        # --- casillas ---
        self.chk_autostart = QCheckBox(tr("autostart"))
        autostart.refresh()
        self.chk_autostart.setChecked(autostart.is_enabled())
        self.chk_autostart.toggled.connect(self.on_autostart_toggled)
        form.addWidget(self.chk_autostart)

        self.chk_start_min = QCheckBox(tr("start_minimized"))
        self.chk_start_min.setChecked(self.settings.value("start_minimized", False, type=bool))
        self.chk_start_min.toggled.connect(lambda v: self.settings.setValue("start_minimized", v))
        form.addWidget(self.chk_start_min)

        # --- botón principal ---
        self.btn_toggle = QPushButton()
        self.btn_toggle.setObjectName("BtnToggle")
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.clicked.connect(self.toggle_filter)
        form.addWidget(self.btn_toggle)

        # --- estadísticas ---
        self.lbl_stats = QLabel()
        self.lbl_stats.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_stats.setStyleSheet(_STATS_IDLE)
        form.addWidget(self.lbl_stats)
        footer = QHBoxLayout()
        lbl_version = QLabel(f"v{__version__}")
        lbl_version.setStyleSheet("color: #555;")
        footer.addWidget(lbl_version)
        footer.addStretch()
        btn_reset = QPushButton(tr("reset_stats"))
        btn_reset.setObjectName("LinkButton")
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self.reset_stats)
        footer.addWidget(btn_reset)
        form.addLayout(footer)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(lambda: self.lbl_stats.setStyleSheet(_STATS_IDLE))

        self.setup_tray(icon)
        self.update_stats()
        self.update_state(False)

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _spin(lo, hi, value):
        spin = QSpinBox()
        spin.setRange(lo, hi)
        spin.setValue(value)
        spin.setSuffix(" ms")
        return spin

    @staticmethod
    def _row(text, widget, tooltip=None):
        row = QHBoxLayout()
        label = QLabel(text)
        if tooltip:
            label.setToolTip(tooltip)
            widget.setToolTip(tooltip)
        row.addWidget(label)
        row.addStretch()
        row.addWidget(widget)
        return row

    # ------------------------------------------------------------ filtro
    def start_filter(self, show_errors=True):
        try:
            self.controller.start()
            return True
        except BackendError as e:
            log.warning("No se pudo iniciar el filtro: %s", e)
            if show_errors:
                self.show_error(str(e))
            return False

    def toggle_filter(self):
        if self.controller.active:
            self.controller.stop()
        else:
            self.start_filter()

    def update_state(self, active):
        self.btn_toggle.setText(tr("btn_active") if active else tr("btn_paused"))
        self.btn_toggle.setStyleSheet(_BTN_ON if active else _BTN_OFF)
        if hasattr(self, "action_pause"):
            self.action_pause.setText(tr("tray_pause") if active else tr("tray_resume"))
            self.tray.setToolTip(f"{APP_NAME} — {tr('btn_active') if active else tr('btn_paused')}")

    def show_error(self, message):
        if self._quitting:
            return
        self.show_window()
        if logs.log_file():
            message = f"{message}\n\n{tr('log_hint', path=logs.log_file())}"
        box = QMessageBox(QMessageBox.Icon.Warning, tr("err_title"), message, parent=self)
        box.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.exec()

    def on_mode_changed(self, index):
        self.controller.set_selection(index == 0)

    def open_keys_dialog(self):
        dlg = KeysDialog(self.controller, self)
        if dlg.exec():
            self.controller.set_selection(self.combo_mode.currentIndex() == 0,
                                          dlg.selected_codes(), dlg.names)
            self.controller.forget_keys(dlg.removed)

    def on_bounce(self, code):
        self.controller.register_bounce(code)
        self.update_stats(self.controller.key_name(code))
        self.lbl_stats.setStyleSheet(_STATS_FLASH)
        self._flash_timer.start(150)

    def update_stats(self, last_key=None):
        total = self.controller.total
        self.lbl_stats.setText(tr("stats_last", key=last_key, total=total) if last_key
                               else tr("stats", total=total))

    def reset_stats(self):
        self.controller.reset_stats()
        self.update_stats()

    def on_autostart_toggled(self, checked):
        try:
            autostart.set_enabled(checked)
        except OSError as e:
            QMessageBox.warning(self, APP_NAME, str(e))
        self.chk_autostart.blockSignals(True)
        self.chk_autostart.setChecked(autostart.is_enabled())
        self.chk_autostart.blockSignals(False)

    # ------------------------------------------------------------ bandeja
    def setup_tray(self, icon):
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        menu.setStyleSheet(STYLE)
        action_show = QAction(tr("tray_show"), self)
        action_show.triggered.connect(self.show_window)
        self.action_pause = QAction(tr("tray_pause"), self)
        self.action_pause.triggered.connect(self.toggle_filter)
        action_quit = QAction(tr("tray_quit"), self)
        action_quit.triggered.connect(self.force_quit)
        menu.addAction(action_show)
        menu.addAction(self.action_pause)
        menu.addSeparator()
        menu.addAction(action_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.on_tray_activated)
        if self.tray_available():
            self.tray.show()

    @staticmethod
    def tray_available():
        return QSystemTrayIcon.isSystemTrayAvailable()

    def wait_for_tray(self, on_timeout, attempts=20):
        """Reintenta mostrar el icono de la bandeja cada 0,5 s (unos 10 s en total)."""
        if self.tray_available():
            self.tray.show()
        elif attempts > 0:
            QTimer.singleShot(500, lambda: self.wait_for_tray(on_timeout, attempts - 1))
        else:
            log.info("No hay bandeja del sistema; se muestra la ventana")
            on_timeout()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and not self.isMinimized():
                self.hide()
            else:
                self.show_window()

    def show_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def hide_to_tray(self):
        if not self.tray_available():
            self.showMinimized()          # sin bandeja: minimizar a la barra de tareas
            return
        self.hide()
        if not self.settings.value("tray_hint_shown", False, type=bool):
            self.tray.showMessage(tr("tray_bg_title"), tr("tray_bg_msg"),
                                  QSystemTrayIcon.MessageIcon.Information, 3000)
            self.settings.setValue("tray_hint_shown", True)

    def force_quit(self):
        self._quitting = True
        self.shutdown()
        QApplication.instance().quit()

    def prepare_session_end(self):
        """El sistema se apaga o se cierra la sesión: no preguntar ni bloquear el cierre."""
        log.info("Fin de sesión del sistema")
        self._quitting = True
        self.settings.sync()

    def shutdown(self):
        self._quitting = True
        self.controller.stop()
        self.tray.hide()
        self.settings.sync()

    def closeEvent(self, event):
        if self._quitting:
            event.accept()
            return
        action = self.settings.value("close_action", "ask")
        if action == "ask":
            dlg = CloseActionDialog(self)
            result = dlg.exec()
            if result == CloseActionDialog.CANCEL:
                event.ignore()
                return
            action = "minimize" if result == CloseActionDialog.MINIMIZE else "exit"
            if dlg.chk_remember.isChecked():
                self.combo_close.setCurrentIndex(1 if action == "minimize" else 2)
        if action == "minimize":
            event.ignore()
            self.hide_to_tray()
        else:
            event.ignore()
            self.force_quit()
