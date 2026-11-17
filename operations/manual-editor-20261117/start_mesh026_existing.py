exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import base64,zlib,uuid
launch=json.loads(Path('/tmp/opencode/dense-026-parque-launch.json').read_text())
files={name:Path('/tmp/opencode',local).read_text() for name,local in
       [('mesh_existing_worker.py','mesh026_existing_worker.py'),('mesh_existing_chunks.py','mesh026_existing_chunks.py')]}
unit='barranco-mesh026-existing-'+uuid.uuid4().hex[:10]
launch['mesh_unit']=unit
Path('/tmp/opencode/mesh026-existing-launch.json').write_text(json.dumps(launch,indent=2))
code=f'''
import pathlib,json,subprocess,shlex,os
assert (pathlib.Path.home()/'L507_019.txt').is_file()
assert {macs['L507_019']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
assert root.stat().st_dev==pathlib.Path('/data').stat().st_dev
if (root/'mesh-existing').exists():
 status=json.loads((root/'reconstruction-mesh-existing-status.json').read_text())
 assert status['state'] in ('failed','completed'),'Refuse to replace an active mesh job'
 assert "native=scene.parent/'scene_dense.ply'" not in (root/'mesh_existing_chunks.py').read_text(),'Existing dense-based mesh requires explicit resume'
 (root/'mesh-existing').rename(root/('mesh-existing-failed-'+{uuid.uuid4().hex[:8]!r}))
source=pathlib.Path(json.loads((root/'pilot.json').read_text())['source_root'])
out=source/'outputs/cuadra-026/phone_native_2fps_all_review_v1/mvs'
assert (out/'dense-batches.json').is_file()
for name,content in {files!r}.items():
 target=root/name
 if target.exists():target.rename(target.with_name(target.name+'.previous-'+{uuid.uuid4().hex[:8]!r}))
 target.write_text(content)
(root/'mesh-existing.json').write_text(json.dumps(dict(source_mvs=str(out),delete_authorized=False,
 preserve_depth_maps=True,requested_face_reduction_percent=70)))
print('MESH026_START',str(root),flush=True)
command=['systemd-run','--user','--wait','--pipe','--unit='+{unit!r},
 '-p','MemoryMax=42G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-p','RuntimeMaxSec=259200','sg','docker','-c',
 shlex.join(['python3','-B',str(root/'mesh_existing_worker.py'),str(root)])]
result=subprocess.run(command)
print('MESH026_END',result.returncode,flush=True)
raise SystemExit(result.returncode)
'''
encoded=base64.b64encode(zlib.compress(code.encode())).decode()
command="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
print('026 mesh-only supervisor',unit,flush=True)
run('ssh',opts+[site['ssh_user']+'@192.0.2.63',shlex.join(['python3','-B','-c',command])])
