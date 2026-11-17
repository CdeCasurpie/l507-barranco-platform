"""Mesh existing dense chunks only. Never write into the source campaign."""
import fcntl
import json
from pathlib import Path
import signal
import sys
import time
from phone_worker import PhoneWorker
root=Path(sys.argv[1])
source=Path(json.loads((root/'pilot.json').read_text())['source_root'])
class MeshOnly(PhoneWorker):
    def docker_args(self,stage,role,argv,gpu=True):
        name,token,args=super().docker_args(stage,role,argv,gpu)
        index=args.index(self.spec['images'][role]['tag'])
        args[index:index]=['--mount',f'type=bind,src={source},dst={source},readonly']
        return name,token,args
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    w=MeshOnly(root,'mesh-existing')
    signal.signal(signal.SIGTERM,lambda *_:setattr(w,'cancelled',True))
    signal.signal(signal.SIGINT,lambda *_:setattr(w,'cancelled',True))
    try:
        t=w.sample()
        # No new dense workspaces or depth maps: budget 20 GiB above the
        # unchanged hard 50 GiB reserve, rather than dense's 100 GiB admission.
        assert t['data_free_gib']>=70 and t['ram_available_gib']>=40 and t['root_free_gib']>=3.75
        w.save(dense_reused=True,triangulation_executed=False,originals_readonly=True)
        w.command('mesh-existing','reconstruction',
            ['python3','-B',str(root/'mesh_existing_chunks.py'),str(root)],gpu=True,timeout=72*3600)
        w.save(state='completed',stage='mesh_complete',finished_at=time.time())
    except BaseException as error:
        w.save(state='failed',error=str(error),finished_at=time.time())
        raise
