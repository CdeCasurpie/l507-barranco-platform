import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

assignment=next(a for a in BINDINGS['assignments'] if a['node_tag']==NODE_TAG)
assert assignment['operation']=='download_only'
assert os.path.ismount('/data')
assert shutil.disk_usage('/').free > 3.75*2**30
assert shutil.disk_usage('/data').free-sum(f['bytes'] for f in assignment['files']) > 50*2**30
root=Path(assignment['work_root'])
assert root.is_relative_to('/data/photogrammetry/campaigns/barranco-running-20261116')
assert not root.is_symlink()
root.mkdir(parents=True,exist_ok=True)
with (root/'bootstrap.lock').open('a') as guard:
    fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    path=root/'assignment.json'
    if path.exists():
        assert json.loads(path.read_text())==assignment,'Immutable assignment mismatch'
    else:
        path.write_text(json.dumps(assignment,indent=2)+'\n')
    status_path=root/'status.json'
    status=json.loads(status_path.read_text()) if status_path.exists() else {}
    proc=Path('/proc/'+str(status.get('pid'))+'/cmdline')
    alive=proc.exists() and str(root).encode() in proc.read_bytes()
    if alive or status.get('state')=='downloaded':
        reply={'tag':NODE_TAG,'block':assignment['block_id'],'existing':status,'worker_alive':alive}
    else:
        assert not status or status.get('state') not in ('failed',), 'Inspect failed attempt before retry'
        source=BINDINGS['worker']
        script=root/'download_worker.py'
        if script.exists():
            assert script.read_text()==source
        else:
            script.write_text(source)
        record={'assignment_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'worker_sha256':hashlib.sha256(source.encode()).hexdigest(),
                'operation':'download_only','reconstruction_authorized':False,
                'started_at':time.time()}
        with (root/'download.log').open('a') as log:
            process=subprocess.Popen(['python3','-B','-u',str(script),str(root)],
                                     stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                                     start_new_session=True)
        record['pid']=process.pid
        (root/'download-launch.json').write_text(json.dumps(record,indent=2)+'\n')
        reply={'tag':NODE_TAG,'block':assignment['block_id'],'state':'starting',
               'pid':process.pid,'files':len(assignment['files']),
               'bytes':sum(f['bytes'] for f in assignment['files']),'root':str(root)}
print('ADMIN_REPLY='+json.dumps(reply))
