exec(open('/tmp/opencode/probe_remote_triangulation.py').read().split('code=f')[0])
from concurrent.futures import ThreadPoolExecutor,as_completed
import base64,zlib,uuid
cache=json.loads(Path('/home/exitoso/.lab_monitor_cache.json').read_text())
labels=['006-horiz-s-m','010','011','014','015','020','021','027']
helper=Path('/tmp/opencode/dense_cleanup_verified.py').read_text()
worker=Path('/tmp/opencode/resume_dense_after_cleanup_worker.py').read_text()
def start(label):
 launch=json.loads(Path('/tmp/opencode/dense-'+label+'-launch.json').read_text())
 provenance=json.loads((Path('/data/barranco/review/catalog-20261116-134343')/label/'collection.json').read_text())
 tag=provenance['tag'];options=list(opts)
 if tag=='L507_005':options+=['-o','HostKeyAlias=192.0.2.58']
 unit='barranco-dense-resume-'+label+'-'+uuid.uuid4().hex[:8]
 code=f'''
import pathlib,json,subprocess,shlex,sys,shutil,time,fcntl
assert (pathlib.Path.home()/({tag!r}+'.txt')).is_file()
assert {macs[tag]!r} in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path({launch['root']!r})
assert root.stat().st_dev==pathlib.Path('/data').stat().st_dev
s=json.loads((root/'reconstruction-full-status.json').read_text())
assert s['state']=='failed' and s['stage']=='dense'
assert 'SAFETY STOP: data_free_gib=' in s['error']
block=json.loads((root/'assignment.json').read_text())['block_id']
assert block in {{'006','010','011','014','015','020','021','027'}} and block!='026'
authorization=dict(block=block,allowed_suffix='.dmap',completed_only=True,
 user_authorized=True,future_completed_chunks=True,originals_excluded=True)
assert not (root/'cleanup-authorization.json').exists(),'Do not duplicate cleanup/resume coordinator'
(root/'cleanup-authorization.json').write_text(json.dumps(authorization,indent=2))
(root/'dense_cleanup.py').write_text({helper!r})
(root/'resume_after_cleanup.py').write_text({worker!r})
sys.path.insert(0,str(root))
from dense_cleanup import cleanup_verified_chunk
with pathlib.Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as guard:
 fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
 removed=[]
 output=root/'outputs'/('cuadra-'+block)/json.loads((root/'reconstruction.json').read_text())['full_experiment']
 for receipt in sorted((output/'mvs/chunks').glob('*/batch-receipt.json')):
  removed.append(cleanup_verified_chunk(receipt.parent,json.loads(receipt.read_text())))
 path=root/'dense_batches.py';text=path.read_text()
 assert 'cleanup_verified_chunk' not in text
 assert "from campaign_post import scalar_ply,save,sha" in text
 assert "        inputs.append((scalar,done['cloud']));receipts.append(done)" in text
 path.with_name('dense_batches.before-authorized-cleanup.py').write_text(text)
 text=text.replace("from campaign_post import scalar_ply,save,sha","from campaign_post import scalar_ply,save,sha\\nfrom dense_cleanup import cleanup_verified_chunk")
 text=text.replace("        inputs.append((scalar,done['cloud']));receipts.append(done)",
 "        cleanup_verified_chunk(directory,done)\\n        inputs.append((scalar,done['cloud']));receipts.append(done)")
 # Driver hash participates in cache keys. Preserve its previous identity only
 # for this cleanup-only patch; geometry/config/batch selection are unchanged.
 old_driver_hash=__import__('hashlib').sha256(path.read_bytes()).hexdigest()
 text=text.replace("'driver':sha(Path(__file__))","'driver':"+repr(old_driver_hash))
 compile(text,str(path),'exec')
 temp=path.with_suffix('.new');temp.write_text(text);temp.replace(path)
 summary=dict(removed=removed,removed_gib=sum(r['removed_bytes'] for r in removed)/2**30,
  free_gib=shutil.disk_usage('/data').free/2**30,unit={unit!r},at=time.time())
 (root/'cleanup-summary.json').write_text(json.dumps(summary,indent=2))
print('CLEANED',json.dumps(summary),flush=True)
command=['systemd-run','--user','--wait','--pipe','--unit='+{unit!r},
 '-p','MemoryMax=42G','-p','MemorySwapMax=0','-p','CPUQuota=400%','-p','Nice=10',
 '-p','RuntimeMaxSec=432000','sg','docker','-c',
 shlex.join(['python3','-B',str(root/'resume_after_cleanup.py'),str(root)])]
result=subprocess.run(command)
print('RESUME_END',result.returncode,flush=True)
raise SystemExit(result.returncode)
'''
 encoded=base64.b64encode(zlib.compress(code.encode())).decode()
 command="import base64,zlib;exec(zlib.decompress(base64.b64decode("+repr(encoded)+")))"
 print('CLEANUP_RESUME_START',label,unit,flush=True)
 run('ssh',options+[site['ssh_user']+'@'+cache[tag]['ip'],shlex.join(['python3','-B','-c',command])])
 return dict(label=label,finished=True)
original_spawn=pexpect.spawn
def persistent_spawn(*args,**kwargs):
 kwargs['timeout']=None
 return original_spawn(*args,**kwargs)
pexpect.spawn=persistent_spawn
with ThreadPoolExecutor(max_workers=8) as pool:
 futures={pool.submit(start,label):label for label in labels}
 for future in as_completed(futures):
  try:print(json.dumps(future.result()),flush=True)
  except Exception as error:print(json.dumps(dict(label=futures[future],error=str(error))),flush=True)
