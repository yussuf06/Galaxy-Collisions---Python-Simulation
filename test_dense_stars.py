"""Reference morphology and live-field tracer regression tests."""
import unittest
import numpy as np
from galaxy_app.physics import NBody, NUMBA_AVAILABLE
from galaxy_app.dense_stars import (DenseStars, aggregate_sources,
    generate_cinematic_galaxy, _tracer_force_numpy, _tracer_force_numba,
    _tracer_force_parallel)


class DenseStarsTests(unittest.TestCase):
    def engine(self, **kw):
        return NBody({'count':128, 'seed':123, 'relax_steps':0, **kw})

    def test_generator_matches_original_reference_numbers(self):
        # Recorded by extracting and executing only the original generator
        # from the user's main.py with np.random.seed(123), not its UI code.
        p, v, c = generate_cinematic_galaxy(np.array([1.,2.,3.]),
            np.array([.2,.3,.4]), 75., 200, (30.,15.,0.), 'blue', np.random.RandomState(123))
        expected_p = [[1.4750911517887637,2.734519749964143,3.098556087907974],
                      [-1.5392144973972681,-2.117112875022052,1.3606866004134373],
                      [1.8109225392345167,1.7405945335961617,1.4933534173467449]]
        expected_v = [[-6.553669432667344,4.11919469253114,4.4924377936018605],
                      [3.90774878387661,-1.227603383771418,-1.506562775770798],
                      [5.170089353432834,5.504350839403181,2.178997445547893]]
        expected_c = [[.9281618595123291,.9664755463600159,1.,.6126441359519958],
                      [.5744968056678772,.8014318346977234,1.,.4287383258342743],
                      [.8793962001800537,.9437182545661926,1.,.5872860550880432]]
        np.testing.assert_allclose(p[:3], expected_p, atol=1e-12)
        np.testing.assert_allclose(v[:3], expected_v, atol=1e-12)
        np.testing.assert_allclose(c[:3], expected_c, atol=1e-7)

    def test_generation_uses_local_seed_and_does_not_change_massive_state(self):
        e = self.engine()
        before = e.snapshot(); np.random.seed(71); random_before = np.random.get_state()
        a = DenseStars.from_engine(e, 150)
        b = DenseStars.from_engine(e, 150)
        self.assertEqual(len(a.positions), 300)
        self.assertEqual(set(a.origin), {0,1})
        np.testing.assert_array_equal(a.positions, b.positions)
        np.testing.assert_array_equal(a.velocities, b.velocities)
        np.testing.assert_array_equal(np.random.get_state()[1], random_before[1])
        for key in ('positions','velocities','accelerations'):
            np.testing.assert_array_equal(e.snapshot()[key], before[key])

    def test_aggregation_preserves_mass_and_center_of_mass(self):
        e = self.engine()
        p, m = aggregate_sources(e.positions,e.masses,e.origin,1.25)
        self.assertLess(len(p), len(e.positions))
        self.assertAlmostEqual(float(m.sum()),float(e.masses.sum()),places=12)
        np.testing.assert_allclose(np.sum(p*m[:,None],axis=0),
                                   np.sum(e.positions*e.masses[:,None],axis=0),atol=1e-12)

    def test_force_kernel_agrees_with_direct_numpy_and_far_field(self):
        stars = np.array([[0.,0.,0.],[1.,0.,0.],[0.,0.,100.]])
        src = np.array([[3.,0.,0.],[-3.,0.,0.]])
        mass = np.array([2.,2.]); eps=.45
        expected = _tracer_force_numpy(stars,src,mass,eps)
        if NUMBA_AVAILABLE:
            np.testing.assert_allclose(_tracer_force_numba(stars,src,mass,eps),expected,atol=1e-12)
        self.assertAlmostEqual(expected[0,0],0.,places=12)
        self.assertLess(expected[2,2],0.)
        self.assertAlmostEqual(expected[2,2],-4/100**2,delta=1e-6)

    @unittest.skipUnless(NUMBA_AVAILABLE, 'Optional Numba accelerator unavailable')
    def test_parallel_force_is_bitwise_equal_and_restores_thread_mask(self):
        from numba import get_num_threads, set_num_threads, config
        rng=np.random.default_rng(923)
        stars=rng.normal(size=(4200,3));sources=rng.normal(size=(110,3))
        masses=rng.uniform(.01,.2,len(sources))
        original_stars=stars.copy();original_sources=sources.copy()
        expected=_tracer_force_numba(stars,sources,masses,.45)
        previous=get_num_threads()
        try:
            set_num_threads(min(2,config.NUMBA_NUM_THREADS))
            direct=_tracer_force_parallel(stars,sources,masses,.45)
            np.testing.assert_array_equal(direct,expected)
            tracer=DenseStars();tracer.accelerated=True;tracer.softening=.45
            before=get_num_threads()
            actual=tracer._force(stars,sources,masses)
            self.assertEqual(get_num_threads(),before)
            np.testing.assert_array_equal(actual,expected)
        finally:
            set_num_threads(previous)
        np.testing.assert_array_equal(stars,original_stars)
        np.testing.assert_array_equal(sources,original_sources)

    def test_snapshot_roundtrip_replays_exact_trajectory_with_pending_step(self):
        e = self.engine(); a = DenseStars.from_engine(e, 80)
        e.step(); a.advance(e,e.dt)
        self.assertGreater(a.pending,0.)
        physical = e.snapshot(); state=a.snapshot()
        b = DenseStars.restore(state)
        np.testing.assert_array_equal(a.positions,b.positions)
        for _ in range(11):e.step();a.advance(e,e.dt)
        expected=a.positions.copy(); expected_v=a.velocities.copy()
        e.restore(physical)
        for _ in range(11):e.step();b.advance(e,e.dt)
        np.testing.assert_array_equal(expected,b.positions)
        np.testing.assert_array_equal(expected_v,b.velocities)
        state['positions'][:]=0
        self.assertTrue(np.any(b.positions))
        self.assertAlmostEqual(b.time,e.time)

    def test_live_gravity_changes_tracer_motion_and_is_finite(self):
        e=self.engine();d=DenseStars.from_engine(e,100)
        initial=d.positions.copy();v=d.velocities.copy()
        for _ in range(40):e.step();d.advance(e,e.dt)
        self.assertTrue(np.isfinite(d.positions).all())
        self.assertGreater(np.linalg.norm(d.positions-(initial+v*e.time)),.01)
        self.assertEqual(e.time,d.time)

    def test_isolated_disk_does_not_immediately_disperse(self):
        e=self.engine(isolated=True);d=DenseStars.from_engine(e,600)
        initial=np.linalg.norm(d.positions-e.centers()[0],axis=1)
        for _ in range(140):e.step();d.advance(e,e.dt)
        final=np.linalg.norm(d.positions-e.centers()[0],axis=1)
        self.assertTrue(np.isfinite(final).all())
        self.assertLess(np.quantile(final,.9)/np.quantile(initial,.9),1.5)

    def test_zero_tracers_and_numpy_mode_are_supported(self):
        e=self.engine(backend='numpy');d=DenseStars.from_engine(e,0)
        self.assertEqual(d.positions.shape,(0,3))
        self.assertFalse(d.accelerated)
        e.step(4);d.advance(e,e.dt*4)
        self.assertEqual(DenseStars.restore(d.snapshot()).positions.shape,(0,3))
        d=DenseStars.from_engine(e,20);e.step(4);d.advance(e,e.dt*4)
        self.assertTrue(np.isfinite(d.positions).all())

    def test_invalid_snapshot_and_mismatched_time_are_rejected(self):
        e=self.engine();d=DenseStars.from_engine(e,20)
        with self.assertRaises(ValueError):d.advance(e,.1)
        for key,value in [('pending',1.),('dt',.1),('time',float('nan'))]:
            state=d.snapshot();state[key]=value
            with self.assertRaises(ValueError):DenseStars.restore(state)
        state=d.snapshot();state['positions'][0,0]=np.inf
        with self.assertRaises(ValueError):DenseStars.restore(state)


if __name__=='__main__':
    unittest.main()
