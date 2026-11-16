"""Metadata export and coordinate-preserving scalar PLY normalization."""
import bisect
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys


def save(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024**2),b''):h.update(chunk)
    return h.hexdigest()


def catalog(root,out):
    assignment=json.loads((root/'assignment.json').read_text())
    info=json.loads((out/'metrics/videos_info.json').read_text())
    result={};report={}
    for relative,entry in info.items():
        source,filename=relative.split('/',1)
        video=root/'datasets/raw'/('cuadra-'+assignment['block_id'])/source/filename
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_packets','-show_entries','packet=pts_time','-of','json',str(video)],text=True))
        times=sorted(float(p['pts_time']) for p in probe['packets'] if p.get('pts_time') is not None and float(p['pts_time'])>=0)
        settings=entry['settings'];fps=float(settings['fps']);start=settings.get('start') or 0
        if isinstance(start,str):start=sum(float(v)*60**i for i,v in enumerate(reversed(start.split(':'))))
        rounded=[math.floor((t-float(start))*fps+.5+1e-9) for t in times]
        frames=sorted((out/'frames'/source).glob(Path(filename).stem+'_*.jpg'))
        if len(frames)!=entry['frames_extracted'] or not times:raise RuntimeError('Frame/catalog input mismatch')
        for index,p in enumerate(frames):
            chosen=max(0,bisect.bisect_right(rounded,index)-1)
            result[str(p.relative_to(out/'frames'))]={'clip':Path(filename).stem,'index':index+1,
                'time_s':times[chosen],'output_time_s':float(start)+index/fps,
                'source_presentation_index':chosen,
                'timestamp_method':'MP4 packet PTS, presentation-order, FFmpeg fps near rounding'}
        # Independently decode a selected source presentation frame. This catches
        # a PTS-origin, rounding, ordering or indexing error before using GPS.
        from PIL import Image
        import numpy as np
        checks=[]
        for i in sorted({0,len(frames)//2}):
            row=result[str(frames[i].relative_to(out/'frames'))]
            ordinal=row['source_presentation_index']
            raw=subprocess.check_output(['ffmpeg','-v','error','-nostdin','-i',str(video),
                '-vf',f'select=eq(n\\,{ordinal})','-frames:v','1','-vsync','0','-q:v','2','-threads','8',
                '-f','image2pipe','-vcodec','mjpeg','pipe:1'])
            with Image.open(io.BytesIO(raw)) as expected,Image.open(frames[i]) as observed:
                x=np.asarray(expected.convert('RGB'));y=np.asarray(observed.convert('RGB'))
                if x.shape!=y.shape or not np.array_equal(x,y):
                    raise RuntimeError('PTS/frame pixel correspondence failed: '+str(frames[i]))
            checks.append({'image':frames[i].name,'source_presentation_index':ordinal,'pixels_identical':True})
        report[relative]={'frames':len(frames),'source_packet_count':len(times),'native_dimensions':[int(entry['probe']['width']),int(entry['probe']['height'])],
                          'timestamp_pixel_checks':checks}
    from PIL import Image
    for name in result:
        with Image.open(out/'frames'/name) as image:
            if image.size!=(3840,2160):raise RuntimeError('Original image resolution was not retained')
    save(out/'image_info.json',result);save(out/'input-coverage.json',report)


def scalar_ply(source,destination):
    # OpenMVS places all scalar properties before its variable-length view lists.
    sizes={'char':1,'uchar':1,'uint8':1,'int8':1,'short':2,'ushort':2,'uint16':2,'int16':2,
           'int':4,'uint':4,'float':4,'int32':4,'uint32':4,'float32':4,'double':8,'float64':8}
    count=None;props=[];lists=[];format_name=None;seen_list=False;current=None
    temporary=destination.with_suffix('.ply.part')
    with source.open('rb') as f:
        if f.readline().strip()!=b'ply':raise RuntimeError('Not PLY')
        for _ in range(10000):
            row=f.readline().decode('ascii').strip().split()
            if not row:continue
            if row[0]=='end_header':break
            if row[0]=='format':format_name=row[1]
            elif row[0]=='element':
                current=row[1]
                if current=='vertex':count=int(row[2])
                elif int(row[2]):raise RuntimeError('Unexpected non-vertex PLY elements')
            elif row[0]=='property' and current=='vertex':
                if row[1]=='list':
                    if row[2] not in ['uchar','uint8']:raise RuntimeError('Unsupported PLY list count')
                    lists.append(sizes[row[3]]);seen_list=True
                else:
                    if seen_list:raise RuntimeError('Scalar after list requires a different adapter')
                    props.append((row[1],row[2]))
        if format_name!='binary_little_endian' or not count:raise RuntimeError('Expected binary little-endian cloud')
        size=sum(sizes[t] for t,n in props)
        if not lists:
            if source.stat().st_size-f.tell()!=count*size:raise RuntimeError('Truncated scalar payload')
            if temporary.exists():temporary.unlink()
            os.link(source,temporary);temporary.replace(destination)
            return {'vertices':count,'properties':props,'source_sha256':sha(source),'sha256':sha(destination),
                    'operation':'already scalar; coordinate-preserving hardlink, no duplicate data blocks'}
        with temporary.open('wb') as dst:
            dst.write(('ply\nformat binary_little_endian 1.0\nelement vertex '+str(count)+'\n'+''.join('property '+t+' '+n+'\n' for t,n in props)+'end_header\n').encode())
            buffer=bytearray()
            for i in range(count):
                raw=f.read(size)
                if len(raw)!=size:raise RuntimeError('Truncated scalar payload')
                buffer.extend(raw)
                for unit in lists:
                    n=f.read(1)
                    if not n:raise RuntimeError('Truncated list count')
                    payload=f.read(n[0]*unit)
                    if len(payload)!=n[0]*unit:raise RuntimeError('Truncated list payload')
                if len(buffer)>=4*1024**2:dst.write(buffer);buffer.clear()
            if buffer:dst.write(buffer)
            if f.read(1):raise RuntimeError('Unexpected trailing PLY data')
    temporary.replace(destination)
    return {'vertices':count,'properties':props,'source_sha256':sha(source),'sha256':sha(destination),
            'operation':'scalar attributes copied byte-for-byte; list attributes retained in original PLY'}


def validate(root,out):
    import numpy as np
    info=json.loads((out/'image_info.json').read_text())
    selected=(out/'colmap/best_model.txt').read_text().strip()
    # The certified 3.11 Python bindings can abort on reconstruction object
    # lifetimes. Read the documented binary records without native bindings;
    # the independent 3.13 adapter performs full model/feature audits later.
    def points(path):
        result={}
        with path.open('rb') as f:
            count=struct.unpack('<Q',f.read(8))[0]
            for _ in range(count):
                row=struct.unpack('<QdddBBBdQ',f.read(51))
                result[row[0]]=row[1:4];f.seek(row[-1]*8,1)
            if f.tell()!=path.stat().st_size:raise RuntimeError('Malformed point tracks')
        return result
    def image_names(path):
        names=set()
        with path.open('rb') as f:
            count=struct.unpack('<Q',f.read(8))[0]
            for _ in range(count):
                if len(f.read(64))!=64:raise RuntimeError('Truncated image record')
                name=bytearray()
                while True:
                    byte=f.read(1)
                    if byte==b'\0':break
                    if not byte or len(name)>65536:raise RuntimeError('Invalid image name')
                    name.extend(byte)
                n=struct.unpack('<Q',f.read(8))[0];f.seek(24*n,1);names.add(name.decode())
            if f.tell()!=path.stat().st_size:raise RuntimeError('Malformed image observations')
        return names
    original_xyz=points(out/'colmap/sparse'/selected/'points3D.bin')
    rectified_xyz=points(out/'colmap/undistorted/sparse/points3D.bin')
    if set(original_xyz)!=set(rectified_xyz):raise RuntimeError('Undistort changed point identities')
    delta=max((math.dist(p,rectified_xyz[pid]) for pid,p in original_xyz.items()),default=0)
    if delta>1e-10:raise RuntimeError('Sparse and dense-generator coordinate frames differ')
    registered=image_names(out/'colmap/sparse'/selected/'images.bin')
    per_clip={}
    for name,item in info.items():
        c=per_clip.setdefault(item['clip'],{'extracted':0,'registered':0})
        c['extracted']+=1;c['registered']+=name in registered
    ratio=len(registered)/len(info)
    models=[p.name for p in (out/'colmap/sparse').iterdir() if (p/'images.bin').is_file()]
    additional_views={name:sorted(image_names(out/'colmap/sparse'/name/'images.bin')-registered) for name in models}
    destination=out/'mvs/scene_dense_scalar.ply'
    conversion=scalar_ply(out/'mvs/scene_dense.ply',destination)
    # Create an independent, consistent feature DB export. Never edit the live source.
    db=out/'colmap/database.db';snapshot=out/'colmap/database.snapshot.db'
    if not snapshot.exists():
        src=sqlite3.connect(db.as_uri()+'?mode=ro',uri=True);dst=sqlite3.connect(snapshot)
        src.backup(dst);dst.execute('PRAGMA journal_mode=DELETE');dst.close();src.close()
    lineage={'schema':1,'selected_sparse':selected,'sparse_files_sha256':{n:sha(out/'colmap/sparse'/selected/n) for n in ['cameras.bin','images.bin','points3D.bin']},
             'undistort_xyz_max_delta':delta,'sparse_from_dense':np.eye(4).tolist(),
             'dense_source':'InterfaceCOLMAP from this run undistorted sparse; no georef or scene transform',
             'dense_scalar':conversion}
    save(out/'dense-lineage.json',lineage)
    quality={'complete':ratio>=.95 and all(v['registered']/v['extracted']>=.8 for v in per_clip.values()) and not any(additional_views.values()),
             'registered':len(registered),'extracted':len(info),'registered_ratio':ratio,'per_clip':per_clip,
             'sparse_components':models,'selected_component':selected,'sparse_points':len(original_xyz),
             'dense_points':conversion['vertices'],'native_resolution':[3840,2160],
             'sparse_from_dense_verified':True}
    quality['component_views_outside_selected']=additional_views
    batches=out/'mvs/dense-batches.json'
    if batches.exists():
        b=json.loads(batches.read_text());quality.update(dense_batches=b['batches'],dense_assembly=b['operation'],
            overlap_note='Redundant points may remain between overlapping bounded batches; not a globally deduplicated surface')
    save(out/'campaign-quality.json',quality)
    print(json.dumps(quality),flush=True)


if __name__=='__main__':
    root=Path(sys.argv[1]);out=root/'outputs'/('cuadra-'+json.loads((root/'assignment.json').read_text())['block_id'])/sys.argv[2]
    if sys.argv[3]=='catalog':catalog(root,out)
    elif sys.argv[3]=='validate':validate(root,out)
    elif sys.argv[3]=='seed':
        seed=json.loads((root/'recovery.json').read_text())
        model=out/'colmap/sparse/0'
        if not seed['validation']['passed']:raise RuntimeError('Unvalidated recovery seed')
        for name,expected in seed['model_sha256'].items():
            if sha(model/name)!=expected:raise RuntimeError('Derived model fingerprint mismatch')
        with (model/'images.bin').open('rb') as f:count=struct.unpack('<Q',f.read(8))[0]
        if count!=seed['validation']['registered_union']:raise RuntimeError('Derived view union changed')
        subprocess.run(['colmap','model_analyzer','--path',str(model)],check=True)
        print('Validated derived seed',count,'registered images',flush=True)
    else:raise ValueError('Unknown postprocessing operation')
