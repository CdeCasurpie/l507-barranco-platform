"""Prepare only the approved 2.03 GB clip on L507_010; preserve original videos."""
import copy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import review_experiments as control


def main():
    original = next(a for a in json.loads((control.STATE / 'assignments.json').read_text())['assignments']
                    if a['node_tag'] == 'L507_010')
    assignment = copy.deepcopy(original)
    assignment.update(campaign_id='barranco-single006-sequential-20261115',
                      variant='single14nov-sequential',
                      work_root='/data/photogrammetry/campaigns/barranco-single006-sequential-20261115/cuadra-006')
    assignment['files'] = [f for f in assignment['files'] if f['name'] == 'VID20261114142304.mp4']
    assert len(assignment['files']) == 1 and assignment['files'][0]['bytes'] == 2032723786
    folder = control.STATE.parent / assignment['campaign_id']
    folder.mkdir(exist_ok=True)
    keys = folder / 'known_hosts'
    if not keys.exists():
        keys.write_bytes((control.STATE / 'known_hosts').read_bytes())
    bundle = {'campaign_id': assignment['campaign_id'], 'operation': 'download_only',
              'assignments': [assignment]}
    path = folder / 'assignments.json'
    if path.exists():
        assert json.loads(path.read_text()) == bundle
    else:
        path.write_text(json.dumps(bundle, indent=2))
    code = '''
import pathlib,json,os,hashlib,subprocess
a=ASSIGNMENT;previous=PREVIOUS
assert (pathlib.Path.home()/'L507_010.txt').is_file()
assert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
assert os.path.ismount('/data')
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip(),'GPU occupied'
old=pathlib.Path(previous['work_root'])
state=json.loads((old/'reconstruction-full-status.json').read_text())
assert state.get('operator_discarded'), 'Previous experiment was not explicitly discarded'
root=pathlib.Path(a['work_root']);assert not root.is_symlink();root.mkdir(parents=True,exist_ok=True)
p=root/'assignment.json'
if p.exists():assert json.loads(p.read_text())==a
else:p.write_text(json.dumps(a,indent=2))
spec=a['files'][0];source=old/spec['relative_path'];target=root/spec['relative_path']
receipt=json.loads(source.with_name(source.name+'.fetch.json').read_text())
assert receipt['drive_file_id']==spec['id'] and source.stat().st_size==spec['bytes']
h=hashlib.sha256()
with source.open('rb') as f:
 for chunk in iter(lambda:f.read(4194304),b''):h.update(chunk)
assert h.hexdigest()==receipt['sha256']
target.parent.mkdir(parents=True,exist_ok=True)
if not target.exists():os.link(source,target)
assert target.stat().st_ino==source.stat().st_ino
target.with_name(target.name+'.fetch.json').write_text(json.dumps(receipt,indent=2))
(root/'status.json').write_text(json.dumps({'state':'downloaded','files':{spec['name']:{'state':'verified','sha256':receipt['sha256'],'bytes':spec['bytes'],'reused':True}}},indent=2))
print('REVIEW_REPLY='+json.dumps({'root':str(root),'video':spec['name'],'bytes':target.stat().st_size,'reused_without_copy':True}))
'''.replace('ASSIGNMENT', repr(assignment)).replace('PREVIOUS', repr(original))
    print(json.dumps(control.remote(original, code), indent=2))
    print('ASSIGNMENTS', path)


if __name__ == '__main__':
    main()
