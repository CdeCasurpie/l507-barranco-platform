"""Explicit, read-only SSH collection of original photos/features for one revision.

Never runs reconstruction, modifies remote files, changes power or stops jobs.
Credentials and host keys are obtained by the existing trusted lab transport.
"""
import json
from pathlib import Path
import shlex
import shutil
import sys
import time
import hashlib


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(4194304), b""):
            h.update(chunk)
    return h.hexdigest()

sys.path.insert(0, "/home/exitoso/lab-deploy/tools")


def collect(record, destination, progress):
    import review_experiments as transport
    import pexpect
    project = Path("/home/exitoso/lab-deploy")
    assignments = []
    for p in (project/".state/campaigns").glob("*/assignments.json"):
        assignments.extend(json.loads(p.read_text()).get("assignments", []))
    native = record.get("native_source_root")
    candidates = [a for a in assignments if a["node_tag"] == record.get("node")
                  and native and Path(native).is_relative_to(Path(a["work_root"]))]
    if not candidates:
        raise ValueError("No trusted assignment for this node/source; attach a local snapshot instead")
    assignment = candidates[0]
    component = Path(record["model"]).name
    # All remote actions below are reads. A nonempty WAL is refused, not altered.
    code = r'''
import pathlib,hashlib,json,struct
a=ASSIGNMENT
assert (pathlib.Path.home()/(a['node_tag']+'.txt')).is_file()
assert a['mac'] in [p.read_text().strip() for p in pathlib.Path('/sys/class/net').glob('*/address')]
root=pathlib.Path(NATIVE)
assert root.is_relative_to(pathlib.Path(a['work_root']))
model=root/'colmap/sparse'/COMPONENT
paths=[model/n for n in ('cameras.bin','images.bin','points3D.bin')]
db=root/'colmap/database.snapshot.db'
if not db.is_file():db=root/'colmap/database.db'
wal=pathlib.Path(str(db)+'-wal')
assert not (wal.exists() and wal.stat().st_size),'Active WAL: export a consistent database first'
paths.append(db)
with (model/'images.bin').open('rb') as f:
 count=struct.unpack('<Q',f.read(8))[0]
 for _ in range(count):
  f.read(64);name=bytearray()
  while True:
   b=f.read(1)
   assert b,'Invalid image record'
   if b==b'\0':break
   name.extend(b)
  name=name.decode();p=pathlib.Path(name)
  assert not p.is_absolute() and '..' not in p.parts
  paths.append(root/'frames'/p)
  n=struct.unpack('<Q',f.read(8))[0];f.seek(24*n,1)
files={}
for p in paths:
 assert p.is_file(),str(p)
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(4194304),b''):h.update(chunk)
 files[str(p.relative_to(root))]={'bytes':p.stat().st_size,'sha256':h.hexdigest()}
print('REVIEW_REPLY='+json.dumps({'files':files,'database':str(db.relative_to(root)),'root':str(root)}))
'''.replace("ASSIGNMENT", repr(assignment)).replace("NATIVE", repr(native)).replace("COMPONENT", repr(component))
    progress(stage="input_inventory")
    snapshot = transport.remote(assignment, code, timeout=600)
    expected = sum(v["bytes"] for v in snapshot["files"].values())
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(destination).free < expected+50*1024**3:
        raise ValueError("Insufficient disk space while preserving 50 GiB")
    # Before transferring potentially large originals, verify the remote sparse is
    # exactly the locally reviewed revision (not a newer corrected component).
    for name, sha in record["hashes"].items():
        relative = "colmap/sparse/"+component+"/"+name
        if snapshot["files"][relative]["sha256"] != sha:
            raise ValueError("Remote sparse differs from the reviewed revision")
    filelist = destination/"files.txt"
    filelist.write_text("\n".join(snapshot["files"])+"\n")
    site = json.loads((project/"config/site.json").read_text())
    password, _ = transport.credentials(site)
    ssh = shlex.join(["ssh", "-o", "StrictHostKeyChecking=yes",
                     "-o", "UserKnownHostsFile="+str(transport.STATE/"known_hosts")])
    progress(stage="input_transfer", bytes_total=expected)
    child = pexpect.spawn("rsync", ["-a", "--partial", "--files-from="+str(filelist), "-e", ssh,
        site["ssh_user"]+"@"+assignment["ip"]+":"+native+"/", str(destination)+"/"],
        encoding="utf-8", echo=False, timeout=1800)
    try:
        attempts = 0
        while True:
            event = child.expect(["[Pp]assword:", pexpect.EOF, pexpect.TIMEOUT])
            if event == 0:
                attempts += 1
                if attempts > 2:
                    raise ValueError("SSH authentication rejected")
                child.sendline(password)
            elif event == 1:
                break
            else:
                raise ValueError("Input transfer timed out")
        child.close()
        if child.exitstatus:
            raise ValueError("Input transfer failed")
    finally:
        if child.isalive():
            child.close(force=True)
    progress(stage="input_verification")
    for name, expected_file in snapshot["files"].items():
        p = destination/name
        if p.stat().st_size != expected_file["bytes"] or file_hash(p) != expected_file["sha256"]:
            raise ValueError("Transferred input checksum mismatch: "+name)
    manifest = {"schema_version": "manual-inputs-1", "block_id": record["block"],
        "sparse": {"model_uri": str(destination/"colmap/sparse"/component)},
        "features": {"database_uri": str(destination/snapshot["database"]), "family": "sift"},
        "images": {"root_uri": str(destination/"frames")},
        "provenance": {"source_run": native, "node": record["node"], "collected_at": time.time(),
                       "remote_actions": "read_only", "files": snapshot["files"]}}
    path = destination/"block.json"
    path.write_text(json.dumps(manifest, indent=2))
    return str(path)


if __name__ == "__main__":
    directory = Path(sys.argv[1])
    request = json.loads((directory/"request.json").read_text())
    def progress(**values):
        status = json.loads((directory/"status.json").read_text())
        status.update(values, state="running", updated_at=time.time())
        temporary = directory/"input-status.tmp"
        temporary.write_text(json.dumps(status))
        temporary.replace(directory/"status.json")
    manifest = collect(request["incoming_record"], request["input_destination"], progress)
    (directory/"input-result.json").write_text(json.dumps({"manifest": manifest}))
