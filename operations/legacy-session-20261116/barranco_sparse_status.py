import json
from pathlib import Path
a=next(a for a in BINDINGS['assignments'] if a['node_tag']==NODE_TAG)
root=Path(a['work_root'])
path=root/'reconstruction-full-status.json'
s=json.loads(path.read_text()) if path.exists() else {}
launch=json.loads((root/'sparse-launch.json').read_text()) if (root/'sparse-launch.json').exists() else {}
pid=s.get('pid',launch.get('pid'))
proc=Path('/proc/'+str(pid)+'/cmdline')
alive=proc.exists() and str(root).encode() in proc.read_bytes()
reply={'tag':NODE_TAG,'block':a['block_id'],'state':s.get('state','starting'),
       'stage':s.get('stage','preflight/input-hash'),'worker_alive':alive,
       'error':s.get('error'),'completed_stages':s.get('completed_stages',[]),
       'telemetry':s.get('telemetry'),'registered_images':s.get('registered_images'),
       'components':s.get('components')}
if not alive or s.get('state')=='failed':
    log=root/'sparse-worker.log'
    reply['log_tail']=log.read_text(errors='replace')[-1800:] if log.exists() else ''
print('ADMIN_REPLY='+json.dumps(reply))
