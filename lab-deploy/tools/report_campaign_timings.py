"""Evidence-based retrospective: never label inferred/counterfactual times measured."""
import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import heapq
import json
from pathlib import Path
import re
import subprocess
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from drive_download_campaign import remote
sys.path.insert(0,str(PROJECT))
from labdeploy.store import atomic_json

CENTRAL=Path('/data/barranco/campaigns/barranco-full-v1')
DEST=Path('/data/barranco/reports/baseline-v1')
UTC=timezone.utc


def epoch(value):
    return datetime.fromisoformat(value).timestamp()


def iso(value):
    return datetime.fromtimestamp(value,UTC).isoformat() if value is not None else 'no registrado'


def duration(value):
    return sum(float(n)*{'h':3600,'m':60,'s':1,'ms':.001}[unit] for n,unit in re.findall(r'(\d+(?:\.\d+)?)(ms|h|m|s)',value))


def native_attempts(path):
    """OpenMVS internal timer is direct; process timestamp span has 1 s resolution."""
    lines=path.read_text(errors='replace').splitlines();segments=[];current=[]
    for line in lines:
        if re.match(r'^\d{2}:\d{2}:\d{2} .*OpenMVS x64',line):
            if current:segments.append(current)
            current=[]
        current.append(line)
    if current:segments.append(current)
    result=[]
    for part in segments:
        if not any('Command line: DensifyPointCloud' in line for line in part):continue
        times=[m.group(1) for line in part if (m:=re.match(r'^(\d{2}:\d{2}:\d{2}) \[App',line))]
        completed=[m.group(1) for line in part if (m:=re.search(r'Densifying point-cloud completed:.*\(([^()]*)\)',line))]
        span=None
        begin_epoch=None;end_epoch=None
        if len(times)>=2:
            start=sum(int(v)*60**i for i,v in enumerate(reversed(times[0].split(':'))));end=sum(int(v)*60**i for i,v in enumerate(reversed(times[-1].split(':'))));span=(end-start)%86400
            midnight=datetime.fromtimestamp(path.stat().st_mtime,UTC).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
            begin_epoch=midnight+start
            if begin_epoch>path.stat().st_mtime+2:begin_epoch-=86400
            end_epoch=begin_epoch+span
        result.append({'successful':bool(completed),'compute_fusion_internal_s':duration(completed[-1]) if completed else None,
                       'process_log_span_s':span,'start_epoch_approx':begin_epoch,'end_epoch_approx':end_epoch,
                       'timestamp_resolution_s':1,'path':str(path)})
    return result


def file_birth(path):
    p=subprocess.run(['stat','--format=%W',str(path)],capture_output=True,text=True)
    try:value=int(p.stdout.strip());return value if value>0 else None
    except ValueError:return None


def gather(site,key,a):
    code=f'''
import json,subprocess,time
from pathlib import Path
r=Path({a['work_root']!r});v={{'key':{key!r},'node_tag':{a['node_tag']!r},'work_root':str(r),'gathered_at':time.time(),'statuses':{{}},'attempts':[],'log_files':{{}},'telemetry':{{}}}}
for p in r.glob('reconstruction-*-status.json'):
 v['statuses'][p.name]=json.loads(p.read_text())
for p in r.glob('attempt-history/**/*.json'):
 if p.name.endswith('-status.json'):v['attempts'].append({{'path':str(p),'value':json.loads(p.read_text())}})
for p in r.glob('logs/reconstruction/*/*.log'):
 x=subprocess.run(['stat','--format=%W',str(p)],capture_output=True,text=True)
 v['log_files'][str(p.relative_to(r))]={{'birth_epoch_s':int(x.stdout.strip()) if x.returncode==0 else None,'mtime':p.stat().st_mtime,'bytes':p.stat().st_size}}
for p in r.glob('logs/reconstruction/*/telemetry.jsonl'):
 rows=[json.loads(line) for line in p.read_text().splitlines() if line.strip()];covered=0;gpu=0;gaps=[]
 for left,right in zip(rows,rows[1:]):
  dt=right['at']-left['at']
  if 0<dt<=20:covered+=dt;gpu+=dt*(left['gpu_busy']+right['gpu_busy'])/200
  elif dt>20:gaps.append({{'start':left['at'],'end':right['at'],'seconds':dt}})
 v['telemetry'][str(p.relative_to(r))]={{'first_at':rows[0]['at'] if rows else None,'last_at':rows[-1]['at'] if rows else None,'samples':len(rows),'covered_seconds':covered,'sampled_gpu_busy_equivalent_seconds':gpu,'gaps':gaps}}
for p in r.glob('reconstruction-*-launch.json'):
 x=subprocess.run(['stat','--format=%W',str(p)],capture_output=True,text=True);v.setdefault('launches',{{}})[p.name]={{'value':json.loads(p.read_text()),'birth_epoch_s':int(x.stdout.strip()) if x.returncode==0 else None}}
print('DOWNLOAD_REPLY='+json.dumps(v))
'''
    value=remote(site,a['ip'],code,timeout=120);atomic_json(DEST/'evidence/nodes'/(key+'.json'),value);return key


def write_csv(path,rows):
    if not rows:return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def lpt(costs,machines):
    queue=[(0,i) for i in range(machines)];heapq.heapify(queue)
    for value in sorted(costs,reverse=True):
        at,i=heapq.heappop(queue);heapq.heappush(queue,(at+value,i))
    return max(t for t,i in queue)


def hours(value):return f'{value/3600:.3f}' if value is not None else 'N/D'


def main(refresh=False):
    DEST.mkdir(parents=True,exist_ok=True)
    state=json.loads((CENTRAL/'execution-status.json').read_text())
    original={a['block_id']:a for a in json.loads((CENTRAL/'assignments.json').read_text())['assignments'] if a['block_id']!='TODO'}
    entries=dict(original);entries.update(json.loads((CENTRAL/'execution-overrides.json').read_text()))
    if refresh or not (DEST/'evidence/nodes/025.json').exists():
        site=json.loads((PROJECT/'config/site.json').read_text());jobs=list(entries.items())+[('007-original',original['007'])]
        with ThreadPoolExecutor(max_workers=5) as pool:
            for key in pool.map(lambda item:gather(site,*item),jobs):print('Timing evidence',key,flush=True)
    stage_rows=[];batch_rows=[];jobs=[];intervals=[];collection_rows=[];notes=[]
    for block,a in sorted(entries.items()):
        result=Path(state['collections'][block]['destination']);evidence=json.loads((DEST/'evidence/nodes'/(block+'.json')).read_text())
        final=evidence['statuses']['reconstruction-full-status.json']
        base=result
        if block=='007':
            base=Path('/data/barranco/results/barranco-full-v1/007/barranco_4k_2fps_combined_v1')
        markers={p.stem:json.loads(p.read_text()) for p in (result/'.stages').glob('*.done')}
        base_markers={p.stem:json.loads(p.read_text()) for p in (base/'.stages').glob('*.done')}
        timer_total=0;starts=[]
        for name in ['frames','telemetry','masks','sfm','undistort']:
            item=(markers if name=='undistort' else base_markers).get(name)
            if item is None:
                notes.append(f'{block}: falta temporizador {name}');continue
            seconds=float(item['elapsed_seconds']);end=epoch(item['finished_at']);start=end-seconds;timer_total+=seconds;starts.append(start)
            stage_rows.append({'block':block,'node':a['node_tag'],'stage':name,'seconds':seconds,'kind':'direct_stage_timer_rounded_0.01s',
                               'start_utc_approx':iso(start),'end_utc_rounded_1s':iso(end),'source':str((result if name=='undistort' else base)/'.stages'/(name+'.done'))})
        sfm=json.loads((base/'metrics/metrics.json').read_text()).get('sfm_breakdown_seconds',{})
        for name,value in sfm.items():
            stage_rows.append({'block':block,'node':a['node_tag'],'stage':'sfm_detail_'+name,'seconds':value,'kind':'direct_command_timer_rounded_0.01s',
                               'start_utc_approx':'','end_utc_rounded_1s':'','source':str(base/'metrics/metrics.json')})
        paths=sorted((result/'mvs/chunks').glob('*/dense.log'))
        if not paths:paths=[result/'logs/dense.log']
        compute=0;cli=0;native_calls=0;all_success_compute=0;planned_calls=0
        for path in paths:
            attempts=native_attempts(path)
            first_success=next((e for e in attempts if e['successful']),None)
            if first_success:
                compute+=first_success['compute_fusion_internal_s'];cli+=first_success['process_log_span_s'] or 0;planned_calls+=1
            for n,event in enumerate(attempts):
                row={'block':block,'batch':path.parent.name if 'chunks' in path.parts else 'monolithic','attempt_index':n,
                     'successful':event['successful'],'compute_fusion_internal_s':event['compute_fusion_internal_s'],
                     'process_log_span_s':event['process_log_span_s'],'start_epoch_approx':event['start_epoch_approx'],
                     'end_epoch_approx':event['end_epoch_approx'],'source':str(path)};batch_rows.append(row)
                if event['successful']:
                    all_success_compute+=event['compute_fusion_internal_s'];native_calls+=1
        stage_rows.append({'block':block,'node':a['node_tag'],'stage':'dense_compute_fusion_internal','seconds':compute,'kind':'sum_direct_openmvs_internal_timers',
                           'start_utc_approx':'','end_utc_rounded_1s':'','source':'dense_batches.csv'})
        known_attempts=[x['value'] for x in evidence['attempts'] if x['value'].get('profile')=='full']+[final]
        unique={v['pid']:v for v in known_attempts if v.get('started_at') and v.get('finished_at')}
        for v in unique.values():intervals.append({'block':block,'node':a['node_tag'],'pid':v['pid'],'start':v['started_at'],'end':v['finished_at'],
            'state':v['state'],'kind':'recorded_attempt_epoch_envelope','error':v.get('error','')})
        telemetry=evidence['telemetry'].get('logs/reconstruction/full/telemetry.jsonl',{})
        launch=evidence.get('launches',{}).get('reconstruction-full-launch.json',{}).get('birth_epoch_s')
        # Preflight-only workers also sampled into this telemetry file. Their
        # earlier samples are not reconstruction launches.
        original_start=min(x for x in [min(starts) if starts else None,launch] if x)
        wrapper=evidence['log_files'].get('logs/reconstruction/full/dense.log',{})
        complete=result/'mvs/dense-batches.json'
        wrapper_s=max(0,complete.stat().st_mtime-wrapper['birth_epoch_s']) if complete.exists() and wrapper.get('birth_epoch_s') else None
        plan=result/'mvs/dense-batch-plan.json'
        camera_instances=sum(len(v['selected']) for v in json.loads(plan.read_text())['batches']) if plan.exists() else final['quality']['registered']
        demand=timer_total+compute
        jobs.append({'block':block,'node':a['node_tag'],'frames':final['quality']['extracted'],'registered':final['quality']['registered'],
                     'direct_base_stages_s':timer_total,'dense_compute_fusion_s':compute,'dense_successful_cli_log_spans_s':cli,
                     'dense_file_envelope_s':wrapper_s,'core_workload_lower_bound_s':demand,'successful_dense_calls':native_calls,
                     'dense_batches_once':planned_calls,'all_successful_dense_internal_s':all_success_compute,
                     'duplicate_successful_dense_internal_s':all_success_compute-compute,
                     'dense_camera_instances':camera_instances,'observed_first_start':original_start,'observed_final_finish':final['finished_at'],
                     'observed_span_s':final['finished_at']-original_start,'known_attempts':len(unique),'known_attempt_envelopes_sum_s':sum(v['finished_at']-v['started_at'] for v in unique.values()),
                     'sampled_worker_covered_s':telemetry.get('covered_seconds'),'sampled_gpu_busy_equivalent_s':telemetry.get('sampled_gpu_busy_equivalent_seconds'),
                     'recovery_note':'Original frames/masks/SfM timers + recovered undistort; merge/BA and superseded dense are extra' if block=='007' else
                         'Cached validation retries make final attempt duration incomplete; use stage timers' if block=='025' else
                         'Multiple thermal/cache attempts; dense envelope contains gaps/retries' if block=='023' else
                         'Original admission hold and cached resume' if block in ['005','009'] else ''})
        receipt=json.loads((result/'collection-receipt.json').read_text());birth=file_birth(result)
        collection_rows.append({'block':block,'bytes':receipt['bytes'],'start_directory_birth':birth,'verified_at':receipt['at'],
            'transfer_and_verify_envelope_s':receipt['at']-birth if birth else None,'kind':'filesystem_birth_to_receipt_includes_pauses_retries_and_verification',
            'effective_product_MiB_s':receipt['bytes']/(receipt['at']-birth)/1024**2 if birth else None})
    original_seven=json.loads((DEST/'evidence/nodes/007-original.json').read_text())
    old_status=original_seven['statuses']['reconstruction-full-status.json']
    intervals.append({'block':'007-original','node':old_status['node_tag'],'pid':old_status['pid'],'start':old_status['started_at'],
        'end':old_status['finished_at'],'state':old_status['state'],'kind':'recorded_superseded_attempt_epoch_envelope','error':old_status.get('error','')})
    write_csv(DEST/'stages.csv',stage_rows);write_csv(DEST/'dense_batches.csv',batch_rows);write_csv(DEST/'jobs.csv',jobs)
    write_csv(DEST/'attempts.csv',intervals);write_csv(DEST/'collections.csv',collection_rows)
    costs=[j['core_workload_lower_bound_s'] for j in jobs];sim=[]
    for k in [1,2,4,8,15,19]:sim.append({'machines':k,'list_schedule_lpt_core_seconds':lpt(costs,k),'mathematical_lower_bound_core_seconds':max(max(costs),sum(costs)/k),
        'kind':'counterfactual_component_only_model_not_a_sequential_measurement'})
    write_csv(DEST/'counterfactuals.csv',sim)
    first=min(j['observed_first_start'] for j in jobs);last=max(j['observed_final_finish'] for j in jobs)
    events=[]
    for i in intervals:events.extend([(i['start'],1),(i['end'],-1)])
    running=0;maximum=0
    for t,delta in sorted(events,key=lambda x:(x[0],x[1])):running+=delta;maximum=max(maximum,running)
    # Final source result files expose operation-body envelopes, not profiler times.
    master=[];ws=Path('/data/barranco/alignment/barranco-full-v1')
    for result in (ws/'runs').glob('*/result.json'):
        context=result.parent/'local-context.json'
        if context.exists():master.append({'run_id':result.parent.name,'body_envelope_s':result.stat().st_mtime-context.stat().st_mtime,
            'start_context_mtime':context.stat().st_mtime,'end_result_mtime':result.stat().st_mtime,'kind':'filesystem_context_to_result_not_process_timer',
            'result':json.loads(result.read_text())})
    atomic_json(DEST/'master_operations.json',master)
    journal=subprocess.run(['journalctl','--user','-u','barranco-alignment-*','-o','json','--no-pager'],capture_output=True,text=True)
    journal_rows=[json.loads(line) for line in journal.stdout.splitlines() if line.startswith('{')]
    journal_evidence=DEST/'evidence/master-scope-journal.json'
    if journal_rows:
        atomic_json(journal_evidence,journal_rows)
    elif journal_evidence.exists():
        journal_rows=json.loads(journal_evidence.read_text())
    else:
        raise RuntimeError('No hay journal de scopes ni evidencia archivada; no se pueden reconstruir sus tiempos')
    scopes=[]
    for row in journal_rows:
        message=row.get('MESSAGE','');unit=row.get('USER_UNIT','')
        match=re.search(r'Consumed (.*?) CPU time over (.*?) wall clock time, (.*?) memory peak',message)
        if match:scopes.append({'unit':unit,'finished_epoch':int(row['__REALTIME_TIMESTAMP'])/1e6,
            'wall_seconds':duration(match[2].replace('min','m').replace(' ','')),
            'cpu_seconds':duration(match[1].replace('min','m').replace(' ','')),'memory_peak_text':match[3],
            'kind':'systemd_accounted_scope_wall_clock','message':message})
    write_csv(DEST/'master_scopes.csv',scopes)
    final_alignment=next(v for v in scopes if v['unit'].startswith('barranco-alignment-campaign-'))
    final_dense=next(v for v in scopes if v['unit'].startswith('barranco-alignment-dense-export-'))
    final_sparse=next(v for v in scopes if v['unit'].startswith('barranco-alignment-sparse-preview-'))
    allocations=json.loads((CENTRAL/'assignments.json').read_text());download_status=json.loads((PROJECT/'.state/campaigns/barranco-full-v1/status.json').read_text())
    report={'kind':'retrospective_baseline_not_controlled_benchmark','created_at':datetime.now(UTC).isoformat(),
        'campaign_created_at':allocations['created_at'],'downloads_terminal_updated_at':download_status.get('updated_at'),
        'reconstruction_first_observed_at':first,'reconstruction_last_validated_at':last,'observed_reconstruction_span_s':last-first,
        'observed_campaign_to_final_export_s':state['updated_at']-allocations['created_at'],'final_export_at':state['updated_at'],
        'download_campaign_envelope_s':download_status['updated_at']-allocations['created_at'],
        'pre_reconstruction_after_downloads_s':first-download_status['updated_at'],
        'post_reconstruction_tail_to_export_s':state['updated_at']-last,
        'collection_envelopes_sum_s':sum(v['transfer_and_verify_envelope_s'] or 0 for v in collection_rows),
        'collected_product_bytes':sum(v['bytes'] for v in collection_rows),
        'mesh_seconds':None,'texture_seconds':None,
        'direct_base_stages_sum_s':sum(j['direct_base_stages_s'] for j in jobs),'dense_internal_success_sum_s':sum(j['dense_compute_fusion_s'] for j in jobs),
        'core_workload_lower_bound_sum_s':sum(costs),'ideal_parallel_core_lower_bound_s':max(costs),
        'direct_masking_sum_s':sum(r['seconds'] for r in stage_rows if r['stage']=='masks'),
        'direct_sfm_sum_s':sum(r['seconds'] for r in stage_rows if r['stage']=='sfm'),
        'native_dense_calls':sum(j['successful_dense_calls'] for j in jobs),'dense_camera_instances':sum(j['dense_camera_instances'] for j in jobs),
        'planned_dense_batches_once':sum(j['dense_batches_once'] for j in jobs),
        'duplicate_successful_dense_internal_s':sum(j['duplicate_successful_dense_internal_s'] for j in jobs),
        'final_alignment_scope_wall_s':final_alignment['wall_seconds'],'final_dense_export_scope_wall_s':final_dense['wall_seconds'],
        'final_sparse_export_scope_wall_s':final_sparse['wall_seconds'],
        'all_incremental_alignment_scopes_wall_sum_s':sum(v['wall_seconds'] for v in scopes if v['unit'].startswith('barranco-alignment-incremental-')),
        'registered_source_views':sum(j['registered'] for j in jobs),'known_attempts_max_concurrent':maximum,
        'max_concurrency_note':'Based on retained attempt intervals; early overwritten attempts are missing',
        'jobs':jobs,'counterfactuals':sim,'missing_or_qualified_data':notes,
        'limitations':['metrics.json omite la etapa densa personalizada por lotes: timings_total_seconds no es el total del pipeline.',
            'No se midieron SegFormer y SAM3 por separado; masks registra su duración combinada, incluida carga de modelos.',
            'Los contrafactuales cubren solo componentes observados: faltan partes de carga, normalización, ensamblaje, verificaciones, traslados y recuperación.',
            'Los timestamps UTC de fin de etapa tienen resolución de un segundo; el elapsed del timer está redondeado a 0,01 s.',
            'No se registraron offsets históricos de sincronización de relojes entre máquinas.',
            'Las fechas absolutas de dense.log son heurísticas HH:MM:SS + mtime UTC, no timestamps fechados por OpenMVS; las duraciones internas no dependen de esa inferencia.',
            'Los status sobrescriben intentos: faltan algunos detalles de los primeros intentos 025/005/009.',
            '007 reutiliza preparación de v1; la densa parcial descartada y el merger/BA son costes extra de recuperación.',
            'Se procesaron 15 bloques: pilotos y barreras retrasaron el lote principal; el pico observado fue 12 trabajos de hija, no 19.',
            'Se cambiaron cuotas de CPU, afinidad y potencia GPU: no es un benchmark uniforme a máxima potencia.',
            '023 reutilizó mapas de profundidad después de abortos; no está completamente medido su coste de densa desde caché fría.',
            'La carga útil selecciona el primer timer exitoso de cada lote; las repeticiones exitosas se contabilizan aparte.',
            'No se ejecutaron malla ni textura: sus tiempos son N/D, no cero. El producto medido aquí es nube, no malla texturizada.']}
    atomic_json(DEST/'report.json',report)
    lines=['# Tiempos de la campaña Barranco 4K — auditoría retrospectiva','',
        '**No es una medición controlada de «19 máquinas contra una».** Es la cronología real de una campaña con desarrollo, pilotos, límites y recuperaciones.','',
        '## Resultados principales','',
        f'- Origen de campaña: {iso(allocations["created_at"])}.',f'- Primera reconstrucción observada: {iso(first)}.',f'- Última reconstrucción validada: {iso(last)}.',
        f'- Ventana real de reconstrucción, incluyendo esperas/recuperaciones: **{hours(last-first)} h**.',
        f'- Campaña creada → exportaciones finales: **{hours(report["observed_campaign_to_final_export_s"])} h**.',
        f'- Suma de temporizadores principales conocidos: **{hours(sum(costs))} h** (cota parcial de carga, no tiempo secuencial real).',
        f'- Máximo de esa carga parcial por manzana: **{hours(max(costs))} h** (cota ideal para 15 o 19 nodos sin esperas).',
        f'- Segmentación combinada medida: {hours(report["direct_masking_sum_s"])} h-nodo; SfM: {hours(report["direct_sfm_sum_s"])} h-nodo.',
        f'- Descarga/configuración de la cola de entradas: {report["download_campaign_envelope_s"]/60:.2f} min; después hubo {report["pre_reconstruction_after_downloads_s"]/60:.2f} min hasta el inicio de la primera reconstrucción de videos completos (preparación, pruebas y piloto).',
        f'- Transferencia/verificación: suma de envolventes por directorio **{hours(report["collection_envelopes_sum_s"])} h**, {report["collected_product_bytes"]/1024**3:.2f} GiB de productos finales. Se solapa con el cómputo: no sumar ambos tiempos como si fueran fases seriales.',
        f'- Cola después de terminar la última reconstrucción hasta exportar: **{hours(report["post_reconstruction_tail_to_export_s"])} h**.',
        f'- Densificación: {report["planned_dense_batches_once"]} lotes únicos, {report["native_dense_calls"]} llamadas exitosas, {report["dense_camera_instances"]} instancias de cámara para {report["registered_source_views"]} vistas fuente registradas; timers internos útiles: **{hours(report["dense_internal_success_sum_s"])} h-nodo**. Repeticiones exitosas adicionales: {report["duplicate_successful_dense_internal_s"]:.3f} s.',
        f'- Alineación final con cachés: **{report["final_alignment_scope_wall_s"]:.3f} s**; no es una alineación desde cero.',
        f'- Scopes de alineación incremental: {report["all_incremental_alignment_scopes_wall_sum_s"]/60:.2f} min acumulados, ejecutados durante la recolección.',
        f'- Exportación densa global: **{report["final_dense_export_scope_wall_s"]:.3f} s**; sparse: **{report["final_sparse_export_scope_wall_s"]:.3f} s** (contabilidad systemd).',
        '', '## Etapas agregadas','',
        '| Etapa | Tiempo (h-nodo salvo indicación) | Evidencia |',
        '|---|---:|---|',
        *[f'| {name} | {hours(sum(r["seconds"] for r in stage_rows if r["stage"]==name))} | Temporizador de etapa |' for name in ['frames','telemetry','masks','sfm','undistort']],
        f'| Densa: cómputo/fusión internos | {hours(report["dense_internal_success_sum_s"])} | Primer éxito por lote; carga/ensamblaje incompletos |',
        '| SegFormer / SAM3 individualmente | N/D | Solo se registró masks combinado |',
        '| Malla / textura | N/D | Etapas no ejecutadas |',
        '', 'Los detalles SIFT/matching/mapper de stages.csv están contenidos en SfM; no volver a sumarlos.',
        '', '## Qué explica la duración real','',
        '1. Se preparó y depuró el sistema durante la campaña; los pilotos se ejecutaron antes de liberar las otras tareas.',
        '2. Hubo solo 15 tareas de manzana, y el pico real observado fue 12. La política no lanzó 19 tareas simultáneas.',
        '3. SfM incluye trabajo CPU de mapper/BA: GPU disponible no equivale a GPU ocupada durante toda la tarea.',
        '4. Los lotes densos repiten cámaras halo, normalizan y ensamblan PLY; la nube global duplica físicamente los puntos individuales en otro archivo.',
        '5. La maestra recibe a unos 9,6 MiB/s por su enlace de 100 Mbps. Centralizar ~209 GiB de productos consume horas aunque el cálculo ya haya terminado.',
        '6. Los límites térmicos, cambios de recursos y recuperaciones son costes reales de esta ejecución, no ventajas/desventajas intrínsecas de cualquier método sparse o dense.',
        '', '## Qué se puede afirmar','',
        f'Hay {hours(sum(costs))} h de componentes principales registrados. Su suma es una cota de trabajo secuencial bajo esos mismos costes, no una medición de ejecución secuencial completa. El máximo por tarea ({hours(max(costs))} h) es una cota parcial ideal en paralelo, no una promesa de terminar toda la entrega en ese tiempo.',
        'No se puede dar retrospectivamente un tiempo exacto de todo secuencial ni de 19 nodos a máxima potencia: esos experimentos no se ejecutaron. Para la tesis deben figurar como modelos/estimaciones, con condiciones y costes omitidos.',
        '', '## Por manzana','',
        '| Manzana | Frames | Segmentación (s) | SfM (s) | OpenMVS interno (s) | Carga principal parcial (h) |','|---|---:|---:|---:|---:|---:|']
    for j in jobs:
        stage={r['stage']:r['seconds'] for r in stage_rows if r['block']==j['block']}
        lines.append(f'| {j["block"]} | {j["frames"]} | {stage.get("masks","N/D")} | {stage.get("sfm","N/D")} | {j["dense_compute_fusion_s"]:.3f} | {hours(j["core_workload_lower_bound_s"])} |')
    lines+=['','## Contrafactual de cómputo principal','',
        'Mismos costes parciales medidos por tarea, máquinas independientes, sin red ni preparación. No ejecutar estos escenarios no permite llamarlos tiempos medidos.','',
        '| Máquinas | Simulación LPT (h) | Cota matemática (h) |','|---:|---:|---:|']
    for row in sim:lines.append(f'| {row["machines"]} | {hours(row["list_schedule_lpt_core_seconds"])} | {hours(row["mathematical_lower_bound_core_seconds"])} |')
    lines+=['','## Fuentes y limitaciones','']+['- '+v for v in report['limitations']]
    lines+=['','## Archivos','',
        '- `stages.csv`: temporizadores registrados y desglose SIFT/matcher/mapper. No sumar las filas sfm_detail otra vez sobre sfm.',
        '- `dense_batches.csv`: intentos OpenMVS, temporizador interno directo y rango de timestamps reconstruido.',
        '- `jobs.csv`: carga parcial, envolventes de ejecución, recuperación y muestreo GPU (no profiler).',
        '- `attempts.csv`: intervalos conservados de intentos, incluidos fallos.',
        '- `collections.csv`: envolvente de transferencia/verificación por metadatos del filesystem, incluye pausas y reintentos.',
        '- `counterfactuals.csv`: estimaciones, no ejecuciones experimentales.',
        '- `master_operations.json`: envolventes de operaciones; `master_scopes.csv`: tiempos completos contabilizados por systemd.',
        '- `evidence/`: metadatos originales de nodos y journal de scopes para auditoría.',
        '', 'Los tiempos absolutos están expresados en UTC. America/Lima = UTC−5.']
    (DEST/'REPORTE.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['jobs','counterfactuals','limitations']},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true');a=p.parse_args();main(a.refresh)
