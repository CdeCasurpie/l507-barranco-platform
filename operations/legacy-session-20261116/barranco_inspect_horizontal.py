import json
from pathlib import Path
import subprocess
root=Path('/data/photogrammetry/campaigns/barranco-006-horizontal-20261115/cuadra-006')
r={'tag':NODE_TAG,'root':str(root)}
for name in ('assignment.json','config-full.json','reconstruction.json','reconstruction-full-status.json'):
    r[name]=json.loads((root/name).read_text())
s=r['reconstruction-full-status.json']
out=root/'outputs/cuadra-006'/s['experiment']
frames=out/'frames'
r['frame_count']=sum(1 for p in frames.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png'))
r['output_files']=[str(p.relative_to(out)) for p in out.iterdir()]
for key,args in [('gpu',['nvidia-smi','--query-gpu=temperature.gpu,power.limit','--format=csv,noheader,nounits']),
                 ('jobs',['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader']),
                 ('disk',['df','-h','/','/data'])]:
    p=subprocess.run(args,capture_output=True,text=True,timeout=15)
    r[key]={'rc':p.returncode,'out':p.stdout,'err':p.stderr}
print('ADMIN_REPLY='+json.dumps(r))
