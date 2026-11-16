#!/usr/bin/env python3
"""Worker para videos de celular (1080p, sin SRT) reutilizando el worker certificado
de la campaña (reconstruction_worker.py, sin modificar): mismos contenedores, límites
y guardia térmica. Cambia solo la admisión (sin chequeos exclusivos de dron 4K) y las
etapas: frames -> masks -> sfm -> undistort -> dense (por lotes si >96 vistas) -> metrics.
La sparse queda lista tras 'undistort' (status: sparse_ready=true)."""
import argparse, fcntl, importlib.util, json, signal, struct, subprocess, time
from pathlib import Path

_spec = importlib.util.spec_from_file_location('rw', Path(__file__).with_name('reconstruction_worker.py'))
rw = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(rw)


class PhoneWorker(rw.Worker):
    def __init__(self, root, profile):
        super().__init__(root, profile)
        # El worker certificado fija 'barranco_4k_2fps_combined_v1'; usar el experimento de esta corrida.
        self.experiment = self.spec['full_experiment']; self.status['experiment'] = self.experiment
        # Reanudar: no repetir etapas ya completadas en una corrida anterior.
        try:
            prev = json.loads(self.status_path.read_text()).get('completed_stages', [])
        except Exception:
            prev = []
        self.status['completed_stages'] = list(prev); self.status['resumed_with'] = list(prev)

    def stage(self, stage, role, argv, **kw):
        if stage in self.status['completed_stages']:
            return
        self.command(stage, role, argv, **kw)

    def preflight(self):
        for image in self.spec['images'].values():
            got = rw.capture(['docker', 'image', 'inspect', '--format', '{{.Id}}', image['tag']]).strip()
            if got != image['id']:
                raise RuntimeError(f"Imagen distinta a la certificada: {image['tag']} {got}")
        if not rw.capture(['docker', 'info', '--format', '{{.DockerRootDir}}']).strip().startswith('/data/'):
            raise RuntimeError('Docker must store its runtime on /data')
        if rw.capture(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits']).strip():
            raise RuntimeError('Another GPU compute process is active')
        t = self.sample()
        if t['ram_available_gib'] < 40 or t['data_free_gib'] < 100 or t['root_free_gib'] < 3.75:
            raise RuntimeError('Insufficient initial memory/disk reserve')
        while t['gpu_c'] >= 65 or t['cpu_c'] >= 75 or t['ssd_c'] >= 60:
            self.save(state='waiting_cooldown'); time.sleep(30); t = self.sample()
        self.save(preflight_passed=True)

    def run(self):
        self.preflight()
        config = str(self.root / 'config-full.json')
        scene = 'cuadra-' + self.assignment['block_id']
        P = ['python3', '-B', '-m', 'pipeline', 'run', '--scene', scene, '--config', config, '--stages']
        for stage, role in [('frames', 'reconstruction'), ('masks', 'segmentation'),
                            ('sfm', 'reconstruction'), ('undistort', 'reconstruction')]:
            self.stage(stage, role, P + [stage], timeout=48 * 3600)
        out = self.root / 'outputs' / scene / self.experiment
        best = (out / 'colmap/best_model.txt').read_text().strip()
        with (out / 'colmap/sparse' / best / 'images.bin').open('rb') as f:
            registered = struct.unpack('<Q', f.read(8))[0]
        self.save(sparse_ready=True, sparse_model=str(out / 'colmap/sparse' / best), registered_images=registered)
        if registered > 96:
            self.stage('dense', 'reconstruction', ['python3', '-B', str(self.root / 'dense_batches.py'),
                                                     str(self.root), self.experiment], timeout=72 * 3600)
        else:
            self.stage('dense', 'reconstruction', P + ['dense'], timeout=48 * 3600)
        self.stage('metrics', 'reconstruction', P + ['metrics'])
        self.save(state='completed', stage='complete', finished_at=time.time())


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('root', type=Path); a = ap.parse_args()
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        w = PhoneWorker(a.root, 'full')
        def cancel(signum, frame): w.cancelled = True
        signal.signal(signal.SIGTERM, cancel); signal.signal(signal.SIGINT, cancel)
        try:
            w.run()
        except BaseException as exc:
            w.save(state='failed', error=str(exc), finished_at=time.time()); raise
