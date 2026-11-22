"""Exercise real Qt controls and Python physics without a physical display."""
from __future__ import annotations
import os,time,tempfile
from pathlib import Path

def run():
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    os.environ.setdefault('XDG_CACHE_HOME',str(Path(tempfile.gettempdir())/'galaxy-qt-cache'))
    import numpy as np
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt,QPoint
    from .window import MainWindow
    app=QApplication.instance() or QApplication([])
    messages=[]
    QMessageBox.warning=lambda *args:messages.append(('warning',str(args[-1])))
    QMessageBox.information=lambda *args:messages.append(('info',str(args[-1])))
    QMessageBox.exec=lambda self:0
    w=MainWindow();w.show()
    def wait(test,timeout=45):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            app.processEvents()
            if test():return
            time.sleep(.005)
        raise AssertionError('Timed out; status='+w.status.text()+';messages='+str(messages))
    try:
        wait(lambda:w.frame is not None and not w.busy)
        assert w.frame['positions'].shape==(1024,3)
        assert set(w.frame['kind'])=={0,1}
        original_yaw=w.view.yaw
        QTest.mousePress(w.view,Qt.MouseButton.LeftButton,pos=QPoint(100,100));QTest.mouseMove(w.view,QPoint(150,120));QTest.mouseRelease(w.view,Qt.MouseButton.LeftButton,pos=QPoint(150,120))
        assert w.view.yaw != original_yaw
        QTest.mousePress(w.view,Qt.MouseButton.RightButton,pos=QPoint(150,150));QTest.mouseMove(w.view,QPoint(190,160));QTest.mouseRelease(w.view,Qt.MouseButton.RightButton,pos=QPoint(190,160))
        assert not w.auto.isChecked() and not w.view.auto
        w.camera_preset('reset');assert w.auto.isChecked()
        image=w.view.grab().toImage();assert image.width()>300
        w.play_button.click();wait(lambda:w.frame['time']>1.65)
        w.play_button.click();wait(lambda:w.frame['phase']=='paused')
        t=w.frame['time'];w.rewind_button.click();wait(lambda:w.frame['time']<t-.5)
        assert w.frame['phase']=='paused'
        w.quality.setCurrentIndex(0);w.sliders['impact'].setValue(230);w.apply_button.click()
        wait(lambda:not w.busy and w.frame['phase']=='ready' and w.frame['count']==512)
        assert w.frame['config']['impact']==2.3
        with tempfile.TemporaryDirectory() as folder:
            checkpoint=str(Path(folder)/'test.npz')
            original=w.frame['positions'].copy()
            w.last_checkpoint=None;w.command.emit({'action':'save','path':checkpoint});wait(lambda:getattr(w,'last_checkpoint',None)==('save',checkpoint))
            w.play_button.click();wait(lambda:w.frame['time']>.3)
            w.last_checkpoint=None;w.command.emit({'action':'load','path':checkpoint});wait(lambda:getattr(w,'last_checkpoint',None)==('load',checkpoint));assert w.frame['time']==0
            assert np.array_equal(original,w.frame['positions'])
        assert w.mode=='simulation' and not hasattr(w,'mode_combo')
        assert w.custom_settings.isVisible()
        assert w.display_style.count()==1 and w.display_style.currentData()=='cinematic'
        w.value_inputs['speed'].setValue(.65);w.value_inputs['massratio'].setValue(1.2)
        assert w.configuration()['speed']==.65 and w.sliders['massratio'].value()==120
        assert '120%' in w.outputs['massratio'].text()
        w.encounter_combo.setCurrentIndex(w.encounter_combo.findData('slowclose'))
        assert w.custom_settings.isVisible() and w.value_inputs['impact'].value()==.65
        w.apply_button.click();wait(lambda:not w.busy and w.frame['config']['speed']==.65)
        w.halos.setChecked(True);w.camera_preset('front');app.processEvents();w.camera_preset('reset')
        # Snapshot actual Qt widgets for visual inspection when requested.
        output=os.environ.get('GALAXY_TEST_CAPTURE')
        if output:
            w.resize(1320,860);app.processEvents();w.grab().save(output,'PNG')
        w.play_button.click();wait(lambda:w.frame['phase']=='running');assert w.frame['mode']=='simulation'
        w.play_button.click();wait(lambda:w.frame['phase']=='paused')
        seed=w.frame['config']['seed'];w.new_button.click()
        wait(lambda:not w.busy and w.frame['phase']=='ready' and w.frame['config']['seed']!=seed,timeout=90)
        assert not [m for m in messages if m[0]=='warning'],messages
        print('PASS: real offscreen Qt rendering, play/pause, rewind, settings, state round-trip, numeric inputs, always-visible starting conditions, original style only, new random encounter and clean thread shutdown.')
        return 0
    finally:
        w.close();wait(lambda:not w.thread.isRunning(),timeout=45)
        app.processEvents()
