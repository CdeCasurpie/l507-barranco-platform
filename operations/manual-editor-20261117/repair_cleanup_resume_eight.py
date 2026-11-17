exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
from concurrent.futures import ThreadPoolExecutor,as_completed
import base64,zlib,uuid
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
labels=['006-horiz-s-m','010','011','014','015','020','021','027']
helper=Path('/tmp/opencode/dense_cleanup_verified.py').read_text()
def repair(label):
 launch=json.loads(Path('/tmp/opencode/dense-'+label+'-launch.json').read_text())
 provenance=json.loads((Path('/data/barranco/review/catalog-20261116-134343')/label/'collection.json').read_text())
 tag=provenance['tag'];options=list(opts)
 if tag=='L507_005':options+=['-o','HostKeyAlias=192.0.2.58']
 unit='barranco-dense-resume-fix-'+label+'-'+uuid.uuid4().hex[:8]
 code=f'''
import pathlib,json,subprocess,shlex
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
s=json.loads((root/'reconstruction-full-status.json').read_text())
assert s['state']=='failed' and s['stage']=='dense',s
log=root/'logs/reconstruction/full/dense.log'
assert 'cleanup_verified_chunk' in log.read_text()[-4000:]
assert json.loads((root/'cleanup-authorization.json').read_text())['block']!='026'
path=root/'dense_cleanup.py'
old=path.read_text()
assert "json.loads(receipt.read_text())==done" in old
backup=path.with_name('dense_cleanup.before-json-schema-fix.py')
assert not backup.exists()
backup.write_text(old)
temp=path.with_suffix('.new');temp.write_text({helper!r});temp.replace(path)
(root/'cleanup-resume-fix.json').write_text(json.dumps(dict(unit={unit!r},reason='Normalize JSON tuple/list representation; geometry validation remains enabled')))
command=['systemd-run','--user','--wait','--pipe','--unit='+{unit!r},
 '-p','MemoryMax=42G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-p','RuntimeMaxSec=432000','sg','docker','-c',
 shlex.join(['python3','-B',str(root/'resume_after_cleanup.py'),str(root)])]
result=subprocess.run(command)
raise SystemExit(result.returncode)
'''
 encoded=base64.b64encode(zlib.compress(code.encode())).decode()
 command="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
 print('REPAIR_RESUME',label,unit,flush=True)
 run('ssh',options+[site['ssh_user']+'@'+cache[tag]['ip'],shlex.join(['python3','-B','-c',command])])
 return dict(label=label,completed=True)
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
with ThreadPoolExecutor(max_workers=8) as pool:
 futures={pool.submit(repair,label):label for label in labels}
 for future in as_completed(futures):
  try:print(json.dumps(future.result()),flush=True)
  except Exception as error:print(json.dumps(dict(label=futures[future],error=str(error))),flush=True)
