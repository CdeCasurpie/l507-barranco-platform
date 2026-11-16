import json
from pathlib import Path
root=Path('/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1/code')
result=[]
for p in (root/'pipeline').glob('*.py'):
    text=p.read_text(errors='replace')
    if 'masks_dir' in text and p.name in ('config.py','cli.py'):
        lines=text.splitlines()
        for i,line in enumerate(lines):
            if 'masks_dir' in line:result.append({'file':str(p),'excerpt':'\n'.join(lines[max(0,i-3):i+8])})
print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'matches':result}))
