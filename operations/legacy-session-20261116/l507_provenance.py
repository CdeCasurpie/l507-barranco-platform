import pathlib
exec(pathlib.Path('/tmp/opencode/l507_storage.py').read_text().split('\njobs=')[0])
BASE=pathlib.Path('/tmp/opencode/l507-provenance')
BASE.mkdir(exist_ok=True)
# Reuse the already verified SSH host keys, without changing campaign state.
(BASE/'known_hosts').write_text(pathlib.Path('/tmp/opencode/l507-storage/known_hosts').read_text())
manifest=json.loads(pathlib.Path('/home/exitoso/home/barranco-roi/state/mesh-campaign-20261112/manifest.json').read_text())
assignments=manifest['assignments']
identity=CODE.split("docker=[]")[0]
CODE=identity+"\nassignments="+repr(assignments)+r'''
a=next(a for a in assignments.values() if a['node_tag']==tag)
b=a['roi']['block']
source=pathlib.Path(a['source_root'].replace('/mnt/datos/','/data/',1))
mesh=pathlib.Path(a['work_root'].replace('/mnt/datos/','/data/',1))
result.update(block=b,source=str(source),mesh_root=str(mesh))
paths=['colmap/best_model.txt','mvs/scene.mvs','mvs/scene_dense.mvs','mvs/scene_dense.ply','mvs/scene_dense_scalar.ply','mvs/dense-batches.json','dense-lineage.json']
result['source_files']={p:{'exists':(source/p).is_file(),'bytes':(source/p).stat().st_size if (source/p).is_file() else None} for p in paths}
chunks=sorted((source/'mvs/chunks').glob('*'))
result['chunks']=[{'chunk':p.name,'native':(p/'scene_dense.ply').is_file(),'scene':(p/'scene_dense.mvs').is_file()} for p in chunks if p.is_dir()]
result['mesh_files']={p:{'exists':(mesh/p).is_file(),'bytes':(mesh/p).stat().st_size if (mesh/p).is_file() else None} for p in ['assignment.json','status.json','result.json','camera-audit.json','native_10cm.ply','scene.mvs','mesh_local.ply','manzana_'+b+'_world.ply']}
for name in ['status.json','result.json']:
 p=mesh/name
 if p.is_file():result[name]=json.loads(p.read_text())
result['undistorted_images']=len([p for p in (source/'colmap/undistorted/images').rglob('*') if p.is_file()])
result['after']=mounts
print('RESULT='+json.dumps(result))
'''
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 jobs=[(a['node_tag'],IPS[a['node_tag'][-3:]],a['mac']) for a in assignments.values()]
 for r in pool.map(lambda x:work(*x),jobs):print(r,flush=True)
