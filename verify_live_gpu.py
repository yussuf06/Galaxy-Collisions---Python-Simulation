"""Verify the actual window, live solver, dense stars and hardware renderer."""
import json
import sys
import time
from pathlib import Path
import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from galaxy_app.window import MainWindow

app = QApplication([])
failures = []
sys.excepthook = lambda *exc: failures.append(repr(exc))
QMessageBox.warning = lambda *args: failures.append(str(args[-1]))
window = MainWindow()
window.show()
started = time.perf_counter()
stage = 'preparing'
ready_at = None
moving_at = None
frame_count = None
initial = None
report = {}
result = 1

def check():
    global stage, ready_at, moving_at, frame_count, initial, report, result
    now = time.perf_counter()
    try:
        if failures: raise AssertionError(failures)
        if now-started > 55: raise AssertionError('Native integration timed out: '+window.status.text())
        if stage == 'preparing' and window.frame is not None and not window.busy:
            assert hasattr(window.view, 'canvas'), 'Software fallback was selected'
            assert len(window.frame['tracer_positions']) == 30000
            assert window.view.canvas.native.context().isValid()
            ready_at = now; stage = 'ready'
        elif stage == 'ready' and now-ready_at >= 1.:
            window.view.capture().save(str(Path(__file__).with_name('live-gpu-ready.png')))
            initial = window.frame['tracer_positions'].copy()
            window.play()
            moving_at = now; frame_count = window.view.render_frames; stage = 'moving'
        elif stage == 'moving' and now-moving_at >= 5.:
            elapsed = now-moving_at
            fps = (window.view.render_frames-frame_count)/elapsed
            assert window.frame['time'] > .5, window.status.text()
            assert not np.array_equal(initial, window.frame['tracer_positions'])
            assert np.isfinite(window.frame['tracer_positions']).all()
            assert fps >= 25, f'Live GPU draw rate too low: {fps:.1f}'
            report = dict(renderer=window.view.gpu_renderer, moving_draw_fps=round(fps,2),
                          model_time=window.frame['time'], elapsed_seconds=round(elapsed,2),
                          stars=len(window.frame['tracer_positions']),
                          gravity_particles=window.frame['count'], step_ms=window.frame['step_ms'],
                          native_framebuffer=list(window.view.canvas.physical_size), result='PASS')
            window.play(); stage = 'pausing'
        elif stage == 'pausing' and window.frame['phase'] == 'paused':
            window.view.capture().save(str(Path(__file__).with_name('live-gpu-moving.png')))
            Path(__file__).with_name('live-gpu-verification.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report), flush=True)
            result = 0; timer.stop(); window.close(); app.quit()
    except Exception as exc:
        print('FAIL: '+repr(exc), flush=True)
        timer.stop(); window.close(); app.quit()

timer = QTimer(); timer.setInterval(50); timer.timeout.connect(check); timer.start()
app.exec()
raise SystemExit(result)
