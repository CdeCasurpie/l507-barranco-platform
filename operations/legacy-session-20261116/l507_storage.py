import concurrent.futures, json, pathlib, shlex, subprocess, sys
import pexpect
sys.path.insert(0, '/home/exitoso/lab/scripts')
import lab_config

BASE=pathlib.Path('/tmp/opencode/l507-storage')
BASE.mkdir(exist_ok=True)
SITE=json.loads(pathlib.Path('/home/exitoso/lab-deploy/config/site.json').read_text())
IPS=dict(zip(['001','002','003','004','005','006','007','008','009','010','011','012','014','015','019','021','022','023','024'],
 ['56','54','55','44','103','64','71','77','78','100','65','53','59','61','63','80','101','72','68']))
CODE=r'''
import json, pathlib, subprocess, os, sys
def run(*args):
 p=subprocess.run(args,text=True,capture_output=True,timeout=30)
 if p.returncode: raise RuntimeError(str(args)+': '+p.stderr[:1500])
 return p.stdout
tag,mac,operate=sys.argv[1:]
tags=[p.stem for p in pathlib.Path('/home/'+('exitoso' if tag=='L507_MAESTRA' else 'utec_alumno')).glob('L507_*.txt')]
macs=[p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
assert tag in tags and mac in macs, ('identity mismatch',tags,macs)
blocks=json.loads(run('lsblk','-b','-J','-o','PATH,SIZE,FSTYPE,UUID,MOUNTPOINTS'))
def flatten(items):
 for x in items:
  yield x
  yield from flatten(x.get('children',[]))
candidates=[x for x in flatten(blocks['blockdevices']) if x.get('fstype')=='ext4' and 480*1024**3<int(x['size'])<500*1024**3]
assert len(candidates)==1, candidates
d=candidates[0]; dev=d['path']
mounts=[x for x in d.get('mountpoints',[]) if x]
result={'tag':tag,'device':d,'before':mounts}
docker=[]
try:
 ids=run('docker','ps','-aq').split()
 if ids:
  for c in json.loads(run('docker','inspect',*ids)):
   docker.append({'name':c['Name'],'image':c['Config']['Image'],'state':c['State']['Status'],
    'mounts':c['Mounts'],'working_dir':c['Config'].get('WorkingDir'),'entrypoint':c['Config'].get('Entrypoint'),'cmd':c['Config'].get('Cmd')})
 result['docker']=docker
 result['images']=run('docker','image','ls','--format','{{.Repository}}:{{.Tag}} {{.Size}}').splitlines()
except Exception as e: result['docker_error']=str(e)
if operate=='yes' and mounts!=['/data']:
 target=pathlib.Path('/data')
 assert not target.is_symlink(), '/data is symlink'
 assert not os.path.ismount('/data'), '/data already another mount'
 assert not target.exists() or not any(target.iterdir()), '/data contains files; not hiding them'
 assert len(mounts)<=1, 'multiple mounts'
 if mounts:
  old=mounts[0]
  assert not any(c['state']=='running' and any(m.get('Source','')==old or m.get('Source','').startswith(old+'/') for m in c['mounts']) for c in docker), 'running Docker bind mounts depend on old path'
  if 'docker_error' in result:
   procs=run('ps','-eo','comm,args')
   assert not any(line.split()[0] in ('dockerd','containerd-shim','runc','docker-proxy') or line.split()[0].startswith('containerd-shim') for line in procs.splitlines() if line.split()), 'Docker runtime processes exist but API unavailable'
  busy=subprocess.run(['fuser','-m',old],capture_output=True,text=True)
  assert busy.returncode==1, 'filesystem in use: '+busy.stdout
  run('umount',old)
 target.mkdir(exist_ok=True)
 try: run('mount','-t','ext4','-o','nodev,nosuid',dev,'/data')
 except Exception:
  if mounts: run('mount','-t','ext4','-o','nodev,nosuid',dev,mounts[0])
  raise
result['after']=run('findmnt','-rn','-S',dev,'-o','TARGET,SOURCE,FSTYPE,OPTIONS').splitlines()
result['busy']=subprocess.run(['fuser','-vm',mounts[0] if mounts else '/data'],capture_output=True,text=True).stderr
root=pathlib.Path('/data') if os.path.ismount('/data') else pathlib.Path(mounts[0]) if mounts else None
if root:
 result['root_entries']=[p.name for p in root.iterdir()]
 projects=[p for p in root.iterdir() if p.is_dir() and ('photo' in p.name.lower() or 'fotogram' in p.name.lower())]
 result['projects']={}
 for p in projects:
  result['projects'][str(p)]={'entries':[x.name for x in p.iterdir()],
   'docs':{str(x.relative_to(p)):x.read_text(errors='replace')[:40000] for x in p.glob('README*') if x.is_file()}}
  result['projects'][str(p)]['files']=run('find',str(p),'-maxdepth','3','-type','f','-iname','README*','-o','-name','Dockerfile*','-o','-name','*compose*.yml').splitlines()[:100]
  result['projects'][str(p)]['source_docs']={str(x.relative_to(p)):x.read_text(errors='replace')[:45000] for x in [p/'repo/README.md',p/'repo/containers/README.md',p/'repo/containers/Dockerfile',p/'repo/containers/Dockerfile.pycolmap',p/'repo/containers/Dockerfile.segmentation'] if x.is_file()}
  result['projects'][str(p)]['runtime_entries']=list(str(x.relative_to(p)) for x in (p/'runtime').glob('*'))
 result['home_projects']=[str(x) for x in pathlib.Path('/home/utec_alumno').iterdir() if x.is_dir() and ('photo' in x.name.lower() or 'pipeline' in x.name.lower())] if tag!='L507_MAESTRA' else []
 result['data_unmounted_entries']=[x.name for x in pathlib.Path('/data').iterdir()] if pathlib.Path('/data').is_dir() and not os.path.ismount('/data') else []
 result['docker_services']=subprocess.run(['systemctl','is-active','docker','containerd'],capture_output=True,text=True).stdout
 result['docker_saved_configs']=[]
 for cfg in pathlib.Path('/var/lib/docker/containers').glob('*/config.v2.json'):
  try:
   c=json.loads(cfg.read_text())
   result['docker_saved_configs'].append({'name':c.get('Name'),'image':c.get('Config',{}).get('Image'),'state':c.get('State'),'mountpoints':c.get('MountPoints')})
  except Exception: pass
 result['disk']=run('df','-h',str(root))
print('RESULT='+json.dumps(result))
'''

def work(tag,ip,mac):
 try:
  args=['python3','-B','-c',CODE,tag,mac,'no' if '--inspect' in sys.argv else 'yes']
  if ip:
   cmd=shlex.join(['sudo','-S','-p','SUDO_PROMPT:',*args])
   c=pexpect.spawn('ssh',['-o','ConnectTimeout=8','-o','StrictHostKeyChecking=accept-new','-o','UserKnownHostsFile='+str(BASE/'known_hosts'),'utec_alumno@10.100.41.'+ip,cmd],encoding='utf-8',timeout=90,echo=False)
  else:
   c=pexpect.spawn('sudo',['-S','-p','SUDO_PROMPT:',*args],encoding='utf-8',timeout=90,echo=False)
  output=''
  while True:
   e=c.expect(['[Pp]assword:', 'SUDO_PROMPT:',pexpect.EOF,pexpect.TIMEOUT])
   output+=c.before
   if e==0:c.sendline(lab_config.DEFAULT_SSH_PASSWORD)
   elif e==1:c.sendline(lab_config.DEFAULT_SUDO_PASSWORD if ip else 'qwertyuiop')
   else:break
  c.close()
  (BASE/(tag+'.log')).write_text(output)
  if 'RESULT=' in output:
   data=json.loads(output.rsplit('RESULT=',1)[1].strip())
   (BASE/(tag+'.json')).write_text(json.dumps(data,indent=2))
   return tag, data['after']
  return tag,output[-1800:]
 except Exception as e:return tag,str(e)

jobs=[('L507_MAESTRA',None,'02:00:00:00:00:02')]+[('L507_'+n,ip,SITE['nodes']['L507_'+n]) for n,ip in IPS.items()]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 for r in pool.map(lambda x:work(*x),jobs):print(json.dumps(r),flush=True)
