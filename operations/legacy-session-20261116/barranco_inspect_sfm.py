import json
from pathlib import Path
active=json.loads(Path('/var/lib/lab-deploy/active.json').read_text())
root=Path(active['code_root'])
files=[]
for p in root.rglob('*.py'):
    if '.git' in p.parts:continue
    text=p.read_text(errors='replace')
    if 'sequential_overlap' in text or 'match_sequential' in text or 'sequential_matcher' in text:
        files.append({'file':str(p.relative_to(root)),'text':text[:35000]})
print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'active':active,'files':files}))
