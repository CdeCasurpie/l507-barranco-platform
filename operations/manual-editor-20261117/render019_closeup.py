import json
from pathlib import Path
import sys
import bpy
import array
from mathutils import Vector
root=Path(sys.argv[sys.argv.index('--')+1])
bpy.ops.wm.open_mainfile(filepath=str(root/'019_preview_render.blend'))
scene=bpy.context.scene
obj=next(o for o in scene.objects if o.type=='MESH')
raw=array.array('f',[0.])*(len(obj.data.vertices)*3)
obj.data.vertices.foreach_get('co',raw)
step=max(1,len(obj.data.vertices)//100000)
xyz=[Vector(raw[i*3:i*3+3]) for i in range(0,len(obj.data.vertices),step)]
def limits(values):
    ordered=sorted(values)
    return ordered[round((len(ordered)-1)*.005)],ordered[round((len(ordered)-1)*.995)]
camera=scene.camera
lo=Vector([limits([p[i] for p in xyz])[0] for i in range(3)])
hi=Vector([limits([p[i] for p in xyz])[1] for i in range(3)])
center=(lo+hi)*.5
radius=(hi-lo).length*.5
aspect=scene.render.resolution_x/scene.render.resolution_y
records=[]
for name,direction in [('019_detalle_oblicuo',Vector((1.,-1.,.9))),('019_detalle_superior',Vector((.001,-.001,1.)))]:
    direction.normalize()
    camera.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()
    rotation=camera.rotation_euler.to_matrix()
    inverse=rotation.transposed()
    projected=[inverse@(point-center) for point in xyz]
    x0,x1=limits([p.x for p in projected]);y0,y1=limits([p.y for p in projected])
    shifted=center+rotation@Vector(((x0+x1)*.5,(y0+y1)*.5,0.))
    camera.location=shifted+direction*radius*8
    camera.data.ortho_scale=max(x1-x0,(y1-y0)*aspect)*1.12
    camera.data.clip_end=max(camera.data.clip_end,radius*100)
    scene.render.filepath=str(root/(name+'.png'))
    bpy.ops.render.render(write_still=True)
    records.append(dict(image=scene.render.filepath,framing='central 99% projected vertex distribution; outlier fragments may be outside frame'))
(root/'closeup-report.json').write_text(json.dumps(dict(mesh_unchanged=True,render_proxy_decimated=True,views=records),indent=2))
