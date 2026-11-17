"""Bounded mesh-only comparison; original geometry and camera poses preserved."""
import fcntl,hashlib,json,shutil,signal,sys,time
from pathlib import Path
from phone_worker import PhoneWorker
root=Path(sys.argv[1])
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 return h.hexdigest()
with Path('/data/photogrammetry/.lab-deploy/reconstruction.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 w=PhoneWorker(root,'refine-trial')
 signal.signal(signal.SIGTERM,lambda *_:setattr(w,'cancelled',True))
 signal.signal(signal.SIGINT,lambda *_:setattr(w,'cancelled',True))
 try:
  out=root/'outputs'/('cuadra-'+w.assignment['block_id'])/w.experiment/'mvs'
  chunk=out/'chunks/000';source=chunk/'scene_mesh.ply';scene=chunk/'scene_dense.mvs'
  images=chunk/'images';assert source.is_file() and scene.is_file() and images.is_dir()
  original=sha(source);scene_hash=sha(scene)
  trial=root/'refine-trial';trial.mkdir()
  (trial/'images').symlink_to(images,target_is_directory=True)
  t=w.sample();assert t['data_free_gib']>=52 and t['ram_available_gib']>=40
  variants=[]
  for name,holes in [('refined_no_fill',0),('refined_small_holes',20)]:
   directory=trial/name;directory.mkdir()
   (directory/'images').symlink_to(images,target_is_directory=True)
   # RefineMesh documents mesh input as mutable: pass only our disposable copy.
   copied=directory/'input_copy.ply';shutil.copy2(source,copied)
   output=directory/'result.ply'
   args=['RefineMesh','-w',str(directory),'-i',str(scene),'-m',str(copied),
    '-o',str(output),'--cuda-device','-2','--max-threads','4',
    '--resolution-level','1','--min-resolution','640','--max-views','4',
    '--decimate','1','--close-holes',str(holes),'--scales','2',
    '--max-face-area','64','--reduce-memory','1','--regularity-weight','0.2']
   w.command(name,'reconstruction',args,gpu=True,timeout=2*3600)
   assert output.is_file() and output.stat().st_size>0
   assert sha(source)==original and sha(scene)==scene_hash
   variants.append(dict(name=name,path=str(output),sha256=sha(output),bytes=output.stat().st_size,
    close_holes=holes,resolution_level=1,source_sha256=original))
   (trial/'comparison.json').write_text(json.dumps(dict(variants=variants,original=str(source),
    original_sha256=original,camera_scene_unchanged=True,geometry_original_preserved=True,
    hole_fill_warning='Boundary-size threshold, not meters; may close genuine openings',
    complete=False),indent=2))
  report=json.loads((trial/'comparison.json').read_text());report['complete']=True
  (trial/'comparison.json').write_text(json.dumps(report,indent=2))
  w.save(state='completed',stage='refine-comparison-complete',output=str(trial),finished_at=time.time())
 except BaseException as e:
  w.save(state='failed',error=str(e),finished_at=time.time());raise
