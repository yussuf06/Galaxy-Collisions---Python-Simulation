"""Native GPU integration/benchmark; deliberately refuses an offscreen fallback.

Run on this Windows desktop with the existing interpreter:
    python test_gpu_view.py
Writes gpu-verification.json and a full-resolution gpu-verification.png.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import numpy as np
from PySide6.QtCore import QTimer, qInstallMessageHandler
from PySide6.QtWidgets import QApplication
from galaxy_app.dense_stars import generate_cinematic_galaxy
from galaxy_app.gpu_view import GalaxyView


def reference_frame():
    rng = np.random.RandomState(23)
    a = generate_cinematic_galaxy(np.array([-13., 4., -2.5]), np.zeros(3), 75.,
                                  15000, (30, 15, 0), 'blue', rng=rng)
    b = generate_cinematic_galaxy(np.array([13., -4., 2.5]), np.zeros(3), 60.,
                                  15000, (-40, 25, 10), 'gold', rng=rng)
    dense = np.vstack((a[0], b[0])).astype(np.float32)
    colors = np.vstack((a[2], b[2])).astype(np.float32)
    origin = np.repeat(np.array([0, 1], np.int8), 15000)
    ids = np.concatenate((np.arange(0, 15000, 60), np.arange(15000, 30000, 60)))
    stars = dense[ids]
    halos = rng.normal(size=(128, 3))*5
    halos[:64] += [-13., 4., -2.5]; halos[64:] += [13., -4., 2.5]
    positions = np.vstack((stars, halos)).astype(np.float32)
    return dict(positions=positions, kind=np.r_[np.zeros(len(stars), np.int8), np.ones(128, np.int8)],
                origin=np.r_[origin[ids], np.repeat(np.array([0, 1], np.int8), 64)],
                centers=np.array([[-13., 4., -2.5], [13., -4., 2.5]]),
                config={'seed':23, 'isolated':False, 'reference_length_scale':1.}, time=0., phase='paused', mode='simulation',
                count=len(positions), backend='Numba', sequence=1,
                tracer_positions=dense, tracer_colors=colors, tracer_origin=origin)


def run():
    if os.environ.get('QT_QPA_PLATFORM', '').lower() in ('offscreen', 'minimal'):
        raise RuntimeError('This test requires the real desktop OpenGL backend, not offscreen/minimal.')
    app = QApplication.instance() or QApplication([])
    warnings = []; exceptions = []
    previous_handler = qInstallMessageHandler(lambda kind, context, msg: warnings.append(msg))
    previous_hook = sys.excepthook
    sys.excepthook = lambda *error: exceptions.append(repr(error))
    view = GalaxyView(); view.resize(1280, 800); view.setWindowTitle('Galaxy GPU verification')
    view.set_data(reference_frame()); view.show()
    timer = QTimer(); timer.setInterval(16); timer.timeout.connect(view.animate); timer.start()
    def pump(seconds):
        deadline = time.perf_counter()+seconds
        while time.perf_counter() < deadline:
            app.processEvents(); time.sleep(.001)
    report = {}
    try:
        pump(2.)
        assert view.canvas.native.context().isValid(), 'OpenGL widget has no valid native context'
        assert not exceptions, exceptions
        assert view._active_count == 30000, f'Expected reference 30k stars, got {view._active_count}'
        assert view.gpu_renderer != 'initializing', 'No GPU draw event was observed'
        software = ('llvmpipe', 'software rasterizer', 'gdi generic', 'swiftshader')
        assert not any(name in view.gpu_renderer.lower() for name in software), view.gpu_renderer
        view.auto = False; view.orbit = False
        first = view.canvas.render(alpha=False)
        physical = tuple(view.canvas.physical_size)
        assert first.shape[:2] == (physical[1], physical[0]), (first.shape, physical)
        assert physical[0] >= 1200 and physical[1] >= 750, physical
        blue = (first[:, :, 2].astype(int)-first[:, :, 0].astype(int)) > 20
        gold = (first[:, :, 0].astype(int)-first[:, :, 2].astype(int)) > 20
        assert np.count_nonzero(blue) > 50, 'No visible blue galaxy in GPU framebuffer'
        assert np.count_nonzero(gold) > 50, 'No visible gold galaxy in GPU framebuffer'
        # Native perspective auto-fit must also work after rapid expansion and
        # a different camera angle, rather than only the initial static pair.
        expanded = reference_frame()
        expanded['tracer_positions'] = expanded['tracer_positions']*np.array([1.7, 1.3, 1.2], np.float32)
        expanded['centers'] = expanded['centers']*np.array([1.7, 1.3, 1.2])
        view.set_data(expanded); view.auto = True; view.yaw = 1.15; view.pitch = .6
        view.animate(); pump(2.5); view.animate()
        mapped = view.scene_view.scene.node_transform(view.canvas.scene).map(expanded['tracer_positions'])
        px = mapped[:, :2]/mapped[:, 3, None]
        width, height = view.canvas.size
        inside = ((mapped[:, 3] > 0) & (px[:, 0] >= 0) & (px[:, 0] <= width)
                  & (px[:, 1] >= 0) & (px[:, 1] <= height))
        assert inside.mean() >= .985, f'Native auto-fit clips {1-inside.mean():.2%} of luminous stars'
        view.set_data(reference_frame()); view.auto = False; view.yaw = -.35; view.pitch = np.radians(65)
        view.extent = 20.; view.center[:] = 0; view.animate()
        view.yaw += .3; view.animate(); pump(.1)
        moved = view.canvas.render(alpha=False)
        assert not np.array_equal(first, moved), 'GPU camera did not change the framebuffer'
        view.set_detail('raw'); view.animate(); pump(.1)
        assert view._active_count == 500, view._active_count
        view.set_detail('cinematic'); view.animate(); pump(.1)
        assert view._active_count == 30000
        view.orbit = True
        before = view.render_frames; started = time.perf_counter()
        pump(5.)
        elapsed = time.perf_counter()-started; fps = (view.render_frames-before)/elapsed
        assert not exceptions, exceptions
        assert fps >= 25., f'GPU camera benchmark too slow: {fps:.1f} actual draws/s'
        view.orbit = False
        view.capture().save(str(Path(__file__).with_name('gpu-verification.png')), 'PNG')
        report = dict(renderer=view.gpu_renderer, vendor=view.gpu_vendor, draw_fps=round(fps, 2),
                      framebuffer_size=list(physical), uploaded_stars=view._active_count,
                      colored_blue_pixels=int(np.count_nonzero(blue)), colored_gold_pixels=int(np.count_nonzero(gold)),
                      native_autofit_visible_fraction=float(inside.mean()),
                      warnings=warnings, result='PASS')
        Path(__file__).with_name('gpu-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report), flush=True)
        return 0
    finally:
        timer.stop(); view.close(); app.processEvents()
        qInstallMessageHandler(previous_handler); sys.excepthook = previous_hook


if __name__ == '__main__':
    raise SystemExit(run())
