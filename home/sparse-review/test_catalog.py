import json
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from http.server import ThreadingHTTPServer
from catalog_app import Gallery, datasets, model_catalog


class CatalogTests(unittest.TestCase):
    def test_models_are_local_and_selected_exists(self):
        rows = datasets(Path('/nonexistent'))
        self.assertGreaterEqual(len(rows), 14)
        for row in rows:
            models, catalog = model_catalog(row)
            self.assertIn(catalog['selected'], models)
            self.assertTrue(catalog['readonly'])

    def test_http_gallery_and_prefixed_view(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Gallery)
        server.collection = Path('/nonexistent')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:'+str(server.server_port)
        key = datasets(Path('/nonexistent'))[0]['id']
        try:
            with urlopen(base+'/') as response:
                self.assertIn(b'Elegir nube', response.read())
            with urlopen(base+'/view/'+key+'/') as response:
                html = response.read()
                self.assertIn(('/view/'+key+'/api/models').encode(), html)
                self.assertIn(('/view/'+key+'/model/').encode(), html)
            with urlopen(base+'/view/'+key+'/api/models') as response:
                self.assertTrue(json.load(response)['readonly'])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
