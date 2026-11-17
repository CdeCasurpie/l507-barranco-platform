import json
from pathlib import Path
import subprocess
import sys
root=Path(sys.argv[1])
meshes=[]
for scene in sorted((root/'chunks').glob('*/scene_dense.mvs')):
    directory=scene.parent
    with (directory/'mesh.log').open('ab') as log:
        subprocess.run(['ReconstructMesh','-w',str(directory),str(scene),
                        '-p',str(directory/'scene_dense.ply'),'-o','scene_mesh.mvs',
                        '--max-threads','4'],stdout=log,stderr=subprocess.STDOUT,check=True)
    mesh=directory/'scene_mesh.ply'
    assert mesh.is_file() and mesh.stat().st_size>0
    meshes.append(str(mesh))
    (root/'mesh-chunks.json').write_text(json.dumps(dict(meshes=meshes,complete=False),indent=2))
assert meshes
(root/'mesh-chunks.json').write_text(json.dumps(dict(meshes=meshes,complete=True,
    note='Separate overlapping chunk meshes in the unchanged sparse frame; not a globally fused mesh'),indent=2))
