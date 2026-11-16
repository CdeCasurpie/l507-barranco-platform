import math
from pathlib import Path
import struct
import tempfile
import unittest

from app import read_points, read_cameras, encode_cloud


class ReaderTests(unittest.TestCase):
    def test_points_tracks_colors_and_original_coordinates(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'points3D.bin'
            p.write_bytes(struct.pack('<Q', 1)
                          + struct.pack('<QdddBBBdQ', 17, 10., -4., 2., 255, 128, 0, .75, 2)
                          + struct.pack('<iiii', 2, 3, 4, 5))
            original = p.read_bytes()
            points = read_points(p)
            self.assertEqual(points['xyz'], [10., -4., 2.])
            self.assertEqual(points['tracks'], [2])
            data, meta = encode_cloud(points, [])
            self.assertEqual(len(data), 32)
            self.assertEqual(meta['center'], [10., -4., 2.])
            self.assertEqual(p.read_bytes(), original)

    def test_camera_center_is_inverse_extrinsic_translation(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'images.bin'
            p.write_bytes(struct.pack('<Q', 1)
                          + struct.pack('<i7di', 3, 1., 0., 0., 0., 2., -3., 4., 1)
                          + b'frame.jpg\0' + struct.pack('<Q', 0))
            self.assertEqual(read_cameras(p)[0]['center'], [-2., 3., -4.])

    def test_truncated_points_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)/'points3D.bin'
            p.write_bytes(struct.pack('<Q', 2))
            with self.assertRaisesRegex(ValueError, 'Truncated'):
                read_points(p)


if __name__ == '__main__':
    unittest.main()
