import json
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Handler, ThreadingHTTPServer
from roi.catalog import BlockCatalog, reviewed_placements, read_sparse_points
from roi.multi import MultiReviewService

PROJECT=Path(__file__).resolve().parents[1]


class ReviewedAlignmentTests(unittest.TestCase):
    def test_only_023_changes_and_relative_transform_matches_blender_xyz(self):
        manual=json.loads((PROJECT/'config/manual_alignment_023.json').read_text())
        anchor=np.array([[2.,0,0,100],[0,2,0,-40],[0,0,2,8],[0,0,0,1]])
        entries={'001':{'world_from_asset':np.eye(4).tolist()},
                 '023':{'world_from_asset':(np.eye(4)*4).tolist()},
                 '025':{'world_from_asset':anchor.tolist()}}
        transforms,audit=reviewed_placements(entries,manual)
        expected=np.array([[-.9111008546936504,.8034523585684914,-.20538631913354946,-.8634744574963438],
                           [-.3822073682259004,-.13604608439944157,1.1632854295457378,2.238514476208522],
                           [.7359597545045047,.9240020402738883,.3498677883420548,2.3203805467975043],
                           [0,0,0,1]])
        np.testing.assert_allclose(np.linalg.inv(anchor)@transforms['023'],expected,rtol=0,atol=1e-12)
        np.testing.assert_array_equal(transforms['025'],anchor)
        np.testing.assert_array_equal(transforms['001'],np.eye(4))
        self.assertEqual(audit['manual_blocks'],['023'])

    def test_sparse_reader_preserves_coordinates_and_skips_variable_tracks(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'points3D.bin'
            data=struct.pack('<Q',2)
            data+=struct.pack('<QdddBBBdQ',101,1,2,3,4,5,6,.2,1)+struct.pack('<ii',8,9)
            data+=struct.pack('<QdddBBBdQ',102,-1,-2,-3,40,50,60,.4,2)+struct.pack('<iiii',1,2,3,4)
            p.write_bytes(data)
            xyz,rgb=read_sparse_points(Path(directory))
            np.testing.assert_array_equal(xyz,[[1,2,3],[-1,-2,-3]])
            np.testing.assert_array_equal(rgb,[[4,5,6],[40,50,60]])


@unittest.skipUnless(Path('/data/barranco/exports/barranco-full-v1/transforms_atlas.json').is_file(),'local dataset unavailable')
class MultiBlockHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog=BlockCatalog(include_rejected=True)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.state=Path(self.temp.name)
        self.multi=MultiReviewService(self.catalog,self.state)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.multi=self.multi
        self.server.review=self.multi.for_block('025')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.multi.stop();self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def get(self,path):
        with urlopen(self.url+path) as response:return json.load(response)

    def post(self,path,payload):
        request=Request(self.url+path,data=json.dumps(payload).encode(),headers={
            'Content-Type':'application/json','X-ROI-Client':'local-editor'})
        with urlopen(request) as response:return json.load(response)

    def save(self,block):
        d=self.catalog.get(block);lo,hi=np.quantile(d.world,[.2,.8],axis=0)
        vertices=[[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]]
        return self.post('/api/selections?block='+block,{'block':block,'fingerprint':d.fingerprint,
                         'vertices':vertices,'name':'ISOLATED TEST '+block})

    def test_catalog_and_overview_include_15_placed_blocks(self):
        rows=self.get('/api/blocks');self.assertEqual(len(rows),15)
        self.assertEqual(next(r for r in rows if r['block']=='013')['node'],'L507_006')
        self.assertEqual(next(r for r in rows if r['block']=='023')['placement'],'manual_023_relative_to_025')
        overview=self.get('/api/overview')
        self.assertEqual(len(overview['blocks']),15)
        self.assertLessEqual(sum(len(r['points']) for r in overview['blocks']),120000)

    def test_active_catalog_excludes_rejected_block_without_moving_others(self):
        path = Path('/data/barranco/active/manifest.json')
        if not path.is_file():
            self.skipTest('active package not installed')
        current = BlockCatalog()
        active = json.loads(path.read_text())
        self.assertEqual(set(current.records), set(active['blocks']))
        self.assertNotIn('023', current.records)
        for block in current.records:
            np.testing.assert_array_equal(current.transforms[block], self.catalog.transforms[block])

    def test_sparse_roi_works_without_local_dense_and_keeps_identity(self):
        from roi.core import BlockDataset, InputError
        from roi.service import ReviewService
        original = BlockDataset('025', self.catalog)
        is_file = Path.is_file
        def without_dense(path):
            return False if path.name == 'scene_dense_scalar.ply' else is_file(path)
        with patch.object(Path, 'is_file', without_dense):
            sparse = BlockDataset('025', self.catalog)
        self.assertIsNone(sparse.source)
        self.assertEqual(sparse.fingerprint, original.fingerprint)
        self.assertFalse(sparse.payload['dense_local_available'])
        lo, hi = np.quantile(sparse.world, [.2, .8], axis=0)
        service = ReviewService(sparse, self.state / 'sparse-only')
        selection = service.save({
            'block': '025', 'fingerprint': sparse.fingerprint,
            'vertices': [[lo[0], lo[1]], [hi[0], lo[1]], [hi[0], hi[1]], [lo[0], hi[1]]]})
        self.assertEqual(selection['block'], '025')
        with self.assertRaisesRegex(InputError, 'hija'):
            service.start({'kind': 'analyze', 'selection_id': selection['id']})

    def test_selections_and_ready_machine_json_are_isolated(self):
        one=self.save('001');two=self.save('023')
        self.assertEqual(one['block'],'001');self.assertEqual(two['block'],'023')
        self.assertEqual(len(self.get('/api/selections?block=001')),1)
        self.assertEqual(len(self.get('/api/selections?block=023')),1)
        self.assertEqual(len(self.get('/api/selections?block=025')),0)
        exported=self.get('/api/roi.json?block=023&selection_id='+two['id'])
        self.assertEqual(exported['node_tag'],'L507_023')
        self.assertEqual(exported['deployment_status'],'not_submitted')
        self.assertFalse(exported['mesh_parameters']['close_holes'])
        np.testing.assert_array_equal(exported['world_from_block'],self.catalog.transforms['023'])
        self.assertEqual(exported['alignment_provenance']['anchor'],'025')
        self.assertTrue((self.state/'exports/roi_001.json').is_file())
        self.assertTrue((self.state/'exports/roi_023.json').is_file())
        with self.assertRaises(HTTPError):self.get('/api/selections/'+one['id']+'?block=023')

    def test_cross_block_fingerprint_or_body_never_saves(self):
        d=self.catalog.get('001')
        payload={'block':'023','fingerprint':d.fingerprint,'vertices':[[0,0],[1,0],[0,1]]}
        with self.assertRaises(HTTPError):self.post('/api/selections?block=023',payload)
        payload['block']='001'
        with self.assertRaises(HTTPError):self.post('/api/selections?block=023',payload)
        self.assertEqual(self.get('/api/selections?block=023'),[])

    def test_legacy_025_selection_preserved_and_new_revision_sorts_by_date(self):
        old=PROJECT/'state/selections/s-1794364122096131540.json'
        if not old.is_file():self.skipTest('legacy selection unavailable')
        destination=self.state/'selections'/old.name;destination.parent.mkdir(exist_ok=True)
        shutil.copy2(old,destination);before=destination.read_bytes()
        item=json.loads(before)
        self.assertTrue(self.catalog.get('025').accepts_selection(item))
        self.assertEqual(self.multi.for_block('025').selection(item['id'])['historical_fingerprint'],item['fingerprint'])
        rows=self.get('/api/blocks');self.assertTrue(next(r for r in rows if r['block']=='025')['selected'])
        new=self.save('025')
        self.assertEqual(self.get('/api/selections?block=025')[0]['id'],new['id'])
        self.assertEqual(destination.read_bytes(),before)

    def test_dense_busy_gate_does_not_block_saving_another_polygon(self):
        one=self.save('001')
        self.multi.work_gate.acquire()
        try:
            with self.assertRaises(HTTPError):
                self.post('/api/jobs?block=001',{'block':'001','kind':'analyze','selection_id':one['id']})
            two=self.save('023')
            self.assertEqual(two['block'],'023')
        finally:self.multi.work_gate.release()
