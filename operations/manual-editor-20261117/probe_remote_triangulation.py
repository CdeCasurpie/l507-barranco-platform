exec(open('/tmp/opencode/collect_cut020_review.py').read().split('code="import pathlib,json')[0])
macs=json.loads(Path('/home/exitoso/.lab_wake_macs.json').read_text())
opts=['-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8','-o',
 'UserKnownHostsFile=/home/exitoso/lab-deploy/.state/known_hosts /home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115/known_hosts']
code=f'''
import pathlib,subprocess,json,shutil
assert (pathlib.Path.home()/'L507_011.txt').is_file()
assert {macs['L507_011']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
paths=set()
for root in ['/data','/opt',str(pathlib.Path.home())]:
 p=pathlib.Path(root)
 if p.exists():
  out=subprocess.run(['find',root,'-maxdepth','8','-path','*/bin/python*','-type','f'],capture_output=True,text=True,timeout=15)
  paths.update(out.stdout.splitlines())
  out=subprocess.run(['find',root,'-maxdepth','8','-path','*/bin/python*','-type','l'],capture_output=True,text=True,timeout=15)
  paths.update(out.stdout.splitlines())
if shutil.which('python3'):paths.add(shutil.which('python3'))
results=[]
for path in sorted(paths):
 try:
  p=subprocess.run([path,'-B','-c','import pycolmap,numpy; print(pycolmap.__version__); print(hasattr(pycolmap,"IncrementalTriangulator"))'],capture_output=True,text=True,timeout=15)
  results.append(dict(python=path,ok=p.returncode==0,output=p.stdout.strip()))
 except (OSError,subprocess.TimeoutExpired):pass
print('PROBE='+json.dumps(results))
'''
result=run('ssh',opts+[site['ssh_user']+'@192.0.2.65',shlex.join(['python3','-B','-c',code])],'PROBE=')
Path('/tmp/opencode/remote-triangulation-probe.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result),flush=True)
