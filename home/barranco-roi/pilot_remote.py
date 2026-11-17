"""Prepare the authorized 025 native subset on L507_015 and copy only pilot inputs."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tarfile
import time
import pexpect

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,'/home/exitoso/lab-deploy/tools')
from drive_download_campaign import remote
sys.path.insert(0,'/home/exitoso/lab-deploy')
from labdeploy.ssh import credentials
from labdeploy.store import atomic_json

SITE=json.load(open('/home/exitoso/lab-deploy/config/site.json'))
IP='192.0.2.61'
SEL='s-1794364122096131540'
OUT=Path('/data/barranco/roi/025')/SEL/'pilot-v1'
REMOTE='/data/photogrammetry/roi-pilot-025/'+SEL
LOCAL=ROOT/'runtime/native-025'/SEL


def transfer(source,target):
    password,_=credentials(SITE)
    ssh='ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=yes -o UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts -o LogLevel=ERROR -o PreferredAuthentications=password -o PubkeyAuthentication=no -o NumberOfPasswordPrompts=1'
    child=pexpect.spawn('rsync',['-a','--partial','-e',ssh,source,target],encoding='utf-8',timeout=180,echo=False)
    while True:
        event=child.expect(['[Pp]assword:',pexpect.EOF,pexpect.TIMEOUT])
        if event==0:child.sendline(password)
        elif event==1:break
        else:child.close(force=True);raise RuntimeError('Pilot transfer timed out')
    child.close()
    if child.exitstatus!=0:raise RuntimeError('Pilot transfer failed')


def main():
    selection=json.loads((ROOT/'state/selections'/f'{SEL}.json').read_text())
    prep=json.loads((OUT/'prepare.json').read_text())
    LOCAL.mkdir(parents=True,exist_ok=True)
    config=LOCAL/'polygon.txt'
    config.write_text(' '.join(str(v) for row in selection['source']['world_from_block'] for v in row)+'\n'+str(len(selection['vertices']))+'\n'+'\n'.join(' '.join(map(str,p)) for p in selection['vertices'])+'\n')
    ready=remote(SITE,IP,f'''
import json,os
from pathlib import Path
if not (Path.home()/'L507_015.txt').is_file():raise RuntimeError('Wrong tag')
if '02:00:71:28:66:c7' not in [p.read_text().strip().lower() for p in Path('/sys/class/net').glob('*/address')]:raise RuntimeError('Wrong MAC')
if not os.path.ismount('/data'):raise RuntimeError('Authorized source /data is not mounted')
p=Path({REMOTE!r});p.mkdir(parents=True,exist_ok=True)
print('DOWNLOAD_REPLY='+json.dumps({{'directory':str(p)}}))
''')
    prefix=SITE['ssh_user']+'@'+IP+':'
    for source,name in [(ROOT/'runtime/tools/crop_native','crop_native'),(config,'polygon.txt'),(OUT/'common_roi_indices.bin','indices.bin')]:
        transfer(str(source),prefix+REMOTE+'/'+name)
    code=f'''
import json,os,subprocess,hashlib,time,fcntl
from pathlib import Path
root=Path({REMOTE!r});source=Path('/data/photogrammetry/campaigns/barranco-full-v1/cuadra-025/outputs/cuadra-025/barranco_4k_2fps_combined_v1/mvs/scene_dense.ply')
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lease:
 fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
 h=hashlib.sha256()
 with source.open('rb') as f:
  for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
 if h.hexdigest()!='dd2cec0668a3cf344a280dbde311dc73b2818bda010c4b4b882a503a0577787b':raise RuntimeError('Native source checksum mismatch')
 allowed=set(os.sched_getaffinity(0));chosen={{8,9}};os.sched_setaffinity(0,chosen if chosen<=allowed else set(sorted(allowed)[:2]))
 cloud=root/'native_common.ply';receipt=root/'native.json'
 if not receipt.exists():
  start=time.monotonic();p=subprocess.Popen([str(root/'crop_native'),str(source),str(cloud),str(root/'polygon.txt'),str(root/'indices.bin')],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  while p.poll() is None:
   temperatures=[]
   for hw in Path('/sys/class/hwmon').glob('hwmon*'):
    if (hw/'name').exists() and (hw/'name').read_text().strip()=='coretemp':temperatures += [int(q.read_text())/1000 for q in hw.glob('temp*_input')]
   if temperatures and max(temperatures)>=90:p.terminate();p.wait();raise RuntimeError('Native preparation paused: CPU reached 90C')
   time.sleep(2)
  output,error=p.communicate()
  if p.returncode:raise RuntimeError(error)
  value=json.loads(output)
  if value['inside_points']!={26860347!r} or value['selected_points']!={prep['common_points']!r}:raise RuntimeError('Native/scalar selection count differs')
  h=hashlib.sha256()
  with cloud.open('rb') as f:
   for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
  value.update(sha256=h.hexdigest(),bytes=cloud.stat().st_size,seconds=time.monotonic()-start,source_sha256='dd2cec0668a3cf344a280dbde311dc73b2818bda010c4b4b882a503a0577787b')
  receipt.write_text(json.dumps(value,indent=2))
print('DOWNLOAD_REPLY='+receipt.read_text().replace('\\n',''))
'''
    result=remote(SITE,IP,code,timeout=600)
    print(json.dumps(result,indent=2),flush=True)
    transfer(prefix+REMOTE+'/native_common.ply',str(LOCAL/'native_common.ply'))
    transfer(prefix+REMOTE+'/native.json',str(LOCAL/'native.json'))
    h=hashlib.sha256()
    with (LOCAL/'native_common.ply').open('rb') as f:
        for block in iter(lambda:f.read(4*1024**2),b''):h.update(block)
    if h.hexdigest()!=result['sha256']:raise RuntimeError('Transferred native cloud checksum mismatch')
    atomic_json(OUT/'native_input.json',dict(result,local_path=str(LOCAL/'native_common.ply'),node='L507_015'))
    # Bundle only the certified executables and non-system ABI dependencies.
    bundle_code="""
import os,json,subprocess,shutil,tarfile
from pathlib import Path
root=Path('/pilot');destination=root/'openmvs-bundle';(destination/'bin').mkdir(parents=True,exist_ok=True);(destination/'lib').mkdir(exist_ok=True)
skip=('libc.so','libm.so','libpthread.so','libdl.so','librt.so','libstdc++.so','libgcc_s.so','ld-linux')
libraries={}
for name in ['ReconstructMesh','InterfaceCOLMAP','TextureMesh']:
 binary=Path(shutil.which(name));shutil.copy2(binary,destination/'bin'/name)
 for line in subprocess.check_output(['ldd',str(binary)],text=True).splitlines():
  parts=line.strip().split()
  if len(parts)>=3 and parts[1]=='=>':
   soname,path=parts[0],parts[2]
   if path.startswith('/') and not soname.startswith(skip):libraries[soname]=path
for name,path in libraries.items():shutil.copy2(Path(path).resolve(),destination/'lib'/name)
archive=root/'openmvs-runtime.tar.gz'
with tarfile.open(archive,'w:gz',compresslevel=1) as tar:tar.add(destination,arcname='openmvs')
print(json.dumps({'libraries':len(libraries),'archive_bytes':archive.stat().st_size}))
"""
    bundle_result=remote(SITE,IP,f'''
import json,subprocess
code={bundle_code!r}
p=subprocess.run(['docker','run','--rm','--network','none','--cpus','2','--memory','2g','--memory-swap','2g','--user',str(__import__('os').getuid())+':'+str(__import__('os').getgid()),'--mount','type=bind,src={REMOTE},dst=/pilot','--entrypoint','python3','photogrammetry:l507-v1-pycolmap','-c',code],capture_output=True,text=True,timeout=180)
if p.returncode:raise RuntimeError(p.stderr)
print('DOWNLOAD_REPLY='+p.stdout.strip().splitlines()[-1])
''',timeout=200)
    print(json.dumps(bundle_result,indent=2),flush=True)
    transfer(prefix+REMOTE+'/openmvs-runtime.tar.gz',str(LOCAL/'openmvs-runtime.tar.gz'))
    if not (ROOT/'runtime/openmvs').exists():
        with tarfile.open(LOCAL/'openmvs-runtime.tar.gz') as tar:tar.extractall(ROOT/'runtime',filter='data')
    atomic_json(OUT/'runtime.json',dict(bundle_result,source_image='photogrammetry:l507-v1-pycolmap',isolated_path=str(ROOT/'runtime/openmvs')))
    print('Native input and certified isolated runtime ready',flush=True)


if __name__=='__main__':main()
