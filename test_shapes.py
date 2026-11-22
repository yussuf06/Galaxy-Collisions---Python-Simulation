"""Physics continuity, spherical companion and display invariants."""
import tempfile
from pathlib import Path
import unittest
import numpy as np
from PySide6.QtCore import QCoreApplication
from galaxy_app.colour import grade_colours,compress_light
from galaxy_app.physics import NBody
from galaxy_app.dense_stars import DenseStars
from galaxy_app.shape_presets import SHAPES,get_shape,shape_config
from galaxy_app.worker import PhysicsWorker

class ShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QCoreApplication.instance() or QCoreApplication([])

    def test_palette_and_highlights_do_not_change_source_data(self):
        rgba=np.array([[1.,1.,1.,.65],[1.,.5,.2,.3]],np.float32);before=rgba.copy()
        graded=grade_colours(rgba,np.array([0,1]),'aurora')
        np.testing.assert_array_equal(rgba,before)
        np.testing.assert_array_equal(graded[:,3],rgba[:,3])
        light=np.array([[.1,.2,.4],[10.,20.,40.],[1e3,2e3,4e3]])
        mapped=compress_light(light)
        self.assertTrue(np.isfinite(mapped).all())
        self.assertTrue(np.all((mapped>=0)&(mapped<1)))
        self.assertTrue(np.all(np.diff(mapped[:,2])>0))
        np.testing.assert_allclose(mapped[:,0]/mapped[:,2],.25)

    def test_spherical_companion_is_round_and_conserves_momentum(self):
        config=shape_config(dict(count=256,relax_steps=100,tracer_count=128),'penguin')
        engine=NBody(config)
        mask=(engine.kind==0)&(engine.origin==1)
        eigen=np.linalg.eigvalsh(np.cov(engine.positions[mask].T))
        self.assertGreater(eigen[0]/eigen[-1],.2)
        dense=DenseStars.from_engine(engine,128)
        eigen=np.linalg.eigvalsh(np.cov(dense.positions[dense.origin==1].T))
        self.assertGreater(eigen[0]/eigen[-1],.2)
        momentum=np.sum(engine.velocities*engine.masses[:,None],axis=0)
        energy=engine.energy();engine.step(150)
        np.testing.assert_allclose(np.sum(engine.velocities*engine.masses[:,None],axis=0),momentum,atol=1e-10)
        self.assertLess(abs((engine.energy()-energy)/energy),.025)

    def test_suggested_moment_matches_actual_solver_and_checkpoint(self):
        worker=PhysicsWorker({'tracer_count':32,'simulation_only':True})
        messages=[];worker.message.connect(messages.append)
        requested=dict(count=128,relax_steps=0,tracer_count=32)
        worker.handle(dict(action='shape_setup',shape_id='penguin',preview=True,config=requested))
        self.assertFalse([m for m in messages if m['type']=='error'])
        direct=NBody(shape_config(requested,'penguin'))
        tracers=DenseStars.from_engine(direct,32)
        for _ in range(round(get_shape('penguin')['time']/direct.dt)):
            direct.step();tracers.advance(direct,direct.dt)
        np.testing.assert_array_equal(worker.engine.positions,direct.positions)
        np.testing.assert_array_equal(worker.tracers.positions,tracers.positions)
        self.assertEqual(worker.phase,'paused');self.assertEqual(worker.mode,'simulation')
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'shape.npz';worker.save(path)
            worker.handle(dict(action='reset'))
            self.assertEqual(worker.engine.time,0.)
            worker.load(path)
            self.assertEqual(worker.engine.config['morphology_b'],'spheroid')
            np.testing.assert_array_equal(worker.engine.positions,direct.positions)
            np.testing.assert_array_equal(worker.tracers.positions,tracers.positions)

    def test_each_recipe_keeps_quality_and_is_independent(self):
        for shape in SHAPES:
            config=shape_config(dict(count=2048,tracer_count=30000,backend='numpy'),shape['id'])
            self.assertEqual(config['count'],2048);self.assertEqual(config['tracer_count'],30000)
            self.assertEqual(config['backend'],'numpy')
            copy=get_shape(shape['id']);copy['config']['speed']=0
            self.assertGreater(get_shape(shape['id'])['config']['speed'],0)

if __name__=='__main__':unittest.main()
