"""Reference point-star geometry with colour-preserving floating-point light.

Camera controls and marker geometry are retained. Model-space coordinates
convert back to reference length units. Physics stays in the worker. An
unchanged view does not request another draw.
"""
from __future__ import annotations
from collections import deque
import math
import time
from typing import NamedTuple
import numpy as np
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from vispy import app, scene
from vispy.gloo import gl
from .tracking_camera import TrackingCamera
from .hdr_canvas import LightCanvas
from .colour import grade_colours, PALETTES


class DisplayStars(NamedTuple):
    positions: np.ndarray
    origin: np.ndarray
    luminosity: np.ndarray
    warmth: np.ndarray


class GalaxyView(QWidget):
    auto_changed = Signal(bool)
    orbit_changed = Signal(bool)
    renderer_name = 'Reference VisPy / OpenGL'

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 360)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.data = None
        self.preparation_text = 'Preparing live Python galaxies…'
        self.yaw = math.radians(30); self.pitch = math.radians(65)
        self.zoom = 1.; self.pan = np.zeros(2); self.center = np.zeros(3)
        self.auto = False; self.orbit = False
        self.halos = False; self.tracks = False; self.labels = False; self.stats = False
        self.background = True; self.exposure = 1.25; self.star_size = 1.
        self.palette='aurora';self.core_detail=1.;self.protect_highlights=True
        self.detail = 'cinematic'; self.drag = None; self.extent = 10.
        self.centers_history = deque(maxlen=150)
        self.display_stars = None
        self.render_frames = 0; self.upload_count = 0; self.fps = 0.
        self.gpu_renderer = 'initializing'; self.gpu_vendor = 'initializing'
        self._clock = time.perf_counter(); self._fps_at = self._clock
        self._fps_frames = 0; self._last_draw_at = self._clock
        self._serial = 0; self._state_key = None; self._camera_state = {}
        self._geometry_key = None; self._aux_key = None; self._active_count = 0
        self._positions = None; self._colors = None; self._length_scale = .42
        self._from_positions = None; self._received = self._clock; self._frame_interval = .033
        self._tracker=TrackingCamera();self._tracking_target_key=None
        self._manual_distance=42.;self._camera_dt=.016
        self._photo_evidence=None;self._photo_evidence_serial=0
        self.canvas = LightCanvas(keys=None, bgcolor='#020308', show=False,
                                        app=app.use_app('pyside6'), parent=self, vsync=True)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas.native)
        self.canvas.native.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.canvas.native.installEventFilter(self)
        self.scene_view = self.canvas.central_widget.add_view()
        self.camera = scene.TurntableCamera(fov=45, distance=42, elevation=25, azimuth=30)
        self.scene_view.camera = self.camera
        self.camera.interactive = False
        self.sky_positions = np.random.default_rng(901).uniform(-120, 120, (3000, 3)).astype(np.float32)
        self.background_visual = scene.visuals.Markers(parent=self.scene_view.scene)
        self.background_visual.set_data(self.sky_positions, edge_width=0,
                                        face_color=(1, 1, 1, .35), size=1.8)
        self.stars_visual = scene.visuals.Markers(parent=self.scene_view.scene)
        self.stars_visual.set_gl_state('additive', depth_test=False)
        self.photo_visual=scene.visuals.Markers(parent=self.scene_view.scene)
        self.photo_visual.set_gl_state('additive',depth_test=False);self.photo_visual.visible=False
        self.halo_visual = scene.visuals.Markers(parent=self.scene_view.scene)
        self.halo_visual.set_gl_state('additive', depth_test=False)
        self.halo_visual.visible = False
        self.trail_visuals = [scene.visuals.Line(parent=self.scene_view.scene, color=c,
                                                width=1, method='gl')
                              for c in ('#527eaa', '#a1784d')]
        self.name_visuals = [scene.visuals.Text(text='', parent=self.scene_view.scene,
                                               color=c, font_size=11, anchor_y='bottom')
                             for c in ('#b9dfff', '#ffdcad')]
        for visual in self.trail_visuals+self.name_visuals: visual.visible = False
        self.hud = QLabel(self)
        self.hud.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hud.setStyleSheet('background:transparent;color:#a8bfd7;font-size:10px;padding:6px;')
        self.hud.move(10, 8); self.hud.hide()
        self.canvas.events.draw.connect(self._on_draw)
        self.setToolTip('Reference style · Left drag: rotate · Right drag: pan · Wheel: zoom')

    def _on_draw(self, event):
        now = time.perf_counter()
        if now-self._last_draw_at > .5:
            self._fps_at = now; self._fps_frames = 0
        self._last_draw_at = now
        self.render_frames += 1; self._fps_frames += 1
        elapsed = now-self._fps_at
        if elapsed >= .75:
            self.fps = self._fps_frames/elapsed; self._fps_frames = 0; self._fps_at = now
        if self.gpu_renderer == 'initializing':
            self.gpu_renderer = str(gl.glGetParameter(gl.GL_RENDERER))
            self.gpu_vendor = str(gl.glGetParameter(gl.GL_VENDOR))

    def _select_stars(self, data):
        if self.detail != 'raw' and 'tracer_positions' in data:
            positions = np.asarray(data['tracer_positions'], dtype=np.float32)
            colors = np.asarray(data['tracer_colors'], dtype=np.float32)
            origin = np.asarray(data['tracer_origin'], dtype=np.int8)
            if self.detail == 'balanced':
                positions = positions[::2]; colors = colors[::2]; origin = origin[::2]
        else:
            mask = data['kind'] == 0
            positions = np.asarray(data['positions'][mask], dtype=np.float32)
            origin = data['origin'][mask]
            colors = np.array([[.55, .8, 1., .75], [1., .73, .39, .75]], np.float32)[origin]
        if positions.shape != (len(origin), 3) or colors.shape != (len(origin), 4):
            raise ValueError('Stellar metadata must match positions')
        if not np.isfinite(positions).all() or not np.isfinite(colors).all():
            raise ValueError('Stellar geometry must be finite')
        return positions, colors, origin

    def set_data(self, data):
        previous = self.data
        now = time.perf_counter()
        from_positions = self._display_positions(now) if self._positions is not None else None
        if (previous is None or data['config']['seed'] != previous['config']['seed'] or
                data['time'] < previous['time'] or data['time'] < .01):
            self.centers_history.clear()
        self.data = data; self._serial += 1
        scale = float(data['config'].get('reference_length_scale', .42))
        if not math.isfinite(scale) or scale <= 0: raise ValueError('Invalid reference length scale')
        self._length_scale = scale
        if not self.centers_history or data['time'] > self.centers_history[-1][0]+.1:
            self.centers_history.append((data['time'], data['centers'].copy()))
        self._positions, self._colors, origin = self._select_stars(data)
        continuing=(previous is not None and previous.get('phase')=='running' and
                    data.get('phase')=='running' and data['time']>previous['time'] and
                    data['config']['seed']==previous['config']['seed'] and
                    from_positions is not None and from_positions.shape==self._positions.shape)
        if continuing:
            interval=float(np.clip(now-self._received,.016,.15))
            self._frame_interval=.7*self._frame_interval+.3*interval
            self._from_positions=from_positions
        else:
            self._from_positions=self._positions
        self._received=now
        self.display_stars = DisplayStars(self._positions, origin,
                                         np.ones(len(origin), np.float32), np.zeros(len(origin), np.float32))

    def set_detail(self, detail):
        if detail not in ('cinematic', 'balanced', 'raw'): raise ValueError('Unknown display detail')
        self.detail = detail
        if self.data is not None: self.set_data(self.data)
        self.update()

    def set_palette(self,palette):
        if palette not in PALETTES:raise ValueError('Unknown colour palette')
        self.palette=palette;self.update()

    def set_photo_evidence(self,positions,objective='tidal'):
        if positions is None:
            if self._photo_evidence is None:return
            self._photo_evidence=None;self.photo_visual.visible=False
        else:
            points=np.asarray(positions,dtype=np.float32)
            if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('Invalid photographed feature')
            self._photo_evidence=points.copy()
            if len(points):
                points=points[::max(1,len(points)//500)]
                self.photo_visual.set_data(points/self._length_scale,edge_width=1.1,
                                           edge_color=(1.,.85,.25,.95),face_color=(1.,.8,.2,.12),size=7.)
            self.photo_visual.visible=bool(len(points))
        self._photo_evidence_serial+=1;self.update()

    def reset_camera(self):
        self.yaw = math.radians(30); self.pitch = math.radians(65)
        self.zoom = 1.; self.pan[:] = 0; self.center[:] = 0; self.auto = False
        self._manual_distance=42.;self._tracker.reset(np.zeros(3),42.);self._tracking_target_key=None
        self.auto_changed.emit(False)
        self.update()

    def set_tracking(self, enabled):
        enabled=bool(enabled)
        if enabled and not self.auto:
            center=np.asarray(self.camera.center,dtype=float)
            self._tracker.reset(center,float(self.camera.distance))
            self._tracking_target_key=None;self.zoom=1.;self.pan[:]=0
        elif not enabled and self.auto:
            self.center=np.asarray(self.camera.center,dtype=float)*self._length_scale
            self._manual_distance=float(self.camera.distance)*self.zoom
            self.pan[:]=0
        self.auto=enabled;self.auto_changed.emit(enabled);self.update()

    def rotation(self):
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        return np.array([[cy, -sy, 0], [sy*cp, cy*cp, -sp], [sy*sp, cy*sp, cp]])

    def _fraction(self,now):
        if self.data is None or self.data.get('phase')!='running':return 1.
        return min(1.,max(0.,(now-self._received)/self._frame_interval))

    def _display_positions(self,now):
        fraction=self._fraction(now)
        if fraction>=1. or self._from_positions is None:return self._positions
        return self._from_positions+(self._positions-self._from_positions)*fraction

    def _key(self,now=None):
        return (self._serial, self.yaw, self.pitch, self.zoom, *self.pan,
                self.auto, self.exposure, self.star_size, self.detail,
                self.background, self.halos, self.tracks, self.labels, self.stats,
                self.palette,self.core_detail,self.protect_highlights,
                self.width(), self.height(),self._photo_evidence_serial,round(self._fraction(time.perf_counter() if now is None else now),4))

    def animate(self):
        now = time.perf_counter(); elapsed = min(now-self._clock, .1); self._clock = now
        self._camera_dt=elapsed
        if not self.isVisible(): return
        if self.orbit and self.drag is None: self.yaw += elapsed*.12
        if self._key(now) == self._state_key and not (self.auto and not self._tracker.settled): return
        self._refresh_scene()
        self.canvas.update()

    def _refresh_scene(self):
        now=time.perf_counter()
        if self.data is None:
            self.hud.setText(self.preparation_text); self.hud.adjustSize(); self.hud.show()
            self._state_key = self._key(); return
        data = self.data; scale = self._length_scale
        self.canvas.exposure=self.exposure
        self.canvas.core_detail=self.core_detail
        self.canvas.protect_highlights=self.protect_highlights
        self.canvas.reference_mode=bool(data.get('illustration'))
        positions = self._display_positions(now)/scale
        self.background_visual.visible = self.background
        center = self.center/scale
        distance = self._manual_distance
        if self.auto and len(positions):
            target_key=(self._serial,self.width(),self.height(),scale)
            if target_key!=self._tracking_target_key:
                self._tracker.retarget(self._positions/scale,data['centers']/scale,
                                       self.width()/max(1,self.height()))
                self._tracking_target_key=target_key
            center,distance=self._tracker.advance(self._camera_dt)
        shift = np.array([-self.pan[0], self.pan[1], 0.])*distance*.8/max(1, self.height())
        camera_center = center+shift@self.rotation()
        values = {'azimuth':round(math.degrees(self.yaw), 10),
                  'elevation':round(float(np.clip(90-math.degrees(self.pitch), -89.9, 89.9)), 10),
                  'distance':distance/self.zoom, 'center':tuple(camera_center)}
        for key, value in values.items():
            if self._camera_state.get(key) != value:
                setattr(self.camera, key, value); self._camera_state[key] = value
        geometry_key = (self._serial, self.star_size, self.detail,self.palette,
                        self.protect_highlights, self.exposure if not self.protect_highlights else 0.,round(self._fraction(now),4))
        if geometry_key != self._geometry_key:
            colors = self._colors if data.get('illustration') else grade_colours(self._colors,self.display_stars.origin,self.palette)
            if not self.protect_highlights and self.exposure != 1.:
                colors = colors.copy(); colors[:, 3] = np.clip(colors[:, 3]*self.exposure, 0, 1)
            self.stars_visual.set_data(positions, edge_width=0, face_color=colors,
                                       size=3.5*self.star_size)
            self.upload_count += 1; self._active_count = len(positions)
            self._geometry_key = geometry_key
        aux_key = (self._serial, self.halos, self.tracks, self.labels)
        if aux_key != self._aux_key:
            self.halo_visual.visible = self.halos
            if self.halos:
                self.halo_visual.set_data(data['positions'][data['kind'] == 1]/scale,
                                          edge_width=0, face_color=(.35, .43, .7, .3), size=2.)
            names = data.get('galaxy_names',('Milky Way','Andromeda') if data['mode']=='andromeda' else ('Galaxy A','Galaxy B'))
            for i, visual in enumerate(self.name_visuals):
                visual.visible = self.labels and not (i == 1 and data['config'].get('isolated'))
                if visual.visible:
                    visual.text = names[i]; visual.pos = data['centers'][i]/scale+[0, 0, 1.]
            for i, visual in enumerate(self.trail_visuals):
                visual.visible = self.tracks and len(self.centers_history) > 1 and not (i == 1 and data['config'].get('isolated'))
                if visual.visible:
                    visual.set_data(pos=np.array([c[i] for _, c in self.centers_history], np.float32)/scale)
            self._aux_key = aux_key
        illustration=data.get('illustration')
        self.hud.setVisible(self.stats or bool(illustration))
        if illustration:
            self.hud.setText(illustration['title']+' · PHOTO-BASED ILLUSTRATION\n'+
                ' + '.join(illustration['names'])+' · Illustrative depth; no gravity evolution\n'+illustration['credit'])
            self.hud.adjustSize();self.hud.raise_()
        elif self.stats:
            status=f'{self.fps:.0f} draw FPS' if data.get('phase')=='running' or self.orbit else 'Paused · draws on interaction'
            self.hud.setText(f'{status} · {self._active_count:,} stars · {self.gpu_renderer}')
            self.hud.adjustSize(); self.hud.raise_()
        self._state_key = self._key(now)

    def capture(self):
        self._refresh_scene()
        if self.data and self.data.get('illustration'):return self.grab()
        pixels = np.ascontiguousarray(self.canvas.render(alpha=False))
        h, w = pixels.shape[:2]
        return QPixmap.fromImage(QImage(pixels.data, w, h, w*3, QImage.Format.Format_RGB888).copy())

    def update(self, *args):
        super().update(*args)
        self._state_key = None

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.MouseButtonPress: self.mousePressEvent(event); return True
        if kind == QEvent.Type.MouseMove: self.mouseMoveEvent(event); return self.drag is not None
        if kind == QEvent.Type.MouseButtonRelease: self.mouseReleaseEvent(event); return True
        if kind == QEvent.Type.Wheel: self.wheelEvent(event); return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        self.setFocus(); self.drag = (event.position(), event.button(), self.yaw, self.pitch, self.pan.copy())
        if self.orbit: self.orbit = False; self.orbit_changed.emit(False)

    def mouseMoveEvent(self, event):
        if not self.drag: return
        start, button, yaw, pitch, pan = self.drag; delta = event.position()-start
        if button == Qt.MouseButton.LeftButton:
            self.yaw = yaw+delta.x()*.008; self.pitch = float(np.clip(pitch+delta.y()*.008, -1.55, 1.55))
        else:
            if self.auto:self.set_tracking(False)
            self.pan = pan+np.array([delta.x(), delta.y()])
            self.auto = False;self.auto_changed.emit(False)
        self.update()

    def mouseReleaseEvent(self, event): self.drag = None

    def wheelEvent(self, event):
        self.zoom = float(np.clip(self.zoom*(1.15 if event.angleDelta().y() > 0 else 1/1.15), .25, 5)); self.update()

    def closeEvent(self, event): self.shutdown(); super().closeEvent(event)

    def shutdown(self): self.canvas.close()
