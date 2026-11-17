import sys,json,shlex,hashlib,time,socket
from pathlib import Path
import pexpect
sys.path.insert(0,'/home/exitoso/lab-deploy')
from labdeploy.ssh import credentials
state=Path('/home/exitoso/lab-deploy/.state/campaigns/barranco-020-cut10fps-20261116')
a=json.loads((state/'assignments.json').read_text())['assignments'][0]
site=json.loads(Path('/home/exitoso/lab-deploy/config/site.json').read_text())
password,_=credentials(site)
opts=['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o','HostKeyAlias=192.0.2.58','-o','UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts']
def run(cmd,args,marker=None):
 c=pexpect.spawn(cmd,args,encoding='utf-8',echo=False,timeout=300)
 chunks=[]
 while True:
  e=c.expect(['[Pp]assword:',pexpect.EOF,pexpect.TIMEOUT]);chunks.append(c.before)
  if e==0:c.sendline(password)
  elif e==1:break
  else:c.close(force=True);raise RuntimeError('Consulta/transferencia agotó tiempo; parciales preservados')
 c.close()
 assert c.exitstatus==0,'Consulta/transferencia fallida'
 if marker:return json.loads(''.join(chunks).rsplit(marker,1)[1].splitlines()[0])
code="import pathlib,json\n"+"a="+repr(a)+"\n"
code+="assert (pathlib.Path.home()/(a['node_tag']+'.txt')).is_file()\nassert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]\n"
code+="BINDINGS={'assignments':[a]}\nNODE_TAG=a['node_tag']\n"
code+=Path('/tmp/opencode/barranco_sparse_manifest.py').read_text()
m=run('ssh',opts+[site['ssh_user']+'@'+a['ip'],shlex.join(['python3','-B','-c',code])],'ADMIN_REPLY=')
dest=Path('/data/barranco/review/barranco-020-cut10fps-20261116/020-local10fps-268-280')
assert not dest.exists(),'Destino ya existe; inspeccionar sin sobrescribir'
dest.mkdir(parents=True)
(state/'sparse-review-manifest.json').write_text(json.dumps(m,indent=2))
filelist=state/'sparse-review-files.txt'
filelist.write_text('\n'.join(m['files'])+'\n')
run('rsync',['-a','--partial','--files-from='+str(filelist),'-e',shlex.join(['ssh']+opts),site['ssh_user']+'@'+a['ip']+':'+m['root']+'/',str(dest)+'/'])
for name,expected in m['files'].items():
 p=dest/name
 assert p.stat().st_size==expected['bytes']
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4194304),b''):h.update(b)
 assert h.hexdigest()==expected['sha256'],name
receipt=dict(m,destination=str(dest),collected_at=time.time(),sha256_verified=True,dense_collected=False,manually_accepted=False)
(dest/'collection.json').write_text(json.dumps(receipt,indent=2))
(state/'sparse-review-collected.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({'destination':str(dest),'components':m['components'],'files':len(m['files']),'sha256_verified':True}))
