"""Same-camera RGB geometry comparison for the selected 025 polygon."""
import os
os.environ.update(OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2')
from pathlib import Path
import sys
import json
import time
import html
import numpy as np
import shapely
from PIL import Image, ImageDraw, ImageFont
from scipy.spatial import cKDTree
from pilot import ROOT,OUT,SOURCE,selection,guard
from roi.core import ply_header,world_xyz,atomic_json,polygon,inside
sys.path.insert(0,str(ROOT/'runtime/meshdeps'))
sys.path.insert(0,'/tmp/opencode/render-deps')
import pymeshlab as pm
import moderngl

W,H=1600,1000


def unit(v):return v/np.linalg.norm(v)


def camera_matrix(camera):
    eye=np.array(camera['eye']);target=np.array(camera['target']);up=np.array(camera.get('up',[0,0,1.]))
    f=unit(target-eye);right=unit(np.cross(f,up));up=np.cross(right,f)
    look=np.eye(4);look[:3,:3]=[right,up,-f];look[:3,3]=-look[:3,:3]@eye
    q=1/np.tan(np.deg2rad(55)/2);n,far=.15,1500.;p=np.zeros((4,4))
    p[0,0]=q/(W/H);p[1,1]=q;p[2,2]=(far+n)/(n-far);p[2,3]=2*far*n/(n-far);p[3,2]=-1
    return (p@look).astype('f4').T.tobytes()


def cameras(common):
    s=selection();v=np.array(s['vertices']);center=np.array([*v.mean(axis=0),float(np.median(common['xyz'][::20,2]))])
    span=float(max(np.ptp(v[:,0]),np.ptp(v[:,1])))
    views=[{'name':'cenital','label':'Cenital · polígono completo','eye':(center+[0,0,span*1.1]).tolist(),'target':center.tolist(),'up':[0,1,0]},
           {'name':'dron_sur','label':'Dron · desde el sur','eye':(center+[25,-span*.85,span*.65]).tolist(),'target':(center+[0,0,8]).tolist()},
           {'name':'dron_norte','label':'Dron · desde el norte','eye':(center+[-25,span*.85,span*.65]).tolist(),'target':(center+[0,0,8]).tolist()},
           {'name':'dron_oeste','label':'Dron · desde el oeste','eye':(center+[-span*.9,10,span*.5]).tolist(),'target':(center+[0,0,8]).tolist()}]
    # A lower oblique shot from an original observed flight XY, looking into the ROI.
    import pycolmap
    run=Path('/data/barranco/results/barranco-full-v1/025/barranco_4k_2fps_combined_v1')
    rec=pycolmap.Reconstruction(str(run/'colmap/undistorted/sparse'));T=np.array(s['source']['world_from_block'])
    positions=np.array([T[:3,:3]@im.projection_center()+T[:3,3] for im in rec.images.values()])
    index=np.argmin(np.linalg.norm(positions[:,:2]-center[:2],axis=1))
    eye=positions[index];target=center.copy();target[2]+=8
    if np.linalg.norm(eye-target)<15:eye=eye+np.array([45,-30,15])
    views.append({'name':'fachada','label':'Fachadas · perspectiva cercana','eye':eye.tolist(),'target':target.tolist()})
    return views


def render(only=None):
    required=['ball_pivoting.json','delaunay.json','ransac_planar.json']
    if not only and not all((OUT/p).is_file() for p in required):raise RuntimeError('Wait until all three pilot methods finish')
    common=np.load(OUT/'common.npz');views=cameras(common)
    ctx=moderngl.create_standalone_context(backend='egl')
    program=ctx.program(vertex_shader='''#version 330
    uniform mat4 mvp;uniform float point_size;in vec3 position;in vec3 rgb;out vec3 col;
    void main(){gl_Position=mvp*vec4(position,1);gl_PointSize=point_size;col=rgb;}''',
    fragment_shader='''#version 330
    uniform bool points;in vec3 col;out vec4 color;
    void main(){if(points && length(gl_PointCoord-vec2(.5))>.5)discard;color=vec4(col,1);}''')
    ctx.enable(moderngl.DEPTH_TEST|moderngl.PROGRAM_POINT_SIZE)
    methods=[('full_cloud','Densa recortada · 26,86 M puntos',None),
             ('common_cloud','Muestra común · 5,20 M puntos',None),
             ('delaunay','Delaunay + visibilidad','delaunay_world.ply'),
             ('ball_pivoting','Ball Pivoting · teselas 3D','ball_pivoting_world.ply'),
             ('ransac_planar','RANSAC · solo parches planos','ransac_planar_world.ply')]
    if only:methods=[m for m in methods if m[0]==only]
    rows=[]
    for method,label,path in methods:
        guard();buffers=[]
        for camera in views:
            color=ctx.texture((W,H),3);depth=ctx.depth_renderbuffer((W,H));fb=ctx.framebuffer([color],depth)
            fb.use();fb.clear(.055,.08,.115,1,depth=1)
            buffers.append((camera,fb,color,depth,camera_matrix(camera)))
        program['points'].value=path is None;program['point_size'].value=1.8
        def draw(xyz,rgb,faces=None):
            if faces is not None:
                pos=xyz[faces.ravel()];col=rgb[faces.ravel()]
            else:pos=xyz;col=rgb
            packed=np.empty(len(pos),dtype=[('position','<f4',(3,)),('rgb','u1',(3,))])
            packed['position']=pos;packed['rgb']=col
            gpu=ctx.buffer(packed.tobytes());vao=ctx.vertex_array(program,[(gpu,'3f 3f1','position','rgb')])
            for _,fb,_,_,matrix in buffers:
                fb.use();program['mvp'].write(matrix);vao.render(moderngl.TRIANGLES if faces is not None else moderngl.POINTS)
            ctx.finish();vao.release();gpu.release()
        if method=='full_cloud':
            meta=ply_header(SOURCE);T=np.array(selection()['source']['world_from_block'])
            with SOURCE.open('rb') as f:
                f.seek(meta['offset']);remaining=meta['count']
                while remaining:
                    n=min(500000,remaining);d=np.frombuffer(f.read(n*meta['dtype'].itemsize),dtype=meta['dtype'])
                    draw(world_xyz(d,T),np.column_stack([d[k] for k in ['red','green','blue']]))
                    remaining-=n
        elif method=='common_cloud':draw(common['xyz'],common['rgb'])
        else:
            ms=pm.MeshSet();ms.load_new_mesh(str(OUT/path));m=ms.current_mesh()
            xyz=m.vertex_matrix().astype('f4');rgb=np.clip(m.vertex_color_matrix()[:,:3]*255,0,255).astype('u1');faces=m.face_matrix()
            for start in range(0,len(faces),300000):draw(xyz,rgb,faces[start:start+300000])
            del ms,m,xyz,rgb,faces
        for camera,fb,color,depth,_ in buffers:
            img=Image.frombytes('RGB',(W,H),fb.read(components=3)).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            filename=f'{method}_{camera["name"]}.jpg';img.save(OUT/filename,quality=95,subsampling=0)
            rows.append({'method':method,'label':label,'view':camera['name'],'view_label':camera['label'],'file':filename})
            fb.release();color.release();depth.release()
        print('Rendered',method,flush=True)
    atomic_json(OUT/'render-cameras.json',{'resolution':[W,H],'vertical_fov_degrees':55,'views':views,'images':rows,'appearance':'original RGB per point, interpolated vertex colors for meshes; no UV photographic atlases yet'})
    font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',17)
    sheet=Image.new('RGB',(2000,len(views)*285),'#111c28')
    for i,view in enumerate(views):
        for j,(method,label,_) in enumerate(methods):
            with Image.open(OUT/f'{method}_{view["name"]}.jpg') as im:sheet.paste(im.resize((400,250)),(j*400,i*285))
            ImageDraw.Draw(sheet).text((j*400+8,i*285+257),label.split(' · ')[0],font=font,fill='white')
    sheet.save(OUT/'RESUMEN.jpg',quality=92)


def metrics(only=None):
    common=np.load(OUT/'common.npz');rng=np.random.default_rng(25)
    meta=ply_header(SOURCE);stride=max(1,meta['count']//100000)
    raw=np.memmap(SOURCE,dtype=meta['dtype'],mode='r',offset=meta['offset'],shape=(meta['count'],))
    reference=world_xyz(raw[::stride],np.array(selection()['source']['world_from_block']))
    tree=cKDTree(common['xyz']);results=[];p=polygon(selection()['vertices'])
    for name in ['delaunay','ball_pivoting','ransac_planar']:
        if only and name!=only:continue
        guard();stats=json.loads((OUT/(name+'.json')).read_text());path=OUT/(name+'_world.ply')
        ms=pm.MeshSet();ms.load_new_mesh(str(path));mesh=ms.current_mesh();xyz=mesh.vertex_matrix();faces=mesh.face_matrix()
        # Independent serialized-vertex check: tolerate only float32 roundoff for reporting.
        outside=~inside(p,xyz)
        outside_dist=float(np.max(shapely.distance(shapely.points(xyz[outside,:2]),p))) if outside.any() else 0.
        if outside_dist>5e-5:raise RuntimeError('Published mesh exceeds user polygon')
        ms.add_mesh(pm.Mesh(vertex_matrix=reference), 'fixed dense evaluation sample')
        ms.compute_scalar_by_distance_from_another_mesh_per_vertex(measuremesh=1,refmesh=0,signeddist=False,maxdist=pm.PureValue(2.0))
        distances=np.abs(ms.mesh(1).vertex_scalar_array())
        outside_search=int((distances>2).sum())
        distances=np.minimum(distances,2.)
        faceids=rng.choice(len(faces),min(100000,len(faces)),replace=False)
        centroids=xyz[faces[faceids]].mean(axis=1)
        support,_=tree.query(centroids,k=1,workers=2)
        row={'method':name,'vertices':stats['vertices'],'faces':stats['faces'],'bytes':path.stat().st_size,
            'duration_s':stats['duration_s'],'dense_evaluation_points':len(reference),
            'dense_to_mesh_distance_m_quantiles':np.quantile(distances,[.5,.9,.95,.99]).tolist(),
            'dense_to_mesh_coverage_10cm_percent':float(100*(distances<=.1).mean()),
            'dense_to_mesh_coverage_20cm_percent':float(100*(distances<=.2).mean()),
            'outside_2m_search_radius_points':outside_search,
            'mesh_face_centroid_to_common_distance_m_quantiles':np.quantile(support,[.5,.9,.95,.99]).tolist(),
            'max_serialized_vertex_distance_outside_polygon_m':outside_dist,
            'evaluation_note':'Concordance to existing dense reconstruction, not independent ground truth. Distance search capped at 2 m.'}
        results.append(row);atomic_json(OUT/(name+'-metrics.json'),row);print('Metrics',row,flush=True)
        del ms,mesh,xyz,faces
    if not only:
        atomic_json(OUT/'comparison.json',{'selection_id':selection()['id'],'methods':results,'reference':'fixed uniform ~100k sample of full 26.86M ROI; same for all methods','ransac_scope':'only planar support, not complete reconstruction'})


def page():
    results=json.loads((OUT/'comparison.json').read_text());renderdata=json.loads((OUT/'render-cameras.json').read_text())
    methods=[('full_cloud','Densa completa'),('common_cloud','Muestra 10 cm'),('delaunay','Delaunay'),('ball_pivoting','BPA · teselas 3D'),('ransac_planar','RANSAC planar')]
    sections=[]
    for view in renderdata['views']:
        cards=[]
        for method,label in methods:
            filename=f'{method}_{view["name"]}.jpg'
            cards.append(f'<figure><a href="{filename}"><img loading="lazy" src="{filename}" alt="{html.escape(label)}"></a><figcaption>{html.escape(label)}</figcaption></figure>')
        sections.append(f'<section><h2>{html.escape(view["label"])}</h2><div class="comparison">'+''.join(cards)+'</div></section>')
    table=[]
    for row in results['methods']:
        table.append(f'<tr><td>{row["method"]}</td><td>{row["faces"]:,}</td><td>{row["dense_to_mesh_coverage_10cm_percent"]:.1f}%</td><td>{row["dense_to_mesh_coverage_20cm_percent"]:.1f}%</td><td>{row["duration_s"]:.1f} s</td></tr>')
    css='''body{background:#0b131e;color:#e4edf8;font:15px/1.6 system-ui;margin:28px auto;padding:0 24px;max-width:1900px}h1{font-size:32px;margin:8px 0}h2{font-size:19px;margin-top:34px}p{color:#a8bcd1;max-width:1100px}a{color:#75e4b4}.comparison{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}figure{margin:0;background:#162434;border-radius:7px;overflow:hidden}img{display:block;width:100%}figcaption{padding:9px;font-size:12px}table{border-collapse:collapse;width:100%;max-width:1000px}td,th{padding:10px;border-bottom:1px solid #304359;text-align:left}.tag{display:inline-block;border:1px solid #3d6556;border-radius:20px;padding:4px 12px;color:#75e4b4;font-size:11px}code{font-size:11px;overflow-wrap:anywhere}@media(max-width:1100px){.comparison{grid-template-columns:repeat(2,minmax(0,1fr))}}'''
    (OUT/'gallery.css').write_text(css)
    content='''<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>025 · piloto de superficies</title><link rel="stylesheet" href="gallery.css"><span class="tag">MANZANA 025 · POLÍGONO DEL USUARIO</span><h1>Un recorte, tres métodos de superficie.</h1><p><a href="/">Volver al selector</a> · <a href="RESUMEN.jpg">Ver resumen</a> · <a href="comparison.json">Métricas</a></p>
    <p>Se conservaron 26.860.347 puntos de tu polígono de 11.054 m². Los tres métodos recibieron las mismas posiciones de una muestra común de 5.204.407 puntos, un representante original por vóxel de 10 cm. Delaunay conserva además la visibilidad nativa. No se ejecutó cierre de huecos ni suavizado. Se rechazaron caras fuera del contorno y aristas excesivas.</p>
    <p>Las imágenes usan RGB original por punto o interpolación de color por vértice sobre la malla; aún no son atlas de textura fotográfica. Ball Pivoting se ejecutó por teselas 3D con halos internos y vértices originales compartidos, tras detener intentos globales de coste elevado; no se presenta como una ejecución global idéntica. RANSAC muestra solo las regiones que pudo explicar como planos: no representa toda la geometría ni la vegetación. Las zonas oscuras indican falta de geometría.</p>
    <h2>Concordancia geométrica con la nube densa</h2><table><tr><th>Método</th><th>Caras</th><th>A ≤10 cm</th><th>A ≤20 cm</th><th>Tiempo de etapa</th></tr>'''+''.join(table)+'''</table><p>Evaluación sobre la misma muestra fija de la densa completa. No es exactitud contra terreno ni tiempo total de preparación. Las geometrías planares pueden omitir detalle aunque encajen bien localmente.</p>'''+''.join(sections)+f'<h2>Archivos</h2><p><code>{OUT}</code></p></html>'
    (OUT/'gallery.html').write_text(content)
    atomic_json(OUT/'pilot-report.json',{'selection_id':selection()['id'],'status':'completed','gallery':'gallery.html','comparison':'comparison.json','methods':[r['method'] for r in results['methods']],'roi_source_points':26860347,'common_points':5204407,'voxel_m':.1})


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['render','metrics','page','all']);p.add_argument('--only');a=p.parse_args()
    if a.stage in ['render','all']:render(a.only)
    if a.stage in ['metrics','all']:metrics(a.only)
    if a.stage in ['page','all']:page()
