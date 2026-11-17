"""Additional low-angle geometry views. Original mesh data remains unchanged."""
import array
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector,Matrix
root=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.wm.open_mainfile(filepath=str(root/'019_preview_render.blend'))
scene=bpy.context.scene
obj=next(o for o in scene.objects if o.type=='MESH')
raw=array.array('f',[0.])*(len(obj.data.vertices)*3)
obj.data.vertices.foreach_get('co',raw)
step=max(1,len(obj.data.vertices)//100000)
points=[Vector(raw[i*3:i*3+3]) for i in range(0,len(obj.data.vertices),step)]
def limits(values):
    values=sorted(values)
    return values[round((len(values)-1)*.005)],values[round((len(values)-1)*.995)]
lo=Vector([limits([p[i] for p in points])[0] for i in range(3)])
hi=Vector([limits([p[i] for p in points])[1] for i in range(3)])
center=(lo+hi)*.5;radius=(hi-lo).length*.5
camera=scene.camera;aspect=scene.render.resolution_x/scene.render.resolution_y
scene.display.shading.single_color=(.78,.78,.76)
scene.display.shading.studiolight_rotate_z=.7
views=[]
basis=json.loads((root/'camera-basis.json').read_text())
up=Vector(basis['up']);axis_a=Vector(basis['axis_a']);axis_b=Vector(basis['axis_b'])
for name,direction in [
    ('019_fachadas_A',axis_a-axis_b+up*.55),
    ('019_fachadas_B',-axis_a-axis_b+up*.55),
    ('019_fachadas_C',-axis_a+axis_b+up*.55),
    ('019_fachadas_D',axis_a+axis_b+up*.55),
]:
    direction.normalize()
    right=(-direction).cross(up).normalized();camera_up=direction.cross(right).normalized()
    rotation=Matrix((right,camera_up,direction)).transposed()
    camera.rotation_euler=rotation.to_euler();inverse=rotation.transposed()
    projected=[inverse@(p-center) for p in points]
    x0,x1=limits([p.x for p in projected]);y0,y1=limits([p.y for p in projected])
    shifted=center+rotation@Vector(((x0+x1)*.5,(y0+y1)*.5,0.))
    camera.location=shifted+direction*radius*8
    camera.data.ortho_scale=max(x1-x0,(y1-y0)*aspect)*1.12
    camera.data.clip_end=max(camera.data.clip_end,radius*100)
    scene.render.filepath=str(root/(name+'.png'));bpy.ops.render.render(write_still=True)
    views.append(dict(image=scene.render.filepath,framing='central 99 percent of sampled projected vertices'))
(root/'facade-render-report.json').write_text(json.dumps(dict(views=views,
    preview_proxy=True,mesh_unchanged=True,neutral_material=True),indent=2))
