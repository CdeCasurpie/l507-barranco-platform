import pathlib
exec(pathlib.Path('/tmp/opencode/l507_storage.py').read_text().split('\njobs=')[0])
BASE=pathlib.Path('/tmp/opencode/l507-download-probe')
BASE.mkdir(exist_ok=True)
(BASE/'known_hosts').write_text(pathlib.Path('/tmp/opencode/l507-storage/known_hosts').read_text())
identity=CODE.split("docker=[]")[0]
CODE=identity+r'''
import shutil,hashlib,struct,datetime
def mp4_meta(path):
 found=[]
 with path.open('rb') as f:
  def scan(end,depth=0):
   while f.tell()+8<=end:
    start=f.tell();size,kind=struct.unpack('>I4s',f.read(8));header=8
    if size==1:size=struct.unpack('>Q',f.read(8))[0];header=16
    if size==0:size=end-start
    if size<header or start+size>end:break
    if kind in (b'moov',b'trak',b'mdia') and depth<4:scan(start+size,depth+1)
    elif kind in (b'mvhd',b'mdhd'):
     raw=f.read(min(size-header,40));v=raw[0]
     if v==0:created,modified,scale,duration=struct.unpack('>IIII',raw[4:20])
     elif v==1:created,modified,scale,duration=struct.unpack('>QQIQ',raw[4:32])
     else:f.seek(start+size);continue
     found.append({'box':kind.decode(),'created_utc':(datetime.datetime(1904,1,1,tzinfo=datetime.timezone.utc)+datetime.timedelta(seconds=created)).isoformat(),'duration_s':duration/scale if scale else None})
    f.seek(start+size)
  scan(path.stat().st_size)
 return found
result['free_gib']=shutil.disk_usage('/data').free/1024**3
result['videos']=[]
base=pathlib.Path('/data/photogrammetry/incoming')
for p in base.rglob('*'):
 if p.is_file() and p.suffix.lower()=='.mp4' and any(x in str(p) for x in ('manzana_06','manzana_026')):
  info={'path':str(p),'bytes':p.stat().st_size,'inode':p.stat().st_ino}
  info['mp4_metadata']=mp4_meta(p)
  info['sidecars']={str(q.name):q.read_text()[:12000] for q in p.parent.glob('*.json') if q.stat().st_size<100000}
  result['videos'].append(info)
result['processes']=run('ps','-eo','pid,comm')
result['after']=mounts
print('RESULT='+json.dumps(result))
'''
for n in ('006','010','008','019'):
 print(work('L507_'+n,IPS[n],SITE['nodes']['L507_'+n]),flush=True)
