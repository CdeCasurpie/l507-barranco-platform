"""Diagnostic poses only. Never writes COLMAP models, cameras or databases."""
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np
import pycolmap

ROOT = Path('/data/barranco/review/diagnostics/019-pnp-20261116')
MODELS = {
    'original': Path('/data/barranco/review/catalog-20261116-134343/019/colmap/sparse/0'),
    'cut10fps': Path('/data/barranco/review/catalog-20261116-134343/019-corte-10fps/colmap/sparse/0')}


def hashfile(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4194304), b''):
            h.update(chunk)
    return h.hexdigest()


def candidates(reconstruction, bytime, pairs, query_time, refs, excluded):
    query = bytime[query_time]
    choices = {}
    for pair in pairs:
        a,b = pair['left_seconds'],pair['right_seconds']
        if a == query_time and b in refs:
            reference_time = b
            matches = [(j,i) for i,j in pair['matches']]
        elif b == query_time and a in refs:
            reference_time = a
            matches = pair['matches']
        else:
            continue
        reference = bytime[reference_time]
        for ri,qi in matches:
            observation = reference.points2D[ri]
            if not observation.has_point3D():
                continue
            point_id = observation.point3D_id
            point = reconstruction.points3D[point_id]
            ids = {el.image_id for el in point.track.elements}
            refids = {bytime[t].image_id for t in refs}
            if len(ids & refids) < 2 or ids & excluded or point.error > 4 or len(ids) < 3:
                continue
            choices.setdefault(qi,set()).add(point_id)
    unique = {qi:next(iter(ids)) for qi,ids in choices.items() if len(ids)==1}
    counts = {}
    for point in unique.values():
        counts[point] = counts.get(point,0)+1
    unique = {qi:point for qi,point in unique.items() if counts[point]==1}
    keys = sorted(unique)
    xy = np.asarray([query.points2D[qi].xy for qi in keys], dtype=float).reshape(-1,2)
    xyz = np.asarray([reconstruction.points3D[unique[qi]].xyz for qi in keys], dtype=float).reshape(-1,3)
    return xy,xyz


def estimate(reconstruction, query, xy, xyz, seed):
    base = dict(candidates=len(xy),seed=seed)
    if len(xy)<12:
        return dict(base,status='insufficient_independent_candidates')
    pycolmap.set_random_seed(seed)
    camera0 = reconstruction.cameras[query.camera_id]
    camera = pycolmap.Camera(model=camera0.model,width=camera0.width,
                            height=camera0.height,params=np.array(camera0.params).copy())
    options = pycolmap.AbsolutePoseEstimationOptions()
    options.ransac.max_error = 4.
    options.ransac.max_num_trials = 5000
    refinement = pycolmap.AbsolutePoseRefinementOptions()
    refinement.refine_focal_length = False
    refinement.refine_extra_params = False
    result = pycolmap.estimate_and_refine_absolute_pose(xy,xyz,camera,options,refinement)
    if result is None:
        return dict(base,status='pnp_failed')
    pose = result['cam_from_world']
    mask = np.asarray(result['inlier_mask'], dtype=bool)
    inliers = xy[mask]
    width,height = camera.width,camera.height
    cells = {(min(3,int(x/width*4)),min(3,int(y/height*4))) for x,y in inliers}
    normalized = inliers/np.array([width,height])
    spread = np.linalg.eigvalsh(np.cov(normalized.T)) if len(inliers)>2 else np.zeros(2)
    singular = np.linalg.svd(xyz[mask]-np.mean(xyz[mask],axis=0),compute_uv=False)
    center = -pose.rotation.matrix().T@pose.translation
    oldcenter = np.asarray(query.projection_center())
    rotation_delta = pose.rotation.matrix()@query.cam_from_world.rotation.matrix().T
    angle = math.degrees(math.acos(np.clip((np.trace(rotation_delta)-1)/2,-1,1)))
    camxyz = (pose.rotation.matrix()@xyz[mask].T).T+pose.translation
    projected = np.asarray([camera.img_from_cam(v[:2]/v[2]) for v in camxyz])
    errors = np.linalg.norm(projected-xy[mask],axis=1)
    return dict(base,status='estimated',inliers=int(mask.sum()),inlier_ratio=float(mask.mean()),
                grid_cells_4x4=len(cells),normalized_xy_cov_eigenvalues=spread.tolist(),
                point_singular_ratios=(singular/max(singular[0],1e-12)).tolist(),
                center=center.tolist(),original_center=oldcenter.tolist(),
                center_change=float(np.linalg.norm(center-oldcenter)),rotation_change_deg=angle,
                reprojection_median_px=float(np.median(errors)),reprojection_p95_px=float(np.percentile(errors,95)),
                positive_depth_fraction=float(np.mean(camxyz[:,2]>0)))


def main():
    assert pycolmap.__version__ == '3.11.1'
    inputs = json.loads((ROOT/'inputs.json').read_text())
    output = dict(started_at=time.time(),pycolmap=pycolmap.__version__,max_error_px=4,
                  inputs_sha256=hashfile(ROOT/'inputs.json'),tests=[],
                  policy='Reference points must have >=2 reference views, >=3 total track views, error<=4px, no selected opposite-window observations. Intrinsics fixed. No Sim3 or model write.')
    for label,path in MODELS.items():
        for name,expected in inputs[label]['model_hashes'].items():
            assert hashfile(path/name)==expected,'Remote/local model mismatch'
        r = pycolmap.Reconstruction(str(path))
        bytime = {}
        for im in r.images.values():
            stem=Path(im.name).stem
            seconds=(int(stem.rsplit('_',1)[1])-1)/2 if label=='original' else int(stem.split('_')[1])/1e6
            bytime[seconds]=im
        for left,right in [(247.,247.5),(413.5,414.)]:
            before=[left-1.5,left-1,left-.5,left]
            after=[right,right+.5,right+1,right+1.5]
            for direction,refs,queries in [('forward',before,after),('reverse',after,before)]:
                excluded={bytime[t].image_id for t in queries}
                for qi,t in enumerate(queries):
                    for subset,reference_times,seed in [
                        ('all',refs,0),('all',refs,1),('first_two',refs[:2],0),('last_two',refs[2:],0)]:
                        xy,xyz=candidates(r,bytime,inputs[label]['pairs'],t,reference_times,excluded)
                        result=estimate(r,bytime[t],xy,xyz,seed)
                        result.update(model=label,cut=[left,right],direction=direction,
                                      query_seconds=t,query_name=bytime[t].name,
                                      role='reserved_validation' if qi==3 else 'diagnostic',
                                      references=reference_times,reference_subset=subset)
                        output['tests'].append(result)
                        print(json.dumps(result),flush=True)
        del r,bytime
    output['finished_at']=time.time()
    target=ROOT/'results.json'
    with target.open('x') as stream:
        json.dump(output,stream,indent=2)
    print('REPORT='+str(target),flush=True)


if __name__=='__main__':
    main()
