"""Publish a tiny canary on 014 and prepare an isolated source-lifecycle trial."""
import hashlib
import json
from pathlib import Path
import sys
import pexpect
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from labdeploy import config
from labdeploy.ssh import SSH,credentials
from labdeploy.cli import spec_for
from labdeploy.store import Store

store=Store();site=config.site()
node=store.read('inventory.json')['L507_014']
assert node['available']
SSH(site,store).call(node['ip'],'probe',{'spec':spec_for(site,'L507_014','')})
data=b'{"fixture":"labctl-source-cycle"}\n'
sha=hashlib.sha256(data).hexdigest()
file=store.root/'source-cycle-fixture.json';file.write_bytes(data)
target=site['data_root']+'/.lab-deploy/cache/'+sha
options=['-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(store.root/'known_hosts'),
         '-o','LogLevel=ERROR','-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no']
c=pexpect.spawn('scp',options+[str(file),site['ssh_user']+'@'+node['ip']+':'+target],encoding='utf-8',timeout=60,echo=False)
password,_=credentials(site)
while True:
    event=c.expect(['[Pp]assword:',pexpect.EOF,pexpect.TIMEOUT])
    if event==0:c.sendline(password)
    elif event==1:
        c.close();assert c.exitstatus==0
        break
    else:raise SystemExit('Canary upload timed out')
release,_=config.release('l507-segmentation-v1')
release['name']='labctl-source-cycle-smoke'
release['artifacts'].append({'name':'source-cycle-fixture','sha256':sha,'bytes':len(data),
                            'target':'resources/source-cycle.json','local_candidates':[],
                            'source_paths':{'L507_014':['.lab-deploy/cache/'+sha]}})
release['verify']={'commands':[['python3','-c',"import json,os,pathlib; p=pathlib.Path(os.environ['PG_DATA_ROOT'])/'resources/source-cycle.json'; assert json.loads(p.read_text())['fixture']=='labctl-source-cycle'; print('source artifact verified')"]], 'metrics':None}
config.validate_release(release)
store.write('source-cycle-release.json',release)
site['sources']=['L507_014']
store.write('source-cycle-site.json',site)
print('Local source-cycle manifest prepared; no activation performed')
