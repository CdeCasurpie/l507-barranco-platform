import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import threading
import sqlite3
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import graph_edit


def synthetic_model(root,num_images=3):
    root.mkdir()
    xyz=[((i%5-2)*.3,(i//5%4-2)*.3,5.+i/30) for i in range(60)]
    (root/'cameras.bin').write_bytes(struct.pack('<QiiQQddd',1,1,0,1000,1000,500.,500.,500.))
    with (root/'images.bin').open('wb') as f:
        f.write(struct.pack('<Q',num_images))
        for image in range(1,num_images+1):
            center=image-1.
            f.write(struct.pack('<i7di',image,1.,0.,0.,0.,-center,0.,0.,1))
            f.write(('phone/video_%06d.jpg'%image).encode()+b'\0')
            f.write(struct.pack('<Q',len(xyz)))
            for index,(x,y,z) in enumerate(xyz,1):
                f.write(struct.pack('<ddq',500+500*(x-center)/z,500+500*y/z,index))
    with (root/'points3D.bin').open('wb') as f:
        f.write(struct.pack('<Q',len(xyz)))
        for index,(x,y,z) in enumerate(xyz,1):
            f.write(struct.pack('<QdddBBBdQ',index,x,y,z,100,150,200,0.,num_images))
            for image in range(1,num_images+1):f.write(struct.pack('<II',image,index-1))
    return root


class GraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='/tmp/opencode');self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.model=synthetic_model(self.root/'model')
        # Explicit derived DB input for low-level triangulation tests.
        self.database=self.root/'matches.db'
        with sqlite3.connect(self.database) as connection:
            connection.execute('CREATE TABLE images(image_id INTEGER,name TEXT)')
            connection.execute('CREATE TABLE two_view_geometries(pair_id INTEGER,rows INTEGER,cols INTEGER,data BLOB)')
            for i in range(1,4):
                connection.execute('INSERT INTO images VALUES (?,?)',(i,'phone/video_%06d.jpg'%i))
            for a,b in [(1,2),(1,3),(2,3)]:
                blob=b''.join(struct.pack('<II',i,i) for i in range(60))
                connection.execute('INSERT INTO two_view_geometries VALUES (?,?,?,?)',(2147483647*a+b,60,2,blob))
        self.meta,_=graph_edit.get_graph(self.model)
        self.body=dict(revision=self.meta['revision'],stiffness=1.,pins=[
            dict(id=1,target=[0.,0.,0.],kind='anchor'),
            dict(id=3,target=[2.03,0.,0.],kind='move')])

    def test_graph_has_tracks_and_constraints_propagate_without_source_writes(self):
        before=graph_edit.fingerprint(self.model)
        result=graph_edit.solve(self.model,self.body)
        self.assertEqual(result['displacements'][0],[0.,0.,0.])
        self.assertAlmostEqual(result['displacements'][2][0],.03)
        self.assertGreater(result['displacements'][1][0],0)
        self.assertLess(result['displacements'][1][0],.03)
        self.assertEqual(graph_edit.fingerprint(self.model),before)
        self.assertTrue(any(e['kind']=='visual' for e in self.meta['edges']))

    def test_drafts_are_immutable_and_never_approve_geometry(self):
        with patch.object(graph_edit,'STATE',self.root/'drafts'):
            first=graph_edit.save_revision(self.model,self.body,'dataset','0')
            second=graph_edit.save_revision(self.model,self.body,'dataset','0')
            self.assertNotEqual(first['id'],second['id'])
            self.assertFalse(first['geometry_approved'])
            self.assertFalse(first['dense_authorized'])

    def test_stale_revision_and_moving_fixed_anchor_are_rejected(self):
        bad=dict(self.body,revision='old')
        with self.assertRaises(ValueError):graph_edit.solve(self.model,bad)
        self.body['pins'][0]['target']=[.1,0,0]
        with self.assertRaises(ValueError):graph_edit.solve(self.model,self.body)

    def test_bone_rotation_propagates_and_anchor_does_not_rotate(self):
        import numpy as np
        self.body['pins'][1]['rotation']=[0,0,30]
        result=graph_edit.solve(self.model,self.body)
        np.testing.assert_allclose(result['rotations'][0],np.eye(3),atol=1e-10)
        self.assertGreater(result['rotations'][2][1][0],.49)
        self.assertGreater(result['rotations'][1][1][0],0)
        self.assertAlmostEqual(result['displacements'][2][0],.03)

    def test_camera_exclusion_is_saved_and_cannot_be_pinned(self):
        self.body['deleted']=[2]
        result=graph_edit.solve(self.model,self.body)
        with patch.object(graph_edit,'STATE',self.root/'drafts'):
            saved=graph_edit.save_revision(self.model,self.body,'dataset','0')
            self.assertEqual(saved['deleted'],[2])
        self.body['deleted']=[1]
        with self.assertRaises(ValueError):graph_edit.solve(self.model,self.body)

    def test_elastic_influence_has_rigid_core_and_finite_graph_support(self):
        meta=dict(self.meta,cameras=[dict(id=i,center=[float(i),0,0]) for i in range(7)],
                  edges=[dict(a=i,b=i+1,weight=1.) for i in range(5)])
        body=dict(revision=meta['revision'],radius=4,pins=[
            dict(id=0,target=[0.,1.,0.],kind='move')])
        with patch.object(graph_edit,'get_graph',return_value=(meta,b'')):
            result=graph_edit.solve(self.model,body)
            self.assertAlmostEqual(result['displacements'][1][1],1.)
            self.assertGreater(result['displacements'][2][1],result['displacements'][3][1])
            self.assertEqual(result['displacements'][4],[0.,0.,0.])
            self.assertEqual(result['displacements'][6],[0.,0.,0.])
            body['direct_only']=True
            direct=graph_edit.solve(self.model,body)
            self.assertGreater(direct['displacements'][1][1],0)
            self.assertEqual(direct['displacements'][2],[0.,0.,0.])

    def test_synthetic_derived_adjustment_keeps_source_and_pins(self):
        import graph_job
        try:import pycolmap
        except ImportError:self.skipTest('Requires alignment311')
        if pycolmap.__version__!='3.11.1':self.skipTest('Requires alignment311')
        before=graph_edit.fingerprint(self.model)
        deformation=graph_edit.solve(self.model,self.body)
        job=self.root/'job';job.mkdir()
        (job/'request.json').write_text(json.dumps(dict(
            draft=dict(source_model=str(self.model),source_hashes=before,pins=self.body['pins']),
            database_path=str(self.database),camera_ids=[c['id'] for c in self.meta['cameras']],displacements=deformation['displacements'])))
        graph_job.compute(job)
        report=json.loads((job/'report.json').read_text())
        self.assertTrue(report['quality_screen_passed'])
        self.assertFalse(report['geometry_approved'])
        self.assertFalse(report['dense_authorized'])
        self.assertEqual(graph_edit.fingerprint(self.model),before)
        self.assertLess(max(report['pin_errors'].values()),1e-6)
        self.assertTrue((job/'candidate/images.bin').exists())

    def test_original_poses_can_be_retriangulated_without_manual_pins(self):
        import graph_job
        import pycolmap
        if pycolmap.__version__!='3.11.1':self.skipTest('Requires alignment311')
        job=self.root/'original-job';job.mkdir()
        before=graph_edit.fingerprint(self.model)
        (job/'request.json').write_text(json.dumps(dict(
            draft=dict(source_model=str(self.model),source_hashes=before,pins=[]),
            database_path=str(self.database),camera_ids=[1,2,3],
            displacements=[[0.,0.,0.]]*3)))
        graph_job.compute(job)
        report=json.loads((job/'report.json').read_text())
        self.assertFalse(report['ba_executed'])
        self.assertEqual(report['pin_errors'],{})
        self.assertGreater(report['points'],0)
        self.assertEqual(graph_edit.fingerprint(self.model),before)

    def test_derived_adjustment_with_deleted_camera_has_no_invalid_pose_access(self):
        import graph_job
        import pycolmap
        if pycolmap.__version__!='3.11.1':self.skipTest('Requires alignment311')
        self.model=synthetic_model(self.root/'five-view-model',num_images=5)
        self.meta,_=graph_edit.get_graph(self.model)
        self.body['revision']=self.meta['revision']
        with sqlite3.connect(self.database) as connection:
            connection.execute('INSERT INTO images VALUES (?,?)',(4,'phone/video_000004.jpg'))
            connection.execute('INSERT INTO images VALUES (?,?)',(5,'phone/video_000005.jpg'))
            blob=b''.join(struct.pack('<II',i,i) for i in range(60))
            for a in (1,2,3):
                connection.execute('INSERT INTO two_view_geometries VALUES (?,?,?,?)',
                                   (2147483647*a+4,60,2,blob))
        self.body['deleted']=[2]
        before=graph_edit.fingerprint(self.model)
        deformation=graph_edit.solve(self.model,self.body)
        job=self.root/'deleted-job';job.mkdir()
        (job/'request.json').write_text(json.dumps(dict(
            draft=dict(source_model=str(self.model),source_hashes=before,pins=self.body['pins'],deleted=[2]),
            database_path=str(self.database),camera_ids=[c['id'] for c in self.meta['cameras']],displacements=deformation['displacements'],
            rotations=deformation['rotations'])))
        graph_job.compute(job)
        candidate=pycolmap.Reconstruction(str(job/'candidate'))
        self.assertEqual(set(candidate.reg_image_ids()),{1,3,4,5})
        self.assertEqual(json.loads((job/'report.json').read_text())['unmatched_camera_ids'],[5])
        self.assertFalse(json.loads((job/'report.json').read_text())['ba_executed'])
        self.assertEqual(graph_edit.fingerprint(self.model),before)

    def test_http_editor_requires_local_origin_and_preserves_sources(self):
        import catalog_app
        collection=self.root/'collection';dataset=collection/'test-019'
        model=dataset/'colmap/sparse/0'
        model.parent.mkdir(parents=True)
        synthetic_model(model)
        (dataset/'colmap/best_model.txt').write_text('0')
        (dataset/'collection.json').write_text(json.dumps({'sha256_verified':True}))
        state=self.root/'state'
        with patch.object(graph_edit,'STATE',state),patch.object(catalog_app,'STATE',state):
            server=ThreadingHTTPServer(('127.0.0.1',0),catalog_app.Gallery)
            server.collection=collection
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base='http://127.0.0.1:'+str(server.server_port)
            try:
                rows=json.load(urlopen(base+'/api/datasets'))
                identity=next(r['id'] for r in rows if r['label']=='test-019')
                prefix=base+'/api/editor/'+identity+'/0/'
                meta=json.load(urlopen(prefix+'graph'))
                body=dict(self.body,revision=meta['revision'])
                before=graph_edit.fingerprint(model)
                request=Request(prefix+'save',data=json.dumps(body).encode(),
                                headers={'Content-Type':'application/json'},method='POST')
                with self.assertRaises(HTTPError) as raised:urlopen(request)
                self.assertEqual(raised.exception.code,403)
                request.add_header('Origin',base);request.add_header('X-Barranco-Editor','1')
                result=json.load(urlopen(request))
                self.assertEqual(result['status'],'manual_draft_unvalidated')
                self.assertEqual(graph_edit.fingerprint(model),before)
                with urlopen(base+'/view/'+identity+'/editor/0') as response:
                    self.assertIn(b'graph_editor.js',response.read())
                anchor=next(r for r in rows if 'ancla fija' in r['label'])
                with self.assertRaises(HTTPError) as raised:
                    urlopen(base+'/api/editor/'+anchor['id']+'/0/graph')
                self.assertEqual(raised.exception.code,403)
            finally:server.shutdown();server.server_close()


if __name__=='__main__':unittest.main()
