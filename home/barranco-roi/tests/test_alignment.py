"""Synthetic control-plane/HTTP tests. Never align or approve production data."""
import importlib.util
from collections import OrderedDict
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import subprocess
import struct
import os
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, "/data/repos/Alineacion-point-cloud/src")
spec = importlib.util.spec_from_file_location("manual_fixture", "/data/repos/Alineacion-point-cloud/tests/test_manual.py")
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)

from app import Handler, ThreadingHTTPServer
from roi.alignment import AlignmentService
from roi.catalog import BlockCatalog
from roi.core import InputError, atomic_json
from roi.multi import MultiReviewService


class AlignmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir="/tmp/opencode")
        self.root = Path(self.temp.name)
        target, _ = fixture.make_scene(self.root/"target")
        source, self.truth = fixture.make_scene(self.root/"source", incoming=True)
        self.manifest = {**source, "block_id": "026"}
        self.input_path = self.root/"source/block.json"
        atomic_json(self.input_path, self.manifest)
        catalog = BlockCatalog.__new__(BlockCatalog)
        catalog.data = self.root; catalog.origin = [100,200,0]
        catalog.records = {"A": {"model": Path(target["sparse"]["model_uri"]), "transform": np.eye(4),
            "node": "test-node", "native_source_root": str(self.root/"target"), "run": self.root/"target",
            "entry":{"block":"A","categorical_rgb":[100,120,140]}, "block":"A",
            "sparse_count":160,"dense_count":0,"batch_count":0,"placement":"existing_alignment"}}
        catalog.transforms = {"A": np.eye(4)}
        catalog.alignment_audit = {"manual_blocks":[]}
        catalog.lock=threading.RLock();catalog.cache=OrderedDict();catalog._overview=None
        self.service = AlignmentService(catalog, self.root/"state", discover=False)
        self.row = self.service.register(source["sparse"]["model_uri"],"026","synthetic",manifest=str(self.input_path))
        self.payload = {"reconstruction": self.row["id"], "anchor_revision": self.service.anchor_revision,
            "matrix": self.truth.tolist(), "edges":[{"anchor":"A",
                "forward":{"views":[{"id":i,"role":"fit" if i<7 else "validation"} for i in range(1,9)],
                           "pairs":[{"query":i,"support":i%8+1} for i in range(1,9)]},
                "reverse":{"views":[],"pairs":[]}}]}
        self.server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        self.server.alignment=self.service
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()

    def request(self,path,payload=None,origin=None):
        kwargs={} if payload is None else {"data":json.dumps(payload).encode(),"headers":{
            "Content-Type":"application/json","X-ROI-Client":"local-editor",**({"Origin":origin} if origin else {})}}
        with urlopen(Request(self.url+path,**kwargs)) as r:
            return json.load(r)

    def test_routes_dont_resolve_a_default_accepted_block_and_no_gps_is_needed(self):
        catalog=self.request("/api/alignment/catalog")
        self.assertEqual(len(catalog["anchors"]),1)
        self.assertEqual(len(catalog["pending"]),1)
        self.assertTrue(catalog["pending"][0]["matching_ready"])
        geometry=self.request("/api/alignment/geometry/"+self.row["id"])
        self.assertEqual(len(geometry["views"]),8)
        saved=self.request("/api/alignment/sessions",self.payload)
        self.assertEqual(saved["edges"],self.payload["edges"])
        self.assertEqual(self.request("/api/alignment/sessions/"+saved["id"])["matrix"],self.payload["matrix"])
        self.assertEqual(list((self.root/"state/alignment/jobs").glob("*/request.json")),[])

    def test_manual_approval_requires_confirmation_and_keeps_anchors_exact(self):
        before=self.service.anchors["A"]["matrix"]
        saved=self.service.save(self.payload)
        with self.assertRaises(InputError):
            self.service.approve({"session_id":saved["id"]})
        p=self.service.approve({"session_id":saved["id"],"confirm_manual":True})
        self.assertEqual(p["validation"],"manual_unvalidated")
        self.assertEqual(self.service.anchors["A"]["matrix"],before)
        dataset=self.service.catalog.get(p["id"])
        self.assertTrue(np.isfinite(dataset.world).all())
        self.assertEqual(dataset.placement,"manual_unvalidated")
        self.assertNotEqual(p["id"],"026")
        self.assertIn(p["id"],self.service.anchors)

    def test_invalid_sim3_pairs_stale_revision_and_cross_origin_rejected(self):
        cases=[]
        bad=json.loads(json.dumps(self.payload));bad["matrix"][0][0]*=2;cases.append(bad)
        bad=json.loads(json.dumps(self.payload));bad["anchor_revision"]="stale";cases.append(bad)
        bad=json.loads(json.dumps(self.payload));bad["edges"][0]["forward"]["pairs"][0]["query"]=999;cases.append(bad)
        bad=json.loads(json.dumps(self.payload));bad["edges"][0]["forward"]["views"][0]["role"]="automatic";cases.append(bad)
        for value in cases:
            with self.assertRaises(HTTPError):self.request("/api/alignment/sessions",value)
        with self.assertRaises(HTTPError) as error:
            self.request("/api/alignment/sessions",self.payload,"https://elsewhere.invalid")
        self.assertEqual(error.exception.code,403)

    def test_candidates_preserve_query_selection_and_path_escape_rejected(self):
        result=self.service.candidates({"session":self.payload,"anchor":"A","direction":"forward","limit":2})
        self.assertEqual({p["query"] for p in result["pairs"]},set(range(1,9)))
        self.assertEqual(len(result["pairs"]),16)
        self.assertEqual(len(self.payload["edges"][0]["forward"]["views"]),8)
        with self.assertRaises(InputError):self.service.allowed("/etc/passwd")
        with self.assertRaises(InputError):self.service.register(self.row["model"],"023","rejected")

    def test_frozen_job_code_and_real_limits_are_in_submission(self):
        anchor={**self.manifest,"block_id":"A","sparse":{"model_uri":self.service.anchors["A"]["model"]}}
        # Use the actual target DB/photos for the target model.
        anchor["features"]={"database_uri":str(self.root/"target/features.db"),"family":"sift"}
        anchor["images"]={"root_uri":str(self.root/"target/frames")}
        path=self.root/"anchor.json";atomic_json(path,anchor);self.service.attach({"manifest":str(path)})
        saved=self.service.save(self.payload)
        completed=type("Completed",(),{"returncode":0,"stderr":""})()
        with patch("roi.alignment.subprocess.run",return_value=completed) as run:
            job=self.service.start({"session_id":saved["id"],"mode":"sim3"})
        command=run.call_args.args[0]
        self.assertIn("MemoryMax=40G",command)
        self.assertIn("KillMode=control-group",command)
        directory=self.root/"state/alignment/jobs"/job["id"]
        self.assertTrue((directory/"src/blockalign/manual.py").is_file())
        self.assertTrue((directory/"worker.py").is_file())
        request=json.loads((directory/"request.json").read_text())
        self.assertEqual(request["session"]["edges"],self.payload["edges"])
        self.assertFalse((directory/"result.json").exists())

    def test_native_supervised_worker_with_synthetic_data_only(self):
        path=self.root/"anchor.json"
        atomic_json(path, {"block_id":"A","sparse":{"model_uri":self.service.anchors["A"]["model"]},
            "features":{"database_uri":str(self.root/"target/features.db"),"family":"sift"},
            "images":{"root_uri":str(self.root/"target/frames")}})
        self.service.attach({"manifest":str(path)})
        saved=self.service.save(self.payload)
        job=self.service.start({"session_id":saved["id"],"mode":"ba"})
        try:
            deadline=time.monotonic()+45
            status=job
            while status["state"] in ("queued","running") and time.monotonic()<deadline:
                time.sleep(.1);status=self.service.job(job["id"])
            if status["state"]!="completed":
                log=self.root/"state/alignment/jobs"/job["id"]/"error.log"
                self.fail(str(status)+"\n"+(log.read_text() if log.exists() else "no worker error log"))
            result=self.service.result(job["id"])
            self.assertTrue(result["validated"])
            self.assertTrue(result["ba"]["anchors_fixed"])
            self.assertEqual(result["ba"]["reserved_relocalized"],2)
            p=self.service.approve({"session_id":saved["id"],"job_id":job["id"]})
            self.assertTrue(p["dense_requires_regeneration"])
            self.assertEqual(self.service.catalog.get(p["id"]).transform.tolist(),np.eye(4).tolist())
        finally:
            subprocess.run(["systemctl","--user","stop",job["unit"]],capture_output=True)

    def test_cancel_targets_only_its_own_service_and_missing_inputs_do_not_launch(self):
        key="j-test-cancellation";directory=self.root/"state/alignment/jobs"/key;directory.mkdir()
        atomic_json(directory/"status.json",{"id":key,"state":"running","created_at":time.time(),
                    "unit":"barranco-align-"+key})
        with patch("roi.alignment.subprocess.run") as run:
            cancelled=self.service.cancel(key)
        self.assertEqual(cancelled["state"],"cancelled")
        self.assertEqual(run.call_args.args[0],["systemctl","--user","stop","barranco-align-"+key])
        saved=self.service.save(self.payload)
        with patch("roi.alignment.subprocess.run") as run:
            with self.assertRaisesRegex(InputError,"faltan"):
                self.service.start({"session_id":saved["id"],"mode":"sim3"})
            run.assert_not_called()

    def test_changed_geometry_never_reuses_a_saved_revision(self):
        path=Path(self.row["model"])/"points3D.bin"
        path.write_bytes(path.read_bytes()+b"changed")
        with self.assertRaisesRegex(InputError,"cambió"):
            self.service.save(self.payload)

    def test_compact_geometry_is_cached_and_versioned_without_loading_other_clouds(self):
        version=self.service.geometry_version(self.row["id"])
        from roi.catalog import read_sparse_points
        with patch("roi.alignment.read_sparse_points",wraps=read_sparse_points) as read:
            first,etag=self.service.render_cloud(self.row["id"],version)
            second,_=self.service.render_cloud(self.row["id"],version)
            self.assertIs(first,second);self.assertEqual(read.call_count,1)
        length=struct.unpack("<I",first[:4])[0]
        header=json.loads(first[4:4+length])
        self.assertEqual(header["format"],2)
        self.assertEqual(len(header["views"]),8)
        self.assertEqual(len(first)-4-length,header["render_count"]*16)
        vertices=np.frombuffer(first,offset=4+length,dtype=[("xyz","<f4",(3,)),("rgba","u1",(4,))])
        xyz,_=read_sparse_points(self.row["model"])
        np.testing.assert_allclose(vertices["xyz"]+header["origin"],xyz,atol=1e-6)
        request=Request(self.url+"/api/alignment/cloud/"+self.row["id"]+"?v="+version)
        with urlopen(request) as response:
            self.assertEqual(response.headers["ETag"],etag)
            self.assertIn("immutable",response.headers["Cache-Control"])
        with self.assertRaises(HTTPError) as unchanged:
            urlopen(Request(request.full_url,headers={"If-None-Match":etag}))
        self.assertEqual(unchanged.exception.code,304)
        with self.assertRaises(InputError):
            self.service.render_cloud(self.row["id"],"old")

    def test_catalog_does_not_decode_points_and_identity_cache_detects_changes(self):
        with patch("roi.alignment.read_sparse_points",side_effect=AssertionError("metadata must be cheap")):
            payload=self.service.catalog_payload()
        self.assertIn("geometry_version",payload["pending"][0])
        self.service.identity(self.row["model"])
        with patch("roi.alignment.model_identity",side_effect=AssertionError("cached identity")):
            self.assertEqual(self.service.identity(self.row["model"]),self.row["hashes"])

    def test_thumbnail_is_decoded_once_per_photo_revision(self):
        from PIL import Image
        with patch("PIL.Image.open",wraps=Image.open) as opened:
            first=self.service.thumbnail(self.row["id"],1)
            second=self.service.thumbnail(self.row["id"],1)
            self.assertEqual(first,second);self.assertEqual(opened.call_count,1)

    def test_render_revision_changes_even_if_mtime_is_restored(self):
        key=self.row["id"];version=self.service.geometry_version(key)
        self.service.render_cloud(key,version)
        path=Path(self.row["model"])/"points3D.bin";stamp=path.stat()
        path.write_bytes(path.read_bytes()+b"modified")
        os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
        self.assertNotEqual(self.service.geometry_version(key),version)
        with self.assertRaisesRegex(InputError,"revisión visual"):
            self.service.render_cloud(key,version)


if __name__=="__main__":
    unittest.main()
