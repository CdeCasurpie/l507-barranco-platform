"""Real Blender round-trip: 15 independently editable objects, geometry and RGB."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import numpy as np
from simplify_meshes import save_mesh
from package_simplified_blocks import prepare

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which('blender'),'Blender executable required')
class BlockDeliveryTests(unittest.TestCase):
    def test_fifteen_unique_meshes_survive_compressed_blend_roundtrip(self):
        blocks=['001','002','003','004','005','007','008','009','012','013','017','018','023','024','025']
        with tempfile.TemporaryDirectory(prefix='barranco-delivery-',dir='/tmp/opencode') as d:
            root=Path(d)
            meshes=root/'meshes'
            meshes.mkdir()
            records={}
            for i,block in enumerate(blocks):
                xyz=np.array([[i*3.,0,0],[i*3.+1,0,0],[i*3.,1,0]],float)
                faces=np.array([[0,1,2]],'i4')
                rgb=np.array([[20+i,80,150],[128,20+i,210],[255,0,40+i]],'u1')
                path=meshes/('manzana_'+block+'_simplified_70pct.ply')
                stats=save_mesh(path,xyz,faces,rgb)
                records[block]=dict(mesh=str(path),**stats)
            (root/'manifest.json').write_text(json.dumps(dict(completed=15,blocks=records)))
            prepare(root)
            blend=root/'barranco_15_manzanas_70pct.blend'
            commands=[['blender','--background','--factory-startup'],['blender','--background',str(blend)]]
            for prefix,mode in zip(commands,['build','audit']):
                result=subprocess.run(prefix+['--threads','2','--python-exit-code','1','--python',str(ROOT/'blender_blocks.py'),'--',str(root),mode],
                                      capture_output=True,text=True,timeout=90)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                self.assertTrue(blend.is_file(),result.stdout+result.stderr)
            audit=json.loads((root/'blender-audit.json').read_text())
            self.assertEqual(audit['objects'],15)
            self.assertEqual(audit['unique_mesh_data'],15)
            self.assertTrue(audit['geometry_hashes_verified'])
            self.assertTrue(audit['colors_verified'])
            self.assertTrue(all(b['mesh_users']==1 and b['instance_type']=='NONE' for b in audit['blocks']))


if __name__=='__main__':
    unittest.main()
