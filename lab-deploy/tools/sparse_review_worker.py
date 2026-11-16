"""Single-video, sparse-only worker with unchanged thermal guards."""
import fcntl
import hashlib
import json
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
from phone_worker import PhoneWorker


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4194304),b''):
            h.update(block)
    return h.hexdigest()


class SparseWorker(PhoneWorker):
    def preflight(self):
        assert len(self.assignment['files'])==1
        assert self.assignment['files'][0]['name'].lower().endswith('.mp4')
        current=json.loads(Path('/var/lib/lab-deploy/active.json').read_text())
        assert current['code_root']==self.spec['code_root']
        assert current['data_root']==self.spec['certified_data_root']
        assert subprocess.check_output(['git','-C',self.spec['code_root'],'rev-parse','HEAD'],text=True).strip()==self.spec['pipeline_commit']
        assert not subprocess.check_output(['git','-C',self.spec['code_root'],'status','--porcelain'],text=True).strip()
        for name,expected in self.spec['bundle_hashes'].items():
            assert digest(self.root/name)==expected,'Execution bundle changed: '+name
        item=self.assignment['files'][0]
        path=self.root/item['relative_path']
        receipt=json.loads(path.with_name(path.name+'.fetch.json').read_text())
        assert receipt['drive_file_id']==item['id']
        assert path.stat().st_size==item['bytes']
        assert digest(path)==receipt['sha256'],'Downloaded input hash changed'
        super().preflight()

    def run(self):
        self.preflight()
        scene='cuadra-'+self.assignment['block_id']
        config=str(self.root/'config-full.json')
        command=['python3','-B','-m','pipeline','run','--scene',scene,'--config',config,'--stages']
        for stage,role in [('frames','reconstruction'),('masks','segmentation')]:
            self.stage(stage,role,command+[stage],timeout=12*3600)
        self.stage('sfm','reconstruction',
                   ['python3','-B',str(self.root/'sparse_loop_overlay.py'),'run',
                    '--scene',scene,'--config',config,'--stages','sfm'],timeout=24*3600)
        out=self.root/'outputs'/scene/self.experiment
        models={}
        for path in sorted((out/'colmap/sparse').glob('*/images.bin')):
            with path.open('rb') as stream:
                cameras=struct.unpack('<Q',stream.read(8))[0]
            with (path.parent/'points3D.bin').open('rb') as stream:
                points=struct.unpack('<Q',stream.read(8))[0]
            models[path.parent.name]={'registered_images':cameras,'points3D':points}
        best=(out/'colmap/best_model.txt').read_text().strip()
        assert best in models
        self.save(state='awaiting_review',stage='sparse_review',components=models,
                  sparse_ready=True,sparse_model=str(out/'colmap/sparse'/best),
                  registered_images=models[best]['registered_images'],
                  review_required=True,geometry_approved=False,dense_authorized=False,
                  mesh_authorized=False,alignment_authorized=False,finished_at=time.time())


if __name__=='__main__':
    root=Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=SparseWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
        signal.signal(signal.SIGINT,lambda *_:setattr(worker,'cancelled',True))
        try:
            worker.run()
        except BaseException as exc:
            worker.save(state='failed',error=str(exc),finished_at=time.time())
            raise
