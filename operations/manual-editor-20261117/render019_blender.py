import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
objects=[]
for path in sorted((root/'render_parts').glob('*.ply')):
    bpy.ops.wm.ply_import(filepath=str(path))
    objects.append(bpy.context.object)
assert len(objects)==26
for obj in objects:obj.select_set(True)
bpy.context.view_layer.objects.active=objects[0]
bpy.ops.object.join()
obj=bpy.context.object;obj.name='019_unida_preview_geometria'
points=[obj.matrix_world@Vector(corner) for corner in obj.bound_box]
lo=Vector([min(p[i] for p in points) for i in range(3)])
hi=Vector([max(p[i] for p in points) for i in range(3)])
center=(lo+hi)*.5;radius=max((p-center).length for p in points)
assert radius>0
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.display.shading.light='STUDIO'
scene.display.shading.studiolight_rotate_z=math.radians(30)
scene.display.shading.color_type='SINGLE'
scene.display.shading.single_color=(.65,.68,.72)
scene.display.shading.show_shadows=True
scene.display.shading.show_cavity=True
scene.display.shading.cavity_type='BOTH'
scene.display.shading.show_specular_highlight=True
scene.display.shading.show_backface_culling=False
scene.display.shading.background_type='WORLD'
scene.world.color=(.045,.05,.06)
scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
camera_data=bpy.data.cameras.new('Camera');camera=bpy.data.objects.new('Camera',camera_data)
scene.collection.objects.link(camera);scene.camera=camera;camera_data.type='ORTHO'
camera_data.ortho_scale=radius*2.3*scene.render.resolution_x/scene.render.resolution_y
camera_data.clip_start=max(radius*.00001,.00001);camera_data.clip_end=radius*20
for name,direction in [('019_vista_oblicua',Vector((1.,-1.,.9))),('019_vista_superior',Vector((.001,-.001,1.)))]:
    camera.location=center+direction.normalized()*radius*4
    camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath=str(root/(name+'.png'))
    bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'019_preview_render.blend'))
(root/'render-report.json').write_text(json.dumps(dict(render='real mesh geometry, neutral solid material; not textured',
    preview_decimated=True,full_resolution_mesh=str(root/'manzana019_unida.ply'),
    camera_framing='all geometry bounds; native Z for top view',parts=26),indent=2))
