#!/bin/bash
# opencode-link.sh : genera un enlace NUEVO de vinculación (un uso, 5 min) para el opencode de la 001.
# Arranca el servidor de opencode si estuviera detenido (p. ej. tras un reinicio de la 001).
cd ~/mesh-run && python3 hrun.py 192.0.2.56 'export NO_COLOR=1; O=~/.opencode/bin/opencode; [ "$($O service status 2>&1 | head -1)" = stopped ] && (cd /mnt/datos/tesis-cava && $O service start >/dev/null 2>&1; sleep 5); timeout 90 $O pair --remote --yes 2>&1 | grep -E "Links work|https://"' | grep -v '^\s*$' | sed 's/\x1b\[[0-9;]*m//g'
