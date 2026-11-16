"""Approved isolated horizontal-only 006 run; stop at sparse for visual review."""
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_experiments as control

WORKER = '''
import fcntl,json,signal,struct,sys,time,hashlib
from pathlib import Path
from phone_worker import PhoneWorker
class HorizontalWorker(PhoneWorker):
    def preflight(self):
        assert self.assignment['node_tag']=='L507_010'
        assert (Path.home()/'L507_010.txt').is_file()
        assert self.assignment['mac'] in [p.read_text().strip() for p in Path('/sys/class/net').glob('*/address')]
        assert len(self.assignment['files'])==1
        item=self.assignment['files'][0]
        assert item['name']=='manzana_06.mp4'
        path=self.root/item['relative_path']
        receipt=json.loads(path.with_name(path.name+'.fetch.json').read_text())
        assert path.stat().st_size==item['bytes'] and receipt['drive_file_id']==item['id']
        h=hashlib.sha256()
        with path.open('rb') as f:
            for b in iter(lambda:f.read(4194304),b''):h.update(b)
        assert h.hexdigest()==receipt['sha256']
        super().preflight()
    def run(self):
        self.preflight()
        scene='cuadra-006'
        command=['python3','-B','-m','pipeline','run','--scene',scene,'--config',str(self.root/'config-full.json'),'--stages']
        for stage,role in [('frames','reconstruction'),('masks','segmentation'),('sfm','reconstruction')]:
            self.stage(stage,role,command+[stage],timeout=48*3600)
        out=self.root/'outputs'/scene/self.experiment
        selected=(out/'colmap/best_model.txt').read_text().strip()
        assert selected.isdigit()
        models={}
        for p in (out/'colmap/sparse').glob('*/images.bin'):
            with p.open('rb') as f:models[p.parent.name]=struct.unpack('<Q',f.read(8))[0]
        assert selected in models
        self.save(state='awaiting_review',stage='sparse_review',sparse_ready=True,
                  sparse_model=str(out/'colmap/sparse'/selected),registered_images=models[selected],
                  components=models,review_required=True,dense_authorized=False,
                  alignment_authorized=False,mesh_authorized=False,finished_at=time.time())
if __name__=='__main__':
    root=Path(sys.argv[1])
    with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        w=HorizontalWorker(root,'full')
        signal.signal(signal.SIGTERM,lambda *_:setattr(w,'cancelled',True))
        signal.signal(signal.SIGINT,lambda *_:setattr(w,'cancelled',True))
        try:w.run()
        except BaseException as exc:
            w.save(state='failed',error=str(exc),finished_at=time.time());raise
'''


def main():
    source = next(a for a in json.loads((control.STATE/'assignments.json').read_text())['assignments']
                  if a['node_tag'] == 'L507_010')
    assignment = copy.deepcopy(source)
    assignment.update(campaign_id='barranco-006-horizontal-20261115', variant='horizontal-sequential',
                      work_root='/data/photogrammetry/campaigns/barranco-006-horizontal-20261115/cuadra-006')
    assignment['files'] = [f for f in source['files'] if f['name'] == 'manzana_06.mp4']
    assert len(assignment['files']) == 1
    folder = control.STATE.parent/assignment['campaign_id']
    folder.mkdir(exist_ok=True)
    (folder/'known_hosts').write_bytes((control.STATE/'known_hosts').read_bytes())
    bundle = {'campaign_id':assignment['campaign_id'], 'assignments':[assignment]}
    path = folder/'assignments.json'
    if path.exists():
        assert json.loads(path.read_text()) == bundle
    else:
        path.write_text(json.dumps(bundle,indent=2))
    files = {'horizontal_worker.py':WORKER,
             'phone_worker.py':Path('/home/exitoso/phone-run/phone_worker.py').read_text(),
             'reconstruction_worker.py':Path(__file__).with_name('reconstruction_worker.py').read_text()}
    config = json.loads(Path('/home/exitoso/phone-run/m3/006/config-full.json').read_text())
    experiment = 'phone_native_2fps_horizontal_sequential_review_v1'
    root = assignment['work_root']
    config['experiment'] = {'name':experiment,'notes':'Horizontal manzana_06 only; stop at sparse; explicit review before dense'}
    config['paths'] = {'raw_root':root+'/datasets/raw','output_root':root+'/outputs'}
    config['frames'].update(fps=2,resize=None,start=None,end=None)
    config['telemetry'] = {'enabled':False}
    config['colmap']['single_camera_per_source'] = True
    config['colmap']['matcher'].update(methods=['sequential'],sequential_overlap=10,loop_detection=False,vocab_tree_path=None)
    for stage in ('mesh','refine','clean','texture'):
        config['openmvs'][stage]['enabled'] = False
    payload = base64.b64encode(json.dumps({'assignment':assignment,'source':source,
        'files':files,'config':config,'experiment':experiment,
        'worker_sha256':hashlib.sha256(files['reconstruction_worker.py'].encode()).hexdigest()}).encode()).decode()
    code = '''
import base64,json,pathlib,os,hashlib,subprocess,fcntl
p=json.loads(base64.b64decode(PAYLOAD));a=p['assignment']
assert (pathlib.Path.home()/'L507_010.txt').is_file()
assert a['mac'] in [q.read_text().strip() for q in pathlib.Path('/sys/class/net').glob('*/address')]
assert os.path.ismount('/data')
root=pathlib.Path(a['work_root']);assert not root.exists(),'Do not overwrite an existing attempt'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
with pathlib.Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('r') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
source=pathlib.Path(p['source']['work_root']);item=a['files'][0];video=source/item['relative_path']
receipt=json.loads(video.with_name(video.name+'.fetch.json').read_text())
assert receipt['drive_file_id']==item['id'] and video.stat().st_size==item['bytes']
h=hashlib.sha256()
with video.open('rb') as f:
 for b in iter(lambda:f.read(4194304),b''):h.update(b)
assert h.hexdigest()==receipt['sha256']
template=pathlib.Path('/data/photogrammetry/campaigns/barranco-single006-sequential-20261115/cuadra-006')
spec=json.loads((template/'reconstruction.json').read_text())
spec.update(campaign_id=a['campaign_id'],full_experiment=p['experiment'],worker_sha256=p['worker_sha256'])
spec['resource_limits']['cpus']=4
root.mkdir(parents=True)
for name,value in [('assignment.json',a),('config-full.json',p['config']),('reconstruction.json',spec)]:
 (root/name).write_text(json.dumps(value,indent=2))
target=root/item['relative_path'];target.parent.mkdir(parents=True);os.link(video,target)
target.with_name(target.name+'.fetch.json').write_text(json.dumps(receipt,indent=2))
for name,text in p['files'].items():(root/name).write_text(text)
for name in ('scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction','outputs'):(root/name).mkdir(parents=True,exist_ok=True)
(root/'status.json').write_text(json.dumps({'state':'downloaded','files':{item['name']:{'state':'verified','sha256':receipt['sha256'],'reused':True}}}))
with (root/'review-worker.log').open('a') as log:
 worker=subprocess.Popen(['python3','-B','-u',str(root/'horizontal_worker.py'),str(root)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('REVIEW_REPLY='+json.dumps({'state':'starting','pid':worker.pid,'root':str(root),'experiment':p['experiment'],'video':item['name'],'stop_after':'sfm'}))
'''.replace('PAYLOAD',repr(payload))
    result = control.remote(source,code,timeout=180)
    (folder/'reconstruction-launch.json').write_text(json.dumps({assignment['node_tag']:result},indent=2))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
