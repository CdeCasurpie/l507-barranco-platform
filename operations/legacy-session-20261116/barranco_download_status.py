import json
from pathlib import Path
import shutil
a=next(a for a in BINDINGS['assignments'] if a['node_tag']==NODE_TAG)
root=Path(a['work_root'])
path=root/'status.json'
s=json.loads(path.read_text()) if path.exists() else {}
proc=Path('/proc/'+str(s.get('pid'))+'/cmdline')
alive=proc.exists() and str(root).encode() in proc.read_bytes()
print('ADMIN_REPLY='+json.dumps({
    'tag':NODE_TAG,'block':a['block_id'],'state':s.get('state'),
    'worker_alive':alive,'completed_files':s.get('completed_files'),
    'total_files':s.get('total_files'),'current_file':s.get('current_file'),
    'current_bytes':s.get('current_bytes'),'error':s.get('error'),
    'root_free_gib':round(shutil.disk_usage('/').free/2**30,2),
    'completed_bytes':s.get('completed_bytes'),
    'total_bytes':s.get('total_bytes')}))
