exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
from concurrent.futures import ThreadPoolExecutor,as_completed
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
labels=['006-horiz-s-m','010','011','014','015','016-023','019','020','021','022','026-parque','027']
def inspect(label):
 launch_path=Path('/tmp/opencode')/('pilot022-dense-launch.json' if label=='022' else 'dense-'+label+'-launch.json')
 if not launch_path.exists():return dict(label=label,state='launch_not_confirmed')
 launch=json.loads(launch_path.read_text())
 receipt=json.loads((Path('/data/barranco/review/catalog-20261116-134343')/label/'collection.json').read_text())
 tag=receipt['tag'];ip=cache[tag]['ip'];options=list(opts)
 if tag=='L507_005':options+=['-o','HostKeyAlias=192.0.2.58']
 code=f'''
import pathlib,json
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r});p=root/'reconstruction-full-status.json'
s=json.loads(p.read_text()) if p.exists() else {{}}
r={{k:s.get(k) for k in ['state','stage','error','completed_stages','updated_at','telemetry']}}
progress=list((root/'outputs').glob('*/*/mvs/dense-batches-progress.json'))
if progress:r['dense_progress']=json.loads(progress[0].read_text())
if s.get('state')=='failed':
 r['logs']={{str(p.relative_to(root)):p.read_text(errors='replace')[-2200:] for p in (root/'logs').rglob('*.log')}}
print('STATUS='+json.dumps(r))
'''
 result=run('ssh',options+[site['ssh_user']+'@'+ip,shlex.join(['python3','-B','-c',code])],'STATUS=')
 return dict(label=label,**result)
results=[]
with ThreadPoolExecutor(max_workers=6) as pool:
 for future in as_completed({pool.submit(inspect,label):label for label in labels}):
  try:
   result=future.result();results.append(result);print(json.dumps(result),flush=True)
  except Exception as error:print(json.dumps(dict(error=str(error))),flush=True)
Path('/tmp/opencode/dense-all-latest-status.json').write_text(json.dumps(results,indent=2))
