exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import subprocess,uuid
launch=json.loads(Path('/tmp/opencode/dense-019-launch.json').read_text())
remote=launch['output']+'/mvs'
code=f'''
import pathlib,json,hashlib
assert (pathlib.Path.home()/'L507_004.txt').is_file()
assert {macs['L507_004']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({remote!r})
manifest=json.loads((root/'mesh-chunks.json').read_text())
assert manifest['complete']
rows=[]
for name in manifest['meshes']:
 p=pathlib.Path(name);h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(8*1024**2),b''):h.update(block)
 rows.append(dict(path=str(p.relative_to(root)),bytes=p.stat().st_size,sha256=h.hexdigest()))
print('MESHES='+json.dumps(rows))
'''
rows=run('ssh',opts+[site['ssh_user']+'@192.0.2.44',shlex.join(['python3','-B','-c',code])],'MESHES=')
dest=Path('/data/barranco/review')/('019-union-render-'+uuid.uuid4().hex)
dest.mkdir();raw=dest/'raw';raw.mkdir()
(dest/'source-manifest.json').write_text(json.dumps(rows,indent=2))
filelist=dest/'files.txt';filelist.write_text('\n'.join(r['path'] for r in rows)+'\n')
original_spawn=pexpect.spawn
def patient_spawn(*args,**kwargs):
 kwargs['timeout']=1800
 return original_spawn(*args,**kwargs)
pexpect.spawn=patient_spawn
print('COLLECTING',len(rows),'meshes',sum(r['bytes'] for r in rows),'bytes',dest,flush=True)
run('rsync',['-a','--partial','--files-from='+str(filelist),'-e',shlex.join(['ssh']+opts),
 site['ssh_user']+'@192.0.2.44:'+remote+'/',str(raw)+'/'])
for row in rows:
 p=raw/row['path'];assert p.stat().st_size==row['bytes']
 with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256']
Path('/tmp/opencode/019-render-delivery.json').write_text(json.dumps(dict(directory=str(dest)),indent=2))
subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-join019-'+uuid.uuid4().hex[:10],
 '-p','MemoryMax=36G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-E','OPENBLAS_NUM_THREADS=4','-E','OMP_NUM_THREADS=4',
 '/data/barranco/runtime/alignment313/bin/python','-B','/tmp/opencode/join019_preview.py',str(dest)],check=True)
subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-render019-'+uuid.uuid4().hex[:10],
 '-p','MemoryMax=24G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 'blender','--background','--factory-startup','--threads','4','--python-exit-code','1',
 '--python','/tmp/opencode/render019_blender.py','--',str(dest)],check=True)
print('RENDER_READY',dest,flush=True)
