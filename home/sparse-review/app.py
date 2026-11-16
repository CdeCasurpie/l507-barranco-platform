"""Read-only local COLMAP component viewer. No third-party dependencies."""
import argparse
from array import array
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import struct
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
DEFAULT = Path('/data/barranco/review/barranco-inputs-20261115/006-single14nov-sequential')


def read_points(path, budget=250_000):
    """Original COLMAP coordinates, sampled uniformly; originals never rewritten."""
    with path.open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        if count > 100_000_000:
            raise ValueError('Invalid point count')
        step = max(1, math.ceil(count / budget))
        xyz, colors, errors, tracks = [], [], [], []
        low, high = [math.inf] * 3, [-math.inf] * 3
        for i in range(count):
            record = f.read(51)
            if len(record) != 51:
                raise ValueError('Truncated point record')
            _, x, y, z, r, g, b, error, n = struct.unpack('<QdddBBBdQ', record)
            if n > 10_000_000:
                raise ValueError('Invalid track count')
            f.seek(n * 8, 1)
            if not all(math.isfinite(v) for v in (x, y, z, error)):
                continue
            for j, v in enumerate((x, y, z)):
                low[j], high[j] = min(low[j], v), max(high[j], v)
            if i % step == 0:
                xyz.extend((x, y, z))
                colors.extend((r / 255, g / 255, b / 255))
                errors.append(error)
                tracks.append(n)
        if f.tell() != path.stat().st_size:
            raise ValueError('Point file length mismatch')
    return dict(total=count, shown=len(errors), xyz=xyz, colors=colors,
                errors=errors, tracks=tracks, bounds=[low, high])


def read_cameras(path):
    cameras = []
    with path.open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        for _ in range(count):
            raw = f.read(64)
            if len(raw) != 64:
                raise ValueError('Truncated image record')
            image_id, qw, qx, qy, qz, tx, ty, tz, camera_id = struct.unpack('<i7di', raw)
            name = bytearray()
            while True:
                char = f.read(1)
                if not char:
                    raise ValueError('Truncated image name')
                if char == b'\0':
                    break
                name.extend(char)
                if len(name) > 65536:
                    raise ValueError('Image name too long')
            n, = struct.unpack('<Q', f.read(8))
            f.seek(n * 24, 1)
            norm = math.sqrt(qw*qw + qx*qx + qy*qy + qz*qz)
            if not norm:
                raise ValueError('Invalid quaternion')
            w, x, y, z = (v / norm for v in (qw, qx, qy, qz))
            rotation = [[1-2*y*y-2*z*z, 2*x*y-2*w*z, 2*x*z+2*w*y],
                        [2*x*y+2*w*z, 1-2*x*x-2*z*z, 2*y*z-2*w*x],
                        [2*x*z-2*w*y, 2*y*z+2*w*x, 1-2*x*x-2*y*y]]
            center = [-sum(rotation[k][j] * (tx, ty, tz)[k] for k in range(3)) for j in range(3)]
            cameras.append(dict(id=image_id, camera_id=camera_id,
                                name=name.decode('utf-8', errors='replace'), center=center))
    return cameras


def encode_cloud(points, cameras):
    # Rebase only the displayed float32 buffer. Source coordinates stay intact.
    values = [sorted(points['xyz'][axis::3]) for axis in range(3)]
    center = [v[len(v)//2] if v else 0 for v in values]
    radius_values = sorted(math.dist(points['xyz'][i:i+3], center)
                           for i in range(0, len(points['xyz']), 3))
    radius = max(1e-8, radius_values[int((len(radius_values)-1)*.98)] if radius_values else 1)
    data = array('f')
    for i, (error, track) in enumerate(zip(points['errors'], points['tracks'])):
        data.extend((*( (points['xyz'][i*3+j] - center[j]) / radius for j in range(3)),
                     *points['colors'][i*3:i*3+3], error, float(track)))
    for camera in cameras:
        data.extend((*((camera['center'][j]-center[j])/radius for j in range(3)),
                     1., .42, .05, 0., 1e9))
    if struct.pack('=I', 1) != struct.pack('<I', 1):
        data.byteswap()
    return data.tobytes(), dict(center=center, display_radius=radius,
                               points=points['shown'], camera_count=len(cameras),
                               total_points=points['total'], sampled=points['shown'] < points['total'],
                               cameras=cameras, original_bounds=points['bounds'])


class Handler(BaseHTTPRequestHandler):
    def reply(self, content, mime, status=200):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        try:
            path = urlsplit(self.path).path
            if path == '/':
                return self.reply((ROOT/'index.html').read_bytes(), 'text/html; charset=utf-8')
            if path == '/api/models':
                return self.reply(json.dumps(self.server.catalog).encode(), 'application/json')
            parts = path.strip('/').split('/')
            if len(parts) == 3 and parts[0] == 'model' and parts[1] in self.server.models:
                cloud, info = self.server.load(parts[1])
                if parts[2] == 'cloud.bin':
                    return self.reply(cloud, 'application/octet-stream')
                if parts[2] == 'info.json':
                    return self.reply(json.dumps(info).encode(), 'application/json')
            self.reply(b'Not found', 'text/plain', 404)
        except Exception as exc:
            self.reply(json.dumps({'error': str(exc)}).encode(), 'application/json', 500)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', type=Path, default=DEFAULT)
    parser.add_argument('--port', type=int, default=8780)
    args = parser.parse_args()
    models = {p.name: p for p in sorted((args.dataset/'colmap/sparse').iterdir())
              if p.is_dir() and p.name.isdigit() and (p/'points3D.bin').is_file()}
    selected = (args.dataset/'colmap/best_model.txt').read_text().strip()
    rows = []
    for name, p in models.items():
        with (p/'points3D.bin').open('rb') as f:
            points, = struct.unpack('<Q', f.read(8))
        cameras = read_cameras(p/'images.bin')
        rows.append(dict(id=name, points=points, images=len(cameras),
                         selected=name == selected))
    @lru_cache(maxsize=2)
    def load(name):
        p = models[name]
        return encode_cloud(read_points(p/'points3D.bin'), read_cameras(p/'images.bin'))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    server.models, server.load = models, load
    server.catalog = dict(models=rows, selected=selected, dataset=str(args.dataset),
                          readonly=True, independent_coordinate_frames=True)
    print(f'READ-ONLY VIEWER http://127.0.0.1:{args.port}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
