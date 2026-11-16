"""Run with alignment311; synthetic data only."""
import importlib.util
from pathlib import Path
import types
import unittest
import numpy as np
import pycolmap

source = Path(__file__).resolve().parents[1]/'tools/pnp019_diagnostic.py'
spec = importlib.util.spec_from_file_location('pnp_diagnostic',source)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class DiagnosticTests(unittest.TestCase):
    def test_recovers_synthetic_pose_without_changing_camera(self):
        rng=np.random.default_rng(42)
        xyz=rng.uniform([-2,-2,5],[2,2,10],(100,3))
        camera=pycolmap.Camera(model='SIMPLE_RADIAL',width=1080,height=1920,
                               params=[1000.,540.,960.,0.])
        xy=camera.img_from_cam(xyz[:,:2]/xyz[:,2:])
        xy[:15]=rng.uniform([0,0],[1080,1920],(15,2))
        original=pycolmap.Rigid3d()
        query=types.SimpleNamespace(camera_id=1,cam_from_world=original,
                                    projection_center=lambda:np.zeros(3))
        reconstruction=types.SimpleNamespace(cameras={1:camera})
        before=camera.params.copy()
        result=audit.estimate(reconstruction,query,xy,xyz,0)
        self.assertEqual(result['status'],'estimated')
        self.assertGreaterEqual(result['inliers'],85)
        self.assertLess(result['center_change'],1e-5)
        np.testing.assert_array_equal(camera.params,before)

    def test_insufficient_candidates_are_not_a_pose(self):
        result=audit.estimate(None,None,np.zeros((5,2)),np.zeros((5,3)),0)
        self.assertEqual(result['status'],'insufficient_independent_candidates')
        self.assertNotIn('center',result)


if __name__=='__main__':
    unittest.main()
