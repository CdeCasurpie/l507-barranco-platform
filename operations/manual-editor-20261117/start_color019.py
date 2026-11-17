exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import base64,zlib,uuid
launch=json.loads(Path('/tmp/opencode/dense-019-launch.json').read_text())
script=Path('/tmp/opencode/color019_dense_vertices.py').read_text()
unit='barranco-color019-'+uuid.uuid4().hex[:10]
worker="""import json,sys,signal,fcntl,time
from pathlib import Path
from phone_worker import PhoneWorker
root=Path(sys.argv[1])
class Color(PhoneWorker):
 def docker_args(self,stage,role,argv,gpu=True):
  name,token,args=super().docker_args(stage,role,argv,gpu)
  index=args.index(self.spec['images'][role]['tag'])
  args[index:index]=['-e',f'PYTHONPATH={self.root}/python-deps']
  return name,token,args
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 w=Color(root,'vertex-color')
 signal.signal(signal.SIGTERM,lambda *_:setattr(w,'cancelled',True))
 try:
  out=root/'outputs'/('cuadra-'+w.assignment['block_id'])/w.experiment/'mvs'
  w.command('vertex-color','reconstruction',['python3','-B',str(root/'color_dense_vertices.py'),str(out)],gpu=False,timeout=12*3600)
  w.save(state='completed',stage='vertex-color-complete',output=str(out/'colored-chunks'),finished_at=time.time())
 except BaseException as e:
  w.save(state='failed',error=str(e),finished_at=time.time());raise
"""
code=f'''
import pathlib,subprocess,json,shlex
assert (pathlib.Path.home()/'L507_004.txt').is_file()
assert {macs['L507_004']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
status=json.loads((root/'reconstruction-full-status.json').read_text());assert status['state']=='completed'
assert not (root/'color_dense_vertices.py').exists(),'Refuse duplicate color job'
(root/'color_dense_vertices.py').write_text({script!r})
(root/'color_worker.py').write_text({worker!r})
(root/'vertex-color-launch.json').write_text(json.dumps(dict(unit={unit!r},geometry_changes_authorized=False)))
result=subprocess.run(['systemd-run','--user','--wait','--pipe','--unit='+{unit!r},
 '-p','MemoryMax=32G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 'sg','docker','-c',shlex.join(['python3','-B',str(root/'color_worker.py'),str(root)])])
raise SystemExit(result.returncode)
'''
encoded=base64.b64encode(zlib.compress(code.encode())).decode()
bootstrap="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
print('START019_VERTEX_RGB',unit,flush=True)
run('ssh',opts+[site['ssh_user']+'@192.0.2.44',shlex.join(['python3','-B','-c',bootstrap])])
