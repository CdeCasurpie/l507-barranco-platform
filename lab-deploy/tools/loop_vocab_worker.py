"""Isolated 2-fps vocabulary-loop experiment; certified thermal supervisor."""
import fcntl
import json
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
from sparse_review_worker import SparseWorker, digest


class LoopVocabWorker(SparseWorker):
    def docker_args(self, stage, role, argv, gpu=True):
        name, token, args = super().docker_args(stage, role, argv, gpu)
        index = args.index(self.spec['images'][role]['tag'])
        out = self.root/'outputs'/('cuadra-'+self.assignment['block_id'])/self.experiment
        for path in [out/'frames', out/'masks', self.root/'datasets',
                     self.root/'vocab_tree_flickr100K_words32K.bin']:
            args[index:index] = ['--mount', f'type=bind,src={path},dst={path},readonly']
            index += 2
        return name, token, args

    def run(self):
        self.preflight()
        inventory = json.loads((self.root/'reused-inputs.json').read_text())
        out = self.root/'outputs'/('cuadra-'+self.assignment['block_id'])/self.experiment
        for name, entry in inventory.items():
            assert digest(out/name) == entry['sha256'], 'Reused input changed: '+name
        assert float(subprocess.check_output(
            ['nvidia-smi', '--query-gpu=power.limit', '--format=csv,noheader,nounits'],
            text=True).strip()) == 100
        tree = self.root/'vocab_tree_flickr100K_words32K.bin'
        assert digest(tree) == self.spec['vocabulary']['sha256']
        cfg = json.loads((self.root/'config-full.json').read_text())
        assert cfg['frames']['fps'] == 2
        assert cfg['colmap']['matcher']['loop_detection'] is True
        scene = 'cuadra-'+self.assignment['block_id']
        self.save(reused_source_stages=['frames', 'masks'], vocabulary=self.spec['vocabulary'])
        self.stage('sfm', 'reconstruction', [
            'python3', '-B', str(self.root/'sparse_loop_overlay.py'), 'run',
            '--scene', scene, '--config', str(self.root/'config-full.json'),
            '--stages', 'sfm'], timeout=12*3600)
        out = self.root/'outputs'/scene/self.experiment
        models = {}
        for p in sorted((out/'colmap/sparse').glob('*/images.bin')):
            with p.open('rb') as stream:
                images, = struct.unpack('<Q', stream.read(8))
            with (p.parent/'points3D.bin').open('rb') as stream:
                points, = struct.unpack('<Q', stream.read(8))
            models[p.parent.name] = dict(registered_images=images, points3D=points)
        best = (out/'colmap/best_model.txt').read_text().strip()
        assert best in models
        self.save(state='awaiting_review', stage='sparse_review', sparse_ready=True,
                  sparse_model=str(out/'colmap/sparse'/best), components=models,
                  registered_images=models[best]['registered_images'],
                  review_required=True, geometry_approved=False, dense_authorized=False,
                  mesh_authorized=False, alignment_authorized=False, finished_at=time.time())


if __name__ == '__main__':
    root = Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        worker = LoopVocabWorker(root, 'full')
        signal.signal(signal.SIGTERM, lambda *_: setattr(worker, 'cancelled', True))
        signal.signal(signal.SIGINT, lambda *_: setattr(worker, 'cancelled', True))
        try:
            worker.run()
        except BaseException as error:
            worker.save(state='failed', error=str(error), finished_at=time.time())
            raise
