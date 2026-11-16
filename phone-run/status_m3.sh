#!/bin/bash
# status_m3.sh: estado de la re-corrida con máscaras personas/postes/cables
cd ~/mesh-run
for x in "006 192.0.2.55 L507_003" "010 192.0.2.54 L507_002" "011 192.0.2.64 L507_006"; do set -- $x
  R=/data/photogrammetry/campaigns/barranco-2026-11-12-m3/cuadra-$1
  echo "cuadra-$1 ($3): $(timeout 40 python3 hrun.py $2 "python3 -c \"import json;d=json.load(open('$R/reconstruction-full-status.json'));print(d.get('state'),d.get('stage'),'hechas='+','.join(d.get('completed_stages',[])),'img='+str(d.get('registered_images','-')),d.get('error','')[:150])\" 2>&1; nvidia-smi --query-gpu=temperature.gpu,power.draw --format=csv,noheader" | grep -v '^\s*$' | tr '\n' ' ')"
done
