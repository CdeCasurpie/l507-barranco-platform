"""Resource-bounded subprocess for manual alignment; never operates in HTTP threads."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import traceback
import hashlib

os.environ.update(OMP_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4", MKL_NUM_THREADS="4")
sys.path.insert(0, str(Path(sys.argv[1])/"src"))
os.environ["PATH"] = "/data/barranco/runtime/alignment313/bin:"+os.environ["PATH"]
from blockalign.manual import measure, normalize, solve, constrained_ba, residuals, ManualError
from blockalign.storage import write as atomic_json, read as load
from blockalign.manual import file_hash as sha_file


def model_identity(model):
    return {n: sha_file(Path(model)/n) for n in ("cameras.bin", "images.bin", "points3D.bin")}


def main(directory):
    directory = Path(directory)
    request = load(directory/"request.json")
    status = load(directory/"status.json")
    session = request["session"]
    def update(**values):
        status.update(values, updated_at=time.time())
        atomic_json(directory/"status.json", status)
    def verify():
        if (directory/"cancel.json").exists():
            raise ManualError("Cancellation requested")
        if request.get("accepted_manifest_sha") and sha_file(request["accepted_manifest"]) != request["accepted_manifest_sha"]:
            raise ManualError("Accepted anchor snapshot changed")
        if model_identity(request["incoming"]["sparse"]["model_uri"]) != session["input_hashes"]:
            raise ManualError("Incoming sparse changed")
        for aid, anchor in request["anchors"].items():
            if model_identity(anchor["sparse"]["model_uri"]) != request["anchor_sparse_hashes"][aid]:
                raise ManualError("Anchor sparse changed")
    # Native children inherit systemd's cgroup; CPU, memory and cancellation are
    # enforced by the OS. Thermal monitoring stops only this service.
    stop = threading.Event()
    def thermal():
        import subprocess
        hot = None
        while not stop.wait(5):
            try:
                data = json.loads(subprocess.check_output(["sensors", "-j"], timeout=5))
                values = [float(v) for chip in data.values() for item in chip.values() if isinstance(item, dict)
                          for k, v in item.items() if k.endswith("_input") and k.startswith("temp")]
                temp = max(values) if values else 0
                hot = (hot or time.monotonic()) if temp >= 90 else None
                if temp >= 95 or (hot and time.monotonic()-hot >= 30):
                    atomic_json(directory/"thermal-stop.json", {"temperature": temp})
                    subprocess.run(["systemctl", "--user", "stop", "--no-block", status["unit"]], timeout=10)
                    return
            except (OSError, ValueError, subprocess.SubprocessError):
                pass
    monitor = threading.Thread(target=thermal, daemon=True)
    try:
        import pycolmap
        if pycolmap.__version__ != "3.13.0":
            raise ManualError("Requires PyCOLMAP/COLMAP 3.13.0")
        if sha_file("/data/barranco/runtime/alignment313/bin/colmap") != request["runtime"]["colmap_sha256"]:
            raise ManualError("Native COLMAP runtime changed after submission")
        group = Path("/sys/fs/cgroup")/Path("/proc/self/cgroup").read_text().strip().split(":", 2)[2].lstrip("/")
        memory = (group/"memory.max").read_text().strip()
        quota, period = (group/"cpu.max").read_text().split()
        if (memory == "max" or int(memory) > 40*1024**3 or quota == "max"
                or int(quota)/int(period) > 4 or (group/"memory.swap.max").read_text().strip() != "0"):
            raise ManualError("Worker requires real CPU/memory/swap cgroup limits")
        verify(); monitor.start()
        if request["mode"] == "inputs":
            import subprocess
            with (directory/"input-transfer.log").open("w") as log:
                subprocess.run(["/usr/bin/python3", "-B", str(directory/"source_fetch.py"), str(directory)],
                               stdout=log, stderr=subprocess.STDOUT, check=True, timeout=10800)
            manifest = load(directory/"input-result.json")["manifest"]
            verify()
            atomic_json(directory/"result.json", {"inputs_manifest": manifest,
                "reconstruction": session["reconstruction"], "validated": False})
            update(state="completed", stage="inputs_ready", finished_at=time.time())
            return
        outcomes = []
        for n, edge in enumerate(session["edges"]):
            aid = edge["anchor"]; anchor = request["anchors"][aid]
            for direction in ("forward", "reverse"):
                selection = edge.get(direction, {"views": [], "pairs": []})
                if not selection["views"]:
                    continue
                update(state="running", stage=f"{aid}/{direction}", edge=n+1, edges=len(session["edges"]))
                source, target = (request["incoming"], anchor) if direction == "forward" else (anchor, request["incoming"])
                rows = measure(source, target, selection, directory/(aid+"-"+direction), session["policy"],
                               keep_cross=request["mode"] == "ba")
                outcomes.extend(normalize(r, anchor["matrix"], direction, aid) for r in rows)
                atomic_json(directory/"localizations.json", outcomes)
                verify()
        update(stage="joint_sim3")
        result = solve(outcomes, session["matrix"], session["policy"])
        result["localizations"] = [{k: v for k, v in row.items()
                                   if k not in ("cross_observations", "observations")} for row in outcomes]
        if request["mode"] == "ba":
            if not result["validated"]:
                raise ManualError("BA requires a validated initial Sim(3)")
            update(stage="constrained_ba")
            result["ba"] = constrained_ba(request["incoming"], result["matrix"], outcomes,
                                         request["anchors"], directory/"derived-model")
            result["matrix"] = result["ba"]["world_from_model"]
            result["derived_model"] = str(directory/"derived-model")
            result["derived_hashes"] = model_identity(result["derived_model"])
            update(stage="ba_reserved_localization")
            derived = {**request["incoming"], "sparse": {"model_uri": result["derived_model"]}}
            reserved = []
            for edge in session["edges"]:
                aid = edge["anchor"]; anchor = request["anchors"][aid]
                for direction in ("forward", "reverse"):
                    selected = edge.get(direction, {"views": [], "pairs": []})
                    views = [v for v in selected["views"] if v["role"] == "validation"]
                    if not views:
                        continue
                    ids = {v["id"] for v in views}
                    selection = {"views": views, "pairs": [p for p in selected["pairs"] if p["query"] in ids]}
                    source, target = (derived, anchor) if direction == "forward" else (anchor, derived)
                    rows = measure(source, target, selection, directory/(aid+"-"+direction+"-ba-validation"), session["policy"])
                    reserved.extend(normalize(r, anchor["matrix"], direction, aid) for r in rows)
            if not reserved or any(not r["registered"] for r in reserved):
                raise ManualError("BA failed independent reserved-view relocalization")
            import numpy as np
            c, a = residuals(np.eye(4), reserved, session["policy"])
            if max(c) > session["policy"]["max_center_error_m"] or max(a) > session["policy"]["max_rotation_error_deg"]:
                raise ManualError("BA failed reserved-view center/orientation validation")
            result["ba"]["reserved_relocalized"] = len(reserved)
        verify()
        atomic_json(directory/"result.json", result)
        update(state="completed", stage="review", validated=result["validated"], finished_at=time.time())
    except BaseException as exc:
        update(state="failed", error=str(exc), finished_at=time.time())
        (directory/"error.log").write_text(traceback.format_exc())
        raise
    finally:
        stop.set()


if __name__ == "__main__":
    main(sys.argv[1])
