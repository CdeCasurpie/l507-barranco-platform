import json
from pathlib import Path
import threading

import numpy as np

from .core import atomic_json
from .service import ReviewService


class MultiReviewService:
    """Per-block state, legacy 025 preserved, one dense operation globally."""
    def __init__(self, catalog, state):
        self.catalog = catalog
        self.state = Path(state)
        self.lock = threading.RLock()
        self.work_gate = threading.BoundedSemaphore(1)
        self.services = {}
        self.config_root = self.state / 'exports'
        atomic_json(self.state / 'alignment-review.json', catalog.alignment_audit)
        atomic_json(self.state / 'effective-transforms.json', {
            'coordinate_frame': 'map_world', 'world_origin': catalog.origin,
            'world_from_block': {b: t.tolist() for b, t in catalog.transforms.items()},
            'manual_blocks': [b for b in catalog.alignment_audit.get('manual_blocks', [])
                              if b in catalog.records], 'anchor': '025'})

    def for_block(self, block):
        self.catalog.check_block(block)
        with self.lock:
            if block not in self.services:
                # Keep every historical 025 path and ID intact.
                path = self.state if block == '025' else self.state / 'blocks' / block
                self.services[block] = ReviewService(self.catalog.proxy(block), path,
                    work_gate=self.work_gate, config_root=self.config_root)
            return self.services[block]

    def summaries(self):
        rows = self.catalog.summary()
        for row in rows:
            block = row['block']
            path = self.state if block == '025' else self.state / 'blocks' / block
            saved = list((path / 'selections').glob('*.json'))
            row.update(selection_count=len(saved), latest_selection_id=None, selected=False)
            if saved:
                selection = max((json.loads(p.read_text()) for p in saved), key=lambda s: s['created_at'])
                dataset = self.catalog.get(block)
                current = dataset.accepts_selection(selection)
                row.update(latest_selection_id=selection['id'], selected=current,
                           selection_area_m2=selection['area_m2'], selection_name=selection['name'],
                           selection_current=current)
        return rows

    def overview(self):
        # Return a new metadata layer while keeping cached point arrays immutable.
        result = dict(self.catalog.overview())
        result['saved_polygons'] = []
        for row in self.summaries():
            if row['selected']:
                service = self.for_block(row['block'])
                item = service.selection(row['latest_selection_id'])
                result['saved_polygons'].append({'block': row['block'], 'vertices': item['vertices']})
        return result

    def stop(self):
        with self.lock:
            for service in self.services.values():
                for event in service.cancellations.values():
                    event.set()
