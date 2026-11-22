"""Worker regressions: real physics, checkpoint continuity, and game lifecycle.

Run with the same interpreter used to launch main.py: python -m unittest test_worker -v
No desktop window or extra test dependency is required.
"""
from __future__ import annotations

from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtCore import QCoreApplication

from galaxy_app.worker import END_TIME, PhysicsWorker


class WorkerRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.worker = PhysicsWorker()
        self.messages = []
        self.worker.message.connect(self.messages.append)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def setup_scene(self, **changes):
        config = dict(count=256, seed=123, impact=1.8, speed=.8)
        config.update(changes)
        self.worker.handle({'action': 'setup', 'config': config})
        self.assert_no_errors()
        self.assertEqual(self.worker.phase, 'ready')

    def assert_no_errors(self):
        self.assertFalse([m for m in self.messages if m['type'] == 'error'])

    def checkpoint(self, name='state.npz'):
        return str(Path(self.directory.name) / name)

    def advance_tick(self):
        # Supply elapsed wall time without sleeping; tick still uses its normal
        # step cap, fixed physical dt, scoring, history, and finish logic.
        self.worker.last_clock -= 1.0
        self.worker.tick()

    def test_checkpoint_resumes_exact_trajectory_and_reset(self):
        self.setup_scene()
        original = self.worker.engine.snapshot()
        self.worker.engine.step(75)
        self.worker.phase = 'running'
        self.worker.handle({'action': 'save', 'path': self.checkpoint()})
        self.assertEqual(self.worker.phase, 'paused')
        saved = self.worker.engine.snapshot()
        self.worker.engine.step(40)
        expected = self.worker.engine.snapshot()
        self.worker.handle({'action': 'load', 'path': self.checkpoint()})
        self.assert_no_errors()
        self.assertEqual(self.worker.phase, 'paused')
        self.assertEqual(self.worker.engine.ticks, saved['ticks'])
        self.assertTrue(np.array_equal(self.worker.engine.positions, saved['positions']))
        self.worker.engine.step(40)
        for field in ('positions', 'velocities', 'accelerations'):
            self.assertTrue(np.array_equal(getattr(self.worker.engine, field), expected[field]), field)
        self.worker.handle({'action': 'reset'})
        self.assert_no_errors()
        self.assertEqual(self.worker.engine.ticks, 0)
        self.assertTrue(np.array_equal(self.worker.engine.positions, original['positions']))

    def test_startup_count_and_no_jit_survive_reconfiguration_and_checkpoint(self):
        self.worker = PhysicsWorker({'count':512, 'backend':'numpy', 'relax_steps':0})
        self.worker.message.connect(self.messages.append)
        self.worker.start()
        self.worker.timer.stop()
        self.assert_no_errors()
        self.assertEqual(len(self.worker.engine.masses), 512)
        self.assertEqual(self.worker.engine.backend, 'NumPy')
        self.worker.handle({'action':'setup', 'config':{
            'count':128, 'backend':'auto', 'seed':51, 'relax_steps':0}})
        self.assert_no_errors()
        self.assertEqual(self.worker.engine.backend, 'NumPy')
        self.worker.handle({'action':'save', 'path':self.checkpoint()})
        with np.load(self.checkpoint(), allow_pickle=False) as archive:
            saved = {name:archive[name].copy() for name in archive.files}
        metadata = json.loads(saved['metadata'].item())
        metadata['config']['backend'] = 'auto'
        saved['metadata'] = np.array(json.dumps(metadata))
        np.savez_compressed(self.checkpoint(), **saved)
        self.worker.handle({'action':'load', 'path':self.checkpoint()})
        self.assert_no_errors()
        self.assertEqual(self.worker.engine.backend, 'NumPy')
        self.worker.handle({'action':'reset'})
        self.assert_no_errors()
        self.assertEqual(self.worker.engine.backend, 'NumPy')

    def test_rewind_replays_the_same_physical_trajectory(self):
        self.setup_scene()
        self.worker.handle({'action': 'play'})
        while self.worker.engine.time < 3:
            self.advance_tick()
        self.worker.handle({'action': 'pause'})
        latest = self.worker.engine.snapshot()
        self.worker.handle({'action': 'rewind'})
        self.assertEqual(self.worker.phase, 'paused')
        self.assertLess(self.worker.engine.ticks, latest['ticks'])
        self.worker.engine.step(latest['ticks'] - self.worker.engine.ticks)
        self.assertTrue(np.array_equal(self.worker.engine.positions, latest['positions']))
        self.assertTrue(np.array_equal(self.worker.engine.velocities, latest['velocities']))
        self.assert_no_errors()

    def test_failed_startup_reports_exception_and_can_retry(self):
        with self.assertLogs('galaxy_app.worker', level='ERROR'), patch(
            'galaxy_app.worker.NBody', side_effect=ImportError('test startup dependency failure')
        ):
            self.worker.handle({'action': 'setup', 'config': {'count': 256}})
        errors = [m for m in self.messages if m['type'] == 'error']
        self.assertEqual(len(errors), 1)
        self.assertIn('ImportError', errors[0]['text'])
        self.assertIn('test startup dependency failure', errors[0]['text'])
        self.assertIsNone(self.worker.engine)
        self.assertNotIn(self.worker.phase, ('loading', 'planning', 'running'))
        self.messages.clear()
        self.setup_scene()

    def test_invalid_checkpoint_preserves_existing_scene(self):
        self.setup_scene()
        self.worker.engine.step(60)
        prior = self.worker.engine.snapshot()
        self.worker.handle({'action': 'save', 'path': self.checkpoint()})
        with np.load(self.checkpoint(), allow_pickle=False) as archive:
            damaged = {name: archive[name].copy() for name in archive.files}
        damaged['positions'][0, 0] = np.nan
        broken = self.checkpoint('broken.npz')
        np.savez_compressed(broken, **damaged)
        self.messages.clear()
        with self.assertLogs('galaxy_app.worker', level='ERROR'):
            self.worker.handle({'action': 'load', 'path': broken})
        self.assertTrue(any(m['type'] == 'error' for m in self.messages))
        self.assertEqual(self.worker.engine.ticks, prior['ticks'])
        self.assertTrue(np.array_equal(self.worker.engine.positions, prior['positions']))
        self.assertTrue(np.array_equal(self.worker.engine.velocities, prior['velocities']))

    def test_preparation_reports_progress_and_cancellation_keeps_scene(self):
        self.setup_scene()
        notices = [m for m in self.messages if m['type'] == 'notice' and m.get('busy')]
        progress = [m['progress'] for m in notices]
        self.assertGreater(len(set(progress)), 4)
        self.assertEqual(progress, sorted(progress))
        self.assertEqual(progress[-1], 100)
        self.assertTrue(any('gravity' in m['text'].lower() for m in notices))
        prior = self.worker.engine

        def cancel_after_start(message):
            if message['type'] == 'notice' and message.get('busy'):
                self.worker.cancel_job.set()

        self.worker.message.connect(cancel_after_start)
        self.worker.handle({'action': 'setup', 'config': {'count': 512, 'seed': 456}})
        self.worker.message.disconnect(cancel_after_start)
        self.assertIs(self.worker.engine, prior)
        self.assertEqual(self.worker.phase, 'paused')
        self.assertTrue(any(m['type'] == 'notice' and 'cancelled' in m['text'] for m in self.messages))
        self.messages.clear()
        self.setup_scene(seed=456)

    def test_game_helper_success_checkpoints_and_attempts(self):
        self.worker.handle({'action': 'challenge', 'config': {'count': 512, 'seed': 123}})
        self.assert_no_errors()
        self.assertEqual(self.worker.mode, 'game')
        self.assertIn(self.worker.challenge['objective'], ('tidal', 'bridge'))
        self.assertGreater(self.worker.challenge['threshold'], 0)
        self.worker.handle({'action': 'hint'})
        self.worker.handle({'action': 'save', 'path': self.checkpoint('ready.npz')})
        self.worker.handle({'action': 'load', 'path': self.checkpoint('ready.npz')})
        self.assertEqual(self.worker.phase, 'ready')
        self.assertEqual(self.worker.attempts, 0)
        self.worker.handle({'action': 'play'})
        self.assertEqual(self.worker.attempts, 1)
        self.worker.handle({'action': 'pause'})
        self.worker.handle({'action': 'play'})
        self.assertEqual(self.worker.attempts, 1, 'Resuming must not consume another attempt')
        for _ in range(int(END_TIME / self.worker.engine.dt) + 1):
            if self.worker.phase != 'running':
                break
            self.advance_tick()
        self.assertEqual(self.worker.phase, 'ended')
        results = [m for m in self.messages if m['type'] == 'result']
        self.assertTrue(results[-1]['success'], 'The tested helper must reach its physical goal')
        self.assertGreaterEqual(self.worker.peak, self.worker.challenge['threshold'])
        final_positions = self.worker.engine.positions.copy()
        final_peak = self.worker.peak
        self.worker.handle({'action': 'save', 'path': self.checkpoint('ended.npz')})
        self.worker.handle({'action': 'reset'})
        self.worker.handle({'action': 'load', 'path': self.checkpoint('ended.npz')})
        self.assertEqual(self.worker.phase, 'ended')
        self.assertEqual(self.worker.peak, final_peak)
        self.assertTrue(np.array_equal(self.worker.engine.positions, final_positions))
        self.assertEqual(self.worker.attempts, 1)
        self.worker.handle({'action': 'play'})
        self.assertEqual(self.worker.attempts, 2)
        self.assertEqual(self.worker.engine.ticks, 0)
        self.assertEqual(self.worker.peak, 0)
        self.worker.finish(False)
        self.worker.handle({'action': 'play'})
        self.assertEqual(self.worker.attempts, 3)
        self.worker.finish(False)
        self.worker.handle({'action': 'play'})
        self.assertNotEqual(self.worker.phase, 'running')
        self.assertEqual(self.worker.attempts, 3)
        self.worker.handle({'action': 'reset'})
        self.assertEqual(self.worker.attempts, 0)
        self.assertEqual(self.worker.phase, 'ready')
        self.assert_no_errors()


if __name__ == '__main__':
    unittest.main()
