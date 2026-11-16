"""Deploy only a derived bridge-recovery experiment to L507_010."""
import base64
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_experiments as control


def main():
    source_state = control.STATE.parent/'barranco-single006-sequential-20261115'
    source = json.loads((source_state/'assignments.json').read_text())['assignments'][0]
    a = copy.deepcopy(source)
    a.update(campaign_id='barranco-006-bridges-20261115', variant='single14nov-bridges',
             operation='bridge_reconstruction',
             work_root='/data/photogrammetry/campaigns/barranco-006-bridges-20261115/cuadra-006')
    a['files'] = []
    state = control.STATE.parent/a['campaign_id']
    state.mkdir(exist_ok=True)
    (state/'known_hosts').write_bytes((source_state/'known_hosts').read_bytes())
    path = state/'assignments.json'
    bundle = {'campaign_id':a['campaign_id'],'assignments':[a]}
    if path.exists():
        assert json.loads(path.read_text()) == bundle
    else:
        path.write_text(json.dumps(bundle,indent=2))
    worker = Path(__file__).with_name('reconnect006_worker.py').read_text()
    payload = base64.b64encode(json.dumps({'source':source,'assignment':a,'worker':worker}).encode()).decode()
    code = '''
import base64,json,pathlib,subprocess,hashlib
p=json.loads(base64.b64decode(PAYLOAD));a=p['assignment'];source=pathlib.Path(p['source']['work_root'])
assert (pathlib.Path.home()/'L507_010.txt').is_file()
assert a['mac'] in [q.read_text().strip() for q in pathlib.Path('/sys/class/net').glob('*/address')]
assert json.loads((source/'reconstruction-full-status.json').read_text())['state']=='awaiting_review'
root=pathlib.Path(a['work_root']);assert not root.is_symlink();root.mkdir(parents=True,exist_ok=True)
for name,value in [('assignment.json',a)]:
 q=root/name
 if q.exists():assert json.loads(q.read_text())==value
 else:q.write_text(json.dumps(value,indent=2))
s=json.loads((source/'reconstruction-full-status.json').read_text())
source_out=source/'outputs/cuadra-006'/s['experiment']
spec=json.loads((source/'reconstruction.json').read_text())
spec.update(campaign_id=a['campaign_id'],full_experiment='colmap_bridge_recovery_v1',bridge_source=str(source_out))
spec['resource_limits']['cpus']=4
q=root/'reconstruction.json'
if q.exists():assert json.loads(q.read_text())==spec
else:q.write_text(json.dumps(spec,indent=2))
for name in ['phone_worker.py','reconstruction_worker.py']:
 q=root/name;text=(source/name).read_text()
 if q.exists():assert q.read_text()==text
 else:q.write_text(text)
q=root/'reconnect006_worker.py'
if q.exists():assert q.read_text()==p['worker']
else:q.write_text(p['worker'])
for name in ['scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction','outputs']:(root/name).mkdir(parents=True,exist_ok=True)
status=root/'reconstruction-full-status.json'
if status.exists():
 old=json.loads(status.read_text());proc=pathlib.Path('/proc/'+str(old.get('pid'))+'/cmdline')
 if old.get('state')=='awaiting_review' or (proc.exists() and str(root).encode() in proc.read_bytes()):
  print('REVIEW_REPLY='+json.dumps(old));raise SystemExit(0)
 raise RuntimeError('An existing recovery attempt requires explicit reconciliation')
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader'],text=True).strip()
with (root/'review-worker.log').open('a') as log:
 process=subprocess.Popen(['python3','-B','-u',str(root/'reconnect006_worker.py'),str(root)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print('REVIEW_REPLY='+json.dumps({'state':'starting','pid':process.pid,'root':str(root)}))
'''.replace('PAYLOAD',repr(payload))
    result = control.remote(source,code)
    (state/'reconstruction-launch.json').write_text(json.dumps({a['node_tag']:result},indent=2))
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
