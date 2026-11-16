from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import threading
import time

import numpy as np
import shapely
from shapely.geometry import Polygon, Point
from shapely.validation import explain_validity

GIB = 1024 ** 3
TYPES = {'float': '<f4', 'float32': '<f4', 'double': '<f8', 'float64': '<f8',
         'uchar': 'u1', 'uint8': 'u1', 'ushort': '<u2', 'uint16': '<u2',
         'int': '<i4', 'uint': '<u4', 'int32': '<i4', 'uint32': '<u4'}


class InputError(ValueError):
    pass


class Cancelled(RuntimeError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def sha_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4 * 1024 ** 2), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + str(threading.get_ident()) + '.tmp')
    try:
        with temporary.open('w') as f:
            json.dump(value, f, indent=2, ensure_ascii=False, allow_nan=False)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def polygon(vertices):
    if not isinstance(vertices, list) or not 3 <= len(vertices) <= 512:
        raise InputError('El polígono necesita entre 3 y 512 vértices.')
    try:
        coords = np.asarray(vertices, dtype=np.float64)
    except (ValueError, TypeError) as exc:
        raise InputError('Coordenadas de polígono inválidas.') from exc
    if coords.ndim != 2 or coords.shape[1] != 2 or not np.isfinite(coords).all():
        raise InputError('Cada vértice debe contener X e Y finitos.')
    if len(coords) > 3 and np.array_equal(coords[0], coords[-1]):
        coords = coords[:-1]
    if len(np.unique(coords, axis=0)) != len(coords):
        raise InputError('Hay vértices duplicados en el contorno.')
    p = Polygon(coords)
    if not p.is_valid:
        raise InputError('Contorno inválido o cruzado: ' + explain_validity(p))
    if p.is_empty or p.area <= 1e-8:
        raise InputError('El contorno no tiene un área válida.')
    shapely.prepare(p)
    return p


def inside(p, world):
    # For point-vs-polygon, intersects includes the boundary, unlike contains.
    return shapely.intersects_xy(p, world[:, 0], world[:, 1])


def world_xyz(data, transform):
    xyz = np.column_stack([data[n] for n in ('x', 'y', 'z')]).astype(np.float64)
    return xyz @ transform[:3, :3].T + transform[:3, 3]


def ply_header(path):
    properties = []
    count = None
    current = None
    with Path(path).open('rb') as f:
        if f.readline().strip() != b'ply':
            raise InputError('La fuente no es PLY.')
        fmt = None
        for _ in range(1000):
            line = f.readline()
            if not line:
                raise InputError('Cabecera PLY incompleta.')
            row = line.decode('ascii').split()
            if not row:
                continue
            if row[0] == 'end_header':
                break
            if row[0] == 'format':
                fmt = row[1]
            elif row[0] == 'element':
                current = row[1]
                if current == 'vertex':
                    count = int(row[2])
                elif int(row[2]):
                    raise InputError('Esta operación acepta nubes, no mallas.')
            elif row[0] == 'property' and current == 'vertex':
                if row[1] not in TYPES or row[1] == 'list':
                    raise InputError('Propiedad PLY no soportada para recorte escalar.')
                properties.append((row[2], row[1]))
        else:
            raise InputError('Cabecera PLY excesiva.')
        offset = f.tell()
    names = [n for n, _ in properties]
    if fmt != 'binary_little_endian' or count is None or count <= 0:
        raise InputError('Se requiere PLY binario little-endian no vacío.')
    if len(set(names)) != len(names) or not {'x', 'y', 'z'} <= set(names):
        raise InputError('Esquema PLY inválido.')
    dt = np.dtype([(n, TYPES[t]) for n, t in properties])
    if Path(path).stat().st_size != offset + count * dt.itemsize:
        raise InputError('El tamaño PLY no coincide con la cabecera.')
    return {'count': count, 'properties': properties, 'offset': offset, 'dtype': dt}


def output_header(count, properties):
    return ('ply\nformat binary_little_endian 1.0\n'
            'comment ROI derivative: original block-local coordinates and attributes\n'
            f'element vertex {count}\n' + ''.join(f'property {t} {n}\n' for n, t in properties)
            + 'end_header\n').encode('ascii')


@dataclass
class CloudSource:
    path: Path
    transform: np.ndarray
    expected_sha256: str
    frame_id: str = '025-local'

    def __post_init__(self):
        self.path = Path(self.path)
        self.transform = np.asarray(self.transform, dtype=np.float64)
        if self.transform.shape != (4, 4) or not np.isfinite(self.transform).all():
            raise InputError('Transformación inválida.')
        self.meta = ply_header(self.path)
        stat = self.path.stat()
        self.stamp = (stat.st_size, stat.st_mtime_ns, stat.st_ino)

    def unchanged(self):
        stat = self.path.stat()
        if self.stamp != (stat.st_size, stat.st_mtime_ns, stat.st_ino):
            raise RuntimeError('La fuente cambió; recarga la aplicación antes de continuar.')


def crop_cloud(source, vertices, *, target=None, expected_count=None, progress=None,
               cancel=None, chunk_size=300_000, preview_budget=120_000,
               reserve_bytes=50 * GIB, budget_bytes=2 * GIB, disk_root=None):
    """Single streaming pass. Retain original record bytes; SHA-verify entire input."""
    p = polygon(vertices)
    source.unchanged()
    meta = source.meta
    count = meta['count']
    target = Path(target) if target else None
    temporary = None
    output = None
    predicted = None
    if target:
        if expected_count is None or not 0 < expected_count <= count:
            raise InputError('Primero analiza una selección no vacía.')
        head = output_header(expected_count, meta['properties'])
        predicted = len(head) + expected_count * meta['dtype'].itemsize
        if predicted > budget_bytes:
            raise InputError('La salida supera el presupuesto de 2 GiB del piloto.')
        if target.exists():
            raise InputError('El destino ya existe: se conserva la revisión anterior.')
        target.parent.mkdir(parents=True, exist_ok=True)
        disk_root = Path(disk_root or target.parent)
        if shutil.disk_usage(disk_root).free < predicted + reserve_bytes + 16 * 1024 ** 2:
            raise InputError('No cabe la salida manteniendo 50 GiB libres. No se inició la copia.')
        temporary = target.with_name('.' + target.name + '.part')
        output = temporary.open('xb')
        output.write(head)
    start = time.monotonic()
    seen = kept = 0
    hasher = hashlib.sha256()
    preview = []
    stride = max(1, math.ceil(count / preview_budget))
    minimum = np.full(3, np.inf)
    maximum = np.full(3, -np.inf)
    last_report = 0
    try:
        with source.path.open('rb') as f:
            hasher.update(f.read(meta['offset']))
            while seen < count:
                if cancel and cancel.is_set():
                    raise Cancelled('Operación cancelada; el original se conserva.')
                n = min(chunk_size, count - seen)
                raw = f.read(n * meta['dtype'].itemsize)
                if len(raw) != n * meta['dtype'].itemsize:
                    raise RuntimeError('Fuente PLY truncada.')
                hasher.update(raw)
                data = np.frombuffer(raw, dtype=meta['dtype'])
                world = world_xyz(data, source.transform)
                if not np.isfinite(world).all():
                    raise RuntimeError('La fuente contiene coordenadas no finitas.')
                mask = inside(p, world)
                local_count = int(mask.sum())
                kept += local_count
                if local_count:
                    selected_world = world[mask]
                    minimum = np.minimum(minimum, selected_world.min(axis=0))
                    maximum = np.maximum(maximum, selected_world.max(axis=0))
                    if output:
                        output.write(data[mask].tobytes())
                first = (-seen) % stride
                selected = np.flatnonzero(mask[first::stride]) * stride + first
                if len(selected):
                    colors = (np.column_stack([data[n][selected] for n in ('red', 'green', 'blue')])
                              if {'red', 'green', 'blue'} <= set(data.dtype.names)
                              else np.full((len(selected), 3), 190))
                    preview.extend(np.column_stack([world[selected], colors]).round(5).tolist())
                seen += n
                now = time.monotonic()
                if now - last_report > .5 or seen == count:
                    if target and shutil.disk_usage(disk_root).free < reserve_bytes:
                        raise RuntimeError('Se alcanzó la reserva de disco; salida parcial descartada.')
                    if progress:
                        progress({'processed': seen, 'source_points': count, 'kept': kept,
                                  'percent': round(100 * seen / count, 2), 'elapsed_s': now - start})
                    last_report = now
        source.unchanged()
        actual_sha = hasher.hexdigest()
        if actual_sha != source.expected_sha256:
            raise RuntimeError('SHA256 de la nube original distinto al registrado. No se publica la salida.')
        if output:
            if kept != expected_count:
                raise RuntimeError('El conteo cambió respecto al análisis. No se publica la salida.')
            output.flush()
            os.fsync(output.fileno())
            output.close()
            output = None
            if temporary.stat().st_size != predicted:
                raise RuntimeError('Tamaño inesperado de la salida.')
            if cancel and cancel.is_set():
                raise Cancelled('Cancelado antes de publicar.')
            temporary.rename(target)
        return {'source_points': count, 'kept': kept, 'discarded': count - kept,
                'kept_percent': round(100 * kept / count, 4), 'source_sha256_verified': actual_sha,
                'estimated_ply_bytes': len(output_header(kept, meta['properties'])) + kept * meta['dtype'].itemsize,
                'area_m2': p.area, 'elapsed_s': time.monotonic() - start,
                'world_bounds': [minimum.tolist(), maximum.tolist()] if kept else None,
                'preview': preview, 'preview_sampling_stride': stride,
                'coordinate_frame': source.frame_id if target else 'map_world',
                'export_path': str(target) if target else None,
                'attributes': [n for n, _ in meta['properties']],
                'visibility': 'Scalar source: no per-point camera visibility lists',
                'boundary_rule': 'XY intersects polygon, including boundary; Z unrestricted'}
    finally:
        if output:
            output.close()
        if temporary:
            temporary.unlink(missing_ok=True)


class BlockDataset:
    def __init__(self, block='025', catalog=None):
        from .catalog import BlockCatalog, read_sparse_points
        catalog = catalog or BlockCatalog()
        catalog.check_block(block)
        record = catalog.records[block]
        self.block = block
        self.node = record['node']
        self.native_source_root = record['native_source_root']
        self.batch_count = record['batch_count']
        self.placement = record['placement']
        self.placement_details = record.get('placement_details', catalog.alignment_audit if block == '023'
                                  else {'placement': 'existing_alignment', 'block': block})
        self.run = record['run']
        self.export_root = catalog.data / 'roi' / block
        entry = record['entry']
        self.transform = record['transform'].copy()
        # The interactive application is sparse-only. Legacy standalone crop
        # utilities above remain available to historical batch scripts.
        self.source = None
        model = record['model']
        files = {name: sha_file(model / name) for name in ('cameras.bin', 'images.bin', 'points3D.bin')}
        xyz, self.colors = read_sparse_points(model)
        self.world = xyz @ self.transform[:3, :3].T + self.transform[:3, 3]
        if not np.isfinite(self.world).all():
            raise RuntimeError('Sparse contiene coordenadas inválidas.')
        self.origin = catalog.origin
        self.identity = {'block': self.block, 'block_revision': entry['block'], 'sparse_hashes': files,
                          'world_from_block': self.transform.tolist(), 'world_origin': self.origin}
        self.fingerprint = digest(self.identity)
        self.payload = {'block': self.block, 'title': record.get('title', 'Manzana '+block), 'sparse_count': len(xyz),
                        'dense_local_available': False,
                        'node': self.node, 'placement': self.placement, 'batch_count': self.batch_count,
                        'fingerprint': self.fingerprint, 'coordinate_frame': 'map_world',
                        'crs': 'EPSG:32718', 'world_origin': self.origin,
                        'full_bounds': [self.world.min(axis=0).tolist(), self.world.max(axis=0).tolist()],
                        'focus_bounds': np.quantile(self.world, [.005, .995], axis=0).tolist(),
                        'points': np.column_stack([self.world, self.colors]).round(5).tolist()}

    def accepts_selection(self, selection):
        if selection.get('fingerprint') == self.fingerprint:
            return True
        # Read-only compatibility: old selections bound identity to a dense
        # checksum. Accept only identical sparse geometry AND placement/origin.
        source = selection.get('source', {})
        return (source.get('sparse_hashes') == self.identity['sparse_hashes']
                and source.get('world_from_block') == self.identity['world_from_block']
                and source.get('world_origin') == self.identity['world_origin']
                and selection.get('block', '025') == self.block)

    def validate(self, vertices):
        p = polygon(vertices)
        kept = int(inside(p, self.world).sum())
        return {'vertices': list(map(list, p.exterior.coords[:-1])), 'area_m2': p.area,
                'sparse_kept': kept, 'sparse_total': len(self.world),
                'sparse_discarded': len(self.world) - kept}
