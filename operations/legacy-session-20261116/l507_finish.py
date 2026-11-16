import pathlib
exec(pathlib.Path('/tmp/opencode/l507_storage.py').read_text().split('\njobs=')[0])
identity=CODE.split("docker=[]")[0]
CODE=identity+r'''
result['mountinfo']=run('findmnt','-J','-o','TARGET,SOURCE,FSTYPE,OPTIONS')
result['busy_details']=subprocess.run(['fuser','-vm',mounts[0]],capture_output=True,text=True).stderr if mounts else ''
result['data_entries']=[{'path':str(p),'symlink':p.is_symlink(),'mount':os.path.ismount(p),'stat':list(p.lstat()),'children':[x.name for x in p.iterdir()][:30] if p.is_dir() else []} for p in pathlib.Path('/data').iterdir()]
result['after']=mounts
print('RESULT='+json.dumps(result))
'''
if '--apply' in sys.argv:
 CODE=identity+r'''
import signal,time,datetime
assert tag in ('L507_001','L507_005')
assert len(mounts)==1
old=mounts[0]
assert old!='/data'
assert not os.path.ismount('/data') and not pathlib.Path('/data').is_symlink()
backup=None
if tag=='L507_005':
 entries=list(pathlib.Path('/data').iterdir())
 assert [x.name for x in entries]==['tesis-cava'], entries
 source=entries[0]
 allmounts=json.loads(run('findmnt','-J','-o','TARGET'))
 assert not any(x['target']==str(source) or x['target'].startswith(str(source)+'/') for x in flatten(allmounts['filesystems'])), 'nested mount: needs separate handling'
 backup=pathlib.Path('/data-preserved-L507_005-'+datetime.datetime.now().strftime('%Y%m%dT%H%M%S'))
 assert not backup.exists()
 assert source.stat().st_dev==pathlib.Path('/').stat().st_dev
 backup.mkdir(mode=0o755)
 inode=source.lstat().st_ino
 source.rename(backup/'tesis-cava')
 assert (backup/'tesis-cava').lstat().st_ino==inode
 result['preserved']=str(backup/'tesis-cava')
assert not any(pathlib.Path('/data').iterdir())
def users():
 p=subprocess.run(['fuser','-m',old],capture_output=True,text=True)
 assert p.returncode in (0,1), p.stderr
 return [int(x) for x in p.stdout.split() if x.isdigit()]
protected={os.getpid()}
pid=os.getpid()
while pid>1:
 try:
  pid=int(pathlib.Path('/proc/'+str(pid)+'/stat').read_text().split(') ',1)[1].split()[1])
  protected.add(pid)
 except (FileNotFoundError,ValueError):break
terminated=[]
for sig in (signal.SIGTERM,signal.SIGKILL):
 pids=users()
 assert not protected.intersection(pids), 'own connection using filesystem'
 for pid in pids:
  try:
   os.kill(pid,sig);terminated.append({'pid':pid,'signal':int(sig)})
  except ProcessLookupError:pass
 if pids:time.sleep(3)
assert not users(), 'still busy'
run('sync','-f',old)
run('umount',old)
try:
 run('mount','-t','ext4','-o','nodev,nosuid',dev,'/data')
except Exception:
 run('mount','-t','ext4','-o','nodev,nosuid',dev,old)
 if backup and not any(pathlib.Path('/data').iterdir()):
  (backup/'tesis-cava').rename('/data/tesis-cava')
 raise
result['terminated']=terminated
result['after']=run('findmnt','-rn','--mountpoint','/data','-o','TARGET,SOURCE,FSTYPE,OPTIONS').splitlines()
assert pathlib.Path('/data/photogrammetry').is_dir()
result['data_entries']=[p.name for p in pathlib.Path('/data').iterdir()]
if backup:result['preserved_exists']=(backup/'tesis-cava').is_dir()
print('RESULT='+json.dumps(result))
'''
for n in ('001','005'):
 print(work('L507_'+n,IPS[n],SITE['nodes']['L507_'+n]),flush=True)
