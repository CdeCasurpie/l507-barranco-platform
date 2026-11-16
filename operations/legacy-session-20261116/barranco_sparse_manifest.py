import hashlib
import json
from pathlib import Path
a=next(a for a in BINDINGS['assignments'] if a['node_tag']==NODE_TAG)
assert a['block_id'] in ('019','020','021')
root=Path(a['work_root'])
s=json.loads((root/'reconstruction-full-status.json').read_text())
assert s['state']=='awaiting_review' and s['sparse_ready']
assert s['stage']=='sparse_review' and 'sfm' in s['completed_stages']
out=root/'outputs'/('cuadra-'+a['block_id'])/s['experiment']
files={}
paths=[out/'colmap/best_model.txt']
for model in (out/'colmap/sparse').iterdir():
    if model.is_dir() and model.name.isdigit():
        paths.extend(model/name for name in ('cameras.bin','images.bin','points3D.bin'))
paths+=list((out/'metrics').glob('*.json'))
for name in ('config_resolved.yaml','run_manifest.json'):
    if (out/name).is_file():paths.append(out/name)
for p in paths:
    assert p.is_file() and not p.is_symlink()
    h=hashlib.sha256()
    with p.open('rb') as stream:
        for b in iter(lambda:stream.read(4194304),b''):h.update(b)
    files[str(p.relative_to(out))]={'bytes':p.stat().st_size,'sha256':h.hexdigest()}
print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'block':a['block_id'],'root':str(out),
       'files':files,'selected':(out/'colmap/best_model.txt').read_text().strip(),
       'registered_images':s.get('registered_images'),'components':s.get('components'),
       'geometry_approved':False}))
