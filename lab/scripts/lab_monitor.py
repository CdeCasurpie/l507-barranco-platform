#!/usr/bin/env python3
"""make monitor: monitoreo vivo del lab cada 3s hasta Ctrl+C.

Estado por maquina (grid fisico 001-024):
  verde  = puerto 22 abierto y tag identificado (TXT via SSH o cache)
  amarillo = responde a ping pero no da SSH, o SSH sin TXT (no sabemos quien es)
  plomo / gris  = no responde (apagada o desconectada del cable)

Cache JSON con la ultima IP conocida por tag para identificarlas aunque
cambien de IP o perdan SSH temporalmente.
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
import threading
import time

try:
    import pexpect
except ImportError:
    sys.exit("falta pexpect")

CY = "\033[36m"
CG = "\033[32m"
CYL = "\033[33m"
CR = "\033[31m"
GR = "\033[90m"
B = "\033[1m"
R = "\033[0m"

from lab_config import DEFAULT_SSH_PASSWORD

SSH_USER = os.environ.get("LAB_SSH_USER", "utec_alumno")
SSH_PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
CACHE_PATH = os.environ.get("LAB_MONITOR_CACHE", os.path.expanduser("~/.lab_monitor_cache.json"))
REFRESH = float(os.environ.get("LAB_MONITOR_REFRESH", "3"))

NUMERS = list(range(1, 25))
TAG_BY_NUM = {i: f"L507_{i:03d}" for i in NUMERS}

STATE_UNKNOWN = "down"
STATE_ON = "on"
STATE_SSH = "ssh"


def discover_subnet():
    data = subprocess.run(["ip", "-j", "-4", "addr"], text=True, capture_output=True, timeout=10).stdout
    for itf in json.loads(data):
        for ad in itf.get("addr_info", []):
            if ad["local"].startswith("10.100.41."):
                return ipaddress.ip_interface(f'{ad["local"]}/{ad["prefixlen"]}').network, ad["local"]
    return ipaddress.ip_network("192.0.2.0/25"), ""


def load_cache():
    try:
        with open(CACHE_PATH) as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_cache(cache):
    try:
        with open(CACHE_PATH, "w") as fh:
            json.dump(cache, fh, indent=1)
    except Exception:
        pass


def ping_ok(ip):
    try:
        p = subprocess.run(["ping", "-c", "1", "-W", "1", "-n", ip],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return p.returncode == 0
    except Exception:
        return False


def port22_ok(ip, timeout=0.5):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex((ip, 22)) == 0
    finally:
        s.close()


def ssh_tag_lookup(ip, timeout=25):
    """Devuelve el tag L507_XXX del TXT en el home, o None."""
    cmd = "ls -m ~ ; echo __END__"
    try:
        child = pexpect.spawn("ssh", [
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "NumberOfPasswordPrompts=1",
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
            f"{SSH_USER}@{ip}", cmd,
        ], encoding="utf-8", timeout=timeout, echo=False)
        ev = child.expect(["[Pp]assword:", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
        if ev == 0:
            child.sendline(SSH_PASSWORD)
            child.expect(pexpect.EOF, timeout=timeout)
        out = (child.before or "").replace("\r", "")
        child.close()
        if child.exitstatus != 0:
            return None
        m = re.search(r"L507[_ ]?\d+", out, re.I)
        return m.group(0).upper().replace(" ", "_") if m else None
    except Exception:
        return None


def collect_cycle(net, own_ip, cache, lock):
    """Un ciclo completo de sondeo; actualiza cache y devuelve estado."""
    ssh_hosts, ping_hosts = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=48) as pool:
        net_hosts = [str(ip) for ip in net.hosts() if str(ip) != own_ip]
        for ip, ok in zip(net_hosts, pool.map(ping_ok, net_hosts)):
            if ok:
                ping_hosts.append(ip)
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        for ip, ok in zip(ping_hosts, pool.map(port22_ok, ping_hosts)):
            if ok:
                ssh_hosts.append(ip)

    arp = {}
    try:
        raw = subprocess.run(["ip", "-j", "neigh"], text=True, capture_output=True, timeout=8).stdout
        for e in json.loads(raw):
            if e.get("dst"):
                arp[e["dst"]] = (e.get("lladdr") or "").lower()
    except Exception:
        pass

    ip2tag = {v["ip"]: t for t, v in cache.items() if isinstance(v, dict) and v.get("ip")}
    state, unknown = {}, []
    for ip in ping_hosts:
        tag = ip2tag.get(ip)
        mac = arp.get(ip, "")
        if ip in ssh_hosts:
            if tag:
                state[tag] = (STATE_SSH, ip)
                continue
            got = None
            with lock:
                got = ssh_tag_lookup(ip)
            if got and got in TAG_BY_NUM.values():
                cache[got] = {"ip": ip, "ts": time.time()}
                save_cache(cache)
                state[got] = (STATE_SSH, ip)
            elif mac.startswith("f4:f1:9e"):
                unknown.append(ip)
        else:
            if tag:
                state[tag] = (STATE_ON, ip)
            elif mac.startswith("f4:f1:9e"):
                unknown.append(ip)
    return state, unknown, ping_hosts, ssh_hosts


class Monitor:
    def __init__(self, net, own_ip, cache):
        self.net = net
        self.own = own_ip
        self.cache = cache
        self.lock = threading.Lock()
        self.data = ({}, [], [], [])
        self.new_data = False
        self.pending = True
        self.stop = False

    def collector(self):
        while not self.stop:
            try:
                state, unknown, pings, sshs = collect_cycle(self.net, self.own, self.cache, self.lock)
                with self.lock:
                    self.data = (state, unknown, pings, sshs)
                    self.new_data = True
            except Exception as e:
                with self.lock:
                    self.data = ({}, [f"ERR:{e}"], [], [])
            time.sleep(3)

    def render(self):
        with self.lock:
            state, unknown, pings, sshs = self.data
            if not (state or unknown or pings or sshs):
                if self.pending:
                    return f"\n  {CYL}Sondeando red...{R}\n"
            self.pending = False
        n_green = sum(1 for v in state.values() if v[0] == STATE_SSH)
        n_on = sum(1 for v in state.values() if v[0] == STATE_ON)
        lines = []
        lines.append(f"\n  {B}{CY}MONITOR LABORATORIO UTEC{R}   {GR}actualizado {time.strftime('%H:%M:%S')}{R}\n")
        for base in (1, 7, 13, 19):
            cells = []
            for i in range(base, base + 6):
                st = state.get(TAG_BY_NUM[i])
                num = f"{i:02d}"
                if st is None:
                    cells.append(f"{num} {GR}\u25cb{R}")
                elif st[0] == STATE_SSH:
                    cells.append(f"{num} {CG}\u25cf{R}")
                else:
                    cells.append(f"{num} {CYL}\u25cf{R}")
            lines.append("    " + "   ".join(cells[:3]) + "     " + "   ".join(cells[3:]) + "\n")
        lines.append("\n")
        lines.append(f"    {CG}\u25cf{R} Accesible SSH    {CYL}\u25cf{R} Encendida sin SSH    {GR}\u25cb{R} Apagada/desconectada\n")
        lines.append(f"\n    {B}Disponibles: {n_green}/{len(NUMERS)}{R}   encendidas sin SSH: {n_on}\n")
        if unknown:
            ips = "  ".join(unknown)
            lines.append(f"\n    {CYL}Sin identificar ({len(unknown)}): {ips}{R}\n")
        return "".join(lines)


def main():
    net, own = discover_subnet()
    cache = load_cache()
    mon = Monitor(net, own, cache)
    t = threading.Thread(target=mon.collector, daemon=True)
    print(f"{GR}monitor lab en {net} (cache {CACHE_PATH}); Ctrl+C para salir{R}", file=sys.stderr)
    t.start()
    time.sleep(3.5)
    try:
        while True:
            payload = mon.render()
            sys.stdout.write("\033[H\033[2J" + payload)
            sys.stdout.flush()
            time.sleep(REFRESH)
    except KeyboardInterrupt:
        print(f"{GR}monitor finalizado{R}", file=sys.stderr)


if __name__ == "__main__":
    main()
