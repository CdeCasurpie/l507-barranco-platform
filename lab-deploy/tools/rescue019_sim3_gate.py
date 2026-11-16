"""Sim3/partition gate using saved PnP only; no model writing or BA."""
import itertools
import json
from pathlib import Path
import time
import numpy as np
import pycolmap
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, maximum_flow, breadth_first_order

BASE=Path('/data/barranco/review/diagnostics/019-pnp-20261116')
MODEL=Path('/data/barranco/review/catalog-20261116-134343/019-corte-10fps/colmap/sparse/0')
OUT=Path('/data/barranco/review/diagnostics/019-sim3-rescue-20261116')


def fit_similarity(x,y):
    xc,yc=x-x.mean(axis=0),y-y.mean(axis=0)
    u,d,vt=np.linalg.svd(yc.T@xc/len(x))
    signs=np.ones(3)
    signs[-1]=np.linalg.det(u@vt)
    rotation=u@np.diag(signs)@vt
    scale=float(np.sum(d*signs)/np.mean(np.sum(xc*xc,axis=1)))
    t=y.mean(axis=0)-scale*rotation@x.mean(axis=0)
    return scale,rotation,t


def apply(t,x):
    s,r,p=t
    return s*(r@np.asarray(x).T).T+p


def assess(rows,step):
    rows=sorted(rows,key=lambda v:v['query_seconds'])
    training=[v for v in rows if v['role']=='diagnostic']
    held=[v for v in rows if v['role']=='reserved_validation']
    x=np.array([v['original_center'] for v in training])
    y=np.array([v['center'] for v in training])
    singular=np.linalg.svd(x-x.mean(axis=0),compute_uv=False)
    ratio=float(singular[1]/singular[0])
    # Three independent queries is the algebraic minimum, not a robust consensus.
    transform=fit_similarity(x,y)
    residuals=np.linalg.norm(apply(transform,x)-y,axis=1)
    validation=[dict(seconds=v['query_seconds'],residual=float(np.linalg.norm(
        apply(transform,np.array(v['original_center']))-np.array(v['center']))),
        inliers=v['inliers']) for v in held]
    s,r,t=transform
    result=dict(training_views=[v['query_seconds'] for v in training],
        heldout_views=validation,independent_training_views=len(training),
        source_singular_values=singular.tolist(),source_second_to_first_ratio=ratio,
        target_second_to_first_ratio=float(np.linalg.svd(y-y.mean(axis=0),compute_uv=False)[1]/
                                            np.linalg.svd(y-y.mean(axis=0),compute_uv=False)[0]),
        scale=s,rotation=r.tolist(),translation=t.tolist(),
        training_residuals=residuals.tolist(),
        training_residuals_in_median_steps=(residuals/step).tolist(),
        heldout_residuals_in_median_steps=[v['residual']/step for v in validation],
        robust_consensus_possible=len(training)>=4,
        geometry_pass=ratio>=0.05,
        residuals_pass=bool(validation) and max(v['residual'] for v in validation)<=step,
        accepted=False)
    result['accepted']=result['geometry_pass'] and result['residuals_pass'] and result['robust_consensus_possible']
    return transform,result


def main():
    OUT.mkdir(exist_ok=False)
    inputs=json.loads((BASE/'results.json').read_text())
    r=pycolmap.Reconstruction(str(MODEL))
    timed={}
    for im in r.images.values():
        timed[int(Path(im.name).stem.split('_')[1])/1e6]=im
    times=sorted(timed)
    ids=[timed[t].image_id for t in times];index={i:k for k,i in enumerate(ids)}
    centers=np.array([timed[t].projection_center() for t in times])
    speed=np.linalg.norm(np.diff(centers,axis=0),axis=1)/np.diff(times)
    step=float(np.median(speed[speed>0])*.5)
    records=[v for v in inputs['tests'] if v['model']=='cut10fps' and
             v['cut']==[247.,247.5] and v['reference_subset']=='all' and v['seed']==0 and v['status']=='estimated']
    transforms={};reports={}
    for direction in ['forward','reverse']:
        transforms[direction],reports[direction]=assess([v for v in records if v['direction']==direction],step)
    covariance=np.zeros((len(ids),len(ids)),dtype=np.int32)
    track_sets=[]
    for point in r.points3D.values():
        members=np.array(sorted({index[el.image_id] for el in point.track.elements}),dtype=int)
        covariance[np.ix_(members,members)]+=1
        track_sets.append(members)
    np.fill_diagonal(covariance,0)
    graph_summaries={}
    for threshold in [1,10,30,100]:
        n,labels=connected_components(csr_matrix(covariance>=threshold),directed=False)
        graph_summaries[str(threshold)]=dict(components=int(n),
                                           largest_sizes=sorted(np.bincount(labels).tolist(),reverse=True)[:10])
    n=len(ids)
    anchors_left=[index[timed[t].image_id] for t in [245.5,246.,246.5,247.]]
    anchors_right=[index[timed[t].image_id] for t in [247.5,248.,248.5,249.]]
    capacity=np.zeros((n+2,n+2),dtype=np.int64)
    capacity[:n,:n]=covariance
    big=int(covariance.sum()+1)
    for i in anchors_left:capacity[n,i]=big;capacity[i,n]=big
    for i in anchors_right:capacity[n+1,i]=big;capacity[i,n+1]=big
    flow=maximum_flow(csr_matrix(capacity),n,n+1)
    residual=csr_matrix(capacity)-flow.flow
    residual.data=(residual.data>0).astype(np.int8);residual.eliminate_zeros()
    reachable=breadth_first_order(residual,n,directed=True,return_predecessors=False)
    mask=np.zeros(n,dtype=bool)
    mask[reachable[reachable<n]]=True
    partitions={'temporal_before_cut':np.array(times)<=247.,'graph_mincut_left':mask}
    partition_reports={}
    for name,mask in partitions.items():
        crossing=sum(bool(np.any(mask[m]) and np.any(~mask[m])) for m in track_sets)
        pairs=np.argwhere(np.triu(covariance*(mask[:,None]!=mask[None,:]),k=1)>0)
        strongest=sorted([(int(covariance[i,j]),int(i),int(j)) for i,j in pairs],reverse=True)[:10]
        virtual=centers.copy()
        # Map the right partition into the left reference frame using forward PnP.
        virtual[~mask]=apply(transforms['forward'],centers[~mask])
        new_speed=np.linalg.norm(np.diff(virtual,axis=0),axis=1)/np.diff(times)
        ranked=np.argsort(new_speed)[-10:][::-1]
        partition_reports[name]=dict(left_cameras=int(mask.sum()),right_cameras=int((~mask).sum()),
            crossing_tracks=int(crossing),crossing_covisibility_edges=len(pairs),
            strongest_crossing_edges=[dict(shared_points=v,start=times[i],end=times[j]) for v,i,j in strongest],
            relative_transform_gate_pass=reports['forward']['accepted'],
            independently_movable_without_shared_point_conflicts=crossing==0,
            virtual_top_jumps=[dict(start=times[i],end=times[i+1],speed=float(new_speed[i]),
                                   ratio_to_baseline_median=float(new_speed[i]/(step*2))) for i in ranked],
            note='Virtual camera centers only. Shared points cannot be assigned two different transforms.')
    inverse_errors=np.linalg.norm(apply(transforms['reverse'],apply(transforms['forward'],centers))-centers,axis=1)
    result=dict(model=str(MODEL),created_at=time.time(),median_step_05s=step,
        gates_fixed_before_evaluation=dict(min_source_second_first_singular_ratio=.05,
                                          min_independent_training_views_for_robust_fit=4,
                                          max_heldout_error_median_steps=1),
        sim3=reports,graph=graph_summaries,partitions=partition_reports,
        bidirectional_composition_error_median=float(np.median(inverse_errors)),
        bidirectional_composition_error_p95=float(np.percentile(inverse_errors,95)),
        decision='STOP_NO_CANDIDATE',
        reason='Saved PnP has only three independent training cameras per direction; assess conditioning and crossing tracks before any model transformation.',
        originals_modified=False,pnp_repeated=False,matching_repeated=False,ba_executed=False)
    (OUT/'analysis.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':
    main()
