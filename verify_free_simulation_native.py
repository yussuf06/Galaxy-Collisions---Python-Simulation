"""Verify the real OpenGL window and capture the updated controls."""
import os
import sys
from pathlib import Path
import time

ROOT=Path(__file__).resolve().parent
os.environ['NUMBA_CACHE_DIR']=str(ROOT/'phase-export-cache')
sys.dont_write_bytecode=True
sys.path.insert(0,r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop')
import galaxy_app
if '--installed' not in sys.argv:
    galaxy_app.__path__.insert(0,str(ROOT/'free-simulation-ui/galaxy_app'))
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QMessageBox,QComboBox,QScrollArea
from galaxy_app.window import MainWindow

app=QApplication([])
app.setQuitOnLastWindowClosed(False)
window=MainWindow({'count':512})
window.resize(1500,1000);window.show()
started=time.monotonic();state='waiting';result=1;errors=[]
sys.excepthook=lambda *exc:errors.append(str(exc))
QMessageBox.warning=lambda *args:errors.append(str(args[-1]))

def tick():
    global state,result
    try:
        if state=='closing':
            if not window.thread.isRunning():timer.stop();app.quit()
            return
        if errors:raise AssertionError(errors)
        if time.monotonic()-started>65:raise TimeoutError(window.status.text())
        if state=='waiting' and window.frame is not None and not window.busy:
            assert window.mode=='simulation' and not hasattr(window,'mode_combo')
            assert not hasattr(window,'photo_button') and not hasattr(window,'helper_button')
            assert window.display_style.count()==1
            assert window.custom_settings.isVisible()
            assert window.worker.simulation_only
            assert hasattr(window.view,'canvas') and window.view.canvas.native.context().isValid()
            window.encounter_combo.setCurrentIndex(window.encounter_combo.findData('slowclose'))
            for key,value in dict(impact=.65,speed=.65,massratio=1.,inclination=20.).items():
                assert window.value_inputs[key].value()==value
            assert window.view.detail=='cinematic'
            state='capture'
        elif state=='capture':
            folder=ROOT/'free-simulation-ui'
            window.grab().save(str(folder/'free-simulation-window.png'))
            window.custom_settings.grab().save(str(folder/'numeric-starting-conditions.png'))
            print('PASS: native OpenGL, free simulation only, numeric values and meanings, one original style.',flush=True)
            result=0;state='closing';window.close()
    except Exception as exc:
        print('FAIL:',repr(exc),flush=True)
        state='closing';window.close()

timer=QTimer();timer.setInterval(100);timer.timeout.connect(tick);timer.start()
app.exec()
raise SystemExit(result)
