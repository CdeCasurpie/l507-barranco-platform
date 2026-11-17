"""Single-port gallery with isolated manual drafts; source snapshots immutable."""
import argparse
import json
import struct
import hashlib
from functools import lru_cache
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from app import Handler, ROOT, read_cameras, read_points, encode_cloud
import re
import subprocess
from graph_edit import get_graph, solve, save_revision, start_job, STATE


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
    for status_path in (STATE/'jobs').glob('j-*/status.json'):
        status=json.loads(status_path.read_text())
        candidate=status_path.parent/'candidate'
        if status.get('state') in ('candidate_review_required','candidate_rejected') and (candidate/'images.bin').is_file():
            request=json.loads((status_path.parent/'request.json').read_text())
            rows.append(dict(label='Manual '+request['draft']['dataset_id'][:8]+' · '+status_path.parent.name[:10]+' · '+status['state'],
                             model=str(candidate)))
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
    def do_POST(self):
        try:
            expected={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
            host=self.headers.get('Host','')
            if host not in expected or self.headers.get('Origin') not in {'http://'+h for h in expected} or self.headers.get('X-Barranco-Editor')!='1':
                return self.reply(b'Local editor origin required','text/plain',403)
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=200000:
                return self.reply(b'Invalid request size','text/plain',413)
            body=json.loads(self.rfile.read(size))
            parts=urlsplit(self.path).path.strip('/').split('/')
            if len(parts)==3 and parts[:2]==['api','cancel'] and re.fullmatch(r'j-[a-f0-9]{32}',parts[2]):
                job=STATE/'jobs'/parts[2]
                if not (job/'request.json').is_file():raise ValueError('Unknown job')
                subprocess.run(['systemctl','--user','stop','barranco-manual-'+parts[2]],check=True,timeout=20)
                return self.reply(b'{"cancelled":true}','application/json')
            if len(parts)!=5 or parts[:2]!=['api','editor']:
                return self.reply(b'Not found','text/plain',404)
            _,_,dataset,component,action=parts
            row=next((r for r in datasets(self.server.collection) if r['id']==dataset),None)
            if row is None or 'model' in row:
                return self.reply(b'Fixed original anchors are not editable','text/plain',403)
            models,_=model_catalog(row)
            if component not in models:raise ValueError('Unknown component')
            model=models[component]
            if action=='solve':result=solve(model,body)
            elif action=='save':result=save_revision(model,body,dataset,component)
            elif action=='adjust':result=start_job(model,body,dataset,component)
            else:return self.reply(b'Not found','text/plain',404)
            return self.reply(json.dumps(result).encode(),'application/json')
        except (ValueError,KeyError,TypeError) as error:
            self.reply(json.dumps({'error':str(error)}).encode(),'application/json',400)
        except Exception as error:
            self.reply(json.dumps({'error':str(error)}).encode(),'application/json',500)

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            rows = datasets(self.server.collection)
            if path=='/editor-assets/graph_editor.js':
                return self.reply((ROOT/'graph_editor.js').read_bytes(),'text/javascript; charset=utf-8')
            parts=path.strip('/').split('/')
            if len(parts)==3 and parts[:2]==['api','job'] and re.fullmatch(r'j-[a-f0-9]{32}',parts[2]):
                job=STATE/'jobs'/parts[2]
                return self.reply((job/'status.json').read_bytes(),'application/json')
            if len(parts)==5 and parts[:2]==['api','editor']:
                _,_,dataset,component,action=parts
                row=next((r for r in rows if r['id']==dataset),None)
                if row is None or 'model' in row:
                    return self.reply(b'Fixed anchors are not editable','text/plain',403)
                models,_=model_catalog(row)
                if component not in models:raise ValueError('Unknown component')
                meta,binary=get_graph(models[component])
                if action=='graph':
                    return self.reply(json.dumps(meta).encode(),'application/json')
                if action=='cloud.bin':
                    return self.reply(binary,'application/octet-stream')
                if action=='history':
                    history=[]
                    if STATE.exists():
                        for f in STATE.glob('g-*.json'):
                            revision=json.loads(f.read_text())
                            if revision['dataset_id']==dataset and revision['component']==component:
                                history.append(revision)
                    return self.reply(json.dumps(sorted(history,key=lambda x:x['created_at'],reverse=True)[:100]).encode(),'application/json')
                return self.reply(b'Not found','text/plain',404)
            if path == '/api/datasets':
                return self.reply(json.dumps(rows).encode(), 'application/json')
            if path == '/':
                page = """<!doctype html><meta charset="utf-8"><title>Barranco · todas las sparse</title>
<style>body{margin:0;background:#0b1013;color:white;font:14px system-ui}header{padding:10px;display:flex;gap:16px;align-items:center}select{background:#222;color:white;padding:8px;max-width:55vw}iframe{width:100%;height:calc(100vh - 65px);border:0}</style>
<header><b>Barranco · revisión</b><select id="datasets"><option value="">Elegir nube…</option></select>
<span>Originales protegidos · editor manual por grafo disponible en cada variante</span></header><iframe id="viewer"></iframe>
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
            if len(suffix)==2 and suffix[0]=='editor' and suffix[1] in models:
                if 'model' in row:
                    return self.reply(b'Fixed original anchors are not editable','text/plain',403)
                page=(ROOT/'graph_editor.html').read_text().replace('__CONTEXT__',
                    json.dumps({'dataset':row['id'],'component':suffix[1],'label':row['label']}))
                return self.reply(page.encode(),'text/html; charset=utf-8')
            if not suffix:
                page = (ROOT/'index.html').read_text()
                page = page.replace("'/api/models'", repr(prefix+'/api/models'))
                page = page.replace("'/model/'", repr(prefix+'/model/'))
                if 'model' not in row:
                    button="""<script>const editorLink=document.createElement('button');
editorLink.textContent='Abrir editor manual por grafo';
editorLink.onclick=()=>location.href=location.pathname.replace(/\\/$/,'')+'/editor/'+document.getElementById('model').value;
document.querySelector('aside').prepend(editorLink);</script>"""
                    page=page.replace('</body>',button+'</body>')
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
