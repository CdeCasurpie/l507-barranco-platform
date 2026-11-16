"""Integration fixture: same reconstruction in two namespaces must yield identity.

This is a numerical compatibility test, not evidence of two real blocks aligned.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

REPO=Path('/data/repos/Alineacion-point-cloud')
sys.path.insert(0,str(REPO/'src'))
os.environ.update(OMP_NUM_THREADS='8',OPENBLAS_NUM_THREADS='8',MKL_NUM_THREADS='8')
os.environ['PATH']='/data/barranco/runtime/alignment313/bin:'+os.environ['PATH']
from blockalign import Workspace
from blockalign.storage import write
from blockalign.contracts import Policy,digest
from blockalign.artifacts import require_job
from blockalign.audit import audit_block
from blockalign.pairwise import align_pair

root=Path('/data/barranco/compatibility/identity-pair')
root.mkdir(exist_ok=True)
context=root/'local-context.json';write(context,{'backend':'local','pid':os.getpid()})
os.environ['BLOCKALIGN_LOCAL_CONTEXT']=str(context)
require_job()
workspace=Workspace.open(root/'workspace')
original=json.loads(Path('/data/barranco/alignment-inputs/barranco-full-v1/025/barranco_4k_2fps_combined_v1/block.json').read_text())
fixture=copy.deepcopy(original);fixture['block_id']='fixture-025'
fixture['provenance']['test_only']='same reconstruction, different namespace; not another real block'
refs=[workspace.register_block(m) for m in [original,fixture]]
scratch=Path(tempfile.mkdtemp(prefix='scratch-',dir=root))
audits=[]
for ref in refs:
    summary,path,hit=audit_block(workspace.root,ref,workspace.block(ref),scratch);audits.append((summary,path))
policy=Policy.parse({'max_source_views':8,'max_target_views':4,'max_pairs':32}).to_dict()
result,hit=align_pair(workspace.root,audits[1][0],audits[0][0],audits[1][1],audits[0][1],policy,scratch,
    digest({'fixture':'identity-namespaces-v1','runtime':'colmap313'}),8)
matrix=np.asarray(result['target_from_source'])
if not np.allclose(matrix,np.eye(4),atol=1e-3,rtol=0):raise RuntimeError('Identity fixture transformation failed')
receipt={'fixture':'same reconstruction in two operation-local namespaces','not_a_real_two_block_alignment':True,
         'matrix':matrix.tolist(),'registered_bridges':result['registered'],'holdout':result['holdout'],
         'measurement_id':result['id'],'passed':True}
write(root/'result.json',receipt);print(json.dumps(receipt,indent=2))
