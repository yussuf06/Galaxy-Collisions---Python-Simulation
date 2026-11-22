"""Deterministic display reconstruction of a sparse collisionless stellar sample.

The returned points are visual samples, not additional gravitating particles.
Every sample belongs to a live star or a local pair from the same galaxy. Their
positions follow the *current* geometry, including tidal deformation. No orbit,
spiral, galaxy potential, or physical force is imposed by this module.

This deliberately uses no temporal state: a frame has the same appearance after
rewind or checkpoint loading, even when loaded into a fresh application.
"""
from __future__ import annotations

from typing import NamedTuple
import numpy as np


class DisplayStars(NamedTuple):
    positions: np.ndarray
    origin: np.ndarray
    luminosity: np.ndarray
    warmth: np.ndarray


class AppearanceSampler:
    """Reconstruct local stellar density for the shared simulator/game view.

    ``sample(frame, detail)`` returns ``DisplayStars``. ``luminosity`` is relative
    light per display point, normally 0.2..1.2 (not normalized by point count).
    ``warmth`` is 0 at the outer disk/tails and tends to 1 at the pale core; use
    origin to choose blue/gold outer colors. Brightness is illustrative and is
    not a stellar temperature, mass measurement, or calibrated photometry.

    cinematic: up to 20,000 points; balanced: up to 8,000 points;
    raw/scientific: exactly the physical stellar samples, without reconstruction.
    """

    TARGETS = {'cinematic': 20_000, 'balanced': 8_000}

    def sample(self, frame: dict, detail: str = 'cinematic') -> DisplayStars:
        if detail not in (*self.TARGETS, 'raw', 'scientific'):
            raise ValueError('Unknown appearance detail: ' + str(detail))
        positions = np.asarray(frame['positions'])
        kind = np.asarray(frame['kind'])
        origins = np.asarray(frame['origin'])
        centers = np.asarray(frame['centers'])
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError('Positions must have shape (N, 3)')
        if kind.shape != (len(positions),) or origins.shape != kind.shape:
            raise ValueError('Particle metadata must match positions')
        if not np.isfinite(positions).all() or not np.isfinite(centers).all():
            raise ValueError('Display geometry must be finite')
        ids = np.flatnonzero(kind == 0)
        stars = np.asarray(positions[ids], dtype=np.float64)
        origin = origins[ids].astype(np.int8, copy=True)
        n = len(stars)
        if not n:
            return DisplayStars(np.empty((0, 3), dtype=np.float32), origin,
                                np.empty(0, dtype=np.float32), np.empty(0, dtype=np.float32))
        if np.any(origin < 0) or np.any(origin >= len(centers)):
            raise ValueError('Star origin has no matching center')
        radius = np.linalg.norm(stars - centers[origin], axis=1)
        warmth = np.exp(-radius / .9).astype(np.float32)
        seed = int(frame.get('config', {}).get('seed', 0)) & 0xffffffff
        rng = np.random.default_rng(seed ^ 0x6A09E667)
        base_light = rng.uniform(.8, 1.2, n).astype(np.float32)
        target = self.TARGETS.get(detail, n)
        if n >= target or detail in ('raw', 'scientific'):
            return DisplayStars(stars.astype(np.float32), origin, base_light, warmth)

        # Pairwise work is limited to each original galaxy and to row blocks.
        # This is a density reconstruction, not another gravitational solve.
        width = 8
        neighbors = np.repeat(np.arange(n)[:, None], width, axis=1)
        delta = np.zeros((n, width, 3), dtype=np.float64)
        neighbor_count = np.zeros(n, dtype=np.int8)
        for galaxy in np.unique(origin):
            members = np.flatnonzero(origin == galaxy)
            points = stars[members]
            k = min(width, len(members) - 1)
            if k <= 0:
                continue
            neighbor_count[members] = k
            for lo in range(0, len(members), 128):
                hi = min(lo + 128, len(members))
                diff = points[None, :, :] - points[lo:hi, None, :]
                distance2 = np.einsum('ijk,ijk->ij', diff, diff)
                distance2[np.arange(hi-lo), np.arange(lo, hi)] = np.inf
                # Partial selection avoids sorting the whole galaxy. NumPy's
                # deterministic partition plus local ordering reproduces the
                # same neighbors whenever the identical frame is supplied.
                near = np.argpartition(distance2, k-1, axis=1)[:, :k]
                chosen_distances = np.take_along_axis(distance2, near, axis=1)
                local_order = np.argsort(chosen_distances, axis=1, kind='stable')
                near = np.take_along_axis(near, local_order, axis=1)
                if k < width:
                    near = near[:, np.arange(width) % k]
                row = members[lo:hi]
                neighbors[row] = members[near]
                delta[row] = points[near] - points[lo:hi, None, :]

        cfg = frame.get('config', {})
        eps = float(cfg.get('softening', .15))
        if not np.isfinite(eps):
            raise ValueError('Softening must be finite')
        # A fixed upper limit prevents a sparse tail/outlier from being filled
        # with a false luminous bridge. Widths cannot grow with the encounter.
        edge_limit = float(np.clip(eps * 5., .35, .85))
        lengths = np.linalg.norm(delta, axis=2)
        usable = lengths <= edge_limit
        local_delta = delta * usable[:, :, None]
        # These local vectors factor the covariance. Sampling that factor
        # directly avoids arbitrary eigenvector flips in thin or symmetric
        # disks, keeping the reconstruction stable as live geometry changes.
        # Cap each factor before sampling, then cap the final footprint below.
        local_delta *= np.minimum(1., .45 / np.maximum(lengths, 1e-12))[:, :, None]

        amount = target - n
        owner = np.arange(amount) % n
        chosen = rng.integers(0, width, amount)
        link = delta[owner, chosen]
        length = lengths[owner, chosen]
        fraction = rng.uniform(0., .5, amount)
        # Interpolation is disabled for stretched links. Their light smoothly
        # fades before this cutoff; samples stay at their physical parent.
        bounded_fraction = fraction * (length <= edge_limit)
        coefficients = np.clip(rng.normal(size=(amount, width)), -2.5, 2.5) * .28
        jitter = np.einsum('nki,nk->ni', local_delta[owner], coefficients)
        # A tiny isotropic anti-alias kernel keeps duplicate samples visible
        # without turning a thin stellar disk into a spherical cloud.
        jitter += np.clip(rng.normal(size=(amount, 3)), -2.5, 2.5) * .004
        # Cap the total kernel footprint as well as each covariance axis.
        jitter_norm = np.linalg.norm(jitter, axis=1)
        # A well-supported disk interior can carry a broad reconstruction
        # kernel. Sparse tails keep a narrow footprint, so broad smoothing does
        # not inflate a physical tidal bridge or fill a gap between galaxies.
        support = np.sum(usable, axis=1)
        jitter_cap = np.minimum(.35, .07 + support[owner] * .035)
        jitter *= np.minimum(1., jitter_cap / np.maximum(jitter_norm, 1e-12))[:, None]
        offset = bounded_fraction[:, None] * link + jitter
        offset *= np.minimum(1., .64 / np.maximum(np.linalg.norm(offset, axis=1), 1e-12))[:, None]
        reconstructed = stars[owner] + offset
        fade = np.exp(-8. * np.maximum(length / edge_limit - .6, 0.) ** 2)
        fade[length > edge_limit] = 0.
        fade[neighbor_count[owner] == 0] = 0.
        synthetic_light = rng.uniform(.2, 1., amount) * fade
        neighbor = neighbors[owner, chosen]
        synthetic_warmth = (warmth[owner] * (1. - bounded_fraction)
                            + warmth[neighbor] * bounded_fraction)
        return DisplayStars(
            np.vstack((stars, reconstructed)).astype(np.float32),
            np.concatenate((origin, origin[owner])),
            np.concatenate((base_light, synthetic_light.astype(np.float32))),
            np.concatenate((warmth, synthetic_warmth.astype(np.float32))),
        )


def sample(frame: dict, detail: str = 'cinematic') -> DisplayStars:
    """Convenience entry point; the sampler intentionally has no temporal state."""
    return AppearanceSampler().sample(frame, detail)
