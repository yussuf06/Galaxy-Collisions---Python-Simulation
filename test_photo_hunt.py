"""Morphology and lifecycle checks for live stellar photography missions."""
from pathlib import Path
import json
import tempfile
import unittest
import numpy as np
from PySide6.QtCore import QCoreApplication
from galaxy_app.photo_hunt import evaluate_feature
from galaxy_app.worker import PhysicsWorker


class PhotoMorphologyTests(unittest.TestCase):
    def test_initial_outer_stars_and_no_encounter_cannot_score(self):
        pos=np.array([[8.,0,0],[9.,0,0],[-8.,0,0],[-9.,0,0]])
        origin=np.array([0,0,1,1]);centers=np.array([[-3.,0,0],[3.,0,0]])
        radii=np.linalg.norm(pos-centers[origin],axis=1)
        for after,closest,isolated in [(False,1.,False),(True,8.,False),(True,1.,True)]:
            r=evaluate_feature(pos,origin,centers,radii,'tidal',after_pericentre=after,closest=closest,isolated=isolated)
            self.assertEqual(r['score'],0);self.assertEqual(r['feature_count'],0)
        r=evaluate_feature(pos,origin,centers,radii,'tidal',after_pericentre=True,closest=1.)
        self.assertEqual(r['score'],0,'Unchanged initial outer points are not tidal evidence')

    def test_tail_and_bridge_indices_match_actual_geometry(self):
        centers=np.array([[-4.,0,0],[4.,0,0]])
        pos=np.array([[-10.,0,0],[-11.,0,0],[-4.,0,0],[4.,0,0]])
        origin=np.array([0,0,0,1]);before=pos.copy()
        result=evaluate_feature(pos,origin,centers,np.ones(4),'tidal',after_pericentre=True,closest=1.)
        np.testing.assert_array_equal(result['indices'],[0,1]);self.assertTrue(result['success'])
        np.testing.assert_array_equal(pos,before)
        bridge=np.array([[-1.,0,0],[1.,.2,0],[-4.,0,0],[4.,0,0]])
        result=evaluate_feature(bridge,origin,centers,np.ones(4),'bridge',after_pericentre=True,closest=1.)
        np.testing.assert_array_equal(result['indices'],[0,1]);self.assertTrue(result['success'])
        result=evaluate_feature(bridge,origin,np.array([[-1.,0,0],[1.,0,0]]),np.ones(4),'bridge',after_pericentre=True,closest=1.)
        self.assertEqual(result['score'],0,'Merged cores do not form a separated bridge')


class PhotoWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def setUp(self):
        self.worker=PhysicsWorker({'tracer_count':300});self.messages=[]
        self.worker.message.connect(self.messages.append)
        self.worker.handle({'action':'photo_setup','config':{'count':512,'tracer_count':300},'objective':'tidal'})
        self.assert_no_errors()
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)

    def assert_no_errors(self):self.assertFalse([m for m in self.messages if m['type']=='error'])

    def step(self,n):
        for _ in range(n):
            self.worker.engine.step();self.worker.tracers.advance(self.worker.engine,self.worker.engine.dt)

    def checkpoint(self):return str(Path(self.directory.name)/'photo.npz')

    def test_capture_freezes_actual_frame_and_enforces_three_shots(self):
        self.worker.handle({'action':'capture'})
        self.assertEqual(self.worker.photo.shot_count,0)
        for shot in range(3):
            self.worker.handle({'action':'play'})
            positions=self.worker.engine.positions.copy();stars=self.worker.tracers.positions.copy()
            self.worker.handle({'action':'capture'})
            np.testing.assert_array_equal(self.worker.engine.positions,positions)
            np.testing.assert_array_equal(self.worker.tracers.positions,stars)
            self.assertEqual(self.worker.photo.shot_count,shot+1)
            self.assertEqual(self.worker.photo.last_capture['source'],'tracers')
            self.assertFalse(self.worker.photo.last_capture['success'])
        self.assertEqual(self.worker.phase,'ended')
        self.worker.handle({'action':'capture'});self.assertEqual(self.worker.photo.shot_count,3)
        self.worker.handle({'action':'reset'});self.assertEqual(self.worker.photo.shot_count,0)
        self.assertEqual(self.worker.phase,'ready');self.assert_no_errors()

    def test_real_visible_stars_produce_reachable_tail_and_bridge(self):
        self.step(round(12./self.worker.engine.dt))
        self.worker.handle({'action':'play'});self.worker.handle({'action':'capture'})
        result=[m for m in self.messages if m['type']=='photo_capture'][-1]
        self.assertTrue(result['success'],result)
        self.assertGreater(len(result['feature_positions']),0)
        all_points=self.worker.tracers.positions.astype(np.float32)
        for point in result['feature_positions']:
            self.assertTrue(np.any(np.all(all_points==point,axis=1)))
        self.worker.handle({'action':'photo_next'})
        self.assertEqual(self.worker.photo.objective,'bridge');self.assertEqual(self.worker.photo.round,2)
        self.step(round(9.5/self.worker.engine.dt))
        self.worker.handle({'action':'play'});self.worker.handle({'action':'capture'})
        self.assertTrue(self.worker.photo.last_capture['success'],self.worker.photo.last_capture)
        self.assertTrue(self.worker.photo.summary()['completed'])
        self.assert_no_errors()

    def test_checkpoint_roundtrip_preserves_photo_and_exact_trajectory(self):
        self.step(120);self.worker.handle({'action':'play'});self.worker.handle({'action':'capture'})
        photo=self.worker.photo.summary()
        self.worker.handle({'action':'save','path':self.checkpoint()})
        self.step(12);expected=self.worker.tracers.positions.copy();massive=self.worker.engine.positions.copy()
        self.worker.handle({'action':'setup','config':{'count':128,'tracer_count':10}})
        self.worker.handle({'action':'load','path':self.checkpoint()})
        self.assertEqual(self.worker.mode,'photo');self.assertEqual(self.worker.photo.summary(),photo)
        self.step(12);np.testing.assert_array_equal(self.worker.tracers.positions,expected)
        np.testing.assert_array_equal(self.worker.engine.positions,massive)
        self.assert_no_errors()

    def test_rewind_does_not_refund_shots_and_invalid_checkpoint_preserves_scene(self):
        self.step(120);self.worker.history.append(self.worker.snapshot())
        self.step(120);self.worker.history.append(self.worker.snapshot())
        self.worker.handle({'action':'play'});self.worker.handle({'action':'capture'})
        now=self.worker.engine.time
        self.worker.handle({'action':'rewind'})
        self.assertLess(self.worker.engine.time,now);self.assertEqual(self.worker.photo.shot_count,1)
        self.worker.handle({'action':'save','path':self.checkpoint()})
        with np.load(self.checkpoint(),allow_pickle=False) as stored:
            arrays={k:stored[k].copy() for k in stored.files}
        info=json.loads(str(arrays['metadata'].item()));info['photo']['objective']='fake'
        arrays['metadata']=np.array(json.dumps(info));np.savez_compressed(self.checkpoint(),**arrays)
        original=self.worker.engine;positions=original.positions.copy();photo=self.worker.photo.summary()
        self.worker.handle({'action':'load','path':self.checkpoint()})
        self.assertIs(self.worker.engine,original)
        np.testing.assert_array_equal(self.worker.engine.positions,positions)
        self.assertEqual(self.worker.photo.summary(),photo)
        self.assertTrue([m for m in self.messages if m['type']=='error'])


if __name__=='__main__':unittest.main()
