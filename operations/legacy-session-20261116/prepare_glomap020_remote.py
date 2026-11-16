import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import urllib.request

assert (Path.home()/'L507_005.txt').is_file()
assert '02:00:00:00:00:07' in [p.read_text().strip() for p in Path('/sys/class/net').glob('*/address')]
source=Path('/data/photogrammetry/campaigns/barranco-020-vocabloop-20261116/cuadra-020')
root=Path('/data/photogrammetry/campaigns/barranco-020-glomap-20261116/cuadra-020')
runtime=Path('/data/photogrammetry/runtime/glomap-1.1.0-020-20261116')
assert os.path.ismount('/data') and not root.exists() and not runtime.exists()
assert shutil.disk_usage('/data').free>100*2**30 and shutil.disk_usage('/').free>3.75*2**30
assert not subprocess.check_output(['docker','ps','-q'],text=True).strip()
assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
assert float(subprocess.check_output(['nvidia-smi','--query-gpu=power.limit','--format=csv,noheader,nounits'],text=True).strip())==100
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
s=json.loads((source/'reconstruction-full-status.json').read_text())
assert s['state']=='awaiting_review' and s['registered_images']==970
source_out=source/'outputs/cuadra-020'/s['experiment']
root.mkdir(parents=True);runtime.mkdir(parents=True)
url='https://conda.anaconda.org/conda-forge/linux-64/micromamba-2.10.0-0.tar.bz2'
expected='9a97976244929bbae28fb1fae504e74a3e7e6d1932870e3a03321f01b7fbd07b'
archive=root/'micromamba-2.10.0-0.tar.bz2'
with urllib.request.urlopen(url,timeout=60) as response,archive.open('xb') as stream:
    shutil.copyfileobj(response,stream)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==expected
with tarfile.open(archive) as tar:
    member=tar.getmember('bin/micromamba')
    assert member.isfile() and member.size<50*1024**2
    with tar.extractfile(member) as inp,(root/'micromamba').open('xb') as out:shutil.copyfileobj(inp,out)
(root/'micromamba').chmod(0o755)
a=json.loads((source/'assignment.json').read_text())
a.update(campaign_id='barranco-020-glomap-20261116',work_root=str(root),
         operation='glomap_global_sparse_diagnostic',variant='2fps-vocabdb-glomap')
spec=json.loads((source/'reconstruction.json').read_text())
files={name:(source/name).read_text() for name in spec['bundle_hashes'] if name not in ['config-full.json','assignment.json','loop_vocab_worker.py']}
files.update(FILES)
cfg=json.loads((source/'config-full.json').read_text())
experiment='phone_020_2fps_vocabdb_glomap_review_v1'
cfg['experiment']={'name':experiment,'notes':'GLOMAP1.1.0 CPU on a SQLite backup of completed 020 vocabulary-loop DB; original images/features/matches reused; no new matching; sparse only'}
cfg['paths']={'raw_root':str(root/'datasets/raw'),'output_root':str(root/'outputs')}
files['config-full.json']=json.dumps(cfg,indent=2)
files['assignment.json']=json.dumps(a,indent=2)
spec.update(campaign_id=a['campaign_id'],full_experiment=experiment,
            source_root=str(source),source_database=str(source_out/'colmap/database.db'),
            source_frames=str(source_out/'frames'),glomap_runtime=str(runtime),
            sparse_only=True,dense_authorized=False)
spec['bundle_hashes']={name:hashlib.sha256(text.encode()).hexdigest() for name,text in files.items()}
for name,text in files.items():(root/name).write_text(text)
(root/'reconstruction.json').write_text(json.dumps(spec,indent=2))
item=a['files'][0];target=root/item['relative_path'];target.parent.mkdir(parents=True)
os.link(source/item['relative_path'],target)
os.link((source/item['relative_path']).with_name(target.name+'.fetch.json'),target.with_name(target.name+'.fetch.json'))
for path in ['scratch/tmp/home','scratch/cache','scratch/hf','logs/reconstruction','outputs']:
    (root/path).mkdir(parents=True,exist_ok=True)
receipt=dict(root=str(root),runtime=str(runtime),assignment=a,spec=spec,prepared_at=time.time(),
             bootstrap_url=url,bootstrap_sha256=expected,power_changed=False)
(root/'preparation.json').write_text(json.dumps(receipt,indent=2))
print('PREPARED='+json.dumps(receipt))
