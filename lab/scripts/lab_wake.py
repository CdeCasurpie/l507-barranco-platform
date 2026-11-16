#!/usr/bin/env python3
"""make wake / make wake-all: enciende PCs del lab L507 via Wake-on-LAN.

make wake NUM=019   -> Magic Packet a esa PC y espera que suba SSH
make wake-all       -> Magic Packet a todas las registradas; las sin MAC solo aviso

MACs en ~/.lab_wake_macs.json. Tags sin MAC registrada: advertencia y no envia.
La maestra nunca recibe paquetes.
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

MACS_PATH = os.environ.get("LAB_WAKE_MACS", os.path.expanduser("~/.lab_wake_macs.json"))
CACHE_PATH = os.environ.get("LAB_MONITOR_CACHE", os.path.expanduser("~/.lab_monitor_cache.json"))
SUBNET = ipaddress.ip_network("192.0.2.0/25")
SSH_USER = os.environ.get("LAB_SSH_USER", "utec_alumno")
from lab_config import DEFAULT_SSH_PASSWORD

SSH_PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
MASTER_IP = None
ALL_TAGS = ["L507_%03d" % i for i in range(1, 25)]


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
    m = str(n).strip().upper().replace(" ", "")
    m = m.replace("L507_", "")
    m = m.lstrip("L")
    if not m.isdigit():
        return None
    return int(m)


def tag_of(n):
    return "L507_%03d" % n


def port22(ip, timeout=0.4):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, 22)) == 0
    except Exception:
        return False
    finally:
        s.close()


def alive(ip):
    try:
        p = subprocess.run(["ping", "-c", "1", "-W", "1", "-n", ip],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return p.returncode == 0
    except Exception:
        return False


def send_wol(mac):
    pkt = bytes.fromhex("ff" * 6 + mac.replace(":", "").lower() * 16)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    n = 0
    for dst in ["192.0.2.127", "255.255.255.255"]:
        for port in (9, 7):
            try:
                s.sendto(pkt, (dst, port))
                n += 1
            except Exception:
                pass
    s.close()
    return n


def wait_ip_up(ip, timeout=240):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if port22(ip):
            return int(time.time() - t0)
        time.sleep(5)
    return None


def ssh_tag_at(ip, timeout=45):
    try:
        import pexpect
        child = pexpect.spawn("ssh", ["-o", "ConnectTimeout=6", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
            "-o", "NumberOfPasswordPrompts=1", "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no", "%s@%s" % (SSH_USER, ip), "ls -m ~ ; echo __END__"],
            encoding="utf-8", timeout=timeout, echo=False)
        child.expect(["[Pp]assword:", pexpect.EOF], timeout=20)
        child.sendline(SSH_PASSWORD)
        child.expect(pexpect.EOF, timeout=timeout)
        out = child.before or ""
        child.close()
        if child.exitstatus != 0:
            return None
        return out
    except Exception:
        return None


def scan_new_ip(tag, timeout=120):
    """Busca en toda la subred la maquina con este tag, por si DHCP la movio."""
    t0 = time.time()
    hosts = [str(x) for x in SUBNET.hosts() if str(x) != masters_ip()]
    while time.time() - t0 < timeout:
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as ex:
            for ip, ok in zip(list(hosts), ex.map(port22, list(hosts))):
                if ok and tag_of(int(tag[-3:])) and tag in (ssh_tag_at(ip) or ""):
                    return ip
        time.sleep(10)
    return None


def wake_one(tag, mac, ip, wait=True):
    """Devuelve (tag, estado, datoss).
    estados: YA_LINEA / UPTIME / ENVIADO / TIMEOUT / SIN_MAC
    """
    if not mac:
        return tag, "SIN_MAC", None
    if ip and port22(ip):
        return tag, "YA_LINEA", ip
    n = 0
    for _ in range(3):
        n += send_wol(mac)
        time.sleep(1)
    if not (ip and ip != masters_ip()):
        return tag, "ENVIADO", None
    dt = wait_ip_up(ip, 240 if wait else 5)
    if dt is not None:
        return tag, "UP", (ip, dt)
    ipnew = scan_new_ip(tag, 90)
    if ipnew:
        cache = load_json(CACHE_PATH, {})
        cache[tag] = {"ip": ipnew, "ts": time.time()}
        try:
            with open(CACHE_PATH, "w") as fh:
                json.dump(cache, fh, indent=1)
        except Exception:
            pass
        return tag, "UP", (ipnew, "rescan")
    return tag, "TIMEOUT", None


def main():
    args = [a for a in sys.argv[1:] if a]
    all_mode = "--all" in args
    nfiles = [a for a in args if a != "--all"]
    macs = load_json(MACS_PATH, {})
    cache = load_json(CACHE_PATH, {})
    ips = {t: v.get("ip") for t, v in cache.items() if isinstance(v, dict) and v.get("ip")}

    print(f"\n{B}{CP}WAKE-ON-LAN LAB L507{R}\n")
    if all_mode:
        targets = ALL_TAGS
        no_mac = [t for t in ALL_TAGS if not macs.get(t)]
        print(f"{GR}registradas {len(ALL_TAGS)-len(no_mac)}/24{R}   {CYL}sin MAC (no se enviara paquete): "
              f"{', '.join(no_mac) if no_mac else '-'}{R}\n")
    else:
        if not nfiles or norm_num(nfiles[0]) is None:
            print(f"{CR}uso: make wake NUM=019   (acepta 19, 019, L507_019){R}\n")
            sys.exit(1)
        tag = tag_of(norm_num(nfiles[0]))
        if not macs.get(tag):
            print(f"{CR}advertencia: {tag} no tiene MAC registrada -> NO envio Magic Packet.{R}")
            print(f"{GR}para registrarla: prendela, deja que make check/monitor la vea, y agrego la MAC.{R}\n")
            sys.exit(2)
        targets = [tag]

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
        futs = [ex.submit(wake_one, t, macs.get(t), ips.get(t), wait=True) for t in targets]
        for f in concurrent.futures.as_completed(futs):
            results.append(f.result())
    results.sort()

    icono = {"UP": f"{CG}UP{R}", "YA_LINEA": f"{CYL}YA LINEA{R}", "ENVIADO": f"{CY}PAQUETE ENVIADO{R}",
             "TIMEOUT": f"{CR}NO RESPONDE{R}", "SIN_MAC": f"{CR}SIN MAC{R}"}
    print()
    for tag, st, meta in results:
        extra = ""
        if st == "UP":
            extra = f"{GR} {meta[0]}  (ssh listo en {meta[1]} s){R}"
        elif st == "YA_LINEA":
            extra = f"{GR} {meta if meta else '-'}{R}"
        print(f"  {B}{tag}{R}  {icono[st]}{extra}")
    print()
    n_up = sum(1 for _, s, _ in results if s in ("UP", "YA_LINEA") or True)


if __name__ == "__main__":
    main()
