#!/usr/bin/env python3
"""make logout / make logout-all: cierra la sesion grafica (monitor) de las hijas.

Sin tocar el SSH. Las sesiones de asiento seat0 se terminan con
`loginctl terminate-session`; el monitor queda en el greeter y
nada puede usarse sin credencial hasta el proximo boot (donde vuelve
el autologin de utec_alumno).
"""
import concurrent.futures
import os
import re
import sys

from lab_inventory import CG, CYL, CR, GR, R, SSH_USER, discover_subnet, scan_port22

from lab_config import DEFAULT_SSH_PASSWORD, DEFAULT_SUDO_PASSWORD

SSH_PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
SUDO_PASSWORD = os.environ.get("LAB_SUDO_PASSWORD", DEFAULT_SUDO_PASSWORD)

SCRIPT = """\
IDS=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$4=="seat0" && $6=="user" {print $1}')
if [ -z "$IDS" ]; then echo NOGUI; exit 0; fi
for I in $IDS; do loginctl terminate-session "$I" 2>&1 | head -1; done
sleep 2
LEFT=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$4=="seat0" && $6=="user" {print $1}' | wc -l)
echo ENDED=LEFT$LEFT
"""


def _b64(text):
    import base64
    return base64.b64encode(text.encode()).decode()


def logout_one(ip, timeout=50):
    import pexpect
    bundled = _b64(SCRIPT)
    try:
        child = pexpect.spawn("ssh", [
            "-o", "ConnectTimeout=6",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR",
            "-o", "NumberOfPasswordPrompts=1",
            "-o", "PreferredAuthentications=password",
            "-o", "PubkeyAuthentication=no",
            f"{SSH_USER}@{ip}",
            f"echo {bundled} | base64 -d > /tmp/lg.sh && printf %s {SUDO_PASSWORD} | sudo -S -p '' -k sh /tmp/lg.sh",
        ], encoding="utf-8", timeout=timeout, echo=False)
        ev = child.expect(["[Pp]assword:", pexpect.EOF, pexpect.TIMEOUT], timeout=timeout)
        if ev == 0:
            child.sendline(SSH_PASSWORD)
            child.expect(pexpect.EOF, timeout=timeout)
        out = (child.before or "").replace("\r", "")
        child.close()
        return out
    except Exception as e:
        return "ERR:" + str(e)


def report(ip, out):
    if "ERR:" in out:
        return ip, "fail", f"FALLO {out.strip()[-60:]}"
    if "NOGUI" in out:
        return ip, "nogui", CYL + "sin sesion grafica" + R
    if "ENDED=LEFT0" in out:
        return ip, "done", CG + "LOGOUT hecho" + R
    left = re.search(r"ENDED=LEFT(\d+)", out)
    if left:
        return ip, "partial", CYL + f"quedan {left.group(1)} ses(ion)es abiertas" + R
    return ip, "fail", "respuesta inesperada: " + out.strip()[-50:]


def run(targets):
    n_done = n_fail = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for ip, out in zip(targets, pool.map(logout_one, targets)):
            _, kind, msg = report(ip, out)
            print(f"  {ip}  {msg}")
            n_done += kind == "done"
            n_fail += kind not in ("done", "nogui")
    print(f"\n{CG}logout {n_done}{R} | {CYL}sin sesion{R} | {CR if n_fail else GR}fallos {n_fail}{R}")
    if n_fail:
        sys.exit(1)


def main():
    argv = sys.argv[1:]
    if argv and argv[0].strip().lower() not in ("all", ""):
        run(argv)
        return
    net, iface, own = discover_subnet()
    targets = [h for h in scan_port22(net) if h != own]
    print(f"{GR}Cerrando sesion grafica de {len(targets)} hijas (subred {net}){R}")
    run(targets)


if __name__ == "__main__":
    main()
