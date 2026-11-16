"""Publish convenient links and a truthful final report from verified artifacts."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from labdeploy.store import atomic_json

central=Path('/data/barranco/campaigns/barranco-full-v1');workspace=Path('/data/barranco/alignment/barranco-full-v1')
destination=Path('/data/barranco/exports/barranco-full-v1');destination.mkdir(parents=True,exist_ok=True)
s=json.loads((central/'execution-status.json').read_text())
assert s['phase']=='finished' and len(s['imports'])==15
assert all(v['state']=='verified' for v in s['collections'].values())
alignment=s['alignment'];assert len(alignment['components'])==1 and alignment['components'][0]['blocks']==15
assert not alignment['technical_failures'] and not alignment['audit_rejections']
mapping=workspace/'maps'/alignment['largest_map']/'map.json';m=json.loads(mapping.read_text())
dense_id=json.loads((central/'dense-export.log').read_text())['result']['export_revision']
sparse_id=json.loads((central/'sparse-export.log').read_text())['result']['export_revision']
dense=workspace/'exports'/dense_id;sparse=workspace/'exports'/sparse_id
da=json.loads((dense/'atlas.json').read_text());sa=json.loads((sparse/'atlas.json').read_text())
points=sum(v['quality']['dense_points'] for v in s['nodes'].values());sparse_points=sum(v['quality']['sparse_points'] for v in s['nodes'].values())
assert da['combined']['vertices']==points and sa['combined']['vertices']==sparse_points
preview=json.loads((destination/'dense_preview_5M.json').read_text());assert preview['source_vertices']==points
assert preview['source_bytes']==(dense/'combined.ply').stat().st_size
links={'dense_global.ply':dense/'combined.ply','sparse_global_por_manzana.ply':sparse/'combined.ply',
       'transforms_atlas.json':dense/'atlas.json','map.json':mapping,'legend.png':sparse/'legend.png','palette.json':sparse/'palette.json',
       'campaign.json':workspace/alignment['artifact'],'overview_xy_original.png':sparse/'overview_xy.png'}
for name,target in links.items():
    link=destination/name
    if link.is_symlink():
        if link.resolve()!=target.resolve():raise RuntimeError('Existing link points elsewhere: '+str(link))
    elif link.exists():raise RuntimeError('Preserve existing file: '+str(link))
    else:link.symlink_to(os.path.relpath(target,destination))
rows=[]
for block,node in sorted(s['nodes'].items()):
    q=node['quality'];rows.append({'manzana':block,'maquina':node['node_tag'],'calidad':node['state'],
        'vistas_extraidas':q['extracted'],'vistas_registradas':q['registered'],'puntos_sparse':q['sparse_points'],
        'puntos_densos':q['dense_points'],'lotes_densos':q.get('dense_batches',1),'resultado':s['collections'][block]['destination'],
        'manifiesto_alineacion':s['imports'][block]})
with (destination/'resultados_por_manzana.csv').open('w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
report={'campaign_id':'barranco-full-v1','at':time.time(),'reconstructed_blocks':15,'collected_verified_blocks':15,
        'visually_connected_blocks':15,'used_edges':len(m['measurements']),'technical_alignment_failures':0,
        'sparse_vertices':sparse_points,'dense_vertices':points,'dense_bytes':preview['source_bytes'],
        'dense_sha256':preview['source_sha256'],'registered_views':sum(r['vistas_registradas'] for r in rows),
        'extracted_views':sum(r['vistas_extraidas'] for r in rows),'map_revision':m['id'],'world_origin':m['world_origin'],'crs':m['crs'],
        'preview_vertices':preview['preview_vertices'],'free_gib_after_outputs':shutil.disk_usage('/data').free/1024**3,
        'coverage_warning':{'block':'023','registered':468,'extracted':480,'registered_percent':97.5,'all_four_clips_contribute':True,
            'note':'Twelve tail frames have insufficient verified 2D-3D correspondences; no thresholds were relaxed'},
        'assembly_note':'Original-resolution point placement and concatenation; overlap redundancy is retained, not a deduplicated surface',
        'master_makefile_sha256':hashlib.sha256(Path('/home/exitoso/Makefile').read_bytes()).hexdigest(),
        'rows':rows,'outputs':{k:str(destination/k) for k in links}}
atomic_json(destination/'report.json',report)
summary=f'''# Barranco — resultados de la campaña 4K

15 manzanas reconstruidas, recopiladas con SHA256 verificado y conectadas en un
solo marco mediante {len(m['measurements'])} aristas visuales aceptadas. Sin fallos técnicos de alineación.

## Abrir primero

- `overview_xy_focus.png`: distribución de las 15 manzanas, vista sparse de revisión.
- `dense_preview_5M.ply`: {preview['preview_vertices']:,} puntos, muestreo para visualización.
- `sparse_global_por_manzana.ply`: {sparse_points:,} puntos con color por manzana.
- `legend.png` y `palette.json`: correspondencia de colores y etiquetas.

## Resolución completa

`dense_global.ply`: **{points:,} puntos**, {preview['source_bytes']/1024**3:.2f} GiB,
RGB fotográfico, normales y `block_id` uint16. Es una colocación/concatenación de
nubes y lotes con solape; conserva redundancia y no es una superficie deduplicada.
La malla no forma parte de esta ejecución. Para una estación de 64 GiB conviene
revisar primero las versiones ligeras; el archivo completo requiere streaming o teselas.

SHA256: `{preview['source_sha256']}`.

## Coordenadas y procedencia

Marco local métrico EPSG:32718. Para obtener coordenadas proyectadas se suma
`world_origin` de `map.json`. Las transformaciones de `transforms_atlas.json`
aplican a las nubes fuente; ya están aplicadas en los PLY globales.
El campo `block_id` identifica manzanas, no computadoras.

Los resultados por manzana están en `/data/barranco/results/barranco-full-v1/`;
`resultados_por_manzana.csv` enumera rutas, vistas y conteos. Los mapas de
profundidad y las nubes nativas de cada lote permanecen en las hijas.

## Cobertura

La 023 conserva aviso: **468/480 vistas registradas (97,5%)**, con los cuatro videos
representados. No se forzó el registro de las doce vistas sin evidencia suficiente.
El estado general del coordinador es `partial` por este criterio de cobertura;
la alineación sí conecta las 15 manzanas y las dos exportaciones están publicadas.

No hay material en las carpetas 006,010,011,014,015,016,019,020,021,022.
Los tres videos `TODO` siguen descargados y sin procesar en L507_019.
'''
(destination/'RESUMEN.md').write_text(summary)
print(json.dumps({k:v for k,v in report.items() if k!='rows'},indent=2))
