"""Local manual-alignment control plane. Workers own all heavy computation."""
from collections import OrderedDict
import io
import json
import math
import os
from pathlib import Path
import signal
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid

import numpy as np

from .core import InputError, atomic_json, digest, sha_file
from .catalog import read_sparse_points
from .service import safe_id

REPO = Path("/data/repos/Alineacion-point-cloud")
PYTHON = Path("/data/barranco/runtime/alignment313/bin/python")
ROOT = Path(__file__).resolve().parents[1]
if str(REPO/"src") not in sys.path:
    sys.path.insert(0, str(REPO/"src"))
from alignexp.binary import images as read_views
from blockalign.manual import propose, policy, ManualError
from blockalign.graph import similarity


def load(path):
    return json.loads(Path(path).read_text())


def model_identity(model):
    return {n: sha_file(Path(model)/n) for n in ("cameras.bin", "images.bin", "points3D.bin")}


def count(path):
    with Path(path).open("rb") as f:
        return struct.unpack("<Q", f.read(8))[0]


class AlignmentService:
    def __init__(self, catalog, state, *, discover=True):
        self.catalog = catalog
        self.root = Path(state)/"alignment"
        self.lock = threading.RLock()
        self.image_gate = threading.BoundedSemaphore(2)
        self.processes = {}
        self.cache = OrderedDict()
        self.render_cache = OrderedDict()
        self.view_cache = OrderedDict()
        self.thumbnail_cache = OrderedDict()
        self.identity_cache = OrderedDict()
        for name in ("reconstructions", "sessions", "jobs", "placements"):
            (self.root/name).mkdir(parents=True, exist_ok=True)
        self.anchors = {}
        for block, record in catalog.records.items():
            if block == "023":
                continue
            self.anchors[block] = {"id": block, "block": block, "matrix": record["transform"].tolist(),
                "model": str(record["model"]), "node": record["node"],
                "hashes": self.identity(record["model"]),
                "native_source_root": str(record["native_source_root"]),
                "input_manifest": None}
        self.anchor_revision = digest({"origin": catalog.origin, "anchors": self.anchors})
        active = catalog.data/"active/manifest.json"
        self.accepted_manifest_sha = sha_file(active) if active.is_file() else None
        snapshot = self.root/"anchors.json"
        body = {"id": self.anchor_revision, "world_origin": catalog.origin, "anchors": self.anchors}
        if snapshot.exists() and load(snapshot) != body:
            raise InputError("El conjunto de anclas cambió. Usa un estado nuevo; no se reoptimiza el anterior.")
        if not snapshot.exists():
            atomic_json(snapshot, body)
        self.records = {p.stem: load(p) for p in (self.root/"reconstructions").glob("*.json")}
        # Reconcile only this app's named services; never kill unrelated processes.
        for p in (self.root/"jobs").glob("*/status.json"):
            row = load(p)
            if row["state"] in ("queued", "running"):
                active = subprocess.run(["systemctl", "--user", "is-active", row["unit"]],
                                        capture_output=True, text=True).stdout.strip() == "active"
                if not active:
                    atomic_json(p, {**row, "state": "interrupted", "error": "Worker interrupted; inspect logs"})
        if discover:
            self.discover()
        self.restore_placements()

    def discover(self):
        """Only known review roots. Discovering a sparse never approves it."""
        for model in sorted((self.catalog.data/"review").glob("*/*/colmap/sparse/*")):
            if not (model/"images.bin").is_file():
                continue
            run = model.parent.parent.parent
            receipt = load(run/"collection.json") if (run/"collection.json").is_file() else {}
            block = receipt.get("block", run.name.split("-")[0])
            if block == "023" or block in self.anchors:
                continue
            self.register(str(model), block, run.name, receipt.get("node"),
                          receipt.get("root"), None, automatic=True)
        # Native-compatible snapshots prepared by the existing importer.
        for path in sorted((self.catalog.data/"alignment-inputs").glob("**/block.json")):
            try:
                manifest = load(path)
                block = manifest["block_id"]
                if block in self.anchors:
                    for anchor in [self.anchors[block]]:
                        # Attach only when geometry/feature indices can correspond.
                        if self.identity(anchor["model"]) == self.identity(manifest["sparse"]["model_uri"]):
                            anchor["input_manifest"] = str(path)
                    continue
                hashes = self.identity(manifest["sparse"]["model_uri"])
                known = next((r for r in self.records.values() if r["hashes"] == hashes
                              and r.get("native_source_root") == manifest.get("provenance", {}).get("source_run")), None)
                if known:
                    self.attach({"manifest": str(path), "reconstruction": known["id"]})
                    continue
                self.register(manifest["sparse"]["model_uri"], block, path.parent.name,
                              None, manifest.get("provenance", {}).get("source_run"), str(path), automatic=True)
            except (OSError, ValueError, KeyError):
                continue

    def allowed(self, path):
        p = Path(path).expanduser().resolve()
        # No arbitrary filesystem access from HTTP.
        if not p.is_relative_to(self.catalog.data.resolve()) and not p.is_relative_to((self.root/"jobs").resolve()):
            raise InputError("La entrada debe estar dentro de "+str(self.catalog.data))
        return p

    @staticmethod
    def file_stamp(path):
        s = Path(path).stat()
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

    def model_stamp(self, model):
        return tuple(self.file_stamp(Path(model)/n) for n in ("cameras.bin", "images.bin", "points3D.bin"))

    def identity(self, model):
        """Avoid rehashing unchanged multi-GB models during every editor request.

        A changed inode/size/mtime/ctime forces a new hash. Workers independently
        hash their inputs again; this cache never replaces job integrity audits.
        """
        stamp = (str(model), self.model_stamp(model))
        with self.lock:
            if stamp not in self.identity_cache:
                hashes = model_identity(model)
                if stamp[1] != self.model_stamp(model):
                    raise InputError("La sparse cambió durante la verificación.")
                self.identity_cache[stamp] = hashes
                while len(self.identity_cache) > 64:
                    self.identity_cache.popitem(last=False)
            self.identity_cache.move_to_end(stamp)
            return self.identity_cache[stamp]

    def geometry_version(self, key):
        return digest({"format": 2, "model": self.record(key)["model"],
                       "stamp": self.model_stamp(self.record(key)["model"])})[:32]

    def view_rows(self, key):
        version = self.geometry_version(key)
        cache_key = (key, version)
        with self.lock:
            if cache_key not in self.view_cache:
                views = read_views(self.record(key)["model"])
                self.view_cache[cache_key] = [{"id": i, "name": v["name"], "camera_id": v["camera_id"],
                    "center": v["center"].tolist(), "R": v["R"].tolist(),
                    "direction": v["R"].T[:, 2].tolist()} for i, v in views.items()]
                while len(self.view_cache) > 24:
                    self.view_cache.popitem(last=False)
            self.view_cache.move_to_end(cache_key)
            return self.view_cache[cache_key]

    def render_cloud(self, key, version=None):
        """Compact, cached Float32 XYZ + RGBA packet; original XYZ stays intact."""
        current = self.geometry_version(key)
        if version is not None and version != current:
            raise InputError("La revisión visual cambió; actualiza el catálogo.")
        cache_key = (key, current)
        with self.lock:
            if cache_key not in self.render_cache:
                xyz, colors = read_sparse_points(self.record(key)["model"])
                bounds = np.quantile(xyz, [.005, .995], axis=0)
                origin = (bounds[0]+bounds[1])/2
                stride = max(1, math.ceil(len(xyz)/80000))
                selected = xyz[::stride]
                records = np.empty(len(selected), dtype=[("xyz", "<f4", (3,)), ("rgba", "u1", (4,))])
                records["xyz"] = selected-origin
                records["rgba"][:, :3] = colors[::stride]
                records["rgba"][:, 3] = 255
                header = json.dumps({"format": 2, "id": key, "version": current,
                    "origin": origin.tolist(), "bounds": bounds.tolist(),
                    "render_count": len(selected), "sparse_count": len(xyz),
                    "sampled": stride > 1, "views": self.view_rows(key)},
                    ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
                padded = header+b" "*((-len(header)) % 4)
                blob = struct.pack("<I", len(padded))+padded+records.tobytes()
                if current != self.geometry_version(key):
                    raise InputError("La sparse cambió mientras se preparaba la vista.")
                self.render_cache[cache_key] = blob
                while len(self.render_cache) > 12 or sum(map(len, self.render_cache.values())) > 64*1024**2:
                    self.render_cache.popitem(last=False)
            self.render_cache.move_to_end(cache_key)
            return self.render_cache[cache_key], '"cloud-'+current+'"'

    def register(self, model, block, label, node=None, native=None, manifest=None, automatic=False):
        model = self.allowed(model)
        if not isinstance(block, str) or not block or len(block) > 64 or block == "023":
            raise InputError("Manzana inválida o rechazada.")
        if block in self.anchors:
            raise InputError("Las anclas aceptadas no pueden reemplazarse.")
        hashes = self.identity(model)
        key = "r-"+digest({"model": str(model), "hashes": hashes})[:24]
        row = {"id": key, "block": block, "label": str(label)[:150], "component": model.name,
               "model": str(model), "hashes": hashes, "images": count(model/"images.bin"),
               "points": count(model/"points3D.bin"), "node": node,
               "native_source_root": native, "manifest": manifest, "created_at": time.time()}
        with self.lock:
            if key in self.records:
                old = self.records[key]
                if manifest and old.get("manifest") != manifest:
                    row = {**old, "manifest": manifest}
                    atomic_json(self.root/"reconstructions"/(key+".json"), row)
                    self.records[key] = row
                return self.records[key]
            atomic_json(self.root/"reconstructions"/(key+".json"), row)
            self.records[key] = row
        return row

    def attach(self, payload):
        """Attach an explicit, local snapshot. Missing original inputs block matching."""
        path = self.allowed(payload["manifest"])
        manifest = load(path)
        if manifest["features"].get("family", "sift") != "sift":
            raise InputError("Solo se admiten features SIFT compatibles con la sparse.")
        model = self.allowed(manifest["sparse"]["model_uri"])
        self.allowed(manifest["features"]["database_uri"])
        self.allowed(manifest["images"]["root_uri"])
        block = manifest["block_id"]
        target = payload.get("reconstruction")
        if target:
            row = self.record(target)
            if target in self.anchors or row["block"] != block or self.identity(model) != row["hashes"]:
                raise InputError("El snapshot no coincide con la reconstrucción seleccionada.")
            row = {**row, "manifest": str(path)}
            atomic_json(self.root/"reconstructions"/(target+".json"), row)
            self.records[target] = row
            return row
        if block in self.anchors:
            if self.identity(model) != self.identity(self.anchors[block]["model"]):
                # 3.11 -> 3.13 adds optional binary files, but legacy geometry bytes
                # must be identical before allowing an existing accepted placement.
                raise InputError("La sparse del snapshot no coincide byte a byte con el ancla.")
            self.anchors[block]["input_manifest"] = str(path)
            atomic_json(self.root/"anchor-inputs.json",
                        {k: a.get("input_manifest") for k, a in self.anchors.items()})
            return {"anchor": block, "attached": True}
        return self.register(str(model), block, path.parent.name, manifest=str(path))

    def record(self, key):
        if key in self.anchors:
            return self.anchors[key]
        if key not in self.records:
            raise InputError("Reconstrucción desconocida.")
        return self.records[key]

    def manifest(self, key):
        row = self.record(key)
        if row.get("reconstruction"):
            return self.manifest(row["reconstruction"])
        saved = self.root/"anchor-inputs.json"
        path = row.get("manifest") or row.get("input_manifest")
        if key in self.anchors and saved.exists():
            path = load(saved).get(key) or path
        if path:
            m = load(path)
            return {"sparse": m["sparse"], "features": m["features"], "images": m["images"]}
        model = Path(row["model"])
        if key in self.anchors:
            run = Path(self.catalog.records[key]["run"])
        else:
            run = model.parent.parent.parent
        db = run/"colmap/database.snapshot.db"
        if not db.is_file():
            db = run/"colmap/database.db"
        return {"sparse": {"model_uri": str(model)}, "features": {"database_uri": str(db), "family": "sift"},
                "images": {"root_uri": str(run/"frames")}}

    def availability(self, key):
        m = self.manifest(key)
        missing = []
        if not Path(m["features"]["database_uri"]).is_file():
            missing.append("base SIFT")
        if not Path(m["images"]["root_uri"]).is_dir():
            missing.append("fotos originales")
        return {"matching_ready": not missing, "missing": missing}

    def catalog_payload(self):
        placements = self.placement_rows()
        selection_path = self.root/"alignment-selection.json"
        selection = load(selection_path) if selection_path.is_file() else None
        visible = selection.get("reconstructions", {}) if selection else None
        return {"anchor_revision": self.anchor_revision, "world_origin": self.catalog.origin,
            "anchors": [{**{k: v for k, v in a.items() if k != "input_manifest"},
                         "geometry_version": self.geometry_version(key), **self.availability(key)}
                        for key, a in self.anchors.items()],
            "pending": [{**r, **({"display_label": visible[key]} if visible is not None else {}),
                          "geometry_version": self.geometry_version(key), **self.availability(key),
                          "approved": any(p["reconstruction"] == key for p in placements)}
                        for key, r in sorted(self.records.items(), key=lambda item: (item[1]["block"], item[0]))
                        if visible is None or key in visible],
            "placements": placements}

    def geometry(self, key):
        row = self.record(key)
        model = row["model"]
        stamp = tuple((Path(model)/n).stat().st_mtime_ns for n in ("images.bin", "points3D.bin"))
        cache_key = (key, stamp)
        with self.lock:
            if cache_key not in self.cache:
                xyz, colors = read_sparse_points(model)
                stride = max(1, math.ceil(len(xyz)/60000))
                views = read_views(model)
                self.cache[cache_key] = {"points": np.c_[xyz[::stride], colors[::stride]].tolist(),
                    "bounds": np.quantile(xyz, [.005, .995], axis=0).tolist(),
                    "views": [{"id": i, "name": v["name"], "camera_id": v["camera_id"],
                               "center": v["center"].tolist(), "R": v["R"].tolist(),
                               "direction": v["R"].T[:, 2].tolist()} for i, v in views.items()],
                    "sparse_count": len(xyz), "sampled": stride > 1}
                while len(self.cache) > 3:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(cache_key)
            return self.cache[cache_key]

    def thumbnail(self, key, iid):
        from PIL import Image, ImageOps
        views = self.view_rows(key)
        view = next((v for v in views if v["id"] == iid), None)
        if view is None:
            raise InputError("Vista desconocida.")
        root = Path(self.manifest(key)["images"]["root_uri"]).resolve()
        path = (root/view["name"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise InputError("Foto original no disponible localmente.")
        stamp = (str(path), self.file_stamp(path))
        with self.lock:
            if stamp in self.thumbnail_cache:
                self.thumbnail_cache.move_to_end(stamp)
                return self.thumbnail_cache[stamp]
        with self.image_gate:
            with Image.open(path) as image:
                image.draft("RGB", (400, 260))
                image = ImageOps.exif_transpose(image)
                image.thumbnail((400, 260))
                b = io.BytesIO(); image.convert("RGB").save(b, "JPEG", quality=75)
                value = b.getvalue()
        with self.lock:
            self.thumbnail_cache[stamp] = value
            while len(self.thumbnail_cache) > 256 or sum(map(len, self.thumbnail_cache.values())) > 24*1024**2:
                self.thumbnail_cache.popitem(last=False)
        return value

    def sessions(self):
        return sorted([load(p) for p in (self.root/"sessions").glob("*.json")],
                      key=lambda s: s["created_at"], reverse=True)

    def session(self, key):
        p = self.root/"sessions"/(safe_id(key)+".json")
        if not p.is_file():
            raise InputError("Sesión desconocida.")
        return load(p)

    def validate_session(self, payload):
        active = self.catalog.data/"active/manifest.json"
        if self.accepted_manifest_sha and sha_file(active) != self.accepted_manifest_sha:
            raise InputError("El paquete aceptado cambió; reinicia con una revisión de estado nueva.")
        key = payload["reconstruction"]
        if key not in self.records:
            raise InputError("Selecciona una reconstrucción pendiente, no un ancla.")
        row = self.records[key]
        if self.identity(row["model"]) != row["hashes"]:
            raise InputError("La reconstrucción cambió; registra una revisión nueva.")
        matrix = similarity(payload["matrix"]).tolist()
        if payload.get("anchor_revision") != self.anchor_revision:
            raise InputError("La revisión de anclas no coincide.")
        settings = policy(payload.get("policy"))
        edges = payload.get("edges", [])
        if not isinstance(edges, list) or len(edges) > len(self.anchors):
            raise InputError("Lista de anclas inválida.")
        seen = set(); total = 0; roles = {}
        for edge in edges:
            aid = edge["anchor"]
            if aid not in self.anchors or aid in seen:
                raise InputError("Ancla inválida o duplicada.")
            seen.add(aid)
            if self.identity(self.anchors[aid]["model"]) != self.anchors[aid]["hashes"]:
                raise InputError("La geometría de un ancla cambió; no se ejecutará contra otra revisión.")
            if self.anchors[aid].get("reconstruction") == key:
                raise InputError("Una reconstrucción no puede ser su propia ancla.")
            for direction in ("forward", "reverse"):
                sel = edge.get(direction, {"views": [], "pairs": []})
                views, pairs = sel["views"], sel["pairs"]
                if len(views) > 256 or len(pairs) > 6000:
                    raise InputError("Presupuesto de vistas/pares excedido.")
                query, support = (key, aid) if direction == "forward" else (aid, key)
                valid_q = {v["id"] for v in self.view_rows(query)}
                valid_t = {v["id"] for v in self.view_rows(support)}
                selected = set()
                for view in views:
                    iid = view["id"]
                    if isinstance(iid, bool) or not isinstance(iid, int) or iid not in valid_q or iid in selected or view["role"] not in ("fit", "validation"):
                        raise InputError("Vista seleccionada inválida o duplicada.")
                    selected.add(iid)
                    physical = (query, iid)
                    if physical in roles and roles[physical] != view["role"]:
                        raise InputError("Una misma vista no puede ser ajuste y validación entre anclas.")
                    roles[physical] = view["role"]
                pair_ids = set()
                for p in pairs:
                    pair = (p["query"], p["support"])
                    if any(isinstance(v, bool) or not isinstance(v, int) for v in pair) or pair[0] not in selected or pair[1] not in valid_t or pair in pair_ids:
                        raise InputError("Par inválido, duplicado o ajeno a la selección.")
                    pair_ids.add(pair)
                total += len(pairs)
        if total > 10000:
            raise InputError("Máximo 10.000 pares explícitos por sesión.")
        return {"reconstruction": key, "matrix": matrix, "anchor_revision": self.anchor_revision,
                "edges": edges, "policy": settings, "name": str(payload.get("name", "Colocación"))[:150]}

    def save(self, payload):
        body = self.validate_session(payload)
        body.update(id="s-"+uuid.uuid4().hex, created_at=time.time(),
                    input_hashes=self.records[body["reconstruction"]]["hashes"])
        atomic_json(self.root/"sessions"/(body["id"]+".json"), body)
        return body

    def candidates(self, payload):
        session = self.validate_session(payload["session"])
        aid = payload["anchor"]; direction = payload["direction"]
        edge = next((e for e in session["edges"] if e["anchor"] == aid), None)
        if not edge or direction not in ("forward", "reverse"):
            raise InputError("Dirección/ancla inválida.")
        source, target = (session["reconstruction"], aid) if direction == "forward" else (aid, session["reconstruction"])
        sm, tm = (session["matrix"], self.anchors[aid]["matrix"]) if direction == "forward" else (self.anchors[aid]["matrix"], session["matrix"])
        sv = read_views(self.record(source)["model"]); tv = read_views(self.record(target)["model"])
        return {"pairs": propose(sv, tv, [v["id"] for v in edge[direction]["views"]], sm, tm,
            limit=payload.get("limit", 12), radius=float(payload.get("radius", 80)),
            angle=float(payload.get("angle", 110)))}

    def job(self, key):
        p = self.root/"jobs"/safe_id(key)/"status.json"
        if not p.is_file():
            raise InputError("Trabajo desconocido.")
        row = load(p)
        if row["state"] in ("queued", "running") and time.time()-row.get("updated_at", row["created_at"]) > 3:
            active = subprocess.run(["systemctl", "--user", "is-active", row["unit"]],
                                    capture_output=True, text=True).stdout.strip()
            if active not in ("active", "activating"):
                thermal = p.parent/"thermal-stop.json"
                row.update(state="interrupted", error="Worker detenido por límite de recursos o interrupción"+
                           (" térmica" if thermal.exists() else ""))
                atomic_json(p, row)
        return row

    def jobs(self):
        return sorted([self.job(p.parent.name) for p in (self.root/"jobs").glob("*/status.json")],
                      key=lambda r: r["created_at"], reverse=True)

    def start(self, payload):
        session = self.session(payload["session_id"])
        self.validate_session(session)
        mode = payload.get("mode", "sim3")
        if mode not in ("sim3", "ba", "inputs"):
            raise InputError("Operación inválida.")
        if mode != "inputs" and not any(e.get(d, {}).get("pairs") for e in session["edges"] for d in ("forward", "reverse")):
            raise InputError("Selecciona vistas y aprueba pares antes de ejecutar.")
        keys = {session["reconstruction"]} | ({e["anchor"] for e in session["edges"]} if mode != "inputs" else set())
        for k in keys if mode != "inputs" else []:
            available = self.availability(k)
            if not available["matching_ready"]:
                raise InputError(k+": faltan "+", ".join(available["missing"])+". Prepara un snapshot local.")
        with self.lock:
            if any(j["state"] in ("queued", "running") for j in self.jobs()):
                raise InputError("Ya hay un trabajo de alineación activo.")
            key = "j-"+uuid.uuid4().hex
            unit = "barranco-align-"+key
            directory = self.root/"jobs"/key; directory.mkdir()
            manifests = {k: self.manifest(k) for k in keys}
            anchor_models = {k: {"matrix": self.anchors[k]["matrix"], **manifests[k]}
                             for k in keys if k in self.anchors}
            request = {"id": key, "session": session, "mode": mode, "anchors": anchor_models,
                       "incoming": manifests[session["reconstruction"]],
                       "anchor_sparse_hashes": {k: self.anchors[k]["hashes"] for k in anchor_models},
                       "engine": digest({str(p.relative_to(REPO)): sha_file(p)
                                        for p in (REPO/"src").rglob("*.py")}),
                       "accepted_manifest": str(self.catalog.data/"active/manifest.json"),
                       "accepted_manifest_sha": self.accepted_manifest_sha,
                       "runtime": {"python": sys.version, "colmap_sha256": sha_file(PYTHON.parent/"colmap")},
                       "created_at": time.time()}
            request["incoming_record"] = self.records[session["reconstruction"]]
            request["input_destination"] = str(self.catalog.data/"alignment-inputs/manual"/key)
            for name in ("blockalign", "alignexp"):
                shutil.copytree(REPO/"src"/name, directory/"src"/name,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            shutil.copy2(ROOT/"alignment_worker.py", directory/"worker.py")
            shutil.copy2(ROOT/"source_fetch.py", directory/"source_fetch.py")
            atomic_json(directory/"request.json", request)
            status = {"id": key, "unit": unit, "state": "queued", "stage": "admission",
                      "mode": mode, "session_id": session["id"], "created_at": request["created_at"]}
            atomic_json(directory/"status.json", status)
            command = ["systemd-run", "--user", "--unit="+unit, "--collect",
                "-p", "MemoryMax=40G", "-p", "MemorySwapMax=0", "-p", "CPUQuota=400%",
                "-p", "TasksMax=128", "-p", "RuntimeMaxSec=14400", "-p", "KillMode=control-group",
                str(PYTHON), "-B", str(directory/"worker.py"), str(directory)]
            p = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if p.returncode:
                status.update(state="failed", error=p.stderr)
                atomic_json(directory/"status.json", status)
                raise InputError("No se pudo iniciar el worker: "+p.stderr)
            return status

    def cancel(self, key):
        with self.lock:
            job = self.job(key)
            if job["state"] not in ("queued", "running"):
                return job
            atomic_json(self.root/"jobs"/key/"cancel.json", {"at": time.time()})
            subprocess.run(["systemctl", "--user", "stop", job["unit"]], check=False, timeout=30,
                           capture_output=True)
            job = self.job(key)
            if job["state"] in ("queued", "running"):
                job.update(state="cancelled", error="Cancelado explícitamente")
                atomic_json(self.root/"jobs"/key/"status.json", job)
            return job

    def result(self, key):
        job = self.job(key)
        p = self.root/"jobs"/key/"result.json"
        if job["state"] != "completed" or not p.is_file():
            raise InputError("No hay resultado publicado.")
        return load(p)

    def approve(self, payload):
        session = self.session(payload["session_id"])
        self.validate_session(session)
        job_id = payload.get("job_id")
        result = self.result(job_id) if job_id else None
        if result and self.job(job_id)["session_id"] != session["id"]:
            raise InputError("El trabajo pertenece a otra sesión.")
        if result and not result["validated"]:
            raise InputError("La validación falló; no se puede aprobar como alineación calculada.")
        if not result and payload.get("confirm_manual") is not True:
            raise InputError("Confirma explícitamente la colocación sin validación.")
        reconstruction = session["reconstruction"]
        matrix = result["matrix"] if result else session["matrix"]
        if result and result.get("derived_model"):
            if model_identity(result["derived_model"]) != result["derived_hashes"]:
                raise InputError("La geometría derivada cambió desde su validación.")
            row = self.records[reconstruction]
            inputs = {**self.manifest(reconstruction), "block_id": row["block"],
                      "sparse": {"model_uri": result["derived_model"]}}
            manifest_path = Path(result["derived_model"]).parent/"derived-inputs.json"
            atomic_json(manifest_path, inputs)
            derived = self.register(result["derived_model"], row["block"], row["label"]+" · BA",
                                    row.get("node"), row.get("native_source_root"), str(manifest_path))
            reconstruction = derived["id"]
        placement = {"id": "p-"+uuid.uuid4().hex, "session_id": session["id"], "job_id": job_id,
            "reconstruction": reconstruction, "matrix": matrix, "created_at": time.time(),
            "validation": "matched" if result else "manual_unvalidated",
            "anchor_revision": self.anchor_revision, "geometry_changed": bool(result and result.get("derived_model")),
            "dense_requires_regeneration": bool(result and result.get("derived_model"))}
        with self.lock, self.catalog.lock:
            atomic_json(self.root/"placements"/(placement["id"]+".json"), placement)
            self.install_placement(placement)
        return placement

    def placement_rows(self):
        return sorted([load(p) for p in (self.root/"placements").glob("*.json")],
                      key=lambda p: p["created_at"])

    def restore_placements(self):
        for p in self.placement_rows():
            self.install_placement(p)

    def install_placement(self, placement):
        r = self.records[placement["reconstruction"]]
        # Revision-specific ROI key: never overwrite a previous accepted placement.
        key = placement["id"]
        self.catalog.records[key] = {"block": key, "node": r.get("node"), "run": Path(r["model"]),
            "model": Path(r["model"]), "entry": {"block": r["id"], "categorical_rgb": [255, 181, 82]},
            "transform": np.array(placement["matrix"]), "origin": self.catalog.origin,
            "sparse_count": r["points"], "dense_count": 0, "batch_count": 0,
            "native_source_root": r.get("native_source_root"), "placement": placement["validation"],
            "placement_details": {**placement, "source_block": r["block"], "source_revision": r["id"]},
            "title": r["block"]+" · "+r["label"],
            "source_block": r["block"]}
        self.catalog.transforms[key] = np.array(placement["matrix"])
        self.catalog._overview = None
        self.anchors[key] = {"id": key, "block": r["block"], "matrix": placement["matrix"],
            "hashes": r["hashes"],
            "model": r["model"], "node": r.get("node"), "native_source_root": r.get("native_source_root"),
            "input_manifest": r.get("manifest"), "reconstruction": r["id"],
            "accepted_derived": True, "validation": placement["validation"]}
