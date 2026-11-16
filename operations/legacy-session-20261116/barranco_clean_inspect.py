import collections
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time
import zipfile

def command(argv, timeout=90):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return {'rc': p.returncode, 'stdout': p.stdout[-7000:], 'stderr': p.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {'error': 'timeout'}

before = shutil.disk_usage('/').free
deleted = []
skipped = []
home = Path('/home/utec_alumno')
if NODE_TAG == 'L507_004':
    directory = home/'Descargas'
    assert directory.is_dir() and not directory.is_symlink()
    for path in sorted(directory.iterdir()):
        s = path.lstat()
        if not stat.S_ISREG(s.st_mode) or not path.name.endswith(('.zip', '.zip.part')):
            skipped.append({'path': str(path), 'reason': 'not an inventoried zip download'})
            continue
        if any(x in path.name.lower() for x in ('thesis', 'tesis', 'cava', 'barranco')):
            skipped.append({'path': str(path), 'reason': 'protected name'})
            continue
        if s.st_size:
            try:
                with zipfile.ZipFile(path) as archive:
                    protected = any(any(x in name.lower() for x in
                        ('thesis', 'tesis_cava', 'barranco')) for name in archive.namelist())
                if protected:
                    skipped.append({'path': str(path), 'reason': 'protected archive member'})
                    continue
            except zipfile.BadZipFile:
                pass  # Previously inventoried incomplete browser downloads.
        if time.time() - s.st_mtime < 3600:
            skipped.append({'path': str(path), 'reason': 'recently modified'})
            continue
        opened = False
        for fd in Path('/proc').glob('[0-9]*/fd/*'):
            try:
                if os.readlink(fd) == str(path):
                    opened = True
                    break
            except OSError:
                continue
        if opened:
            skipped.append({'path': str(path), 'reason': 'open file'})
            continue
        current = path.lstat()
        assert (current.st_ino, current.st_size, current.st_mtime_ns) == (s.st_ino, s.st_size, s.st_mtime_ns)
        deleted.append({'path': str(path), 'bytes': s.st_size})
        path.unlink()

result = {
    'tag': NODE_TAG, 'deleted': deleted, 'skipped': skipped,
    'freed_gib': round((shutil.disk_usage('/').free-before)/2**30, 3),
    'disk': command(['df','-h','/','/data']),
    'root_usage': command(['du','-x','-B1','--max-depth=1','/']),
    'failed_units': command(['systemctl','--failed','--no-pager','--plain']),
    'gpu': command(['nvidia-smi','--query-gpu=temperature.gpu,utilization.gpu,memory.used,power.limit','--format=csv,noheader']),
    'gpu_jobs': command(['nvidia-smi','--query-compute-apps=pid,process_name,used_gpu_memory','--format=csv,noheader']),
}
print('ADMIN_REPLY='+json.dumps(result))
