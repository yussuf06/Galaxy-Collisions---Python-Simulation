"""Exercise appearance controls against a real, paused Qt physics worker.

Run separately: python -m unittest test_view_ui -v
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PySide6.QtCore import QPoint, Qt, qInstallMessageHandler
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from galaxy_app.window import MainWindow


class AppearanceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_until(self, predicate, window, timeout=15):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail('Timed out: '+window.status.text())

    @staticmethod
    def capture(view):
        image = view.grab().toImage()
        if image.isNull():
            raise AssertionError('View capture is empty')
        return hashlib.sha256(bytes(image.constBits())).hexdigest()

    def test_appearance_and_camera_controls_preserve_paused_physics(self):
        warnings = []
        exceptions = []
        previous_handler = qInstallMessageHandler(lambda kind, context, message: warnings.append(message))
        previous_hook = sys.excepthook
        sys.excepthook = lambda *error: exceptions.append(error)
        window = None
        try:
            window = MainWindow(startup_config={'count':512, 'backend':'numpy', 'relax_steps':0})
            window.show()
            self.wait_until(lambda: window.frame is not None and not window.busy, window)
            self.assertEqual(window.frame['count'], 512)
            self.assertEqual(window.frame['backend'], 'NumPy')
            window.play_button.click()
            self.wait_until(lambda: window.frame['time'] >= .25, window)
            window.play_button.click()
            self.wait_until(lambda: window.frame['phase'] == 'paused', window)
            window.auto.setChecked(False)
            positions = window.frame['positions'].copy()
            config = dict(window.frame['config'])
            model_time = window.frame['time']

            def unchanged():
                self.assertEqual(window.frame['phase'], 'paused')
                self.assertEqual(window.frame['time'], model_time)
                self.assertEqual(window.frame['config'], config)
                self.assertTrue(np.array_equal(window.frame['positions'], positions))
                self.assertFalse(window.dirty)

            cinematic = self.capture(window.view)
            dense_count = len(window.view.display_stars.positions)
            stellar_count = int(np.count_nonzero(window.frame['kind'] == 0))
            self.assertGreater(dense_count, stellar_count*10)
            self.assertEqual(window.display_style.count(),1)
            window.palette_combo.setCurrentIndex(window.palette_combo.findData('violet'))
            self.app.processEvents()
            self.assertNotEqual(cinematic,self.capture(window.view))
            self.assertEqual(len(window.view.display_stars.positions),dense_count)
            unchanged()

            for slider in window.appearance_sliders.values():
                before = self.capture(window.view)
                initial = slider.value()
                slider.setValue(slider.maximum())
                self.app.processEvents()
                self.assertNotEqual(before, self.capture(window.view))
                unchanged()
                slider.setValue(initial)

            for checkbox in (window.labels, window.trails, window.starfield, window.halos):
                initial = checkbox.isChecked()
                checkbox.click()
                self.app.processEvents()
                self.capture(window.view)
                unchanged()
                checkbox.setChecked(initial)

            cinema = next(button for button in window.findChildren(QPushButton)
                          if button.text() == 'Cinema (C)')
            self.assertTrue(window.side.isVisible())
            cinema.click()
            self.app.processEvents()
            self.assertFalse(window.side.isVisible())
            self.assertFalse(window.camera_bar.isVisible())
            self.capture(window.view)
            unchanged()
            cinema.click()
            self.app.processEvents()
            self.assertTrue(window.side.isVisible())
            self.assertTrue(window.camera_bar.isVisible())

            window.orbit.click()
            initial_yaw = window.view.yaw
            self.wait_until(lambda: window.view.yaw > initial_yaw+.005, window)
            self.assertTrue(window.view.orbit)
            unchanged()
            QTest.mousePress(window.view, Qt.MouseButton.LeftButton, pos=QPoint(100, 100))
            QTest.mouseMove(window.view, QPoint(155, 125))
            QTest.mouseRelease(window.view, Qt.MouseButton.LeftButton, pos=QPoint(155, 125))
            self.app.processEvents()
            self.assertFalse(window.orbit.isChecked())
            self.assertFalse(window.view.orbit)
            self.capture(window.view)
            unchanged()
            self.assertIsNone(window.last_error)
            self.assertFalse(exceptions, repr(exceptions))
            render_warnings = [message for message in warnings if any(
                term in message.lower() for term in ('qpainter', 'paint engine', 'qbackingstore'))]
            self.assertFalse(render_warnings, '\n'.join(render_warnings))
        finally:
            if window is not None:
                window.close()
                self.wait_until(lambda: not window.thread.isRunning(), window)
                self.app.processEvents()
            sys.excepthook = previous_hook
            qInstallMessageHandler(previous_handler)


if __name__ == '__main__':
    unittest.main()
