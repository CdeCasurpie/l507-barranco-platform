import concurrent.futures
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time
import pexpect
sys.path.insert(0,'/home/exitoso/lab-deploy')
from labdeploy.ssh import credentials

state=Path('/home/exitoso/lab-deploy/.state/campaigns/barranco-running-20261116')
site=json.loads(Path('/home/exitoso/lab-deploy/config/site.json').read_text())
password,_=credentials(site)
parser=argparse.ArgumentParser()
parser.add_argument('--manifest',default='sparse-020-021-manifest.json')
parser.add_argument('--output',default='sparse-020-021-collected.json')
args=parser.parse_args()
manifests=json.loads((state/args.manifest).read_text())
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(4194304),b''):h.update(b)
    return h.hexdigest()
def collect(m):
    assert m['block'] in ('019','020','021') and not m.get('error')
    destination=Path('/data/barranco/review/barranco-running-20261116')/(m['block']+'-seq20-loop')
    destination.mkdir(parents=True,exist_ok=True)
    for name,metadata in m['files'].items():
        assert '..' not in Path(name).parts and not Path(name).is_absolute()
        p=destination/name
        assert not p.is_symlink()
        if p.exists():assert sha(p)==metadata['sha256'],'Do not overwrite different existing geometry'
    filelist=state/(m['tag']+'-review-filelist.txt')
    filelist.write_text('\n'.join(m['files'])+'\n')
    opts=['ssh','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8',
          '-o','UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts']
    ip={'L507_002':'192.0.2.54','L507_004':'192.0.2.44','L507_005':'192.0.2.103'}[m['tag']]
    if m['tag']=='L507_005':
        ip='192.0.2.103';opts+=['-o','HostKeyAlias=192.0.2.58']
    child=pexpect.spawn('rsync',['-a','--partial','--files-from='+str(filelist),'-e',shlex.join(opts),
                                  site['ssh_user']+'@'+ip+':'+m['root']+'/',str(destination)+'/'],
                        encoding='utf-8',echo=False,timeout=180)
    while True:
        e=child.expect(['[Pp]assword:',pexpect.EOF,pexpect.TIMEOUT])
        if e==0:child.sendline(password)
        elif e==1:break
        else:child.close(force=True);raise RuntimeError('Sparse transfer timed out; partials preserved')
    child.close()
    assert child.exitstatus==0,'Sparse transfer failed'
    for name,metadata in m['files'].items():
        p=destination/name
        assert p.stat().st_size==metadata['bytes'] and sha(p)==metadata['sha256']
    record=dict(m,node=m['tag'],destination=str(destination),manually_accepted=False,
                dense_collected=False,collected_at=time.time())
    receipt=destination/'collection.json'
    if not receipt.exists():receipt.write_text(json.dumps(record,indent=2)+'\n')
    return {'block':m['block'],'destination':str(destination),'components':m['components'],
            'sha256_verified':True}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results=list(pool.map(collect,manifests))
(state/args.output).write_text(json.dumps(results,indent=2)+'\n')
for r in results:print(json.dumps(r))
