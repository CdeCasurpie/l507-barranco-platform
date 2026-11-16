import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time

assert NODE_TAG=='L507_005'
root=Path('/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-020')
s=json.loads((root/'reconstruction-full-status.json').read_text())
assert s['state']=='awaiting_review'
out=root/'outputs/cuadra-020'/s['experiment']
code=Path('/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1/code')
excerpts={}
for name in ('frames.py','masks.py'):
    p=code/'pipeline'/name
    text=p.read_text()
    if name=='frames.py':
        excerpts[name]=text[:35000]
    else:
        lines=text.splitlines()
        excerpts[name]='\n'.join(lines[195:257])
with sqlite3.connect((out/'colmap/database.db').as_uri()+'?mode=ro',uri=True) as db:
    images=dict(db.execute('SELECT image_id,name FROM images'))
    rows=[]
    for i in range(543,555):
        for j in range(i+1,555):
            pair=i*2147483647+j
            row=db.execute('SELECT rows,config FROM two_view_geometries WHERE pair_id=?',(pair,)).fetchone()
            if row:rows.append({'a':i,'b':j,'inliers':row[0],'config':row[1]})
    total=len(images)
names=[p.name for p in (out/'frames/phone').glob('*.jpg')]
r={'tag':NODE_TAG,'root':str(root),'output':str(out),'total_images':total,
   'targets':{str(i):images.get(i) for i in (547,548,549,550)},
   'verified_pairs_near_cut':rows,'frame_files':len(names),'source_code':excerpts,
   'videos_info':json.loads((out/'metrics/videos_info.json').read_text()),
   'mask_files_examples':[str(p.relative_to(out/'masks')) for p in (out/'masks').rglob('*.png')][:8]}
for key,args in [('gpu',['nvidia-smi','--query-gpu=temperature.gpu,power.limit','--format=csv,noheader,nounits']),
                 ('gpu_jobs',['nvidia-smi','--query-compute-apps=pid,process_name','--format=csv,noheader']),
                 ('disk',['df','-h','/','/data'])]:
    p=subprocess.run(args,capture_output=True,text=True,timeout=15);r[key]=p.stdout.strip()
print('ADMIN_REPLY='+json.dumps(r))
