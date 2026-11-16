#!/bin/bash
# relaunch.sh IP BLK : relanza phone_worker (reanuda etapas hechas) si no está corriendo
IP=$1; BLK=$2; R=/data/photogrammetry/campaigns/barranco-2026-11-12/cuadra-$BLK
cd ~/mesh-run
python3 hput.py 10.100.41.$IP $R/ ~/phone-run/phone_worker.py >/dev/null
python3 hrun.py 10.100.41.$IP "pgrep -f '^python3 -B /[^ ]*/phone_worker[.]py $R' >/dev/null && echo YA-CORRIENDO || (echo '--- relanzado' \$(date) >> $R/worker.log; setsid nohup python3 -B $R/phone_worker.py $R >> $R/worker.log 2>&1 < /dev/null & sleep 25; python3 -c \"import json;d=json.load(open('$R/reconstruction-full-status.json'));print(d.get('state'),d.get('stage'),d.get('experiment'),d.get('resumed_with'),d.get('error',''))\"; tail -2 $R/worker.log)"
