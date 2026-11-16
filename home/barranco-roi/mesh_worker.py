"""Standalone daughter worker; stdlib only, CPU-only OpenMVS, immutable sources."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback

from mvs_interface import camera_table, camera_mapping, relocate_scene


def atomic(path, value):
    temp = path.with_suffix('.json.new')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for raw in iter(lambda: f.read(8*1024**2), b''):
            h.update(raw)
    return h.hexdigest()


def temperatures():
    values = []
    for hw in Path('/sys/class/hwmon').glob('hwmon*'):
        name = hw / 'name'
        if name.exists() and name.read_text().strip() in ('coretemp','k10temp'):
            values.extend(int(p.read_text())/1000 for p in hw.glob('temp*_input'))
    return max(values, default=0)


def main(root):
    root = Path(root)
    a = json.loads((root/'assignment.json').read_text())
    roi = a['roi']
    source = Path(a['source_root'])
    runtime = root.parent/'runtime'
    state = dict(block=roi['block'], selection_id=roi['selection_id'], pid=os.getpid(), started_at=time.time())
    child = None

    def status(stage, **kwargs):
        state.update(stage=stage, updated_at=time.time(), **kwargs)
        atomic(root/'status.json', state)
        print(time.strftime('%H:%M:%S'), stage, kwargs, flush=True)

    def stop(*_):
        if child is not None and child.poll() is None:
            child.terminate()
        raise RuntimeError('Own worker was stopped')

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def run(stage, args, env=None):
        nonlocal child
        status(stage, command=list(map(str,args)))
        started = time.monotonic()
        hot_since = None
        with (root/(stage+'.log')).open('a') as log:
            child = subprocess.Popen(list(map(str,args)), cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                while child.poll() is None:
                    time.sleep(3)
                    temp = temperatures()
                    if temp >= 90:
                        hot_since = hot_since or time.monotonic()
                    else:
                        hot_since = None
                    if temp >= 95 or (hot_since and time.monotonic()-hot_since >= 30):
                        raise RuntimeError('CPU thermal limit reached')
                    if shutil.disk_usage(root).free < 50*1024**3:
                        raise RuntimeError('50 GiB disk reserve reached')
                    mem = {k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
                    if mem['MemAvailable'] < 8*1024**3:
                        raise RuntimeError('Available system RAM fell below 8 GiB')
                    if time.monotonic()-started > 4*3600:
                        raise RuntimeError('Own stage exceeded four hours')
                    status(stage, stage_seconds=round(time.monotonic()-started,1), cpu_temperature_c=temp)
                if child.returncode:
                    raise RuntimeError(stage+' failed with code '+str(child.returncode)+'; inspect '+stage+'.log')
            except BaseException:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
                raise
        state.setdefault('durations_s',{})[stage] = time.monotonic()-started
        lines = (root/(stage+'.log')).read_text().splitlines()
        return json.loads(lines[-1]) if stage != 'delaunay' else None

    try:
        status('verifying_sources')
        assert (Path.home()/(a['node_tag']+'.txt')).is_file(), 'Tag mismatch'
        assert a['mac'] in [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')], 'MAC mismatch'
        assert os.path.ismount(a['mountpoint']), 'Data volume is not mounted'
        lease = (Path(a['mountpoint'])/'photogrammetry/.lab-deploy/reconstruction.lock').open('a')
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Lock path is the mounted photogrammetry root, including /mnt/datos on 001.
        selected = (source/'colmap/best_model.txt').read_text().strip()
        for name, expected in roi['source']['sparse_hashes'].items():
            if digest(source/'colmap/sparse'/selected/name) != expected:
                raise RuntimeError('Selected sparse fingerprint mismatch: '+name)
        global_scene = source/'mvs/scene.mvs'
        global_table = camera_table(global_scene)
        batches_meta = json.loads((source/'mvs/dense-batches.json').read_text())
        if batches_meta['cloud_sha256'] != roi['source']['dense_sha256']:
            raise RuntimeError('Batch source identity differs from selected ROI')
        batches = []
        audit = []
        first = 0
        for item in batches_meta['ranges']:
            if item['first_vertex'] != first:
                raise RuntimeError('Noncontiguous dense batch ranges')
            first += item['vertices']
            chunk = source/'mvs/chunks'/Path(item['source']).parent.name
            table = camera_table(chunk/'scene_dense.mvs')
            mapping, delta = camera_mapping(global_table, table)
            # Independently compare original and densified camera membership and poses.
            dense_from_original, _ = camera_mapping(table, camera_table(chunk/'scene.mvs'))
            if dense_from_original != list(range(len(mapping))):
                raise RuntimeError('Densification reordered cameras')
            native = chunk/'scene_dense.ply'
            if not native.is_file():
                raise RuntimeError('Native visibility cloud missing: '+str(native))
            batches.append((native,item['vertices'],mapping))
            audit.append(dict(batch=chunk.name, native=str(native), vertices=item['vertices'], global_image_indices=mapping, max_pose_delta=delta))
        if first != batches_meta['vertices']:
            raise RuntimeError('Dense range total differs')
        atomic(root/'camera-audit.json', dict(global_images=len(global_table['images']), batches=audit))
        config = root/'polygon.txt'
        config.write_text(' '.join(str(v) for row in roi['world_from_block'] for v in row)+'\n'+str(len(roi['vertices']))+'\n'+'\n'.join(' '.join(map(str,p)) for p in roi['vertices'])+'\n')
        (root/'batches.txt').write_text(str(len(batches))+'\n'+'\n'.join(json.dumps(str(p))+' '+str(n)+' '+str(len(m))+' '+' '.join(map(str,m)) for p,n,m in batches)+'\n')
        # Atomic derived scene publication also repairs an interrupted preflight
        # from this campaign; sources and completed meshes are never overwritten.
        if not (root/'sampling.json').exists():
            relocate_scene(global_scene, root/'scene.mvs', global_table, source/'colmap/undistorted/images')
        tool = runtime/'mesh_roi'
        native = root/'native_10cm.ply'
        if (root/'sampling.json').exists():
            sample = json.loads((root/'sampling.json').read_text())
            if not native.is_file() or digest(native) != sample['native_sha256']:
                raise RuntimeError('Cached native sample changed')
        else:
            sample = run('sampling', [tool,'sample',config,root/'batches.txt',source/'mvs/scene_dense_scalar.ply',native])
            if sample['scalar_sha256'] != roi['source']['dense_sha256']:
                raise RuntimeError('Full scalar source SHA differs from selected ROI')
            sample.update(native_sha256=digest(native), native_bytes=native.stat().st_size)
            atomic(root/'sampling.json', sample)
        status('sample_verified', sample=sample)
        env = dict(os.environ, LD_LIBRARY_PATH=str(runtime/'openmvs/lib'), OPENBLAS_NUM_THREADS=str(a['threads']), OMP_NUM_THREADS=str(a['threads']))
        if not (root/'delaunay-complete.json').exists():
            command = [runtime/'openmvs/bin/ReconstructMesh','-w',root,'-i',root/'scene.mvs','-p',native,'-o',root/'mesh_local.ply',
                       '--cuda-device','-2','--max-threads',str(a['threads']),'--min-point-distance','0','--constant-weight','0','--decimate','1',
                       '--remove-spurious','0','--remove-spikes','0','--close-holes','0','--smooth','0','--crop-to-roi','0','--archive-type','1']
            atomic(root/'delaunay-command.json', dict(argv=list(map(str,command)),gpu=False))
            run('delaunay', command, env=env)
            atomic(root/'delaunay-complete.json',dict(completed_at=time.time()))
        world = root/('manzana_'+roi['block']+'_world.ply')
        if (root/'result.json').exists():
            result = json.loads((root/'result.json').read_text())
            if digest(world) != result['sha256']:
                raise RuntimeError('Published mesh changed')
        else:
            result = run('filtering', [tool,'finish',config,native,root/'mesh_local.ply',world])
            result.update(block=roi['block'], selection_id=roi['selection_id'], fingerprint=roi['fingerprint'], world_from_block=roi['world_from_block'],
                          mesh=str(world), bytes=world.stat().st_size, sha256=digest(world), sample=sample,
                          method='OpenMVS 2.3 Delaunay + visibility graph-cut', node_tag=a['node_tag'], gpu=False,
                          sampling_note='First original point per globally anchored 10 cm voxel; original view weights retained and camera IDs remapped.',
                          durations_s=state.get('durations_s',{}), created_at=time.time())
            atomic(root/'result.json', result)
        status('completed', result=result, total_seconds=time.time()-state['started_at'])
    except BaseException as exc:
        status('failed', error=str(exc))
        traceback.print_exc()
        raise


if __name__ == '__main__':
    main(sys.argv[1])
