"""Sparse-only polygon revisions; no dense readers or export workers."""
import json
from pathlib import Path
import re
import shutil
import threading
import time

from .core import atomic_json, InputError, GIB

ID = re.compile(r'^[a-z0-9-]{1,80}$')


def safe_id(value):
    if not isinstance(value, str) or not ID.fullmatch(value):
        raise InputError('Identificador inválido.')
    return value


class ReviewService:
    def __init__(self, dataset, state, *, work_gate=None, config_root=None):
        self.dataset = dataset
        self.block = getattr(dataset, 'block', '025')
        self.work_gate = work_gate
        self.state = Path(state)
        self.config_root = Path(config_root or self.state/'exports')
        self.state.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs, self.cancellations = {}, {}  # historical batch callers only

    def resolved_dataset(self):
        return self.dataset.resolve() if callable(getattr(self.dataset, 'resolve', None)) else self.dataset

    def selections(self):
        rows = []
        for p in (self.state/'selections').glob('*.json'):
            item = json.loads(p.read_text())
            rows.append({k: item[k] for k in ('id', 'created_at', 'name', 'area_m2', 'sparse_kept', 'fingerprint')})
        return sorted(rows, key=lambda x: x['created_at'], reverse=True)

    def selection(self, key):
        path = self.state/'selections'/(safe_id(key)+'.json')
        if not path.is_file():
            raise InputError('Selección no encontrada.')
        item = json.loads(path.read_text())
        if item.get('block', '025') != self.block:
            raise InputError('La selección pertenece a otra manzana.')
        dataset = self.resolved_dataset()
        if (item['fingerprint'] != dataset.fingerprint
                and callable(getattr(dataset, 'accepts_selection', None)) and dataset.accepts_selection(item)):
            item = {**item, 'historical_fingerprint': item['fingerprint'],
                    'fingerprint': dataset.fingerprint, 'source': dataset.identity}
        return item

    def export_config(self, selection):
        dataset = self.resolved_dataset()
        if selection['block'] != self.block or selection['fingerprint'] != dataset.fingerprint:
            raise InputError('La selección no coincide con la manzana o la alineación vigente.')
        details = getattr(dataset, 'placement_details', {})
        return {'schema': 3, 'block': self.block, 'selection_id': selection['id'],
            'source_block': details.get('source_block', self.block),
            'name': selection['name'], 'vertices': selection['vertices'],
            'coordinate_frame': 'map_world', 'crs': 'EPSG:32718',
            'world_origin': selection['source'].get('world_origin'),
            'world_from_block': selection['source']['world_from_block'],
            'boundary_rule': 'inside_or_boundary', 'z_limits': None,
            'fingerprint': selection['fingerprint'], 'source': selection['source'],
            'sparse_kept': selection['sparse_kept'], 'area_m2': selection['area_m2'],
            'node_tag': getattr(dataset, 'node', None),
            'native_source_root': getattr(dataset, 'native_source_root', None),
            'placement': getattr(dataset, 'placement', 'existing_alignment'),
            'alignment_provenance': details, 'dense_requires_regeneration': details.get('geometry_changed', False),
            'mesh_parameters': {'method': 'OpenMVS Delaunay + visibility graph-cut',
                'voxel_m': .1, 'min_point_distance_pixels': 0, 'constant_weight': False,
                'decimation': 1, 'close_holes': False, 'smoothing': False, 'max_edge_m': .45},
            'deployment_status': 'not_submitted', 'created_at': selection['created_at']}

    def latest_config(self):
        rows = self.selections()
        if not rows:
            raise InputError('Esta manzana aún no tiene un polígono guardado.')
        return self.export_config(self.selection(rows[0]['id']))

    def publish_config(self, selection):
        config = self.export_config(selection)
        atomic_json(self.config_root/('roi_'+self.block+'.json'), config)
        return config

    def save(self, payload):
        dataset = self.resolved_dataset()
        if payload.get('block', self.block) != self.block:
            raise InputError('La manzana de la solicitud no coincide.')
        if payload.get('fingerprint') != dataset.fingerprint:
            raise InputError('Los datos o su transformación cambiaron. Recarga antes de guardar.')
        result = dataset.validate(payload.get('vertices'))
        name = payload.get('name', '').strip() or 'Región de conservación'
        if len(name) > 100:
            raise InputError('Nombre demasiado largo.')
        key = 's-'+self.block+'-'+str(time.time_ns())
        item = dict(result, id=key, name=name, block=self.block, created_at=time.time(),
                    fingerprint=dataset.fingerprint, source=dataset.identity,
                    coordinate_frame='map_world', crs='EPSG:32718',
                    boundary_rule='inside_or_boundary', z_limits=None)
        atomic_json(self.state/'selections'/(key+'.json'), item)
        self.publish_config(item)
        return {**item, 'config_path': str(self.config_root/('roi_'+self.block+'.json'))}

    def start(self, payload):
        raise InputError('Solo sparse: la densa permanece en la hija; no se analiza ni exporta aquí.')

    def disk(self):
        free = shutil.disk_usage('/data').free
        return {'free_bytes': free, 'reserve_bytes': 50*GIB,
                'usable_bytes': max(0, free-50*GIB), 'source_mounted': Path('/data').is_mount()}
