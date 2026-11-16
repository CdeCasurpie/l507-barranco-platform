"""Resume park rectification/dense with bounded mask-map cache, isolated per job."""
import base64
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_experiments as control

RUNNER = '''
"""Per-process overlay: only mask cache lifetime changes, not projection math."""
import hashlib,importlib.util,json,runpy,sys
from pathlib import Path
root=Path(__file__).resolve().parent
patch=root/'mask_geometry_bounded.py'
receipt=json.loads((root/'mask-memory-patch.json').read_text())
assert hashlib.sha256(patch.read_bytes()).hexdigest()==receipt['patched_sha256']
sys.path.insert(0,'/work')
import pipeline
name='pipeline.mask_geometry'
spec=importlib.util.spec_from_file_location(name,patch)
module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module)
sys.argv=['pipeline',*sys.argv[1:]]
runpy.run_module('pipeline',run_name='__main__')
'''

WORKER = '''
import fcntl,json,signal,sys
from pathlib import Path
from review_worker import ReviewWorker
class RecoveryWorker(ReviewWorker):
    def command(self,stage,role,argv,**kwargs):
        if argv[:4]==['python3','-B','-m','pipeline']:
            argv=['python3','-B',str(self.root/'pipeline_bounded.py'),*argv[4:]]
        return super().command(stage,role,argv,**kwargs)
if __name__=='__main__':
    root=Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        w=RecoveryWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(w,'cancelled',True))
        try:w.run()
        except BaseException as e:
            w.save(state='failed',error=str(e));raise
'''


def bounded_source(source):
    needle = '        if key not in cache:\n            cache[key] = sampling_map(camera, out_camera)'
    replacement = ('        if key not in cache:\n'
                   '            if len(cache) >= 2:\n'
                   '                cache.clear()\n'
                   '            cache[key] = sampling_map(camera, out_camera)')
    assert source.count(needle) == 1, 'Unexpected certified source; review required'
    patched = source.replace(needle, replacement)
    compile(patched, '<bounded-mask-geometry>', 'exec')
    return patched


def prepare():
    assignment = next(a for a in json.loads((control.STATE/'assignments.json').read_text())['assignments']
                      if a['node_tag'] == 'L507_019')
    facts = control.remote(assignment, '''
import pathlib,json
root=pathlib.Path(ROOT)
spec=json.loads((root/'reconstruction.json').read_text())
path=pathlib.Path(spec['code_root'])/'pipeline/mask_geometry.py'
print('REVIEW_REPLY='+json.dumps({'path':str(path),'source':path.read_text()}))
'''.replace('ROOT', repr(assignment['work_root'])))
    patched = bounded_source(facts['source'])
    receipt = {'source':facts['path'],
               'original_sha256':hashlib.sha256(facts['source'].encode()).hexdigest(),
               'patched_sha256':hashlib.sha256(patched.encode()).hexdigest(),
               'max_cached_camera_maps':2, 'projection_math_unchanged':True}
    payload = base64.b64encode(json.dumps({
        'assignment':assignment,'patch':patched,'receipt':receipt,
        'runner':RUNNER,'worker':WORKER}).encode()).decode()
    code = '''
import base64,hashlib,json,pathlib,shutil,time
p=json.loads(base64.b64decode(PAYLOAD));a=p['assignment'];root=pathlib.Path(a['work_root'])
assert (pathlib.Path.home()/'L507_019.txt').is_file()
assert a['mac'] in [q.read_text().strip() for q in pathlib.Path('/sys/class/net').glob('*/address')]
status=json.loads((root/'reconstruction-full-status.json').read_text())
assert status['state']=='failed' and status['stage']=='undistort'
assert all(s in status['completed_stages'] for s in ('frames','masks','sfm'))
history=root/'attempt-history'/('mask-memory-'+str(time.time_ns()));history.mkdir(parents=True)
shutil.copy2(root/'reconstruction-full-status.json',history/'reconstruction-full-status.json')
shutil.copy2(root/'review-worker.log',history/'review-worker.log')
spec=json.loads((root/'reconstruction.json').read_text())
original=pathlib.Path(spec['code_root'])/'pipeline/mask_geometry.py'
assert hashlib.sha256(original.read_bytes()).hexdigest()==p['receipt']['original_sha256']
for name,text in [('mask_geometry_bounded.py',p['patch']),('pipeline_bounded.py',p['runner']),('park_recovery_worker.py',p['worker'])]:
 q=root/name
 if q.exists() and q.read_text()!=text:
  assert name=='pipeline_bounded.py','Existing worker differs; explicit review required'
  shutil.copy2(q,history/name);q.write_text(text)
 else:q.write_text(text)
(root/'mask-memory-patch.json').write_text(json.dumps(p['receipt'],indent=2))
print('REVIEW_REPLY='+json.dumps({'prepared':True,'root':str(root),'history':str(history),'receipt':p['receipt']}))
'''.replace('PAYLOAD', repr(payload))
    result = control.remote(assignment,code)
    print(json.dumps(result,indent=2))
    return assignment


def start():
    a = next(a for a in json.loads((control.STATE/'assignments.json').read_text())['assignments']
             if a['node_tag']=='L507_019')
    code = '''
import pathlib,json,subprocess
root=pathlib.Path(ROOT)
assert (pathlib.Path.home()/'L507_019.txt').is_file()
status=json.loads((root/'reconstruction-full-status.json').read_text())
assert status['state']=='failed' and status['stage']=='undistort'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
with (root/'review-worker.log').open('a') as log:
 p=subprocess.Popen(['python3','-B','-u',str(root/'park_recovery_worker.py'),str(root)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('REVIEW_REPLY='+json.dumps({'state':'starting','pid':p.pid,'root':str(root),'recovery':'bounded mask cache'}))
'''.replace('ROOT',repr(a['work_root']))
    result = control.remote(a,code)
    path = control.STATE/'reconstruction-launch.json'
    launches = json.loads(path.read_text())
    launches[a['node_tag']] = result
    path.write_text(json.dumps(launches,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    if '--start' in sys.argv:
        start()
    else:
        prepare()
