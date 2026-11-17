"""Read-only source catalogue, reviewed placement and bounded sparse cache."""
from collections import OrderedDict
import csv
import json
import math
from pathlib import Path
import struct
import threading

import numpy as np

from .core import BlockDataset, InputError, digest

PROJECT = Path(__file__).resolve().parents[1]
DATA = Path('/data/barranco')


def blender_matrix(position, rotation, scale):
    """Blender Euler XYZ with column vectors: T @ Rz @ Ry @ Rx @ S."""
    x, y, z = map(math.radians, rotation)
    cx, sx, cy, sy, cz, sz = math.cos(x), math.sin(x), math.cos(y), math.sin(y), math.cos(z), math.sin(z)
    rx = np.array([[1., 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1., 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1.]])
    matrix = np.eye(4)
    matrix[:3, :3] = rz @ ry @ rx @ np.diag(scale)
    matrix[:3, 3] = position
    return matrix


def reviewed_placements(entries, manual):
    original = {block: np.array(entry['world_from_asset'], dtype=np.float64) for block, entry in entries.items()}
    effective = {block: matrix.copy() for block, matrix in original.items()}
    audit = {'manual_blocks': [], 'original_atlas_preserved': True}
    if manual.get('enabled'):
        if (manual['block'], manual['anchor'], manual['source_frame'], manual['euler_order']) != ('023', '025', 'original_local_sparse', 'XYZ'):
            raise InputError('La revisión manual solo admite 023 local respecto a 025, Euler XYZ.')
        m23 = blender_matrix(**manual['mobile'])
        m25 = blender_matrix(**manual['anchor_capture'])
        relative = np.linalg.inv(m25) @ m23
        new = original['025'] @ relative
        if not np.isfinite(new).all() or np.linalg.det(new[:3, :3]) <= 0:
            raise InputError('Revisión manual inválida.')
        effective['023'] = new
        audit.update(manual_blocks=['023'], anchor='025', source=manual,
                     block25_from_block23=relative.tolist(),
                     original_world_from_023=original['023'].tolist(),
                     world_from_023=new.tolist(), world_from_025=original['025'].tolist(),
                     delta_for_already_world_aligned_023=(new @ np.linalg.inv(original['023'])).tolist())
    for block in original:
        if block != '023' and not np.array_equal(original[block], effective[block]):
            raise RuntimeError('Una transformación no autorizada cambió.')
    return effective, audit


def read_sparse_points(model):
    """COLMAP points3D.bin: read XYZ/RGB, skip tracks without loading observations."""
    path = Path(model) / 'points3D.bin'
    with path.open('rb') as f:
        raw = f.read(8)
        if len(raw) != 8:
            raise InputError('Sparse truncado.')
        count = struct.unpack('<Q', raw)[0]
        if not 0 < count <= 10_000_000:
            raise InputError('Número de puntos sparse inesperado.')
        xyz = np.empty((count, 3), dtype=np.float64)
        colors = np.empty((count, 3), dtype=np.uint8)
        for i in range(count):
            raw = f.read(51)
            if len(raw) != 51:
                raise InputError('Registro sparse truncado.')
            row = struct.unpack('<QdddBBBdQ', raw)
            xyz[i] = row[1:4]
            colors[i] = row[4:7]
            f.seek(row[-1] * 8, 1)
        if f.tell() != path.stat().st_size:
            raise InputError('Longitud de tracks sparse inválida.')
    if not np.isfinite(xyz).all():
        raise InputError('Sparse contiene coordenadas no finitas.')
    return xyz, colors


class DatasetProxy:
    def __init__(self, catalog, block):
        self.catalog, self.block = catalog, block

    def resolve(self):
        return self.catalog.get(self.block)

    def __getattr__(self, name):
        return getattr(self.resolve(), name)


class BlockCatalog:
    def __init__(self, data=DATA, manual_path=None, include_rejected=False):
        self.data = Path(data)
        active_path = self.data / 'active/manifest.json'
        if active_path.is_file() and not include_rejected:
            active = json.loads(active_path.read_text())
            self.origin = active['world_origin']
            self.records, self.entries, self.transforms = {}, {}, {}
            self.alignment_audit = {'placement': 'accepted_fixed_snapshot',
                'original_atlas_preserved': True, 'manual_blocks': [],
                'excluded_blocks': active.get('excluded_blocks', {})}
            for block, row in active['blocks'].items():
                matrix = np.asarray(row['world_from_block'], dtype=np.float64)
                entry = {'block': block, 'categorical_rgb':
                         [int(x) for x in (70+(int(block)*43)%170, 100+(int(block)*67)%150, 90+(int(block)*31)%160)]}
                self.entries[block] = entry
                self.transforms[block] = matrix
                self.records[block] = {'block': block, 'node': row['node'],
                    'run': Path(row['source_run']), 'model': Path(row['source_sparse']),
                    'entry': entry, 'transform': matrix, 'origin': self.origin,
                    'sparse_count': 0, 'dense_count': 0, 'batch_count': 0,
                    'native_source_root': row['native_source_root'], 'placement': 'existing_alignment'}
            self.lock = threading.RLock()
            self.cache = OrderedDict()
            self._overview = None
            return
        exports = self.data / 'exports/barranco-full-v1'
        atlas = json.loads((exports / 'transforms_atlas.json').read_text())
        self.entries = {entry['block'].split('@')[0]: entry for entry in atlas['atlas']}
        self.origin = json.loads((exports / 'map.json').read_text())['world_origin']
        with (exports / 'resultados_por_manzana.csv').open() as f:
            self.rows = {row['manzana']: row for row in csv.DictReader(f)}
        manual_path = Path(manual_path or PROJECT / 'config/manual_alignment_023.json')
        manual = json.loads(manual_path.read_text())
        self.transforms, self.alignment_audit = reviewed_placements(self.entries, manual)
        self.records = {}
        active_path = self.data / 'active/manifest.json'
        excluded = (json.loads(active_path.read_text()).get('excluded_blocks', {})
                    if active_path.is_file() and not include_rejected else {})
        for block, entry in sorted(self.entries.items()):
            if block in excluded:
                continue
            row = self.rows[block]
            run = Path(row['resultado'])
            selected = (run / 'colmap/best_model.txt').read_text().strip()
            if '/' in selected or selected in ('', '.', '..'):
                raise InputError('Modelo sparse seleccionado inválido.')
            receipt = json.loads((run / 'collection-receipt.json').read_text())
            self.records[block] = {'block': block, 'node': row['maquina'], 'run': run,
                'model': run / 'colmap/sparse' / selected, 'entry': entry,
                'transform': self.transforms[block], 'origin': self.origin,
                'sparse_count': int(row['puntos_sparse']), 'dense_count': int(row['puntos_densos']),
                'batch_count': int(row['lotes_densos']), 'quality': row['calidad'],
                'native_source_root': receipt['source'],
                'placement': 'manual_023_relative_to_025' if block == '023' else 'existing_alignment'}
        self.lock = threading.RLock()
        self.cache = OrderedDict()
        self._overview = None

    def check_block(self, block):
        if block not in self.records:
            raise InputError('Manzana desconocida o excluida del conjunto activo.')
        return block

    def get(self, block):
        self.check_block(block)
        with self.lock:
            if block not in self.cache:
                self.cache[block] = BlockDataset(block, self)
            result = self.cache[block]
            self.cache.move_to_end(block)
            while len(self.cache) > 2:
                self.cache.popitem(last=False)
            return result

    def proxy(self, block):
        return DatasetProxy(self, self.check_block(block))

    def summary(self):
        return [{'block': r['block'], 'node': r['node'], 'sparse_count': r['sparse_count'],
                 'title': r.get('title', 'Manzana '+r['block']),
                 'quality': r.get('quality'), 'placement': r['placement']}
                 for r in self.records.values()]

    def overview(self):
        with self.lock:
            if self._overview is not None:
                return self._overview
            blocks = []
            lows, highs = [], []
            for block, r in self.records.items():
                xyz, colors = read_sparse_points(r['model'])
                transform = r['transform']
                world = xyz @ transform[:3, :3].T + transform[:3, 3]
                bounds = np.quantile(world, [.005, .995], axis=0)
                lows.append(bounds[0]); highs.append(bounds[1])
                stride = max(1, math.ceil(len(world) / 8000))
                blocks.append({'block': block, 'label': r.get('source_block', block),
                    'points': world[::stride].round(5).tolist(),
                    'rgb': colors[::stride].tolist(),
                    'color': r['entry']['categorical_rgb'], 'center': np.median(world, axis=0).tolist(),
                    'focus_bounds': bounds.tolist(), 'placement': r['placement'],
                    'total_sparse_points': len(world), 'preview_stride': stride})
            self._overview = {'blocks': blocks, 'coordinate_frame': 'map_world', 'world_origin': self.origin,
                'bounds': [np.min(lows, axis=0).tolist(), np.max(highs, axis=0).tolist()],
                'note': 'Contexto sparse muestreado; la manzana activa se carga completa. Solo se recorta la activa.'}
            return self._overview
