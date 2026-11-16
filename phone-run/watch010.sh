#!/bin/bash
# Vigila cuadra-010: si falla por la ruta best_model.txt (bug de experimento), la relanza una vez.
R=/data/photogrammetry/campaigns/barranco-2026-11-12/cuadra-010
for i in $(seq 1 480); do
  S=$(cd ~/mesh-run && python3 hrun.py 192.0.2.54 "python3 -c \"import json;d=json.load(open('$R/reconstruction-full-status.json'));print('ST',d.get('state'),d.get('experiment'),'best_model.txt' in d.get('error',''))\"" | grep '^ST')
  echo "$(date '+%F %T') $S"
  case "$S" in
    "ST failed barranco_4k_2fps_combined_v1 True") echo "relanzando"; bash ~/phone-run/relaunch.sh 54 010; exit 0;;
    "ST completed"*|"ST failed"*) echo "fin sin acción"; exit 0;;
    *"barranco_phone_1080p_2fps_v1"*) echo "ya relanzado"; exit 0;;
  esac
  sleep 120
done
