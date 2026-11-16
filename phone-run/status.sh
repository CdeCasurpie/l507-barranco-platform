#!/bin/bash
# Estado de las 3 manzanas de celular (barranco-2026-11-12)
for t in 006:80 010:54 011:44; do b=${t%:*}; ip=10.100.41.${t#*:}; R=/data/photogrammetry/campaigns/barranco-2026-11-12/cuadra-$b
  echo "cuadra-$b ($ip): $(python3 ~/mesh-run/hrun.py $ip "python3 -c \"import json;d=json.load(open(\\\"$R/reconstruction-full-status.json\\\"));t=d.get(\\\"telemetry\\\",{});print(d[\\\"state\\\"],d.get(\\\"stage\\\"),\\\"hechas=\\\"+\\\",\\\".join(d.get(\\\"completed_stages\\\",[])),\\\"sparse_lista=\\\"+str(d.get(\\\"sparse_ready\\\",False)),\\\"img=\\\"+str(d.get(\\\"registered_images\\\",\\\"-\\\")),\\\"gpu=%.0fC cpu=%.0fC\\\"%(t.get(\\\"gpu_c\\\",0),t.get(\\\"cpu_c\\\",0)),d.get(\\\"error\\\",\\\"\\\"))\"" < /dev/null | tail -1)"
done
