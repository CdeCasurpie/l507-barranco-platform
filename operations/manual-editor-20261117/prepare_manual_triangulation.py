"""Prepare verified DB snapshots and restart only authorized 006/011 requests."""
exec(open('/tmp/opencode/collect_cut020_review.py').read().split('code="import pathlib,json')[0])
import shutil,subprocess,uuid
jobs=Path('/data/barranco/manual-graph-editor/jobs')
for label,tag,ip in [('006-horiz-s-m','L507_010','192.0.2.100'),('010','L507_007','192.0.2.71'),('011','L507_015','192.0.2.61'),('015','L507_009','192.0.2.78')]:
 dest=Path('/data/barranco/review/catalog-20261116-134343')/label
 receipt=json.loads((dest/'collection.json').read_text())
 remote=receipt['root']
 opts=['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o','UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts /home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115/known_hosts']
 snapshot=remote+'/colmap/editor-triangulation-snapshot-'+uuid.uuid4().hex+'.db'
 code=f'''
import pathlib,sqlite3,json,hashlib
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
source=pathlib.Path({remote!r})/'colmap/database.db'
target=pathlib.Path({snapshot!r})
with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:
 src.execute('PRAGMA query_only=ON');src.backup(dst)
h=hashlib.sha256(target.read_bytes()).hexdigest()
print('SNAP='+json.dumps({{'sha256':h}}))
'''
 snap=run('ssh',opts+[site['ssh_user']+'@'+ip,shlex.join(['python3','-B','-c',code])],'SNAP=')
 target=dest/'colmap/database.db'
 assert not target.exists(),'Do not overwrite a DB'
 run('rsync',['-a','--partial','-e',shlex.join(['ssh']+opts),site['ssh_user']+'@'+ip+':'+snapshot,str(target)])
 assert hashlib.sha256(target.read_bytes()).hexdigest()==snap['sha256']
 print('READY',label,flush=True)
for old_id in ['j-f096e7864c154c42bfd03aa8b86a04af','j-405fbafc38434287acd70feb88953499']:
 old=jobs/old_id;spec=json.loads((old/'request.json').read_text())
 model=Path(spec['draft']['source_model'])
 spec['database_path']=str(model.parents[1]/'database.db');spec['mode']='triangulation_only'
 identity='j-'+uuid.uuid4().hex;job=jobs/identity;job.mkdir()
 (job/'request.json').write_text(json.dumps(spec))
 for name in ['graph_job.py','graph_edit.py','app.py']:shutil.copy2(Path('/home/exitoso/home/sparse-review')/name,job/name)
 (job/'status.json').write_text(json.dumps({'state':'starting','retry_of':old_id,'mode':'triangulation_only'}))
 print('START',identity,flush=True)
 subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-manual-'+identity,
 '-p','MemoryMax=40G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','RuntimeMaxSec=3600',
 '-E','OMP_NUM_THREADS=4','-E','OPENBLAS_NUM_THREADS=4',
 '/data/barranco/runtime/alignment311/bin/python','-B',str(job/'graph_job.py'),str(job)],check=True)
 print((job/'status.json').read_text(),flush=True)
