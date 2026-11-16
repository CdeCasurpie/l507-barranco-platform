import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

a=next(a for a in BINDINGS['assignments'] if a['node_tag']==NODE_TAG)
assert len(a['files'])==1
assert a['block_id']!='016-023' or BINDINGS.get('allow_combined_terrestrial') is True
assert os.path.ismount('/data')
root=Path(a['work_root'])
assert json.loads((root/'assignment.json').read_text())==a
download=json.loads((root/'status.json').read_text())
assert download['state']=='downloaded','Wait for verified download'
assert download['completed_files']==1
assert shutil.disk_usage('/').free > 3.75*2**30
assert shutil.disk_usage('/data').free > 100*2**30
active=json.loads(Path('/var/lib/lab-deploy/active.json').read_text())
with (root/'sparse-bootstrap.lock').open('a') as bootstrap:
    fcntl.flock(bootstrap,fcntl.LOCK_EX|fcntl.LOCK_NB)
    status=root/'reconstruction-full-status.json'
    launch=root/'sparse-launch.json'
    if status.exists() or launch.exists():
        existing=json.loads((status if status.exists() else launch).read_text())
        print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'existing':existing,'not_relaunched':True}))
        raise SystemExit(0)
    jobs=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
    assert not jobs,'Another GPU computation is active'
    assert subprocess.run(['docker','info'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    spec=dict(BINDINGS['spec'])
    spec.update(campaign_id=a['campaign_id'],node_tag=NODE_TAG,block_id=a['block_id'],
                code_root=active['code_root'],certified_data_root=active['data_root'],
                full_experiment='phone_native_2fps_seq20_loop_sparse_review_v1',
                sparse_only=True,dense_authorized=False)
    spec['resource_limits']=dict(spec['resource_limits'],cpus=4)
    spec['resource_limits'].pop('cpuset_cpus',None)
    spec['bundle_hashes']={name:hashlib.sha256(text.encode()).hexdigest() for name,text in BINDINGS['files'].items()}
    spec['worker_sha256']=spec['bundle_hashes']['reconstruction_worker.py']
    spec['post_sha256']=spec['bundle_hashes']['campaign_post.py']
    spec['dense_batches_sha256']=spec['bundle_hashes']['dense_batches.py']
    cfg=json.loads(json.dumps(BINDINGS['config']))
    cfg['experiment']={'name':spec['full_experiment'],'notes':'Authorized single-video sparse only; seq20 linear + verified start/end candidates; stop for review'}
    cfg['paths']={'raw_root':str(root/'datasets/raw'),'output_root':str(root/'outputs')}
    for name,obj in [('config-full.json',cfg),('reconstruction.json',spec)]:
        path=root/name
        assert not path.exists(),'Never overwrite an existing experiment configuration'
        path.write_text(json.dumps(obj,indent=2)+'\n')
    for name,text in BINDINGS['files'].items():
        path=root/name
        assert not path.exists()
        path.write_text(text)
    for suffix in ('scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction','outputs'):
        (root/suffix).mkdir(parents=True,exist_ok=True)
    with (root/'sparse-worker.log').open('a') as log:
        process=subprocess.Popen(['python3','-B','-u',str(root/'sparse_review_worker.py'),str(root)],
                                 stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                 start_new_session=True)
    receipt={'tag':NODE_TAG,'block':a['block_id'],'state':'starting','pid':process.pid,
             'experiment':spec['full_experiment'],'stop_after':'sfm','authorized_at':time.time(),
             'config_sha256':hashlib.sha256((root/'config-full.json').read_bytes()).hexdigest()}
    launch.write_text(json.dumps(receipt,indent=2)+'\n')
    print('ADMIN_REPLY='+json.dumps(receipt))
