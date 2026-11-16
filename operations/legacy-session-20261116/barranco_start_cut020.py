import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

block=BINDINGS.get('block_id','020')
assert {'019':'L507_004','020':'L507_005'}[block]==NODE_TAG
start,end=BINDINGS.get('interval',[268,280])
assert (block,start,end) in [('019',408,420),('020',268,280)]
scene='cuadra-'+block
campaign='barranco-'+block+'-cut10fps-20261116'
source=Path('/data/photogrammetry/campaigns/barranco-running-20261116')/scene
root=Path('/data/photogrammetry/campaigns')/campaign/scene
assert os.path.ismount('/data') and not root.exists(),'Never overwrite/relaunch an existing cut trial'
s=json.loads((source/'reconstruction-full-status.json').read_text())
assert s['state']=='awaiting_review' and s['stage']=='sparse_review'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
assert float(subprocess.check_output(['nvidia-smi','--query-gpu=power.limit','--format=csv,noheader,nounits'],text=True).strip())==100
assert shutil.disk_usage('/data').free>100*2**30 and shutil.disk_usage('/').free>3.75*2**30
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
    fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
cfg=json.loads((source/'config-full.json').read_text())
assert cfg['frames']['fps']==2 and cfg['frames']['start'] is None
assert cfg['masking']['enabled'] and cfg['masking']['per_source']=={}
a=json.loads((source/'assignment.json').read_text())
assert a['block_id']==block and len(a['files'])==1
a.update(campaign_id=campaign,work_root=str(root),
         operation='sparse_cut_density_diagnostic',variant=f'local10fps-{start}-{end}')
spec=json.loads((source/'reconstruction.json').read_text())
source_out=source/'outputs'/scene/s['experiment']
for name,expected in BINDINGS['baseline_hashes'].items():
    h=hashlib.sha256()
    with (source_out/'colmap/sparse/0'/name).open('rb') as stream:
        for b in iter(lambda:stream.read(4194304),b''):h.update(b)
    assert h.hexdigest()==expected,'Original geometry changed since inspection'
experiment=f'phone_{block}_local10fps_{start}_{end}_sparse_review_v1'
cfg['experiment']={'name':experiment,'notes':f'Diagnostic: 2 fps outside [{start},{end}), 10 fps inside; original untouched; masks reused/generated with same policy; sparse only'}
cfg['paths']={'raw_root':str(root/'datasets/raw'),'output_root':str(root/'outputs')}
clip=json.loads(json.dumps(cfg))
clip['experiment']={'name':'cut_clip_10fps','notes':'Only the selected cut interval, masks preparation'}
clip['paths']['output_root']=str(root/'extra-outputs')
clip['frames'].update(fps=10,start=start,end=end)
files=BINDINGS['files']
spec.update(campaign_id=a['campaign_id'],full_experiment=experiment,source_root=str(source),
            sparse_only=True,dense_authorized=False)
spec['bundle_hashes']={name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
spec['worker_sha256']=spec['bundle_hashes']['reconstruction_worker.py']
spec['post_sha256']=spec['bundle_hashes']['campaign_post.py']
spec['dense_batches_sha256']=spec['bundle_hashes']['dense_batches.py']
item=a['files'][0]
policy={'source_output':str(source_out),'source_root':str(source),
        'block_id':block,'video_stem':Path(item['name']).stem,
        'baseline_frame_count':BINDINGS.get('baseline_frame_count',970),
        'start_seconds':start,'end_seconds':end,'target_image_ids':BINDINGS.get('target_image_ids',[547,548,549,550]),
        'outside_fps':2,'inside_fps':10,'video_relative_path':item['relative_path'],
        'baseline_hashes':BINDINGS['baseline_hashes'],
        'intervention':'Replace 24 baseline samples only in derived run; 120 new samples. Original remains intact.'}
root.mkdir(parents=True)
video=source/item['relative_path'];target=root/item['relative_path']
target.parent.mkdir(parents=True)
os.link(video,target)
os.link(video.with_name(video.name+'.fetch.json'),target.with_name(target.name+'.fetch.json'))
for name,data in [('assignment.json',a),('reconstruction.json',spec),('config-full.json',cfg),
                  ('config-clip.json',clip),('cut-policy.json',policy),
                  ('baseline-cut-inspection.json',BINDINGS['baseline_diagnostics'])]:
    (root/name).write_text(json.dumps(data,indent=2)+'\n')
for name,text in files.items():(root/name).write_text(text)
for directory in ('scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction','outputs','extra-outputs'):
    (root/directory).mkdir(parents=True,exist_ok=True)
with (root/'sparse-worker.log').open('a') as log:
    worker=subprocess.Popen(['python3','-B','-u',str(root/'cut020_worker.py'),str(root)],
                            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                            start_new_session=True)
record={'tag':NODE_TAG,'block':block+' local10fps','root':str(root),'pid':worker.pid,
        'state':'starting','start_seconds':start,'end_seconds':end,'power_limit_w':100,
        'stop_after':'sfm','source_unchanged':True,'authorized_at':time.time()}
(root/'sparse-launch.json').write_text(json.dumps(record,indent=2)+'\n')
print('ADMIN_REPLY='+json.dumps(record))
