from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
from shapely.geometry import Polygon

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pilot import filter_faces


class SurfaceBoundaryTests(unittest.TestCase):
    @patch('pilot.guard')
    def test_triangle_with_inside_vertices_and_centroid_but_crossing_concavity_is_rejected(self, guard):
        p=Polygon([[0,0],[3,0],[3,1],[1,1],[1,3],[0,3]])
        vertices=np.array([[.2,2,0],[2,.2,0],[0,0,0]],float)
        faces,stats=filter_faces(vertices,np.array([[0,1,2]]),p,max_edge=4)
        self.assertEqual(len(faces),0)
        self.assertEqual(stats['rejected_outside_roi'],1)

    @patch('pilot.guard')
    def test_vertical_face_with_degenerate_xy_projection_remains_if_supported_inside_polygon(self, guard):
        p=Polygon([[0,0],[3,0],[3,3],[0,3]])
        vertices=np.array([[1,1,0],[1,1,1],[1,2,0]],float)
        faces,stats=filter_faces(vertices,np.array([[0,1,2]]),p,max_edge=2)
        self.assertEqual(len(faces),1)
        self.assertEqual(stats['rejected_outside_roi'],0)
