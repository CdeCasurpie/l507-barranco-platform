"""Read-only candidate inventory; never delete maps or other files."""
exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
from concurrent.futures import ThreadPoolExecutor
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
labels=['006-horiz-s-m','010','011','014','015','020','021','027']
def inspect(label):
 launch=json.loads(Path('/tmp/opencode/dense-'+label+'-launch.json').read_text())
 receipt=json.loads((Path('/data/barranco/review/catalog-20261116-134343')/label/'collection.json').read_text())
 tag=receipt['tag'];options=list(opts)
 if tag=='L507_005':options+=['-o','HostKeyAlias=192.0.2.58']
 code=f'''
import pathlib,json,shutil
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
status=json.loads((root/'reconstruction-full-status.json').read_text())
out=list((root/'outputs').glob('*/*/mvs'))
assert len(out)==1
mvs=out[0]
progress=mvs/'dense-batches-progress.json'
complete=[];incomplete=[]
for chunk in sorted((mvs/'chunks').glob('*')):
 if not chunk.is_dir():continue
 maps=[p for p in chunk.rglob('*.dmap') if p.is_file() and not p.is_symlink()]
 row=dict(chunk=chunk.name,files=len(maps),bytes=sum(p.stat().st_size for p in maps),
  native_ply=(chunk/'scene_dense.ply').is_file(),scene=(chunk/'scene_dense.mvs').is_file(),
  scalar_ply=(chunk/'scene_dense_scalar.ply').is_file())
 p=chunk/'batch-receipt.json'
 if p.exists() and row['native_ply'] and row['scene'] and row['scalar_ply']:
  r=json.loads(p.read_text());row['receipt_sha256']=r['cloud']['sha256']
  complete.append(row)
 else:incomplete.append(row)
result=dict(label={label!r},root=str(root),state=status['state'],stage=status.get('stage'),error=status.get('error'),
 progress=json.loads(progress.read_text()) if progress.exists() else None,
 free_gib=shutil.disk_usage('/data').free/2**30,
 completed_maps_gib=sum(r['bytes'] for r in complete)/2**30,
 incomplete_maps_gib=sum(r['bytes'] for r in incomplete)/2**30,
 completed=complete,incomplete=incomplete)
print('INVENTORY='+json.dumps(result))
'''
 return run('ssh',options+[site['ssh_user']+'@'+cache[tag]['ip'],shlex.join(['python3','-B','-c',code])],'INVENTORY=')
with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(inspect,labels))
Path('/tmp/opencode/dense-cleanup-inventory.json').write_text(json.dumps(results,indent=2))
for r in results:
 print(json.dumps({k:r[k] for k in ['label','state','stage','progress','free_gib','completed_maps_gib','incomplete_maps_gib']}),flush=True)
