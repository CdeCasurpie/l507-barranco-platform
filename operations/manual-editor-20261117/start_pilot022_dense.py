exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import subprocess,uuid,base64,zlib
label=sys.argv[1] if len(sys.argv)>1 else '022'
receipt=json.loads((Path('/data/barranco/review/catalog-20261116-134343')/label/'collection.json').read_text())
tag=receipt['tag']
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
ip=cache[tag]['ip']
if tag=='L507_005':opts+=['-o','HostKeyAlias=192.0.2.58']
state=Path('/data/barranco/manual-graph-editor')
drafts=[json.loads(p.read_text()) for p in state.glob('g-*.json')]
candidates=[d for d in drafts if '/'+label+'/colmap/sparse/' in d['source_model']]
draft=max(candidates,key=lambda d:d['created_at']) if candidates else dict(
 source_model=str(Path('/data/barranco/review/catalog-20261116-134343')/label/'colmap/sparse'/receipt['selected']),
 pins=[],deleted=[],id='original-poses-'+label)
solve_code="""import json,sys
from pathlib import Path
sys.path.insert(0,'/home/exitoso/home/sparse-review')
import graph_edit
d=json.load(sys.stdin);m=Path(d['source_model'])
meta,_=graph_edit.get_graph(m)
if 'source_hashes' in d:assert graph_edit.fingerprint(m)==d['source_hashes']
if d['pins']:r=graph_edit.solve(m,d)
else:r=dict(displacements=[[0.,0.,0.] for c in meta['cameras']],rotations=[[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]] for c in meta['cameras']])
print(json.dumps(dict(result=r,ids=[c['id'] for c in meta['cameras']],source_hashes=meta['source_hashes'])))
"""
solved=json.loads(subprocess.check_output(['/data/barranco/runtime/alignment311/bin/python','-B','-c',solve_code],input=json.dumps(draft),text=True))
remote_output=Path(receipt['root'])
source=str(remote_output.parents[2])
experiment=remote_output.name
scene=remote_output.parent.name
component=Path(draft['source_model']).name
pilot='/data/photogrammetry/campaigns/manual'+label+'-dense-'+uuid.uuid4().hex
draft['source_hashes']=solved['source_hashes']
draft['source_model']=str(remote_output/'colmap/sparse'/component)
spec=dict(draft=draft,camera_ids=solved['ids'],displacements=solved['result']['displacements'],
    rotations=solved['result']['rotations'],database_path=str(remote_output/'colmap/database.db'),mode='triangulation_only')
if label in ('026-parque','027'):spec['mode']='dense_only'
files={n:Path('/home/exitoso/home/sparse-review',n).read_text() for n in ['graph_job.py','graph_edit.py','app.py']}
files.update({'pilot_worker.py':Path('/tmp/opencode/pilot022_remote_worker.py').read_text(),
 'mesh_chunks.py':Path('/tmp/opencode/pilot022_mesh_chunks.py').read_text(),
 'triangulate.py':"from pathlib import Path\nimport sys,faulthandler\nfaulthandler.enable()\nfrom graph_job import compute\ncompute(Path(sys.argv[1]))\n"})
payload=dict(pilot=pilot,source=source,experiment=experiment,spec=spec,files=files)
code=f'''
import pathlib,json,shutil,subprocess,os,shlex
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
data=json.loads({json.dumps(payload)!r})
root=pathlib.Path(data['pilot']);source=pathlib.Path(data['source'])
assert not root.exists()
root.mkdir();(root/'job').mkdir()
(root/'job/request.json').write_text(json.dumps(data['spec']))
for name,content in data['files'].items():(root/name).write_text(content)
for name in ['phone_worker.py','reconstruction_worker.py','dense_batches.py','campaign_post.py']:
 shutil.copy2(source/name,root/name)
assignment=json.loads((source/'assignment.json').read_text());assignment['work_root']=str(root)
(root/'assignment.json').write_text(json.dumps(assignment))
spec=json.loads((source/'reconstruction.json').read_text())
spec.update(full_experiment='manual_fixed_poses_dense_mesh',dense_authorized=True,mesh_authorized=True,sparse_only=False)
(root/'reconstruction.json').write_text(json.dumps(spec))
cfg=json.loads((source/'config-full.json').read_text())
cfg['experiment']['name']=spec['full_experiment']
cfg['paths']['output_root']=str(root/'outputs')
cfg['openmvs']['mesh']['enabled']=True
cfg['openmvs']['refine']['enabled']=False
cfg['openmvs']['texture']['enabled']=False
(root/'config-full.json').write_text(json.dumps(cfg))
(root/'pilot.json').write_text(json.dumps(dict(source_root=str(source),authorization='User explicitly accepts low-quality candidate for dense and mesh; no BA')))
out=root/'outputs'/{scene!r}/spec['full_experiment'];out.mkdir(parents=True)
original=source/'outputs'/{scene!r}/data['experiment']
for name in ['frames']+(['masks'] if cfg['masking']['enabled'] else []):
 assert (original/name).is_dir()
 (out/name).symlink_to(original/name,target_is_directory=True)
for name in ['tmp','cache','hf']:(root/'scratch'/name).mkdir(parents=True)
install=['docker','run','--rm','--pull=never','--cpus','4','--memory','4g','--memory-swap','4g',
 '--read-only','--tmpfs','/tmp:rw,size=1g','--cap-drop','ALL','--security-opt','no-new-privileges=true',
 '--user',str(os.getuid())+':'+str(os.getgid()),'--mount',f'type=bind,src={{root}},dst={{root}}',
 '--entrypoint','python3',spec['images']['reconstruction']['id'],'-m','pip','install','--no-cache-dir',
 '--only-binary=:all:','--target',str(root/'python-deps'),'pycolmap==3.11.1','numpy<2','scipy']
with (root/'install.log').open('wb') as log:
 installed=subprocess.run(install,stdout=log,stderr=subprocess.STDOUT,timeout=240)
assert installed.returncode==0,'Isolated installation failed; inspect '+str(root/'install.log')
if not cfg['masking']['enabled']:
 p=root/'dense_batches.py'
 text=p.read_text()
 text=text.replace("for view in views.values():\\n        if not (masks/", "for view in (views.values() if cfg.get('masking',{{}}).get('enabled') else []):\\n        if not (masks/")
 text=text.replace("invoke(args,directory,directory/'dense.log')", "if not cfg.get('masking',{{}}).get('enabled'):\\n                at=args.index('--mask-path');del args[at:at+4]\\n            invoke(args,directory,directory/'dense.log')")
 compile(text,str(p),'exec');p.write_text(text)
unit='barranco-dense-'+{label!r}+'-'+root.name.rsplit('-',1)[1][:12]
p=subprocess.run(['systemd-run','--user','--unit='+unit,'-p','MemoryMax=42G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10','-p','RuntimeMaxSec=432000','sg','docker','-c',shlex.join(['python3','-B',str(root/'pilot_worker.py'),str(root)])],capture_output=True,text=True,timeout=15)
assert p.returncode==0,p.stderr
print('LAUNCH='+json.dumps(dict(root=str(root),unit=unit,output=str(out))))
'''
encoded=base64.b64encode(zlib.compress(code.encode())).decode()
bootstrap="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
if len(bootstrap)>60000:
 local_launcher=Path('/tmp/opencode')/('remote-launch-'+uuid.uuid4().hex+'.py')
 local_launcher.write_text(bootstrap)
 remote_launcher='/data/photogrammetry/campaigns/'+local_launcher.name
 run('rsync',['-a','-e',shlex.join(['ssh']+opts),str(local_launcher),site['ssh_user']+'@'+ip+':'+remote_launcher])
 command=['python3','-B',remote_launcher]
else:
 command=['python3','-B','-c',bootstrap]
result=run('ssh',opts+[site['ssh_user']+'@'+ip,shlex.join(command)],'LAUNCH=')
Path('/tmp/opencode/dense-'+label+'-launch.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
