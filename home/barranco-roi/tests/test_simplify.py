import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simplify_meshes import clean_components, surface_distances, topology, regularize_planes


def grid(n=20):
    x,y=np.meshgrid(np.linspace(0,4,n),np.linspace(0,4,n))
    xyz=np.column_stack([x.ravel(),y.ravel(),np.zeros(n*n)])
    faces=[]
    for j in range(n-1):
        for i in range(n-1):
            a=j*n+i
            faces.extend([[a,a+1,a+n],[a+1,a+n+1,a+n]])
    return xyz,np.array(faces,'i4')


class SimplificationTests(unittest.TestCase):
    def test_distance_is_to_triangle_surface_not_to_vertices(self):
        dense,faces=grid(12)
        coarse=np.array([[0,0,0],[4,0,0],[0,4,0],[4,4,0]],float)
        report=surface_distances(dense,faces,coarse,np.array([[0,1,2],[1,3,2]],'i4'),samples=1000,all_vertices=True)
        for direction in ['reference_to_candidate','candidate_to_reference']:
            self.assertLess(report[direction]['sampled_max_m'],1e-5)
            self.assertEqual(report[direction]['samples'],sum(int(v['n_samples']) for v in report[direction]['filter_summary'].values()))
        self.assertEqual(report['reference_to_candidate']['all_vertex_samples'],len(dense))
        self.assertEqual(report['candidate_to_reference']['all_vertex_samples'],len(coarse))

    def test_cleanup_requires_both_small_area_and_small_diameter(self):
        xyz,faces=grid(3)
        extra=np.array([[10,0,0],[10.03,0,0],[10,.03,0]],float)
        all_xyz=np.r_[xyz,extra]
        all_faces=np.r_[faces,np.array([[9,10,11]],'i4')]
        clean,fc,_,stats=clean_components(all_xyz,all_faces,np.ones((12,3),'u1'))
        self.assertEqual(stats['removed_components'],1)
        self.assertEqual(len(fc),len(faces))
        self.assertEqual(len(clean),len(xyz))

    def test_planar_projection_preserves_open_boundary_and_limits_motion(self):
        xyz,faces=grid(24)
        xyz[:,2]=.015*np.sin(xyz[:,0]*4)*np.sin(xyz[:,1]*4)
        normals,areas,left,right,protected=topology(xyz,faces)
        result,eligible,report=regularize_planes(xyz,faces,normals,areas,left,right,protected,tolerance=.05)
        self.assertTrue(eligible.any())
        self.assertTrue(np.array_equal(result[protected],xyz[protected]))
        self.assertLessEqual(np.linalg.norm(result-xyz,axis=1).max(),.05)
        self.assertGreater(report['connected_regions'],0)


if __name__=='__main__':
    unittest.main()
