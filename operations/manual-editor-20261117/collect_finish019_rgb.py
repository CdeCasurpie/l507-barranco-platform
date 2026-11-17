exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import subprocess,uuid,shutil
launch=json.loads(Path('/tmp/opencode/dense-019-launch.json').read_text())
local=Path(json.loads(Path('/tmp/opencode/019-render-delivery.json').read_text())['directory'])
assert (local/'simplified70/report.json').is_file()
assert shutil.disk_usage(local).free>55*2**30
remote=launch['output']+'/mvs/colored-chunks'
code=f'''
import pathlib,json
assert (pathlib.Path.home()/'L507_004.txt').is_file()
assert {macs['L507_004']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
m=json.loads(pathlib.Path({remote!r},'manifest.json').read_text())
assert m['complete'] and m['geometry_unchanged'] and len(m['meshes'])==26
print('RGB='+json.dumps(m))
'''
manifest=run('ssh',opts+[site['ssh_user']+'@192.0.2.44',shlex.join(['python3','-B','-c',code])],'RGB=')
destination=local/'colored-reference';destination.mkdir()
filelist=local/'colored-files.txt'
filelist.write_text('\n'.join(['manifest.json']+[r['chunk']+'.ply' for r in manifest['meshes']])+'\n')
original_spawn=pexpect.spawn
def patient_spawn(*args,**kwargs):
 kwargs['timeout']=1800
 return original_spawn(*args,**kwargs)
pexpect.spawn=patient_spawn
print('COLLECTING019_RGB',destination,flush=True)
run('rsync',['-a','--partial','--files-from='+str(filelist),'-e',shlex.join(['ssh']+opts),
 site['ssh_user']+'@192.0.2.44:'+remote+'/',str(destination)+'/'])
for row in manifest['meshes']:
 with (destination/(row['chunk']+'.ply')).open('rb') as f:
  assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
print('VERIFIED019_RGB_REFERENCE',flush=True)
subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-finish019-rgb-'+uuid.uuid4().hex[:10],
 '-p','MemoryMax=24G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-E','OPENBLAS_NUM_THREADS=4','-E','OMP_NUM_THREADS=4',
 '/data/barranco/runtime/alignment313/bin/python','-B','/tmp/opencode/finish019_rgb.py',str(local)],check=True)
subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-render019-rgb-'+uuid.uuid4().hex[:10],
 '-p','MemoryMax=24G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 'blender','--background','--factory-startup','--threads','4','--python-exit-code','1',
 '--python','/tmp/opencode/render019_rgb.py','--',str(local)],check=True)
print('019_SIMPLIFIED_RGB_READY',local,flush=True)
