import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from roi.core import (CloudSource, Cancelled, InputError, crop_cloud, inside, output_header,
                      ply_header, polygon, sha_file, world_xyz)


class GeometryTests(unittest.TestCase):
    def test_concavity_and_boundary_are_not_replaced_by_bounding_box(self):
        p = polygon([[0, 0], [3, 0], [3, 1], [1, 1], [1, 3], [0, 3]])
        xyz = np.array([[.5, .5, -100], [2, 2, 8], [1, 2, 9], [0, 0, 0], [4, 1, 0]])
        self.assertEqual(inside(p, xyz).tolist(), [True, False, True, True, False])

    def test_crossed_nonfinite_and_repeated_vertices_rejected(self):
        for vertices in ([[0, 0], [2, 2], [0, 2], [2, 0]],
                         [[0, 0], [1, 0], [0, float('nan')]],
                         [[0, 0], [1, 0], [1, 0], [0, 1]]):
            with self.subTest(vertices=vertices), self.assertRaises(InputError):
                polygon(vertices)

    def test_closed_polygon_ring_supported(self):
        self.assertEqual(polygon([[0, 0], [1, 0], [0, 1], [0, 0]]).area, .5)


class CropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.props = [('x', 'float'), ('y', 'float'), ('z', 'float'),
                      ('red', 'uchar'), ('green', 'uchar'), ('blue', 'uchar'),
                      ('nx', 'float'), ('ny', 'float'), ('nz', 'float')]
        self.dt = np.dtype([(n, '<f4' if t == 'float' else 'u1') for n, t in self.props])
        self.data = np.zeros(6, dtype=self.dt)
        self.data['x'] = [0, 0, 0, 0, 0, 0]
        self.data['y'] = [0, 1, 1, 1, 0, 2]
        self.data['z'] = [0, 1, 3, 4, 2, 1]
        self.data['red'] = [10, 20, 30, 40, 50, 60]
        self.data['nx'] = 1
        self.path = self.root / 'source.ply'
        self.path.write_bytes(output_header(len(self.data), self.props) + self.data.tobytes())
        # Rotation about Y: world X depends on LOCAL Z, not on local X.
        self.transform = np.array([[0, 0, 2, 10], [0, 2, 0, 20], [-2, 0, 0, 30], [0, 0, 0, 1.]])
        self.source = CloudSource(self.path, self.transform, sha_file(self.path))
        self.vertices = [[10, 20], [14, 20], [14, 22], [10, 22]]

    def tearDown(self):
        self.temp.cleanup()

    def test_streamed_crop_applies_rotation_and_preserves_exact_original_records(self):
        before = self.path.read_bytes()
        result = crop_cloud(self.source, self.vertices, chunk_size=2)
        self.assertEqual(result['kept'], 3)
        target = self.root / 'cropped.ply'
        cropped = crop_cloud(self.source, self.vertices, target=target, expected_count=3,
                             chunk_size=2, reserve_bytes=0)
        meta = ply_header(target)
        actual = np.fromfile(target, dtype=meta['dtype'], offset=meta['offset'])
        self.assertEqual(actual.tobytes(), self.data[[0, 1, 4]].tobytes())
        self.assertTrue(inside(polygon(self.vertices), world_xyz(actual, self.transform)).all())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(cropped['source_sha256_verified'], hashlib.sha256(before).hexdigest())

    def test_bad_source_checksum_does_not_publish(self):
        self.source.expected_sha256 = '0' * 64
        target = self.root / 'bad.ply'
        with self.assertRaisesRegex(RuntimeError, 'SHA256'):
            crop_cloud(self.source, self.vertices, target=target, expected_count=3, reserve_bytes=0)
        self.assertFalse(target.exists())
        self.assertFalse((self.root / '.bad.ply.part').exists())

    def test_changed_count_does_not_publish(self):
        target = self.root / 'bad-count.ply'
        with self.assertRaisesRegex(RuntimeError, 'conteo'):
            crop_cloud(self.source, self.vertices, target=target, expected_count=4, reserve_bytes=0)
        self.assertFalse(target.exists())

    def test_cancellation_discards_only_own_partial_output(self):
        target = self.root / 'cancelled.ply'
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            crop_cloud(self.source, self.vertices, target=target, expected_count=3,
                       cancel=event, reserve_bytes=0)
        self.assertFalse(target.exists())
        self.assertTrue(self.path.exists())

    def test_reserve_and_output_budget_block_before_copy(self):
        target = self.root / 'too-large.ply'
        with self.assertRaisesRegex(InputError, 'presupuesto'):
            crop_cloud(self.source, self.vertices, target=target, expected_count=3,
                       budget_bytes=1, reserve_bytes=0)
        usage = type('Disk', (), {'free': 100})()
        with patch('roi.core.shutil.disk_usage', return_value=usage):
            with self.assertRaisesRegex(InputError, '50 GiB'):
                crop_cloud(self.source, self.vertices, target=target, expected_count=3,
                           reserve_bytes=90)
        self.assertFalse(target.exists())

    def test_existing_destination_and_partial_are_not_overwritten(self):
        target = self.root / 'existing.ply'
        target.write_bytes(b'user-work')
        with self.assertRaises(InputError):
            crop_cloud(self.source, self.vertices, target=target, expected_count=3, reserve_bytes=0)
        self.assertEqual(target.read_bytes(), b'user-work')

    def test_modified_source_detected_before_read(self):
        self.path.write_bytes(self.path.read_bytes() + b'changed')
        with self.assertRaisesRegex(RuntimeError, 'fuente cambió'):
            crop_cloud(self.source, self.vertices)


if __name__ == '__main__':
    unittest.main()
