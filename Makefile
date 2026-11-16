ifneq ($(origin LAB_SSH_PASSWORD),undefined)
export LAB_SSH_PASSWORD
endif
ifneq ($(origin LAB_SUDO_PASSWORD),undefined)
export LAB_SUDO_PASSWORD
endif
export LAB_NET ?= auto

CY := \033[36m
CYEL := \033[33m
CGRAY := \033[90m
CB := \033[1m
R := \033[0m

.PHONY: help check monitor barranco-status pipeline-status barranco-status-json restart-all lock-all unlock unlock-all logout logout-all wake wake-all turn-off turn-off-all

.DEFAULT_GOAL := help

help:
	@printf "  ${CB}${CY}LAB L507 - comandos${R}\n\n"
	@printf "  ${CB}${CY}Flujo habitual${R}\n"
	@printf "  ${CGRAY}1. make check      ${R}inventario: tag, IP, MAC, GPU, disco, arranque\n"
	@printf "  ${CGRAY}2. make monitor    ${R}monitor vivo de la red cada 3s (Ctrl+C para salir)\n"
	@printf "  ${CGRAY}   make barranco-status${R}estado actual del pipeline Barranco (solo consulta)\n"
	@printf "  ${CGRAY}3. make restart-all${R}reinicia hijas (encienden con desktop abierto)\n"
	@printf "  ${CGRAY}4. make lock-all   ${R}bloquea monitores (lock screen; recomendado a diario)\n"
	@printf "  ${CGRAY}5. make unlock-all ${R}desbloquea todas (o una: make unlock IP=x.x.x.x)\n"
	@printf "  ${CGRAY}6. make logout-all ${R}cierra sesion del monitor (cierra apps abiertas)\n"
	@printf "  ${CGRAY}   make logout IP= ${R}lo mismo en una sola\n\n"
	@printf "  ${CYEL}Encender / apagar${R}\n"
	@printf "  ${CGRAY}make wake NUM=019  ${R}WoL: magic packet a esa PC (espera SSH ~5min)\n"
	@printf "  ${CGRAY}make wake-all      ${R}WoL a todas las registradas (sin MAC: solo aviso)\n"
	@printf "  ${CGRAY}make turn-off NUM= ${R}apaga una via SSH (sudo poweroff)\n"
	@printf "  ${CGRAY}make turn-off-all  ${R}apaga TODAS las hijas con SSH (maestra excluida)\n\n"
	@printf "  ${CYEL}Detalles${R}\n"
	@printf "  ${CGRAY}monitor            ${R}verde=SSH, amarillo=encendida sin SSH, gris=apagada\n"
	@printf "  ${CGRAY}                   ${R}cache de ultima IP por tag en ~/.lab_monitor_cache.json\n"
	@printf "  ${CGRAY}wake               ${R}MACs por tag en ~/.lab_wake_macs.json; sin MAC=no envia\n"
	@printf "  ${CGRAY}unlock-all         ${R}unlock por sesion como sudo -u + fallback gdm\n"
	@printf "  ${CGRAY}Claves(override)   ${R}make X LAB_SSH_PASSWORD=... LAB_SUDO_PASSWORD=...\n"
	@printf "  ${CGRAY}Subred             ${R}auto-detectada del cable (192.0.2.0/25)\n\n"

check:
	@python3 lab/scripts/lab_inventory.py

monitor:
	@python3 lab/scripts/lab_monitor.py

barranco-status:
	@python3 -B lab-deploy/tools/barranco_status.py

pipeline-status: barranco-status

barranco-status-json:
	@python3 -B lab-deploy/tools/barranco_status.py --json

wake:
	@python3 lab/scripts/lab_wake.py $(NUM)

wake-all:
	@python3 lab/scripts/lab_wake.py --all

turn-off:
	@python3 lab/scripts/lab_turnoff.py $(NUM)

turn-off-all:
	@python3 lab/scripts/lab_turnoff.py --all

restart-all:
	@python3 lab/scripts/lab_restart_all.py

lock-all:
	@python3 lab/scripts/lab_lock_all.py

unlock-all:
	@python3 lab/scripts/lab_unlock.py

unlock:
	@test -n "$(IP)" || { echo "uso: make unlock IP=192.0.2.44   (o make unlock-all)"; exit 1; }
	@python3 lab/scripts/lab_unlock.py $(IP)

logout-all:
	@python3 lab/scripts/lab_logout.py

logout:
	@test -n "$(IP)" || { echo "uso: make logout IP=192.0.2.65   (o make logout-all)"; exit 1; }
	@python3 lab/scripts/lab_logout.py $(IP)
