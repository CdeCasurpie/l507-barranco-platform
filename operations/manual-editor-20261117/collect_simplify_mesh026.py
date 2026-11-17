"""Run after the remote mesh-only job completes; preserve all remote inputs."""
exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import subprocess,uuid
launch=json.loads(Path('/tmp/opencode/mesh026-existing-launch.json').read_text())
remote=launch['root']+'/mesh-existing'
code=f'''
import pathlib,json
assert (pathlib.Path.home()/'L507_019.txt').is_file()
assert {macs['L507_019']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
manifest=json.loads(pathlib.Path({remote!r},'manifest.json').read_text())
assert manifest['complete'] and len(manifest['meshes'])==40
print('MANIFEST='+json.dumps(manifest))
'''
manifest=run('ssh',opts+[site['ssh_user']+'@192.0.2.63',shlex.join(['python3','-B','-c',code])],'MANIFEST=')
destination=Path('/data/barranco/review')/('026-mesh70-'+uuid.uuid4().hex)
destination.mkdir()
raw=destination/'raw';raw.mkdir()
files=destination/'remote-files.txt'
files.write_text('\n'.join(['manifest.json']+[m['chunk']+'/mesh.ply' for m in manifest['meshes']])+'\n')
original_spawn=pexpect.spawn
def patient_spawn(*args,**kwargs):
 kwargs['timeout']=1800
 return original_spawn(*args,**kwargs)
pexpect.spawn=patient_spawn
run('rsync',['-a','--partial','--files-from='+str(files),'-e',shlex.join(['ssh']+opts),
 site['ssh_user']+'@192.0.2.63:'+remote+'/',str(raw)+'/'])
for mesh in manifest['meshes']:
 p=raw/mesh['chunk']/'mesh.ply'
 assert p.stat().st_size==mesh['bytes']
 with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==mesh['sha256']
(destination/'source-receipt.json').write_text(json.dumps(manifest,indent=2))
print('COLLECTED',destination,flush=True)
subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-simplify026-'+uuid.uuid4().hex[:10],
 '-p','MemoryMax=32G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-E','OPENBLAS_NUM_THREADS=4','-E','OMP_NUM_THREADS=4',
 '/data/barranco/runtime/alignment313/bin/python','-B',
 '/tmp/opencode/simplify_mesh026.py',str(destination)],check=True)
print('SIMPLIFIED_READY',destination,flush=True)
