"""Authorized serial 006/011 replacements; no BA or dense stages."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

root=Path('/data/barranco/manual-graph-editor/jobs')
app=Path('/home/exitoso/home/sparse-review')
for old_id in ['j-f096e7864c154c42bfd03aa8b86a04af','j-405fbafc38434287acd70feb88953499']:
    for status in root.glob('*/status.json'):
        state=json.loads(status.read_text())
        if state.get('state') in ('starting','running'):
            raise RuntimeError('Another editor job is active: '+status.parent.name)
    spec=json.loads((root/old_id/'request.json').read_text())
    database=Path(spec['draft']['source_model']).parents[1]/'database.db'
    receipt=json.loads((database.parent/'editor-database-receipt.json').read_text())
    with database.open('rb') as f:
        assert hashlib.file_digest(f,'sha256').hexdigest()==receipt['sha256']
    memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    assert int(memory['MemAvailable'].split()[0])/1024**2>=44,'Insufficient RAM reserve'
    assert shutil.disk_usage(root).free>=50*2**30,'Insufficient disk reserve'
    spec.update(database_path=str(database),mode='triangulation_only')
    identity='j-'+uuid.uuid4().hex
    job=root/identity
    job.mkdir()
    (job/'request.json').write_text(json.dumps(spec))
    (job/'retry.json').write_text(json.dumps(dict(previous_job=old_id,edits_unchanged=True,
        mode='triangulation_only',ba_authorized=False,dense_authorized=False)))
    for name in ['graph_job.py','graph_edit.py','app.py']:
        shutil.copy2(app/name,job/name)
    (job/'status.json').write_text(json.dumps(dict(state='starting',retry_of=old_id,
        mode='triangulation_only',geometry_approved=False,dense_authorized=False)))
    print('START',identity,spec['draft']['source_model'],flush=True)
    result=subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-manual-'+identity,
        '-p','MemoryMax=40G','-p','MemorySwapMax=0','-p','CPUQuota=400%',
        '-p','RuntimeMaxSec=3600','-p','Nice=10',
        '-E','OMP_NUM_THREADS=4','-E','OPENBLAS_NUM_THREADS=4',
        '/data/barranco/runtime/alignment311/bin/python','-B',str(job/'graph_job.py'),str(job)])
    status=json.loads((job/'status.json').read_text())
    print(json.dumps(dict(job=identity,status=status)),flush=True)
    if result.returncode or status.get('state')=='failed':
        raise RuntimeError('Stopped after failed bounded job; remaining request preserved')
