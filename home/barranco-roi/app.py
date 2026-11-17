#!/usr/bin/env python3
"""Local-only sparse ROI editor. Run using the existing alignment313 Python."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS', '2')
os.environ.setdefault('OMP_NUM_THREADS', '2')

import argparse
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import signal
import threading
import traceback
from urllib.parse import urlsplit, parse_qs

from roi.core import BlockDataset, InputError
from roi.service import ReviewService
from roi.catalog import BlockCatalog
from roi.multi import MultiReviewService
from roi.alignment import AlignmentService, ManualError

ROOT = Path(__file__).resolve().parent
PILOT_ROOT = Path('/data/barranco/roi/025/s-1794364122096131540/pilot-v1')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('%s %s' % (self.log_date_time_string(), fmt % args), flush=True)

    def send(self, code, value, content_type='application/json; charset=utf-8', filename=None,
             cache_control='no-store', etag=None):
        if etag and self.headers.get('If-None-Match') == etag:
            self.send_response(304)
            self.send_header('ETag', etag)
            self.send_header('Cache-Control', cache_control)
            self.end_headers()
            return
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode() if isinstance(value, (dict, list)) else value
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        if filename:
            self.send_header('Content-Disposition', 'attachment; filename="' + filename + '"')
        self.send_header('Cache-Control', cache_control)
        if etag:
            self.send_header('ETag', etag)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def service_for(self, block):
        multi = getattr(self.server, 'multi', None)
        if multi:
            return multi.for_block(block)
        service = self.server.review
        if block != service.block:
            raise InputError('Manzana no disponible en esta instancia.')
        return service

    def alignment_get(self, path, query):
        service = getattr(self.server, 'alignment', None)
        if service is None:
            raise InputError('Alineación no disponible en esta instancia.')
        parts = path.strip('/').split('/')[2:]
        if parts == ['catalog']:
            return self.send(200, service.catalog_payload())
        if parts == ['sessions']:
            rows = service.sessions()
            if query.get('summary') == ['1']:
                rows = [{k: r[k] for k in ('id', 'name', 'created_at', 'reconstruction')} for r in rows]
            return self.send(200, rows)
        if parts == ['jobs']:
            return self.send(200, service.jobs())
        if len(parts) == 2 and parts[0] == 'geometry':
            return self.send(200, service.geometry(parts[1]))
        if len(parts) == 2 and parts[0] == 'cloud':
            version = query.get('v', [None])[0]
            blob, etag = service.render_cloud(parts[1], version)
            return self.send(200, blob, 'application/octet-stream',
                cache_control='private, max-age=31536000, immutable' if version else 'private, no-cache',
                etag=etag)
        if len(parts) == 3 and parts[0] == 'thumbnail':
            raw = service.thumbnail(parts[1], int(parts[2]))
            import hashlib
            return self.send(200, raw, 'image/jpeg', cache_control='private, no-cache',
                             etag='"'+hashlib.sha256(raw).hexdigest()+'"')
        if len(parts) == 2 and parts[0] == 'sessions':
            return self.send(200, service.session(parts[1]))
        if len(parts) in (2, 3) and parts[0] == 'jobs':
            if len(parts) == 2:
                return self.send(200, service.job(parts[1]))
            if parts[2] == 'result':
                return self.send(200, service.result(parts[1]))
            if parts[2] == 'localizations':
                job = service.job(parts[1])
                p = service.root/'jobs'/job['id']/'localizations.json'
                rows = json.loads(p.read_text()) if p.is_file() else []
                return self.send(200, [{k: v for k, v in r.items() if k not in ('observations', 'cross_observations')}
                                       for r in rows])
            if parts[2] == 'geometry':
                result = service.result(parts[1])
                model = result.get('derived_model')
                if not model:
                    raise InputError('El resultado no tiene geometría derivada.')
                from roi.catalog import read_sparse_points
                xyz, colors = read_sparse_points(model)
                import numpy as np
                stride = max(1, int(np.ceil(len(xyz)/60000)))
                return self.send(200, {'points': np.c_[xyz[::stride], colors[::stride]].tolist(),
                                       'bounds': np.quantile(xyz, [.005, .995], axis=0).tolist()})
        return self.send(404, {'error': 'Recurso no encontrado.'})

    def alignment_post(self, path, payload):
        service = getattr(self.server, 'alignment', None)
        if service is None:
            raise InputError('Alineación no disponible.')
        parts = path.strip('/').split('/')[2:]
        operations = {'sessions': service.save, 'candidates': service.candidates,
                      'validate': service.validate_session,
                      'inputs': service.attach, 'jobs': service.start, 'approve': service.approve}
        if len(parts) == 1 and parts[0] in operations:
            return self.send(200, operations[parts[0]](payload))
        if len(parts) == 3 and parts[0] == 'jobs' and parts[2] == 'cancel':
            return self.send(200, service.cancel(parts[1]))
        return self.send(404, {'error': 'Operación no encontrada.'})

    def do_GET(self):
        try:
            url = urlsplit(self.path)
            path = url.path
            query = parse_qs(url.query)
            if path.startswith('/api/alignment/'):
                return self.alignment_get(path, query)
            if path in ('/align.js', '/align.css', '/cloud-renderer.js', '/cloud-cache.js', '/sparse-visualizer.js', '/sparse-visualizer.css'):
                return self.send(200, (ROOT/'web'/path[1:]).read_bytes(),
                    'text/javascript; charset=utf-8' if path.endswith('.js') else 'text/css; charset=utf-8')
            block = query.get('block', ['025'])[0]
            service = self.service_for(block)
            multi = getattr(self.server, 'multi', None)
            if path in ('/', '/index.html', '/app.js', '/style.css', '/multi.css'):
                name = 'index.html' if path == '/' else path[1:]
                mime = {'index.html': 'text/html; charset=utf-8', 'app.js': 'text/javascript; charset=utf-8',
                        'style.css': 'text/css; charset=utf-8', 'multi.css': 'text/css; charset=utf-8'}[name]
                return self.send(200, (ROOT / 'web' / name).read_bytes(), mime)
            if path == '/api/health':
                if multi:
                    from roi.alignment import count
                    sparse_count = count(multi.catalog.records[block]['model']/'points3D.bin')
                else:
                    sparse_count = service.dataset.payload['sparse_count']
                return self.send(200, {'status': 'ready', 'block': service.block,
                    'sparse_count': sparse_count,
                    'available_blocks': list(multi.catalog.records) if multi else [service.block]})
            if path == '/api/blocks':
                return self.send(200, multi.summaries() if multi else [{'block': service.block}])
            if path == '/api/overview' and multi:
                return self.send(200, multi.overview())
            if path == '/api/alignment' and multi:
                return self.send(200, multi.catalog.alignment_audit)
            if path == '/api/dataset':
                return self.send(200, service.dataset.payload)
            if path == '/api/disk':
                return self.send(200, service.disk())
            if path == '/api/pilot':
                if block != '025':
                    return self.send(200, {'status': 'not_started', 'block': block})
                report = PILOT_ROOT / 'pilot-report.json'
                if report.is_file():
                    return self.send(200, json.loads(report.read_text()))
                methods = [name for name in ('delaunay', 'ball_pivoting', 'ransac_planar')
                           if (PILOT_ROOT / (name + '.json')).is_file()]
                return self.send(200, {'status': 'running' if PILOT_ROOT.is_dir() else 'not_started',
                                      'methods': methods, 'selection_id': 's-1794364122096131540'})
            if path in ('/pilot', '/pilot/'):
                if path == '/pilot':
                    self.send_response(302)
                    self.send_header('Location', '/pilot/')
                    self.end_headers()
                    return
                path = '/pilot/gallery.html'
            if path.startswith('/pilot/'):
                target = (PILOT_ROOT / path[len('/pilot/'):]).resolve()
                types = {'.html': 'text/html; charset=utf-8', '.css': 'text/css; charset=utf-8',
                         '.jpg': 'image/jpeg', '.json': 'application/json; charset=utf-8'}
                if target.parent == PILOT_ROOT.resolve() and target.suffix.lower() in types and target.is_file():
                    return self.send(200, target.read_bytes(), types[target.suffix.lower()])
                return self.send(404, {'error': 'Resultado del piloto no disponible.'})
            if path == '/api/selections':
                return self.send(200, service.selections())
            if path == '/api/roi.json':
                selection_id = query.get('selection_id', [None])[0]
                config = (service.export_config(service.selection(selection_id)) if selection_id
                          else service.latest_config())
                return self.send(200, config, filename='roi_' + service.block + '.json')
            parts = path.strip('/').split('/')
            if len(parts) == 3 and parts[:2] == ['api', 'selections']:
                return self.send(200, service.selection(parts[2]))
            self.send(404, {'error': 'Recurso no encontrado.'})
        except (InputError, ManualError, ValueError, KeyError) as exc:
            self.send(400, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            self.send(500, {'error': 'Error interno. Consulta el registro de la aplicación.'})

    def do_POST(self):
        try:
            host = self.headers.get('Host', '')
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if host not in allowed or self.headers.get('X-ROI-Client') != 'local-editor':
                return self.send(403, {'error': 'Esta operación solo está disponible desde el editor local.'})
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://' + h for h in allowed}:
                return self.send(403, {'error': 'Origen no permitido.'})
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4 * 1024**2 or self.headers.get_content_type() != 'application/json':
                return self.send(400, {'error': 'Se requiere una solicitud JSON de hasta 4 MiB.'})
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise InputError('Se requiere un objeto JSON.')
            url = urlsplit(self.path)
            path = url.path
            if path.startswith('/api/alignment/'):
                return self.alignment_post(path, payload)
            block = parse_qs(url.query).get('block', [payload.get('block', '025')])[0]
            if payload.get('block', block) != block:
                raise InputError('La manzana del cuerpo y de la URL no coincide.')
            service = self.service_for(block)
            if path == '/api/validate':
                if payload.get('fingerprint') and payload['fingerprint'] != service.dataset.fingerprint:
                    raise InputError('La alineación o manzana cambió; recarga la vista.')
                return self.send(200, service.dataset.validate(payload.get('vertices')))
            if path == '/api/selections':
                return self.send(201, service.save(payload))
            self.send(404, {'error': 'Operación no encontrada.'})
        except (InputError, ManualError, ValueError, TypeError, KeyError) as exc:
            self.send(400, {'error': str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            self.send(500, {'error': 'Error interno. Consulta el registro de la aplicación.'})


def main():
    parser = argparse.ArgumentParser(description='Barranco · ROI sparse y alineación manual multiancla')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state-dir', type=Path, default=ROOT / 'state')
    args = parser.parse_args()
    state = args.state_dir.resolve()
    state.mkdir(parents=True, exist_ok=True)
    lease = (state / 'server.lock').open('a')
    fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
    print('Preparando sparse y anclas aceptadas, sin leer densas…', flush=True)
    catalog = BlockCatalog()
    alignment = AlignmentService(catalog, state)
    multi = MultiReviewService(catalog, state)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.multi = multi
    server.alignment = alignment
    server.review = multi.for_block('025')
    def stop(*_):
        multi.stop()
        threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f'Listo: http://127.0.0.1:{args.port} · {len(alignment.anchors)} anclas fijas', flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
