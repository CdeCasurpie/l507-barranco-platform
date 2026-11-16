"""Run inside Blender; stdlib only. Build/audit 15 unique editable mesh objects."""
import array
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy
from mathutils import Quaternion


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for raw in iter(lambda:f.read(8*1024**2),b''):h.update(raw)
    return h.hexdigest()


def read_array(root,spec,typecode,count):
    path=root/spec['path']
    assert sha(path)==spec['sha256']
    result=array.array(typecode)
    with path.open('rb') as f:
        result.fromfile(f,count)
        assert not f.read(1)
    return result


def atomic(path,value):
    temp=path.with_suffix('.json.new')
    temp.write_text(json.dumps(value,indent=2)+'\n')
    temp.replace(path)


def audit(root):
    started=time.monotonic()
    inputs=json.loads((root/'blender-inputs.json').read_text())
    objects=[obj for obj in bpy.context.scene.objects if obj.type=='MESH']
    assert len(objects)==15
    assert len({obj.data.as_pointer() for obj in objects})==15
    assert len(bpy.context.scene.objects)==15, 'Unexpected instancer/camera/extra object in delivery'
    records=[]
    for item in inputs['blocks']:
        obj=bpy.context.scene.objects.get(item['name'])
        assert obj is not None and obj.type=='MESH'
        assert obj.instance_type=='NONE' and obj.parent is None and obj.data.users==1
        assert all(abs(obj.matrix_world[i][j]-(1. if i==j else 0.))<1e-12 for i in range(4) for j in range(4))
        mesh=obj.data
        nv,nf=item['vertices'],item['faces']
        assert len(mesh.vertices)==nv and len(mesh.polygons)==nf and len(mesh.loops)==nf*3
        positions=array.array('f',[0.])*(nv*3)
        mesh.vertices.foreach_get('co',positions)
        assert hashlib.sha256(memoryview(positions)).hexdigest()==item['buffers']['positions']['sha256'], 'Coordinates changed'
        del positions
        indices=array.array('i',[0])*(nf*3)
        mesh.loops.foreach_get('vertex_index',indices)
        assert hashlib.sha256(memoryview(indices)).hexdigest()==item['buffers']['indices']['sha256'], 'Indices changed'
        del indices
        totals=array.array('i',[0])*nf
        mesh.polygons.foreach_get('loop_total',totals)
        assert all(v==3 for v in totals)
        del totals
        colors=array.array('f',[0.])*(nv*4)
        attribute=mesh.color_attributes.get('Color')
        assert attribute is not None and attribute.domain=='POINT'
        attribute.data.foreach_get('color_srgb',colors)
        color_hash=hashlib.sha256(memoryview(colors)).hexdigest()
        error=0.
        if color_hash!=item['buffers']['colors']['sha256']:
            expected=read_array(root,item['buffers']['colors'],'f',nv*4)
            error=max(abs(a-b) for a,b in zip(colors,expected))
            assert error<1e-5, 'Vertex color transfer changed beyond roundoff'
            del expected
        del colors
        records.append(dict(block=item['block'],object=obj.name,mesh_data=mesh.name,mesh_users=mesh.users,
                            instance_type=obj.instance_type,vertices=nv,faces=nf,color_max_error=error))
        print('AUDITED',obj.name,'unique mesh',mesh.name,'vertices',nv,'faces',nf,flush=True)
    result=dict(objects=15,unique_mesh_data=15,geometry_hashes_verified=True,colors_verified=True,blocks=records,
                blender_version=bpy.app.version_string,seconds=time.monotonic()-started,
                blend_bytes=(root/'barranco_15_manzanas_70pct.blend').stat().st_size)
    atomic(root/'blender-audit.json',result)
    print('ALL 15 OBJECTS INDEPENDENT AND VERIFIED',flush=True)


def build(root):
    started=time.monotonic()
    destination=root/'barranco_15_manzanas_70pct.blend'
    if destination.exists():
        bpy.ops.wm.open_mainfile(filepath=str(destination))
        return audit(root)
    inputs=json.loads((root/'blender-inputs.json').read_text())
    assert len(inputs['blocks'])==15 and sys.byteorder=='little'
    for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    collection=bpy.data.collections.new('Barranco_15_manzanas_70pct')
    bpy.context.scene.collection.children.link(collection)
    material=bpy.data.materials.new('Barranco_RGB_por_vertice')
    material.use_nodes=True
    attribute=material.node_tree.nodes.new('ShaderNodeAttribute')
    attribute.attribute_name='Color'
    shader=material.node_tree.nodes.get('Principled BSDF')
    material.node_tree.links.new(attribute.outputs['Color'],shader.inputs['Base Color'])
    shader.inputs['Roughness'].default_value=1.
    for item in inputs['blocks']:
        nv,nf=item['vertices'],item['faces']
        mesh=bpy.data.meshes.new(item['name']+'_Mesh')
        positions=read_array(root,item['buffers']['positions'],'f',nv*3)
        mesh.vertices.add(nv)
        mesh.vertices.foreach_set('co',positions)
        del positions
        indices=read_array(root,item['buffers']['indices'],'i',nf*3)
        mesh.loops.add(nf*3)
        mesh.loops.foreach_set('vertex_index',indices)
        del indices
        mesh.polygons.add(nf)
        mesh.polygons.foreach_set('loop_start',array.array('i',range(0,nf*3,3)))
        mesh.polygons.foreach_set('loop_total',array.array('i',[3])*nf)
        mesh.polygons.foreach_set('use_smooth',array.array('b',[1])*nf)
        mesh.update(calc_edges=True)
        colors=read_array(root,item['buffers']['colors'],'f',nv*4)
        attribute=mesh.color_attributes.new(name='Color',type='BYTE_COLOR',domain='POINT')
        attribute.data.foreach_set('color_srgb',colors)
        mesh.color_attributes.active_color_index=0
        del colors
        mesh.materials.append(material)
        obj=bpy.data.objects.new(item['name'],mesh)
        collection.objects.link(obj)
        obj['manzana']=item['block']
        obj['source_ply']=item['mesh']
        obj['source_sha256']=item['source_sha256']
        obj['coordinate_frame']='map_world'
        obj['face_reduction_target_percent']=70
        print('BUILT',obj.name,nv,'vertices',nf,'faces',flush=True)
    scene=bpy.context.scene
    scene.unit_settings.system='METRIC'
    scene.unit_settings.scale_length=1.
    scene['coordinate_frame']='map_world'
    scene['crs']=inputs['crs']
    scene['world_origin']=inputs['world_origin']
    scene['independent_block_objects']=15
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                space=area.spaces.active
                space.shading.type='SOLID'
                space.shading.color_type='VERTEX'
                space.clip_end=10000.
                space.region_3d.view_location=(215.,2.,-9.)
                space.region_3d.view_distance=650.
                space.region_3d.view_rotation=Quaternion((1.,0.,0.,0.))
                space.region_3d.view_perspective='ORTHO'
    obj=bpy.data.objects.get('Manzana_025')
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.wm.save_as_mainfile(filepath=str(destination),compress=True,check_existing=False)
    atomic(root/'blender-build.json',dict(seconds=time.monotonic()-started,bytes=destination.stat().st_size,
                objects=15,blender_version=bpy.app.version_string))
    print('SAVED INDEPENDENT BLOCK SCENE',destination,flush=True)


if __name__=='__main__':
    arguments=sys.argv[sys.argv.index('--')+1:]
    root=Path(arguments[0]).resolve()
    if arguments[1]=='build':build(root)
    elif arguments[1]=='audit':audit(root)
    else:raise ValueError('Expected build or audit')
