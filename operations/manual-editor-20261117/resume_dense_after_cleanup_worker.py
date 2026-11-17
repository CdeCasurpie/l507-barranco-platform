"""Resume dense and mesh only; keep all completed geometry and original poses."""
import fcntl
import json
from pathlib import Path
import signal
import subprocess
import sys
import time
from phone_worker import PhoneWorker

root=Path(sys.argv[1])
source=Path(json.loads((root/'pilot.json').read_text())['source_root'])
class Resume(PhoneWorker):
    def docker_args(self,stage,role,argv,gpu=True):
        name,token,args=super().docker_args(stage,role,argv,gpu)
        index=args.index(self.spec['images'][role]['tag'])
        args[index:index]=['--mount',f'type=bind,src={source},dst={source},readonly',
                          '-e',f'PYTHONPATH={self.root}/python-deps']
        return name,token,args
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    worker=Resume(root,'full')
    signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
    signal.signal(signal.SIGINT,lambda *_:setattr(worker,'cancelled',True))
    try:
        assert 'undistort' in worker.status['completed_stages']
        assert 'dense' not in worker.status['completed_stages']
        for image in worker.spec['images'].values():
            got=subprocess.check_output(['docker','image','inspect','--format','{{.Id}}',image['tag']],text=True).strip()
            assert got==image['id']
        assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
        t=worker.sample()
        # Resume existing undistorted workspace, no extra workspace copies.
        # Hard runtime stops stay unchanged: /data >=50GiB, RAM >=8GiB, thermal guards.
        assert t['data_free_gib']>=80 and t['ram_available_gib']>=40 and t['root_free_gib']>=3.75
        worker.save(state='running',resume_after_authorized_depth_cleanup=True,
                    cleanup_completed_chunks_only=True,ba_authorized=False)
        worker.command('dense','reconstruction',
            ['python3','-B',str(root/'dense_batches.py'),str(root),worker.experiment],timeout=72*3600)
        output=root/'outputs'/('cuadra-'+worker.assignment['block_id'])/worker.experiment
        worker.command('mesh','reconstruction',
            ['python3','-B',str(root/'mesh_chunks.py'),str(output/'mvs')],timeout=48*3600)
        worker.save(state='completed',stage='complete',finished_at=time.time(),output=str(output),
            mesh_layout='one dense-input Delaunay mesh per chunk; overlaps retained')
    except BaseException as error:
        worker.save(state='failed',error=str(error),finished_at=time.time())
        raise
