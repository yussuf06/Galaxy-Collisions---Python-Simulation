"""Dense reference galaxies evolved as luminous tracers of live N-body gravity.

The generator is adapted from the user's cinematic ``main.py``: identical
gamma radii, three winding arms, thickness, rotations and blue/gold gradients.
Tracers have no mass or back reaction. The original massive stars and halo
particles remain the mutual-gravity model used for game scoring. A spatial
monopole approximation of their *current* field makes 30,000 luminous tracers
affordable. No galaxy center follows an imposed orbit and no merger is forced.
"""
from __future__ import annotations

import math
import numpy as np
from .physics import NUMBA_AVAILABLE, njit

if NUMBA_AVAILABLE:
    from numba import prange, get_num_threads, set_num_threads, config as numba_config
    _TRACER_THREADS = min(4, numba_config.NUMBA_NUM_THREADS)
else:
    prange = range
    _TRACER_THREADS = 1


def generate_cinematic_galaxy(center, vel, mass, n_stars, tilt_deg, color_theme,
                              rng=None):
    """Reference generator, with an optional local RNG for repeatable games.

    Coordinates and speeds returned here retain the reference's G=1.5 units.
    ``DenseStars.from_engine`` converts lengths and recalibrates circular
    speeds to the existing app's live, extended gravitational field.
    """
    rng = np.random if rng is None else rng
    G = 1.5
    radii = rng.gamma(shape=1.6, scale=1.8, size=n_stars) + 0.15
    radii = np.clip(radii, 0.15, 11.0)
    arms = rng.choice([0, 2*np.pi/3, 4*np.pi/3], size=n_stars)
    spread = rng.normal(0, 0.22+(radii/25.0), size=n_stars)
    angle = arms+(radii*1.15)+spread
    x = radii*np.cos(angle)
    y = radii*np.sin(angle)
    thickness = 0.6*np.exp(-radii/2.5)+0.08
    z = rng.normal(0, thickness, size=n_stars)
    speeds = np.sqrt(G*mass/(radii+0.6))
    vx = -speeds*np.sin(angle)
    vy = speeds*np.cos(angle)
    vz = np.zeros(n_stars)
    pos = np.column_stack((x, y, z))
    vel_arr = np.column_stack((vx, vy, vz))
    rx, ry, rz = np.radians(tilt_deg)
    Rx = np.array([[1, 0, 0], [0, np.cos(rx), -np.sin(rx)],
                   [0, np.sin(rx), np.cos(rx)]])
    Ry = np.array([[np.cos(ry), 0, np.sin(ry)], [0, 1, 0],
                   [-np.sin(ry), 0, np.cos(ry)]])
    Rz = np.array([[np.cos(rz), -np.sin(rz), 0],
                   [np.sin(rz), np.cos(rz), 0], [0, 0, 1]])
    R = Rz @ Ry @ Rx
    pos = pos @ R.T+center
    vel_arr = vel_arr @ R.T+vel
    norm_r = np.clip(radii/9.0, 0, 1)
    colors = np.ones((n_stars, 4), dtype=np.float32)
    if color_theme == 'blue':
        colors[:, 0] = 1.0-0.75*norm_r
        colors[:, 1] = 1.0-0.35*norm_r
        colors[:, 2] = 1.0
    else:
        colors[:, 0] = 1.0
        colors[:, 1] = 0.95-0.55*norm_r
        colors[:, 2] = 0.85-0.75*norm_r
    colors[:, 3] = np.clip(0.65*(1.0-0.6*norm_r), 0.15, 0.75)
    return pos, vel_arr, colors


def aggregate_sources(positions, masses, origins, cell_size=1.0):
    """Cell monopoles preserve every source mass and its center of mass.

    Cells are local to each live galaxy's current mass center; their centers
    move freely. This avoids a fixed grid following a prescribed galaxy path.
    """
    result_pos, result_mass = [], []
    for origin in np.unique(origins):
        mask = origins == origin
        pos, mass = positions[mask], masses[mask]
        center = np.average(pos, axis=0, weights=mass)
        cell = np.floor((pos-center)/cell_size).astype(np.int64)
        _, inverse = np.unique(cell, axis=0, return_inverse=True)
        total = np.bincount(inverse, weights=mass)
        centers = np.column_stack([np.bincount(inverse, weights=mass*pos[:, k])
                                   for k in range(3)])/total[:, None]
        result_pos.append(centers); result_mass.append(total)
    if not result_pos:
        return np.empty((0, 3)), np.empty(0)
    return np.ascontiguousarray(np.vstack(result_pos)), np.concatenate(result_mass)


@njit(cache=True, nogil=True)
def _tracer_force_numba(stars, sources, masses, eps):
    acceleration = np.zeros_like(stars)
    eps2 = eps*eps
    for i in range(len(stars)):
        for j in range(len(sources)):
            dx = sources[j, 0]-stars[i, 0]
            dy = sources[j, 1]-stars[i, 1]
            dz = sources[j, 2]-stars[i, 2]
            r2 = dx*dx+dy*dy+dz*dz+eps2
            force = masses[j]/(r2*math.sqrt(r2))
            acceleration[i, 0] += dx*force
            acceleration[i, 1] += dy*force
            acceleration[i, 2] += dz*force
    return acceleration


@njit(cache=True, nogil=True, parallel=True)
def _tracer_force_parallel(stars, sources, masses, eps):
    """Each worker owns complete rows; summation order stays unchanged."""
    acceleration = np.zeros_like(stars)
    eps2 = eps*eps
    for i in prange(len(stars)):
        for j in range(len(sources)):
            dx = sources[j, 0]-stars[i, 0]
            dy = sources[j, 1]-stars[i, 1]
            dz = sources[j, 2]-stars[i, 2]
            r2 = dx*dx+dy*dy+dz*dz+eps2
            force = masses[j]/(r2*math.sqrt(r2))
            acceleration[i, 0] += dx*force
            acceleration[i, 1] += dy*force
            acceleration[i, 2] += dz*force
    return acceleration


def _tracer_force_numpy(stars, sources, masses, eps):
    acceleration = np.empty_like(stars)
    for start in range(0, len(stars), 256):
        end = min(start+256, len(stars))
        delta = sources[None, :, :]-stars[start:end, None, :]
        r2 = np.einsum('ijk,ijk->ij', delta, delta)+eps*eps
        inv = masses[None, :]/(r2*np.sqrt(r2))
        acceleration[start:end] = np.einsum('ijk,ij->ik', delta, inv)
    return acceleration


class DenseStars:
    """Live tracer state. Snapshot arrays are independent owned copies.

    ``positions`` predicts the small remainder between fixed tracer steps for
    smooth presentation. Saved ``positions`` are the integrated coordinates.
    ``time`` always matches the latest supplied NBody state. Field updates use
    fixed .06 model-unit leapfrog steps, independent of UI playback speed.
    """
    dt = .06

    @classmethod
    def from_engine(cls, engine, count_per_galaxy=15_000):
        count = int(count_per_galaxy)
        if count < 0 or count > 60_000:
            raise ValueError('Tracer count per galaxy must be 0..60000')
        self = cls()
        self.accelerated = bool(engine.accelerated and NUMBA_AVAILABLE)
        # A coarsened monopole field needs a correspondingly smoother kernel;
        # this is close to the reference's 1.2-unit smoothing after rescaling.
        self.softening = max(float(engine.config['softening']), .45)
        # The full field still acts on the massive bodies; tracers use a
        # deliberately coarser field for smooth, fast educational imagery.
        self.cell_size = 1.25 if self.accelerated else 2.0
        self.time = float(engine.time); self.pending = 0.; self.source_time = self.time
        self.source_positions = np.asarray(engine.positions, dtype=np.float64).copy()
        self.source_masses = np.asarray(engine.masses, dtype=np.float64).copy()
        self.source_origin = np.asarray(engine.origin, dtype=np.int8).copy()
        centers = engine.centers()
        position, velocity, color, origin = [], [], [], []
        for galaxy in np.unique(engine.origin):
            mask = engine.origin == galaxy
            bulk = np.average(engine.velocities[mask], axis=0, weights=engine.masses[mask])
            tilt = (30., 15., 0.) if galaxy == 0 else (-40., float(engine.config['inclination']), 10.)
            if engine.config.get('aligned_disks'):
                tilt=(0.,0.,0.) if galaxy==0 else (float(engine.config['inclination']),0.,0.)
            rng = np.random.RandomState((int(engine.config['seed'])+int(galaxy)*104729) & 0xffffffff)
            p, v, c = generate_cinematic_galaxy(np.zeros(3), np.zeros(3),
                                               75. if galaxy == 0 else 60., count,
                                               tilt, 'blue' if galaxy == 0 else 'gold', rng)
            spherical=galaxy==1 and engine.config.get('morphology_b')=='spheroid'
            if spherical:
                u=rng.uniform(.0001,(5.**2/(5.**2+.8**2))**1.5,count)
                radius=.8/np.sqrt(u**(-2./3.)-1.)
                direction=rng.normal(size=(count,3));direction/=np.maximum(np.linalg.norm(direction,axis=1)[:,None],1e-12)
                p=direction*radius[:,None]
                v=rng.normal(size=(count,3))
                norm=np.clip(radius/9.,0,1)
                c=np.column_stack((np.ones(count),.95-.55*norm,.85-.75*norm,.65*(1.-.6*norm))).astype(np.float32)
            p *= .42
            radial = p/np.maximum(np.linalg.norm(p, axis=1)[:, None], 1e-12)
            p += centers[int(galaxy)]
            src, mass = aggregate_sources(engine.positions[mask], engine.masses[mask],
                                         engine.origin[mask], self.cell_size)
            force = self._force(p, src, mass)
            inward = np.maximum(-np.einsum('ij,ij->i', force, radial), 0.)
            radius = np.linalg.norm(p-centers[int(galaxy)], axis=1)
            speed = np.sqrt(np.maximum(inward*radius, 0.))
            v /= np.maximum(np.linalg.norm(v, axis=1)[:, None], 1e-12)
            if galaxy == 1 and engine.config['spin'] < 0:
                v *= -1
            v = v*speed[:, None]+bulk
            position.append(p); velocity.append(v); color.append(c)
            origin.append(np.full(count, galaxy, dtype=np.int8))
        self._positions = np.ascontiguousarray(np.vstack(position), dtype=np.float64)
        self.velocities = np.ascontiguousarray(np.vstack(velocity), dtype=np.float64)
        self.colors = np.vstack(color).astype(np.float32)
        self.origin = np.concatenate(origin)
        src, mass = aggregate_sources(self.source_positions, self.source_masses,
                                     self.source_origin, self.cell_size)
        self.accelerations = self._force(self._positions, src, mass)
        return self

    def _force(self, stars, sources, masses):
        if self.accelerated and len(stars) >= 4096 and _TRACER_THREADS > 1:
            previous = get_num_threads()
            try:
                set_num_threads(_TRACER_THREADS)
                return _tracer_force_parallel(stars, sources, masses, self.softening)
            finally:
                set_num_threads(previous)
        fn = _tracer_force_numba if self.accelerated else _tracer_force_numpy
        return fn(stars, sources, masses, self.softening)

    @property
    def positions(self):
        if self.pending < 1e-12:
            return self._positions
        return self._positions+self.velocities*self.pending+self.accelerations*(.5*self.pending*self.pending)

    def advance(self, engine, delta_time):
        delta = float(delta_time)
        if not math.isfinite(delta) or delta < 0:
            raise ValueError('Tracer advance must be finite and nonnegative')
        if abs(float(engine.time)-(self.time+delta)) > 1e-7:
            raise ValueError('Tracer advance must end at the supplied engine time')
        if engine.positions.shape != self.source_positions.shape:
            raise ValueError('Source population changed; regenerate tracers')
        if delta == 0:
            return self
        end_sources = np.asarray(engine.positions)
        source_delta = end_sources-self.source_positions
        elapsed = self.dt-self.pending
        while elapsed <= delta+1e-10:
            self.velocities += self.accelerations*(.5*self.dt)
            self._positions += self.velocities*self.dt
            fraction = min(1., max(0., elapsed/delta))
            sources = self.source_positions+source_delta*fraction
            src, mass = aggregate_sources(sources, self.source_masses,
                                         self.source_origin, self.cell_size)
            self.accelerations = self._force(self._positions, src, mass)
            self.velocities += self.accelerations*(.5*self.dt)
            elapsed += self.dt
        steps = max(0, int(math.floor((self.pending+delta+1e-10)/self.dt)))
        self.pending = max(0., self.pending+delta-steps*self.dt)
        self.time = float(engine.time)
        self.source_time = self.time
        self.source_positions = end_sources.copy()
        return self

    def snapshot(self):
        state = {name:getattr(self, name).copy() for name in
                 ('velocities', 'colors', 'origin', 'accelerations', 'source_positions',
                  'source_masses', 'source_origin')}
        state['positions'] = self._positions.copy()
        state.update(time=self.time, pending=self.pending, source_time=self.source_time,
                     dt=self.dt, softening=self.softening, accelerated=self.accelerated,
                     cell_size=self.cell_size)
        return state

    @classmethod
    def restore(cls, state):
        self = cls()
        for name in ('positions', 'velocities', 'accelerations', 'colors', 'origin',
                     'source_positions', 'source_masses', 'source_origin'):
            setattr(self, '_positions' if name == 'positions' else name, np.asarray(state[name]).copy())
        n = len(self._positions); m = len(self.source_positions)
        if n > 120_000 or m < 1 or m > 4096:
            raise ValueError('Invalid tracer population')
        for array in (self._positions, self.velocities, self.accelerations):
            if array.shape != (n, 3) or not np.isfinite(array).all():
                raise ValueError('Invalid tracer vector array')
        if self.colors.shape != (n, 4) or not np.isfinite(self.colors).all() or np.any(self.colors < 0) or np.any(self.colors > 1):
            raise ValueError('Invalid tracer colors')
        if self.origin.shape != (n,) or not np.isin(self.origin, (0, 1)).all():
            raise ValueError('Invalid tracer origins')
        if self.source_positions.shape != (m, 3) or not np.isfinite(self.source_positions).all():
            raise ValueError('Invalid tracer source positions')
        if self.source_masses.shape != (m,) or not np.isfinite(self.source_masses).all() or np.any(self.source_masses <= 0):
            raise ValueError('Invalid tracer source masses')
        if self.source_origin.shape != (m,) or not np.isin(self.source_origin, (0, 1)).all():
            raise ValueError('Invalid tracer source origins')
        for name in ('_positions', 'velocities', 'accelerations', 'source_positions', 'source_masses'):
            setattr(self, name, np.ascontiguousarray(getattr(self, name), dtype=np.float64))
        self.colors = np.ascontiguousarray(self.colors, dtype=np.float32)
        self.origin = self.origin.astype(np.int8)
        self.source_origin = self.source_origin.astype(np.int8)
        for key in ('time', 'pending', 'source_time', 'dt', 'softening', 'cell_size'):
            value = float(state[key])
            if not math.isfinite(value):
                raise ValueError('Invalid tracer time or field parameter')
            setattr(self, key, value)
        if self.time < 0 or self.dt != .06 or not 0 <= self.pending < self.dt+1e-8 or abs(self.source_time-self.time) > 1e-7 or not .06 <= self.softening <= 2 or not .1 <= self.cell_size <= 4:
            raise ValueError('Invalid tracer time or field parameter')
        self.accelerated = bool(state['accelerated']) and NUMBA_AVAILABLE
        return self
