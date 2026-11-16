import pathlib
exec(pathlib.Path('/tmp/opencode/l507_storage.py').read_text().split('\njobs=')[0])
BASE=pathlib.Path('/tmp/opencode/l507-find-blocks')
BASE.mkdir(exist_ok=True)
(BASE/'known_hosts').write_text(pathlib.Path('/tmp/opencode/l507-storage/known_hosts').read_text())
identity=CODE.split("docker=[]")[0]
CODE=identity+r'''
import re
pattern=re.compile(r'(?:cuadra|manzana|block)[-_ ]*0*(6|11|26)(?!\d)|^(?:006|011|026)$',re.I)
found=[]
roots=[pathlib.Path('/data/photogrammetry'),pathlib.Path('/home/utec_alumno')]
for root in roots:
 for base,dirs,files in os.walk(root):
  rel=pathlib.Path(base).relative_to(root)
  dirs[:]=[x for x in dirs if x not in ('runtime','.git','node_modules','.cache','.local','.config','.vscode-server','models','checkpoints','site-packages','frames','images','masks','scratch')]
  if len(rel.parts)>7:dirs[:]=[];continue
  if pattern.search(pathlib.Path(base).name):
   p=pathlib.Path(base)
   item={'path':str(p),'entries':sorted(dirs+files)[:40]}
   if 'outputs' not in rel.parts and 'raw' not in rel.parts:
    item['status']={}
    for name in ('reconstruction-full-status.json','status.json','reconstruction.json','assignment.json'):
     q=p/name
     if q.is_file():
      try:
       v=json.loads(q.read_text())
       item['status'][name]={k:v[k] for k in ('state','stage','block_id','node_tag','campaign_id','full_experiment','updated_at','error') if k in v}
      except Exception:pass
    item['results']=[{'path':str(q.parent),'dense':(q.parent/'mvs/scene_dense_scalar.ply').is_file(),'scene':(q.parent/'mvs/scene.mvs').is_file()} for q in (p/'outputs').glob('*/*/run_manifest.json')]
   found.append(item)
result['found']=found
result['after']=mounts
print('RESULT='+json.dumps(result))
'''
jobs=[('L507_'+n,ip,SITE['nodes']['L507_'+n]) for n,ip in IPS.items()]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for r in pool.map(lambda x:work(*x),jobs):print(r,flush=True)
