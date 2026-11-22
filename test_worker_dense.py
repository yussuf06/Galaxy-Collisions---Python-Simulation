"""Dense stellar continuity through the actual worker's UI actions."""
from pathlib import Path
import json
import tempfile
import unittest

import numpy as np
from PySide6.QtCore import QCoreApplication

from galaxy_app.worker import PhysicsWorker


class DenseWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.worker = PhysicsWorker({'tracer_count':128})
        self.messages = []
        self.worker.message.connect(self.messages.append)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = str(Path(self.directory.name)/'dense.npz')
        self.worker.handle({'action':'setup', 'config':{
            'count':128, 'seed':123, 'relax_steps':0, 'backend':'numpy'}})
        self.assert_no_errors()

    def assert_no_errors(self):
        self.assertFalse([msg for msg in self.messages if msg['type']=='error'])

    def tick(self, count=1):
        self.worker.phase = 'running'
        for _ in range(count):
            self.worker.last_clock -= 1.
            self.worker.tick()
        self.assert_no_errors()

    def test_frame_owns_positions_and_both_galaxies_evolve(self):
        first = [m for m in self.messages if m['type']=='frame'][-1]
        original = first['tracer_positions'].copy()
        self.assertEqual(first['tracer_positions'].shape, (256,3))
        self.assertEqual(first['tracer_colors'].shape, (256,4))
        self.assertEqual(set(first['tracer_origin']), {0,1})
        self.tick(3)
        self.assertTrue(np.array_equal(first['tracer_positions'], original))
        current = [m for m in self.messages if m['type']=='frame'][-1]
        self.assertFalse(np.array_equal(current['tracer_positions'], original))
        self.assertAlmostEqual(self.worker.tracers.time, self.worker.engine.time)
        self.assertTrue(np.isfinite(current['tracer_positions']).all())

    def test_stellar_density_does_not_change_massive_motion_or_scoring(self):
        sparse = PhysicsWorker({'tracer_count':0})
        sparse.handle({'action':'setup','config':{
            **self.worker.engine.config,'tracer_count':0}})
        sparse.phase = 'running'
        self.worker.phase = 'running'
        for _ in range(8):
            for worker in (self.worker,sparse):
                worker.last_clock -= 1.
                worker.tick()
        self.assert_no_errors()
        self.assertIsNone(sparse.tracers)
        self.assertTrue(np.array_equal(sparse.engine.positions,self.worker.engine.positions))
        self.assertTrue(np.array_equal(sparse.engine.velocities,self.worker.engine.velocities))
        self.assertEqual(sparse.engine.metrics(),self.worker.engine.metrics())

    def test_checkpoint_preserves_dense_state_and_continues_exactly(self):
        self.tick(7)
        self.worker.handle({'action':'save','path':self.path})
        saved = self.worker.tracers.positions.copy()
        self.tick(4)
        expected_dense = self.worker.tracers.positions.copy()
        expected_massive = self.worker.engine.positions.copy()
        self.worker.handle({'action':'load','path':self.path})
        self.assert_no_errors()
        self.assertTrue(np.array_equal(self.worker.tracers.positions,saved))
        self.tick(4)
        self.assertTrue(np.array_equal(self.worker.tracers.positions,expected_dense))
        self.assertTrue(np.array_equal(self.worker.engine.positions,expected_massive))

    def test_rewind_restores_dense_history_and_reset_recreates_start(self):
        original = self.worker.tracers.positions.copy()
        self.tick(25)
        latest_tick = self.worker.engine.ticks
        latest_dense = self.worker.tracers.positions.copy()
        self.worker.handle({'action':'pause'})
        self.worker.handle({'action':'rewind'})
        self.assert_no_errors()
        self.assertLess(self.worker.engine.ticks,latest_tick)
        while self.worker.engine.ticks < latest_tick:
            self.worker.engine.step()
            self.worker.tracers.advance(self.worker.engine,self.worker.engine.dt)
        self.assertTrue(np.array_equal(self.worker.tracers.positions,latest_dense))
        self.worker.handle({'action':'reset'})
        self.assert_no_errors()
        self.assertTrue(np.array_equal(self.worker.tracers.positions,original))

    def test_invalid_dense_checkpoint_preserves_existing_scene(self):
        self.tick(3)
        self.worker.handle({'action':'save','path':self.path})
        old_engine = self.worker.engine
        old_tracers = self.worker.tracers
        old_positions = old_tracers.positions.copy()
        with np.load(self.path,allow_pickle=False) as archive:
            content = {key:archive[key].copy() for key in archive.files}
        content['tracer_positions'][0,0] = np.nan
        np.savez_compressed(self.path,**content)
        self.messages.clear()
        with self.assertLogs('galaxy_app.worker',level='ERROR'):
            self.worker.handle({'action':'load','path':self.path})
        self.assertTrue(any(m['type']=='error' for m in self.messages))
        self.assertIs(self.worker.engine,old_engine)
        self.assertIs(self.worker.tracers,old_tracers)
        self.assertTrue(np.array_equal(self.worker.tracers.positions,old_positions))

    def test_legacy_checkpoint_recreates_dense_stars_at_saved_time(self):
        self.tick(3)
        self.worker.handle({'action':'save','path':self.path})
        with np.load(self.path,allow_pickle=False) as archive:
            content = {key:archive[key].copy() for key in archive.files if not key.startswith('tracer_')}
        metadata = json.loads(content['metadata'].item())
        metadata['version'] = 1
        metadata.pop('tracers')
        content['metadata'] = np.array(json.dumps(metadata))
        np.savez_compressed(self.path,**content)
        self.worker.handle({'action':'load','path':self.path})
        self.assert_no_errors()
        self.assertAlmostEqual(self.worker.tracers.time,self.worker.engine.time)
        self.assertEqual(len(self.worker.tracers.positions),256)


if __name__=='__main__':
    unittest.main()
