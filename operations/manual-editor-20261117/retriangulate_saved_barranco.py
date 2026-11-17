"""User-authorized saved revisions only, sequential fixed-pose triangulation."""
exec(open('/tmp/opencode/collect_cut020_review.py').read().split('code="import pathlib,json')[0])
import subprocess,shutil,uuid
sys.path.insert(0,'/home/exitoso/home/sparse-review')
import graph_edit

labels=['015','010','014','016-023','019','020','022']
base=Path('/data/barranco/review/catalog-20261116-134343')
state=Path('/data/barranco/manual-graph-editor')
batch=state/('batch-'+uuid.uuid4().hex)
batch.mkdir()
drafts=[]
for label in labels:
 candidates=[json.loads(p.read_text()) for p in state.glob('g-*.json')]
 candidates=[d for d in candidates if '/'+label+'/colmap/sparse/' in d['source_model']]
 assert candidates,'No saved revision: '+label
 draft=max(candidates,key=lambda d:d['created_at'])
 drafts.append(dict(label=label,draft=draft))
(batch/'plan.json').write_text(json.dumps(dict(items=drafts,mode='triangulation_only',
    alignment='manual_only',preserved=['021','026','027']),indent=2))
print('BATCH',str(batch),flush=True)
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
macs=json.loads(Path('/home/exitoso/.lab_wake_macs.json').read_text())
opts=['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o',
 'UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts /home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115/known_hosts']
def digest(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
original_spawn=pexpect.spawn
def patient_spawn(*args,**kwargs):
 kwargs['timeout']=1800
 return original_spawn(*args,**kwargs)
pexpect.spawn=patient_spawn
for item in drafts:
 label=item['label'];draft=item['draft'];model=Path(draft['source_model'])
 database=model.parents[1]/'database.db'
 receipt=database.parent/'editor-database-receipt.json'
 if not receipt.exists():
  provenance=json.loads((base/label/'collection.json').read_text())
  tag=provenance['tag'];ip=cache[tag]['ip']
  code=f'''
import pathlib,sqlite3,json,hashlib,uuid
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({provenance['root']!r})/'colmap'
target=root/('editor-triangulation-snapshot-'+uuid.uuid4().hex+'.db')
with sqlite3.connect((root/'database.db').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:
 src.execute('PRAGMA query_only=ON');src.backup(dst)
with target.open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
print('SNAP='+json.dumps(dict(path=str(target),sha256=h,bytes=target.stat().st_size)))
'''
  snap=run('ssh',opts+[site['ssh_user']+'@'+ip,shlex.join(['python3','-B','-c',code])],'SNAP=')
  staging=database.with_name('database.batch-transfer.db')
  run('rsync',['-a','--partial','--append-verify','-e',shlex.join(['ssh']+opts),
   site['ssh_user']+'@'+ip+':'+snap['path'],str(staging)])
  assert digest(staging)==snap['sha256']
  if database.exists():database.rename(database.with_name('database.preserved-'+uuid.uuid4().hex+'.db'))
  staging.rename(database);receipt.write_text(json.dumps(snap,indent=2))
 assert digest(database)==json.loads(receipt.read_text())['sha256']
 assert graph_edit.fingerprint(model)==draft['source_hashes']
 for status in (state/'jobs').glob('*/status.json'):
  assert json.loads(status.read_text()).get('state') not in ('starting','running'),'Another editor job is active'
 memory=dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
 assert int(memory['MemAvailable'].split()[0])/1024**2>=44
 assert shutil.disk_usage(state).free>=50*2**30
 solve_code="""import json,sys
from pathlib import Path
sys.path.insert(0,'/home/exitoso/home/sparse-review')
import graph_edit
draft=json.load(sys.stdin)
model=Path(draft['source_model'])
result=graph_edit.solve(model,draft)
meta,_=graph_edit.get_graph(model)
print(json.dumps(dict(result=result,camera_ids=[c['id'] for c in meta['cameras']])))
"""
 solved=json.loads(subprocess.check_output(
  ['/data/barranco/runtime/alignment311/bin/python','-B','-c',solve_code],
  input=json.dumps(draft),text=True))
 result=solved['result']
 identity='j-'+uuid.uuid4().hex;job=state/'jobs'/identity;job.mkdir()
 spec=dict(draft=draft,camera_ids=solved['camera_ids'],
  displacements=result['displacements'],rotations=result['rotations'],
  database_path=str(database),mode='triangulation_only')
 (job/'request.json').write_text(json.dumps(spec))
 for name in ['graph_job.py','graph_edit.py','app.py']:
  shutil.copy2(Path('/home/exitoso/home/sparse-review')/name,job/name)
 (job/'status.json').write_text(json.dumps(dict(state='starting',batch=str(batch),label=label,
  geometry_approved=False,dense_authorized=False)))
 (batch/(label+'.json')).write_text(json.dumps(dict(job=identity,draft_id=draft['id'])))
 print('START',label,identity,'DRAFT',draft['id'],flush=True)
 execution=subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-manual-'+identity,
  '-p','MemoryMax=40G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','RuntimeMaxSec=3600','-p','Nice=10',
  '-E','OMP_NUM_THREADS=4','-E','OPENBLAS_NUM_THREADS=4',
  '/data/barranco/runtime/alignment311/bin/python','-B',str(job/'graph_job.py'),str(job)])
 status=json.loads((job/'status.json').read_text())
 print('FINISH',label,status['state'],flush=True)
 if execution.returncode or status['state']=='failed':raise RuntimeError('Batch stopped: '+label)
print('BATCH_COMPLETE',str(batch),flush=True)
