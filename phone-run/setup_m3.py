#!/usr/bin/env python3
"""setup_m3.py (maestra): re-corre 006/010/011 con máscaras SOLO de personas, postes y cables.
Experimento nuevo en carpeta aparte (no toca barranco-2026-11-12 / v1)."""
import json, subprocess, sys, os
H = os.path.expanduser("~/mesh-run"); W = os.path.expanduser("~/phone-run")
CAMP = "/data/photogrammetry/campaigns/barranco-2026-11-12-m3"
INC = "/data/photogrammetry/incoming/barranco-2026-11-12"
EXP = "barranco_phone_1080p_2fps_m3_v1"
JOBS = [("006", "192.0.2.55", "L507_003"), ("010", "192.0.2.54", "L507_002"), ("011", "192.0.2.64", "L507_006")]
def hrun(ip, cmd):
    return subprocess.run(["python3", f"{H}/hrun.py", ip, cmd], capture_output=True, text=True).stdout.strip()
def hput(ip, dst, *files):
    subprocess.run(["python3", f"{H}/hput.py", ip, dst, *files], check=True)
base_cfg = json.load(open(f"{W}/config-002.json")); base_spec = json.load(open(f"{W}/recon-002.json"))
only = sys.argv[1:]
for blk, ip, tag in JOBS:
    if only and blk not in only: continue
    root = f"{CAMP}/cuadra-{blk}"
    cfg = json.loads(json.dumps(base_cfg))
    cfg["experiment"] = {"name": EXP, "notes": "Celular 1080p 2 fps; máscaras SOLO personas, postes y cables (sin cielo ni vehículos)"}
    cfg["paths"] = {"raw_root": f"{root}/datasets/raw", "output_root": f"{root}/outputs"}
    cfg["telemetry"] = {"enabled": False}
    m = cfg["masking"]
    m["classes"] = ["person", "rider", "pole"]
    m["backends"]["sam3"]["prompts"] = ["person", "utility pole", "power line"]
    m["backends"]["sam3"]["tile_prompts"] = ["power line", "utility pole"]
    spec = json.loads(json.dumps(base_spec))
    spec.update(campaign_id="barranco-2026-11-12-m3", node_tag=tag, block_id=blk, full_experiment=EXP)
    for k in ("worker_sha256", "post_sha256", "recovery"): spec.pop(k, None)
    mac = hrun(ip, "cat /sys/class/net/enp128s31f6/address").splitlines()[-1].strip()
    assign = {"node_tag": tag, "block_id": blk, "mac": mac, "files": [], "source": "phone"}
    d = f"{W}/m3/{blk}"; os.makedirs(d, exist_ok=True)
    json.dump(cfg, open(f"{d}/config-full.json", "w"), indent=2)
    json.dump(spec, open(f"{d}/reconstruction.json", "w"), indent=2)
    json.dump(assign, open(f"{d}/assignment.json", "w"), indent=2)
    r = hrun(ip, f"set -e; mkdir -p {root}/datasets/raw/cuadra-{blk}/phone {root}/outputs {root}/scratch/tmp {root}/scratch/cache {root}/scratch/hf /data/photogrammetry/.lab-deploy; "
                 f"ln -f {INC}/cuadra-{blk}/*.mp4 {root}/datasets/raw/cuadra-{blk}/phone/; ls {root}/datasets/raw/cuadra-{blk}/phone")
    hput(ip, f"{root}/", f"{d}/config-full.json", f"{d}/reconstruction.json", f"{d}/assignment.json",
         f"{W}/phone_worker.py", f"{W}/reconstruction_worker.py", f"{W}/dense_batches.py", f"{W}/cert/campaign_post.py")
    r2 = hrun(ip, f"cd {root}; S(){{ echo Utec@2026 | sudo -S -p '' \"$@\"; }}; "
                  f"sha256sum reconstruction_worker.py dense_batches.py campaign_post.py | cut -c1-12 | tr '\\n' ' '; "
                  f"prev=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader,nounits | cut -d. -f1); "
                  f"[ -f power-limit.json ] || echo \"{{\\\"previous_w\\\":$prev,\\\"applied_w\\\":100}}\" > power-limit.json; S nvidia-smi -pl 100 >/dev/null; "
                  f"echo pl=$(nvidia-smi --query-gpu=power.limit --format=csv,noheader); "
                  f"systemctl is-active -q docker || S systemctl start containerd docker; "
                  f"pgrep -f '^python3 -B /[^ ]*/phone_worker[.]py {root}' >/dev/null && echo YA-CORRIENDO || "
                  f"(setsid nohup python3 -B {root}/phone_worker.py {root} > {root}/worker.log 2>&1 < /dev/null & sleep 25; "
                  f"python3 -c \"import json;d=json.load(open('{root}/reconstruction-full-status.json'));print(d.get('state'),d.get('stage'),d.get('experiment'),d.get('error',''))\" 2>&1; tail -2 {root}/worker.log)")
    print(f"== cuadra-{blk} {tag} {ip}: video={r.splitlines()[-1] if r else '?'} | {r2}", flush=True)
