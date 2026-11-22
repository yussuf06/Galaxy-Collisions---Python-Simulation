"""Shared cinematic/scientific view. Appearance never changes the N-body state."""
from __future__ import annotations
from collections import deque
import math
import time
import numpy as np
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QImage
from PySide6.QtWidgets import QWidget
from .appearance import AppearanceSampler
from .colour import grade_colours,compress_light


def blur(image, passes=1):
    """Small separable binomial filter, with zero rather than wrapped edges."""
    for _ in range(passes):
        padded = np.pad(image, ((1, 1), (0, 0), (0, 0)))
        image = (padded[:-2] + 2*padded[1:-1] + padded[2:])*.25
        padded = np.pad(image, ((0, 0), (1, 1), (0, 0)))
        image = (padded[:, :-2] + 2*padded[:, 1:-1] + padded[:, 2:])*.25
    return image


class GalaxyView(QWidget):
    auto_changed = Signal(bool)
    orbit_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(400, 360)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.data = None
        self.preparation_text = 'Preparing live Python galaxies…'
        self.yaw = -.35; self.pitch = .62; self.zoom = 1.; self.pan = np.zeros(2)
        self.auto = True; self.halos = False; self.tracks = False
        self.labels = True; self.background = True; self.orbit = False
        self.exposure = 1.; self.star_size = 1.; self.detail = 'cinematic'
        self.palette='aurora';self.core_detail=1.;self.protect_highlights=True
        self.extent = 10.; self.center = np.zeros(3); self.drag = None
        self.centers_history = deque(maxlen=150)
        self.sampler = AppearanceSampler()
        self.display_stars = None; self._image_key = None; self._image = None
        self._photo_evidence=None
        self._clock = time.monotonic()
        self.sky = np.random.default_rng(901).random((350, 3))
        self.setToolTip('Left drag: rotate · Right drag: pan · Wheel: zoom\n'
                        'Cinematic detail reconstructs light around the live stellar samples.')

    def set_data(self, data):
        previous = self.data
        self.data = data
        if previous is None or previous['config']['seed'] != data['config']['seed'] or data['time'] < previous['time'] or data['time'] < .01:
            self.centers_history.clear()
        if not self.centers_history or data['time'] > self.centers_history[-1][0]+.1:
            self.centers_history.append((data['time'], data['centers'].copy()))
        self.display_stars = None
        self._image_key = None
        # The window's render clock consumes the latest frame. Requesting a
        # paint for every physics signal can flood Qt on slower CPUs.

    def set_detail(self, detail):
        self.detail = detail; self.display_stars = None; self._image_key = None; self.update()

    def set_palette(self,palette):
        from .colour import PALETTES
        if palette not in PALETTES:raise ValueError('Unknown colour palette')
        self.palette=palette;self._image_key=None;self.update()

    def set_photo_evidence(self,positions,objective='tidal'):
        if positions is None and self._photo_evidence is None:return
        self._photo_evidence=None if positions is None else np.asarray(positions,dtype=np.float32).copy()
        self.update()

    def reset_camera(self):
        self.yaw = -.35; self.pitch = .62; self.zoom = 1.; self.pan[:] = 0
        self.auto = True; self.extent = 10.; self.center[:] = 0; self.update()

    def rotation(self):
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        cp, sp = math.cos(self.pitch), math.sin(self.pitch)
        return np.array([[cy, -sy, 0], [sy*cp, cy*cp, -sp], [sy*sp, cy*sp, cp]])

    def set_tracking(self, enabled):
        self.auto=bool(enabled);self.auto_changed.emit(self.auto);self.update()

    def animate(self):
        now = time.monotonic(); elapsed = min(now-self._clock, .1); self._clock = now
        if self.orbit and self.drag is None:
            self.yaw += elapsed*.12
        self.update()

    def raster(self, xy, origin, luminosity, warmth, w, h):
        """Bilinear light deposition plus soft bloom; no invented gas/dust layer."""
        # Bound the software render size on 4K screens; Qt scales the final image.
        ratio = min(1., 640/max(w, h))
        rw, rh = max(1, round(w*ratio)), max(1, round(h*ratio))
        xy = xy*ratio
        valid = (xy[:, 0] >= 1) & (xy[:, 0] < rw-2) & (xy[:, 1] >= 1) & (xy[:, 1] < rh-2)
        xy = xy[valid]; o = origin[valid]; light = luminosity[valid]; warm = warmth[valid]
        base = np.array([[.27, .59, 1.], [1., .55, .19]], dtype=np.float32)[o]
        colors = base*(1-warm[:, None]*.8)+np.array([1., .94, .82], dtype=np.float32)*warm[:, None]*.8
        if self.palette!='classic':
            rgba=np.column_stack((colors,.26+.39*warm)).astype(np.float32)
            colors=grade_colours(rgba,o,self.palette)[:,:3]
        colors *= light[:, None]*.65*ratio*ratio
        ix = xy.astype(int); f = xy-ix
        deposits = []; weights = []
        for dx, dy in ((0, 0), (1, 0), (0, 1), (1, 1)):
            weight = (f[:, 0] if dx else 1-f[:, 0])*(f[:, 1] if dy else 1-f[:, 1])
            deposits.append((ix[:, 1]+dy)*rw+ix[:, 0]+dx);weights.append(weight)
        indices = np.concatenate(deposits)
        weights = np.concatenate(weights)
        light_colors = np.tile(colors, (4, 1))*weights[:, None]
        field = np.stack([np.bincount(indices, weights=light_colors[:, c], minlength=rh*rw)
                          for c in range(3)], axis=1).astype(np.float32).reshape(rh, rw, 3)
        soft = blur(field, max(1, round(self.star_size)))
        # Bloom in a lower resolution layer keeps the luminous envelope subtle.
        glow_pixels = np.ascontiguousarray(np.clip(soft*95, 0, 255).astype(np.uint8))
        small = QImage(glow_pixels.data,
                       rw, rh, rw*3, QImage.Format.Format_RGB888).copy()
        small = small.scaled(max(1, rw//4), max(1, rh//4), Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        small = small.scaled(rw, rh, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        ptr = small.convertToFormat(QImage.Format.Format_RGBA8888)
        bloom = np.frombuffer(ptr.constBits(), np.uint8).reshape(rh, ptr.bytesPerLine())[:, :rw*4].reshape(rh, rw, 4)[:, :, :3].astype(np.float32)/95.
        hdr = (field*.18+soft*(.9*self.star_size)+bloom*1.5)*self.exposure
        mapped=compress_light(hdr,detail=self.core_detail) if self.protect_highlights else 1-np.exp(-hdr)
        pixels = np.ascontiguousarray((255*mapped).clip(0, 255).astype(np.uint8))
        return QImage(pixels.data, rw, rh, rw*3, QImage.Format.Format_RGB888).copy()

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor('#020409'))
        if self.background:
            p.setPen(Qt.PenStyle.NoPen)
            for x, y, b in self.sky:
                p.setBrush(QColor(152, 174, 204, int(20+b*80)))
                p.drawEllipse(QPointF(x*w, y*h), .3+b*.5, .3+b*.5)
        if self.data is None:
            p.setPen(QColor('#b5cce4'))
            p.drawText(self.rect().adjusted(30, 30, -30, -30), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.preparation_text)
            p.end(); return
        d = self.data; pos = d['positions']; centers = d['centers']; mask = d['kind'] == 0
        if self.auto:
            self.center += (centers.mean(axis=0)-self.center)*.2
        rotation = self.rotation()
        rotated = (pos-self.center)@rotation.T
        if self.auto and np.any(mask):
            # Fit the rectangular viewport, rather than leaving a landscape
            # pair tiny inside an unnecessarily square camera volume.
            aspect = max(.5, (w-50)/max(h-100, 1))
            sample = np.abs(rotated[mask, :2])/np.array([aspect, 1.])
            radius = np.max(sample, axis=1)
            target = max(2.8, float(np.quantile(radius, .985))*1.18)
            self.extent += (target-self.extent)*.12
        scale = max(1, h-100)/(2*self.extent)*self.zoom
        midpoint = np.array([w*.5, h*.5])+self.pan
        def project(points):
            return ((points-self.center)@rotation.T)[:, :2]*[1, -1]*scale+midpoint
        projected = project(pos)
        if d.get('illustration'):
            self.paint_illustration(p,projected,w,h)
            p.end();return
        if self.halos:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(127, 142, 199, 90))
            for x, y in projected[~mask]:
                p.drawEllipse(QPointF(float(x), float(y)), 1., 1.)
        if self.tracks and len(self.centers_history) > 1:
            for origin, color in ((0, '#436b8a'), (1, '#987044')):
                if origin == 1 and d['config'].get('isolated'): continue
                points = project(np.array([history[origin] for _, history in self.centers_history]))
                p.setPen(QPen(QColor(color), 1.))
                for a, b in zip(points[:-1], points[1:]):
                    p.drawLine(QPointF(*a), QPointF(*b))
        if self.display_stars is None:
            self.display_stars = self.sampler.sample(d, self.detail)
        stars = self.display_stars
        key = (w, h, round(self.yaw, 4), round(self.pitch, 4), round(scale, 3),
               *np.round(self.center, 4), *self.pan, self.exposure, self.star_size, self.detail,
               self.palette,self.core_detail,self.protect_highlights)
        if key != self._image_key:
            self._image = self.raster(project(stars.positions), stars.origin, stars.luminosity, stars.warmth, w, h)
            self._image_key = key
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
        p.drawImage(self.rect(), self._image)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.labels:
            names = ('Milky Way', 'Andromeda') if d['mode'] == 'andromeda' else ('Galaxy A', 'Galaxy B')
            for i, xy in enumerate(project(centers)):
                if i == 1 and d['config'].get('isolated'): continue
                p.setPen(QColor('#a5dbff' if i == 0 else '#ffd095')); p.setFont(QFont('Arial', 10))
                p.drawText(QRectF(float(xy[0]-70), float(xy[1]-38), 140, 20), Qt.AlignmentFlag.AlignCenter, names[i])
        p.setPen(QColor('#a2b9d4')); p.setFont(QFont('Arial', 10))
        mode_name = {'simulation':'LIVE SELF-GRAVITY', 'game':'PYTHON PHYSICS CHALLENGE', 'andromeda':'ILLUSTRATIVE FUTURE ENCOUNTER','photo':'PHOTO HUNT · LIVE GRAVITY'}[d['mode']]
        p.drawText(18, 27, mode_name)
        p.setPen(QColor('#738da9')); p.setFont(QFont('Arial', 9))
        p.drawText(18, h-38, 'Collisionless gravity · no gas, dust or star formation · model time')
        text = f"{d['count']:,} gravity particles · {len(stars.positions):,} display samples"
        p.drawText(18, h-20, text if self.detail != 'raw' else f"{d['count']:,} gravity particles · raw stellar samples")
        p.drawText(QRectF(w-240, 13, 220, 24), Qt.AlignmentFlag.AlignRight, self.detail.upper()+' · '+d['backend'])
        if self._photo_evidence is not None:
            p.setPen(QPen(QColor('#ffd65e'),1.2));p.setBrush(Qt.BrushStyle.NoBrush)
            for x,y in project(self._photo_evidence[::max(1,len(self._photo_evidence)//500)]):p.drawEllipse(QPointF(float(x),float(y)),3.5,3.5)
        p.end()

    def paint_illustration(self,p,projected,w,h):
        """Headless/software fallback uses the same registered photo samples."""
        key=(id(self.data),w,h,self.yaw,self.pitch,self.zoom,*self.pan,self.exposure,self.star_size,self.extent)
        if key!=self._image_key:
            ratio=min(1.,900/max(w,h));rw,rh=max(1,round(w*ratio)),max(1,round(h*ratio))
            xy=projected*ratio;ix=xy.astype(int)
            valid=(ix[:,0]>=0)&(ix[:,0]<rw)&(ix[:,1]>=0)&(ix[:,1]<rh)
            colors=self.data['tracer_colors'][valid];ix=ix[valid];indices=ix[:,1]*rw+ix[:,0]
            field=np.stack([np.bincount(indices,weights=colors[:,c]*colors[:,3],minlength=rw*rh) for c in range(3)],axis=1).reshape(rh,rw,3)
            field=blur(field,max(1,round(self.star_size*2)))
            peak=field.max(axis=2,keepdims=True)
            light=field/np.maximum(peak,1e-8)*(1-np.exp(-peak*self.exposure*3.))**.85
            pixels=np.ascontiguousarray(np.clip(light*255,0,255).astype(np.uint8))
            self._image=QImage(pixels.data,rw,rh,rw*3,QImage.Format.Format_RGB888).copy();self._image_key=key
        p.drawImage(self.rect(),self._image)
        info=self.data['illustration'];p.setPen(QColor('#b9dfff'));p.setFont(QFont('Arial',9))
        p.drawText(18,25,info['title']+' · PHOTO-BASED ILLUSTRATION')
        p.drawText(18,42,' + '.join(info['names'])+' · Illustrative depth; no gravity evolution')
        p.drawText(18,59,info['credit'])

    def mousePressEvent(self, event):
        self.setFocus(); self.drag = (event.position(), event.button(), self.yaw, self.pitch, self.pan.copy())
        if self.orbit: self.orbit = False; self.orbit_changed.emit(False)

    def mouseMoveEvent(self, event):
        if not self.drag: return
        start, button, yaw, pitch, pan = self.drag; delta = event.position()-start
        if button == Qt.MouseButton.LeftButton:
            self.yaw = yaw+delta.x()*.008; self.pitch = float(np.clip(pitch+delta.y()*.008, -1.55, 1.55))
        else:
            self.pan = pan+np.array([delta.x(), delta.y()]); self.auto = False; self.auto_changed.emit(False)
        self.update()

    def mouseReleaseEvent(self, event): self.drag = None

    def wheelEvent(self, event):
        self.zoom = float(np.clip(self.zoom*(1.15 if event.angleDelta().y() > 0 else 1/1.15), .25, 5)); self.update()
