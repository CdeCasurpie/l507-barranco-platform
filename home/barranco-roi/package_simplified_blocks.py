"""Portable MeshLab project and raw buffers for a 15-object Blender scene."""
import argparse
import csv
import json
from pathlib import Path
import os
import time
import xml.etree.ElementTree as ET

import numpy as np
from combine_meshes import header
from simplify_meshes import load_mesh
from roi.core import atomic_json, sha_file

ROOT=Path(__file__).resolve().parent
DEFAULT=ROOT/'exports/mesh-campaign-20261112/simplified_70pct_blocks'


def prepare(root):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['completed']==15 and len(manifest['blocks'])==15
    buffers=root/'blender-inputs'
    buffers.mkdir(exist_ok=True)
    project=ET.Element('MeshLabProject')
    group=ET.SubElement(project,'MeshGroup')
    inputs=[]
    for block,result in sorted(manifest['blocks'].items()):
        path=Path(result['mesh'])
        assert sha_file(path)==result['sha256']
        meta=header(path)
        assert meta['vertices']==result['vertices'] and meta['faces']==result['faces']
        xyz,faces,rgb=load_mesh(path)
        rgba=np.ones((len(xyz),4),dtype='<f4')
        rgba[:,:3]=rgb.astype('f4')/np.float32(255.)
        arrays={'positions':xyz.astype('<f4'),'indices':faces.astype('<u4'),'colors':rgba}
        item=dict(block=block,name='Manzana_'+block,vertices=len(xyz),faces=len(faces),
                  mesh=os.path.relpath(path,root),source_sha256=result['sha256'],buffers={})
        for name,array in arrays.items():
            destination=buffers/(block+'.'+name+'.bin')
            temporary=destination.with_suffix('.bin.new')
            with temporary.open('wb') as f:
                array.tofile(f)
                f.flush()
                os.fsync(f.fileno())
            temporary.replace(destination)
            item['buffers'][name]=dict(path=os.path.relpath(destination,root),sha256=sha_file(destination),bytes=destination.stat().st_size)
        inputs.append(item)
        layer=ET.SubElement(group,'MLMesh',label=item['name'],filename=item['mesh'],visible='1')
        ET.SubElement(layer,'MLMatrix44').text='\n1 0 0 0\n0 1 0 0\n0 0 1 0\n0 0 0 1\n'
        print('PREPARED BLENDER',block,'vertices',len(xyz),'faces',len(faces),flush=True)
        del xyz,faces,rgb,rgba,arrays
    ET.SubElement(project,'RasterGroup')
    project_path=root/'barranco_15_manzanas_70pct.mlp'
    ET.ElementTree(project).write(project_path,encoding='utf-8',xml_declaration=True)
    atomic_json(root/'blender-inputs.json',dict(blocks=inputs,coordinate_frame='map_world',
                world_origin=[279932.4471962734,8657453.760760272,116.53700000000002],
                crs='EPSG:32718',require_independent_objects=True))
    # Parse the project back and verify every layer references its own PLY.
    layers=ET.parse(project_path).findall('./MeshGroup/MLMesh')
    assert len(layers)==15 and len({l.attrib['filename'] for l in layers})==15
    assert all((root/l.attrib['filename']).is_file() for l in layers)
    print('MESHLAB PROJECT VERIFIED: 15 separate layers',flush=True)


def finalize(root):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text())
    audit=json.loads((root/'blender-audit.json').read_text())
    assert audit['objects']==15 and audit['unique_mesh_data']==15 and audit['geometry_hashes_verified']
    assert all(v['mesh_users']==1 and v['instance_type']=='NONE' for v in audit['blocks'])
    blend=root/'barranco_15_manzanas_70pct.blend'
    project=root/'barranco_15_manzanas_70pct.mlp'
    rows=[]
    for block,value in sorted(manifest['blocks'].items()):
        path=Path(value['mesh'])
        assert path.stat().st_size==value['bytes'] and sha_file(path)==value['sha256']
        rows.append(dict(block=block,mesh=str(path),vertices=value['vertices'],faces=value['faces'],
                         bytes=value['bytes'],MB=value['bytes']/1e6,MiB=value['bytes']/1024**2,
                         reduction_percent=value['face_reduction_percent'],sha256=value['sha256'],
                         seconds=value.get('execution_seconds',0)))
    summary=dict(completed=15,independent_objects=15,unique_mesh_data=15,instances=0,
                 blend=dict(path=str(blend),bytes=blend.stat().st_size,sha256=sha_file(blend)),
                 meshlab_project=dict(path=str(project),bytes=project.stat().st_size,embeds_geometry=False),
                 individual_geometry_bytes=sum(r['bytes'] for r in rows),
                 vertices=sum(r['vertices'] for r in rows),faces=sum(r['faces'] for r in rows),
                 blocks=rows,distance_gate_enabled=False,reduction_target_percent=70,
                 processing_elapsed_seconds=manifest['elapsed_seconds'],finished_at=time.time())
    atomic_json(root/'delivery.json',summary)
    with (root/'pesos_por_manzana.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines=['# Barranco — 15 manzanas simplificadas, objetos independientes','',
           '## Abrir el conjunto','',
           '- Blender: **barranco_15_manzanas_70pct.blend**. Archivo autocontenido con 15 objetos y 15 datablocks de malla distintos.',
           '- MeshLab: **barranco_15_manzanas_70pct.mlp**. Proyecto de 15 capas que referencia los PLY de `meshes/`; conservar esas rutas relativas.',
           '- Cada objeto se llama `Manzana_NNN`. No hay geometría compartida por instancias ni fusión de los bloques.',
           '- XYZ ya está alineado en `map_world`, en metros. Las transformaciones de los objetos son identidad; no aplicar otras matrices.',
           '- RGB por vértice preservado. En Blender, vista sólida configurada para color por vértice y material que utiliza el atributo Color.',
           '- El archivo se creó con Blender 5.0.1. Para otros flujos se incluyen los 15 PLY individuales.','',
           '## Tamaños','',
           f"- Archivo Blender: {blend.stat().st_size/1e6:.2f} MB ({blend.stat().st_size/1024**2:.2f} MiB).",
           f"- Suma de los PLY individuales: {summary['individual_geometry_bytes']/1e6:.2f} MB.",
           f"- Geometría total: {summary['vertices']:,} vértices, {summary['faces']:,} triángulos.",
           '- El MLP es pequeño porque enlaza los PLY, no porque comprima/contenga toda la geometría.','',
           '| Manzana | Vértices | Triángulos | MB | Reducción de caras |','|---|---:|---:|---:|---:|']
    lines += [f"| {r['block']} | {r['vertices']:,} | {r['faces']:,} | {r['MB']:.2f} | {r['reduction_percent']:.2f} % |" for r in rows]
    lines += ['','## Método y verificación','',
              'Se reutiliza exactamente la 025 aprobada. Las demás usan limpieza mínima de fragmentos, normales PCA, planos conectados y QEM con objetivo de eliminar el 70 % de las caras.',
              'No se aplica rechazo por distancia. Las mediciones geométricas se conservan en reports/. No se rellenan huecos ni se sueldan manzanas.',
              'Se reabrió el .blend en un proceso independiente y se verificaron 15 objetos, 15 mallas únicas, ausencia de instancias, conteos, coordenadas e índices completos mediante hashes, y colores.',
              f"Tiempo de simplificación del lote (dos procesos simultáneos): {manifest['elapsed_seconds']:.2f} s.",
              'Los buffers en blender-inputs/ y las referencias en work/ son auxiliares de construcción/verificación; los archivos de entrega son .blend, .mlp, meshes/, reports/ y los informes.']
    (root/'LEEME.md').write_text('\n'.join(lines)+'\n')
    print('DELIVERY VERIFIED',json.dumps({k:v for k,v in summary.items() if k!='blocks'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,default=DEFAULT)
    parser.add_argument('--finalize',action='store_true')
    args=parser.parse_args()
    (finalize if args.finalize else prepare)(args.root)
