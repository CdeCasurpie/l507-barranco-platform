import hashlib
import json
from pathlib import Path
import subprocess
import sys
root=Path(sys.argv[1])
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024**2),b''):h.update(block)
    return h.hexdigest()
cfg=json.loads((root/'mesh-existing.json').read_text())
source=Path(cfg['source_mvs'])
receipt=json.loads((source/'dense-batches.json').read_text())
assert sha(source/'scene_dense.ply')==receipt['cloud_sha256']
scenes=sorted((source/'chunks').glob('*/scene_dense.mvs'))
assert len(scenes)==receipt['batches']==40
destination=root/'mesh-existing'
destination.mkdir()
results=[]
for scene in scenes:
    chunk=destination/scene.parent.name;chunk.mkdir()
    (chunk/'images').symlink_to(scene.parent/'images',target_is_directory=True)
    output=chunk/'mesh.ply'
    native=scene.parent/'scene_dense.ply'
    assert native.is_file()
    command=['ReconstructMesh','-w',str(chunk),'-i',str(scene),'-p',str(native),'-o',str(output),
        '--cuda-device','-2','--max-threads','4','--min-point-distance','0',
        '--constant-weight','0','--decimate','1','--remove-spurious','0',
        '--remove-spikes','0','--close-holes','0','--smooth','0','--crop-to-roi','0','--archive-type','1']
    with (chunk/'mesh.log').open('ab') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True)
    assert output.is_file() and output.stat().st_size>0
    digest=sha(output)
    results.append(dict(chunk=scene.parent.name,path=str(output),bytes=output.stat().st_size,sha256=digest))
    (destination/'progress.json').write_text(json.dumps(dict(completed=len(results),total=40,meshes=results),indent=2))
    print('MESH026',len(results),'/40',output,flush=True)
(destination/'manifest.json').write_text(json.dumps(dict(meshes=results,complete=True,
    source_dense_sha256=receipt['cloud_sha256'],coordinate_frame='026 native unchanged',
    method='OpenMVS Delaunay; per-chunk meshes, overlap retained; no hole filling'),indent=2))
