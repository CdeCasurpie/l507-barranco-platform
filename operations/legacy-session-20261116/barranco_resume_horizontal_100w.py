import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

assert NODE_TAG=='L507_010'
root=Path('/data/photogrammetry/campaigns/barranco-006-horizontal-nomasks-20261116/cuadra-006')
def capture(args):
    return subprocess.check_output(args,text=True,timeout=30).strip()
assert float(capture(['nvidia-smi','--query-gpu=power.limit','--format=csv,noheader,nounits']))==100
assert not capture(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'])
with (root/'recovery-bootstrap.lock').open('a') as bootstrap:
    fcntl.flock(bootstrap,fcntl.LOCK_EX|fcntl.LOCK_NB)
    state=root/'reconstruction-full-status.json'
    old=json.loads(state.read_text())
    proc=Path('/proc/'+str(old.get('pid'))+'/cmdline')
    assert not (proc.exists() and str(root).encode() in proc.read_bytes())
    assert old['state']=='failed' and old['stage']=='sfm'
    assert old['error'].startswith('SAFETY STOP:')
    assert not (root/'recovery-100w.json').exists(),'Recovery already attempted; inspect first'
    assert shutil.disk_usage('/').free>3.75*2**30
    assert shutil.disk_usage('/data').free>100*2**30
    token=hashlib.sha256((str(root)+'full').encode()).hexdigest()[:12]
    assert not capture(['docker','ps','-q','--filter','label=photogrammetry.run='+token])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    cfg=json.loads((root/'config-full.json').read_text())
    spec=json.loads((root/'reconstruction.json').read_text())
    assert cfg['masking']['enabled'] is False
    for name,expected in spec['bundle_hashes'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
    archive=root/'attempt-history'/(str(time.time_ns())+'-before-100w')
    archive.mkdir(parents=True)
    for name in ('reconstruction-full-status.json','sparse-worker.log','config-full.json','reconstruction.json','sparse-launch.json'):
        p=root/name
        if p.is_file():shutil.copy2(p,archive/name)
    out=root/'outputs/cuadra-006'/spec['full_experiment']
    for name in ('colmap','logs','.stages','metrics'):
        p=out/name
        if p.exists():
            assert not p.is_symlink()
            p.rename(archive/name)
    logs=root/'logs/reconstruction/full'
    if logs.exists():shutil.copytree(logs,archive/'worker-stage-logs')
    with (root/'sparse-worker.log').open('a') as log:
        log.write('\nAUTHORIZED RETRY: 100 W, NO MASKS, OLD SfM ARCHIVED\n')
        log.flush()
        worker=subprocess.Popen(['python3','-B','-u',str(root/'sparse_nomasks_worker.py'),str(root)],
                                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    record={'tag':NODE_TAG,'pid':worker.pid,'action':'restarted_sfm_no_masks',
            'power_limit_w':100,'thermal_guard_modified':False,'frames_reused':1665,
            'history':str(archive),'authorized_at':time.time(),'previous_error':old['error']}
    (root/'recovery-100w.json').write_text(json.dumps(record,indent=2)+'\n')
    print('ADMIN_REPLY='+json.dumps(record))
