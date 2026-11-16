import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

assert NODE_TAG=='L507_005'
root=Path('/data/photogrammetry/campaigns/barranco-020-cut10fps-20261116/cuadra-020')
def capture(args):
    return subprocess.check_output(args,text=True,timeout=30).strip()
assert float(capture(['nvidia-smi','--query-gpu=power.limit','--format=csv,noheader,nounits']))==100
assert not capture(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'])
assert BINDINGS['authorized'] is True
with (root/'recovery-bootstrap.lock').open('a') as bootstrap:
    fcntl.flock(bootstrap,fcntl.LOCK_EX|fcntl.LOCK_NB)
    status=root/'reconstruction-full-status.json'
    old=json.loads(status.read_text())
    proc=Path('/proc/'+str(old.get('pid'))+'/cmdline')
    assert not (proc.exists() and str(root).encode() in proc.read_bytes())
    assert old['state']=='failed' and old['stage']=='merge_frames'
    assert old['completed_stages']==['timing_check','extra_frames','extra_masks']
    assert not (root/'recovery-exdev.json').exists(),'Repair already attempted; inspect first'
    token=hashlib.sha256((str(root)+'full').encode()).hexdigest()[:12]
    assert not capture(['docker','ps','-q','--filter','label=photogrammetry.run='+token])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert shutil.disk_usage('/data').free>100*2**30
    spec_path=root/'reconstruction.json'
    spec=json.loads(spec_path.read_text())
    step=root/'cut020_steps.py'
    before=hashlib.sha256(step.read_bytes()).hexdigest()
    assert before==BINDINGS['expected_old_sha256']==spec['bundle_hashes']['cut020_steps.py']
    out=root/'outputs/cuadra-020'/spec['full_experiment']
    assert not (out/'colmap/database.db').exists(),'Never overwrite an existing SfM database'
    archive=root/'attempt-history'/(str(time.time_ns())+'-before-exdev-fix')
    archive.mkdir(parents=True)
    for name in ('reconstruction-full-status.json','reconstruction.json','cut020_steps.py','sparse-worker.log'):
        shutil.copy2(root/name,archive/name)
    shutil.copytree(root/'logs/reconstruction/full',archive/'worker-stage-logs')
    text=BINDINGS['new_step_source']
    compile(text,'cut020_steps.py','exec')
    after=hashlib.sha256(text.encode()).hexdigest()
    step.write_text(text)
    spec['bundle_hashes']['cut020_steps.py']=after
    spec['execution_amendment']={'reason':'Verified EXDEV copy fallback; no scientific parameter changes',
                                 'previous_step_sha256':before,'new_step_sha256':after}
    spec_path.write_text(json.dumps(spec,indent=2)+'\n')
    with (root/'sparse-worker.log').open('a') as log:
        log.write('\nAUTHORIZED EXDEV FIX: RESUME MERGE ONLY; FRAMES AND MASKS REUSED\n')
        log.flush()
        worker=subprocess.Popen(['python3','-B','-u',str(root/'cut020_worker.py'),str(root)],
                                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                start_new_session=True)
    record={'tag':NODE_TAG,'block':'020 cut10fps','pid':worker.pid,
            'action':'resumed_from_merge_frames','completed_stages_reused':old['completed_stages'],
            'before_step_sha256':before,'after_step_sha256':after,'history':str(archive),
            'power_limit_w':100,'thermal_guard_modified':False,'authorized_at':time.time()}
    (root/'recovery-exdev.json').write_text(json.dumps(record,indent=2)+'\n')
    print('ADMIN_REPLY='+json.dumps(record))
