"""Package completed runs only, using snapshotted user-saved placements."""
exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
import base64,zlib,subprocess,uuid,time,shutil
state=Path('/home/exitoso/home/barranco-roi/state/alignment')
selection=json.loads((state/'alignment-selection.json').read_text())['reconstructions']
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
status=json.loads(Path('/tmp/opencode/dense-all-latest-status.json').read_text())
ready={r['label'] for r in status if r.get('state')=='completed' and r['label']!='026-parque'}
if len(sys.argv)>1:
    requested=set(sys.argv[1:])
    assert requested<=ready,'Requested run is not confirmed complete'
    ready=requested
base=Path('/data/barranco/review')/('mesh-delivery-'+str(int(time.time())))
base.mkdir();plan=[]
for label in sorted(ready):
    block='006' if label=='006-horiz-s-m' else label
    records=[json.loads((state/'reconstructions'/(key+'.json')).read_text()) for key in selection]
    record=next(r for r in records if r['block']==block)
    sessions=[json.loads(p.read_text()) for p in (state/'sessions').glob('*.json')]
    sessions=[s for s in sessions if s['reconstruction']==record['id']]
    if not sessions:raise RuntimeError('Missing saved placement for '+label)
    session=max(sessions,key=lambda s:s['created_at'])
    launch_file='pilot022-dense-launch.json' if label=='022' else 'dense-'+label+'-launch.json'
    launch=json.loads(Path('/tmp/opencode',launch_file).read_text())
    provenance=json.loads((Path('/data/barranco/review/catalog-20261116-134343')/label/'collection.json').read_text())
    plan.append(dict(label=label,block=block,record=record,session=session,launch=launch,tag=provenance['tag']))
(base/'plan.json').write_text(json.dumps(plan,indent=2))
Path('/tmp/opencode/completed-mesh-delivery.json').write_text(json.dumps(dict(directory=str(base)),indent=2))
print('PACKAGING',base,[p['label'] for p in plan],flush=True)
color=Path('/tmp/opencode/color019_dense_vertices.py').read_text().replace('total=26','total=len(manifest["meshes"])')
original_spawn=pexpect.spawn
def patient_spawn(*args,**kwargs):
    kwargs['timeout']=None
    return original_spawn(*args,**kwargs)
pexpect.spawn=patient_spawn
for item in plan:
    label=item['label'];launch=item['launch'];tag=item['tag'];options=list(opts)
    if tag=='L507_005':options+=['-o','HostKeyAlias=192.0.2.58']
    ip=cache[tag]['ip'];dest=base/label;dest.mkdir()
    try:
        assert shutil.disk_usage(base).free>55*2**30
        expected=None
        model=Path(item['record']['model'])
        if (model.parent/'request.json').exists():
            expected=json.loads((model.parent/'request.json').read_text())['draft'].get('id')
        code=f'''
import pathlib,json,subprocess,sys,hashlib,os,fcntl,signal,time
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
s=json.loads((root/'reconstruction-full-status.json').read_text());assert s['state']=='completed'
q=json.loads((root/'job/request.json').read_text())
if {expected!r} is not None:assert q['draft'].get('id')=={expected!r},'Wrong manually corrected revision'
out=pathlib.Path({launch['output']!r})/'mvs'
manifest=out/'colored-chunks/manifest.json'
if not manifest.exists():
 assert not (out/'colored-chunks').exists(),'Partial coloring requires explicit resume'
 tool=root/'package_vertex_rgb.py';assert not tool.exists()
 tool.write_text({color!r})
 sys.path.insert(0,str(root))
 from phone_worker import PhoneWorker
 class ColorWorker(PhoneWorker):
  def docker_args(self,stage,role,argv,gpu=True):
   name,token,args=super().docker_args(stage,role,argv,gpu)
   index=args.index(self.spec['images'][role]['tag'])
   args[index:index]=['-e',f'PYTHONPATH={{self.root}}/python-deps']
   return name,token,args
 with pathlib.Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
  fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
  worker=ColorWorker(root,'package-rgb')
  worker.command('package-rgb','reconstruction',['python3','-B',str(tool),str(out)],gpu=False,timeout=12*3600)
  worker.save(state='completed')
m=json.loads(manifest.read_text());assert m['complete'] and m['geometry_unchanged']
print('PACKAGE='+json.dumps(dict(remote=str(out/'colored-chunks'),meshes=m['meshes'])))
'''
        encoded=base64.b64encode(zlib.compress(code.encode())).decode()
        bootstrap="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
        # sg makes Docker group membership explicit without changing system config.
        remote=run('ssh',options+[site['ssh_user']+'@'+ip,
            shlex.join(['sg','docker','-c',shlex.join(['python3','-B','-c',bootstrap])])],'PACKAGE=')
        files=dest/'files.txt';files.write_text('\n'.join(m['chunk']+'.ply' for m in remote['meshes'])+'\n')
        raw=dest/'raw';raw.mkdir()
        run('rsync',['-a','--partial','--files-from='+str(files),'-e',shlex.join(['ssh']+options),
            site['ssh_user']+'@'+ip+':'+remote['remote']+'/',str(raw)+'/'])
        meshes=[]
        for m in remote['meshes']:
            p=raw/(m['chunk']+'.ply')
            with p.open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==m['sha256']
            meshes.append(dict(filename=p.name,sha256=m['sha256']))
        (dest/'export-plan.json').write_text(json.dumps(dict(block=item['block'],matrix=item['session']['matrix'],
            session_id=item['session']['id'],meshes=meshes,source_record=item['record']),indent=2))
        subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-export-'+label+'-'+uuid.uuid4().hex[:8],
            '-p','MemoryMax=24G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
            '-E','OPENBLAS_NUM_THREADS=4','-E','OMP_NUM_THREADS=4',
            '/data/barranco/runtime/alignment313/bin/python','-B','/tmp/opencode/export_aligned_mesh.py',str(dest)],check=True)
        subprocess.run(['systemd-run','--user','--wait','--pipe','--unit=barranco-render-'+label+'-'+uuid.uuid4().hex[:8],
            '-p','MemoryMax=24G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
            'blender','--background','--factory-startup','--threads','4','--python-exit-code','1',
            '--python','/tmp/opencode/render_aligned_mesh.py','--',str(dest)],check=True)
        print('BLOCK_DELIVERED',label,dest,flush=True)
    except Exception as error:
        (dest/'error.json').write_text(json.dumps(dict(error=str(error),label=label),indent=2))
        print('PACKAGE_FAILED',label,str(error),flush=True)
print('PACKAGE_BATCH_FINISHED',base,flush=True)
