"""Readable sparse overview; changes only plot limits, never reconstruction data."""
import os
os.environ.update(MPLBACKEND='Agg',MPLCONFIGDIR='/data/barranco/runtime/cache/matplotlib',OPENBLAS_NUM_THREADS='4',OMP_NUM_THREADS='4')
import argparse
import json
from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0,'/data/repos/Alineacion-point-cloud/src')
from alignexp import binary
from blockalign.palette import palette
from blockalign.storage import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    mapping=json.loads(a.map.read_text());colors=palette(mapping['manifests']);groups=[];all_xy=[];centers=[]
    for ref,S in mapping['placements'].items():
        m=mapping['manifests'][ref];points=binary.points(m['sparse']['model_uri'])
        keep=(points['length']>=3)&(points['error']>=0)&(points['error']<2)
        xyz=points['xyz'][keep][::max(1,int(keep.sum())//20000)]
        matrix=np.asarray(S);xyz=xyz@matrix[:3,:3].T+matrix[:3,3]
        xy=xyz[np.isfinite(xyz).all(axis=1),:2]
        if not len(xy):raise RuntimeError('Empty preview group')
        center=np.median(xy,axis=0);centers.append(center);all_xy.append(xy)
        groups.append((m['block_id'],xy,center,colors[ref]['hex']))
    points=np.concatenate(all_xy);centers=np.asarray(centers)
    low=np.minimum(np.quantile(points,.005,axis=0),centers.min(axis=0));high=np.maximum(np.quantile(points,.995,axis=0),centers.max(axis=0));pad=np.maximum((high-low)*.08,10)
    fig,ax=plt.subplots(figsize=(12,12))
    for label,xy,center,color in groups:
        ax.scatter(xy[:,0],xy[:,1],s=.22,color=color,alpha=.55)
        ax.text(*center,label,fontsize=10,fontweight='bold',ha='center',bbox={'facecolor':'white','alpha':.75,'edgecolor':'none','pad':1})
    ax.set_xlim(low[0]-pad[0],high[0]+pad[0]);ax.set_ylim(low[1]-pad[1],high[1]+pad[1]);ax.set_aspect('equal');ax.grid(alpha=.2)
    ax.set_title(str(len(groups))+' manzanas alineadas — vista sparse');ax.set_xlabel('Este local (m)');ax.set_ylabel('Norte local (m)')
    fig.text(.5,.02,'Vista de revisión: tracks ≥3, reproyección <2 px; límites robustos. Las nubes originales no se modifican.',ha='center',fontsize=8)
    a.output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.output,dpi=180,bbox_inches='tight');plt.close(fig)
    write(a.output.with_suffix('.json'),{'map_revision':mapping['id'],'blocks':len(groups),'operation':'visualization only; no cloud modification',
        'point_quality_filter':'track length >=3; reprojection <2px','axis_quantiles':[.005,.995],'world_origin':mapping['world_origin']})


if __name__=='__main__':main()
