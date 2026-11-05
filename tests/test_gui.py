"""Prueba de humo de la interfaz en modo offscreen, con la configuración en una carpeta temporal."""

import os
import shutil
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="korvex-test-")
os.environ["HOME"] = _TMP
os.environ["XDG_CONFIG_HOME"] = os.path.join(_TMP, ".config")
os.environ["XDG_STATE_HOME"] = os.path.join(_TMP, ".state")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QCloseEvent, QKeyEvent
    from PyQt6.QtWidgets import QApplication
except ImportError:
    QApplication = None


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


@unittest.skipIf(QApplication is None, "requiere PyQt6")
class GuiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from korvex import gui
        cls.gui = gui

    def setUp(self):
        self.w = self.gui.MainWindow()
        self.addCleanup(self.w.shutdown)

    def test_bounce_updates_stats(self):
        self.w.on_bounce(30)
        self.w.on_bounce(30)
        self.assertEqual(self.w.controller.counts.get(30), 2)
        self.assertIn("2", self.w.lbl_stats.text())

    def test_keys_dialog_and_capture(self):
        dlg = self.gui.KeysDialog(self.w.controller, self.w)
        cap = self.gui.KeyCaptureDialog(self.w.controller, dlg)
        if self.w.controller.backend_cls is None:
            self.skipTest("sin backend en esta plataforma")
        native = 39 + 8 if os.name != "nt" else 0x27
        cap.event(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Ntilde,
                            Qt.KeyboardModifier.NoModifier, native, 0, 0, "ñ"))
        self.assertEqual(cap.result_key[1], "Ñ")

    def test_session_end_closes_without_asking(self):
        self.w.settings.setValue("close_action", "ask")
        self.w.prepare_session_end()
        event = QCloseEvent()
        self.w.closeEvent(event)       # si preguntara, el diálogo modal bloquearía el test
        self.assertTrue(event.isAccepted())


if __name__ == "__main__":
    unittest.main()
