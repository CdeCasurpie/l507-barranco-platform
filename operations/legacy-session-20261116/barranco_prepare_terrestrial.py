import json
import os
from pathlib import Path
import shutil

assert NODE_TAG=='L507_022'
a=BINDINGS['assignments'][0]
source=BINDINGS['source_assignment']
assert len(a['files'])==1 and a['files'][0]['name']=='manzana_16y23.mp4'
assert os.path.ismount('/data')
source_root=Path(source['work_root'])
assert json.loads((source_root/'assignment.json').read_text())==source
assert json.loads((source_root/'status.json').read_text())['state']=='downloaded'
root=Path(a['work_root'])
assert root.name=='cuadra-016-023-terrestrial'
assert not root.exists(),'Do not overwrite an existing terrestrial attempt'
assert shutil.disk_usage('/data').free>100*2**30
root.mkdir()
item=a['files'][0]
original=source_root/item['relative_path']
receipt=original.with_name(original.name+'.fetch.json')
metadata=json.loads(receipt.read_text())
assert metadata['drive_file_id']==item['id'] and original.stat().st_size==item['bytes']
target=root/item['relative_path']
target.parent.mkdir(parents=True)
os.link(original,target)
os.link(receipt,target.with_name(target.name+'.fetch.json'))
(root/'assignment.json').write_text(json.dumps(a,indent=2)+'\n')
(root/'source-reference.json').write_text(json.dumps({
    'source_assignment':source,'operation':'terrestrial-only-hardlink-snapshot',
    'drone_included':False,'originals_modified':False},indent=2)+'\n')
(root/'status.json').write_text(json.dumps({
    'state':'downloaded','completed_files':1,'total_files':1,
    'completed_bytes':item['bytes'],'total_bytes':item['bytes'],
    'files':{item['name']:{'state':'verified','bytes':item['bytes'],
                            'sha256':metadata['sha256'],'reused':True}}},indent=2)+'\n')
print('ADMIN_REPLY='+json.dumps({'tag':NODE_TAG,'state':'prepared',
                               'root':str(root),'video':item['name'],'hardlinked':True}))
