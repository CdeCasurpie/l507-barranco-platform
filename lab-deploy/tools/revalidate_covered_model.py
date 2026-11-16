"""Correct a false partial only when the selected model already covers every input."""
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from drive_download_campaign import remote

site=json.loads((PROJECT/'config/site.json').read_text())
entry=next(a for a in json.loads(Path('/data/barranco/campaigns/barranco-full-v1/assignments.json').read_text())['assignments'] if a['block_id']=='013')
code=f'''
from pathlib import Path
import json,sys,time,hashlib,os
r=Path({entry['work_root']!r});sys.path.insert(0,str(r));from dense_batches import images
out=r/'outputs/cuadra-013/barranco_4k_2fps_combined_v1';qpath=out/'campaign-quality.json';status=r/'reconstruction-full-status.json'
q=json.loads(qpath.read_text());s=json.loads(status.read_text())
if s['state']!='partial':raise RuntimeError('Expected classification-only partial')
if (out/'snapshot.json').exists():raise RuntimeError('Snapshot already frozen; preserve it and issue a separate revision')
selected=(out/'colmap/best_model.txt').read_text().strip();primary={{v['name'] for v in images(out/'colmap/sparse'/selected/'images.bin').values()}}
catalog=set(json.loads((out/'image_info.json').read_text()));additional={{}}
for p in (out/'colmap/sparse').iterdir():
 if (p/'images.bin').exists():additional[p.name]=sorted({{v['name'] for v in images(p/'images.bin').values()}}-primary)
if primary!=catalog or any(additional.values()):raise RuntimeError('There are genuinely uncovered views; retain partial status')
proof={{'at':time.time(),'rule':'Selected connected model contains every input view; redundant alternative models do not imply missing coverage',
       'selected':selected,'registered':len(primary),'extracted':len(catalog),'outside_selected':additional,
       'numeric_geometry_unchanged':True,'original_quality':q}}
provenance=out/'provenance';provenance.mkdir(exist_ok=True)
(provenance/'coverage-revalidation.json').write_text(json.dumps(proof,indent=2)+'\\n')
q.update(complete=True,component_views_outside_selected=additional,coverage_revalidated=True)
tmp=qpath.with_suffix('.tmp');tmp.write_text(json.dumps(q,indent=2)+'\\n');tmp.replace(qpath)
s.update(state='completed',quality=q,revalidated_at=time.time(),coverage_revalidation='provenance/coverage-revalidation.json')
tmp=status.with_suffix('.tmp');tmp.write_text(json.dumps(s,indent=2)+'\\n');tmp.replace(status)
print('DOWNLOAD_REPLY='+json.dumps({{'block':'013','state':'completed','registered':len(primary),'extracted':len(catalog),'dense_points':q['dense_points'],'geometry_unchanged':True}}))
'''
print(remote(site,entry['ip'],code))
