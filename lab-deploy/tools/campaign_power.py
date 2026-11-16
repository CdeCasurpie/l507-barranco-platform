"""Apply/restore an in-range temporary GPU power ceiling with an ownership receipt."""
import json
from pathlib import Path
import shlex
import sys

import pexpect

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT))
from labdeploy.ssh import credentials


def power(site,a,restore=False,watts=120):
    code=f'''
import json,os,subprocess,time
from pathlib import Path
a={a!r};root=Path(a['work_root'])
if not os.path.ismount('/data') or not (Path('/home/utec_alumno')/(a['node_tag']+'.txt')).is_file():raise RuntimeError('Wrong node/data mount')
if a['mac'] not in [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')]:raise RuntimeError('MAC mismatch')
fields=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,power.min_limit,power.max_limit,power.limit','--format=csv,noheader,nounits'],text=True).strip().split(',')
uuid=fields[0].strip();minimum,maximum,current=map(float,fields[1:]);receipt=root/'power-limit.json'
old=json.loads(receipt.read_text()) if receipt.exists() else None
if {restore!r}:
 if not old or old.get('state')!='applied':
  print('POWER_REPLY='+json.dumps(old or {{'state':'not_applied'}}));raise SystemExit(0)
 if old['gpu_uuid']!=uuid:raise RuntimeError('GPU UUID changed')
 if abs(current-old['applied_w'])>.1:
  old.update(state='operator_changed_limit',observed_w=current)
 else:
  subprocess.run(['nvidia-smi','-pl',str(old['original_w'])],check=True,capture_output=True)
  old.update(state='restored',restored_at=time.time())
 value=old
else:
 requested={watts!r}
 if not minimum<=requested<=maximum:raise RuntimeError('Requested ceiling outside supported GPU range')
 if old and old.get('state')=='applied':
  if old['gpu_uuid']!=uuid or abs(current-old['applied_w'])>.1:raise RuntimeError('Existing power receipt no longer matches')
  if requested<current:
   subprocess.run(['nvidia-smi','-pl',str(requested)],check=True,capture_output=True)
   old.setdefault('adjustments',[]).append({{'from_w':current,'to_w':requested,'at':time.time()}})
   old['applied_w']=requested
  value=old
 else:
  active=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
  if active:raise RuntimeError('Another GPU compute workload is active; leaving power limit unchanged')
  target=min(current,requested)
  subprocess.run(['nvidia-smi','-pl',str(target)],check=True,capture_output=True)
  value={{'state':'applied','gpu_uuid':uuid,'original_w':current,'applied_w':target,'at':time.time(),'campaign_id':a['campaign_id']}}
tmp=receipt.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\\n');os.chmod(tmp,0o644);tmp.replace(receipt)
print('POWER_REPLY='+json.dumps(value))
'''
    password,sudo=credentials(site)
    c=pexpect.spawn('ssh',['-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes',
        '-o','UserKnownHostsFile='+str(PROJECT/'.state/known_hosts'),'-o','LogLevel=ERROR',
        '-o','PreferredAuthentications=password','-o','PubkeyAuthentication=no','-o','NumberOfPasswordPrompts=1',
        site['ssh_user']+'@'+a['ip'],shlex.join(['sudo','-S','-p','POWER_SUDO:','--','python3','-B','-c',code])],
        encoding='utf-8',echo=False,timeout=60)
    parts=[];sent=False
    while True:
        event=c.expect(['[Pp]assword:','POWER_SUDO:',pexpect.EOF,pexpect.TIMEOUT]);parts.append(c.before)
        if event==0:c.sendline(password)
        elif event==1:
            if sent:c.close(force=True);raise RuntimeError('Sudo authentication rejected')
            c.sendline(sudo);sent=True
        else:break
    c.close();text=''.join(parts)
    if 'POWER_REPLY=' not in text:raise RuntimeError(text[-1500:])
    return json.loads(text.rsplit('POWER_REPLY=',1)[-1].splitlines()[0])


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--blocks',required=True);p.add_argument('--restore',action='store_true');p.add_argument('--watts',type=float,default=120);args=p.parse_args()
    site=json.loads((PROJECT/'config/site.json').read_text())
    entries=json.loads(Path('/data/barranco/campaigns/barranco-full-v1/assignments.json').read_text())['assignments']
    override=Path('/data/barranco/campaigns/barranco-full-v1/execution-overrides.json')
    if override.exists():
        replacements=json.loads(override.read_text());entries=[replacements.get(a['block_id'],a) for a in entries]
    for a in entries:
        if a['block_id'] in args.blocks.split(','):print(a['block_id'],json.dumps(power(site,a,args.restore,args.watts)))
