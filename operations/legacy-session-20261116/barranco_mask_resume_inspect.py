import json
from pathlib import Path
root=Path('/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1/code')
matches=[]
for p in root.glob('pipeline/*.py'):
    text=p.read_text(errors='replace')
    if 'def run_masks' not in text:
        continue
    lines=text.splitlines()
    positions=set()
    for i,line in enumerate(lines):
        if any(s in line for s in ('def run_masks','rmtree','unlink','exists()','mask_dir','masks_dir','backend_dir','mkdir')):
            positions.update(range(max(0,i-4),min(len(lines),i+8)))
    matches.append({'file':str(p),'excerpts':'\n'.join(f'{i+1}: {lines[i]}' for i in sorted(positions))})
print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'matches':matches}))
