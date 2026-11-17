"""Correct only our pending mesh scripts; never touch original scientific data."""
exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
from concurrent.futures import ThreadPoolExecutor
new=Path('/tmp/opencode/pilot022_mesh_chunks.py').read_text()
old=new.replace("str(scene),\n                        '-p',str(directory/'scene_dense.ply'),'-o'","str(scene),'-o'")
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
labels=['006-horiz-s-m','010','011','014','015','016-023','019','020','021','022','027']
def update(label):
 path=Path('/tmp/opencode')/('pilot022-dense-launch.json' if label=='022' else 'dense-'+label+'-launch.json')
 launch=json.loads(path.read_text())
 receipt=json.loads((Path('/data/barranco/review/catalog-20261116-134343')/label/'collection.json').read_text())
 tag=receipt['tag'];options=list(opts)
 if tag=='L507_005':options+=['-o','HostKeyAlias=192.0.2.58']
 code=f'''
import pathlib,json,hashlib
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
s=json.loads((root/'reconstruction-full-status.json').read_text())
p=root/'mesh_chunks.py';text=p.read_text()
result=dict(label={label!r},state=s['state'],stage=s.get('stage'))
if text=={new!r}:result['fix']='already_correct'
elif text!={old!r}:result['fix']='unexpected_script_preserved'
elif s.get('stage')=='mesh' or 'mesh' in s.get('completed_stages',[]):result['fix']='mesh_started_requires_separate_retry'
else:
 backup=p.with_name('mesh_chunks.pre-dense-input-fix.py')
 assert not backup.exists()
 backup.write_text(text)
 temporary=p.with_suffix('.new');temporary.write_text({new!r});temporary.replace(p)
 result['fix']='explicit_dense_ply_installed'
print('FIX='+json.dumps(result))
'''
 return run('ssh',options+[site['ssh_user']+'@'+cache[tag]['ip'],shlex.join(['python3','-B','-c',code])],'FIX=')
with ThreadPoolExecutor(max_workers=4) as pool:
 results=list(pool.map(update,labels))
Path('/tmp/opencode/dense-mesh-input-fixes.json').write_text(json.dumps(results,indent=2))
for row in results:print(json.dumps(row),flush=True)
