import json
import os
from pathlib import Path
import shutil
import stat
import time

before = shutil.disk_usage('/').free
root_device = Path('/').stat().st_dev
protected = ('thesis', 'tesis', 'cava', 'barranco')
homes = [p for p in Path('/home').iterdir() if p.is_dir() and not p.is_symlink()]
targets = []
for home in homes:
    suffixes = ['.cache/pip', '.cache/uv', '.nv/ComputeCache']
    if NODE_TAG == 'L507_007':
        suffixes.append('.cache/google-chrome')
    for suffix in suffixes:
        path = home/suffix
        if path.is_dir() and not path.is_symlink():
            targets.append((path, 'cache'))
    for suffix in ('miniconda3/pkgs', 'anaconda3/pkgs', 'exit/pkgs'):
        path = home/suffix
        if path.is_dir() and not path.is_symlink():
            targets.append((path, 'conda_archives'))

# Refuse to touch files held open by any process, even inside approved caches.
opened = set()
for fd in Path('/proc').glob('[0-9]*/fd/*'):
    try:
        s = fd.stat()
        opened.add((s.st_dev, s.st_ino))
    except OSError:
        pass
deleted = []
for target, kind in targets:
    assert target.resolve() == target and target.stat().st_dev == root_device
    paths = target.rglob('*') if kind == 'cache' else target.iterdir()
    for path in paths:
        if any(token in str(path).lower() for token in protected):
            continue
        try:
            s = path.lstat()
            if not stat.S_ISREG(s.st_mode) or s.st_dev != root_device:
                continue
            if kind == 'conda_archives' and not path.name.endswith(('.tar.bz2', '.conda')):
                continue
            if time.time()-s.st_mtime < 86400 or (s.st_dev, s.st_ino) in opened:
                continue
            current = path.lstat()
            if (s.st_ino, s.st_size, s.st_mtime_ns) != (current.st_ino, current.st_size, current.st_mtime_ns):
                continue
            path.unlink()
            deleted.append({'path': str(path), 'bytes': s.st_size})
        except FileNotFoundError:
            continue
print('ADMIN_REPLY='+json.dumps({
    'tag':NODE_TAG, 'deleted':deleted,
    'freed_gib':round((shutil.disk_usage('/').free-before)/2**30,3),
    'root_free_gib':round(shutil.disk_usage('/').free/2**30,2)
}))
