import json,sys,array
from pathlib import Path
import bpy
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1]);report=json.loads((root/'delivery.json').read_text())
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.ops.wm.ply_import(filepath=report['mesh'])
obj=bpy.context.object;obj.name='Manzana_'+report['block'];assert obj.data.color_attributes
raw=array.array('f',[0.])*(len(obj.data.vertices)*3);obj.data.vertices.foreach_get('co',raw)
step=max(1,len(obj.data.vertices)//80000)
points=[Vector(raw[i*3:i*3+3]) for i in range(0,len(obj.data.vertices),step)]
def limits(values):
    v=sorted(values);return v[round((len(v)-1)*.005)],v[round((len(v)-1)*.995)]
lo=Vector([limits([p[i] for p in points])[0] for i in range(3)])
hi=Vector([limits([p[i] for p in points])[1] for i in range(3)])
center=(lo+hi)*.5;radius=max((hi-lo).length*.5,.01)
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO';scene.display.shading.color_type='VERTEX'
scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
scene.display.shading.cavity_type='BOTH';scene.display.shading.background_type='WORLD'
scene.world.color=(.045,.05,.06)
scene.render.resolution_x=1600;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
camera_data=bpy.data.cameras.new('Camera');camera=bpy.data.objects.new('Camera',camera_data)
scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO'
camera_data.clip_start=max(radius*.00001,.00001);camera_data.clip_end=radius*100
aspect=scene.render.resolution_x/scene.render.resolution_y
for name,direction in [('oblicua',Vector((1,-1,.75))),('opuesta',Vector((-1,1,.75))),('superior',Vector((.001,-.001,1)))]:
    direction.normalize();camera.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()
    rotation=camera.rotation_euler.to_matrix();projected=[rotation.transposed()@(p-center) for p in points]
    x0,x1=limits([p.x for p in projected]);y0,y1=limits([p.y for p in projected])
    camera.location=center+rotation@Vector(((x0+x1)*.5,(y0+y1)*.5,0.))+direction*radius*8
    camera_data.ortho_scale=max(x1-x0,(y1-y0)*aspect)*1.15
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
# Save delivery with the single full lightweight mesh; no proxy or instancing.
bpy.data.objects.remove(camera,do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/('manzana_'+report['block']+'_editable.blend')))
# Publish only completed derivatives and actual renders to the existing local
# viewer; do not expose the rest of the filesystem or remote inputs.
import html
web=Path('/tmp/opencode/render019-web');gallery=web/'manzanas';gallery.mkdir(exist_ok=True)
block=report['block']
assert all(c.isdigit() or c=='-' for c in block)
target=gallery/block;target.mkdir(exist_ok=True)
for name,source in [
    ('oblicua.png',root/'oblicua.png'),('opuesta.png',root/'opuesta.png'),
    ('superior.png',root/'superior.png'),('malla_rgb.ply',Path(report['mesh'])),
    ('editable.blend',root/('manzana_'+block+'_editable.blend')),
]:
    link=target/name
    if link.is_symlink():link.unlink()
    elif link.exists():raise RuntimeError('Refusing to replace a non-link gallery file')
    link.symlink_to(source)
page=f"""<!doctype html><meta charset="utf-8"><title>Manzana {block}</title>
<style>body{{font:16px system-ui;background:#202428;color:#eee;margin:24px}}a{{color:#8bd5ff}}img{{width:100%}}</style>
<a href="../">Todas las mallas</a><h1>Manzana {block} · RGB · colocación manual</h1>
<p>{report['vertices']:,} vértices · {report['faces']:,} caras. Partes unidas, sin soldar ni fusionar superficies.</p>
<a href="malla_rgb.ply" download>Descargar PLY</a> · <a href="editable.blend" download>Blender editable</a>
<h2>Oblicua</h2><img src="oblicua.png"><h2>Lado opuesto</h2><img src="opuesta.png">
<h2>Superior</h2><img src="superior.png">"""
(target/'index.html').write_text(page)
entries=sorted(p.name for p in gallery.iterdir() if p.is_dir() and (p/'index.html').exists())
listing=''.join(f'<li><a href="{html.escape(n)}/">Manzana {html.escape(n)}</a></li>' for n in entries)
(gallery/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Mallas de Barranco</title>'
 '<style>body{font:18px system-ui;background:#202428;color:#eee;margin:30px}a{color:#8bd5ff}li{margin:12px}</style>'
 '<h1>Mallas listas · RGB y colocación manual</h1><p>Cada manzana es un objeto independiente. Sin soldadura entre partes.</p><ul>'+listing+'</ul>')
