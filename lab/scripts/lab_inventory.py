#!/usr/bin/env python3
"""Inventario del lab UTEC L507.

Descubre PCs con SSH en la subred cableada 10.100.41/25, entra con
utec_alumno por password y reporta: tag del TXT, IP, MAC, driver GPU,
ultimo arranque y estado del disco grande ext4 (~488 GiB).
Lectura pura: no modifica nada en las hijas.
"""
import base64
import concurrent.futures
import ipaddress
import json
import os
import re
import socket
import subprocess
import sys

try:
    import pexpect
except ImportError:
    sys.exit("Falta pexpect: pip install pexpect")

from lab_config import DEFAULT_SSH_PASSWORD

PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
SSH_USER = os.environ.get("LAB_SSH_USER", "utec_alumno")

CR = "\033[31m"
CG = "\033[32m"
CYL = "\033[33m"
CC = "\033[36m"
CM = "\033[35m"
GR = "\033[90m"
B = "\033[1m"
R = "\033[0m"


def run(args, timeout=15):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
        return p.stdout.strip()
    except Exception:
        return ""


def discover_subnet():
    data = run(["ip", "-j", "-4", "addr"])
    try:
        parsed = json.loads(data)
    except Exception:
        return ipaddress.ip_network("192.0.2.0/25"), "?", ""
    for itf in parsed:
        for ad in itf.get("addr_info", []):
            if ad["local"].startswith("10.100.41."):
                try:
                    net = ipaddress.ip_interface(f'{ad["local"]}/{ad["prefixlen"]}').network
                    return net, itf["ifname"], ad["local"]
                except ValueError:
                    pass
    return ipaddress.ip_network("192.0.2.0/25"), "?", ""


def scan_port22(net, timeout=0.7):
    def probe(ip):
        s = socket.socket()
        s.settimeout(timeout)
        try:
            return str(ip) if s.connect_ex((str(ip), 22)) == 0 else None
        finally:
            s.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        found = [r for r in pool.map(probe, list(net.hosts())) if r]
    return sorted(found, key=lambda x: int(x.split(".")[-1]))


REMOTE_CODE = r"""
import json, subprocess, os, re
def run(args, t=15):
    try:
        p = subprocess.run(args, text=True, capture_output=True, timeout=t)
        return {"out": p.stdout.strip(), "rc": p.returncode}
    except Exception as e:
        return {"out": "ERR:" + str(e), "rc": 1}

res = {}
res["hostname"] = run(["uname", "-n"])["out"]
res["kernel"] = run(["uname", "-r"])["out"]

home = os.path.expanduser("~")
res["tags"] = sorted(set(re.findall(r"L507[_ -]?\d+|L507_MAESTRA", " ".join(os.listdir(home)), re.I)))

g = run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
if g["rc"] == 0 and "," in g["out"]:
    name, drv = [x.strip() for x in g["out"].splitlines()[0].split(",", 1)]
    res["gpu"] = {"state": "ok", "name": name, "driver": drv}
else:
    mod = run(["cat", "/proc/driver/nvidia/version"])["out"]
    m = re.search(r"NVRM.*\s(\d+\.\d+(?:\.\d+)?)", mod) if mod.startswith("NVRM") else None
    if m:
        res["gpu"] = {"state": "lib", "driver": m.group(1), "name": "modulo cargado sin nvidia-smi"}
    else:
        res["gpu"] = {"state": "none", "driver": "", "name": "driver no cargado"}

res["mac"] = "?"
for line in run(["ip", "-o", "link"])["out"].splitlines():
    m = re.search(r"link/ether\s+(f4:f1:9e:[0-9a-f:]+)", line)
    if m and line.split(":")[1].strip() != "lo":
        res["mac"] = m.group(1)
        res["iface"] = line.split(":")[1].strip()
        break

res["boot"] = run(["uptime", "-s"])["out"]

res["disk"] = None
try:
    raw = run(["lsblk", "-J", "-b", "-o", "NAME,SIZE,FSTYPE,MOUNTPOINT,UUID"])["out"]
    blocks = json.loads(raw)["blockdevices"]
    flat = []
    def walk(bds):
        for b in bds:
            flat.append(b)
            walk(b.get("children") or [])
    walk(blocks)
    for b in flat:
        try:
            if b.get("size") and int(b["size"]) >= 400 * 1024**3 and b.get("fstype") == "ext4":
                res["disk"] = {"name": b["name"], "uuid": b.get("uuid") or "?", "mp": b.get("mountpoint")}
                break
        except Exception:
            pass
except Exception as e:
    res["lsblk_err"] = str(e)

if res["disk"] and res["disk"].get("mp"):
    d = run(["df", "-B1", "--output=size,used,avail", res["disk"]["mp"]])["out"].splitlines()
    if len(d) >= 2 and d[1].split()[0].isdigit():
        s, u, a = [int(x) for x in d[1].split()]
        res["disk"]["total"], res["disk"]["used"], res["disk"]["avail"] = s, u, a

print(json.dumps(res))
"""


def ssh_collect(ip, timeout=50):
    args = [
        "-o", "ConnectTimeout=6",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password",
        "-o", "PubkeyAuthentication=no",
        f"{SSH_USER}@{ip}",
        "echo " + base64.b64encode(REMOTE_CODE.encode()).decode() + " | base64 -d | python3",
    ]
    try:
        child = pexpect.spawn("ssh", args, encoding="utf-8", timeout=60, echo=False)
        ev = child.expect(["[Pp]assword:", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
        if ev == 0:
            child.sendline(PASSWORD)
            child.expect(pexpect.EOF, timeout=timeout)
        out = (child.before or "").replace("\r", "")
        child.close()
        start, end = out.find("{"), out.rfind("}")
        if child.exitstatus == 0 and start >= 0 and end > start:
            return {"ip": ip, "ssh": "ok", **json.loads(out[start : end + 1])}
        return {"ip": ip, "ssh": "fail", "detail": (out.strip() or "sin respuesta")[-100:]}
    except Exception as e:
        return {"ip": ip, "ssh": "fail", "detail": str(e)[-100:]}


def local_master():
    try:
        p = subprocess.run(["python3", "-c", REMOTE_CODE], text=True, capture_output=True, timeout=30)
        return {"ssh": "local", **json.loads(p.stdout.strip().splitlines()[-1])}
    except Exception:
        return {"ssh": "local"}


def cell(text, width, c=""):
    return c + str(text)[:width].ljust(width) + R


def gpu_text(g):
    if not g:
        return "?" .ljust(36), GR
    st = g.get("state")
    if st == "ok":
        return f"{g.get('name','?')} ({g.get('driver','?')})"[:43].ljust(36), CG
    if st == "lib":
        return f"sin nvidia-smi (drv {g.get('driver','?')})"[:43].ljust(36), CYL
    return "driver no cargado".ljust(36), CR


def disk_text(d):
    if not d:
        return "NO DETECTADA".ljust(30), CYL
    mp = d.get("mp")
    if not mp:
        return "ext4 SIN MONTAR".ljust(30), CYL
    if d.get("total"):
        txt = f"MONTADA {mp} libre {d['avail'] / 1024**3:.0f}G/{d['total'] / 1024**3:.0f}G"
    else:
        txt = f"MONTADA {mp}"
    return txt[:30].ljust(30), CG


def main():
    net, iface, own = discover_subnet()
    print(f"{GR}[*] Subred {net} (iface {iface}){R}", file=sys.stderr)
    hosts = [h for h in scan_port22(net) if h != own]
    print(f"{GR}[*] {len(hosts)} hijas con SSH abierto + maestra (local){R}", file=sys.stderr)

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for rep in pool.map(ssh_collect, hosts):
            results.append(rep)
            mark = CG + "ok" + R if rep["ssh"] == "ok" else CR + "FAIL" + R
            print(f"{GR}      {rep['ip']} {mark}{R}", file=sys.stderr)

    rows = [r for r in results if r["ssh"] == "ok"]
    fails = [r for r in results if r["ssh"] != "ok"]
    rows.append({"ip": own or "?", **local_master()})

    def tagrow(r):
        tags = r.get("tags") or []
        return tags[0].upper() if tags else "SIN TXT"

    def key(r):
        m = re.search(r"(\d+)$", tagrow(r))
        return (0 if r["ssh"] == "local" else 1, int(m.group(1)) if m else 999)

    rows.sort(key=key)

    headers = [("TAG", 13), ("IP", 15), ("MAC", 20), ("GPU/DRIVER", 44), ("DISCO 488G", 31), ("ARRANQUE", 21)]
    print()
    print("".join(cell(t, w, B + CC) for t, w in headers))
    print(GR + "-" * 144 + R)
    for r in rows:
        tc = CG if r.get("tags") else CYL
        gpu, gc = gpu_text(r.get("gpu"))
        dsk, dc = disk_text(r.get("disk"))
        print(
            cell(tagrow(r), 13, tc)
            + cell(r["ip"] + ("*" if r["ssh"] == "local" else ""), 15, CM if r["ssh"] == "local" else "")
            + cell(r.get("mac", "?"), 20, GR)
            + cell(gpu, 44, gc)
            + cell(dsk, 31, dc)
            + cell(r.get("boot", "?"), 21, GR)
        )
    for r in fails:
        print(cell("SSH?", 13, CR) + cell(r["ip"], 15, CR) + cell("-", 20) + cell("login fallo: " + r.get("detail", "")[:25], 85, CYL))
    print(GR + "-" * 144 + R)

    ok = sum(1 for r in rows if (r.get("gpu") or {}).get("state") == "ok")
    tags = sum(1 for r in rows if r.get("tags"))
    mont = sum(1 for r in rows if (r.get("disk") or {}).get("mp"))
    print(
        f"Total filas {len(rows)} | "
        + f"SSH ok {len(rows)} / fallo {len(fails)} | "
        + f"GPU activa {ok} | "
        + f"con TAG {tags} | "
        + f"disco 488G montado {mont}"
    )
    print(f"{GR}(*) = maestra, evaluada localmente en esta PC{R}")
    print()


if __name__ == "__main__":
    main()
