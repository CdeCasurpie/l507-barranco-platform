"""Immutable COLMAP 3.11 -> 3.13 snapshot; no SfM or geometry optimization."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys

import numpy as np
import pycolmap as pc

sys.path.insert(0,str(Path(__file__).resolve().parent))
from campaign_post import scalar_ply,save,sha


def convert(run,destination,block,sparse_only=False):
    if pc.__version__!='3.13.0':raise RuntimeError('Importer requires PyCOLMAP 3.13.0')
    adapter_sha=sha(Path(__file__))
    if destination.exists():raise RuntimeError('Choose a fresh immutable snapshot destination')
    destination.mkdir(parents=True)
    selected=(run/'colmap/best_model.txt').read_text().strip()
    original=run/'colmap/sparse'/selected
    rec=pc.Reconstruction(str(original))
    model=destination/'model';model.mkdir();rec.write(str(model))
    check=pc.Reconstruction(str(model))
    if set(rec.points3D)!=set(check.points3D) or set(rec.images)!=set(check.images):raise RuntimeError('Model IDs changed')
    delta=max((float(np.linalg.norm(p.xyz-check.points3D[pid].xyz)) for pid,p in rec.points3D.items()),default=0)
    if delta!=0:raise RuntimeError('Import changed XYZ')
    for cid,camera in rec.cameras.items():
        np.testing.assert_array_equal(camera.params,check.cameras[cid].params)
    for iid,im in rec.images.items():
        other=check.images[iid]
        if im.name!=other.name or im.camera_id!=other.camera_id:raise RuntimeError('Image identity changed')
        np.testing.assert_allclose(im.cam_from_world().matrix(),other.cam_from_world().matrix(),rtol=0,atol=1e-12)
        if len(im.points2D)!=len(other.points2D):raise RuntimeError('Observation count changed')
        for a,b in zip(im.points2D,other.points2D):
            if a.point3D_id!=b.point3D_id or not np.array_equal(a.xy,b.xy):raise RuntimeError('Observation indexing changed')
    source_db=run/'colmap/database.snapshot.db'
    if not source_db.exists():source_db=run/'colmap/database.db'
    if Path(str(source_db)+'-wal').exists() and Path(str(source_db)+'-wal').stat().st_size:
        raise RuntimeError('Source has a nonempty WAL; export a consistent DB first')
    target_db=destination/'features.db'
    handle=pc.Database.open(str(target_db));handle.close()
    src=sqlite3.connect(source_db.as_uri()+'?mode=ro&immutable=1',uri=True)
    dst=sqlite3.connect(target_db)
    tables=['cameras','images','keypoints','descriptors','matches','two_view_geometries']
    copied={}
    for table in tables:
        source_cols=[r[1] for r in src.execute('PRAGMA table_info('+table+')')]
        target_cols=[r[1] for r in dst.execute('PRAGMA table_info('+table+')')]
        cols=[c for c in source_cols if c in target_cols]
        if not cols:raise RuntimeError('Incompatible feature schema: '+table)
        names=','.join(cols);placeholders=','.join('?' for _ in cols)
        count=0
        for row in src.execute('SELECT '+names+' FROM '+table):
            dst.execute('INSERT INTO '+table+' ('+names+') VALUES ('+placeholders+')',row);count+=1
        copied[table]=count
    for cid, in dst.execute('SELECT camera_id FROM cameras').fetchall():
        dst.execute('INSERT INTO rigs(rig_id,ref_sensor_id,ref_sensor_type) VALUES(?,?,0)',(cid,cid))
    for iid,cid in dst.execute('SELECT image_id,camera_id FROM images').fetchall():
        dst.execute('INSERT INTO frames(frame_id,rig_id) VALUES(?,?)',(iid,cid))
        dst.execute('INSERT INTO frame_data(frame_id,data_id,sensor_id,sensor_type) VALUES(?,?,?,0)',(iid,iid,cid))
    dst.commit()
    if dst.execute('PRAGMA foreign_key_check').fetchone():raise RuntimeError('Database foreign-key mismatch')
    for table in ['keypoints','descriptors']:
        a=hashlib.sha256();b=hashlib.sha256()
        for row in src.execute('SELECT image_id,rows,cols,data FROM '+table+' ORDER BY image_id'):
            a.update(str(row[:3]).encode());a.update(row[3])
        for row in dst.execute('SELECT image_id,rows,cols,data FROM '+table+' ORDER BY image_id'):
            b.update(str(row[:3]).encode());b.update(row[3])
        if a.digest()!=b.digest():raise RuntimeError('Feature bytes or indices changed')
    dst.execute('PRAGMA journal_mode=DELETE');dst.close();src.close()
    info_path=run/'image_info.json'
    if info_path.exists():
        catalog=json.loads(info_path.read_text())
    else:
        # The historical demo did not record per-frame PTS. Its metadata declares
        # fixed-rate source video and FFmpeg fps near rounding. Not used for VFR.
        from fractions import Fraction
        videos=json.loads((run/'metrics/videos_info.json').read_text());catalog={}
        for name,item in videos.items():
            source,filename=name.split('/',1);fps=float(item['settings']['fps'])
            native=float(Fraction(item['probe']['r_frame_rate']))
            frames=sorted((run/'frames'/source).glob(Path(filename).stem+'_*.jpg'))
            for i,p in enumerate(frames):
                index=math.ceil((i+.5)*native/fps)-1
                catalog[str(p.relative_to(run/'frames'))]={'clip':Path(filename).stem,'index':i+1,'time_s':index/native,
                    'timestamp_method':'historical CFR demo metadata + FFmpeg fps near rounding'}
    save(destination/'image_info.json',catalog)
    model_names={im.name for im in check.images.values()}
    if not model_names<=set(catalog):raise RuntimeError('Model names missing from catalog')
    # Stable paths, no duplicated image or telemetry payload inside the adapter.
    (destination/'frames').symlink_to(run/'frames',target_is_directory=True)
    (destination/'telemetry').symlink_to(run/'telemetry',target_is_directory=True)
    lineage=run/'dense-lineage.json'
    if lineage.exists():
        source_lineage=json.loads(lineage.read_text())
        if source_lineage['undistort_xyz_max_delta']>1e-10:raise RuntimeError('Unverified dense coordinate frame')
    else:
        undistorted=pc.Reconstruction(str(run/'colmap/undistorted/sparse'))
        if set(rec.points3D)!=set(undistorted.points3D):raise RuntimeError('Dense generator point IDs differ')
        if any(not np.array_equal(p.xyz,undistorted.points3D[pid].xyz) for pid,p in rec.points3D.items()):
            raise RuntimeError('Dense generator frame differs')
    sys.path.insert(0,'/data/repos/Alineacion-point-cloud/src')
    from blockalign.contracts import digest,BlockManifest
    from blockalign.plyio import header,chunks
    cloud=None;minimum=np.full(3,np.inf);maximum=np.full(3,-np.inf);finite_vertices=0
    if not sparse_only:
        scalar=run/'mvs/scene_dense_scalar.ply'
        if scalar.exists():
            cloud=scalar
        else:
            cloud=destination/'dense_scalar.ply';scalar_ply(run/'mvs/scene_dense.ply',cloud)
        cloud_meta=header(cloud)
        for data in chunks(cloud,cloud_meta):
            xyz=np.column_stack([data[n] for n in ['x','y','z']])
            if not np.isfinite(xyz).all():raise RuntimeError('Nonfinite dense coordinates')
            if {'nx','ny','nz'}<=set(data.dtype.names):
                if not all(np.isfinite(data[n]).all() for n in ['nx','ny','nz']):raise RuntimeError('Nonfinite dense normals')
            minimum=np.minimum(minimum,xyz.min(axis=0));maximum=np.maximum(maximum,xyz.max(axis=0));finite_vertices+=len(data)
    sparse_hash=digest({n:sha(model/n) for n in ['cameras.bin','images.bin','points3D.bin','rigs.bin','frames.bin']})
    manifest={'schema_version':'1.0','block_id':block,
              'sparse':{'model_uri':str(model),'format':'colmap','version':'3.13.0','frame_id':block+'-local'},
              'features':{'database_uri':str(target_db),'family':'sift'},
              'images':{'root_uri':str(destination/'frames'),'catalog_uri':str(destination/'image_info.json'),'catalog_format':'image_info_v1'},
              'geography':{'crs':'EPSG:32718','telemetry_uri':str(destination/'telemetry')},
               'assets':([{'asset_id':'dense','kind':'point_cloud_ply','uri':str(cloud),'frame_id':block+'-dense',
                          'generated_from_sparse':sparse_hash,'sparse_from_asset':np.eye(4).tolist()}] if cloud is not None else []),
              'provenance':{'source_run':str(run),'adapter':'legacy311_to313_preserve_geometry_v1',
                            'adapter_sha256':adapter_sha,
                            'campaign_quality':json.loads((run/'campaign-quality.json').read_text()) if (run/'campaign-quality.json').exists() else {'historical_demo':True}}}
    BlockManifest.parse(manifest)
    save(destination/'block.json',manifest)
    receipt={'source_run':str(run),'source_sparse_sha256':{n:sha(original/n) for n in ['cameras.bin','images.bin','points3D.bin']},
             'adapter_sha256':adapter_sha,
             'canonical_sparse_fingerprint':sparse_hash,'images':check.num_reg_images(),'points':check.num_points3D(),
             'xyz_max_delta':delta,'features_byte_identity_verified':True,'tables_copied':copied,
              'dense_finite_vertices':finite_vertices,'dense_bounds_local':([minimum.tolist(),maximum.tolist()] if cloud is not None else None),
              'sparse_only':sparse_only,
             'operation':'COLMAP 3.13 legacy import + schema adaptation; no optimization or coordinate transform'}
    save(destination/'adaptation.json',receipt)
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--block',required=True)
    p.add_argument('--sparse-only',action='store_true',help='Import sparse/features without reading or collecting the dense cloud')
    a=p.parse_args();convert(a.run.resolve(),a.output.resolve(),a.block,a.sparse_only)
