import importlib.util
from pathlib import Path
import unittest
import numpy as np

spec=importlib.util.spec_from_file_location(
    'rescue_gate',Path(__file__).resolve().parents[1]/'tools/rescue019_sim3_gate.py')
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class Sim3Tests(unittest.TestCase):
    def test_known_similarity(self):
        x=np.array([[0.,0,0],[1,0,0],[0,1,0],[0,0,1]])
        rotation=np.array([[0.,-1,0],[1,0,0],[0,0,1]])
        expected=(2.,rotation,np.array([3.,4,5]))
        result=gate.fit_similarity(x,gate.apply(expected,x))
        np.testing.assert_allclose(gate.apply(result,x),gate.apply(expected,x),atol=1e-10)
        self.assertGreater(np.linalg.det(result[1]),0)

    def test_heldout_is_not_used_in_fit_and_three_views_are_not_robust(self):
        rows=[dict(query_seconds=i,original_center=x,center=x,role=role,inliers=100)
              for i,x,role in [
                  (0,[0.,0,0],'diagnostic'),(1,[1.,0,0],'diagnostic'),
                  (2,[0.,1,0],'diagnostic'),(3,[1.,1,0],'reserved_validation')]]
        t1,r1=gate.assess(rows,.1)
        rows[-1]['center']=[100.,100,100]
        t2,r2=gate.assess(rows,.1)
        for a,b in zip(t1,t2):np.testing.assert_allclose(a,b)
        self.assertTrue(r1['residuals_pass'])
        self.assertFalse(r2['residuals_pass'])
        self.assertFalse(r1['accepted'])
        self.assertFalse(r1['robust_consensus_possible'])


if __name__=='__main__':
    unittest.main()
