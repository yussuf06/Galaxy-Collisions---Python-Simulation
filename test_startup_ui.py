"""Offscreen regression for visible startup failure and recovery.

Run separately with: python -m unittest test_startup_ui -v
This exercises the real Qt worker thread and controls, then retries real physics.
"""
from __future__ import annotations

import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import re
import threading
import time
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication, QMessageBox

from galaxy_app.window import MainWindow


class StartupUiRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def wait_until(self, predicate, window, timeout=45):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.005)
        self.fail('Timed out; status=' + window.status.text())

    def test_failed_startup_stays_visible_and_retry_reaches_galaxies(self):
        release_failure = threading.Event()
        warnings = []
        window = None

        def failing_engine(config, progress=None):
            if progress:
                progress('Testing startup error recovery', .1)
            if not release_failure.wait(10):
                raise RuntimeError('Test did not release startup failure')
            raise ImportError('Injected startup dependency failure')

        try:
            with patch.object(QMessageBox, 'warning', side_effect=lambda *args: warnings.append(args[-1])):
                with self.assertLogs('galaxy_app.worker', level='ERROR'), patch(
                    'galaxy_app.worker.NBody', side_effect=failing_engine
                ):
                    window = MainWindow()
                    window.show()
                    # Keep the worker in a controlled preparation stage while the
                    # UI event loop must remain live and display elapsed time.
                    self.wait_until(
                        lambda: bool(re.search(r'[1-9]\d*s elapsed', window.status.text())),
                        window, timeout=8,
                    )
                    self.assertTrue(window.busy)
                    self.assertIn('Testing startup error recovery', window.status.text())
                    self.assertIn('elapsed', window.view.preparation_text)
                    self.assertFalse(window.play_button.isEnabled())
                    release_failure.set()
                    self.wait_until(lambda: window.last_error is not None and not window.busy, window)
                    self.assertIsNone(window.frame)
                    self.assertEqual(window.play_button.text(), 'Retry preparation')
                    self.assertTrue(window.play_button.isEnabled())
                    self.assertFalse(window.busy_bar.isVisible())
                    self.assertTrue(window.error_label.isVisible())
                    self.assertIn('ImportError', window.error_label.text())
                    self.assertIn('Injected startup dependency failure', window.error_label.text())
                    self.assertIn('Injected startup dependency failure', window.view.preparation_text)
                    self.assertIn('Retry preparation', window.view.preparation_text)
                    self.assertEqual(len(warnings), 1)
                    # The warning function has returned; the same error remains
                    # visible independently of its dismissed dialog.
                    self.app.processEvents()
                    self.assertTrue(window.error_label.isVisible())

                # Restore the actual engine and activate the visible retry control.
                window.quality.setCurrentIndex(0)
                window.play_button.click()
                self.wait_until(lambda: window.frame is not None and not window.busy, window)
                self.assertEqual(window.frame['phase'], 'ready')
                self.assertEqual(window.frame['positions'].shape, (512, 3))
                self.assertTrue(np.isfinite(window.frame['positions']).all())
                self.assertEqual(set(window.frame['origin']), {0, 1})
                self.assertIs(window.view.data, window.frame)
                self.assertIsNone(window.last_error)
                self.assertFalse(window.error_label.isVisible())
                self.assertFalse(window.busy_bar.isVisible())
                self.assertTrue(window.play_button.isEnabled())
                self.assertNotIn('Preparing', window.play_button.text())
                self.assertIn('READY', window.status.text())
                self.assertNotIn('elapsed', window.status.text())
                self.assertEqual(len(warnings), 1, 'Retry must not raise another error')
                self.assertFalse(window.view.grab().isNull())
        finally:
            release_failure.set()
            if window is not None:
                window.close()
                self.wait_until(lambda: not window.thread.isRunning(), window)
                self.app.processEvents()


if __name__ == '__main__':
    unittest.main()
