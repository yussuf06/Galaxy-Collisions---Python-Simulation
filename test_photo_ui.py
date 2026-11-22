"""Free simulation UI checks; kept at the old test path for existing runners."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import unittest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from galaxy_app.window import MainWindow

class FreeSimulationUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def wait(self,predicate,window,timeout=35):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            self.app.processEvents()
            if predicate():return
            time.sleep(.005)
        self.fail('Timed out: '+window.status.text())

    def test_exact_entry_presets_and_pause_controls(self):
        warnings=[];window=None;old_warning=QMessageBox.warning
        QMessageBox.warning=lambda *args:warnings.append(str(args[-1]))
        try:
            window=MainWindow({'count':128,'tracer_count':100,'relax_steps':0})
            window.show();self.wait(lambda:window.frame is not None and not window.busy,window)
            self.assertEqual(window.mode,'simulation')
            for retired in ('mode_combo','photo_button','helper_button','goal_bar'):
                self.assertFalse(hasattr(window,retired),retired)
            self.assertEqual(window.display_style.count(),1)
            self.assertEqual(window.display_style.currentData(),'cinematic')
            self.assertTrue(window.custom_settings.isVisible())
            for key,value in (('impact','-0.65'),('speed','0.65'),('massratio','1.20'),('inclination','20')):
                field=window.value_inputs[key]
                field.setFocus();field.selectAll();QTest.keyClicks(field,value);QTest.keyClick(field,Qt.Key.Key_Return)
                self.assertEqual(field.value(),float(value),key)
                self.assertEqual(window.configuration()[key],float(value),key)
                self.assertTrue(window.parameter_help[key].text())
            self.assertIn('120%',window.outputs['massratio'].text())
            window.sliders['impact'].setValue(123)
            self.assertEqual(window.value_inputs['impact'].value(),1.23)
            for preset in ('fastflyby','slowclose','isolated'):
                window.encounter_combo.setCurrentIndex(window.encounter_combo.findData(preset))
                self.assertTrue(window.custom_settings.isVisible(),preset)
            window.encounter_combo.setCurrentIndex(window.encounter_combo.findData('slowclose'))
            window.apply_button.click()
            self.wait(lambda:not window.busy and window.frame['config']['speed']==.65,window)
            self.assertEqual(window.value_inputs['inclination'].value(),20)
            window.play_button.click();self.wait(lambda:window.frame['phase']=='running',window)
            self.assertTrue(all(not field.isEnabled() for field in window.value_inputs.values()))
            window.play_button.click();self.wait(lambda:window.frame['phase']=='paused',window)
            self.assertTrue(all(field.isEnabled() for field in window.value_inputs.values()))
            self.assertFalse(warnings,warnings)
        finally:
            QMessageBox.warning=old_warning
            if window is not None:
                window.close();self.wait(lambda:not window.thread.isRunning(),window)

if __name__=='__main__':unittest.main()
