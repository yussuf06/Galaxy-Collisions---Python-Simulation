"""Display reconstruction invariants; no Qt or optional acceleration required."""
import copy
import time
import unittest
import numpy as np
from galaxy_app.appearance import AppearanceSampler


def frame_fixture(n=400):
    rng = np.random.default_rng(19)
    origin = (np.arange(n) >= n // 2).astype(np.int8)
    positions = rng.normal(size=(n, 3)) * [.65, .65, .025]
    centers = np.array([[-6., 0., 0.], [6., 0., 0.]])
    positions += centers[origin]
    return dict(positions=positions, kind=np.zeros(n, dtype=np.int8),
                origin=origin, centers=centers,
                config=dict(seed=42, softening=.15), time=0.)


class AppearanceTests(unittest.TestCase):
    def setUp(self):
        self.sampler = AppearanceSampler()

    def test_deterministic_across_frames_rewind_and_new_sampler(self):
        frame = frame_fixture()
        a = self.sampler.sample(frame)
        moved = copy.deepcopy(frame)
        moved['positions'] += np.random.default_rng(6).normal(0, .2, moved['positions'].shape)
        self.sampler.sample(moved)
        b = self.sampler.sample(frame)
        c = AppearanceSampler().sample(frame)
        for aa, bb, cc in zip(a, b, c):
            np.testing.assert_array_equal(aa, bb)
            np.testing.assert_array_equal(aa, cc)

    def test_does_not_mutate_frame_or_global_random_state(self):
        frame = frame_fixture()
        before = copy.deepcopy(frame)
        state = np.random.get_state()
        self.sampler.sample(frame)
        for key in ['positions', 'kind', 'origin', 'centers']:
            np.testing.assert_array_equal(frame[key], before[key])
        self.assertEqual(frame['config'], before['config'])
        after_state = np.random.get_state()
        np.testing.assert_array_equal(state[1], after_state[1])
        self.assertEqual(state[2:], after_state[2:])

    def test_finite_detail_counts_and_raw_stars_only(self):
        frame = frame_fixture()
        frame['kind'][0] = 1
        for detail, count in [('cinematic', 20000), ('balanced', 8000), ('raw', 399), ('scientific', 399)]:
            stars = self.sampler.sample(frame, detail)
            self.assertEqual(stars.positions.shape, (count, 3))
            for value in stars:
                self.assertTrue(np.isfinite(value).all())
            self.assertTrue(np.all((stars.luminosity >= 0) & (stars.luminosity <= 1.2)))
            self.assertTrue(np.all((stars.warmth >= 0) & (stars.warmth <= 1)))
        np.testing.assert_array_equal(self.sampler.sample(frame, 'raw').positions,
                                      frame['positions'][1:].astype(np.float32))

    def test_no_cross_origin_links_even_when_galaxies_overlap(self):
        frame = frame_fixture(40)
        frame['positions'][frame['origin'] == 0] = [-.5, 0, 0]
        frame['positions'][frame['origin'] == 1] = [.5, 0, 0]
        stars = self.sampler.sample(frame)
        self.assertTrue(np.all(stars.positions[stars.origin == 0, 0] < -.45))
        self.assertTrue(np.all(stars.positions[stars.origin == 1, 0] > .45))

    def test_stretched_links_do_not_fill_space_or_emit_synthetic_light(self):
        frame = frame_fixture(4)
        frame['origin'][:] = 0
        frame['positions'][:] = [[0, 0, 0], [10, 0, 0], [20, 0, 0], [30, 0, 0]]
        stars = self.sampler.sample(frame)
        self.assertTrue(np.all(stars.luminosity[4:] == 0))
        nearest = np.min(np.linalg.norm(stars.positions[:, None, :] - frame['positions'][None, :, :], axis=2), axis=1)
        self.assertLess(float(nearest.max()), .03)

    def test_reconstruction_follows_live_geometry_with_bounded_footprint(self):
        frame = frame_fixture(80)
        stars = self.sampler.sample(frame)
        owner = np.arange(len(stars.positions) - 80) % 80
        offsets = stars.positions[80:] - frame['positions'][owner]
        self.assertLessEqual(float(np.linalg.norm(offsets, axis=1).max()), .65)
        shift = np.array([2., -3., 1.])
        moved = copy.deepcopy(frame)
        moved['positions'] += shift
        moved['centers'] += shift
        new = self.sampler.sample(moved)
        np.testing.assert_allclose(new.positions, stars.positions + shift, atol=1e-6)
        np.testing.assert_allclose(new.warmth, stars.warmth, atol=1e-6)

    def test_empty_and_one_star_are_finite(self):
        for n in [0, 1]:
            stars = self.sampler.sample(frame_fixture(n))
            self.assertEqual(stars.positions.shape[1], 3)
            self.assertTrue(np.isfinite(stars.positions).all())


if __name__ == '__main__':
    unittest.main()
