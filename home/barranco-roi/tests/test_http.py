import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import Handler, ThreadingHTTPServer
from roi.core import inside, polygon
from roi.service import ReviewService
import numpy as np


class FakeDataset:
    block = '025'
    fingerprint = 'test-source-revision'
    identity = {'block': '025', 'world_from_block': np.eye(4).tolist()}
    payload = {'block': '025', 'sparse_count': 3, 'points': [[0, 0, 0], [1, 1, 2], [4, 4, 5]]}

    def validate(self, vertices):
        p = polygon(vertices)
        kept = int(inside(p, np.array(self.payload['points'])).sum())
        return {'vertices': list(map(list, p.exterior.coords[:-1])), 'area_m2': p.area,
                'sparse_kept': kept, 'sparse_total': 3, 'sparse_discarded': 3-kept}


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.review = ReviewService(FakeDataset(), Path(self.temp.name))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, path, value, extra=None):
        request = Request(self.url + path, data=json.dumps(value).encode(),
                          headers={'Content-Type': 'application/json', 'X-ROI-Client': 'local-editor', **(extra or {})})
        with urlopen(request) as response:
            return json.load(response)

    def test_save_reload_and_revision_do_not_overwrite(self):
        payload = {'vertices': [[0, 0], [2, 0], [2, 2], [0, 2]],
                   'fingerprint': FakeDataset.fingerprint, 'name': 'Prueba'}
        first = self.post('/api/selections', payload)
        second = self.post('/api/selections', payload)
        self.assertNotEqual(first['id'], second['id'])
        with urlopen(self.url + '/api/selections/' + first['id']) as response:
            restored = json.load(response)
        self.assertEqual(restored['vertices'], payload['vertices'])
        self.assertEqual(restored['sparse_kept'], 2)

    def test_cross_origin_write_and_stale_data_are_rejected(self):
        payload = {'vertices': [[0, 0], [2, 0], [0, 2]], 'fingerprint': 'stale'}
        with self.assertRaises(HTTPError) as stale:
            self.post('/api/selections', payload)
        self.assertEqual(stale.exception.code, 400)
        with self.assertRaises(HTTPError) as origin:
            self.post('/api/validate', payload, {'Origin': 'https://elsewhere.invalid'})
        self.assertEqual(origin.exception.code, 403)

    def test_no_general_file_server_and_no_other_blocks(self):
        for path in ['/api/blocks/023', '/state/server.lock', '/../../etc/passwd']:
            with self.subTest(path=path), self.assertRaises(HTTPError) as exc:
                urlopen(self.url + path)
            self.assertEqual(exc.exception.code, 404)
        with urlopen(self.url + '/api/dataset') as response:
            self.assertEqual(json.load(response)['block'], '025')

    def test_export_requires_completed_analysis(self):
        saved = self.post('/api/selections', {'vertices': [[0, 0], [2, 0], [0, 2]],
                                            'fingerprint': FakeDataset.fingerprint})
        with self.assertRaises(HTTPError):
            self.post('/api/jobs', {'kind': 'export', 'selection_id': saved['id'], 'analysis_id': 'missing'})


if __name__ == '__main__':
    unittest.main()
