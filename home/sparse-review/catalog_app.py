"""Single-port, read-only gallery. Only completed, verified local snapshots."""
import argparse
import json
import struct
import hashlib
from functools import lru_cache
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from app import Handler, ROOT, read_cameras, read_points, encode_cloud


def datasets(collection):
    rows = []
    for receipt in sorted(collection.glob('*/collection.json')):
        data = json.loads(receipt.read_text())
        if data.get('sha256_verified'):
            rows.append(dict(label=receipt.parent.name, dataset=str(receipt.parent)))
    for label, path in [
        ('006 vertical original', '/data/barranco/review/barranco-inputs-20261115/006-single14nov-sequential'),
        ('006 reconectada — NO aprobada', '/data/barranco/review/barranco-inputs-20261115/006-bridges-corrected'),
        ('026 parque — colocación manual sin validar', '/data/barranco/review/barranco-inputs-20261115/026-all'),
        ('020 corte 10fps', '/data/barranco/review/barranco-020-cut10fps-20261116/020-local10fps-268-280'),
    ]:
        if Path(path).is_dir() and not any(r['label'] == label.replace(' ', '-') for r in rows):
            rows.append(dict(label=label, dataset=path))
    active = json.loads(Path('/data/barranco/active/manifest.json').read_text())
    for block, data in active['blocks'].items():
        rows.append(dict(label=block+' · ancla fija (marco local)', model=data['source_sparse']))
    for row in rows:
        row['id'] = hashlib.sha256(row.get('dataset', row.get('model')).encode()).hexdigest()[:16]
    return sorted(rows, key=lambda row: row['label'])


def model_catalog(row):
    if 'model' in row:
        models = {'0': Path(row['model'])}
        selected = '0'
    else:
        root = Path(row['dataset'])
        models = {p.name: p for p in sorted((root/'colmap/sparse').iterdir())
                  if p.is_dir() and p.name.isdigit() and (p/'points3D.bin').is_file()}
        selected = (root/'colmap/best_model.txt').read_text().strip()
    items = []
    for name, p in models.items():
        with (p/'points3D.bin').open('rb') as stream:
            count, = struct.unpack('<Q', stream.read(8))
        with (p/'images.bin').open('rb') as stream:
            images, = struct.unpack('<Q', stream.read(8))
        items.append(dict(id=name, points=count, images=images, selected=name == selected))
    return models, dict(models=items, selected=selected,
                        dataset=row.get('dataset', row.get('model')), readonly=True,
                        independent_coordinate_frames=True)


@lru_cache(maxsize=2)
def cloud(path):
    path = Path(path)
    return encode_cloud(read_points(path/'points3D.bin'), read_cameras(path/'images.bin'))


class Gallery(Handler):
    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            rows = datasets(self.server.collection)
            if path == '/api/datasets':
                return self.reply(json.dumps(rows).encode(), 'application/json')
            if path == '/':
                page = """<!doctype html><meta charset="utf-8"><title>Barranco · todas las sparse</title>
<style>body{margin:0;background:#0b1013;color:white;font:14px system-ui}header{padding:10px;display:flex;gap:16px;align-items:center}select{background:#222;color:white;padding:8px;max-width:55vw}iframe{width:100%;height:calc(100vh - 65px);border:0}</style>
<header><b>Barranco · revisión</b><select id="datasets"><option value="">Elegir nube…</option></select>
<span>Solo lectura · marcos locales independientes · 011 y 006 multivídeo pendientes de SfM al sondeo</span></header><iframe id="viewer"></iframe>
<script>fetch('/api/datasets').then(r=>r.json()).then(rows=>{rows.forEach(r=>{let o=document.createElement('option');o.value=r.id;o.textContent=r.label;datasets.append(o)});datasets.onchange=()=>{viewer.src=datasets.value===''?'about:blank':'/view/'+datasets.value+'/'};});</script>"""
                return self.reply(page.encode(), 'text/html; charset=utf-8')
            parts = path.strip('/').split('/')
            if len(parts) < 2 or parts[0] != 'view':
                return self.reply(b'Not found', 'text/plain', 404)
            row = next((row for row in rows if row['id'] == parts[1]), None)
            if row is None:
                return self.reply(b'Not found', 'text/plain', 404)
            prefix = '/view/'+parts[1]
            models, catalog = model_catalog(row)
            suffix = parts[2:]
            if not suffix:
                page = (ROOT/'index.html').read_text()
                page = page.replace("'/api/models'", repr(prefix+'/api/models'))
                page = page.replace("'/model/'", repr(prefix+'/model/'))
                return self.reply(page.encode(), 'text/html; charset=utf-8')
            if suffix == ['api', 'models']:
                return self.reply(json.dumps(catalog).encode(), 'application/json')
            if len(suffix) == 3 and suffix[0] == 'model' and suffix[1] in models:
                binary, info = cloud(str(models[suffix[1]]))
                if suffix[2] == 'cloud.bin':
                    return self.reply(binary, 'application/octet-stream')
                if suffix[2] == 'info.json':
                    return self.reply(json.dumps(info).encode(), 'application/json')
            self.reply(b'Not found', 'text/plain', 404)
        except Exception as error:
            self.reply(json.dumps({'error': str(error)}).encode(), 'application/json', 500)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--collection', type=Path, required=True)
    parser.add_argument('--port', type=int, default=8790)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Gallery)
    server.collection = args.collection
    server.serve_forever()
