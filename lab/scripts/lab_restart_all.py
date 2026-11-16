#!/usr/bin/env python3
"""make restart-all: reinicia todas las hijas del lab por SSH.

Pide la clave de sudo en consola (ENTER = clave local configurada), manda
`systemctl reboot` a cada hija accesible de la subred cableada
y confirma que vuelvan. La maestra (esta PC) no se reinicia.
"""
import concurrent.futures
import getpass
import json
import os
import sys
import time

from lab_inventory import (
    CG, CYL, CR, CC, CM, GR, B, R,
    SSH_USER,
    cell,
    discover_subnet,
    scan_port22,
)

from lab_config import DEFAULT_SSH_PASSWORD, DEFAULT_SUDO_PASSWORD

SSH_PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
SUDO_PASSWORD = os.environ.get("LAB_SUDO_PASSWORD", DEFAULT_SUDO_PASSWORD)


def ask_key():
    default = SUDO_PASSWORD
    try:
        ans = input(f"{B + CC}Clave sudo{R} [ENTER para usar {default}]: ")
    except EOFError:
        ans = ""
    return ans.strip() or default


def reboot_one(args, ip, sudo_pw, timeout=60):
    try:
        import pexpect
        quoted = "'" + sudo_pw.replace("'", "'\\''") + "'"
        child = pexpect.spawn("ssh", args + [
            f"{SSH_USER}@{ip}",
            "printf %s " + quoted + " | sudo -S -p '' -k systemctl reboot; echo RC=$?",
        ], encoding="utf-8", timeout=timeout, echo=False)
        child.expect(["[Pp]assword:", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
        child.sendline(SSH_PASSWORD)
        child.expect(pexpect.EOF, timeout=timeout)
        out = (child.before or "").replace("\r", "")
        child.close()
        return "RC=0" in out
    except Exception:
        return False


def wait_back(ip, deadline, gone):
    """Espera: primero que el puerto se cierre, luego que vuelva."""
    import socket

    def open_p():
        s = socket.socket()
        s.settimeout(1.5)
        try:
            ok = s.connect_ex((ip, 22)) == 0
            return ok
        finally:
            s.close()

    while time.time() < deadline and open_p():
        time.sleep(3)
    gone.append(ip)
    while time.time() < deadline:
        if open_p():
            return True
        time.sleep(4)
    return False


def main():
    args = [
        "-o", "ConnectTimeout=6",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", "NumberOfPasswordPrompts=1",
        "-o", "PreferredAuthentications=password",
        "-o", "PubkeyAuthentication=no",
    ]
    sudo = ask_key()

    net, iface, own = discover_subnet()
    hosts = [h for h in scan_port22(net) if h != own]
    print(f"{GR}Reiniciando {len(hosts)} hijas (subred {net}; maestra {own} viva){R}\n")

    rc = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for ip, good in zip(hosts, pool.map(lambda h: reboot_one(args, h, sudo), hosts)):
            mark = CG + "REBOOT enviada" + R if good else CR + "FALLO" + R
            print(f"  {ip}  {mark}")
            rc[ip] = good

    print(f"\n{CYL}Esperando que vuelvan (hasta 5 min)...{R}")
    alive, dead = [], []
    deadline = time.time() + 300
    gone = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futs = {ip: pool.submit(wait_back, ip, deadline, gone) for ip, good in rc.items() if good}
        for ip, f in futs.items():
            t0 = time.time()
            reached = f.result()
            wait = int(time.time() - t0)
            print(f"  {ip}  {(CG + 'DE VUELTA' if reached else CR + 'NO RESPONDE') + R}"
                  f"  (~{wait}s)")
            (alive if reached else dead).append(ip)

    for ip, good in rc.items():
        if not good:
            print(f"  {ip}  {CYL}no se envio reboot{R}")
            dead.append(ip)

    print(f"\n{CG}{len(alive)} de vuelta{R} | {CR if dead else GR}{len(dead)} pendientes{R}")
    if dead:
        sys.exit(1)


if __name__ == "__main__":
    main()
