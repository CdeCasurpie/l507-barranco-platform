exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
code=f'''
import pathlib,subprocess,json,os
assert (pathlib.Path.home()/'L507_011.txt').is_file()
assert {macs['L507_011']!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
image='sha256:1a3c25a01680253192d7b95bb57abb3c2a680a1db8d9888c6fe533fcf08e98e0'
cmd=['docker','run','--rm','--pull=never','--network','none','--read-only','--cpus','2','--memory','2g','--memory-swap','2g','--cap-drop','ALL','--security-opt','no-new-privileges=true','--user',str(os.getuid())+':'+str(os.getgid()),'--entrypoint','python3',image,'-B','-c',
 'import pycolmap,numpy,json,shutil; print(json.dumps(dict(version=pycolmap.__version__,low_level=hasattr(pycolmap,"IncrementalTriangulator"),binaries={{n:shutil.which(n) for n in ["colmap","InterfaceCOLMAP","DensifyPointCloud","ReconstructMesh"]}})))']
p=subprocess.run(cmd,capture_output=True,text=True,timeout=60)
print('CONTAINER='+json.dumps(dict(code=p.returncode,stdout=p.stdout,stderr=p.stderr)))
'''
result=run('ssh',opts+[site['ssh_user']+'@192.0.2.65',shlex.join(['python3','-B','-c',code])],'CONTAINER=')
print(json.dumps(result,indent=2))
