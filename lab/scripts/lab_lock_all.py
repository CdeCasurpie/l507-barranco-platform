#!/usr/bin/env python3
"""make lock-all: bloquea la sesion grafica (seat0) activa en las hijas.

Per maquina:
1. `loginctl lock-session <id>` sobre las sesiones del asiento.
2. Refuerzo directo por DBus del usuario: org.gnome.ScreenSaver.SetActive
   true, y verifica con GetActive == true.
Si no hay sesion grafica, quedo en greeter/una apagada (no hay nada que bloquear).
"""
import concurrent.futures
import os
import re
import sys

from lab_inventory import CG, CYL, CR, CC, GR, B, R, SSH_USER, cell, discover_subnet, scan_port22

from lab_config import DEFAULT_SSH_PASSWORD, DEFAULT_SUDO_PASSWORD

SSH_PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
SUDO_PASSWORD = os.environ.get("LAB_SUDO_PASSWORD", DEFAULT_SUDO_PASSWORD)

LOCK_SH = """\
SVS=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$4=="seat0" && $2 ~ /^[0-9]+$/ {print $1":"$2}')
if [ -z "$SVS" ]; then echo NOGUI; exit 0; fi
for S in $SVS; do
  ID=${S%%:*}; UID=${S##*:}
  loginctl lock-session "$ID" 2>/dev/null
  B=unix:path=/run/user/$UID/bus
  UN=$(id -un $UID 2>/dev/null)
  sudo -u "$UN" env DBUS_SESSION_BUS_ADDRESS=$B DISPLAY=:0 \
    gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver \
    --method org.gnome.ScreenSaver.SetActive true >/dev/null 2>&1
  ST=$(sudo -u "$UN" env DBUS_SESSION_BUS_ADDRESS=$B DISPLAY=:0 \
    gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver \
    --method org.gnome.ScreenSaver.GetActive 2>/dev/null)
  case "$ST" in *true*) echo "SES$ID=BLOQUEADA";; *) echo "SES$ID=ONLOCK";; esac
done
"""

def _b64(text):
    import base64
    return base64.b64encode(text.encode()).decode()

def ssh_run(ip, timeout=90):
    import pexpect
    bundled = _b64(LOCK_SH)
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
            f"echo {bundled} | base64 -d > /tmp/lk.sh && printf %s {SUDO_PASSWORD} | sudo -S -p '' -k sh /tmp/lk.sh",
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


def main():
    net, iface, own = discover_subnet()
    hosts = [h for h in scan_port22(net) if h != own]
    print(f"{GR}Bloqueado gui de {len(hosts)} hijas (subred {net}){R}\n")

    stats = {"BLOQ": 0, "NOGUI": 0, "FAIL": 0}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for ip, out in zip(hosts, pool.map(ssh_run, hosts)):
            if "ERR:" in out:
                stats["FAIL"] += 1
                print(f"  {ip}  {CR}FALLO{R} {out.strip()[-60:]}")
            elif "NOGUI" in out:
                stats["NOGUI"] += 1
                print(f"  {ip}  {CYL}sin sesion grafica (nada que bloquear){R}")
            else:
                ses = re.findall(r"SES(\d+)=(\w+)", out)
                if not ses:
                    stats["FAIL"] += 1
                    print(f"  {ip}  {CYL}respuesta inesperada{R}")
                    continue
                ok = any(b == 'BLOQUEADA' for _, b in ses)
                idl = ",".join(i for i, _ in ses)
                if ok:
                    stats["BLOQ"] += 1
                    print(f"  {ip}  {CG}BLOQUEADA (ses {idl}){R}")
                else:
                    stats["FAIL"] += 1
                    print(f"  {ip}  {CR}NO se verifico el lock (ses {idl}){R}")

    print(f"\n{CG}BLOQUEADAS {stats['BLOQ']}{R} | {CYL}sin sesion {stats['NOGUI']}{R} | {CR if stats['FAIL'] else GR}fallos {stats['FAIL']}{R}")
    if stats["FAIL"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
