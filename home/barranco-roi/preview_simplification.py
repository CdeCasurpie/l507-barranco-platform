"""Create distance-unrestricted planar/QEM visual previews by face reduction."""
import argparse
import gc
import json
import os
from pathlib import Path
import subprocess
import time
import xml.etree.ElementTree as ET

import numpy as np
from simplify_meshes import (BASE, load_mesh, surface_distances, topology, regularize_planes,
                             clip_roi, compact, save_mesh, cKDTree, pm)
from combine_meshes import header
from roi.core import atomic_json, sha_file


def open_preview(path, pid, reduction=50):
    proc=Path('/proc')/str(pid)
    if not proc.exists():
        print('VIEWER: desktop anchor process closed; preview is saved and ready to open',flush=True)
        return False
    if proc.stat().st_uid != os.getuid() or (proc/'comm').read_text().strip() not in ['meshlab','bash']:
        raise ValueError('Expected a viewer or terminal owned by this user')
    env={k:v for k,v in os.environ.items() if k in ['HOME','USER','LOGNAME','PATH','LANG','XDG_RUNTIME_DIR','DBUS_SESSION_BUS_ADDRESS']}
    keys={b'DISPLAY',b'XAUTHORITY',b'WAYLAND_DISPLAY',b'XDG_RUNTIME_DIR',b'DBUS_SESSION_BUS_ADDRESS',b'QT_QPA_PLATFORM'}
    for item in (proc/'environ').read_bytes().split(b'\0'):
        key,sep,value=item.partition(b'=')
        if sep and key in keys:
            env[key.decode()]=value.decode()
    if not (env.get('DISPLAY') or env.get('WAYLAND_DISPLAY')):
        print('VIEWER: no graphical display binding in this terminal',flush=True)
        return False
    cmd=['systemd-run','--user','--unit=barranco-preview-025-'+str(reduction)+'pct','-p','MemoryMax=24G','-p','MemorySwapMax=0','-p','Nice=10']
    for key in ['DISPLAY','XAUTHORITY','WAYLAND_DISPLAY','QT_QPA_PLATFORM']:
        if key in env:cmd+=['--setenv='+key+'='+env[key]]
    cmd+=['meshlab',str(path)]
    subprocess.run(cmd,env=env,check=True)
    return True


def generate_preview(pilot,output,mesh,reduction,block='025',progress=None):
    timings={}
    started=time.monotonic()
    xyz,faces,rgb=load_mesh(pilot/'reference_retained.ply')
    timings['load_seconds']=time.monotonic()-started
    if progress:progress('normals_and_planes')
    began=time.monotonic()
    normals,areas,left,right,protected=topology(xyz,faces)
    planar,interior,planes=regularize_planes(xyz,faces,normals,areas,left,right,protected,tolerance=.05)
    timings['normals_and_planes_seconds']=time.monotonic()-began
    atomic_json(output/'planes.json',planes)
    del normals,areas,left,right
    gc.collect()
    weights=np.ones(len(xyz))
    weights[protected]=1000.
    weights[interior]=.25
    target=int(len(faces)*(1-reduction/100))
    print('DECIMATING',len(faces),'faces ->',target,flush=True)
    if progress:progress('decimation')
    began=time.monotonic()
    ms=pm.MeshSet()
    ms.add_mesh(pm.Mesh(vertex_matrix=planar,face_matrix=faces,v_scalar_array=weights),'planar unrestricted preview')
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=target,qualitythr=.3,
        preserveboundary=True,boundaryweight=10.,preservenormal=True,preservetopology=True,
        optimalplacement=True,planarquadric=True,planarweight=.1,qualityweight=True,autoclean=True,selected=False)
    candidate=ms.current_mesh()
    vx,fc=candidate.vertex_matrix(),candidate.face_matrix()
    del candidate,ms,weights,planar
    gc.collect()
    timings['decimation_seconds']=time.monotonic()-began
    began=time.monotonic()
    if progress:progress('roi_color_save')
    roi=json.loads((BASE/block/('roi_'+block+'.json')).read_text())
    fc,rejected=clip_roi(vx,fc,roi['vertices'])
    _,indices=cKDTree(xyz).query(vx,k=1,workers=4)
    colors=rgb[indices]
    vx,fc,colors=compact(vx,fc,colors)
    stats=save_mesh(mesh,vx,fc,colors)
    timings['roi_color_save_seconds']=time.monotonic()-began
    timings['generation_seconds']=time.monotonic()-started
    report=dict(path=str(mesh),target_face_ratio=1-reduction/100,roi_rejected_faces=rejected,
                distance_gate_enabled=False,timings_s=timings,**stats)
    atomic_json(output/'generation.json',report)
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--desktop-pid',type=int)
    parser.add_argument('--reduction',type=int,default=50,choices=range(1,96))
    args=parser.parse_args()
    start=time.monotonic()
    pilot=BASE/'simplified/pilot_025_5cm_v2'
    reduction=args.reduction
    output=BASE/('simplified/previews/025_'+str(reduction)+'pct_no_distance_limit')
    output.mkdir(parents=True,exist_ok=True)
    mesh=output/('manzana_025_'+str(reduction)+'pct_preview.ply')
    if reduction==50:
        attempt=json.loads((pilot/'planar_qem_50.json').read_text())
        source=Path(attempt['path'])
        assert sha_file(source)==attempt['sha256']
        if not mesh.exists():os.link(source,mesh)
    elif mesh.exists():
        attempt=json.loads((output/'generation.json').read_text())
        source=Path(attempt['path'])
    else:
        attempt=generate_preview(pilot,output,mesh,reduction)
        source=mesh
    assert sha_file(mesh)==attempt['sha256']
    meta=header(mesh)
    assert meta['faces']==attempt['faces'] and meta['vertices']==attempt['vertices']
    report=dict(block='025',mesh=str(mesh),sha256=attempt['sha256'],vertices=meta['vertices'],faces=meta['faces'],
                bytes=mesh.stat().st_size,distance_gate_enabled=False,classification='visual_preview',
                method='PCA-normal planar regularization + QEM '+str(reduction)+'% face reduction; distance rejection disabled by user.',
                source_candidate=str(source),coordinate_frame='map_world',already_world_aligned=True)
    report['timings_s']=attempt.get('timings_s',{})
    atomic_json(output/'report.json',report)
    print('PUBLISHED PREVIEW',mesh,'faces',meta['faces'],'bytes',report['bytes'],flush=True)
    began=time.monotonic()
    xyz,faces,_=load_mesh(pilot/'reference_retained.ply')
    vx,fc,_=load_mesh(mesh)
    print('MEASURING: all vertices plus sampled surfaces; reporting only, no rejection threshold',flush=True)
    report['distances']=surface_distances(xyz,faces,vx,fc,all_vertices=True)
    report['measurement_seconds']=time.monotonic()-began
    original=json.loads((BASE/'manifest.json').read_text())['blocks']['025']
    report['original']=dict(vertices=original['vertices'],faces=original['faces'],bytes=original['bytes'])
    report['face_reduction_percent']=100*(1-meta['faces']/original['faces'])
    report['total_seconds']=time.monotonic()-start
    atomic_json(output/'report.json',report)
    project=ET.Element('MeshLabProject')
    group=ET.SubElement(project,'MeshGroup')
    layers=[('Original 025',BASE/'025/manzana_025_world.ply','0'),
            ('Conservadora 025',BASE/'simplified/025/manzana_025_simplified.ply','0')]
    if reduction!=50:
        previous=BASE/'simplified/previews/025_50pct_no_distance_limit/manzana_025_50pct_preview.ply'
        if previous.is_file():layers.append(('Prueba 50%',previous,'0'))
    layers.append(('Prueba '+str(reduction)+'% sin limite de distancia',mesh,'1'))
    for label,path,visible in layers:
        layer=ET.SubElement(group,'MLMesh',label=label,filename=os.path.relpath(path,output),visible=visible)
        ET.SubElement(layer,'MLMatrix44').text='\n1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1\n'
    ET.SubElement(project,'RasterGroup')
    project_path=output/('comparacion_025_'+str(reduction)+'pct.mlp')
    ET.ElementTree(project).write(project_path,encoding='utf-8',xml_declaration=True)
    ds=[report['distances'][d] for d in ['reference_to_candidate','candidate_to_reference']]
    text=['# Prueba visual 025 — reducción del '+str(reduction)+' %','',
          f"Caras: {meta['faces']:,}; vértices: {meta['vertices']:,}; tamaño: {report['bytes']/1e6:.2f} MB.",
          f"Reducción respecto al original: {report['face_reduction_percent']:.3f} %.",
          'Criterio de rechazo por distancia: DESACTIVADO por petición del usuario.',
          'SHA256 e índices verificados. Variante independiente sin rechazo por distancia.',
          f"P99 peor entre ambos sentidos: {max(d['p99_m'] for d in ds)*100:.3f} cm.",
          f"Máximo observado en todos los vértices y las muestras de superficies: {max(d['sampled_max_m'] for d in ds)*100:.3f} cm.",
          'Las distancias se informan, pero no impiden publicar esta prueba.',
          f"Tiempo de medición adicional: {report['measurement_seconds']:.2f} s.",
          f"Tiempo de generación: {report['timings_s'].get('generation_seconds',0):.2f} s (0 indica reutilización del piloto).",
          'La regularización planar mantiene su tolerancia de detección original de 5 cm; lo desactivado es el rechazo por error tras decimar.',
          'Proyecto MeshLab: `'+str(project_path)+'`.']
    (output/'REPORTE.md').write_text('\n'.join(text)+'\n')
    print('MEASURED P99 cm',max(d['p99_m'] for d in ds)*100,'max cm',max(d['sampled_max_m'] for d in ds)*100,
          'seconds',report['measurement_seconds'],flush=True)
    if args.desktop_pid:
        report['viewer_requested']=open_preview(mesh,args.desktop_pid,reduction)
        atomic_json(output/'report.json',report)


if __name__=='__main__':
    main()
