"""Bounded local-cut diagnostic: 10 fps near selected cut, source immutable."""
import fcntl
import json
from pathlib import Path
import signal
import struct
import sys
import time
import subprocess
from sparse_review_worker import SparseWorker


class CutWorker(SparseWorker):
    def docker_args(self,stage,role,argv,gpu=True):
        name,token,args=super().docker_args(stage,role,argv,gpu)
        source=self.spec['source_root']
        index=args.index(self.spec['images'][role]['tag'])
        args[index:index]=['--mount',f'type=bind,src={source},dst={source},readonly']
        return name,token,args

    def run(self):
        self.preflight()
        power=subprocess.check_output(['nvidia-smi','--query-gpu=power.limit','--format=csv,noheader,nounits'],text=True).strip()
        assert float(power)==100
        step=['python3','-B',str(self.root/'cut020_steps.py')]
        self.stage('timing_check','reconstruction',step+['probe',str(self.root)],gpu=False,timeout=900)
        scene='cuadra-'+self.assignment['block_id']
        command=['python3','-B','-m','pipeline','run','--scene',scene,
                 '--config',str(self.root/'config-clip.json'),'--stages']
        self.stage('extra_frames','reconstruction',command+['frames'],gpu=False,timeout=900)
        self.stage('extra_masks','segmentation',command+['masks'],timeout=4*3600)
        self.stage('merge_frames','reconstruction',step+['merge',str(self.root)],gpu=False,timeout=1800)
        self.stage('sfm','reconstruction',step+['sfm',str(self.root)],timeout=12*3600)
        out=self.root/'outputs'/scene/self.experiment
        models={}
        for p in sorted((out/'colmap/sparse').glob('*/images.bin')):
            with p.open('rb') as f:images=struct.unpack('<Q',f.read(8))[0]
            with (p.parent/'points3D.bin').open('rb') as f:points=struct.unpack('<Q',f.read(8))[0]
            models[p.parent.name]={'registered_images':images,'points3D':points}
        selected=(out/'colmap/best_model.txt').read_text().strip()
        assert selected in models
        self.save(state='awaiting_review',stage='sparse_review',sparse_ready=True,
                  sparse_model=str(out/'colmap/sparse'/selected),components=models,
                  registered_images=models[selected]['registered_images'],
                  review_required=True,geometry_approved=False,source_unchanged=True,
                  dense_authorized=False,mesh_authorized=False,alignment_authorized=False,
                  finished_at=time.time())


if __name__=='__main__':
    root=Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=CutWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
        signal.signal(signal.SIGINT,lambda *_:setattr(worker,'cancelled',True))
        try:worker.run()
        except BaseException as exc:
            worker.save(state='failed',error=str(exc),finished_at=time.time())
            raise
