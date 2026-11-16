"""Derived job with validated merged SfM; reuse only unchanged raw/frames/masks."""
import base64
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from drive_download_campaign import remote
sys.path.insert(0,str(PROJECT))
from labdeploy.store import atomic_json

central=Path('/data/barranco/campaigns/barranco-full-v1')
site=json.loads((PROJECT/'config/site.json').read_text())
original=next(a for a in json.loads((central/'assignments.json').read_text())['assignments'] if a['block_id']=='007')
assignment=dict(original,work_root=original['work_root']+'-recovery',full_experiment='barranco_4k_2fps_007_recovered_v2',recovery_of=original['work_root'])
validation=json.loads(Path('/data/barranco/recovery007/result.json').read_text())
if not validation['passed'] or validation['registered_union']!=310:raise RuntimeError('Recovery not validated')
model=Path(validation['derived_model'])
hashes={name:hashlib.sha256((model/name).read_bytes()).hexdigest() for name in ['cameras.bin','images.bin','points3D.bin']}
payload={'assignment':assignment,'validation':validation,'model_sha256':hashes,
         'files':{name:(PROJECT/'tools'/name).read_text() for name in ['reconstruction_worker.py','campaign_post.py','dense_batches.py']}}
encoded=base64.b64encode(json.dumps(payload).encode()).decode()
code=f'''
import base64,copy,json,hashlib,os,shutil,sqlite3,struct
from pathlib import Path
p=json.loads(base64.b64decode({encoded!r}));a=p['assignment'];root=Path(a['work_root']);old=Path(a['recovery_of']);experiment=a['full_experiment']
if not os.path.ismount('/data') or not (Path.home()/(a['node_tag']+'.txt')).is_file():raise RuntimeError('Node/mount mismatch')
if a['mac'] not in [x.read_text().strip().lower() for x in Path('/sys/class/net').glob('*/address')]:raise RuntimeError('MAC mismatch')
if set(x.name for x in root.iterdir())-{{'incoming-model'}}:raise RuntimeError('Fresh recovery root required')
for name,expected in p['model_sha256'].items():
 if hashlib.sha256((root/'incoming-model'/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Seed hash mismatch')
out=root/'outputs/cuadra-007'/experiment;out.mkdir(parents=True)
source=old/'outputs/cuadra-007/barranco_4k_2fps_combined_v1'
for name in ['datasets','reference']:shutil.copytree(old/name,root/name,copy_function=os.link,symlinks=True)
for name in ['frames','masks','telemetry']:shutil.copytree(source/name,out/name,copy_function=os.link,symlinks=True)
(out/'metrics').mkdir()
for name in ['videos_info.json','masks_info.json']:shutil.copy2(source/'metrics'/name,out/'metrics'/name)
target=out/'colmap/sparse/0';target.mkdir(parents=True)
for name in p['model_sha256']:shutil.copy2(root/'incoming-model'/name,target/name)
(out/'colmap/best_model.txt').write_text('0')
src=sqlite3.connect((source/'colmap/database.snapshot.db').as_uri()+'?mode=ro&immutable=1',uri=True)
dst=sqlite3.connect(out/'colmap/database.db');src.backup(dst);src.close()
with (target/'cameras.bin').open('rb') as f:
 count=struct.unpack('<Q',f.read(8))[0]
 for _ in range(count):
  cid,kind,w,h=struct.unpack('<iiQQ',f.read(24))
  if kind!=2:raise RuntimeError('Recovery expects SIMPLE_RADIAL')
  params=f.read(32)
  dst.execute('INSERT OR REPLACE INTO cameras(camera_id,model,width,height,params,prior_focal_length) VALUES(?,?,?,?,?,1)',(cid,kind,w,h,params))
with (target/'images.bin').open('rb') as f:
 count=struct.unpack('<Q',f.read(8))[0]
 for _ in range(count):
  row=struct.unpack('<i7di',f.read(64));name=bytearray()
  while True:
   b=f.read(1)
   if b==b'\\0':break
   if not b:raise RuntimeError('Truncated image name')
   name.extend(b)
  n=struct.unpack('<Q',f.read(8))[0];f.seek(n*24,1)
  found=dst.execute('SELECT name FROM images WHERE image_id=?',(row[0],)).fetchone()
  if found!=(name.decode(),):raise RuntimeError('Image/DB name mismatch')
  if dst.execute('SELECT rows FROM keypoints WHERE image_id=?',(row[0],)).fetchone()!=(n,):raise RuntimeError('Feature indexing mismatch')
  dst.execute('UPDATE images SET camera_id=? WHERE image_id=?',(row[8],row[0]))
dst.commit();dst.execute('PRAGMA journal_mode=DELETE');dst.close()
cfg=json.loads((old/'config-full.json').read_text());cfg['experiment']={{'name':experiment,'notes':'Validated 20-view component overlap merge and explicit BA; original frames/masks reused; dense regenerated'}}
cfg['paths']={{'raw_root':str(root/'datasets/raw'),'output_root':str(root/'outputs')}}
(root/'config-full.json').write_text(json.dumps(cfg,indent=2)+'\\n')
spec=json.loads((old/'reconstruction.json').read_text());spec.update(full_experiment=experiment,recovery={{'kind':'validated-component-merge','source_root':str(old),'validation':'recovery.json'}})
spec['resource_limits'].update(cpus=3,cpuset_cpus='8,9,10')
for name,body in p['files'].items():(root/name).write_text(body)
for key,name in [('worker_sha256','reconstruction_worker.py'),('post_sha256','campaign_post.py'),('dense_batches_sha256','dense_batches.py')]:spec[key]=hashlib.sha256(p['files'][name].encode()).hexdigest()
(root/'reconstruction.json').write_text(json.dumps(spec,indent=2)+'\\n');(root/'assignment.json').write_text(json.dumps(a,indent=2)+'\\n')
(root/'status.json').write_text((old/'status.json').read_text());(root/'NODE_TAG.txt').write_text(a['node_tag']+'\\n')
(root/'recovery.json').write_text(json.dumps({{'validation':p['validation'],'model_sha256':p['model_sha256'],'source_root':str(old)}},indent=2)+'\\n')
for name in ['scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction']:(root/name).mkdir(parents=True,exist_ok=True)
print('DOWNLOAD_REPLY='+json.dumps({{'state':'prepared','root':str(root),'experiment':experiment,'registered_seed':count}}))
'''
print(remote(site,assignment['ip'],code,timeout=180))
path=central/'execution-overrides.json';overrides=json.loads(path.read_text()) if path.exists() else {}
overrides['007']=assignment;atomic_json(path,overrides)
