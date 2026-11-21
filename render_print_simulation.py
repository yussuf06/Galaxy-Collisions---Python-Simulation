"""Render saved live simulation states directly at A3 print resolution."""
from pathlib import Path
import sys
import json
import math
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

root=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,r'C:\Users\yusuf\Desktop\galaxy-python-desktop\galaxy-python-desktop')
from galaxy_app.gpu_view import GalaxyView

saved=root/'our-simulation-phases'
out=root/'output/pdf/source-images'
out.mkdir(parents=True,exist_ok=True)
metadata=json.loads((saved/'phases.json').read_text(encoding='utf-8'))
app=QApplication([])
view=GalaxyView();view.setWindowFlags(Qt.WindowType.FramelessWindowHint)
view.setMinimumSize(4960,3100);view.resize(4960,3100);view.show();app.processEvents()
print('Native canvas:',view.canvas.size,view.canvas.physical_size,flush=True)
assert view.canvas.size==(4960,3100)
view.yaw=0.;view.pitch=math.radians(18)
factor=4960/1440
view.star_size=factor
view.background_visual.set_data(view.sky_positions,edge_width=0,face_color=(1,1,1,.35),size=1.8*factor)
for i,phase in enumerate(metadata['phases'],1):
    with np.load(saved/f'phase-{i}-state.npz',allow_pickle=False) as archive:
        frame={name:archive[name].copy() for name in archive.files}
    frame.update(config=metadata['config'],time=phase['model_time'],phase='paused',mode='simulation')
    view.center=np.mean(frame['centers'],axis=0)
    # Extra room around the extended debris for a standalone print.
    view._manual_distance=phase['camera_distance']*(1.15 if i<3 else 1.4)
    view.set_data(frame);view.update();app.processEvents();view._refresh_scene()
    pixels=np.ascontiguousarray(view.canvas.render(alpha=False))
    from PySide6.QtGui import QImage
    height,width=pixels.shape[:2]
    assert width>=4960 and height>=3100 and abs(width/height-1.6)<.001
    image=QImage(pixels.data,width,height,width*3,QImage.Format.Format_RGB888).copy()
    image.setDotsPerMeterX(round(300/.0254));image.setDotsPerMeterY(round(300/.0254))
    assert image.save(str(out/f'simulation-phase-{i}.png'))
    print(f'Phase {i}: direct {width} x {height} render',flush=True)
view.shutdown();view.close()
