"""Finish 026 from preserved dense-based meshes; no cleanup or densification."""
exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import base64,zlib,subprocess,uuid,time
launch=json.loads(Path('/tmp/opencode/mesh026-existing-launch.json').read_text())
state=Path('/home/exitoso/home/barranco-roi/state/alignment')
records={p.stem:json.loads(p.read_text()) for p in (state/'reconstructions').glob('*.json')}
placements=[json.loads(p.read_text()) for p in (state/'placements').glob('*.json')]
placements=[p for p in placements if records[p['reconstruction']]['block']=='026']
assert placements,'026 requires existing user placement'
placement=max(placements,key=lambda p:p['created_at'])
dest=Path('/data/barranco/review')/('026-rgb-delivery-'+uuid.uuid4().hex)
dest.mkdir()
(dest/'placement-snapshot.json').write_text(json.dumps(placement,indent=2))
color=Path('/tmp/opencode/color019_dense_vertices.py').read_text()
color=color.replace('total=26','total=len(manifest["meshes"])')
color=color.replace("cloud=chunk/'scene_dense_scalar.ply'",
 """original=Path(json.loads((root.parent/'mesh-existing.json').read_text())['source_mvs'])/'chunks'/chunk.name
    cloud=original/'scene_dense_scalar.ply'""")
color=color.replace("receipt=json.loads((chunk/'batch-receipt.json').read_text())",
                    "receipt=json.loads((original/'batch-receipt.json').read_text())")
compile(color,'026-color','exec')
code=f'''
import pathlib,json,sys,fcntl
assert (pathlib.Path.home()/'L507_019.txt').is_file()
assert {macs['L507_019']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r});mesh=root/'mesh-existing'
m=json.loads((mesh/'manifest.json').read_text());assert m['complete'] and len(m['meshes'])==40
assert not (mesh/'colored-chunks').exists(),'Refuse duplicate/partial color job'
tool=root/'color026_existing.py';assert not tool.exists()
tool.write_text({color!r})
(mesh/'mesh-chunks.json').write_text(json.dumps(dict(complete=True,meshes=[r['path'] for r in m['meshes']])))
sys.path.insert(0,str(root))
from phone_worker import PhoneWorker
source=pathlib.Path(json.loads((root/'pilot.json').read_text())['source_root'])
class Color(PhoneWorker):
 def docker_args(self,stage,role,argv,gpu=True):
  name,token,args=super().docker_args(stage,role,argv,gpu)
  i=args.index(self.spec['images'][role]['tag'])
  args[i:i]=['--mount',f'type=bind,src={{source}},dst={{source}},readonly',
              '-e',f'PYTHONPATH={{root}}/python-deps']
  return name,token,args
with pathlib.Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 w=Color(root,'package026-rgb')
 w.command('vertex-color','reconstruction',['python3','-B',str(tool),str(mesh)],gpu=False,timeout=12*3600)
 w.save(state='completed')
result=json.loads((mesh/'colored-chunks/manifest.json').read_text())
assert result['complete'] and result['geometry_unchanged']
print('RGB026='+json.dumps(dict(remote=str(mesh/'colored-chunks'),meshes=result['meshes'])))
'''
encoded=base64.b64encode(zlib.compress(code.encode())).decode()
bootstrap="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
print('026_RGB_UNION_START',dest,flush=True)
remote=run('ssh',opts+[site['ssh_user']+'@192.0.2.63',
 shlex.join(['sg','docker','-c',shlex.join(['python3','-B','-c',bootstrap])])],'RGB026=')
raw=dest/'raw';raw.mkdir()
files=dest/'files.txt';files.write_text('\n'.join(r['chunk']+'.ply' for r in remote['meshes'])+'\n')
run('rsync',['-a','--partial','--files-from='+str(files),'-e',shlex.join(['ssh']+opts),
 site['ssh_user']+'@192.0.2.63:'+remote['remote']+'/',str(raw)+'/'])
meshes=[]
for row in remote['meshes']:
 p=raw/(row['chunk']+'.ply')
 with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
 meshes.append(dict(filename=p.name,sha256=row['sha256']))
(dest/'export-plan.json').write_text(json.dumps(dict(block='026',matrix=placement['matrix'],
 session_id=placement['session_id'],meshes=meshes,source_record=records[placement['reconstruction']]),indent=2))
for stage,command in [
 ('export',['/data/barranco/runtime/alignment313/bin/python','-B','/tmp/opencode/export_aligned_mesh.py',str(dest)]),
 ('render',['blender','--background','--factory-startup','--threads','4','--python-exit-code','1','--python',
 '/tmp/opencode/render_aligned_mesh.py','--',str(dest)])]:
 subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-026-'+stage+'-'+uuid.uuid4().hex[:8],
 '-p','MemoryMax=24G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-E','OPENBLAS_NUM_THREADS=4','-E','OMP_NUM_THREADS=4',*command],check=True)
print('026_DELIVERY_READY',dest,flush=True)
