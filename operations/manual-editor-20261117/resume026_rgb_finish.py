"""Resume verified RGB chunks, then collect, simplify, join and render 026."""
exec(open('/tmp/opencode/package026_existing.py').read().split("code=f'''")[0])
color=color.replace('destination.mkdir()','destination.mkdir(exist_ok=True)')
needle="    cv=np.memmap(cloud,dtype=cm['dtype'],mode='r',offset=cm['offset'],shape=(cm['vertices'],))"
resume="""    existing=destination/(chunk.name+'.ply')
    if existing.exists():
        em=header(existing)
        assert em['vertices']==mm['vertices'] and em['faces']==mm['faces']
        old=np.memmap(mesh,dtype=mm['dtype'],mode='r',offset=mm['offset'],shape=(mm['vertices'],))
        saved=np.memmap(existing,dtype=em['dtype'],mode='r',offset=em['offset'],shape=(em['vertices'],))
        for first in range(0,mm['vertices'],200000):
            for axis in ['x','y','z']:
                np.testing.assert_array_equal(old[axis][first:first+200000],saved[axis][first:first+200000])
        with mesh.open('rb') as a,existing.open('rb') as b:
            a.seek(mm['offset']+mm['vertices']*12);b.seek(em['offset']+em['vertices']*15)
            while True:
                left=a.read(8*1024**2);right=b.read(8*1024**2);assert left==right
                if not left:break
        records.append(dict(chunk=chunk.name,path=str(existing),sha256=sha(existing),
            vertices=mm['vertices'],faces=mm['faces'],xyz_unchanged=True,faces_unchanged=True,
            dense_sha256=receipt['cloud']['sha256'],reused_verified=True))
        print('REUSED_VERIFIED_RGB',chunk.name,flush=True)
        del old,saved
        continue
"""
assert needle in color
color=color.replace(needle,resume+needle)
compile(color,'resume026-color','exec')
code=f'''
import pathlib,json,subprocess,sys,fcntl,shutil
assert (pathlib.Path.home()/'L507_019.txt').is_file()
assert {macs['L507_019']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r});mesh=root/'mesh-existing'
assert shutil.disk_usage('/data').free>=55*2**30
assert not (mesh/'colored-chunks/manifest.json').exists(),'Already completed; use collection only'
tool=root/'color026_resume_verified.py';assert not tool.exists();tool.write_text({color!r})
sys.path.insert(0,str(root))
from phone_worker import PhoneWorker
source=pathlib.Path(json.loads((root/'pilot.json').read_text())['source_root'])
class Color(PhoneWorker):
 def docker_args(self,stage,role,argv,gpu=True):
  name,token,args=super().docker_args(stage,role,argv,gpu)
  i=args.index(self.spec['images'][role]['tag'])
  args[i:i]=['--mount',f'type=bind,src={{source}},dst={{source}},readonly',
              '-e',f'PYTHONPATH={{root}}/python-deps']
  return name,token,args
with pathlib.Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 w=Color(root,'resume026-rgb')
 w.command('vertex-color','reconstruction',['python3','-B',str(tool),str(mesh)],gpu=False,timeout=12*3600)
 w.save(state='completed')
m=json.loads((mesh/'colored-chunks/manifest.json').read_text())
assert m['complete'] and len(m['meshes'])==40
print('RESUMED026='+json.dumps(dict(remote=str(mesh/'colored-chunks'),meshes=m['meshes'])))
'''
encoded=base64.b64encode(zlib.compress(code.encode())).decode()
bootstrap="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
print('RESUMING026_RGB',dest,flush=True)
remote=run('ssh',opts+[site['ssh_user']+'@192.0.2.63',
 shlex.join(['sg','docker','-c',shlex.join(['python3','-B','-c',bootstrap])])],'RESUMED026=')
# The original collection/export/render tail never deletes remote inputs.
tail=open('/tmp/opencode/package026_existing.py').read().split("raw=dest/'raw';raw.mkdir()",1)[1]
exec("raw=dest/'raw';raw.mkdir()"+tail)
