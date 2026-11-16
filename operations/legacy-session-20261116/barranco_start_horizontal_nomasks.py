import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

assert NODE_TAG=='L507_010'
source=Path('/data/photogrammetry/campaigns/barranco-006-horizontal-20261115/cuadra-006')
root=Path('/data/photogrammetry/campaigns/barranco-006-horizontal-nomasks-20261116/cuadra-006')
assert os.path.ismount('/data') and not root.exists(),'Do not overwrite/relaunch an existing diagnostic'
original=json.loads((source/'reconstruction-full-status.json').read_text())
assert original['state']=='failed' and original['completed_stages']==['frames']
assert original['stage']=='masks'
assert shutil.disk_usage('/').free>3.75*2**30 and shutil.disk_usage('/data').free>100*2**30
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
    fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
a=json.loads((source/'assignment.json').read_text())
assert len(a['files'])==1 and a['files'][0]['name']=='manzana_06.mp4'
a.update(campaign_id='barranco-006-horizontal-nomasks-20261116',work_root=str(root),
         variant='horizontal-no-masks',operation='reconstruction_sparse_only')
cfg=json.loads((source/'config-full.json').read_text())
assert cfg['masking']['per_source']=={}
cfg['masking']['enabled']=False
experiment='phone_native_2fps_horizontal_sequential_nomasks_review_v1'
cfg['experiment']={'name':experiment,'notes':'Explicit diagnostic: same original sequential settings; masks disabled; reused frames; sparse only'}
cfg['paths']={'raw_root':str(root/'datasets/raw'),'output_root':str(root/'outputs')}
for key in ('mesh','refine','clean','texture'):
    cfg['openmvs'][key]['enabled']=False
spec=json.loads((source/'reconstruction.json').read_text())
spec.update(campaign_id=a['campaign_id'],full_experiment=experiment,sparse_only=True,masking_enabled=False)
files=BINDINGS['files']
spec['bundle_hashes']={name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
spec['worker_sha256']=spec['bundle_hashes']['reconstruction_worker.py']
spec['post_sha256']=spec['bundle_hashes']['campaign_post.py']
spec['dense_batches_sha256']=spec['bundle_hashes']['dense_batches.py']
source_frames=source/'outputs/cuadra-006'/original['experiment']/'frames'
root.mkdir(parents=True)
target_frames=root/'outputs/cuadra-006'/experiment/'frames'
target_frames.mkdir(parents=True)
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4194304),b''):h.update(block)
    return h.hexdigest()
frames=[]
for path in sorted(source_frames.rglob('*')):
    assert not path.is_symlink(),'Unexpected symlink in source frames'
    relative=path.relative_to(source_frames)
    target=target_frames/relative
    if path.is_dir():
        target.mkdir(exist_ok=True)
    elif path.is_file():
        target.parent.mkdir(parents=True,exist_ok=True)
        os.link(path,target)
        if path.suffix.lower() in ('.jpg','.jpeg','.png'):
            frames.append({'path':str(relative),'bytes':path.stat().st_size,'sha256':sha(path)})
assert len(frames)==1665
item=a['files'][0]
video=source/item['relative_path']
target=root/item['relative_path']
target.parent.mkdir(parents=True)
os.link(video,target)
os.link(video.with_name(video.name+'.fetch.json'),target.with_name(target.name+'.fetch.json'))
for name,value in [('assignment.json',a),('config-full.json',cfg),('reconstruction.json',spec),
                   ('frames-lineage.json',{'source_root':str(source),'frame_count':len(frames),'frames':frames,'originals_modified':False})]:
    (root/name).write_text(json.dumps(value,indent=2)+'\n')
for name,text in files.items():
    (root/name).write_text(text)
for suffix in ('scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction'):
    (root/suffix).mkdir(parents=True,exist_ok=True)
with (root/'sparse-worker.log').open('a') as log:
    p=subprocess.Popen(['python3','-B','-u',str(root/'sparse_nomasks_worker.py'),str(root)],
                       stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
reply={'tag':NODE_TAG,'block':'006 horizontal sin máscaras','state':'starting','pid':p.pid,
       'root':str(root),'frames_reused':len(frames),'masking_enabled':False,
       'matcher':cfg['colmap']['matcher'],'stop_after':'sfm','authorized_at':time.time(),
       'power_changed':False}
(root/'sparse-launch.json').write_text(json.dumps(reply,indent=2)+'\n')
print('ADMIN_REPLY='+json.dumps(reply))
