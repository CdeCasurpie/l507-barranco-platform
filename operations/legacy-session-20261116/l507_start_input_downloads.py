import base64, pathlib, json, time
exec(pathlib.Path('/tmp/opencode/l507_storage.py').read_text().split('\njobs=')[0])
BASE=pathlib.Path('/home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115')
BASE.mkdir(parents=True,exist_ok=True)
keys=pathlib.Path('/tmp/opencode/l507-storage/known_hosts').read_text()
if not (BASE/'known_hosts').exists():(BASE/'known_hosts').write_text(keys)
checks=json.loads(pathlib.Path('/tmp/opencode/drive-checksums.json').read_text())
inventories={b:json.loads(pathlib.Path('/tmp/opencode/drive-'+b+'-inventory.json').read_text())[0] for b in ('006','026')}
for b,inv in inventories.items():
 p=BASE/('drive-'+b+'-inventory.json')
 if not p.exists():p.write_text(json.dumps(inv,indent=2))

worker=pathlib.Path('/home/exitoso/lab-deploy/tools/drive_download_worker.py').read_text()
helpers=r'''
import base64
import ctypes

def content_hashes(path):
    library = ctypes.CDLL(str(Path(__file__).with_name('drive_crc32c.so')))
    update = library.update_crc32c
    update.argtypes = [ctypes.c_uint32, ctypes.c_char_p, ctypes.c_size_t]
    update.restype = ctypes.c_uint32
    digest = hashlib.sha256()
    crc = 0xffffffff
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024**2), b''):
            digest.update(chunk)
            crc = update(crc, chunk, len(chunk))
    return digest.hexdigest(), base64.b64encode((crc ^ 0xffffffff).to_bytes(4, 'big')).decode()

'''
worker=worker.replace('class Confirmation(HTMLParser):',helpers+'\nclass Confirmation(HTMLParser):')
worker=worker.replace("digest = sha256(path)","digest, crc = content_hashes(path)\n        if crc != spec['crc32c_base64']:\n            raise RuntimeError('CRC32C differs from Google Drive; preserving file for inspection')")
worker=worker.replace("if target.exists():\n            # This directory",'''if not target.exists() and spec.get('reuse_source'):
            source = Path(spec['reuse_source'])
            if source.is_symlink() or not source.is_file() or source.stat().st_size != spec['bytes']:
                raise RuntimeError('Existing source is not the inventoried file')
            os.link(source, target)  # Same bytes/inode, no duplicate storage; verify below.
        if target.exists():
            # This directory''')
worker=worker.replace("30 * 1024**3","50 * 1024**3").replace('Less than 30 GiB','Less than 50 GiB')
worker=worker.replace("'sha256': digest})","'sha256': digest, 'crc32c_base64': spec['crc32c_base64']})")
worker=worker.replace("'verified_at': time.time()","'crc32c_base64': spec['crc32c_base64'], 'verified_at': time.time()")
(BASE/'download_worker.py').write_text(worker)
compile(worker,str(BASE/'download_worker.py'),'exec')
library=base64.b64encode(pathlib.Path('/tmp/opencode/drive_crc32c.so').read_bytes()).decode()
assignments=[]
for block,node,variant in [('006','006','14nov'),('006','010','all'),('026','019','all')]:
 files=[]
 for row in inventories[block]:
  if block=='006' and variant=='14nov' and row[2]=='VID20261112102103.mp4':continue
  spec={'id':row[0],'name':row[2],'bytes':int(row[13]),'crc32c_base64':checks[row[0]]['crc32c_base64'],
        'relative_path':'datasets/raw/cuadra-'+block+'/phone/'+row[2]}
  if row[2].startswith('manzana_'):
   folder='manzana_06' if block=='006' else 'manzana_026'
   spec['reuse_source']='/data/photogrammetry/incoming/barranco-2026-11-14/'+folder+'/'+row[2]
  files.append(spec)
 a={'schema':1,'campaign_id':'barranco-inputs-20261115','block_id':block,'variant':variant,
    'node_tag':'L507_'+node,'mac':SITE['nodes']['L507_'+node],'ip':'10.100.41.'+IPS[node],
    'work_root':'/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-'+block+'-'+variant,
    'operation':'download_only','files':files}
 assignments.append(a)
summary={'campaign_id':'barranco-inputs-20261115','assignments':assignments,'operation':'download_only'}
path=BASE/'assignments.json'
if path.exists():assert json.loads(path.read_text())==summary,'Conflicting assignments'
else:path.write_text(json.dumps(summary,indent=2))
for a in assignments:
 CODE=r'''
import os,pwd,json,pathlib,subprocess,base64,shutil
u=pwd.getpwnam('utec_alumno')
if os.getuid()==0:
 os.initgroups(u.pw_name,u.pw_gid);os.setgid(u.pw_gid);os.setuid(u.pw_uid)
os.environ['HOME']=u.pw_dir
os.chdir(u.pw_dir)
'''+'\na='+repr(a)+'\nworker_b64='+repr(base64.b64encode(worker.encode()).decode())+'\nlibrary_b64='+repr(library)+r'''
assert pathlib.Path(u.pw_dir,a['node_tag']+'.txt').is_file(),'Tag mismatch'
assert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')],'MAC mismatch'
assert os.path.ismount('/data'),'No data mount'
assert 'sse4_2' in pathlib.Path('/proc/cpuinfo').read_text(),'CRC acceleration unsupported'
root=pathlib.Path(a['work_root'])
assert not root.is_symlink()
root.mkdir(parents=True,exist_ok=True)
assert root.stat().st_dev==pathlib.Path('/data').stat().st_dev
extra=sum(f['bytes'] for f in a['files'] if not f.get('reuse_source'))
assert shutil.disk_usage('/data').free>50*1024**3+extra,'Disk reserve'
assignment=root/'assignment.json'
if assignment.exists():assert json.loads(assignment.read_text())==a,'Conflicting existing assignment'
else:assignment.write_text(json.dumps(a,indent=2))
status=root/'status.json'
old=json.loads(status.read_text()) if status.exists() else {}
pid=old.get('pid')
proc=pathlib.Path('/proc/'+str(pid)+'/cmdline')
alive=bool(pid and proc.exists() and str(root).encode() in proc.read_bytes())
if not alive and old.get('state')!='downloaded':
 (root/'download_worker.py').write_bytes(base64.b64decode(worker_b64))
 (root/'drive_crc32c.so').write_bytes(base64.b64decode(library_b64))
 with (root/'download.log').open('a') as log:
  p=subprocess.Popen(['python3','-B','-u',str(root/'download_worker.py'),str(root)],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 pid=p.pid
 proc=pathlib.Path('/proc/'+str(pid)+'/cmdline')
 alive=proc.exists()
result={'after':['/data'],'tag':a['node_tag'],'block':a['block_id'],'variant':a['variant'],'pid':pid,'worker_alive':alive,'state':old.get('state','starting'),'root':str(root),'files':[f['name'] for f in a['files']]}
print('RESULT='+json.dumps(result))
'''
 print(work(a['node_tag'],a['ip'].split('.')[-1],a['mac']),flush=True)
