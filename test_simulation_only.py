"""Legacy checkpoints must preserve physics without restoring retired modes."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
from PySide6.QtCore import QCoreApplication
from galaxy_app.worker import PhysicsWorker


class SimulationOnlyCheckpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_old_modes_load_as_free_simulation_with_exact_physical_state(self):
        worker=PhysicsWorker({'simulation_only':True,'backend':'numpy'})
        messages=[];worker.message.connect(messages.append)
        worker.handle({'action':'setup','config':dict(count=128,relax_steps=0,tracer_count=32,seed=812)})
        worker.engine.step(20);worker.sync_tracers();worker.phase='paused'
        expected=worker.engine.positions.copy();expected_stars=worker.tracers.positions.copy()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.npz'
            worker.save(path)
            with np.load(path,allow_pickle=False) as archive:
                arrays={key:archive[key].copy() for key in archive.files}
            info=json.loads(arrays['metadata'].item())
            for old_mode in ('game','andromeda','photo'):
                with self.subTest(mode=old_mode):
                    legacy={**info,'mode':old_mode,'attempts':3,'peak':1.}
                    arrays['metadata']=np.array(json.dumps(legacy))
                    np.savez_compressed(path,**arrays)
                    worker.load(path)
                    self.assertEqual(worker.mode,'simulation')
                    self.assertEqual(worker.phase,'paused')
                    self.assertEqual(worker.attempts,0)
                    self.assertIsNone(worker.photo);self.assertIsNone(worker.challenge)
                    np.testing.assert_array_equal(worker.engine.positions,expected)
                    np.testing.assert_array_equal(worker.tracers.positions,expected_stars)
        self.assertFalse([message for message in messages if message['type']=='error'])


if __name__=='__main__':unittest.main()
