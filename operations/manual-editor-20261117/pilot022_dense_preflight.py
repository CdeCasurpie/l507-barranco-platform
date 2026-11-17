exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
code=f'''
import pathlib,subprocess,json,shutil,os
assert (pathlib.Path.home()/'L507_011.txt').is_file()
assert {macs['L507_011']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path('/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-022')
result=dict(binaries={{n:shutil.which(n) for n in ['python3','pip3','colmap','InterfaceCOLMAP','DensifyPointCloud','ReconstructMesh','RefineMesh']}},
 files=[str(p) for p in root.glob('*')],disk_free_gib=shutil.disk_usage('/data').free/2**30)
for name in ['config-full.json','assignment.json','reconstruction.json']:
 p=root/name
 if p.exists():result[name]=json.loads(p.read_text())
for command in [['nvidia-smi','--query-gpu=name,memory.free,temperature.gpu','--format=csv,noheader'],['python3','-m','pip','--version'],['find','/data/photogrammetry','-maxdepth','4','-type','f','-name','*pipeline*']]:
 p=subprocess.run(command,capture_output=True,text=True,timeout=15)
 result[str(command)]=dict(code=p.returncode,stdout=p.stdout[-12000:],stderr=p.stderr[-1000:])
result['worker_source']=(root/'phone_worker.py').read_text()
result['reconstruction_worker_source']=(root/'reconstruction_worker.py').read_text()
result['pipeline_files']=[str(p) for p in pathlib.Path('/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1/code/pipeline').glob('*')]
result['pipeline_sources']={{name:(pathlib.Path('/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1/code/pipeline')/name).read_text() for name in ['executor.py','mvs.py','sfm.py','config.py','__main__.py']}}
out=root/'outputs/cuadra-022/phone_native_2fps_seq20_loop_sparse_review_v1'
result['output_dirs']=[str(p.relative_to(out)) for p in out.iterdir()]
result['active']=json.loads(pathlib.Path('/var/lib/lab-deploy/active.json').read_text())
print('PREFLIGHT='+json.dumps(result))
'''
result=run('ssh',opts+[site['ssh_user']+'@192.0.2.65',shlex.join(['python3','-B','-c',code])],'PREFLIGHT=')
Path('/tmp/opencode/pilot022-dense-preflight.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
