"""Isolated 022: fixed-pose triangulation, certified dense batches, chunk meshes."""
import fcntl
import json
from pathlib import Path
import signal
import shutil
import sys
import time
from phone_worker import PhoneWorker
from graph_edit import fingerprint

root=Path(sys.argv[1])
source=Path(json.loads((root/'pilot.json').read_text())['source_root'])

class Pilot(PhoneWorker):
    def docker_args(self,stage,role,argv,gpu=True):
        name,token,args=super().docker_args(stage,role,argv,gpu)
        index=args.index(self.spec['images'][role]['tag'])
        args[index:index]=['--mount',f'type=bind,src={source},dst={source},readonly',
                          '-e',f'PYTHONPATH={self.root}/python-deps']
        return name,token,args

with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    worker=Pilot(root,'full')
    signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
    signal.signal(signal.SIGINT,lambda *_:setattr(worker,'cancelled',True))
    try:
        worker.preflight()
        worker.save(quality_override_authorized=True,dense_authorized=True,mesh_authorized=True,ba_authorized=False)
        request=json.loads((root/'job/request.json').read_text())
        if request.get('mode')=='dense_only':
            sparse_source=Path(request['draft']['source_model'])
            assert fingerprint(sparse_source)==request['draft']['source_hashes']
            report=dict(quality_screen_passed=False,ba_executed=False,source_unchanged=True,
                        triangulation_executed=False)
        else:
            worker.command('triangulation','reconstruction',
                ['python3','-B',str(root/'triangulate.py'),str(root/'job')],gpu=False,timeout=3600)
            report=json.loads((root/'job/report.json').read_text())
            assert report['ba_executed'] is False and report['source_unchanged']
            sparse_source=root/'job/candidate'
        scene='cuadra-'+worker.assignment['block_id']
        output=root/'outputs'/scene/worker.experiment
        sparse=output/'colmap/sparse/0'
        shutil.copytree(sparse_source,sparse)
        (output/'colmap/best_model.txt').write_text('0')
        command=['python3','-B','-m','pipeline','run','--scene',scene,
            '--config',str(root/'config-full.json'),'--stages']
        worker.command('undistort','reconstruction',command+['undistort'],timeout=12*3600)
        worker.command('dense','reconstruction',
            ['python3','-B',str(root/'dense_batches.py'),str(root),worker.experiment],timeout=72*3600)
        worker.command('mesh','reconstruction',
            ['python3','-B',str(root/'mesh_chunks.py'),str(output/'mvs')],timeout=48*3600)
        worker.save(state='completed',stage='complete',finished_at=time.time(),
            quality_screen_passed=report['quality_screen_passed'],geometry_approved=False,
            output=str(output),mesh_layout='one mesh per bounded dense chunk')
    except BaseException as error:
        worker.save(state='failed',error=str(error),finished_at=time.time())
        raise
