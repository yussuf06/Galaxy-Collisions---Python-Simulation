"""Native regression for the tracking button and zoom/follow behavior.

Run with the existing Python interpreter on the real desktop. This test never
advances or edits physics while exercising the view with controlled scenes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
from galaxy_app.window import MainWindow


def scene(base, centers, radius, sequence):
    """Two compact star disks placed independently of the untouched solver."""
    centers=np.asarray(centers,dtype=np.float32)
    count=len(base['tracer_positions'])//2
    angle=np.linspace(0,2*np.pi,count,endpoint=False)
    disk=np.column_stack((radius*np.cos(angle),radius*np.sin(angle),np.zeros(count)))
    positions=np.vstack((disk+centers[0],disk+centers[1])).astype(np.float32)
    return {**base,'tracer_positions':positions,'centers':centers,'phase':'paused',
            'time':sequence*.1,'sequence':sequence}


def run():
    if os.environ.get('QT_QPA_PLATFORM','').lower() in ('offscreen','minimal'):
        raise RuntimeError('Tracking camera verification requires native OpenGL.')
    app=QApplication.instance() or QApplication([])
    errors=[]
    previous_hook=sys.excepthook
    sys.excepthook=lambda *exc:errors.append(repr(exc))
    old_warning=QMessageBox.warning
    QMessageBox.warning=lambda *args:errors.append(str(args[-1]))
    window=MainWindow({'count':256,'tracer_count':500,'relax_steps':0})
    window.show()

    def pump(seconds):
        end=time.perf_counter()+seconds
        while time.perf_counter()<end:
            app.processEvents();time.sleep(.002)
            if errors:raise AssertionError(errors)

    def wait(predicate,timeout=12):
        end=time.perf_counter()+timeout
        while time.perf_counter()<end:
            app.processEvents()
            if errors:raise AssertionError(errors)
            if predicate():return
            time.sleep(.002)
        raise AssertionError('Tracking verification timed out: '+window.status.text())

    try:
        wait(lambda:window.frame is not None and not window.busy,timeout=30)
        assert hasattr(window.view,'canvas'),'Software fallback selected'
        assert isinstance(window.auto,QPushButton) and window.auto.isCheckable()
        assert 'Tracking' in window.auto.text(),window.auto.text()
        assert not window.auto.isChecked()
        pump(.2)
        assert window.view.camera.distance==42.,window.view.camera.distance
        base=window.frame
        original_positions=window.worker.engine.positions.copy()
        original_velocities=window.worker.engine.velocities.copy()
        original_config=dict(window.worker.engine.config)
        original_time=window.worker.engine.time
        commands=[]
        window.command.connect(lambda command:commands.append(command))

        wide=scene(base,[[-12.,0.,0.],[12.,0.,0.]],.3,1)
        window.view.set_data(wide)
        window.auto.click()
        assert window.auto.isChecked() and window.view.auto
        wait(lambda:window.view.camera.distance>50.)
        pump(.4)
        wide_distance=float(window.view.camera.distance)

        compact=scene(base,[[3.8,-1.,0.],[4.2,-1.,0.]],.2,2)
        window.view.set_data(compact)
        wait(lambda:window.view.camera.distance<wide_distance*.8)
        wait(lambda:np.linalg.norm(np.asarray(window.view.camera.center)[:2]-np.array([4.,-1.])/.42)<.2)

        # Let the finite smoothing transition finish. A paused, settled tracking
        # view must retain the source renderer's no-continuous-redraw behavior.
        last=None;stable_since=None
        def settled():
            nonlocal last,stable_since
            values=(*np.asarray(window.view.camera.center),float(window.view.camera.distance))
            if values!=last:
                last=values;stable_since=time.perf_counter();return False
            return time.perf_counter()-stable_since>.5
        wait(settled,timeout=15)
        pump(.1)
        before=window.view.render_frames
        pump(.6)
        idle_draws=window.view.render_frames-before
        assert idle_draws<=1,f'Settled paused tracking redrew {idle_draws} times'
        compact_distance=float(window.view.camera.distance)

        native=window.view.canvas.native
        QTest.mousePress(native,Qt.MouseButton.RightButton,pos=QPoint(120,120))
        QTest.mouseMove(native,QPoint(170,145))
        QTest.mouseRelease(native,Qt.MouseButton.RightButton,pos=QPoint(170,145))
        pump(.15)
        assert not window.auto.isChecked() and not window.view.auto,'Manual pan did not disengage tracking'

        window.auto.click();pump(.1)
        window.camera_preset('reset');pump(.15)
        assert not window.auto.isChecked() and not window.view.auto
        assert window.view.camera.distance==42.,window.view.camera.distance
        assert np.allclose(window.view.camera.center,(0,0,0))
        assert np.array_equal(original_positions,window.worker.engine.positions)
        assert np.array_equal(original_velocities,window.worker.engine.velocities)
        assert original_config==window.worker.engine.config
        assert original_time==window.worker.engine.time
        assert not commands,commands
        assert not errors,errors
        window.view.capture().save(str(Path(__file__).with_name('tracking-camera-preview.png')))
        report={'result':'PASS','wide_distance':wide_distance,'compact_distance':compact_distance,
                'settled_idle_draws_in_600ms':idle_draws,'physics_unchanged':True,
                'manual_pan_disengages_tracking':True,'reset_restores_reference_camera':True}
        Path(__file__).with_name('tracking-camera-verification.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report),flush=True)
        return 0
    finally:
        window.close()
        end=time.perf_counter()+10
        while window.thread.isRunning() and time.perf_counter()<end:
            app.processEvents();time.sleep(.005)
        app.processEvents()
        QMessageBox.warning=old_warning;sys.excepthook=previous_hook


if __name__=='__main__':raise SystemExit(run())
