"""Explicit horizontal-006 diagnostic: reused frames, no masks, SfM only."""
import fcntl
import json
from pathlib import Path
import signal
import struct
import sys
import time
from sparse_review_worker import SparseWorker, digest


class NoMasksWorker(SparseWorker):
    def run(self):
        self.preflight()
        config=json.loads((self.root/'config-full.json').read_text())
        assert config['masking']['enabled'] is False
        assert config['masking'].get('per_source',{})=={}
        lineage=json.loads((self.root/'frames-lineage.json').read_text())
        out=self.root/'outputs'/('cuadra-'+self.assignment['block_id'])/self.experiment
        for item in lineage['frames']:
            path=out/'frames'/item['path']
            assert path.stat().st_size==item['bytes']
            assert digest(path)==item['sha256'],'Reused frame changed'
        self.save(completed_stages=['frames'],frames_reused=True,masking_enabled=False)
        self.stage('sfm','reconstruction',
                   ['python3','-B','-m','pipeline','run','--scene','cuadra-006',
                    '--config',str(self.root/'config-full.json'),'--stages','sfm'],
                   timeout=24*3600)
        models={}
        for path in sorted((out/'colmap/sparse').glob('*/images.bin')):
            with path.open('rb') as stream:
                count=struct.unpack('<Q',stream.read(8))[0]
            with (path.parent/'points3D.bin').open('rb') as stream:
                points=struct.unpack('<Q',stream.read(8))[0]
            models[path.parent.name]={'registered_images':count,'points3D':points}
        best=(out/'colmap/best_model.txt').read_text().strip()
        assert best in models
        self.save(state='awaiting_review',stage='sparse_review',sparse_ready=True,
                  sparse_model=str(out/'colmap/sparse'/best),components=models,
                  registered_images=models[best]['registered_images'],
                  review_required=True,geometry_approved=False,
                  dense_authorized=False,mesh_authorized=False,alignment_authorized=False,
                  finished_at=time.time())


if __name__=='__main__':
    root=Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=NoMasksWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
        signal.signal(signal.SIGINT,lambda *_:setattr(worker,'cancelled',True))
        try:
            worker.run()
        except BaseException as exc:
            worker.save(state='failed',error=str(exc),finished_at=time.time())
            raise
