"""One bounded reconstruction per daughter, supervised outside its containers."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time

GIB = 1024**3


def atomic(path, value):
    temporary = path.with_name('.' + path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    os.replace(temporary, path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024**2), b''):
            h.update(block)
    return h.hexdigest()


def capture(argv, timeout=30):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if p.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, argv)) + ': ' + p.stderr[-1500:])
    return p.stdout


def telemetry(root):
    fields = capture(['nvidia-smi', '--query-gpu=temperature.gpu,memory.used,memory.total,power.draw,power.limit,utilization.gpu',
                      '--format=csv,noheader,nounits']).strip().splitlines()
    if len(fields) != 1:
        raise RuntimeError('Expected exactly one GPU')
    t, used, total, power, power_limit, busy = map(float, fields[0].split(','))
    memory = dict(line.split(':', 1) for line in Path('/proc/meminfo').read_text().splitlines())
    cpu, ssd = [], []
    for hw in Path('/sys/class/hwmon').glob('hwmon*'):
        if not (hw / 'name').exists():
            continue
        name = (hw / 'name').read_text().strip()
        if name in ['coretemp', 'k10temp']:
            cpu.extend(int(p.read_text()) / 1000 for p in hw.glob('temp*_input'))
        elif name == 'nvme':
            for p in hw.glob('temp*_input'):
                label = p.with_name(p.name.replace('_input', '_label'))
                if label.exists() and label.read_text().strip() == 'Composite':
                    ssd.append(int(p.read_text()) / 1000)
    if not cpu or not ssd:
        raise RuntimeError('CPU or SSD thermal sensors unavailable')
    if not os.path.ismount('/data') or root.stat().st_dev != Path('/data').stat().st_dev:
        raise RuntimeError('Required data mount disappeared or changed')
    result = {'at': time.time(), 'gpu_c': t, 'cpu_c': max(cpu), 'ssd_c': max(ssd),
              'ram_available_gib': int(memory['MemAvailable'].strip().split()[0]) / 1024**2,
              'root_free_gib': shutil.disk_usage('/').free / GIB,
              'data_free_gib': shutil.disk_usage(root).free / GIB,
              'vram_used_mib': used, 'vram_total_mib': total, 'gpu_w': power,
              'gpu_power_limit_w': power_limit, 'gpu_busy': busy}
    if not all(math.isfinite(v) for v in result.values()):
        raise RuntimeError('Invalid telemetry')
    return result


class Guard:
    """Operating thresholds, independent of vendor thermal shutdown limits."""
    def __init__(self):
        self.since = {}

    def evaluate(self, values, now):
        immediate = [('gpu_c', 85, False), ('cpu_c', 95, False), ('ssd_c', 80, False),
                     ('root_free_gib', 3, True), ('data_free_gib', 50, True)]
        for name, bound, below in immediate:
            if (values[name] < bound) if below else (values[name] >= bound):
                raise RuntimeError(f'SAFETY STOP: {name}={values[name]:.2f}, boundary={bound}')
        sustained = [('gpu_c', 80, False), ('cpu_c', 90, False), ('ssd_c', 70, False),
                     ('ram_available_gib', 8, True)]
        for name, bound, below in sustained:
            active = values[name] < bound if below else values[name] >= bound
            if active:
                self.since.setdefault(name, now)
                if now - self.since[name] >= 30:
                    raise RuntimeError(f'SAFETY STOP: sustained {name}={values[name]:.2f}')
            else:
                self.since.pop(name, None)
        warnings = []
        for name, bound, below in [('gpu_c',75,False),('cpu_c',85,False),('ssd_c',65,False),
                                 ('root_free_gib',3.5,True),('data_free_gib',75,True),('ram_available_gib',10,True)]:
            if (values[name] < bound) if below else (values[name] >= bound):
                warnings.append(name)
        return warnings


class Worker:
    def __init__(self, root, profile):
        self.root = root.resolve()
        self.spec = json.loads((root / 'reconstruction.json').read_text())
        self.assignment = json.loads((root / 'assignment.json').read_text())
        self.profile = profile
        self.experiment = 'barranco_4k_diagnostic_v1' if profile == 'diagnostic' else 'barranco_4k_2fps_combined_v1'
        self.status_path = root / ('reconstruction-' + profile + '-status.json')
        self.status = {'node_tag': self.assignment['node_tag'], 'block_id': self.assignment['block_id'],
                       'experiment': self.experiment, 'profile': profile, 'pid': os.getpid(),
                       'state': 'starting', 'started_at': time.time(), 'completed_stages': [], 'peaks': {},
                       'execution_spec':self.spec}
        self.guard = Guard()
        self.container = None
        self.cancelled = False
        self.log_dir = root / 'logs/reconstruction' / profile
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.last_telemetry = 0

    def save(self, **values):
        self.status.update(values, updated_at=time.time())
        atomic(self.status_path, self.status)

    def sample(self):
        t = telemetry(self.root)
        warnings = self.guard.evaluate(t, time.monotonic())
        peaks = self.status['peaks']
        for key in ['gpu_c','cpu_c','ssd_c','vram_used_mib','gpu_w']:
            peaks[key] = max(peaks.get(key, 0), t[key])
        for key in ['root_free_gib','data_free_gib','ram_available_gib']:
            peaks['min_' + key] = min(peaks.get('min_' + key, t[key]), t[key])
        path = self.log_dir / 'telemetry.jsonl'
        if path.exists() and path.stat().st_size > 5 * 1024**2:
            for n in range(3, 0, -1):
                old = path.with_name(path.name + '.' + str(n))
                if old.exists():
                    if n == 3: old.unlink()
                    else: os.replace(old, path.with_name(path.name + '.' + str(n+1)))
            os.replace(path, path.with_name(path.name + '.1'))
        with path.open('a') as f:
            f.write(json.dumps(t) + '\n')
        self.save(telemetry=t, warnings=warnings)
        return t

    def preflight(self):
        a = self.assignment
        if digest(self.root/'reconstruction_worker.py') != self.spec['worker_sha256'] or digest(self.root/'campaign_post.py') != self.spec['post_sha256']:
            raise RuntimeError('Execution bundle differs from its recorded fingerprint')
        if digest(self.root/'dense_batches.py') != self.spec['dense_batches_sha256']:
            raise RuntimeError('Dense batch engine differs from its recorded fingerprint')
        if not (Path.home() / (a['node_tag'] + '.txt')).is_file():
            raise RuntimeError('Tag mismatch')
        macs = [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')]
        if a['mac'] not in macs:
            raise RuntimeError('MAC mismatch')
        current = json.loads(Path('/var/lib/lab-deploy/active.json').read_text())
        if current['code_root'] != self.spec['code_root'] or current['data_root'] != self.spec['certified_data_root']:
            raise RuntimeError('Certified active release changed')
        if capture(['git','-C',self.spec['code_root'],'rev-parse','HEAD']).strip() != self.spec['pipeline_commit']:
            raise RuntimeError('Code commit mismatch')
        if capture(['git','-C',self.spec['code_root'],'status','--porcelain']).strip():
            raise RuntimeError('Certified checkout is not clean')
        if not capture(['docker','info','--format','{{.DockerRootDir}}']).strip().startswith('/data/'):
            raise RuntimeError('Docker must store its runtime on /data')
        for image in self.spec['images'].values():
            if capture(['docker','image','inspect','--format','{{.Id}}',image['tag']]).strip() != image['id']:
                raise RuntimeError('Certified image mismatch')
        if capture(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits']).strip():
            raise RuntimeError('Another GPU compute process is active')
        t = self.sample()
        if t['ram_available_gib'] < 52 or t['data_free_gib'] < 100 or t['root_free_gib'] < 3.75:
            raise RuntimeError('Insufficient initial memory/disk reserve')
        if t['gpu_c'] >= 65 or t['cpu_c'] >= 75 or t['ssd_c'] >= 60:
            raise RuntimeError('Hardware not cool enough for initial admission')
        for f in a['files']:
            p = self.root / f['relative_path']
            receipt = json.loads(p.with_name(p.name + '.fetch.json').read_text())
            if p.stat().st_size != f['bytes'] or digest(p) != receipt['sha256']:
                raise RuntimeError('Input integrity mismatch: ' + f['name'])
        self.save(preflight_passed=True)

    def docker_args(self, stage, role, argv, gpu=True):
        token = hashlib.sha256((str(self.root) + self.profile).encode()).hexdigest()[:12]
        name = 'barranco-' + token + '-' + stage.replace('_','-')
        image = self.spec['images'][role]
        args = ['docker','run','--rm','--pull=never','--name',name,
                '--label','photogrammetry.campaign=barranco-full-v1',
                '--label','photogrammetry.run='+token,'--label','photogrammetry.block='+self.assignment['block_id'],
                '--cpus',str(self.spec['resource_limits']['cpus']),'--memory','40g','--memory-swap','40g','--pids-limit','1024',
                '--shm-size','1g','--ulimit','nofile=8192:8192','--network','none',
                '--read-only','--cap-drop','ALL','--security-opt','no-new-privileges=true',
                '--log-driver','local','--log-opt','max-size=10m','--log-opt','max-file=3',
                '--init','--user',f'{os.getuid()}:{os.getgid()}','--entrypoint','/usr/bin/env',
                '--mount',f'type=bind,src={self.root},dst={self.root}',
                '--mount',f'type=bind,src={self.spec["code_root"]},dst=/work,readonly',
                '--mount',f'type=bind,src={self.spec["certified_data_root"]}/models,dst=/models,readonly',
                '--mount',f'type=bind,src={self.root}/scratch/tmp,dst=/tmp','-w','/work']
        if gpu:
            args += ['--gpus','all']
        environment = {'PG_DATA_ROOT':str(self.root),'PG_NODE_TAG':self.assignment['node_tag'],
                       'PG_MIN_FREE_GIB':'50','PG_IMAGE_ID':image['id'],'PG_RUN_ROLE':role,
                       'PG_RECON_IMAGE_ID':self.spec['images']['reconstruction']['id'],
                       'PG_SEG_IMAGE_ID':self.spec['images']['segmentation']['id'],
                       'HOME':'/tmp/home','TMPDIR':str(self.root/'scratch/tmp'),
                       'XDG_CACHE_HOME':str(self.root/'scratch/cache'),'HF_HOME':str(self.root/'scratch/hf'),
                       'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','PYTHONDONTWRITEBYTECODE':'1',
                       'PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':str(self.spec['resource_limits']['cpus']),
                       'OPENBLAS_NUM_THREADS':str(self.spec['resource_limits']['cpus']),
                       'MKL_NUM_THREADS':str(self.spec['resource_limits']['cpus']),
                       'NUMEXPR_NUM_THREADS':str(self.spec['resource_limits']['cpus']),'NVIDIA_DRIVER_CAPABILITIES':'compute,utility'}
        for key,value in environment.items():
            args += ['-e',key+'='+value]
        args += [image['tag'],*argv]
        return name, token, args

    def stop_owned(self, name, token):
        p = subprocess.run(['docker','inspect','--format','{{json .Config.Labels}}',name],capture_output=True,text=True,timeout=15)
        if p.returncode:
            return
        labels = json.loads(p.stdout)
        if labels.get('photogrammetry.run') != token or labels.get('photogrammetry.campaign') != 'barranco-full-v1':
            raise RuntimeError('Refusing to stop a container not owned by this run')
        subprocess.run(['docker','stop','--time','15',name],capture_output=True,timeout=30)

    def command(self, stage, role, argv, timeout=24*3600, gpu=True):
        self.sample()
        name, token, args = self.docker_args(stage, role, argv, gpu)
        # Do not adopt or kill an orphan automatically.
        existing = subprocess.run(['docker','inspect',name],capture_output=True)
        if existing.returncode == 0:
            raise RuntimeError('Existing container requires explicit reconciliation: ' + name)
        self.save(state='running', stage=stage, container=name, command=argv, stage_started_at=time.time())
        started = time.monotonic()
        log_path = self.log_dir / (stage + '.log')
        with log_path.open('ab') as log:
            p = subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            self.container = (name,token)
            misses = 0
            try:
                while p.poll() is None:
                    time.sleep(5)
                    if self.cancelled:
                        raise RuntimeError('Operator cancellation')
                    if time.monotonic() - started > timeout:
                        raise RuntimeError('Stage time budget exceeded')
                    try:
                        self.sample()
                        misses = 0
                    except RuntimeError:
                        raise
                    except Exception as exc:
                        misses += 1
                        if misses >= 3:
                            raise RuntimeError('Telemetry lost: ' + str(exc)) from exc
                if p.returncode:
                    raise RuntimeError(f'{stage} exited {p.returncode}; see {log_path}')
            except BaseException:
                self.stop_owned(name,token)
                try: p.wait(timeout=30)
                except subprocess.TimeoutExpired: p.terminate();p.wait(timeout=10)
                raise
            finally:
                self.container = None
        self.status['completed_stages'].append(stage)
        self.save(last_stage_seconds=time.monotonic()-started)

    def run(self):
        self.preflight()
        config = str(self.root / ('config-' + self.profile + '.json'))
        scene = 'cuadra-' + self.assignment['block_id']
        for name,role,profile in [('doctor-dense','reconstruction','dense'),('doctor-masks','segmentation','segmentation')]:
            self.command(name,role,['python3','-B','-m','pipeline','doctor','--profile',profile,'--scene',scene,'--config',config,'--json'],timeout=600)
        self.command('frames','reconstruction',['python3','-B','-m','pipeline','run','--scene',scene,'--config',config,'--stages','frames,telemetry'])
        post = [str(self.root/'campaign_post.py'),str(self.root),self.experiment]
        self.command('catalog','reconstruction',['python3','-B',*post,'catalog'])
        for stage,role in [('masks','segmentation'),('sfm','reconstruction'),('undistort','reconstruction'),('dense','reconstruction')]:
            batched=False
            if stage=='dense':
                import struct
                out=self.root/'outputs'/scene/self.experiment
                selected=(out/'colmap/best_model.txt').read_text().strip()
                with (out/'colmap/sparse'/selected/'images.bin').open('rb') as f:
                    registered=struct.unpack('<Q',f.read(8))[0]
                batched=registered>96
            if batched:
                self.command(stage,role,['python3','-B',str(self.root/'dense_batches.py'),str(self.root),self.experiment],timeout=72*3600)
            else:
                self.command(stage,role,['python3','-B','-m','pipeline','run','--scene',scene,'--config',config,'--stages',stage],timeout=48*3600)
        self.command('metrics','reconstruction',['python3','-B','-m','pipeline','run','--scene',scene,'--config',config,'--stages','metrics'])
        self.command('validate','reconstruction',['python3','-B',*post,'validate'])
        quality=json.loads((self.root/'outputs'/scene/self.experiment/'campaign-quality.json').read_text())
        self.save(state='completed' if quality['complete'] else 'partial',stage='complete',quality=quality,finished_at=time.time())


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('root',type=Path);parser.add_argument('--profile',choices=['diagnostic','full'],default='full')
    parser.add_argument('--preflight',action='store_true')
    args=parser.parse_args()
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
        fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker=Worker(args.root,args.profile)
        if args.preflight:
            worker.status_path=args.root/'reconstruction-preflight-status.json'
        def cancel(signum,frame):worker.cancelled=True
        signal.signal(signal.SIGTERM,cancel);signal.signal(signal.SIGINT,cancel)
        try:
            if args.preflight:
                worker.preflight();worker.save(state='prepared',finished_at=time.time())
            else:worker.run()
        except BaseException as exc:
            worker.save(state='failed',error=str(exc),finished_at=time.time())
            raise
