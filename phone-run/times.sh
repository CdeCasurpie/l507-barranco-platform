# times.sh BLK BASE : tiempos por etapa
B=$1; R=$2/photogrammetry/campaigns/barranco-2026-11-12/cuadra-$B; L=$R/logs/reconstruction/full; O=$R/outputs/cuadra-$B/barranco_phone_1080p_2fps_v1
for s in frames masks sfm undistort metrics; do echo "$s $(grep -ho "etapa '$s': completada en [0-9.,]* s" $L/$s.log 2>/dev/null | tail -1 | grep -o '[0-9.,]* s')"; done
python3 - "$O" "$R" <<'PY'
import json,sys,os,re
O,R=sys.argv[1:]
plan=os.path.getmtime(O+'/mvs/dense-batch-plan.json'); done=os.path.getmtime(O+'/mvs/dense-batches.json')
st=json.load(open(R+'/reconstruction-full-status.json'))
print('dense_batches %.0f s (plan->final)'%(done-plan))
print('worker_inicio', st.get('started_at'), 'fin', st.get('finished_at'))
PY
ls -la --time-style=+%F_%T $R/worker.log | awk '{print "worker.log", $6}'; grep -c relanzado $R/worker.log; head -c 0 /dev/null
stat -c '%y %n' $O/frames 2>/dev/null | cut -c1-19
