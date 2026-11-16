# Continuidad OpenCode — Barranco / estado al cierre del 15-nov-2026

> **Adenda 16-nov-2026:** leer también
> `/home/exitoso/home/OPERACION-20261116-PREFLIGHT-DESCARGAS.md`.
> Se prepararon diez hijas y se iniciaron descargas directas a `/data` de las
> diez carpetas `_running`, campaña `barranco-running-20261116`.
> Actualización posterior: el usuario autorizó y se iniciaron nueve SfM sparse-only
> de vídeos únicos, seq20 + candidatos de cierre; 016-023 quedó aparte.
> Consultar la adenda y `sparse-launch.json`; no repetir lanzamientos.
> Posteriormente se lanzó SOLO la base terrestre 016-023 en L507_022
> (`cuadra-016-023-terrestrial`). Siete bloques nuevos se pararon térmicamente
> durante máscaras; no se reanudaron. Consultar **`make barranco-status`**
> desde `/home/exitoso`; incluye fallos y temperaturas actuales, sin relanzar nada.
> Recuperación posterior AUTORIZADA por el usuario: diez hijas nuevas limitadas
> a 100 W, nueve corridas reanudadas desde máscaras con parciales archivados,
> y 011 continuada sin duplicación. Guardas térmicas sin cambios. Ver recibos
> `power-100w.json` / `recovery-100w-launch.json`; no repetir la recuperación.
> Nueva petición posterior: 006 horizontal SIN máscaras, SOLO SfM, en L507_010,
> corrida separada `barranco-006-horizontal-nomasks-20261116`; se reutilizaron
> 1.665 frames y se conservó la original. Ver fila `006 horiz s/m` del monitor.
> 020 y 021 terminaron SfM, se recogieron sparse con hashes y se publicaron visores:
> http://127.0.0.1:8783/ (020: 970 vistas/562.041 puntos),
> http://127.0.0.1:8784/ (021: 884 vistas/526.355 puntos).
> Solo revisión, sin aprobación ni alineación automática.
> El usuario ve bien 021 y cuestiona un corte en 020. Se añadió marcado A/B
> de cámaras al visor sparse (Ctrl+F5 en 8783), con IDs/nombres y exportación
> local. No se modificó ni recuperó todavía la geometría de 020.
> Petición posterior autorizada: prueba derivada `barranco-020-cut10fps-20261116`
> en L507_005, 10 fps solo 04:28–04:40 y 2 fps fuera, máscaras nuevas solo para
> ese tramo y SfM nuevo. Original 020 intacta. Par 548–549 tenía 1.021 inliers
> pero salto de centros ~36,6× la mediana vecina. Ver adenda; NO declarar reparada.
> Monitor: `020 corte 10fps`.
> La prueba 020 falló en merge_frames por hardlinks entre bind mounts (EXDEV).
> Se corrigió con copia verificada y reanudó SOLO merge/SfM tras autorización;
> frames/máscaras previos conservados. Ver `recovery-exdev-launch.json`; no repetir.
> ÚLTIMO cambio de visor: a petición del usuario, **8783 ahora muestra 019**
> (1.104 vistas / 654.330 puntos). Se detuvo solo el visor 020, no su corrección.
> Original 020 conservada; 021 sigue en 8784. Consultar adenda para URLs vigentes.
> El usuario marcó corte 828–829 en 019 y autorizó otra prueba local10fps:
> `barranco-019-cut10fps-20261116` en L507_004, intervalo06:48–07:00, a100W.
> Original019/visor8783 intactos. Monitor: `019 corte 10fps`; no relanzar.
> PyCOLMAP 3.11.1 instalado aparte en la maestra; app/alineación continúa en 3.13
> por incompatibilidad comprobada de Rig. Las anclas y colocación 026 se preservan.

**Documento principal de relevo. Actualización: 2026-11-15, ~23:17, UTC−05:00.**
Los timestamps Unix y logs de las hijas pueden mostrar ya 16/nov en UTC.
Hablar con el usuario en español, concreto, sin afirmar éxito geométrico por un
simple exit code o conteo de imágenes. No repetir reconstrucciones ni lanzar
trabajos solo por leer este documento.

## 1. Leer primero: situación y objetivo

En esta sesión se pasó de investigar el alineador a **implementar y desplegar
una aplicación integrada de ROI sparse y alineación manual multiancla**.
Después se optimizó y rediseñó dos veces según las observaciones del usuario.
La última interfaz ya está publicada, probada y activa.

El usuario quiere:

- Seleccionar una reconstrucción pendiente y SOLO sus manzanas adyacentes.
- Colocarla manualmente con arrastre, rotación XYZ y escala uniforme.
- Elegir M vistas del bloque nuevo para localizarlas en una ancla; opcionalmente
  N vistas de la ancla para localizarlas en el nuevo.
- Usar varias referencias fijas para una única Sim(3), con matching/PnP,
  validación reservada y BA restringido opcional.
- Aprobar explícitamente la colocación y luego delimitar el ROI.
- Interfaz funcional, minimalista, **negra/blanca, sin logo ni acentos azules**;
  los colores originales de las nubes sí se conservan.
- Visor protagonista; controles flotantes plegables, animaciones discretas,
  movimiento fluido, caché y ninguna manzana preseleccionada al recargar.

**Objetivos operativos pendientes:**

1. Mantener/probar la interfaz con el usuario sin alterar geometría o revisiones.
2. Investigar y proponer una recuperación térmicamente segura de la nueva
   006 horizontal, actualmente detenida en máscaras. **No se reanudó ni se
   relajó la protección térmica. Pedir autorización para cualquier nueva
   operación o cambio de potencia/configuración que no esté confirmado.**
3. Seguir el estado del experimento de varios vídeos de 006 en L507_006.
4. Revisar visualmente la 026 ya densificada y la geometría problemática de la
   006 corregida; no aprobarlas automáticamente.
5. El texturizado fotográfico de mallas reparadas manualmente sigue pendiente.
   No ejecutar mallado, relleno de huecos ni texturizado sin aprobación.

## 2. Fuentes de verdad y rutas

| Ruta | Uso |
|---|---|
| `/home/exitoso/home/opencode.md` | Este relevo: tiene precedencia |
| `/home/exitoso/home/OPERACION-20261115.md` | Montajes, preservación, limpieza, lanzamientos y recuperación del parque; sus pendientes de editor ya están superados |
| `/home/exitoso/home/opencode-historial-20261114.md` | Documento anterior preservado; historia de entrega y plan de texturizado |
| `/home/exitoso/home/opencode-historial-previo-20261112.md` | Historia más antigua |
| `/home/exitoso/home/DECISIONES-MALLA-BARRANCO.md` | Reparación manual de huecos y reproyección fotográfica posterior |
| `/home/exitoso/home/barranco-roi/` | Aplicación integrada, scripts y pruebas |
| `/home/exitoso/home/barranco-roi/README.md` | Arranque, uso, cachés, límites, contratos y pruebas actuales |
| `/home/exitoso/home/sparse-review/` | Visores 3D independientes, solo lectura |
| `/data/repos/Alineacion-point-cloud/` | Repositorio del motor BlockAlign |
| `/data/repos/Alineacion-point-cloud/docs/manual-alignment.md` | Nueva API numérica manual sin GPS |
| `/home/exitoso/lab-deploy/tools/` | Lanzadores, recuperación y supervisión |
| `/home/exitoso/lab-deploy/.state/campaigns/` | Asignaciones, recibos de lanzamiento y estados locales |
| `/data/barranco/active/manifest.json` | Paquete aceptado original: 14 anclas, matrices, fuentes y origen |
| `/data/barranco/review/barranco-inputs-20261115/` | Sparse recogidas de experimentos; NO todas están aprobadas |
| `/data/barranco/alignment-inputs/` | Snapshots de imágenes/features/modelos compatibles |
| `/data/barranco/runtime/alignment313/` | Python, COLMAP y PyCOLMAP 3.13.0, NumPy/SciPy/Shapely/PIL |
| `/data/barranco/reference/mapa_provisional.png` | Guía de ubicaciones; no inventar la ubicación del parque |

Origen `map_world`:
`[279932.4471962734, 8657453.760760272, 116.53700000000002]`.
CRS EPSG:32718; matrices columna: `p_world = T_world_from_local @ p_local`.
No confundir coordenadas relativas al origen con UTM absoluto; no aplicar T dos veces.

## 3. Aplicaciones activas en la maestra

Se comprobaron activas al cierre:

| URL local | Servicio systemd de usuario | Contenido |
|---|---|---|
| `http://127.0.0.1:8765/` | `barranco-roi.service` | ROI + alineación manual, interfaz nueva |
| `http://127.0.0.1:8780/` | `barranco-sparse-review.service` | 006 original de un vídeo, seis componentes |
| `http://127.0.0.1:8781/` | `barranco-sparse-parque.service` | Parque 026: 1.577 cámaras, 751.619 puntos sparse |
| `http://127.0.0.1:8782/` | `barranco-sparse-006-corrected.service` | 006 derivada conectada; geometría NO aprobada |

Abrir desde la maestra. Los visores 878x no editan ni alinean.
En ellos: arrastrar gira; rueda zoom; Mayús+arrastrar desplaza.

Web principal: servicio con 4 GiB RAM, swap=0, CPUQuota=200%.
Después de actualizar frontend: guardar la revisión abierta y Ctrl+F5.
No está habilitado el arranque automático; verificar `/data` antes de iniciarla.

```bash
systemctl --user status barranco-roi
# Solo si no está activa y se necesita:
systemd-run --user --unit=barranco-roi --working-directory=/home/exitoso/home/barranco-roi -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=200% -p Nice=10 /data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/app.py
```

## 4. Anclas y trabajo manual real que NO debe perderse

Anclas originales fijas:
`001,002,003,004,005,007,008,009,012,013,017,018,024,025`.
**023 fue rechazada y será recapturada. No es ancla activa.**
No recalcular las 14 matrices ni utilizar el antiguo solver global para moverlas.

Al cierre la app devuelve **15 referencias**, no porque se haya rehabilitado
023, sino porque existe una colocación manual adicional de **026**:

- Placement: `p-84283c9c41e649a5a40527507a6cc7d2`.
- Sesión: `s-5552ad723cbb47d0afc56a4a0c2eb7d6`.
- Reconstrucción: `r-f41283acbb57cb5484a01462`.
- Estado: **`manual_unvalidated`**, `job_id=null`, geometría interna sin cambios.
- Modelo: `/data/barranco/review/barranco-inputs-20261115/026-all/colmap/sparse/0`.
- Matriz exacta y procedencia están en los JSON de `state/alignment/`.

Tratarlo como trabajo del usuario, NO como resultado de matching ni como prueba
automática. Las pruebas de navegador utilizaron estados temporales aislados;
no reemplazar esta colocación con fixtures ni restablecer `state/`.
La API principal tenía **cero trabajos de alineación registrados** al comprobarla:
no se ejecutó matching/BA de producción desde la app.

Estado persistente:
`/home/exitoso/home/barranco-roi/state/alignment/{anchors.json,reconstructions/,sessions/,jobs/,placements/}`.
Polígonos antiguos: `state/selections/` (025), `state/blocks/<id>/selections/`.
Exportaciones ROI: `state/exports/roi_<id>.json`.
Las colocaciones nuevas tienen claves `p-*` para no sobrescribir el ROI previo.

## 5. Experimentos: estado comprobado al cierre

Consultar identidad por etiqueta + MAC, no confiar solo en IP DHCP.

### A. 006 de varios vídeos — EN EJECUCIÓN

- Máquina **L507_006**, última IP `192.0.2.64`.
- Raíz remota:
  `/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-006-14nov`.
- Experimento: `phone_native_2fps_14nov_review_v1`.
- **Consulta SSH al cierre:** `running / sfm`, worker vivo, sin error,
  completadas `frames,masks`; todavía sin `registered_images` final.
- Inputs efectivos: **dos vídeos** `manzana_06.mp4` y
  `VID20261114142304.mp4`. El usuario lo llama «todos los vídeos», pero
  NO confundir con la antigua variante `006-all` de tres vídeos que se descartó.
- Una consulta anterior mostró 1.686 imágenes en el componente en construcción:
  **es una observación histórica provisional, no el conteo final actual**.
- Perfil original: masks → SfM → undistort → dense → metrics → revisión;
  sin alineación, malla o textura automáticas.

### B. Parque 026 — DENSA TERMINADA, ESPERANDO REVISIÓN

- Máquina **L507_019**, última IP `192.0.2.63`.
- Raíz:
  `/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-026-all`.
- Experimento: `phone_native_2fps_all_review_v1`.
- **Consulta SSH al cierre:** `awaiting_review / dense_complete`,
  etapas completas `frames,masks,sfm,undistort,dense,metrics`, sin error.
- Sparse: **1.577 imágenes, 751.619 puntos**, un componente.
- Copia local: `/data/barranco/review/barranco-inputs-20261115/026-all/`.
- La sparse local NO tiene base SIFT ni fotos originales adjuntas según el
  último registro (`manifest:null`); la densa sigue en la hija.
- No hay aprobación de malla. No confundir la colocación manual de §4 con
  validación de correspondencias o autorización de procesar productos nuevos.

**Fallo y recuperación del parque:** murió por OOM (límite 40 GiB) al remapear
máscaras rectificadas. COLMAP ya había rectificado las imágenes. La caché acumulaba
mapas por cámara. Se aplicó un overlay por corrida que limita la caché a DOS
mapas, sin cambiar proyección ni muestreo ni el checkout certificado.
Herramienta: `/home/exitoso/lab-deploy/tools/park_memory_recovery.py`.
Archivos remotos: `mask_geometry_bounded.py`, `mask-memory-patch.json`,
`pipeline_bounded.py`, `park_recovery_worker.py`, historial en `attempt-history/`.
Se corrigió un primer error de sys.path del wrapper y se reanudó desde undistort.

Tiempos medidos, sin esperas ni intentos fallidos:
frames 71,75 s; masks 3861,57 s; SfM 20121,31 s
(features 52,90, matching exhaustivo 6928,55, mapper 13103,24);
undistort recuperado 521,80 s. La densa YA terminó, pero **su duración final no
se consultó en esta actualización**: leer métricas, no extrapolar los 4/40 lotes.

### C. 006 de un vídeo vertical — ORIGINAL CONSERVADO

- Máquina **L507_010**, última IP `192.0.2.100`.
- Raíz:
  `/data/photogrammetry/campaigns/barranco-single006-sequential-20261115/cuadra-006`.
- Input: `VID20261114142304.mp4`, 1920×1080 codificados,
  rotación de display 90°, ~17 min 44 s, 2,03 GB.
- 2 fps, matching secuencial: 2.129 frames y SEIS componentes.
- Mejor original: modelo `2`, **1.119 imágenes, 363.246 puntos**.
- Densa original: **63.063.293 puntos / 28 lotes** (no copiarla innecesariamente).
- Sparse local:
  `/data/barranco/review/barranco-inputs-20261115/006-single14nov-sequential/`.
- Herramientas: `prepare_single006.py`, `start_review_experiments.py --sequential`.

### D. Reconexión de esa 006 — CÁLCULO COMPLETO, RESULTADO VISUAL CUESTIONADO

- Raíz remota:
  `/data/photogrammetry/campaigns/barranco-006-bridges-20261115/cuadra-006`.
- Experimento: `colmap_bridge_recovery_v1`.
- Se añadieron **33.057 pares candidatos** en una BD COPIADA; no se cambiaron
  máscaras ni se redujeron umbrales geométricos para forzar conexiones.
- COLMAP terminó en ~71 min de mapping y dejó un modelo PLANO en
  `outputs/cuadra-006/colmap_bridge_recovery_v1/colmap/sparse/`.
- El wrapper buscaba subdirectorios y marcó:
  **`failed: No derived model published`**. Ese fallo de publicación sigue en
  el recibo original; no significa que no existan archivos de salida.
- Se comprobó leyendo los binarios:
  **2.129 imágenes únicas, 679.516 puntos, un componente de tracks que abarca
  las 2.129 cámaras**. Cobertura de componentes originales:
  `0:2/2, 1:274/274, 2:1119/1119, 3:192/192, 4:260/260, 5:201/201`.
- Aumentó 1.010 imágenes respecto al mejor original. Hubo retriangulación/BA,
  **con poses de las 1.119 originales fijas** e intrínsecos sin cambios.
- Error almacenado: mediana 0,994 px, p95 2,006 px; track medio 4,37.
  Estos números NO certifican geometría correcta.
- **El usuario la vio rara, aparentemente desconectada. NO está aprobada.**
  Puede haber uniones falsas/deformaciones o huecos sparse; investigar,
  no declarar éxito por conectividad algebraica.
- Se recogieron SOLO tres binarios con hashes verificados y sin alterar la hija:
  `/data/barranco/review/barranco-inputs-20261115/006-bridges-corrected/`.
  Allí se adaptó la disposición local a `colmap/sparse/0` + `best_model.txt`.
- Visor 8782. La original permanece en 8780. No hay densa nueva de esta corrección.
- Código: `reconnect006_worker.py`, `start_reconnect006.py`.

### E. NUEVA 006 solo horizontal — DETENIDA POR SEGURIDAD

Petición explícita posterior del usuario: usar solo el vídeo horizontal que
llamaba «manzana_006», en la máquina del intento de un solo vídeo.

- Archivo real confirmado: **`manzana_06.mp4`**, 3840×2160, **sin rotación**,
  H.264, duración **832,246767 s** (13 min 52 s), **5.213.649.878 bytes**.
- Se distinguió mediante ffprobe del vídeo vertical anterior. El host no tiene
  ffprobe; se usó el de la imagen existente con montaje de lectura.
- Se verificó recibo/hash y se reutilizó por hardlink, sin descargar/duplicar
  ni modificar los tres vídeos originales.
- Máquina: **L507_010**. NO se tocó la corrida de L507_006.
- Raíz:
  `/data/photogrammetry/campaigns/barranco-006-horizontal-20261115/cuadra-006`.
- Experimento: `phone_native_2fps_horizontal_sequential_review_v1`.
- Lanzador nuevo:
  `/home/exitoso/lab-deploy/tools/start_horizontal006.py`.
  Genera `horizontal_worker.py` aislado, config y recibos; rechaza sobrescribir
  un intento existente. **No ejecutarlo otra vez esperando que reanude.**
- 2 fps, matching secuencial overlap=10, sin loop detection; calibración por
  vídeo en ese perfil. Máscaras y criterios geométricos conservados.
- Límite: 4 CPU / 40 GiB / swap=0; reserva disco 50 GiB.
- Por decisión anunciada al usuario, **se detiene tras SfM para revisión**,
  no ejecuta undistort, densa, alineación ni malla. Había ~140 GiB libres al inicio.
- **Consulta SSH al cierre:** `failed / masks`, worker no vivo,
  completado solo `frames`.
- Error: **`SAFETY STOP: sustained gpu_c=82.00`**. La GPU estaba limitada a
  145 W en la última telemetría. NO se bajó potencia ni se subió el umbral.
- El monitor `sh_1e244d9780010e37MpWqosIbfZ` terminó con ese fallo.
- Preservar frames y máscaras parciales. Antes de proponer reanudar: revisar
  enfriamiento/temperaturas, proceso y contenedor propios, disco y opciones de
  potencia/recursos; confirmar el alcance con el usuario. Nunca relajar el guard.

## 6. Supervisión: dónde leer y qué NO confundir

Estado local por campaña:
`/home/exitoso/lab-deploy/.state/campaigns/<campaña>/`
contiene `assignments.json`, `known_hosts`, `reconstruction-launch.json`,
`review-status.json`. Estos últimos pueden estar desactualizados.
Estado real remoto: `<work_root>/reconstruction-full-status.json`.
Logs: `<work_root>/logs/reconstruction/full/{frames,masks,sfm,undistort,dense,bridge-mapping}.log`.
Recibos de etapas/métricas: `<output>/.stages/` y `<output>/metrics/`.

Herramienta: `tools/review_experiments.py`.
**Su CLI no es estrictamente read-only:** también recoge sparse automáticamente
si están listas y escribe estado local. Para solo inspeccionar, importar y llamar
`inspect(assignment)` o hacer una lectura remota controlada. No duplicar monitores.
`--watch` espera y recoge; no lanza/repara reconstrucciones.
El monitor original de los experimentos seguía produciendo `review-status.json`
al cierre; no se reconfirmó su PID. No asumir que sigue vivo eternamente.

Se reutiliza el transporte confiable existente; verifica TXT y MAC en consultas
personalizadas, host keys estrictas y credenciales cargadas por los scripts.
**No leer/imprimir secretos ni volcar entornos.**

## 7. Implementación realizada: archivos y comportamiento

### Aplicación

En `/home/exitoso/home/barranco-roi/`:

- `app.py`: rutas ROI/alineación separadas antes de resolver manzana por defecto,
  POST locales protegidos, paquetes binarios versionados con ETag, assets nuevos,
  health ligero sin cargar la sparse completa.
- `roi/alignment.py`: registro de componentes, anclas fijas, sesiones inmutables,
  pares explícitos, cache de identidad por inode/size/mtime/ctime, caché de puntos,
  miniaturas, jobs systemd, cancelación propia, resultados y aprobaciones.
- `roi/catalog.py`: usa el paquete activo de 14 como fuente de verdad; el modo
  histórico `include_rejected=True` sigue disponible. Overview ahora incluye RGB.
- `roi/core.py`: identidad ROI basada en sparse/transformación/origen, sin
  exigir dense-lineage ni abrir densas. Compatibilidad read-only con selecciones
  históricas cuyo fingerprint incluía la densa.
- `roi/service.py`: **reescrito sparse-only**, sin lectores/preview/export de
  densa. Guarda revisiones y configs; no somete mallado.
- `roi/multi.py`: aislamiento de selecciones y validez por geometría/colocación.
- `alignment_worker.py`: worker numérico fuera de HTTP; snapshot del código
  BlockAlign/alignexp, runtime verificado, cgroup real, thermal guard,
  matching/PnP, solve conjunto, BA opcional y relocalización reservada posterior.
- `source_fetch.py`: transferencia EXPLÍCITA, solo lectura remota, de fotos
  originales y features; valida tag/MAC, hashes y reserva 50 GiB. No se ejecutó
  automáticamente sobre el parque. Usa Python del sistema para pexpect.
- `web/index.html`, `web/app.js`: ROI perezoso, ninguna manzana activa por defecto,
  contexto RGB, selección vacía, panel ROI flotante y proyección 2D optimizada.
- `web/align.js`: selector inicial sin precarga; vecinas explícitas; manipulación
  G/R/S y ejes; sliders XYZ/giro/escala/altura; selección visual separada de M/N;
  revisión, propuesta de pares, jobs/historial, aprobación y ROI.
- `web/align.css`: tema negro/gris/blanco; canvas a todo ancho; paneles flotantes
  transform/opacity, detalles desplegables, responsive, reduced-motion.
- `web/cloud-cache.js`: caché visual RAM + IndexedDB, revisión/ID, deduplicación;
  hasta 24 entradas / 64 MiB. No almacena aprobaciones como caché.
- `web/cloud-renderer.js`: WebGL residente, cambios por uniforms, LOD durante
  interacción; alternativa Canvas sin asignaciones por punto y colores cacheados.
- `tests/test_alignment.py`, `tests/alignment_browser_check.py` y
  `tests/browser_check.py`: pruebas de backend, navegador, caché, gestos y ROI.

No se deben eliminar las funciones legacy PLY de `roi/core.py` utilizadas por
scripts batch históricos solo porque ya no estén en la web.

### BlockAlign

En `/data/repos/Alineacion-point-cloud/`:

- **Nuevo `src/blockalign/manual.py`**: auditoría sin GPS, propuestas de soportes,
  localización de vistas exactas, normalización forward/reverse, solve robusto
  de 7 DoF con anclas constantes, pesos, degeneración y validación.
  Combina evidencia parcial de varias anclas sin exigir seis éxitos POR pareja.
- BA restringido: solo poses/puntos nuevos variables, intrínsecos fijos,
  observaciones de anclas fijas, vistas reservadas excluidas; límites y controles
  de degradación/deformación. Exporta nuevo modelo en `map_world`, no fusiona anclas.
  La densa anterior queda marcada para regenerar.
- `src/alignexp/binary.py`: lector de intrínsecos ampliado a modelos COLMAP
  estándar; antes solo SIMPLE_RADIAL.
- `src/blockalign/colmap_adapter.py`: BD nueva 3.13 con endpoints seleccionados,
  sin copiar una BD multigigabyte por pareja; IDs/nombres con namespaces.
- Nuevos `tests/test_manual.py`, `docs/manual-alignment.md`.
- Contratos automáticos geográficos existentes NO se falsificaron: el nuevo
  modo manual tiene su propia entrada sin GPS. `graph.solve()` automático sigue
  sin ser la ruta adecuada para congelar todas las anclas.
- `pairwise.py`, `correction.py`, `audit.py`, `workspace.py` se investigaron;
  no asumir que el antiguo BA pairwise ofrece las nuevas garantías.

Matching/BA reales del motor se probaron sobre escenas sintéticas, no sobre
reconstrucciones de producción desde la web. «Cámara» en UI significa imagen/vista
registrada, no el ID de intrínsecos compartidos.

## 8. Caché y fluidez: garantías y límites

- No se pide `/api/overview` al entrar en alineación. ROI solo carga al abrirlo.
- Paquete `/api/alignment/cloud/<id>?v=<version>`: header JSON alineado +
  registros XYZ Float32 relativos a origen Float64 y RGBA (16 bytes/punto).
- Hasta 80.000 puntos por nube para DIBUJAR. Matching, matrices y ROI completo
  siguen usando los originales; nunca confundir muestreo visual con recorte.
- Buffers GPU residentes: mover no transforma toda la nube en JS ni la reenvía.
- Encuadre usa ocho esquinas por nube; no ordena todos los puntos.
- Mouse events consolidados por frame; al soltar se aplica el último evento.
- Zoom suaviza SOLO la cámara; no interpola/retoca la matriz científica.
- Nada seleccionado al recargar; RGB por defecto. Esc retira resaltado/ejes,
  no borra M/N ni la revisión. G/R/S seleccionan la nube móvil para manipularla.
- Controles cerrados al abrir; son overlay, no reducen/redimensionan el canvas.
- Borradores locales conservados separadamente de revisiones servidor y de
  selección visual; «Sin selección» no equivale a borrar la colocación manual.
- Antes de recargar versión vieja, guardar revisión; Ctrl+F5 carga frontend nuevo.

## 9. Eliminaciones y preservación

**Limpieza de datos ya realizada al inicio de esta sesión, autorizada y auditada:**

- Recibo exacto:
  `/data/barranco/active/cleanup-1794729639320349624.json`.
- **1.221 archivos enumerados**, ~312,395 GiB lógicos: nube global obsoleta,
  copias centrales `scene_dense_scalar.ply` y multimedia de la campaña vieja
  de mallas/texturas. La lista completa está en el recibo; no inventar nombres
  o volver a ejecutar una eliminación.
- Tras esa limpieza se observaron 364 GiB libres en la maestra:
  cifra HISTÓRICA, consultar `df` antes de presupuestar ahora.
- Antes se preservaron sparse, matrices, escenas OpenMVS y **5.223 imágenes
  rectificadas de las 14 aceptadas**, con hashes/hardlinks en `/data/barranco/active/`.
- Se conservaron mallas/Blender actuales, features/BD, fuentes en hijas,
  scripts y metadatos. No se alteró el `.blend` de 15 objetos histórico.
- El intento antiguo `cuadra-006-all` descartado por el usuario tiene su propio
  `discard-receipt.json`; sus vídeos quedaron, no confundirlo con los nuevos.

**Retirada funcional de UI**, NO borrado de densas en hijas:
preview de densa, análisis y exportación densa del selector, botones/pollers/rutas
y dependencia de dense-lineage para ROI. Los scripts batch legacy permanecen.
Durante reescrituras se sustituyeron `roi/service.py`, `web/align.js`,
`web/align.css` y README; sus reemplazos actuales existen, no son archivos perdidos.

**Documentación:** el anterior `home/opencode.md` se movió a
`home/opencode-historial-20261114.md` en esta actualización para conservar
íntegro el texto anterior sin que contradiga este estado vigente.

## 10. Entregas históricas y restricciones

- Entrega simplificada 70 %:
  `/home/exitoso/home/barranco-roi/exports/mesh-campaign-20261112/simplified_70pct_blocks/`.
- `.blend`: `barranco_15_manzanas_70pct.blend`, 15 objetos y 15 datablocks de malla
  independientes. Son entrega histórica, NO quince anclas activas aceptadas.
- Conservar `delivery.json`, `blender-audit.json`, `.mlp`, meshes y revisiones.
- El usuario puede haber editado manualmente el Blender: comprobar antes de
  cualquier regeneración; nunca sobrescribirlo, fusionar bloques o instanciar
  geometrías para reducir peso sin petición.
- Reparación de huecos MANUAL, no automatizada. Texturizado posterior por
  reproyección de fotos originales sobre geometría aprobada.
- Rectificación ≠ alineación: corrige lente y adapta máscaras/cámaras para MVS.
- Sim(3) solo de colocación no modifica SfM interna y puede reutilizar una densa
  de linaje verificado. BA interno sí exige revisar/regenerar productos derivados.

## 11. Pruebas y control de versiones

Última comprobación de esta sesión:

- **44 tests unittest de la aplicación: OK.**
- **44 tests pytest del repositorio de alineación: OK** en la integración
  anterior; el rediseño posterior solo cambió app/representación.
- Chrome con WebGL y sin WebGL: OK, selección vacía, RGB, paneles, reduced-motion,
  arrastre/giro/sliders, exactitud del pivote, deshacer, caché tras recarga y ROI.
- Escena diagnóstica con tres nubes / ~205.447 puntos muestreados:
  61 actualizaciones en ~1,0–1,14 s. Tiempo CPU de render mediano ~0,2–0,3 ms
  WebGL y ~11–12 ms Canvas con RGB; NO prometer esos tiempos en cualquier equipo.
- Métricas/capturas temporales:
  `/tmp/opencode/alignment-perf-{gpu,fallback}.json`,
  `/tmp/opencode/alignment-*.png`. No representan colocaciones aprobadas.

```bash
/data/barranco/runtime/alignment313/bin/python -B -m unittest discover -s /home/exitoso/home/barranco-roi/tests -q
# Desde /data/repos/Alineacion-point-cloud:
TMPDIR=/tmp/opencode PATH=/data/barranco/runtime/alignment313/bin:$PATH PYTHONPATH=src /data/barranco/runtime/alignment313/bin/python -B -m pytest tests -q
/data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/tests/alignment_browser_check.py
/data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/tests/alignment_browser_check.py --fallback
```

No hubo commits/pushes en esta sesión. Hay cambios locales en el repo externo.
**El Git de `/home/exitoso` ignora `/home/*` mediante `/*`: un `git status`
limpio allí NO significa que la aplicación o este documento estén versionados.**
Inspeccionar el repositorio correcto y las rutas reales, no resetear cambios
ajenos ni borrar estado para obtener un status limpio.

## 12. Seguridad y próximos pasos recomendados al nuevo chat

1. Leer este documento y README; revisar estados actuales sin relanzar nada.
2. Reconocer el trabajo manual 026 de §4 y no sobrescribir su matriz/ROI.
3. Comunicar: 026 densa lista, 006 multivídeo aún SfM al cierre, horizontal
   parada térmica y corregida visualmente dudosa.
4. Acordar con el usuario cuál atender: térmica, revisión geométrica o UI.
5. Si autoriza recuperar horizontal: enfriamiento y límites seguros, conservar
   frames/máscaras parciales y recibos, nueva política explícita de reanudación,
   no volver a llamar al lanzador que rechaza raíces existentes.
6. No hacer malla/densa/BA/alineación por leer este contexto. No ampliar el alcance
   a otras hijas o trabajos de compañeros.

No apagar/reiniciar/bloquear/cerrar sesión en máquinas sin autorización explícita.
**La maestra nunca es objetivo de energía.** Cargar la skill `l507-readonly`
al consultar laboratorio, tags, IPs, GPUs o el Makefile. Las credenciales son
locales y deben cargarlas los scripts existentes, no leerse ni publicarse.
Los montajes ext4 `/data` se estandarizaron en las 20 máquinas inventariadas,
pero **no se persistieron en `/etc/fstab`**; verificarlos tras reinicios.
No subir umbrales térmicos, no matar procesos generales, no eliminar archivos
para «hacer espacio» sin lista y autorización. Preservar siempre fuentes,
revisiones, recibos, hashes y diagnóstico.
