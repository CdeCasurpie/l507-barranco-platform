"""Read-only disk inventory; no pruning, deletion or filesystem changes."""
exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
launch=json.loads(Path('/tmp/opencode/mesh026-existing-launch.json').read_text())
code=f'''
import pathlib,subprocess,json,collections,os
assert (pathlib.Path.home()/'L507_019.txt').is_file()
assert {macs['L507_019']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
result={{}}
commands={{
 'disk':['df','-h','/data'],
 'top':['du','-x','-h','--max-depth=2','/data/photogrammetry'],
 'docker':['docker','system','df'],
 'pilot':['du','-x','-h','--max-depth=3',{launch['root']!r}],
 'campaign':['du','-x','-h','--max-depth=2','/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-026-all'],
}}
for key,cmd in commands.items():
 try:
  p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
  result[key]=dict(code=p.returncode,stdout=p.stdout[-28000:],stderr=p.stderr[-1500:])
 except subprocess.TimeoutExpired:result[key]=dict(error='timeout')
base=pathlib.Path('/data/photogrammetry')
candidates=[];seen=set()
for folder in [base/'incoming',base/'campaigns',base/'.lab-deploy']:
 for current,dirs,files in os.walk(folder,followlinks=False):
  dirs[:]=[d for d in dirs if d not in ['frames','masks','undistorted_masks','python-deps','models','.git']]
  for name in files:
   p=pathlib.Path(current)/name
   if p.is_symlink():continue
   try:s=p.stat()
   except OSError:continue
   if not any(token in name.lower() for token in ['.part','.tmp','snapshot','interrupted','failed','cache','.tar','.zip']):continue
   if s.st_size>=50*1024**2:
    candidates.append(dict(path=str(p),bytes=s.st_size,links=s.st_nlink))
result['named_cache_candidates']=sorted(candidates,key=lambda x:-x['bytes'])[:100]
print('AUDIT026='+json.dumps(result))
'''
d=run('ssh',opts+[site['ssh_user']+'@192.0.2.63',shlex.join(['python3','-B','-c',code])],'AUDIT026=')
Path('/tmp/opencode/026-freeable-audit.json').write_text(json.dumps(d,indent=2))
for k,v in d.items():print(k,json.dumps(v,ensure_ascii=False),flush=True)
