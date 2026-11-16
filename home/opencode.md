# Barranco — relevo operativo actualizado, 16 noviembre 2026

> **Adenda15:51UTC:** usuario autorizó GLOMAP para020. InstaladoGLOMAP1.1.0CPU
> aislado en `/data/photogrammetry/runtime/glomap-1.1.0-020-20261116/env/`
> deL507_005. Nueva raíz `barranco-020-glomap-20261116/cuadra-020`,
> monitor **020 GLOMAP**; observado running/sfm, sinerror, reestimando poses
> desde una COPIA deBD020vocabloop2fps (sin repetir extracción/matching).
> Solo sparse. Ver crónica operativa15:51UTC; NO relanzar.
> 020vocabloop terminó pero conserva el corte548–549; ya en visor8790.
> Rescate019 porSim3 detenidosin candidata: centros casi colineales y
> transformaciones bidireccionales globalmente incompatibles; originales intactos.

> **Adenda posterior, 16-nov ~15:01 UTC:** se recogieron las sparse terminadas
> en `/data/barranco/review/catalog-20261116-134343/`, incluida **011**
> (2.091 vistas / 1.372.798 puntos), disponibles junto a variantes y anclas locales
> en **http://127.0.0.1:8790/**, servicio `barranco-sparse-catalog.service`.
> Los cortes 019/020 a10fps terminaron, mejoraron el corte investigado pero
> presentan regresiones; NO están aprobados.
> Usuario autorizó y se lanzó una nueva **020 a2fps con loop_detection=true**,
> vocabulario oficial32K, raíz `barranco-020-vocabloop-20261116/cuadra-020`
> en L507_005. Observado running/sfm, indexando imágenes, sin error.
> Monitor: **020 vocab loop**. No repetir lanzamiento. Leer detalles y recibos
> en `OPERACION-20261116-PREFLIGHT-DESCARGAS.md`, sección15:01UTC.
> Los estados del cuerpo siguiente corresponden al sondeo histórico09:51UTC.

Documento principal para continuar SIN la conversación anterior. Estado consultado
el **2026-11-16 a las 09:51:44 UTC**. Es una fotografía, no telemetría permanente.
Leer primero este archivo y luego los README e historiales indicados.
**Leer este relevo NO autoriza relanzar, recuperar, densificar ni modificar geometría.**

## 1. Objetivo, decisiones y límites

Estamos reconstruyendo manzanas de Barranco: revisar sparse, investigar cortes,
aprobar geometría y colocar manualmente bloques nuevos respecto de anclas fijas.
Después: densa de la revisión aprobada, ROI, malla, Blender editable y texturizado
fotográfico. No confundir cálculo terminado con geometría correcta.

- Español; explicar observaciones, incertidumbre y permisos sin prometer resultados.
- Los experimentos NUEVOS terminan después de SfM para revisión. Nada de densa,
  alineación, BA de producción, malla, textura o relleno automáticos.
- Una sola componente, muchos matches o un exit code cero NO validan una sparse.
- La densa no repara poses sparse erróneas. Más fps/video continuo no garantizan
  continuidad ni ausencia de huecos.
- Preservar originales, máscaras, BD/features, matrices, recibos, hashes, revisiones
  y trabajo manual. Nunca sobrescribir un `.blend` editado por el usuario.
- Descargas/procesamiento pesado en `/data` de las hijas, no en `/`.
- Preservar TODO lo relacionado con `thesis`, tesis y `tesis_cava`.
- Permisos históricos de limpieza, potencia o energía fueron acotados: no son
  autorización permanente. No apagar/reiniciar/bloquear/cerrar sesiones sin permiso
  explícito. La maestra nunca es objetivo de energía.
- Guardas GPU intactas: ≥80 °C sostenidos 30 s; ≥85 °C inmediato. NO subir a 90 °C.
- No leer/publicar credenciales ni entornos secretos. Transporte existente las carga.
- No revertir cambios ajenos, resetear estados ni limpiar para obtener un Git limpio.

## 2. Fuentes de verdad y documentación preservada

| Ruta | Función |
|---|---|
| `/home/exitoso/home/opencode.md` | Relevo principal vigente |
| `/home/exitoso/home/OPERACION-20261116-PREFLIGHT-DESCARGAS.md` | Crónica detallada de preparación, campañas, cortes y recuperación |
| `/home/exitoso/home/opencode-historial-20261116-antes-relevo-095346.md` | Copia íntegra previa a esta reescritura; detalles implementación, pruebas y experimentos antiguos |
| `/home/exitoso/home/OPERACION-20261115.md` | Montajes, preservación, limpieza y parque |
| `/home/exitoso/home/opencode-historial-20261114.md` | Entrega anterior, visibilidad/Delaunay y texturizado |
| `/home/exitoso/home/opencode-historial-previo-20261112.md` | Historia más antigua |
| `/home/exitoso/home/DECISIONES-MALLA-BARRANCO.md` | Reparación manual y reproyección |
| `/home/exitoso/home/barranco-roi/README.md` | Uso, API, arranque, cachés, límites y pruebas de ROI/alineación |
| `/home/exitoso/home/sparse-review/README.md` | Visores y selección de cámaras A/B |
| `/data/repos/Alineacion-point-cloud/docs/manual-alignment.md` | Motor manual multiancla |
| `/home/exitoso/lab-deploy/.state/campaigns/` | Asignaciones, bundles congelados y recibos |
| `/data/barranco/active/manifest.json` | 14 anclas originales, matrices, fuentes y origen |

La crónica tiene secciones inversamente cronológicas y estados históricos.
Si hay contradicción temporal, manda la observación nueva verificada, no una frase
antigua como «no recuperada» o «8783 muestra 020».
Se preservó el sondeo completo en:
`/home/exitoso/lab-deploy/.state/campaigns/barranco-running-20261116/handoff-status-20261116-095144Z.json`.

## 3. Qué se preparó y lanzó el 16-nov

Se inventarió Drive `PRIVATE_DRIVE_ID`.
Descargas **completas y verificadas**: 25 archivos, 42.359.446.371 bytes:
17 MP4, siete SRT y un PNG. Se excluyeron `old` y proxies LRF.
Son DIEZ carpetas `_running`, no nueve. 016 y 023 son una captura nueva conjunta;
NO rehabilitan la vieja 023 rechazada.

Se prepararon diez hijas; Docker/containerd iniciados, sin habilitar arranque
automático; imágenes certificadas identificadas por ID y pruebas básicas CUDA
COLMAP/PyTorch verificadas. Se limpiaron únicamente cachés/descargas autorizadas:
L507_004 recuperó 63,159 GiB; L507_007 sigue ajustada de raíz (~5,27 GiB libres
en el sondeo). Proyectos y entornos de tesis preservados.

L507_015: se corrigió incompatibilidad fwupd actualizando daemon a 2.0.20 e
instalando `libfwupd3` compatible; servicio activo y `dpkg --audit` limpio.
No se flasheó firmware ni reinició.

Perfil baseline de vídeo único: resolución nativa, **2 fps, sequential overlap=20,
quadratic_overlap=0**, más candidatos acotados inicio/final verificados
geométricamente. Máscaras SegFormer + SAM3: personas/riders, postes y cables;
**no vehículos ni cielo**. Ver configs congeladas, no reconstruirlas de memoria.

Se lanzaron diez sparse-only, incluida 016-023 terrestre por separado.
Tras fallos térmicos a 145 W, el usuario autorizó **100 W en las diez hijas**:
nueve recuperaciones desde máscaras, archivando parciales y fallos en
`attempt-history/`; 011 siguió sin duplicar el worker activo. La etapa masks
reconstruye su directorio, por eso fue imprescindible archivar.
Guardas sin cambios. Potencia verificada, NO persistida tras reinicio.
Recibos: `power-100w.json`, `recovery-100w-launch.json` y los bundles de campaña.

## 4. Estado real del sondeo y mapa de asignaciones

Raíz local baseline:
`/home/exitoso/lab-deploy/.state/campaigns/barranco-running-20261116/`.
Raíz remota normal:
`/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-<bloque>`.

| Bloque | Hija | Estado al sondeo |
|---|---|---|
| 010 | L507_007 | running / sfm, worker vivo |
| 011 | L507_015 | running / sfm, worker vivo |
| 014 | L507_021 | running / sfm, worker vivo |
| 015 | L507_009 | running / sfm, worker vivo |
| 019 | L507_004 | awaiting_review; 1.104 vistas, 654.330 puntos, componente 0 |
| 020 | L507_005 | awaiting_review; 970 vistas, 562.041 puntos, componente 0 |
| 021 | L507_002 | awaiting_review; 884 vistas, 526.355 puntos, componente 0 |
| 022 | L507_011 | running / sfm, worker vivo |
| 016-023 | L507_022 | running / sfm, worker vivo |
| 027 | L507_008 | running / sfm, worker vivo |
| 006 multivídeo | L507_006 | running / sfm, worker vivo |
| 026 parque | L507_019 | awaiting_review / dense_complete; 1.577 vistas |
| 006 horizontal original con máscaras | L507_010 | failed / masks; histórico `SAFETY STOP: sustained gpu_c=82.00` |
| 006 horizontal sin máscaras | L507_010 | running / sfm, worker vivo, 100 W |
| 019 corte 10fps | L507_004 | running / extra_masks, worker vivo, 100 W |
| 020 corte 10fps | L507_005 | running / sfm, worker vivo, 100 W |

Ninguna otra fila reportaba error en ese sondeo. Conteos nulos en trabajos activos
no significan cero cámaras: aún no hay resumen final.
La temperatura actual de una hija puede pertenecer al ensayo de corte, no al
baseline terminado. Una GPU fría no borra un fallo térmico histórico.

016-023: paquete descargado `cuadra-016-023`; trabajo terrestre
`cuadra-016-023-terrestrial`. Plan acordado: revisar primero terrestre, luego
incorporar incrementalmente siete clips DJI con intrínsecos separados y matching
entre vídeos. **DJI todavía NO incorporado**.

## 5. Cortes 019 y 020: diagnóstico y variantes

Se recogieron SOLO sparse/metadatos originales 019/020/021 con SHA256 verificado:
`/data/barranco/review/barranco-running-20261116/{019,020,021}-seq20-loop/`.
Recibos `sparse-*-manifest.json`, `sparse-*-collected.json`.

### 020

Usuario marcó A=549/550, B=547/548. Corte 548–549:
1.021 inliers en BD y salto de centros ~36,58 veces la mediana vecina.
Frames seleccionados verificados en tiempos de salida 273,0–274,5 s.
Ensayo independiente en L507_005:
`/data/photogrammetry/campaigns/barranco-020-cut10fps-20261116/cuadra-020`.
Intervalo **[268,280) s**, 2 fps fuera y 10 fps dentro:
970−24+120 = **1.066 frames esperados**, no cámaras registradas garantizadas.

Falló `merge_frames` con `OSError: [Errno 18] Invalid cross-device link`:
hardlink entre bind mounts. Con autorización se corrigió:
hardlink cuando posible; SOLO ante EXDEV, copia temporal en destino, SHA256,
publicación sin sobrescritura; archivo existente solo reutilizable con hash igual.
Otros errores no se ocultan. Se archivaron helper/spec/estado/logs en
`attempt-history/<timestamp>-before-exdev-fix/`, con `execution_amendment`.
Se reanudó SOLO merge/SfM, sin repetir frames ni máscaras. Merge terminó.
Recibos `repair-exdev-bindings.json`, `recovery-exdev-launch.json`;
remoto `recovery-exdev.json`. NO repetir recuperación por leer esto.

### 019

Usuario marcó A=829, B=828. Salto 1,37292 unidades SfM locales frente a mediana
0,03598 (**38,16×**); giro **22,41°**. 430 inliers BD, pero **cero puntos 3D
compartidos entre estas dos vistas en la sparse final**. No se identificó qué
criterio descartó cada observación. Frames muestran fachada y árbol cercano.

Matches verificados de un par no garantizan triangulación: intervienen paralaje,
poses, profundidad positiva, error de reproyección y tracks multivista coherentes.
Un par temporal ya emparejado no se arregla simplemente «activando loop closure».
El cierre de vuelta conecta revisitas; no es una orden de pegar geometrías.

Usuario autorizó ensayo independiente en L507_004:
`/data/photogrammetry/campaigns/barranco-019-cut10fps-20261116/cuadra-019`.
Intervalo **[408,420) s (06:48–07:00)**:
1.104−24+120 = **1.200 frames esperados**.
Timing verificado y extra_frames terminado; al sondeo generaba extra_masks.

### Contrato compartido de los ensayos

Originales y visores permanecen intactos. Máscaras fuera del intervalo reutilizadas;
nuevas con misma política dentro. Fuente montada RO. Sin bajar criterios
geométricos. Ventana temporal 10 s y candidatos acotados de cierre; 4 CPU/40 GiB,
100 W y guardas intactas; terminan después de SfM.
Helpers conservan nombres `cut020_worker.py`, `cut020_steps.py`, pero ahora son
parametrizados para 019/020. Cada ejecución tiene snapshot inmutable y hashes:
los cambios locales para 019 NO modificaron el 020 que ya corría.
Estados locales: `.state/campaigns/barranco-{019,020}-cut10fps-20261116/`.
Seis tests locales del helper aprobados, incluidos EXDEV y continuidad 019.
**Ninguna corrección geométrica ha sido demostrada todavía**.
No comparar IDs directamente: variantes renombraron frames/IDs; usar tiempos
y procedencia del merge para localizar equivalentes.

## 6. Experimentos anteriores que hay que conservar

### 006 multivídeo — L507_006

Raíz `barranco-inputs-20261115/cuadra-006-14nov`;
experimento `phone_native_2fps_14nov_review_v1`.
Dos vídeos efectivos: `manzana_06.mp4` y `VID20261114142304.mp4`.
No confundir con antigua 006-all de tres vídeos descartada.
Matching exhaustivo. Última inspección detallada vio 3.794 imágenes totales,
contador provisional 2.667 y global BA largo, ~seis núcleos CPU, GPU 0%, 38 °C:
NO es conteo final ni ETA. **Esta campaña legacy sí puede seguir a undistort,
densa y métricas**, a diferencia de las nuevas sparse-only.

### 026 parque — L507_019

Raíz `barranco-inputs-20261115/cuadra-026-all`;
experimento `phone_native_2fps_all_review_v1`.
Densa terminada, sin aprobación automática. Sparse 1.577 cámaras /751.619 puntos;
local `/data/barranco/review/barranco-inputs-20261115/026-all/`.
Densa sigue en hija. Último registro local no tenía fotos/BD SIFT adjuntas.
Recuperación previa de OOM 40 GiB al remapear máscaras: caché acotada a DOS mapas,
sin alterar proyección/muestreo ni checkout certificado. Overlay por corrida,
`park_memory_recovery.py`, `mask_geometry_bounded.py`, `pipeline_bounded.py`,
`park_recovery_worker.py`, `mask-memory-patch.json`; sys.path del wrapper corregido,
reanudar desde undistort. No repetir.
Tiempos medidos: frames71,75 s, masks3861,57 s, SfM20121,31 s,
undistort recuperado521,80 s; duración densa final no consultada.

### 006 vertical original y reconectada — L507_010

Original `barranco-single006-sequential-20261115/cuadra-006`:
`VID20261114142304.mp4`, 1920×1080 codificado, display90°, ~17m44s.
2 fps, 2.129 frames, seis componentes. Mejor modelo2:1.119 vistas/363.246 puntos.
Densa original63.063.293 puntos/28 lotes; no transferir sin necesidad.
Local `.../barranco-inputs-20261115/006-single14nov-sequential/`.

Reconectada `barranco-006-bridges-20261115/cuadra-006`,
experimento `colmap_bridge_recovery_v1`:33.057 pares candidatos sobre BD COPIADA.
Poses de1.119 originales fijas, intrínsecos fijos; retriangulación/BA.
Salida plana confundió wrapper: recibo `failed: No derived model published`,
pero los binarios existen:2.129 vistas únicas/679.516 puntos/un componente de tracks.
Mediana error0,994px, p95 2,006px, track medio4,37 NO validan geometría.
Usuario la vio rara: **NO aprobada**, no densa nueva.
Local `.../barranco-inputs-20261115/006-bridges-corrected/`;
herramientas `reconnect006_worker.py`, `start_reconnect006.py`.

### 006 horizontal y variante sin máscaras — L507_010

Vídeo confirmado `manzana_06.mp4`,3840×2160,sin rotación,
832,246767s,5.213.649.878 bytes. Original reutilizado/verificado, no redescargado.
Intento con máscaras:
`barranco-006-horizontal-20261115/cuadra-006`;
experimento `phone_native_2fps_horizontal_sequential_review_v1`.
2fps,overlap10,sin loop detection; falló máscaras a145W y queda preservado.
Lanzador `start_horizontal006.py` rechaza raíces existentes; NO sirve como resume.

Usuario pidió variante independiente SIN máscaras:
`barranco-006-horizontal-nomasks-20261116/cuadra-006`,
1.665 frames reutilizados y mismo sequential overlap10.
Tras fallo térmico a145W, autorizó100W también en esta hija; SfM parcial archivado
y reiniciado. Estado actual running/sfm a100W, no el viejo masks fallido.
Worker `sparse_nomasks_worker.py`. Sparse-only; no afecta006 multivídeo.

Todas las raíces relativas de esta sección cuelgan de
`/data/photogrammetry/campaigns/` en la hija indicada.

## 7. Visores activos, puertos y uso

Seis servicios de usuario activos comprobados:

| URL local | Servicio | Contenido |
|---|---|---|
| http://127.0.0.1:8765/ | barranco-roi.service | ROI y alineación manual |
| http://127.0.0.1:8780/ | barranco-sparse-review.service | 006 vertical original |
| http://127.0.0.1:8781/ | barranco-sparse-parque.service | 026 |
| http://127.0.0.1:8782/ | barranco-sparse-006-corrected.service | 006 cuestionada |
| http://127.0.0.1:8783/ | barranco-sparse-019.service | **019 original** |
| http://127.0.0.1:8784/ | barranco-sparse-021.service | 021 original |

8783 mostraba020; usuario pidió sustituir SOLO ese visor por019. Se detuvo
`barranco-sparse-020.service`, NO la corrección020 ni se borraron sus datos.
Comprobar título y dataset; Ctrl+F5 si pestaña antigua.

Visores878x solo lectura: arrastrar gira, rueda zoom, Mayús+arrastrar desplaza.
Se añadió selección A/B de cámaras, etiquetas proyectadas, búsqueda por ID/nombre,
modo solo cámaras, copia de reporte y exportación JSON. Marcas en localStorage
por dataset/componente; no editan la geometría ni son revisiones servidor.
ID de cámara seleccionado significa **image_id/vista**, no camera_id de intrínsecos.
Selección probada con Chrome aislado y tres tests del lector aprobados.

Servicios transitorios, no habilitados para arranque automático. Verificar `/data`,
puertos y servicio existente ANTES de cualquier inicio autorizado; no reemplazar
un visor por asumir que un puerto identifica siempre una manzana.
ROI usa alignment313 y4GiB/swap0/CPUQuota200%; visores nuevos1GiB/swap0/CPU200%.
Consultar con `systemctl --user status <servicio>` y
`systemctl --user list-units 'barranco-*' --all --no-pager`.
Arranques completos en README: NO ejecutarlos como prueba al leer el relevo.

## 8. Alineación/ROI ya implementados y trabajo manual protegido

Anclas fijas: **001,002,003,004,005,007,008,009,012,013,017,018,024,025**.
Vieja023 rechazada, no activa. No recalcular sus14 matrices ni usar solver global
antiguo para moverlas.

026 tiene colocación manual adicional, NO validación automática:

- placement `p-84283c9c41e649a5a40527507a6cc7d2`
- sesión `s-5552ad723cbb47d0afc56a4a0c2eb7d6`
- reconstrucción `r-f41283acbb57cb5484a01462`
- estado `manual_unvalidated`, `job_id=null`.

Preservar matriz exacta y procedencia en
`/home/exitoso/home/barranco-roi/state/alignment/`:
anchors,reconstructions,sessions,jobs,placements.
La app podía mostrar15 referencias por026, NO por rehabilitar023.
Última consulta anterior: cero trabajos de alineación de producción desde la web.
No reemplazar estados reales con fixtures de pruebas.
ROI históricos: `state/selections/`, `state/blocks/<id>/selections/`;
exports `state/exports/roi_<id>.json`; claves nuevas `p-*` evitan sobrescrituras.

Convención **EPSG:32718**, origen
`[279932.4471962734,8657453.760760272,116.53700000000002]`;
vectores columna `p_world=T_world_from_local@p_local`.
No confundir UTM absoluto y relativo, ni aplicar T dos veces.
Referencia visual `/data/barranco/reference/mapa_provisional.png`.

### Uso acordado de la app

Elegir bloque pendiente y SOLO vecinas explícitas. Colocar con traslado,
rotacionesXYZ y escala uniforme; seleccionar M vistas nuevas para localizar en
anclas y opcionalmente N de anclas para localizar en nuevo. Resolver una Sim(3)
con referencias fijas, matching/PnP, validación reservada y BA restringido opcional.
Aprobar explícitamente colocación antes de ROI. No inventar ubicación del parque.

Interfaz minimalista negra/blanca sin logo/azul; RGB de nube conservado.
Canvas protagonista, paneles flotantes plegables, nada preseleccionado al recargar.
G/R/S y ejes/sliders; Esc retira selección visual sin borrar M/N ni revisión.
Guardar revisión antes de Ctrl+F5. Borrador navegador ≠ revisión servidor.

### Implementación existente (no rehacer desde cero)

En `home/barranco-roi`: `app.py` rutas/API/POST protegidos/health ligero;
`roi/alignment.py` catálogo,sesiones,pares,cachés,jobs/aprobación;
`roi/catalog.py` paquete activo yRGB; `roi/core.py` identidad sparse/T/origen;
`roi/service.py` selector sparse-only; `roi/multi.py` aislamiento;
`alignment_worker.py` trabajo fuera HTTP con snapshot,cgroup,thermal guard y
validación; `source_fetch.py` transferencia EXPLÍCITA RO de fotos/features,
identidad/hash yreserva50GiB (no automáticamente sobre026).
Frontend `web/{app.js,align.js,align.css,cloud-cache.js,cloud-renderer.js}`.
Detalles archivo por archivo en historial preservado sección7 y README.

BlockAlign en `/data/repos/Alineacion-point-cloud/`:
`src/blockalign/manual.py` solver robusto7DoF sinGPS, soportes multiancla,
forward/reverse, degeneración/validación y BA restringido:
solo poses/puntos nuevos variables, intrínsecos/anclas fijos y vistas reservadas
excluidas. `colmap_adapter.py` BD3.13 nueva con namespaces y endpoints elegidos;
`src/alignexp/binary.py` modelos estándar COLMAP ampliados.
No confundir esta ruta con antiguo `graph.solve()` o BA pairwise.
Matching/BA numérico probado en escenas sintéticas, no validado en producción web.

Caché visual RAM/IndexedDB24entradas/64MiB; WebGL residente/Canvas fallback;
paquetes XYZFloat32 relativos a origenFloat64+RGBA16bytes/punto,ETag.
Hasta80.000puntos/nube PARA DIBUJAR: ROI/matching usan originales completos.
Mover nube cambia uniforms, no geometría científica. ROI carga perezosa.
No borrar funciones PLY legacy utilizadas por batch.

## 9. Runtime, pruebas y control de versiones

Pipeline hijas usa entorno certificado; conservar IDs/hashes de imágenes.
Se instaló PyCOLMAP3.11.1 separado en `/data/barranco/runtime/alignment311/`
para inspección. Aplicación/alineador siguen en
`/data/barranco/runtime/alignment313/` (PyCOLMAP/COLMAP3.13).
**Migración completa NO realizada**:12/44tests de app fallaron con3.11.1 por
ausencia de `pycolmap.Rig`. No cambiar runtime del servicio sin adaptar y validar.

Pruebas registradas, no ejecutadas de nuevo solo por escribir este relevo:
44unittest app y44pytest motor aprobados en integración3.13 anterior;
Chrome WebGL/Canvas, gestos,pivote,caché,ROI aprobados.
Últimos tests nuevos:3lector sparse,3monitor,6cut helper aprobados;
selección cámara verificada en Chrome aislado.
Comandos de prueba de app/motor y browser en README/historial.
No extrapolar resultados sintéticos a geometría real.

No commits ni pushes hechos en esta sesión. Git de `/home/exitoso` ignora
`/home/*` mediante `/*`: status limpio NO prueba que app/documentos estén versionados.
Inspeccionar también repo externo; conservar modificaciones locales.

## 10. Consulta segura, logs, identidad y herramientas

Desde `/home/exitoso`, comandos de estado añadidos a petición del usuario:

```bash
make barranco-status
make pipeline-status
make barranco-status-json
```

Son consulta, NO colección/reinicio/retry. Incluyen campañas nuevas,legacy y cortes,
worker/etapa/error/tiempo/disco raíz y temperatura/potencia EN VIVO.
`pipeline-status` es alias. Implementación `lab-deploy/tools/barranco_status.py`.
Leer Makefile antes de adaptar; no ampliar efectos laterales del monitor.
Para inventario general cargar skill `l507-readonly` y usar su flujo autorizado.

Estado remoto real `<work_root>/reconstruction-full-status.json`;
logs `<work_root>/logs/reconstruction/full/`, `sparse-worker.log`;
outputs/metrics, `.stages/`,config y`reconstruction.json`.
Estados locales son cachés/recibos y pueden envejecer.
`tools/review_experiments.py` CLI **recoge sparse automáticamente**:
NO usarla creyendo que solo consulta; preferir monitor o inspección controlada.

Herramientas durables `lab-deploy/tools/`:
`sparse_review_worker.py`,`sparse_loop_overlay.py`,`sparse_nomasks_worker.py`,
`cut020_worker.py`,`cut020_steps.py`,`barranco_status.py`.
Helpers temporales `/tmp/opencode/barranco_*.py` incluyen transporte,bootstrap,
consulta,colección,potencia yrecuperación. **NO ejecutar scripts start/resume/recover
solo porque existen**. Leer su fuente y recibos, confirmar alcance con usuario.
Para adaptar una futura operación: verificar tag+MAC,host key,/data,espacio,
worker/contenedores/locks,potencia,hash de fuente y bundle; crear variante aislada,
snapshot/recibo,guardar historial y verificar resultado. No sobrescribir raíces.
La recuperación EXDEV no es un comando universal de reanudación.

IPs observadas, DHCP y NO identidad permanente (prefijo10.100.41):
002=.54,004=.44,005=.103,006=.64,007=.71,008=.77,009=.78,
010=.100,011=.65,015=.61,019=.63,021=.80,022=.101.
Host keys confiables cubren aliases005 antigua.58,010 antigua.66,022 antigua.67.
Nunca desactivar StrictHostKeyChecking para resolver un cambio deIP.
L507_023/024 históricamente raíz llena y tormentas rsyslog/journald:
excluidas de trabajos nuevos, NO reparadas.
Montajes ext4/data estandarizados en20máquinas, NO persistidos enfstab:
verificar tras reinicios. Docker y servicios tampoco garantizados tras reinicio.

## 11. Preservación histórica y productos existentes

Limpieza anterior autorizada y auditada:
`/data/barranco/active/cleanup-1794729639320349624.json`:
1.221archivos enumerados/~312,395GiB lógicos, nube global obsoleta,
copias centrales dense_scalar y multimedia de campaña vieja. No repetir.
Antes se preservaron sparse,matrices,escenasOpenMVS y5.223imágenes rectificadas
de14aceptadas con hashes/hardlinks. Mallas/Blender,features/BD yfuentes conservadas.
Antigua006-all tiene discard-receipt propio; vídeos preservados.
Retirada de preview/export densa de UI NO borró densas remotas.

Entrega histórica:
`/home/exitoso/home/barranco-roi/exports/mesh-campaign-20261112/simplified_70pct_blocks/`,
`barranco_15_manzanas_70pct.blend`:15objetos/15datablocks independientes.
No equivale a15anclas aceptadas. Preservar `.blend`,meshes,`.mlp`,
`delivery.json`,`blender-audit.json` yediciones posteriores.

## 12. Plan vigente y siguiente paso

1. Consultar estado sin relanzar. Esperar SfM de ensayos019/020.
2. Recoger SOLO variantes terminadas de forma explícita/verificada cuando proceda;
   abrir visores sin reemplazar puertos ajenos. Mantener originales comparables.
3. Comparar tiempos equivalentes,centros,giro,tracks compartidos,error ycontinuidad
   local/global; inspección visual del usuario. Más cámaras no bastan para aprobar.
4. Si siguen mal, diagnosticar causas y proponer otro ensayo acotado; no forzar
   conexiones ni rellenar geometría automáticamente.
5. Revisar demás sparse,006horizontal,006multivídeo,026 y006reconectada;
   prioridades a decidir con usuario. 016-023: revisar terrestre antes de DJI.
6. Aprobar sparse exacta. Alinear manualmente sin mover14anclas,guardar Sim(3)
   en maestra. Si BA cambia geometría interna,revisar/regenerar derivados.
7. Densificar SOLO revisión aprobada con permiso. Mantener dense/cámaras locales
   yT de colocación separada; Sim(3) pura puede reutilizar densa con linaje verificado.
8. ROI: probar TODOS los puntos3D transformados contra polígono world, no solo
   subconjunto visual ni coordenadas sin transformar.
9. Malla futura: preservar visibilidad nativa y relación cámara/punto para
   OpenMVS Delaunay; seguir documentos de decisiones, no inventar pipeline nuevo.
10. Blender editable con bloques independientes. Reparación de huecos MANUAL,
    únicamente aprobada por usuario; nunca auto-hole-filling.
11. Texturizado fotográfico sigue como piloto pendiente, NO producción validada:
    necesita fotos+intrínsecos/extrínsecos calibrados correctos, NO solo `.mvs`.
    Posible llevar malla editada de vuelta al marco de cámaras, reproyectar por
    bloque y devolverla al global. Superficies reparadas nunca observadas NO
    pueden recuperar textura auténtica inexistente. Rectificar lente ≠ alinear.

Al comenzar otro chat: resumir estados actualizados,problemas,bloqueos yplan;
preguntar qué atender y esperar instrucciones. La solicitud actual solo autorizó
documentación/inspección, no otro lanzamiento,limpieza,producto ni cambio geométrico.
