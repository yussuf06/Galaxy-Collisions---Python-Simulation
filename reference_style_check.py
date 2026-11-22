"""Native pixel parity and idle-work checks against the supplied reference.

This test intentionally uses the real desktop OpenGL backend. It builds the
reference scene literally, feeds both views the same source-generated arrays,
and compares their raw framebuffers before benchmarking each view separately.
"""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from PySide6.QtCore import QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from vispy import app as vispy_app, scene
from vispy.io import write_png

from galaxy_app.gpu_view import GalaxyView


REFERENCE = Path(r'C:\Users\yusuf\Desktop\space shit\main.py')
OUTPUT = Path(__file__).resolve().parent


def source_generator():
    """Compile only the user-supplied generator, never its application loop."""
    tree = ast.parse(REFERENCE.read_text(encoding='utf-8-sig'), filename=str(REFERENCE))
    function = next(node for node in tree.body
                    if isinstance(node, ast.FunctionDef) and node.name == 'generate_cinematic_galaxy')
    namespace = {'np':np, 'G':1.5}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(REFERENCE), 'exec'), namespace)
    return namespace['generate_cinematic_galaxy']


def fixture():
    generate = source_generator()
    previous_rng = np.random.get_state()
    try:
        np.random.seed(23)
        a = generate(np.array([-13., 4., -2.5]), np.array([1.25, -.35, .15]),
                     75., 15000, (30, 15, 0), 'blue')
        b = generate(np.array([13., -4., 2.5]), np.array([-1.55, .35, -.15]),
                     60., 15000, (-40, 25, 10), 'gold')
    finally:
        np.random.set_state(previous_rng)
    positions = np.vstack((a[0], b[0])).astype(np.float32)
    colors = np.vstack((a[2], b[2])).astype(np.float32)
    origin = np.repeat(np.array([0, 1], np.int8), 15000)
    ids = np.r_[np.arange(0, 15000, 60), np.arange(15000, 30000, 60)]
    return dict(positions=positions[ids], kind=np.zeros(len(ids),np.int8), origin=origin[ids],
                centers=np.array([[-13., 4., -2.5],[13., -4., 2.5]]),
                config={'seed':23, 'isolated':False, 'reference_length_scale':1.0},
                time=0., phase='paused', mode='simulation', count=len(ids), backend='Numba',
                sequence=1, tracer_positions=positions, tracer_colors=colors, tracer_origin=origin)


def run():
    if os.environ.get('QT_QPA_PLATFORM','').lower() in ('offscreen','minimal'):
        raise RuntimeError('Reference parity requires the real native OpenGL backend.')
    qt_app = QApplication.instance() or QApplication([])
    warnings, errors = [], []
    previous_handler = qInstallMessageHandler(lambda kind, context, message:warnings.append(message))
    previous_hook = sys.excepthook
    sys.excepthook = lambda *error:errors.append(repr(error))
    view = GalaxyView()
    view.setWindowTitle('Exact reference style verification')
    view.resize(1100,700)
    frame = fixture()
    view.auto = False; view.labels = False; view.halos = False; view.tracks = False
    view.exposure = 1.; view.star_size = 1.; view.background = True; view.orbit = False
    view.set_data(frame)
    view.show()
    # The source uses one additive galaxy visual and the default background
    # marker blend state. No postprocessing, second halo, or multisampling.
    direct = scene.SceneCanvas(keys='interactive', bgcolor='#020308', show=False,
                               app=vispy_app.use_app('pyside6'), size=(1100,700))
    direct.native.setWindowTitle('Unmodified reference rendering recipe')
    direct_view = direct.central_widget.add_view()
    direct_view.camera = scene.cameras.TurntableCamera(fov=45, distance=42, elevation=25, azimuth=30)
    sky_visual = scene.visuals.Markers(parent=direct_view.scene)
    direct_stars = scene.visuals.Markers(parent=direct_view.scene)
    direct_stars.set_gl_state('additive', depth_test=False)
    direct_stars.set_data(frame['tracer_positions'], edge_width=0,
                          face_color=frame['tracer_colors'], size=3.5)
    direct_draws = [0]
    direct.events.draw.connect(lambda event:direct_draws.__setitem__(0,direct_draws[0]+1))

    def pump(seconds):
        deadline=time.perf_counter()+seconds
        while time.perf_counter()<deadline:
            qt_app.processEvents(); time.sleep(.001)
        if errors: raise AssertionError(errors)

    animation = QTimer(); animation.setInterval(16); animation.timeout.connect(view.animate)
    report = {}
    try:
        animation.start(); pump(.3)
        assert view.canvas.native.context().isValid(), 'No valid native OpenGL context'
        assert view._active_count==30000, view._active_count
        assert view.camera.fov==45 and view.camera.distance==42, (view.camera.fov,view.camera.distance)
        assert view.camera.azimuth==30 and view.camera.elevation==25
        assert not hasattr(view,'glow_visual'), 'The extra glow draw is still present'
        assert view.canvas.context.config['samples']==0, view.canvas.context.config
        sky = np.asarray(view.sky_positions,dtype=np.float32)
        sky_visual.set_data(sky, edge_width=0, face_color=(1,1,1,.35), size=1.8)
        direct.native.resize(*view.canvas.size)
        direct.show(); pump(.3)
        expected = direct.render(alpha=False)
        observed = view.canvas.render(alpha=False)
        assert observed.shape==expected.shape, (observed.shape,expected.shape)
        difference = np.abs(observed.astype(np.int16)-expected.astype(np.int16))
        mean_error=float(difference.mean())
        changed_pixels=int(np.count_nonzero(np.max(difference,axis=2)>2))
        changed_fraction=changed_pixels/(observed.shape[0]*observed.shape[1])
        assert mean_error<=.15 and changed_fraction<=.001, (mean_error,changed_fraction)
        write_png(str(OUTPUT/'reference-direct.png'),expected)
        write_png(str(OUTPUT/'reference-matched.png'),observed)

        direct.show(False); pump(.25)
        before_draws=view.render_frames; before_uploads=view.upload_count
        pump(.6)
        idle_draws=view.render_frames-before_draws
        idle_uploads=view.upload_count-before_uploads
        assert idle_draws<=1 and idle_uploads==0, (idle_draws,idle_uploads)
        view.yaw+=.15; view.animate(); pump(.15)
        assert view.render_frames>before_draws, 'Camera interaction did not redraw'
        assert view.upload_count==before_uploads, 'Camera interaction re-uploaded unchanged stars'
        camera_pixels=view.canvas.render(alpha=False)
        assert not np.array_equal(camera_pixels,observed), 'Camera view did not change'
        view.exposure=.6; view.animate(); pump(.15)
        assert view.upload_count>before_uploads, 'Appearance change was not uploaded'
        view.exposure=1.; view.reset_camera(); view.auto=False
        view.set_data(frame); view.animate(); pump(.15)

        # Same vertex arrays, frame cadence, native dimensions and marker style.
        # These draw rates measure renderer workload, not GPU utilization.
        animation.stop()
        base=frame['tracer_positions']
        benchmark_results={}
        for name in ('reference','matched'):
            if name=='reference':
                view.hide(); direct.show()
            else:
                direct.show(False); view.show()
            pump(.2)
            tick=[0]
            def update_frame():
                tick[0]+=1
                p=base.copy();p[:,0]+=.04*np.sin(tick[0]*.02)
                if name=='reference':
                    direct_stars.set_data(p,edge_width=0,face_color=frame['tracer_colors'],size=3.5)
                    direct.update()
                else:
                    current={**frame,'time':tick[0]*.015,'phase':'running','sequence':tick[0]+1,
                             'tracer_positions':p}
                    view.set_data(current);view.animate()
            driver=QTimer();driver.setInterval(16);driver.timeout.connect(update_frame)
            count_before=direct_draws[0] if name=='reference' else view.render_frames
            started=time.perf_counter();driver.start();pump(2.5);driver.stop()
            elapsed=time.perf_counter()-started
            count_after=direct_draws[0] if name=='reference' else view.render_frames
            benchmark_results[name]=dict(draw_fps=round((count_after-count_before)/elapsed,2),
                                         submitted_frames=tick[0])
        assert not errors,errors
        report=dict(result='PASS',renderer=view.gpu_renderer,
                    framebuffer_size=[observed.shape[1],observed.shape[0]],stars=30000,
                    mean_absolute_pixel_error=mean_error,changed_pixel_fraction=changed_fraction,
                    idle_draws_in_600ms=idle_draws,idle_uploads_in_600ms=idle_uploads,
                    render_benchmark=benchmark_results,warnings=warnings)
        (OUTPUT/'reference-style-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report),flush=True)
        return 0
    finally:
        animation.stop();direct.close();view.close();qt_app.processEvents()
        qInstallMessageHandler(previous_handler);sys.excepthook=previous_hook


if __name__=='__main__':
    raise SystemExit(run())
