"""Explicitly authorized removal of exactly two verified installer archives."""
exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
code=f'''
import pathlib,json,hashlib,subprocess,shutil,time
assert (pathlib.Path.home()/'L507_019.txt').is_file()
assert {macs['L507_019']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
images=['sha256:1a3c25a01680253192d7b95bb57abb3c2a680a1db8d9888c6fe533fcf08e98e0','sha256:9679fd9e51dac6b80cd7fdd75d43b3976c783c81393c25f407e24e14bd127042']
for image in images:subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,check=True,timeout=15)
cache=pathlib.Path('/data/photogrammetry/.lab-deploy/cache')
targets=[('b6297c878cef512ffc4179c952505d7f10db63aa4730f4feced96c8ff5260370',5852630528),('8ba01eab5461c3f45f94fe524c97bcaae7377a431b530f137daed783d3ea2416',6484233728)]
verified=[]
for digest,size in targets:
 p=cache/digest;assert p.is_file() and not p.is_symlink()
 s=p.stat();assert s.st_size==size and s.st_nlink==1
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 assert h.hexdigest()==digest
 verified.append(dict(path=str(p),bytes=size,sha256=digest,inode=s.st_ino))
audit=pathlib.Path('/data/photogrammetry/.lab-deploy/authorized-installer-cleanup-'+str(int(time.time()))+'.json')
report=dict(authorized=True,scope='Two cached installer archives only; installed images preserved',
 targets=verified,free_before=shutil.disk_usage('/data').free,completed=False)
audit.write_text(json.dumps(report,indent=2))
for entry in verified:
 p=pathlib.Path(entry['path']);assert p.stat().st_ino==entry['inode']
 p.unlink()
for image in images:subprocess.run(['docker','image','inspect',image],stdout=subprocess.DEVNULL,check=True,timeout=15)
report.update(completed=True,free_after=shutil.disk_usage('/data').free)
audit.write_text(json.dumps(report,indent=2))
print('FREED026='+json.dumps(report))
'''
result=run('ssh',opts+[site['ssh_user']+'@192.0.2.63',shlex.join(['python3','-B','-c',code])],'FREED026=')
Path('/tmp/opencode/026-installers-cleanup-result.json').write_text(json.dumps(result,indent=2))
print(json.dumps(dict(completed=result['completed'],freed_gib=(result['free_after']-result['free_before'])/2**30,
 free_gib=result['free_after']/2**30),indent=2))
