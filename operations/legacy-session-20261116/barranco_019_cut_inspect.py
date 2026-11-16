import json
from pathlib import Path
import sqlite3
assert NODE_TAG=='L507_004'
root=Path('/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-019')
s=json.loads((root/'reconstruction-full-status.json').read_text())
out=root/'outputs/cuadra-019'/s['experiment']
assert s['state']=='awaiting_review'
with sqlite3.connect((out/'colmap/database.db').as_uri()+'?mode=ro',uri=True) as db:
    names=dict(db.execute('SELECT image_id,name FROM images'))
    pairs=[]
    for i in range(824,833):
        for j in range(i+1,834):
            row=db.execute('SELECT rows,config FROM two_view_geometries WHERE pair_id=?',(i*2147483647+j,)).fetchone()
            pairs.append({'a':i,'b':j,'inliers':row[0] if row else 0,'config':row[1] if row else None})
cfg=json.loads((root/'config-full.json').read_text())
print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'source_output':str(out),
    'targets':{str(i):names.get(i) for i in (827,828,829,830)},'pairs':pairs,
    'frames_config':cfg['frames'],'masking_classes':cfg['masking']['classes'],
    'mask_prompts':cfg['masking']['backends']['sam3']['prompts'],
    'videos_info':json.loads((out/'metrics/videos_info.json').read_text())}))
