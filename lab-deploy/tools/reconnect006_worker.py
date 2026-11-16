"""Bounded COLMAP bridge matching on a derived database; no dense or mesh."""
import fcntl
import json
import math
from pathlib import Path
import signal
import sqlite3
import struct
import sys

from phone_worker import PhoneWorker


def image_names(path):
    result = {}
    with path.open('rb') as f:
        count, = struct.unpack('<Q', f.read(8))
        for _ in range(count):
            data = struct.unpack('<i7di', f.read(64))
            name = bytearray()
            while True:
                char = f.read(1)
                if not char:
                    raise ValueError('Truncated image name')
                if char == b'\0':
                    break
                name.extend(char)
            size, = struct.unpack('<Q', f.read(8))
            f.seek(size * 24, 1)
            result[data[0]] = name.decode()
    return result


def sample(values, budget):
    values = sorted(values)
    if len(values) <= budget:
        return values
    return [values[round(i * (len(values)-1)/(budget-1))] for i in range(budget)]


class BridgeWorker(PhoneWorker):
    def docker_args(self, stage, role, argv, gpu=True):
        name, token, args = super().docker_args(stage, role, argv, gpu)
        source = self.spec['bridge_source']
        index = args.index(self.spec['images'][role]['tag'])
        args[index:index] = ['--mount', f'type=bind,src={source},dst={source},readonly']
        return name, token, args

    def run(self):
        self.preflight()
        a = self.assignment
        assert (Path.home()/(a['node_tag']+'.txt')).is_file()
        assert a['mac'] in [p.read_text().strip() for p in Path('/sys/class/net').glob('*/address')]
        source = Path(self.spec['bridge_source'])
        selected = (source/'colmap/best_model.txt').read_text().strip()
        assert selected.isdigit()
        destination = self.root/'outputs'/('cuadra-'+a['block_id'])/self.experiment
        colmap = destination/'colmap'
        colmap.mkdir(parents=True, exist_ok=True)
        database = colmap/'database.db'
        if database.exists():
            raise RuntimeError('Derived DB already exists; explicit new attempt required')
        source_db = source/'colmap/database.db'
        assert not Path(str(source_db)+'-wal').exists() or Path(str(source_db)+'-wal').stat().st_size == 0
        with sqlite3.connect(source_db.as_uri()+'?mode=ro', uri=True) as src:
            with sqlite3.connect(database) as dst:
                src.backup(dst)
        groups = {p.name: image_names(p/'images.bin')
                  for p in (source/'colmap/sparse').iterdir()
                  if p.is_dir() and (p/'images.bin').is_file()}
        with sqlite3.connect(database) as db:
            names = dict(db.execute('SELECT image_id,name FROM images'))
            before = db.execute('SELECT COUNT(*) FROM two_view_geometries WHERE rows>0').fetchone()[0]
        seen = set()
        pairs = set()
        keyframes = {}
        for model, images in groups.items():
            seen.update(images)
            keyframes[model] = sample(images.values(), 96 if model == selected else 32)
        models = sorted(groups)
        for i, left in enumerate(models):
            for right in models[i+1:]:
                for x in keyframes[left]:
                    for y in keyframes[right]:
                        if x != y:
                            pairs.add(tuple(sorted((x, y))))
        registered_names = {name for images in groups.values() for name in images.values()}
        missing = sample(set(names.values())-registered_names, 32)
        for x in missing:
            for values in keyframes.values():
                for y in values:
                    pairs.add(tuple(sorted((x, y))))
        # Also bridge component boundaries using temporal proximity.
        ordered = sorted(names.values())
        membership = {}
        for model, images in groups.items():
            for name in images.values():
                membership.setdefault(name, set()).add(model)
        for i, x in enumerate(ordered):
            for y in ordered[i+1:i+41]:
                if membership.get(x, set()).isdisjoint(membership.get(y, set())):
                    pairs.add((x, y))
        assert len(pairs) <= 100_000, 'Pair budget exceeded'
        assert all(' ' not in x and '\n' not in x for pair in pairs for x in pair)
        pairfile = self.root/'bridge-pairs.txt'
        pairfile.write_text(''.join(x+' '+y+'\n' for x,y in sorted(pairs)))
        self.save(bridge_pairs=len(pairs), original_components={k:len(v) for k,v in groups.items()},
                  source_model=selected, source_registered=len(groups[selected]),
                  dense_requires_regeneration=True)
        self.command('bridge-matching', 'reconstruction', [
            'colmap','matches_importer','--database_path',str(database),
            '--match_list_path',str(pairfile),'--match_type','pairs',
            '--SiftMatching.use_gpu','1','--SiftMatching.num_threads','4'], timeout=6*3600)
        with sqlite3.connect(database) as db:
            after = db.execute('SELECT COUNT(*) FROM two_view_geometries WHERE rows>0').fetchone()[0]
        output = colmap/'sparse'
        output.mkdir()
        self.command('bridge-mapping', 'reconstruction', [
            'colmap','mapper','--database_path',str(database),
            '--image_path',str(source/'frames'),'--input_path',str(source/'colmap/sparse'/selected),
            '--output_path',str(output),'--Mapper.fix_existing_images','1',
            '--Mapper.multiple_models','0','--Mapper.num_threads','4',
            '--Mapper.ba_refine_focal_length','0','--Mapper.ba_refine_principal_point','0',
            '--Mapper.ba_refine_extra_params','0'], gpu=False, timeout=12*3600)
        outputs = {p.name: image_names(p/'images.bin') for p in output.iterdir()
                   if p.is_dir() and (p/'images.bin').is_file()}
        if not outputs:
            raise RuntimeError('No derived model published')
        best = max(outputs, key=lambda k:len(outputs[k]))
        (colmap/'best_model.txt').write_text(best+'\n')
        added = set(outputs[best])-set(groups[selected])
        report = {'source_components':{k:len(v) for k,v in groups.items()},
                  'registered_images':len(outputs[best]), 'total_images':len(names),
                  'registration_ratio':len(outputs[best])/len(names),
                  'added_images':len(added),'verified_pair_count_before':before,
                  'verified_pair_count_after':after,'candidate_pairs':len(pairs),
                  'coverage_per_original_component':{
                      k:len(set(v)&set(outputs[best])) for k,v in groups.items()},
                  'manual_acceptance_required':True,'source_unchanged':True,
                  'dense_requires_regeneration':True}
        (destination/'metrics').mkdir()
        (destination/'metrics/bridge-report.json').write_text(json.dumps(report,indent=2))
        self.save(state='awaiting_review',stage='bridge_complete',sparse_ready=True,
                  registered_images=len(outputs[best]),bridge_report=report,
                  mesh_authorized=False,alignment_authorized=False)


if __name__ == '__main__':
    root = Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        worker = BridgeWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(worker,'cancelled',True))
        try:
            worker.run()
        except BaseException as exc:
            worker.save(state='failed',error=str(exc))
            raise
