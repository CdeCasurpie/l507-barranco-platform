import array
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector,Matrix
root=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
objects=[]
for path in sorted((root/'simplified70_rgb/render_parts').glob('*.ply')):
    bpy.ops.wm.ply_import(filepath=str(path));objects.append(bpy.context.object)
assert len(objects)==26
for obj in objects:obj.select_set(True)
bpy.context.view_layer.objects.active=objects[0];bpy.ops.object.join()
obj=bpy.context.object;obj.name='019_simplificada70_RGB_render_proxy'
assert obj.data.color_attributes
raw=array.array('f',[0.])*(len(obj.data.vertices)*3);obj.data.vertices.foreach_get('co',raw)
step=max(1,len(obj.data.vertices)//100000)
points=[Vector(raw[i*3:i*3+3]) for i in range(0,len(obj.data.vertices),step)]
def limits(values):
    values=sorted(values)
    return values[round((len(values)-1)*.005)],values[round((len(values)-1)*.995)]
lo=Vector([limits([p[i] for p in points])[0] for i in range(3)])
hi=Vector([limits([p[i] for p in points])[1] for i in range(3)])
center=(lo+hi)*.5;radius=(hi-lo).length*.5
basis=json.loads((root/'camera-basis.json').read_text())
up=Vector(basis['up']);a=Vector(basis['axis_a']);b=Vector(basis['axis_b'])
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO';scene.display.shading.color_type='VERTEX'
scene.display.shading.show_shadows=True;scene.display.shading.show_cavity=True
scene.display.shading.cavity_type='BOTH';scene.display.shading.background_type='WORLD'
scene.world.color=(.045,.05,.06)
scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
camera_data=bpy.data.cameras.new('Camera');camera=bpy.data.objects.new('Camera',camera_data)
scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO'
camera_data.clip_start=max(radius*.00001,.00001);camera_data.clip_end=radius*100
aspect=scene.render.resolution_x/scene.render.resolution_y
for name,direction in [('019_RGB_fachadas_A',a-b+up*.7),('019_RGB_fachadas_B',-a-b+up*.7)]:
    direction.normalize();right=(-direction).cross(up).normalized();camera_up=direction.cross(right).normalized()
    rotation=Matrix((right,camera_up,direction)).transposed();camera.rotation_euler=rotation.to_euler()
    projected=[rotation.transposed()@(p-center) for p in points]
    x0,x1=limits([p.x for p in projected]);y0,y1=limits([p.y for p in projected])
    camera.location=center+rotation@Vector(((x0+x1)*.5,(y0+y1)*.5,0.))+direction*radius*8
    camera_data.ortho_scale=max(x1-x0,(y1-y0)*aspect)*1.12
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'019_simplificada70_RGB_preview.blend'))
