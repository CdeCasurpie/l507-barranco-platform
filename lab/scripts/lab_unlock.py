#!/usr/bin/env python3
"""make unlock IP=... / unlock-all: habilita usar desktop de la(s) maquina(s).

Revarelock de la ses grafica activa:
  gsettings lock-enabled false -> SetActive false -> GetActive debe dar false
luego restaurar lock-enabled true para que futuros ciclos vuelvan a exigir
la clave de utec_alumno al lock de nuvo. No toca SSH ni aplica a greeter.
"""
import concurrent.futures
import re
import os
import sys

from lab_inventory import (
    CG, CYL, CR, GR, R, SSH_USER,
    discover_subnet, scan_port22,
)

from lab_config import DEFAULT_SSH_PASSWORD, DEFAULT_SUDO_PASSWORD

SSH_PASSWORD = os.environ.get("LAB_SSH_PASSWORD", DEFAULT_SSH_PASSWORD)
SUDO_PASSWORD = os.environ.get("LAB_SUDO_PASSWORD", DEFAULT_SUDO_PASSWORD)

SCRIPT = """\
SVS=$(loginctl list-sessions --no-legend 2>/dev/null | awk '$4=="seat0" && $2+0>=1000 && $6 ~ /^(active|online|active-bg)/ {print $1":"$2}')
if [ -z "$SVS" ]; then
  systemctl restart gdm 2>/dev/null
  sleep 12
  NEW=$(loginctl list-sessions --no-legend | awk '$4=="seat0" && $2+0>=1000 {print $1}' | head -1)
  if [ -n "$NEW" ]; then echo AUTOLOGIN=ses$NEW; else echo NOGUI; fi
  exit 0
fi
UNLOCKED=0
for S in $SVS; do
  ID=${S%%:*}; UID=${S##*:}
  UN=$(id -un $UID)
  sudo -u "$UN" loginctl unlock-session "$ID" 2>/dev/null
  B=unix:path=/run/user/$UID/bus
  sudo -u "$UN" env DBUS_SESSION_BUS_ADDRESS=$B DISPLAY=:0 \
    gsettings set org.gnome.desktop.screensaver lock-enabled false >/dev/null 2>&1
  sudo -u "$UN" env DBUS_SESSION_BUS_ADDRESS=$B DISPLAY=:0 \
    gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver \
    --method org.gnome.ScreenSaver.SetActive false >/dev/null 2>&1
  ST=$(sudo -u "$UN" env DBUS_SESSION_BUS_ADDRESS=$B DISPLAY=:0 \
    gdbus call --session --dest org.gnome.ScreenSaver --object-path /org/gnome/ScreenSaver \
    --method org.gnome.ScreenSaver.GetActive 2>/dev/null)
  sudo -u "$UN" env DBUS_SESSION_BUS_ADDRESS=$B DISPLAY=:0 \
    gsettings set org.gnome.desktop.screensaver lock-enabled true >/dev/null 2>&1
  case "$ST" in
    *true*) : ;;
    *) UNLOCKED=1; echo "SES$ID=DESBLOQUEADA";;
  esac
done
if [ "$UNLOCKED" = 0 ]; then
  systemctl restart gdm 2>/dev/null
  sleep 12
  NEW=$(loginctl list-sessions --no-legend | awk '$4=="seat0" && $2+0>=1000 {print $1}' | head -1)
  echo "RELOGIN=$NEW"
fi
"""


def _b64(text):
    import base64
    return base64.b64encode(text.encode()).decode()


def unlock_one(ip, timeout=70):
    import pexpect
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
            f"echo {_b64(SCRIPT)} | base64 -d > /tmp/unl.sh && printf %s {SUDO_PASSWORD} | sudo -S -p '' -k sh /tmp/unl.sh",
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
    argv = [a.strip() for a in sys.argv[1:] if a.strip()]
    if argv:
        targets = argv
    else:
        net, iface, own = discover_subnet()
        targets = [h for h in scan_port22(net) if h != own]
        print(f"{GR}Desbloqueando ses grafica de {len(targets)} hijas (subred {net}){R}")

    n_ok = n_fail = n_nogui = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for ip, out in zip(targets, pool.map(unlock_one, targets)):
            if "ERR:" in out:
                n_fail += 1
                print(f"  {ip}  {CR}FALLO{R} {out.strip()[-60:]}")
            elif "DESBLOQUEADA" in out:
                n_ok += 1
                ses = re.findall(r"SES(\d+)", out)
                print(f"  {ip}  {CG}DESBLOQUEADA (ses {','.join(ses)}){R}")
            elif "AUTOLOGIN" in out or "RELOGIN" in out:
                n_ok += 1
                print(f"  {ip}  {CG}DESBLOQUEADA via autologin (gdm reiniciado){R}")
            elif "NOGUI" in out:
                n_nogui += 1
                print(f"  {ip}  {CYL}sin sesion grafica (greeter o apagada){R}")
            else:
                n_fail += 1
                print(f"  {ip}  {CR}no se pudo desbloquear{R} {out.strip()[-50:]}")

    print(f"\n{CG}DESBLOQUEADAS {n_ok}{R} | {CYL}sin sesion {n_nogui}{R} | {CR if n_fail else GR}fallos {n_fail}{R}")
    if n_fail:
        sys.exit(1)


if __name__ == "__main__":
    main()
