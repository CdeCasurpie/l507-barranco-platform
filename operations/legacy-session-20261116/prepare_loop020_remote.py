import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import time

assert (Path.home()/'L507_005.txt').is_file()
assert '02:00:00:00:00:07' in [p.read_text().strip() for p in Path('/sys/class/net').glob('*/address')]
source = Path('/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-020')
root = Path('/data/photogrammetry/campaigns/barranco-020-vocabloop-20261116/cuadra-020')
assert os.path.ismount('/data') and not root.exists()
assert shutil.disk_usage('/data').free > 100*2**30
assert not subprocess.check_output(['docker','ps','-q'],text=True).strip(), 'Active container; reconcile first'
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
assert float(subprocess.check_output(['nvidia-smi','--query-gpu=power.limit','--format=csv,noheader,nounits'],text=True).strip()) == 100
lock = Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a')
fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
s = json.loads((source/'reconstruction-full-status.json').read_text())
assert s['state']=='awaiting_review'
out_source = source/'outputs/cuadra-020'/s['experiment']
cfg = json.loads((source/'config-full.json').read_text())
assert cfg['frames']['fps']==2 and cfg['colmap']['matcher']['sequential_overlap']==20
assert cfg['colmap']['matcher']['loop_detection'] is False
root.mkdir(parents=True)
url='https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_flickr100K_words32K.bin'
tree=root/'vocab_tree_flickr100K_words32K.bin'
temp=tree.with_suffix('.download')
h=hashlib.sha256()
with urllib.request.urlopen(url,timeout=60) as response, temp.open('xb') as output:
    while True:
        chunk=response.read(1024**2)
        if not chunk:break
        output.write(chunk);h.update(chunk)
assert temp.stat().st_size==15229678
temp.rename(tree)
vocabulary={'url':url,'bytes':tree.stat().st_size,'sha256':h.hexdigest(),
            'publisher_hash_available':False,'downloaded_at':time.time(),'words':32768}
a=json.loads((source/'assignment.json').read_text())
a.update(campaign_id='barranco-020-vocabloop-20261116',work_root=str(root),
         operation='sparse_vocabulary_loop_diagnostic',variant='2fps-vocab32k')
experiment='phone_020_2fps_vocab32k_loop_sparse_review_v1'
cfg['experiment']={'name':experiment,'notes':'Independent original 2fps baseline plus native sequential vocabulary loop detection; original start/end overlay preserved; no triangulation/filter changes'}
cfg['paths']={'raw_root':str(root/'datasets/raw'),'output_root':str(root/'outputs')}
cfg['colmap']['matcher'].update(loop_detection=True,vocab_tree_path=str(tree))
spec=json.loads((source/'reconstruction.json').read_text())
files={name:(source/name).read_text() for name in spec['bundle_hashes']}
files.update(FILES)
files['config-full.json']=json.dumps(cfg,indent=2)+'\n'
files['assignment.json']=json.dumps(a,indent=2)+'\n'
spec.update(campaign_id=a['campaign_id'],full_experiment=experiment,
            vocabulary=vocabulary,source_root=str(source),sparse_only=True,dense_authorized=False)
spec['bundle_hashes']={name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
for name,text in files.items():(root/name).write_text(text)
(root/'reconstruction.json').write_text(json.dumps(spec,indent=2))
(root/'vocabulary-receipt.json').write_text(json.dumps(vocabulary,indent=2))
item=a['files'][0]
target=root/item['relative_path'];target.parent.mkdir(parents=True)
os.link(source/item['relative_path'],target)
os.link((source/item['relative_path']).with_name(target.name+'.fetch.json'),target.with_name(target.name+'.fetch.json'))
out=root/'outputs/cuadra-020'/experiment
out.mkdir(parents=True)
inventory={}
for directory in ['frames','masks']:
    for p in sorted((out_source/directory).rglob('*')):
        if not p.is_file():continue
        assert not p.is_symlink()
        dest=out/directory/p.relative_to(out_source/directory)
        dest.parent.mkdir(parents=True,exist_ok=True)
        os.link(p,dest)
        inventory[str(dest.relative_to(out))]={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
assert len(list((out/'frames/phone').glob('*.jpg')))==970
(root/'reused-inputs.json').write_text(json.dumps(inventory,indent=2))
(out/'metrics').mkdir()
shutil.copy2(out_source/'metrics/masks_info.json',out/'metrics/masks_info.json')
for directory in ['scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction']:
    (root/directory).mkdir(parents=True,exist_ok=True)
# Safeguard hardlinked inputs with read-only bind mounts inside the worker containers.
print('PREPARED='+json.dumps({'assignment':a,'spec':spec,'root':str(root),'vocabulary':vocabulary,'files_reused':len(inventory)}))
