"""Same planar/QEM parameters as the approved 70% delivery, per native chunk."""
import gc
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0,'/home/exitoso/home/barranco-roi')
import simplify_meshes as sm
import numpy as np
from roi.core import sha_file

root=Path(sys.argv[1])
output=root/'simplified70';output.mkdir()
reports=[]

def save(path,xyz,faces,rgb):
    assert np.isfinite(xyz).all() and (faces>=0).all() and (faces<len(xyz)).all()
    header=('ply\nformat binary_little_endian 1.0\ncomment 026 native coordinates unchanged; no automatic world alignment\n'
        f'element vertex {len(xyz)}\nproperty float x\nproperty float y\nproperty float z\n'
        'property uchar red\nproperty uchar green\nproperty uchar blue\n'
        f'element face {len(faces)}\nproperty list uchar int vertex_indices\nend_header\n')
    with path.open('xb') as f:
        f.write(header.encode())
        for first in range(0,len(xyz),250000):
            last=min(first+250000,len(xyz));v=np.empty(last-first,sm.VERTEX)
            for i,n in enumerate(['x','y','z']):v[n]=xyz[first:last,i]
            for i,n in enumerate(['red','green','blue']):v[n]=rgb[first:last,i]
            f.write(v.tobytes())
        for first in range(0,len(faces),250000):
            rows=np.empty(min(250000,len(faces)-first),sm.FACE)
            rows['n']=3;rows['indices']=faces[first:first+len(rows)]
            f.write(rows.tobytes())

for source in sorted((root/'raw').glob('*/mesh.ply')):
    chunk=source.parent.name
    print('SIMPLIFY026',chunk,flush=True)
    ms=sm.pm.MeshSet();ms.load_new_mesh(str(source))
    mesh=ms.current_mesh()
    xyz=mesh.vertex_matrix().copy();faces=mesh.face_matrix().copy()
    rgb=np.clip(mesh.vertex_color_matrix()[:,:3]*255,0,255).astype('u1')
    original_faces=len(faces)
    del mesh,ms
    xyz,faces,rgb,cleanup=sm.clean_components(xyz,faces,rgb)
    normals,areas,left,right,protected=sm.topology(xyz,faces)
    planar,interior,planes=sm.regularize_planes(xyz,faces,normals,areas,left,right,protected,tolerance=.05)
    del normals,areas,left,right
    weights=np.ones(len(xyz));weights[protected]=1000.;weights[interior]=.25
    target=int(len(faces)*.30)
    ms=sm.pm.MeshSet()
    ms.add_mesh(sm.pm.Mesh(vertex_matrix=planar,face_matrix=faces,v_scalar_array=weights),'026 planar QEM')
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,qualitythr=.3,
        preserveboundary=True,boundaryweight=10.,preservenormal=True,preservetopology=True,
        optimalplacement=True,planarquadric=True,planarweight=.1,qualityweight=True,autoclean=True,selected=False)
    mesh=ms.current_mesh();vx=mesh.vertex_matrix().copy();fc=mesh.face_matrix().copy()
    _,indices=sm.cKDTree(xyz).query(vx,k=1,workers=4)
    colors=rgb[indices]
    vx,fc,colors=sm.compact(vx,fc,colors)
    destination=output/('026_chunk_'+chunk+'_70pct.ply')
    save(destination,vx,fc,colors)
    report=dict(chunk=chunk,path=str(destination),sha256=sha_file(destination),
        vertices=len(vx),faces=len(fc),original_faces=original_faces,
        target_removed_percent=70,actual_removed_percent=100*(1-len(fc)/original_faces),
        cleanup=cleanup,planes=planes,coordinate_frame='026 native unchanged',
        treatment_tolerance_native_units=.05,metric_scale_not_certified=True,
        close_holes=False,distance_gate_enabled=False,roi_clip=False)
    reports.append(report)
    (output/'progress.json').write_text(json.dumps(dict(completed=len(reports),total=40),indent=2))
    (output/('report_'+chunk+'.json')).write_text(json.dumps(report,indent=2))
    del xyz,faces,rgb,planar,weights,vx,fc,colors,indices,ms,mesh
    gc.collect()
project=ET.Element('MeshLabProject');group=ET.SubElement(project,'MeshGroup')
for report in reports:
    layer=ET.SubElement(group,'MLMesh',label='026 · '+report['chunk'],filename=Path(report['path']).name,visible='1')
    ET.SubElement(layer,'MLMatrix44').text='\n1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1\n'
ET.SubElement(project,'RasterGroup')
ET.ElementTree(project).write(output/'parque026_simplificado70.mlp',encoding='utf-8',xml_declaration=True)
(output/'delivery.json').write_text(json.dumps(dict(complete=len(reports)==40,chunks=reports,
    simplified_by='same planar/QEM parameters as approved 70% batch; no ROI supplied',
    coordinate_frame='026 native unchanged',globally_fused=False,
    source_preserved=True,depth_maps_preserved=True),indent=2))
print('READY_TO_VIEW',output/'parque026_simplificado70.mlp',flush=True)
