"""Approved, narrowly scoped central dense/legacy-mesh cleanup; no daughter files."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

DATA = Path('/data/barranco')


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for raw in iter(lambda: stream.read(8 * 1024**2), b''):
            h.update(raw)
    return h.hexdigest()


def main(apply=False):
    assert os.path.ismount('/data')
    active = json.loads((DATA / 'active/manifest.json').read_text())
    assert len(active['blocks']) == 14 and '023' not in active['blocks']
    # Fail closed if any indispensable texturing input is missing or changed.
    for item in active['blocks'].values():
        assert digest(Path(item['mesh'])) == item['mesh_sha256']
        assert digest(Path(item['scene'])) == item['scene_sha256']
        for image in item['images']:
            p = Path(image['path'])
            assert p.is_file() and p.stat().st_size == image['bytes']
            assert digest(p) == image['sha256']
    assert digest(Path(active['blend'])) == active['blend_sha256']
    candidates = []
    global_link = DATA / 'exports/barranco-full-v1/dense_global.ply'
    if global_link.exists():
        p = global_link.resolve(strict=True)
        assert p.is_relative_to(DATA / 'alignment/barranco-full-v1/exports')
        assert p.name == 'combined.ply' and p.stat().st_size == 164597948033
        candidates.append((p, 'Obsolete global dense; cameras and mesh retained separately'))
    for p in (DATA / 'results/barranco-full-v1').glob('*/*/mvs/scene_dense_scalar.ply'):
        assert not p.is_symlink()
        candidates.append((p, 'Central dense scalar copy; native source retained on daughter'))
    legacy = DATA / 'mesh/barranco-full-v1'
    if legacy.is_dir():
        for p in legacy.rglob('*'):
            if not p.is_file() or p.is_symlink() or 'scripts' in p.relative_to(legacy).parts:
                continue
            if p.suffix.lower() in ('.ply', '.obj', '.mtl', '.jpg', '.jpeg', '.png'):
                candidates.append((p, 'Superseded mesh/texturing experiment'))
    audit = {'created_at': time.time(), 'apply': apply,
             'active_package': str(DATA / 'active/manifest.json'), 'files': []}
    for p, reason in candidates:
        assert p.is_relative_to(DATA)
        assert not p.is_symlink() and p.is_file()
        assert not p.is_relative_to(DATA / 'active')
        busy = subprocess.run(['fuser', str(p)], capture_output=True)
        if busy.returncode != 1:
            raise RuntimeError('File in use or inspection failed: ' + str(p))
        s = p.stat()
        audit['files'].append({'path': str(p), 'bytes': s.st_size, 'inode': s.st_ino,
                               'links': s.st_nlink, 'reason': reason})
    audit['logical_bytes'] = sum(r['bytes'] for r in audit['files'])
    out = DATA / 'active' / ('cleanup-' + str(time.time_ns()) + '.json')
    out.write_text(json.dumps(audit, indent=2))
    print('CANDIDATES', len(candidates), 'GiB', audit['logical_bytes'] / 1024**3, flush=True)
    if not apply:
        print('DRY RUN', out)
        return
    for row in audit['files']:
        p = Path(row['path'])
        stat = p.stat()
        assert (stat.st_ino, stat.st_size) == (row['inode'], row['bytes'])
        p.unlink()
    if global_link.is_symlink() and not global_link.exists():
        global_link.unlink()
    audit['completed_at'] = time.time()
    out.write_text(json.dumps(audit, indent=2))
    print('COMPLETED', out, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
