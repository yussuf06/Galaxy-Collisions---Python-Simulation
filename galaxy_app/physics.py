"""Live, three-dimensional collisionless N-body galaxies for Galaxy Encounter.

All particles are massive: stars and sampled dark matter mutually gravitate.
There are no moving prescribed galaxy potentials, drag forces, imposed mergers,
physical particle collisions, gas, star formation, or a calibrated Andromeda
forecast. Galaxies start in approximate (not research-grade exact) equilibrium:
a live Plummer-like halo plus a warm, rotating exponential stellar disk.

G=1. Distances, masses, and time are model units. Particle softening suppresses
artificial close encounters between the massive samples. Leapfrog integration
uses the same fixed step regardless of UI playback speed.
"""
from __future__ import annotations
import math
from typing import Any, Callable
import numpy as np

try:
    from numba import njit
    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False
    def njit(*args, **kwargs):
        def wrap(fn):
            return fn
        return wrap

ACCELERATED = NUMBA_AVAILABLE

DEFAULTS = dict(seed=735128, count=1024, impact=1.5, speed=1.0,
                massratio=1.0, spin=1, inclination=25.0, dt=0.015,
                softening=0.15, isolated=False, backend="auto", relax_steps=400,
                morphology_b='spiral', aligned_disks=False)


@njit(cache=True, nogil=True)
def _forces_numba(pos, mass, eps):
    """Symmetric pair accumulation conserves total force (up to roundoff)."""
    n = len(mass)
    acc = np.zeros((n, 3), dtype=np.float64)
    eps2 = eps * eps
    for i in range(n - 1):
        for j in range(i + 1, n):
            dx = pos[j, 0] - pos[i, 0]
            dy = pos[j, 1] - pos[i, 1]
            dz = pos[j, 2] - pos[i, 2]
            r2 = dx*dx + dy*dy + dz*dz + eps2
            inv = 1.0 / (r2 * math.sqrt(r2))
            for k in range(3):
                d = dx if k == 0 else dy if k == 1 else dz
                acc[i, k] += d * inv * mass[j]
                acc[j, k] -= d * inv * mass[i]
    return acc


def _forces_numpy(pos, mass, eps):
    """Portable fallback; bounded 64xN temporary blocks, never NxNx3."""
    n = len(mass)
    acc = np.empty_like(pos)
    for lo in range(0, n, 64):
        hi = min(lo + 64, n)
        delta = pos[None, :, :] - pos[lo:hi, None, :]
        r2 = np.einsum("ijk,ijk->ij", delta, delta) + eps*eps
        inv = mass[None, :] / (r2 * np.sqrt(r2))
        acc[lo:hi] = np.einsum("ijk,ij->ik", delta, inv)
    return acc


@njit(cache=True, nogil=True)
def _potential_numba(pos, mass, eps):
    value = 0.0
    for i in range(len(mass) - 1):
        for j in range(i + 1, len(mass)):
            # Scalar 3-D arithmetic avoids Numba's optional SciPy/BLAS path.
            dx = pos[j, 0] - pos[i, 0]
            dy = pos[j, 1] - pos[i, 1]
            dz = pos[j, 2] - pos[i, 2]
            value -= mass[i] * mass[j] / math.sqrt(dx*dx + dy*dy + dz*dz + eps*eps)
    return value


def _potential_numpy(pos, mass, eps):
    value = 0.0
    for lo in range(0, len(mass), 64):
        hi = min(lo + 64, len(mass))
        delta = pos[None, :, :] - pos[lo:hi, None, :]
        r = np.sqrt(np.einsum("ijk,ijk->ij", delta, delta) + eps*eps)
        indices = np.arange(lo, hi)
        r[np.arange(hi-lo), indices] = np.inf
        value -= 0.5 * np.sum(mass[lo:hi, None] * mass[None, :] / r)
    return float(value)


def _directions(rng, n):
    v = rng.normal(size=(n, 3))
    return v / np.linalg.norm(v, axis=1)[:, None]


def _galaxy(rng, count, total_mass, spin, inclination, eps, accelerated, relax_steps,
            progress=None, morphology='spiral'):
    """Warm stellar disk in a live isotropic halo; remove bulk COM motion."""
    def report(text, fraction):
        if progress is not None:
            progress(text, fraction)

    report('Sampling stars and dark matter', 0.)
    nh = max(32, int(round(count * 0.60)))
    ns = count - nh
    scale = 1.35
    # Truncated Plummer radial CDF. Finite extent keeps initial galaxies distinct.
    cut = 7.0
    umax = (cut*cut / (cut*cut + scale*scale)) ** 1.5
    u = rng.uniform(0.0001, umax, nh)
    radii = scale / np.sqrt(u ** (-2.0/3.0) - 1.0)
    halo = _directions(rng, nh) * radii[:, None]
    # Isotropic Plummer f(E): p(q) proportional q²(1-q²)^(7/2).
    q = np.empty(nh)
    for i in range(nh):
        while True:
            candidate = rng.uniform()
            if rng.uniform(0, 0.1) < candidate*candidate*(1-candidate*candidate)**3.5:
                q[i] = candidate
                break
    escape = np.sqrt(2*total_mass / np.sqrt(radii*radii + scale*scale))
    halo_v = _directions(rng, nh) * (q * escape)[:, None]
    # Exponential disk radial PDF p(R)~R exp(-R/Rd), truncated at R=3.4.
    disk_r = rng.gamma(2.0, 0.65, ns)
    bad = disk_r > 3.4
    while np.any(bad):
        disk_r[bad] = rng.gamma(2.0, 0.65, np.count_nonzero(bad))
        bad = disk_r > 3.4
    angle = rng.uniform(0, 2*math.pi, ns)
    disk = np.column_stack((disk_r*np.cos(angle), disk_r*np.sin(angle),
                            rng.normal(0, 0.075, ns)))
    if morphology=='spheroid':
        stellar_scale=.45
        umax=(3.4**2/(3.4**2+stellar_scale**2))**1.5
        u=rng.uniform(.0001,umax,ns)
        disk_r=stellar_scale/np.sqrt(u**(-2./3.)-1.)
        disk=_directions(rng,ns)*disk_r[:,None]
    pos = np.vstack((disk, halo))
    stellar_fraction=.35 if morphology=='spheroid' else .15
    mass = np.concatenate((np.full(ns, total_mass*stellar_fraction/ns),
                           np.full(nh, total_mass*(1.-stellar_fraction)/nh)))
    force = _forces_numba if accelerated else _forces_numpy
    report('Calculating initial self-gravity', .08)
    acc = force(pos, mass, eps)
    radial = np.column_stack((np.cos(angle), np.sin(angle), np.zeros(ns)))
    if morphology=='spheroid':radial=disk/np.maximum(disk_r[:,None],1e-12)
    tangent = np.column_stack((-np.sin(angle), np.cos(angle), np.zeros(ns)))
    inward = np.maximum(-np.einsum("ij,ij->i", acc[:ns], radial), 0.01)
    vc = np.sqrt(inward * disk_r)
    dispersion = 0.15*vc + 0.025*math.sqrt(total_mass/scale)
    # Mild asymmetric drift and random velocities avoid a cold unstable disk.
    mean_rotation = np.sqrt(np.maximum(vc*vc - dispersion*dispersion*(disk_r/0.65), 0.25*vc*vc))
    disk_v = tangent*(spin*mean_rotation)[:, None]
    disk_v += radial*rng.normal(0, dispersion)[:, None]
    disk_v += tangent*rng.normal(0, dispersion*0.7)[:, None]
    disk_v[:, 2] += rng.normal(0, 0.065*math.sqrt(total_mass/scale), ns)
    if morphology=='spheroid':
        # An isotropic stellar component, followed by the same conservative
        # self-gravity settling and virial normalization as the disk model.
        disk_v=_directions(rng,ns)*vc[:,None]
    vel = np.vstack((disk_v, halo_v))
    pos -= np.average(pos, axis=0, weights=mass)
    vel -= np.average(vel, axis=0, weights=mass)
    # Match the softened finite sample's virial equilibrium, not unsoftened CDF.
    # The scalar virial uses sum(m r.a), not potential energy for softened forces.
    acc = force(pos, mass, eps)
    virial = -np.sum(mass[:, None] * pos * acc)
    kinetic = 0.5*np.sum(mass[:, None] * vel*vel)
    vel *= math.sqrt(max(virial, 1e-12)/(2*max(kinetic, 1e-12)))
    # Conservative isolated settling before the encounter reduces initialization
    # transients. There is no damping or imposed equilibrium/merger force.
    # The finite samples remain only approximate equilibrium, especially at low N.
    relax_dt = 0.015
    report(f'Isolated settling: 0/{relax_steps} steps', .1)
    for step in range(relax_steps):
        vel += acc*(0.5*relax_dt)
        pos += vel*relax_dt
        acc = force(pos,mass,eps)
        vel += acc*(0.5*relax_dt)
        if (step + 1) % 20 == 0 or step + 1 == relax_steps:
            report(f'Isolated settling: {step + 1}/{relax_steps} steps',
                   .1 + .85 * (step + 1) / relax_steps)
    pos -= np.average(pos,axis=0,weights=mass)
    vel -= np.average(vel,axis=0,weights=mass)
    # Tilt the entire galaxy coherently; arbitrary 3-D orientation is physical.
    th = math.radians(inclination)
    rot = np.array([[1.,0.,0.],[0.,math.cos(th),-math.sin(th)],
                    [0.,math.sin(th),math.cos(th)]])
    pos = pos @ rot.T
    vel = vel @ rot.T
    kind = np.concatenate((np.zeros(ns, dtype=np.int8), np.ones(nh, dtype=np.int8)))
    # Track a central tagged subset, rather than letting long tails drag the center.
    central = np.argsort(np.linalg.norm(pos, axis=1))[:max(12, count//14)]
    report('Galaxy prepared', 1.)
    return pos, vel, mass, kind, central


class NBody:
    """Fixed-step live self-gravity shared by simulator and game modes."""
    def __init__(self, config: dict[str, Any] | None = None,
                 progress: Callable[[str, float], None] | None = None):
        """Prepare galaxies; optional progress receives stage text and 0..1.

        Progress measures completed stages, not estimated elapsed time. Callback
        exceptions propagate so callers can cancel preparation between steps.
        """
        def report(text, fraction):
            if progress is not None:
                progress(text, fraction)

        report('Checking simulation settings', 0.)
        self.config = {**DEFAULTS, **(config or {})}
        c = self.config
        if c['morphology_b'] not in ('spiral','spheroid'):
            raise ValueError('Galaxy B morphology must be spiral or spheroid')
        c['aligned_disks']=bool(c['aligned_disks'])
        c['count'] = int(np.clip(int(c['count']), 128, 4096))
        c['seed'] = int(c['seed']) & 0xffffffff
        for key in ['impact','speed','massratio','inclination','dt','softening']:
            c[key] = float(c[key])
            if not math.isfinite(c[key]):
                raise ValueError(f'{key} must be finite')
        c['impact'] = float(np.clip(c['impact'], -3, 3))
        c['speed'] = float(np.clip(c['speed'], .45, 2))
        c['massratio'] = float(np.clip(c['massratio'], .6, 1.5))
        c['inclination'] = float(np.clip(c['inclination'], -90, 90))
        c['relax_steps'] = int(np.clip(int(c['relax_steps']),0,1200))
        c['spin'] = -1 if int(c['spin']) < 0 else 1
        c['dt'] = float(np.clip(c['dt'], .002, .04))
        c['softening'] = float(np.clip(c['softening'], .06, .4))
        self.dt = c['dt']
        self.accelerated = NUMBA_AVAILABLE and c['backend'] != 'numpy'
        self.backend = 'Numba' if self.accelerated else 'NumPy'
        self._force = _forces_numba if self.accelerated else _forces_numpy
        self._potential = _potential_numba if self.accelerated else _potential_numpy
        # Compile both kernels before costly galaxy preparation. Tiny contiguous
        # arrays use the same signatures as the simulation, with no RNG draws.
        if self.accelerated:
            warm_pos = np.zeros((2, 3), dtype=np.float64)
            warm_mass = np.ones(2, dtype=np.float64)
            report('Preparing Numba gravity kernel (first use may take longer)', .02)
            self._force(warm_pos, warm_mass, c['softening'])
            report('Preparing Numba energy kernel (first use may take longer)', .06)
            self._potential(warm_pos, warm_mass, c['softening'])
        else:
            report('Using NumPy gravity; preparation may take longer', .06)
        rng = np.random.default_rng(c['seed'])
        n0 = c['count'] if c['isolated'] else c['count']//2
        n1 = c['count'] - n0
        galaxy_total = 1 if c['isolated'] else 2

        def galaxy_progress(index):
            return lambda text, fraction: report(
                f'Galaxy {index + 1}/{galaxy_total}: {text}',
                .1 + .8 * (index + fraction) / galaxy_total)

        a = _galaxy(rng, n0, 8., 1, 0., c['softening'], self.accelerated,c['relax_steps'],
                    galaxy_progress(0))
        if c['isolated']:
            self.positions,self.velocities,self.masses,self.kind,ids = a
            self.origin = np.zeros(n0, dtype=np.int8)
            self._central = [ids, ids]
        else:
            b = _galaxy(rng, n1, 8.*c['massratio'], c['spin'], c['inclination'],
                        c['softening'], self.accelerated,c['relax_steps'], galaxy_progress(1),
                        morphology=c['morphology_b'])
            m0,m1 = a[2].sum(),b[2].sum()
            f0,f1 = m1/(m0+m1),m0/(m0+m1)
            relative = np.array([12.,c['impact']*2.1,0.])
            velocity = np.array([-c['speed']*1.6,0.,0.])
            p0,v0 = a[0]-relative*f0,a[1]-velocity*f0
            p1,v1 = b[0]+relative*f1,b[1]+velocity*f1
            self.positions = np.vstack((p0,p1))
            self.velocities = np.vstack((v0,v1))
            self.masses = np.concatenate((a[2],b[2]))
            self.kind = np.concatenate((a[3],b[3]))
            self.origin = np.concatenate((np.zeros(n0,dtype=np.int8),np.ones(n1,dtype=np.int8)))
            self._central = [a[4],b[4]+n0]
        self.positions = np.ascontiguousarray(self.positions)
        self.velocities = np.ascontiguousarray(self.velocities)
        report('Calculating combined galaxy gravity', .94)
        self.accelerations = self._force(self.positions,self.masses,c['softening'])
        self.ticks = 0
        self.time = 0.
        self.closest = float(np.linalg.norm(self.centers()[1]-self.centers()[0]))
        self.after_pericentre = False
        self._last_separation = self.closest
        self._initial_centers = self.centers().copy()
        self.initial_radii = np.linalg.norm(self.positions-self._initial_centers[self.origin],axis=1)
        self._disk_radius = np.array([3.0,3.0])
        report('Checking initial energy and momentum', .97)
        self.initial_energy = self.energy()
        self.initial_momentum = np.sum(self.masses[:,None]*self.velocities,axis=0)
        report('Galaxies ready', 1.)

    def centers(self):
        return np.array([np.average(self.positions[idx],axis=0,weights=self.masses[idx])
                         for idx in self._central])

    def step(self,nsteps: int = 1):
        nsteps = int(nsteps)
        if nsteps < 0 or nsteps > 100000:
            raise ValueError('nsteps must be 0..100000')
        for _ in range(nsteps):
            self.velocities += self.accelerations*(0.5*self.dt)
            self.positions += self.velocities*self.dt
            self.accelerations = self._force(self.positions,self.masses,self.config['softening'])
            self.velocities += self.accelerations*(0.5*self.dt)
            self.ticks += 1
            centers = self.centers()
            separation = float(np.linalg.norm(centers[1]-centers[0]))
            self.closest = min(self.closest,separation)
            if separation > self._last_separation and self.closest < 8 and not self.config['isolated']:
                self.after_pericentre = True
            self._last_separation = separation
        self.time = self.ticks*self.dt
        return self

    def energy(self):
        kinetic = .5*np.sum(self.masses[:,None]*self.velocities**2)
        return float(kinetic+self._potential(self.positions,self.masses,self.config['softening']))

    def angularmomentum(self):
        return np.sum(np.cross(self.positions,self.velocities)*self.masses[:,None],axis=0)

    def metrics(self):
        centers = self.centers()
        stars = self.kind == 0
        pos = self.positions[stars]
        origin = self.origin[stars]
        relative = pos-centers[origin]
        radii = np.linalg.norm(relative,axis=1)
        thresholds = np.maximum(4.6,2.0*self.initial_radii[stars])
        tidal = float(np.mean(radii > thresholds)) if len(pos) else 0.
        bridge = 0.
        axis = centers[1]-centers[0]
        sep = float(np.linalg.norm(axis))
        if self.after_pericentre and sep > 3.:
            sx = pos-centers[0]
            along = sx @ axis / (sep*sep)
            cross = np.linalg.norm(sx-along[:,None]*axis,axis=1)
            distances0 = np.linalg.norm(sx,axis=1)
            distances1 = np.linalg.norm(pos-centers[1],axis=1)
            bridge = float(np.mean((along>.12)&(along<.88)&(cross<.9)&
                                   (distances0>1.8)&(distances1>1.8)))
        return dict(tidal=tidal,bridge=bridge,separation=sep,closest=self.closest,
                    after_pericentre=self.after_pericentre,
                    encounter=not self.config['isolated'] and self.closest<6.)

    def snapshot(self):
        return dict(positions=self.positions.copy(),velocities=self.velocities.copy(),
                    accelerations=self.accelerations.copy(),ticks=self.ticks,
                    closest=self.closest,after_pericentre=self.after_pericentre,
                    last_separation=self._last_separation)

    def restore(self,state):
        checked = {}
        for key in ['positions','velocities','accelerations']:
            value = np.asarray(state[key],dtype=np.float64)
            if value.shape != self.positions.shape or not np.isfinite(value).all():
                raise ValueError(f'Invalid snapshot {key}')
            checked[key] = value.copy()
        ticks = int(state['ticks'])
        closest = float(state['closest'])
        last = float(state['last_separation'])
        if not 0 <= ticks <= 10000000 or not math.isfinite(closest) or closest < 0 or not math.isfinite(last) or last < 0:
            raise ValueError('Invalid snapshot time or separation')
        for key,value in checked.items():setattr(self,key,value)
        self.ticks = ticks
        self.time = self.ticks*self.dt
        self.closest = closest
        self.after_pericentre = bool(state['after_pericentre'])
        self._last_separation = last
        return self
