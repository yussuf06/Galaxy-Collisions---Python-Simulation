"""Photo geometry remains registered and never becomes an N-body state."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import time
import unittest
import numpy as np
from PySide6.QtWidgets import QApplication
from galaxy_app.reference_shapes import IDENTIFIERS,ASSET_FOLDER,reference_frame
from galaxy_app.window import MainWindow

class ReferenceAssetsTests(unittest.TestCase):
    def test_source_registration_and_read_only_clouds(self):
        for ident in IDENTIFIERS:
            frame=reference_frame(ident)
            with np.load(ASSET_FOLDER/f'{ident}.npz',allow_pickle=False) as data:
                w,h=data['source_size'];xy=data['source_xy'];scale=24/max(w,h)
                np.testing.assert_allclose(frame['positions'][:,0],(xy[:,0]-w/2)*scale,atol=2e-6)
                np.testing.assert_allclose(frame['positions'][:,1],(h/2-xy[:,1])*scale,atol=2e-6)
            self.assertFalse(frame['positions'].flags.writeable)
            self.assertTrue(np.all((frame['tracer_colors']>=0)&(frame['tracer_colors']<=1)))
            self.assertEqual(frame['mode'],'illustration')
            self.assertIn('not measured',frame['illustration']['depth'])
            self.assertTrue(frame['illustration']['source'].startswith('https://science.nasa.gov/'))

class ReferenceUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def wait(self,predicate,window,timeout=35):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            self.app.processEvents()
            if predicate():return
            time.sleep(.005)
        self.fail('Timed out: '+window.status.text())

    def test_shape_switch_rotation_reset_and_return_preserve_gravity(self):
        window=MainWindow({'count':512,'tracer_count':3000,'relax_steps':0,'backend':'numpy'})
        try:
            window.show();self.wait(lambda:window.frame is not None and not window.busy,window)
            window.play_button.click();self.wait(lambda:window.frame['time']>=.05,window)
            window.play_button.click()
            self.wait(lambda:window.frame['phase']=='paused',window)
            saved=window.worker.snapshot()
            config=window.configuration().copy();old_exposure=window.view.exposure
            for ident in IDENTIFIERS:
                window.shape_buttons[ident].click();self.app.processEvents()
                self.assertEqual(window.illustration_id,ident)
                self.assertEqual(window.view.data['illustration']['id'],ident)
                # Illustration handlers are retained; their entry panel is removed.
                self.assertFalse(window.shape_group.isVisible())
                self.assertFalse(window.shape_preview_button.isVisible())
                self.assertFalse(window.custom_settings.isVisible())
                self.assertFalse(window.save_checkpoint_button.isEnabled())
                self.assertFalse(window.auto.isEnabled())
                self.assertIn('no gravity evolution',window.mode_note.text())
                # A real queued pause frame must not overwrite the illustration.
                illustration=window.view.data
                window.on_message(dict(window.frame))
                self.assertIs(window.view.data,illustration)
                positions=illustration['positions'].copy()
                window.play_button.click();self.assertTrue(window.orbit.isChecked())
                window.view.animate();self.app.processEvents()
                window.reset_button.click()
                self.assertFalse(window.orbit.isChecked())
                self.assertEqual(window.view.yaw,0.)
                np.testing.assert_array_equal(window.view.data['positions'],positions)
                self.assertFalse(window.view.grab().isNull())
            current=window.worker.snapshot()
            for key in ('positions','velocities'):
                np.testing.assert_array_equal(current[key],saved[key])
            self.assertEqual(current['ticks'],saved['ticks'])
            window.shape_preview_button.click();self.app.processEvents()
            self.assertIsNone(window.illustration_id)
            self.assertIs(window.view.data,window.frame)
            self.assertEqual(window.configuration(),config)
            self.assertEqual(window.view.exposure,old_exposure)
            self.assertTrue(window.custom_settings.isVisible())
            self.assertTrue(window.save_checkpoint_button.isEnabled())
            self.assertFalse(window.shape_preview_button.isVisible())
            self.assertEqual(window.frame['phase'],'paused')
            window.play_button.click();self.wait(lambda:window.frame['phase']=='running',window)
            window.play_button.click();self.wait(lambda:window.frame['phase']=='paused',window)
            self.assertGreater(window.worker.engine.ticks,saved['ticks'])
        finally:
            window.close();self.wait(lambda:not window.thread.isRunning(),window)

if __name__=='__main__':unittest.main()
