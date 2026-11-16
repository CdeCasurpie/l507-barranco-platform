import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

a=next(a for a in BINDINGS['assignments'] if a['node_tag']==NODE_TAG)
root=Path(a['work_root'])
assert json.loads((root/'assignment.json').read_text())==a
assert os.path.ismount('/data')
assert BINDINGS['authorized'] is True and BINDINGS['power_limit_w']==100
assert BINDINGS['thermal_guard_change_authorized'] is False
def capture(args):
    return subprocess.check_output(args,text=True,timeout=30).strip()
power=float(capture(['nvidia-smi','--query-gpu=power.limit','--format=csv,noheader,nounits']))
assert power==100,'100 W must be applied and verified before resuming'
with (root/'sparse-bootstrap.lock').open('a') as bootstrap:
    fcntl.flock(bootstrap,fcntl.LOCK_EX|fcntl.LOCK_NB)
    path=root/'reconstruction-full-status.json'
    old=json.loads(path.read_text())
    proc=Path('/proc/'+str(old.get('pid'))+'/cmdline')
    alive=proc.exists() and str(root).encode() in proc.read_bytes()
    if alive:
        print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'block':a['block_id'],
              'action':'continued_without_restart','pid':old['pid'],'power_limit_w':power,
              'stage':old.get('stage')}))
        raise SystemExit(0)
    if old.get('state') in ('awaiting_review','completed'):
        print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'block':a['block_id'],
              'action':'already_complete_not_restarted','power_limit_w':power}))
        raise SystemExit(0)
    assert old.get('state')=='failed' and str(old.get('error','')).startswith('SAFETY STOP:'),'Unexpected failure requires inspection'
    assert old.get('stage')=='masks'
    assert old.get('completed_stages')==['frames'],'Do not rerun completed SfM'
    previous=root/'recovery-100w.json'
    assert not previous.exists(),'Do not automatically repeat this recovery'
    assert shutil.disk_usage('/').free>3.75*2**30
    assert shutil.disk_usage('/data').free>100*2**30
    assert not capture(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits']),'Another GPU computation is active'
    token=hashlib.sha256((str(root)+'full').encode()).hexdigest()[:12]
    assert not capture(['docker','ps','-q','--filter','label=photogrammetry.run='+token]),'Reconcile existing run containers first'
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    spec=json.loads((root/'reconstruction.json').read_text())
    for name,expected in spec['bundle_hashes'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected
    out=root/'outputs'/('cuadra-'+a['block_id'])/spec['full_experiment']
    assert not (out/'colmap/database.db').exists(),'Do not destroy an existing SfM database'
    archive=root/'attempt-history'/(str(time.time_ns())+'-before-100w')
    archive.mkdir(parents=True)
    shutil.copy2(path,archive/path.name)
    for name in ('sparse-worker.log','config-full.json','reconstruction.json','sparse-launch.json'):
        p=root/name
        if p.is_file():
            shutil.copy2(p,archive/name)
    masks=out/'masks'
    assert not masks.is_symlink()
    if masks.exists():
        os.rename(masks,archive/'partial-masks')
    telemetry=root/'logs/reconstruction/full'
    if telemetry.exists():
        shutil.copytree(telemetry,archive/'worker-stage-logs')
    if (out/'logs').is_dir():
        shutil.copytree(out/'logs',archive/'pipeline-logs')
    record={'tag':NODE_TAG,'block':a['block_id'],'action':'resumed_from_masks',
            'power_limit_w':power,'thermal_guard_modified':False,
            'frames_reused':True,'partial_masks_preserved':str(archive/'partial-masks'),
            'history':str(archive),'authorized_at':time.time(),
            'previous_pid':old.get('pid'),'previous_error':old.get('error')}
    with (root/'sparse-worker.log').open('a') as log:
        log.write('\nAUTHORIZED RECOVERY AT 100 W; OLD ATTEMPT ARCHIVED\n')
        log.flush()
        process=subprocess.Popen(['python3','-B','-u',str(root/'sparse_review_worker.py'),str(root)],
                                 stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                 start_new_session=True)
    record['pid']=process.pid
    previous.write_text(json.dumps(record,indent=2)+'\n')
    print('ADMIN_REPLY='+json.dumps(record))
