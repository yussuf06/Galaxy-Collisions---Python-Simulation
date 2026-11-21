"""Export four moments from the installed app without modifying its sources."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.environ['NUMBA_CACHE_DIR'] = str(ROOT / 'phase-export-cache')
sys.dont_write_bytecode = True
sys.path.insert(0, r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop')

import json
import math
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QFont
from galaxy_app.physics import NBody
from galaxy_app.dense_stars import DenseStars
from galaxy_app.encounters import apply_preset
from galaxy_app.gpu_view import GalaxyView

OUT = ROOT / 'our-simulation-phases'
OUT.mkdir(exist_ok=True)
config = apply_preset({'count':1024, 'seed':735128, 'tracer_count':15000}, 'slowclose')
engine = NBody(config)
tracers = DenseStars.from_engine(engine, 15000)
frames = []

def remember(label):
    frame = dict(positions=engine.positions.astype(np.float32).copy(),
                 kind=engine.kind.copy(), origin=engine.origin.copy(),
                 centers=engine.centers().copy(), time=engine.time,
                 config=dict(engine.config), phase='paused', mode='simulation',
                 tracer_positions=tracers.positions.astype(np.float32).copy(),
                 tracer_colors=tracers.colors.copy(), tracer_origin=tracers.origin.copy())
    frames.append((label, frame, engine.metrics()))
    print(label, 'time', engine.time, 'separation', frame['centers'], flush=True)

remember('1. Initial approach')
passage = None
while engine.time < 30.:
    engine.step(4)
    tracers.advance(engine, engine.time-tracers.time)
    if passage is None and engine.after_pericentre:
        passage = engine.time
        remember('2. First close passage')
    elif passage is not None and len(frames) == 2 and engine.time >= passage+10.:
        remember('3. Tidal evolution after passage')
    if engine.ticks % 200 == 0:
        print('Computing model time', engine.time, flush=True)
remember('4. Later outcome of the encounter')
assert len(frames) == 4

app = QApplication.instance() or QApplication([])
view = GalaxyView()
view.resize(1440, 900)
view.setWindowTitle('Galaxy Encounter - exporting four actual simulation moments')
view.show()
app.processEvents()
view.yaw = math.radians(0)
view.pitch = math.radians(18)
# Preserve orientation; frame each actual snapshot as the tracking camera does.
report = []
sheet = QImage(1440, 1000, QImage.Format.Format_RGB32)
sheet.fill(QColor('#020308'))
painter = QPainter(sheet)
for i, (label, frame, metrics) in enumerate(frames):
    center = np.mean(frame['centers'], axis=0)
    radius = np.percentile(np.linalg.norm(frame['tracer_positions']-center, axis=1), 99.)
    view.center = center
    view._manual_distance = max(38., float(radius/.42*2.7))
    view.set_data(frame)
    view.update()
    app.processEvents()
    pixmap = view.capture()
    assert not pixmap.isNull()
    filename = OUT / f'phase-{i+1}.png'
    pixmap.save(str(filename))
    x, y = (i % 2)*720, (i//2)*500
    painter.drawPixmap(x, y, 720, 450, pixmap)
    painter.setPen(QColor('#d7e7fa'))
    painter.setFont(QFont('Segoe UI', 13))
    painter.drawText(x+18, y+477, label)
    report.append(dict(label=label, model_time=frame['time'], metrics=metrics,
                       camera_distance=view._manual_distance, image=str(filename)))
    np.savez_compressed(OUT/f'phase-{i+1}-state.npz', **{
        key:value for key,value in frame.items() if isinstance(value,np.ndarray)})
painter.end()
sheet.save(str(OUT/'four-phases.png'))
(OUT/'phases.json').write_text(json.dumps(dict(preset='slowclose', config=engine.config,
    camera=dict(framing='zoom adjusted per frame', elevation=72., azimuth=0.),
    phases=report), indent=2), encoding='utf-8')
view.shutdown()
view.close()
print('Saved', OUT/'four-phases.png', flush=True)
