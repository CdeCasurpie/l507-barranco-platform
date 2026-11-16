#!/usr/bin/env python3
"""make turn-off / turn-off-all: apaga PCs del lab L507 via SSH.

make turn-off NUM=019 -> apaga esa PC via SSH (sudo poweroff)
make turn-off-all     -> apaga TODAS las hijas que acepten SSH
La maestra jamas se apaga ni recibe ordenes.
"""
import concurrent.futures
import ipaddress
import json
import os
import socket
import subprocess
import sys
import time

CY = "\033[36m"
CG = "\033[32m"
CYL = "\033[33m"
CR = "\033[31m"
CP = "\033[35m"
GR = "\033[90m"
B = "\033[1m"
R = "\033[0m"

SUBNET = ipaddress.ip_network("192.0.2.0/25")
SSH_USER = os.environ.get("LAB_SSH_USER", "utec_alumno")
from lab_config import DEFAULT_SSH_PASSWORD

SSH_PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
SUDO_PASSWORD = os.environ.get("LAB_SUDO_PASSWORD", SSH_PASSWORD)
CACHE_PATH = os.environ.get("LAB_MONITOR_CACHE", os.path.expanduser("~/.lab_monitor_cache.json"))
MASTER_IP = None
REMOTE_OFF = "printf %s {sudo_b64} | base64 -d | sudo -S -p '' -k systemctl poweroff"


def masters_ip():
    global MASTER_IP
    if MASTER_IP is None:
        MASTER_IP = ""
        try:
            data = subprocess.run(["ip", "-j", "-4", "addr"], capture_output=True, text=True, timeout=10).stdout
            for itf in json.loads(data):
                for ad in itf.get("addr_info", []):
                    if ad["local"].startswith("10.100.41."):
                        MASTER_IP = ad["local"]
        except Exception:
            pass
    return MASTER_IP


def load_json(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def norm_num(n):
    m = str(n).strip().upper().replace(" ", "").replace("L507_", "").lstrip("L")
    return int(m) if m.isdigit() else None


def port22(ip, timeout=0.4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, 22)) == 0
    except Exception:
        return False
    finally:
        s.close()


def ssh_run(ip, timeout=45):
    import base64
    import pexpect
    sudo_b64 = base64.b64encode(SUDO_PASSWORD.encode()).decode()
    remote = REMOTE_OFF.format(sudo_b64=sudo_b64)
    child = pexpect.spawn("ssh", ["-o", "ConnectTimeout=6", "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
        "-o", "NumberOfPasswordPrompts=1", "-o", "PreferredAuthentications=password",
        "-o", "PubkeyAuthentication=no", "%s@%s" % (SSH_USER, ip), remote],
        encoding="utf-8", timeout=timeout, echo=False)
    ev = child.expect(["[Pp]assword:", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
    if ev == 0:
        child.sendline(SSH_PASSWORD)
        child.expect(pexpect.EOF, timeout=timeout)
    out = (child.before or "").replace("\r", "")
    child.close()
    return child.exitstatus, out.strip()


def discover_ssh_hosts():
    hosts = [str(x) for x in SUBNET.hosts() if str(x) != masters_ip()]
    up = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as ex:
        for ip, ok in zip(list(hosts), ex.map(lambda h: port22(h), list(hosts))):
            if ok:
                up.append(ip)
    return up


def wait_down(ip, timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not port22(ip):
            return int(time.time() - t0)
        time.sleep(4)
    return None


def shutdown(ip):
    if ip == masters_ip():
        return ip, "MAESTRA", None
    if not port22(ip):
        return ip, "YA_APAGADA", None
    code, out = ssh_run(ip)
    if code != 0:
        return ip, "FALLO_SSH", (code, out[-60:])
    dt = wait_down(ip, 120)
    if dt is None:
        return ip, "SIGUE_PRENDIDA", None
    return ip, "APAGADA", dt


def main():
    args = [a for a in sys.argv[1:] if a]
    all_mode = "--all" in args
    nn = [a for a in args if a != "--all"]
    cache = load_json(CACHE_PATH, {})
    ips = {t: v.get("ip") for t, v in cache.items() if isinstance(v, dict) and v.get("ip")}

    print(f"\n{B}{CP}APAGADO REMOTO LAB L507{R}\n")
    if all_mode:
        hosts = discover_ssh_hosts()
        if not hosts:
            print(f"{CYL}no hay maquinas con SSH encima de {SUBNET}{R}\n")
            return
        print(f"{CG}con SSH: {', '.join(sorted(hosts, key=lambda x: int(x.rsplit('.',1)[1])))}{R}\n")
    else:
        if not nn or norm_num(nn[0]) is None:
            print(f"{CR}uso: make turn-off NUM=019   (acepta 19, 019, L507_019){R}\n")
            sys.exit(1)
        tag = "L507_%03d" % norm_num(nn[0])
        ip = ips.get(tag)
        if not ip:
            print(f"{CR}no tengo la ultima IP de {tag} en la cache ({CACHE_PATH}).{R}")
            print(f"{GR}corre make monitor o make check para poblarla, o usa make turn-off-all.{R}\n")
            sys.exit(2)
        hosts = [ip]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(shutdown, h) for h in hosts]
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())
    results.sort()

    icono = {"APAGADA": f"{CG}APAGADA{R}", "YA_APAGADA": f"{CYL}YA APAGADA{R}",
             "SIGUE_PRENDIDA": f"{CR}SIGUE PRENDIDA{R}", "FALLO_SSH": f"{CR}FALLO SSH{R}",
             "MAESTRA": f"{CP}MAESTRA{R}"}
    print()
    for ip, st, meta in results:
        extra = ""
        if st == "APAGADA":
            extra = f"{GR} (ssh cayo en {meta} s){R}"
        elif st == "FALLO_SSH":
            extra = f"{GR} {meta}{R}"
        tag = next((t for t, v in ips.items() if v == ip), "")
        print(f"  {B}{tag or '(?)':12s}{R} {ip:15s} {icono[st]}{extra}")
    print()


if __name__ == "__main__":
    main()
