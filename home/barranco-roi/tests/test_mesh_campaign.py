"""Native visibility remapping, source correspondence and concave mesh clipping."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from roi.mvs_interface import camera_table, camera_mapping, relocate_scene

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'runtime/tools/mesh_roi'
SCALAR = ['property float32 x', 'property float32 y', 'property float32 z',
          'property uint8 red', 'property uint8 green', 'property uint8 blue',
          'property float32 nx', 'property float32 ny', 'property float32 nz']
LISTS = ['property list uint8 uint32 view_indices', 'property list uint8 float32 view_weights']


def ply(points, native=False):
    head = 'ply\nformat binary_little_endian 1.0\nelement vertex ' + str(len(points)) + '\n'
    head += '\n'.join(SCALAR + (LISTS if native else [])) + '\nend_header\n'
    raw = head.encode()
    for xyz, view in points:
        raw += struct.pack('<3f3B3f', *xyz, 20, 40, 60, 0, 0, 1)
        if native:
            raw += struct.pack('<BIBf', 1, view, 1, .75)
    return raw


class NativeCampaignTests(unittest.TestCase):
    def test_mvsi_relocation_preserves_nested_image_paths_and_camera_identity(self):
        def text(s):
            b = s.encode()
            return struct.pack('<Q',len(b))+b
        identity = (1.,0.,0.,0.,1.,0.,0.,0.,1.)
        camera = text('PINHOLE')+text('')+struct.pack('<II',100,100)
        camera += struct.pack('<9d',100,0,50,0,100,50,0,0,1)+struct.pack('<9d3d',*identity,0,0,0)
        platform = text('platform')+struct.pack('<Q',1)+camera+struct.pack('<Q9d3d',1,*identity,0,0,0)
        image = text('images/drone/frame.jpg')+text('')+struct.pack('<IIII3fQ',0,0,0,7,0,0,0,0)
        raw = b'MVSI'+struct.pack('<IIQ',7,0,1)+platform+struct.pack('<Q',1)+image+struct.pack('<6Q',0,0,0,0,0,0)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d/'scene.mvs').write_bytes(raw)
            (d/'images/drone').mkdir(parents=True)
            (d/'images/drone/frame.jpg').touch()
            table = camera_table(d/'scene.mvs')
            relocate_scene(d/'scene.mvs',d/'moved.mvs',table,d/'images')
            moved = camera_table(d/'moved.mvs')
            self.assertEqual(moved['images'][0]['name'],str(d/'images/drone/frame.jpg'))
            self.assertEqual(camera_mapping(table,moved),([0],0.))
            moved['images'][0]['C'] = (1.,0.,0.)
            with self.assertRaisesRegex(ValueError,'pose mismatch'):
                camera_mapping(table,moved)

    def test_multibatch_remaps_views_and_verifies_all_scalar_records(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cfg = d / 'polygon.txt'
            cfg.write_text('1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1\n4\n0 0\n1 0\n1 1\n0 1\n')
            points = [((.02,.02,0),0), ((.03,.03,0),0), ((.22,.02,0),1)]
            (d/'scalar.ply').write_bytes(ply(points))
            (d/'a.ply').write_bytes(ply(points[:2],True))
            (d/'b.ply').write_bytes(ply(points[2:],True))
            (d/'batches.txt').write_text(f'2\n"{d}/a.ply" 2 1 3\n"{d}/b.ply" 1 2 5 9\n')
            p = subprocess.run([str(TOOL),'sample',str(cfg),str(d/'batches.txt'),str(d/'scalar.ply'),str(d/'native.ply')],capture_output=True,text=True,check=True)
            result = json.loads(p.stdout)
            self.assertEqual(result['selected_points'],2)
            self.assertEqual(result['scalar_sha256'],hashlib.sha256((d/'scalar.ply').read_bytes()).hexdigest())
            raw = (d/'native.ply').read_bytes().split(b'end_header\n',1)[1]
            self.assertEqual(struct.unpack_from('<I',raw,28)[0],3)
            self.assertEqual(struct.unpack_from('<I',raw,37+28)[0],9)
            corrupted = bytearray((d/'scalar.ply').read_bytes()); corrupted[-1] ^= 1
            (d/'scalar.ply').write_bytes(corrupted)
            p = subprocess.run([str(TOOL),'sample',str(cfg),str(d/'batches.txt'),str(d/'scalar.ply'),str(d/'bad.ply')],capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('attributes differ',p.stderr)

    def test_concavity_crossing_rejected_and_vertical_supported_face_kept(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            poly = [[0,0],[.3,0],[.3,.1],[.1,.1],[.1,.3],[0,.3]]
            (d/'polygon.txt').write_text('1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1\n6\n'+'\n'.join(' '.join(map(str,p)) for p in poly))
            xyz = [(.02,.2,0),(.2,.02,0),(0,0,0),(.02,.2,.2)]
            (d/'native.ply').write_bytes(ply([(p,0) for p in xyz],True))
            mesh = ('ply\nformat binary_little_endian 1.0\nelement vertex 4\nproperty float x\nproperty float y\nproperty float z\nelement face 2\nproperty list uchar int vertex_indices\nend_header\n').encode()
            mesh += b''.join(struct.pack('<3f',*p) for p in xyz)
            mesh += struct.pack('<B3I',3,0,1,2) + struct.pack('<B3I',3,0,3,2)
            (d/'mesh.ply').write_bytes(mesh)
            p = subprocess.run([str(TOOL),'finish',str(d/'polygon.txt'),str(d/'native.ply'),str(d/'mesh.ply'),str(d/'world.ply')],capture_output=True,text=True,check=True)
            result = json.loads(p.stdout)
            self.assertEqual(result['faces'],1)
            self.assertEqual(result['rejected_faces'],1)


if __name__ == '__main__':
    unittest.main()
