"""Native-resolution OpenMVS in bounded, co-visible camera batches.

The global SfM is immutable. Batch clouds share its coordinates and are
concatenated, not claimed to be a globally deduplicated/fused surface.
"""
from collections import Counter,defaultdict
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

from campaign_post import scalar_ply,save,sha


def images(path):
    result={}
    with path.open('rb') as f:
        count=struct.unpack('<Q',f.read(8))[0]
        for _ in range(count):
            raw=f.read(64);row=struct.unpack('<i7di',raw);name=bytearray()
            while True:
                b=f.read(1)
                if b==b'\0':break
                if not b or len(name)>65536:raise RuntimeError('Invalid image record')
                name.extend(b)
            n=struct.unpack('<Q',f.read(8))[0];f.seek(24*n,1)
            result[row[0]]={'name':name.decode(),'pose':row[1:8],'camera_id':row[8]}
        if f.tell()!=path.stat().st_size:raise RuntimeError('Image payload mismatch')
    return result


def points(path,with_tracks=False):
    result={}
    with path.open('rb') as f:
        count=struct.unpack('<Q',f.read(8))[0]
        for _ in range(count):
            row=struct.unpack('<QdddBBBdQ',f.read(51));raw=f.read(8*row[-1])
            if len(raw)!=8*row[-1]:raise RuntimeError('Truncated point tracks')
            if with_tracks:
                track=[v[0] for v in struct.iter_unpack('<II',raw)]
                result[row[0]]=(row[1:4],track)
            else:result[row[0]]=row[1:4]
    return result


def plan_batches(views,tracks,core_size=40,total_size=64):
    ordered=sorted(views,key=lambda i:views[i]['name']);neighbors=defaultdict(Counter);view_ids=set(views)
    for xyz,track in tracks.values():
        ids=sorted(set(track)&view_ids)
        # Bound planning cost for very long tracks while retaining spread.
        if len(ids)>24:ids=[ids[round(j*(len(ids)-1)/23)] for j in range(24)]
        for i in ids:
            for j in ids:
                if i!=j:neighbors[i][j]+=1
    position={i:n for n,i in enumerate(ordered)};result=[]
    for first in range(0,len(ordered),core_size):
        core=ordered[first:first+core_size];scores=Counter()
        for i in core:scores.update(neighbors[i])
        candidates=[i for i in ordered if i not in core]
        candidates.sort(key=lambda i:(-scores[i],min(abs(position[i]-position[j]) for j in core),i))
        halo=candidates[:max(0,total_size-len(core))]
        result.append({'core':core,'halo':halo,'selected':sorted(core+halo)})
    return result


def invoke(argv,cwd,log):
    print('BATCH COMMAND',' '.join(map(str,argv)),flush=True)
    with log.open('a') as f:
        p=subprocess.run(list(map(str,argv)),cwd=cwd,stdout=f,stderr=subprocess.STDOUT)
    if p.returncode:raise RuntimeError('Batch command failed '+str(p.returncode)+': '+str(log))


def assemble(inputs,destination):
    records=[];props=None;total=0
    for path,meta in inputs:
        # JSON cache receipts decode tuples as lists; compare the schema, not
        # that incidental Python representation after a partial-stage resume.
        schema=[tuple(p) for p in meta['properties']]
        if props is None:props=schema
        if schema!=props:raise RuntimeError('Batch cloud schema mismatch')
        with path.open('rb') as f:
            while True:
                line=f.readline()
                if not line:raise RuntimeError('Invalid cloud header')
                if line.strip()==b'end_header':break
            offset=f.tell()
        records.append((path,offset,meta['vertices']));total+=meta['vertices']
    temp=destination.with_suffix('.ply.part');ranges=[];at=0
    with temp.open('wb') as dst:
        dst.write(('ply\nformat binary_little_endian 1.0\nelement vertex '+str(total)+'\n'+''.join('property '+t+' '+n+'\n' for t,n in props)+'end_header\n').encode())
        for path,offset,count in records:
            with path.open('rb') as src:src.seek(offset);shutil.copyfileobj(src,dst,4*1024**2)
            ranges.append({'source':str(path),'first_vertex':at,'vertices':count});at+=count
    temp.replace(destination)
    return {'vertices':total,'ranges':ranges,'properties':props,
            'operation':'same-frame concatenation of overlapping batch fusions; redundant surfaces may remain'}


def run(root,experiment,core_size=40,max_images=64):
    if not 3<=core_size<=max_images<=64:raise RuntimeError('Invalid bounded batch policy')
    a=json.loads((root/'assignment.json').read_text());out=root/'outputs'/('cuadra-'+a['block_id'])/experiment
    cfg=json.loads((root/'config-full.json').read_text());source=out/'colmap/undistorted/sparse';workspace=out/'colmap/undistorted'
    views=images(source/'images.bin');track_points=points(source/'points3D.bin',True)
    source_hash={n:sha(source/n) for n in ['cameras.bin','images.bin','points3D.bin']}
    key=hashlib.sha256(json.dumps({'model':source_hash,'dense':cfg['openmvs']['densify'],'driver':sha(Path(__file__)),
        'core_images':core_size,'max_batch_images':max_images},sort_keys=True).encode()).hexdigest()
    mvs=out/'mvs';mvs.mkdir(exist_ok=True);complete=mvs/'dense-batches.json'
    if complete.exists():
        old=json.loads(complete.read_text())
        if old['identity']!=key:raise RuntimeError('Batch recipe changed; use a new experiment')
        if sha(mvs/'scene_dense.ply')!=old['cloud_sha256']:raise RuntimeError('Assembled cloud changed')
        print('Reusing verified bounded dense result',flush=True);return
    batches=plan_batches(views,track_points,core_size,max_images)
    save(mvs/'dense-batch-plan.json',{'identity':key,'images':len(views),'max_images_per_batch':max_images,'batches':batches})
    masks=out/'colmap/undistorted_masks'
    for view in views.values():
        if not (masks/(Path(view['name']).stem+'.mask.png')).is_file():raise RuntimeError('Missing rectified mask')
    if not (mvs/'images').exists():
        (mvs/'images').symlink_to(os.path.relpath(workspace/'images',mvs),target_is_directory=True)
    if not (mvs/'scene.mvs').exists():invoke(['InterfaceCOLMAP','-w',mvs,'-i',workspace,'-o','scene.mvs'],mvs,mvs/'global-interface.log')
    inputs=[];receipts=[]
    for index,batch in enumerate(batches):
        directory=mvs/'chunks'/f'{index:03d}';directory.mkdir(parents=True,exist_ok=True)
        receipt=directory/'batch-receipt.json';scalar=directory/'scene_dense_scalar.ply'
        if receipt.exists():
            done=json.loads(receipt.read_text())
            if done['identity']!=key or done['selected']!=batch['selected'] or sha(scalar)!=done['cloud']['sha256']:
                raise RuntimeError('Batch cache changed')
        else:
            local_workspace=directory/'colmap';local_workspace.mkdir(exist_ok=True)
            model=local_workspace/'sparse'
            if model.exists():
                # This is an unpublished derived candidate, not the global SfM.
                model.rename(local_workspace/('interrupted-sparse-'+str(time.time_ns())))
            model.mkdir()
            delete=directory/'delete-image-ids.txt';delete.write_text(''.join(str(i)+'\n' for i in views if i not in batch['selected']))
            invoke(['colmap','image_deleter','--input_path',source,'--output_path',model,'--image_ids_path',delete],directory,directory/'subset.log')
            subset=images(model/'images.bin')
            if set(subset)!=set(batch['selected']):raise RuntimeError('Batch image membership differs')
            for iid,im in subset.items():
                before=views[iid]
                if im['name']!=before['name'] or im['camera_id']!=before['camera_id'] or im['pose']!=before['pose']:
                    raise RuntimeError('Batch creation changed a camera pose')
            if (model/'cameras.bin').read_bytes()!=(source/'cameras.bin').read_bytes():raise RuntimeError('Batch intrinsics changed')
            subset_xyz=points(model/'points3D.bin')
            if any(xyz!=track_points[pid][0] for pid,xyz in subset_xyz.items()):raise RuntimeError('Batch creation changed XYZ')
            link=local_workspace/'images'
            if not link.exists():link.symlink_to(os.path.relpath(workspace/'images',local_workspace),target_is_directory=True)
            link=directory/'images'
            if not link.exists():link.symlink_to(os.path.relpath(workspace/'images',directory),target_is_directory=True)
            invoke(['InterfaceCOLMAP','-w',directory,'-i',local_workspace,'-o','scene.mvs'],directory,directory/'interface.log')
            args=['DensifyPointCloud','-w',directory,'scene.mvs','-o','scene_dense.mvs','--resolution-level','0',
                  '--number-views','4','--max-threads','6','--max-resolution','100000','--min-resolution','640',
                  '--mask-path',masks,'--ignore-mask-label','0','--crop-to-roi','0','--estimate-roi','0','--tower-mode','0']
            invoke(args,directory,directory/'dense.log')
            cloud=scalar_ply(directory/'scene_dense.ply',scalar)
            done={'identity':key,'selected':batch['selected'],'core':batch['core'],'halo':batch['halo'],
                  'camera_poses_intrinsics_xyz_unchanged':True,'cloud':cloud}
            save(receipt,done)
        inputs.append((scalar,done['cloud']));receipts.append(done)
        save(mvs/'dense-batches-progress.json',{'completed':index+1,'total':len(batches),'last_batch':index,'at':time.time()})
        print('DENSE BATCH',index+1,'/',len(batches),'vertices',done['cloud']['vertices'],flush=True)
    result=assemble(inputs,mvs/'scene_dense.ply')
    result.update(identity=key,batches=len(batches),images=len(views),max_images_per_batch=max_images,
                  coordinate_frame='unchanged global sparse/undistorted frame',
                  cloud_sha256=sha(mvs/'scene_dense.ply'),source_sparse_sha256=source_hash,
                  scene_note='Global scene.mvs is the original camera scene; actual densified scenes are under chunks. No fictitious globally fused .mvs is generated.')
    save(complete,result)


if __name__=='__main__':run(Path(sys.argv[1]),sys.argv[2],int(sys.argv[3]) if len(sys.argv)>3 else 40,int(sys.argv[4]) if len(sys.argv)>4 else 64)
