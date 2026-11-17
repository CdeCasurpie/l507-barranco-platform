"""Resume authorized snapshot transfers, preserving differing local databases."""
exec(open('/tmp/opencode/collect_cut020_review.py').read().split('code="import pathlib,json')[0])
import subprocess,shutil,uuid
base=Path('/data/barranco/review/catalog-20261116-134343')
macs=json.loads(Path('/home/exitoso/.lab_wake_macs.json').read_text())
for label,tag,ip in [('006-horiz-s-m','L507_010','192.0.2.100'),('011','L507_015','192.0.2.61'),('010','L507_007','192.0.2.71'),('015','L507_009','192.0.2.78')]:
 dest=base/label
 remote=json.loads((dest/'collection.json').read_text())['root']
 opts=['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o','UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts /home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115/known_hosts']
 code=f'''
import pathlib,sqlite3,json,hashlib,uuid
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({remote!r})/'colmap'
existing=sorted(root.glob('editor-triangulation-snapshot-*.db'),key=lambda p:p.stat().st_mtime)
target=existing[-1] if existing else root/('editor-triangulation-snapshot-'+uuid.uuid4().hex+'.db')
if not existing:
 with sqlite3.connect((root/'database.db').as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(target) as dst:
  src.execute('PRAGMA query_only=ON');src.backup(dst)
h=hashlib.file_digest(target.open('rb'),'sha256').hexdigest()
print('SNAP='+json.dumps(dict(path=str(target),sha256=h,bytes=target.stat().st_size)))
'''
 snap=run('ssh',opts+[site['ssh_user']+'@'+ip,shlex.join(['python3','-B','-c',code])],'SNAP=')
 target=dest/'colmap/database.db'
 def digest(p):
  with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
 if not target.exists() or digest(target)!=snap['sha256']:
  staging=target.with_name('database.verified-transfer.db')
  # Long transfers have an explicit larger timeout; interrupted files remain resumable.
  original_spawn=pexpect.spawn
  def patient_spawn(*args,**kwargs):
   kwargs['timeout']=1800
   return original_spawn(*args,**kwargs)
  pexpect.spawn=patient_spawn
  run('rsync',['-a','--partial','--append-verify','-e',shlex.join(['ssh']+opts),site['ssh_user']+'@'+ip+':'+snap['path'],str(staging)])
  pexpect.spawn=original_spawn
  assert digest(staging)==snap['sha256']
  if target.exists():target.rename(target.with_name('database.pre-verification-'+uuid.uuid4().hex+'.db'))
  staging.rename(target)
 (dest/'colmap/editor-database-receipt.json').write_text(json.dumps(snap,indent=2))
 print('VERIFIED',label,flush=True)
print('DATABASE_PREPARATION_COMPLETE',flush=True)
