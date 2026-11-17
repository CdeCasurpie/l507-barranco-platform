exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import base64,zlib,uuid
launch=json.loads(Path('/tmp/opencode/dense-019-launch.json').read_text())
worker=Path('/tmp/opencode/refine019_trial_worker.py').read_text()
unit='barranco-refine019-trial-'+uuid.uuid4().hex[:8]
code=f'''
import pathlib,subprocess,json,shlex
assert (pathlib.Path.home()/'L507_004.txt').is_file()
assert {macs['L507_004']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
assert json.loads((root/'reconstruction-full-status.json').read_text())['state']=='completed'
assert not (root/'refine-trial').exists()
tool=root/'refine_trial_worker.py';assert not tool.exists();tool.write_text({worker!r})
(root/'refine-trial-launch.json').write_text(json.dumps(dict(unit={unit!r},mesh_only=True,ba=False,originals_preserved=True)))
p=subprocess.run(['systemd-run','--user','--wait','--pipe','--unit='+{unit!r},
 '-p','MemoryMax=42G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-p','RuntimeMaxSec=18000','sg','docker','-c',shlex.join(['python3','-B',str(tool),str(root)])])
raise SystemExit(p.returncode)
'''
encoded=base64.b64encode(zlib.compress(code.encode())).decode()
bootstrap="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
print('REFINE019_TRIAL_START',unit,flush=True)
run('ssh',opts+[site['ssh_user']+'@192.0.2.44',shlex.join(['python3','-B','-c',bootstrap])])
