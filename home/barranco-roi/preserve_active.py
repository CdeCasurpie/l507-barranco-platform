"""Build a self-contained texturing input package before approved central cleanup."""
import hashlib
import json
import os
from pathlib import Path

from roi.catalog import BlockCatalog
from roi.mvs_interface import camera_table, relocate_scene

ROOT = Path(__file__).resolve().parent
DEST = Path('/data/barranco/active')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for raw in iter(lambda: f.read(8 * 1024**2), b''):
            h.update(raw)
    return h.hexdigest()


def link_verified(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        os.link(source, target)
    if target.stat().st_ino != source.stat().st_ino or target.stat().st_dev != source.stat().st_dev:
        raise RuntimeError('Existing destination is not the same preserved content: ' + str(target))


def main():
    assert os.path.ismount('/data')
    catalog = BlockCatalog()
    DEST.mkdir(exist_ok=True)
    manifest = {'schema': 1, 'coordinate_frame': 'map_world', 'world_origin': catalog.origin,
                'excluded_blocks': {'023': 'Rejected by user; recapture required'}, 'blocks': {}}
    for block, record in sorted(catalog.records.items()):
        if block == '023':
            continue
        out = DEST / 'blocks' / block
        scene = record['run'] / 'mvs/scene.mvs'
        table = camera_table(scene)
        photos = []
        for image in table['images']:
            path = Path(image['name'])
            source = path if path.is_absolute() else scene.parent / path
            parts = path.parts
            assert 'images' in parts
            relative = Path(*parts[parts.index('images') + 1:])
            target = out / 'images' / relative
            link_verified(source.resolve(), target)
            photos.append({'path': str(target), 'bytes': target.stat().st_size,
                           'sha256': sha(target)})
        target_scene = out / 'scene.mvs'
        if not target_scene.exists():
            relocate_scene(scene, target_scene, table, out / 'images')
        verified = camera_table(target_scene)
        assert len(verified['images']) == len(photos)
        assert all(Path(i['name']).is_file() for i in verified['images'])
        for source in record['model'].glob('*.bin'):
            link_verified(source.resolve(), out / 'sparse' / source.name)
        mesh = ROOT / 'exports/mesh-campaign-20261112/simplified_70pct_blocks/meshes' / (
            'manzana_' + block + '_simplified_70pct.ply')
        assert mesh.is_file()
        item = {'block': block, 'node': record['node'], 'source_run': str(record['run']),
                'scene': str(target_scene), 'scene_sha256': sha(target_scene),
                'images': photos, 'mesh': str(mesh), 'mesh_sha256': sha(mesh),
                'world_from_block': record['transform'].tolist(),
                'source_sparse': str(out / 'sparse'),
                'native_source_root': record['native_source_root'].replace('/mnt/datos/', '/data/', 1)}
        (out / 'manifest.json').write_text(json.dumps(item, indent=2))
        manifest['blocks'][block] = item
        print('PRESERVED', block, len(photos), 'images', flush=True)
    assert len(manifest['blocks']) == 14
    manifest['blend'] = str(ROOT / 'exports/mesh-campaign-20261112/simplified_70pct_blocks/barranco_15_manzanas_70pct.blend')
    manifest['blend_sha256'] = sha(Path(manifest['blend']))
    temp = DEST / 'manifest.json.new'
    temp.write_text(json.dumps(manifest, indent=2))
    temp.replace(DEST / 'manifest.json')
    print('ACTIVE PACKAGE VERIFIED', flush=True)


if __name__ == '__main__':
    main()
