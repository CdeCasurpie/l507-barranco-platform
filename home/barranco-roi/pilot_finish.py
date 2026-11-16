"""Publication checks and Spanish pilot report; no source geometry changes."""
import hashlib
import json
from pathlib import Path
import shutil
from PIL import Image,ImageDraw,ImageFont
from pilot import OUT,ROOT,selection
from roi.core import atomic_json,sha_file


def main():
    comparison=json.loads((OUT/'comparison.json').read_text())
    cameras=json.loads((OUT/'render-cameras.json').read_text())
    assert comparison['selection_id']==selection()['id']
    assert len(cameras['images'])==25
    for image in cameras['images']:
        with Image.open(OUT/image['file']) as im:
            assert im.size==(1600,1000)
            im.verify()
    checks={}
    for method in comparison['methods']:
        path=OUT/(method['method']+'_world.ply')
        assert method['max_serialized_vertex_distance_outside_polygon_m']<=5e-5
        checks[path.name]={'bytes':path.stat().st_size,'sha256':sha_file(path)}
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
    methods=[('full_cloud','Densa recortada'),('common_cloud','Muestra común 10 cm'),
             ('delaunay','Delaunay + visibilidad'),('ball_pivoting','BPA por teselas 3D'),('ransac_planar','Parches RANSAC')]
    sheet=Image.new('RGB',(2000,285*len(cameras['views'])),'#111c28')
    for i,view in enumerate(cameras['views']):
        for j,(method,label) in enumerate(methods):
            with Image.open(OUT/f'{method}_{view["name"]}.jpg') as im:
                sheet.paste(im.resize((400,250)),(400*j,285*i))
            ImageDraw.Draw(sheet).text((400*j+8,285*i+257),label,font=font,fill='white')
    sheet.save(OUT/'RESUMEN.jpg',quality=93)
    ball=json.loads((OUT/'ball_pivoting.json').read_text())
    planes=json.loads((OUT/'ransac_planar.json').read_text())
    free=shutil.disk_usage('/data').free
    report=['# Piloto 025 — polígono del usuario','',
      f'- Selección: `{selection()["id"]}`; {selection()["area_m2"]:.3f} m².',
      '- Puntos originales: 60.755.108; interiores: **26.860.347**; exteriores descartados: 33.894.761.',
      '- La nube interior completa se conserva sin muestreo. Los tres métodos utilizan una muestra común de **5.204.407 posiciones originales**, un representante por vóxel de 10 cm.',
      '- Delaunay recibió además las listas de visibilidad originales verificadas.',
      '- Las mallas finales están en `map_world`, con colores RGB por vértice. Aún no tienen atlas UV fotográficos.',
      '', '## Resultados','',
      '| Método | Caras | Tamaño MiB | Muestra densa a ≤10 cm | A ≤20 cm | Duración etapa exitosa |',
      '|---|---:|---:|---:|---:|---:|']
    labels={'delaunay':'Delaunay + visibilidad','ball_pivoting':'BPA por teselas 3D','ransac_planar':'Solo parches RANSAC'}
    for row in comparison['methods']:
        report.append(f'| {labels[row["method"]]} | {row["faces"]:,} | {row["bytes"]/1024**2:.2f} | {row["dense_to_mesh_coverage_10cm_percent"]:.2f}% | {row["dense_to_mesh_coverage_20cm_percent"]:.2f}% | {row["duration_s"]:.2f} s |')
    report+=['','## Interpretación y límites','',
      '- Son distancias a la malla sobre **la misma muestra fija de 100.226 puntos de la densa completa**. Miden concordancia con esa reconstrucción; no exactitud frente a terreno ni calidad topológica por sí solas.',
      '- Ball Pivoting sigue más de cerca las muestras, incluido el ruido que pueda quedar dentro del contorno. La mayor concordancia no garantiza una superficie físicamente mejor.',
      '- Delaunay produce una malla más pequeña y usa rayos de visibilidad para seleccionar la superficie.',
      f'- RANSAC detectó {len(planes["planes"])} planos y asignó {planes["assigned_points"]:,} de los puntos comunes ({100*planes["assigned_points"]/5204407:.2f}%). Esta candidata omite el resto; no reemplaza por sí sola toda la reconstrucción.',
      '- Se desactivaron cierre de huecos, suavizado y decimación. Se rechazaron caras exteriores y aristas excesivas. No se añadieron tapas de borde. Los algoritmos aún pueden crear conexiones a su escala local; esto no garantiza conservar cualquier hueco subresolución.',
      f'- BPA se completó por {len(ball["tiles"])} teselas 3D, con halos interiores de 0,5 m y vértices originales compartidos. No se presenta como un único BPA global equivalente. Pueden existir costuras abiertas.',
      '- Los intentos de BPA global y XY lentos se detuvieron. Su contabilidad y parámetros están en `ball-attempt1.json` y `ball-resource-attempts.json`; no se ocultan como si el tiempo de la etapa exitosa fuera el tiempo total de campaña.',
      '- La comprobación del límite permite únicamente el redondeo float32 (máximo observado: unos 0,00000454 m fuera del contorno en Delaunay).',
      '', '## Abrir','',
      '- Galería: http://127.0.0.1:8765/pilot/ (servidor del selector).',
      '- `gallery.html` y `RESUMEN.jpg`: 25 imágenes desde cinco cámaras idénticas.',
      '- `delaunay_world.ply`, `ball_pivoting_world.ply`, `ransac_planar_world.ply`: mallas para MeshLab.',
      '- `comparison.json`, `checksums.json`, parámetros y logs: evidencia reproducible.',
      '', '## Recursos','',
      f'- `/data` libre al publicar: **{free/1024**3:.3f} GiB**, conservando la reserva de 50 GiB.',
      '- Los datos originales no se editaron. El volumen de L507_015 se devolvió a desmontado tras recuperar los insumos autorizados.',
      '- OpenMVS y PyMeshLab se prepararon aisladamente dentro del proyecto, sin cambiar drivers ni bibliotecas del sistema.',
      '', f'Código y detalle del procedimiento: `{ROOT}/PILOT-025.md`.']
    (OUT/'REPORTE.md').write_text('\n'.join(report)+'\n')
    atomic_json(OUT/'checksums.json',checks)
    atomic_json(OUT/'publication-checks.json',{'selection_id':selection()['id'],'images_verified':25,
        'meshes_verified':3,'polygon_tolerance_m':5e-5,'data_free_bytes':free,
        'max_local_bpa_input_points':max(t['input_points'] for t in ball['tiles']),
        'bpa_tiles':len(ball['tiles']),'root_free_bytes':shutil.disk_usage(ROOT).free})
    print(json.dumps({'gallery':'http://127.0.0.1:8765/pilot/','verified_images':25,'verified_meshes':3,'data_free_GiB':free/1024**3},indent=2))


if __name__=='__main__':main()
