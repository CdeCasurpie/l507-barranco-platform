exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import uuid
launch_path=Path('/tmp/opencode/dense-019-launch.json')
launch=json.loads(launch_path.read_text())
launch['unit']='barranco-dense-019-retry-'+uuid.uuid4().hex[:10]
launch_path.write_text(json.dumps(launch,indent=2))
code=f'''
import pathlib,subprocess,json,shlex
assert (pathlib.Path.home()/'L507_004.txt').is_file()
assert {macs['L507_004']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
s=json.loads((root/'reconstruction-full-status.json').read_text())
assert s['state']=='failed' and s['error']=='Operator cancellation'
assert not (root/'job/candidate').exists(),'Inspect completed output before restarting'
print('START_PERSISTENT',str(root),flush=True)
command=['systemd-run','--user','--wait','--pipe','--unit='+{launch['unit']!r},
 '-p','MemoryMax=42G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-p','RuntimeMaxSec=432000','sg','docker','-c',
 shlex.join(['python3','-B',str(root/'pilot_worker.py'),str(root)])]
result=subprocess.run(command)
print('END',result.returncode,flush=True)
raise SystemExit(result.returncode)
'''
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
print('Persistent SSH supervisor started for',launch['unit'],flush=True)
run('ssh',opts+[site['ssh_user']+'@192.0.2.44',shlex.join(['python3','-B','-c',code])])
