# Barranco — preparación y descargas, 16 noviembre 2026

## 15:51 UTC — GLOMAP instalado en /data y 020 iniciada

Autorización explícita: instalar GLOMAP en `/data` de L507_005 y ejecutar
020 reutilizando BD/features/matches. Variante independiente:
`/data/photogrammetry/campaigns/barranco-020-glomap-20261116/cuadra-020`.
PID inicial1074347. NO repetir arranque al leer este relevo.

- Runtime aislado:
  `/data/photogrammetry/runtime/glomap-1.1.0-020-20261116/env/bin/glomap`.
  Paquete conda-forge `glomap=1.1.0=h930c707_0` CPU, instalación91paquetes,
  ~115MBdescargados. Cachés/paquetes/prefix/tmp/DockerRootDir en `/data`.
  Sin apt, sin modificar runtime/alineador o checkout certificado.
- Bootstrap micromamba2.10.0 de conda-forge, SHA256 publicado verificado:
  `9a97976244929bbae28fb1fae504e74a3e7e6d1932870e3a03321f01b7fbd07b`.
  Binario GLOMAP instalado y paquetes exactos/hashes registrados en
  `runtime-receipt.json`; ayuda CLI validada.
- Entrada: **BD terminada de020vocabloop a2fps**, no10fps,970imágenes.
  Backup SQLite desde conexión RO hacia BD nueva; quick_check y conteos
  de tablas verificados. Hash de fuente antes/después de copia en
  `database-copy.json`; se comprueba de nuevo al terminar.
  Reutiliza keypoints/descriptores/matches/two_view_geometries.
  GLOMAP reestima geometría relativa/global desde matches existentes;
  NO nueva extracción, matching ni máscaras.
- `glomap mapper` con defaults propios deGLOMAP: NO afirmar que todos sus
  umbrales de triangulación/filtrado son iguales a los deCOLMAP3.11.
  El paquete es CPU; Docker sinGPU,4CPU/40GiB/swap0, redsolo eninstalación;
  runtime y fuente montadosRO al mapear; BD derivada y salidasRW.
  Guardas certificadas intactas (GPU80°C30s/85°Cinmediato, CPU/SSD/disco).
  Potencia existente100W sin cambio.
- Observación posterior: running/sfm, worker vivo, sinerror; cargó970imágenes
  y25323filas depares (incluye inválidas), comenzó estimación relativa
  para13845pares. GPU36°C/CPU44°C,~119,3GiB libres en/data.
  Carga de datos NO prueba corrección del corte ni reconstrucción completada.
- Solo sparse, sin densa/alineación/malla/autoaprobación.
  Worker durable `lab-deploy/tools/glomap_review_worker.py`.
  Estado local `.state/campaigns/barranco-020-glomap-20261116/`.
  Monitor añade **020 GLOMAP**. Dos tests del worker y tres del monitor OK.

## 019 variante10fps: rescate Sim3 detenido antes de generar candidata

Usuario autorizó usar PnP existente, analizar partición, estimar Sim3 y generar
candidata/retriangular/BA SOLO si transformación y partición resultaban válidas.
No repetir matching/PnP ni reconstruir desde cero.

Ejecutado `lab-deploy/tools/rescue019_sim3_gate.py` con PyCOLMAP3.11.1;
salida `/data/barranco/review/diagnostics/019-sim3-rescue-20261116/analysis.json`.
Servicio acotado4GiB/CPU200%/swap0, terminó en6,83s. Dos tests sintéticos OK.

Datos guardados:4queries independientes por sentido, de las que1reservada.
Solo3entrenamiento, sin redundancia para consenso robusto. Subsets/seeds de
las mismas queries NO se contaron como cámaras adicionales.
Sim3 algebraica tentativa ajustada exclusivamente a3centros por sentido:
forwardescala1,1373, reversescala0,8557; ratios segunda/primera singular
0,0238 y0,0345 (centros casi colineales).
La validación local reservada tiene errores0,00237/0,00150unidades
(0,067/0,042pasosmedianos); NO garantiza estabilidad lejos de esa recta.
Componer las dos transformaciones, que deberían ser inversas si describiesen
una misma relación rígida, desplaza centros globales mediana0,927 y p951,160
unidades frente a paso mediano0,03541. No relación global estable demostrada.

Grafo de1200cámaras conectado incluso exigiendo100puntos comunes por arista.
Partición temporal495/705 cruza78.074tracks y7951aristas de covisibilidad;
ejemplo54s–443s comparte3113puntos. No son dos nubes independientes.
Mincut condicionado a ventanas opuestas aísla1196/4cámaras, cruza748tracks.
Simulación SOLO centros:
- Transformar todo el tramo posterior quita salto objetivo, pero contradice
  numerosas conexiones de revisita; no es evidencia de reparación fotogramétrica.
- Mover solo cuatro cámaras trasladaría el salto a249–249,5s, ~43,5×mediana.

Decisión STOP_NO_CANDIDATE: las condiciones de aceptación no se cumplen.
No se demostró que toda partición concebible sea imposible, ni que puntos
compartidos impidan cualquier reajuste conjunto; se rechazó esta reparación
por Sim3 independiente con las poses existentes y las particiones ensayadas.
No nueva sparse, transformaciones de modelos, asociaciones, triangulación ni BA.
Originales/densas/otrasmanzanas intactos. No repetir PnP para acumular más
queries sin nueva decisión del usuario; una reestimación conjunta es otro alcance.

## 15:38 UTC — resultado 020 con vocabulario: corte original persiste

Usuario pidió recoger y revisar la variante terminada. Consulta remota:
awaiting_review/sparse_review, 970vistas, 558.189puntos, componente0;
SfM supervisada2225,38s (~37min05s). Sparse no aprobada.
Auditoría RO sobre BD y modelo de esta misma corrida, identidad tag/MAC
verificada, coordenadas keypoints BD/modelo coincidentes:

- Corte548–549 (273,5–274s):1.021matches verificados, cero puntos3D
  compartidos, salto32,72× mediana global de velocidad positiva.
  Asociaciones:423ambas sin3D,351soloA,89soloB,158puntos distintos,0mismo.
  No demuestra qué etapa produjo esas asociaciones.
- Ventana201–202,5s: vecinos comparten257,360,506puntos; pasos normales.
  No reproduce los tres saltos graves de la variante10fps.
- Segundo mayor salto temporal de la corrida:1,61×; el corte548–549
  sigue siendo la anomalía claramente dominante.

Reporte:
`/data/barranco/review/diagnostics/020-vocabloop-audit-20261116-153815.json`.
Colección sparse/metadatos solicitada en
`/data/barranco/review/catalog-20261116-134343/020-vocab-loop/`;
solo publicar tras verificar SHA256 y recibo collection.json.
No hay nueva densa, alineación, cambio de umbrales ni reintento autorizado.

## 019: diagnóstico PnP bidireccional, sin reparar modelos

Autorizado por el usuario después de la auditoría de tracks. Se exportaron
solo correspondencias verificadas de ventanas acotadas de las BD originales
en modo RO; identidad tag/MAC y host keys verificadas. Los SHA256 de los tres
binarios remotos coinciden con las sparse locales usadas por PyCOLMAP3.11.1.
No se transfirieron fotografías ni BD completas.

Archivos:
`/data/barranco/review/diagnostics/019-pnp-20261116/{inputs.json,export-snapshot.py,results.json}`.
Código `lab-deploy/tools/pnp019_diagnostic.py`.

128 estimaciones/intentos: original y variante, dos cortes, dos direcciones,
cuatro queries, referencias completas o dos subconjuntos y dos seeds para
referencia completa. Intrínsecos fijos; RANSAC4px/5000trials.
Puntos únicos, tracks>=3vistas, error almacenado<=4px y soporte>=2referencias.
Se excluyen puntos con observaciones en CUALQUIERA de las cuatro queries del
lado opuesto para evitar que la propia pose consultada sostenga su referencia.
Este criterio elimina también muchos puntos válidos en zonas ya conectadas:
insuficiencia de candidatos aquí NO demuestra falta de solape ni fallo de PnP.

Resultados principales (referencia completa, seed0):
- Original828→829:104candidatos/77inliers, mediana reproyección1,60px,
  cambio orientación21,74°. Separación hipotética828–829 pasa1,37292→0,03278
  unidades SfM al sustituir SOLO la pose consultada para medir, sin escribirla.
- Original sentido inverso sobre828:47/37, mediana1,21px; soporte limitado en
  otras queries, sin candidatos suficientes en la query forward más alejada.
- Variante corte247–247,5s: query247,5s130/113, mediana1,33px,
  giro24,32°; separación hipotética1,51198→0,03387. Las cuatro queries
  se localizaron en ambos sentidos con referencia completa. Sensibilidad por
  subconjuntos/semillas preservada en informe.
- Variante zona original413,5–414s: pequeñas diferencias respecto de sus poses
  ya conectadas. El filtro de independencia deja pocas observaciones.

NO se estimó ni aplicó Sim3, no se modificaron cámaras/puntos/tracks, no BA.
La cuarta query de cada dirección quedó etiquetada reservada para un futuro
ajuste; su PnP individual NO constituye validación de una transformación común,
que aún no existe. PnP/validación espacial no certifican puntos estáticos sin
revisión de fotos. El inlier mask procede del estimador; el refinamiento puede
dejar residuos finales>4px y se informa p95 sin ocultarlo.
Ejecutado en maestra, servicio diagnóstico acotado4GiB/CPU200%/swap0/900s,
terminósuccess en1,72s, pico1GiB. Dos tests sintéticos aprobados.
Siguiente decisión: analizar conectividad y coherencia de relaciones entre
subtramos antes de autorizar rescate; no mover por cercanía visual.

## 15:01 UTC — 020 con detector de revisitas por vocabulario; 011 recogida

Autorización explícita posterior: descargar vocabulario, lanzar una variante
020 con `loop_detection=true` y recoger la 011 terminada para el visor único.

- **011**: sparse/metadatos recogidos con SHA256 verificado en
  `/data/barranco/review/catalog-20261116-134343/011/`;
  componente 0, 2.091 vistas / 1.372.798 puntos. API del catálogo
  `http://127.0.0.1:8790/` comprobada; aparece al recargar sin reiniciar servicios.
- **020 nueva** en L507_005:
  `/data/photogrammetry/campaigns/barranco-020-vocabloop-20261116/cuadra-020`.
  Worker PID inicial 908161. Consulta posterior: running/sfm, worker vivo,
  sin error; vocabulario aceptado y COLMAP indexando imágenes, GPU 41 °C,
  límite existente 100 W. No se cambió potencia.
- Parte de la **020 original a 2 fps**, 970 frames, overlap20, mismas máscaras
  y criterios de triangulación/filtrado. Conserva overlay explícito inicio/final.
  La intervención científica es añadir detector nativo de revisitas por
  vocabulario; no es la variante con 10 fps local. Se reextraen features con la
  misma configuración en BD nueva; no se modifica ni reutiliza en escritura la BD
  original. Termina tras SfM: sin densa, alineación, malla ni autoaprobación.
- Vocabulario oficial recomendado para cientos/miles de imágenes:
  `https://github.com/colmap/colmap/releases/download/3.11.1/vocab_tree_flickr100K_words32K.bin`,
  15.229.678 bytes,
  SHA256 `d37d8f19ee0a49705c4c0b06967a08cedfed5cf86519eada3271497256732bc2`.
  Hash calculado localmente; el publicador no aportó digest independiente.
  Descarga directamente en `/data` de la hija, recibo preservado.
- 4.850 archivos frames/máscaras reutilizados por hardlink con inventario/hash.
  Contenedor monta frames, masks, datasets y árbol en RO. Snapshot del código,
  configs y hashes por corrida. Guardas certificadas intactas:
  80 °C sostenidos 30 s / 85 °C inmediato; 4 CPU / 40 GiB.
- Nuevo worker durable `lab-deploy/tools/loop_vocab_worker.py`;
  preparación y lanzamiento preservados en
  `.state/campaigns/barranco-020-vocabloop-20261116/`.
  Monitor añade **020 vocab loop**. No relanzar al leer este registro.
- Tests: tres del monitor y uno de montajes RO del worker aprobados.

La 011 terminó el cálculo, no fue aprobada geométricamente. La nueva 020 aún
no demuestra ninguna corrección. Comparar TODA su trayectoria con la original
y con la variante local10fps al terminar, sin confundir IDs entre datasets.

## Prueba 019: corte 828–829, 10 fps local

El usuario marcó A=829 y B=828 en la 019 original y autorizó aumentar cámaras.
Diagnóstico previo: salto de centros 1,37292 unidades SfM locales, mediana vecina
0,03598 (38,16×); giro 22,41°. La BD tenía 430 inliers en el par, pero la sparse
final no contiene puntos 3D compartidos entre esas dos vistas. No se identificó
el criterio exacto que descartó cada observación. Fotos vecinas muestran fachada,
árbol cercano y cambio importante de encuadre.

Se inició una corrida SEPARADA en L507_004, a 100 W:
`/data/photogrammetry/campaigns/barranco-019-cut10fps-20261116/cuadra-019`.
Muestreo: 2 fps fuera de [408,420) s (06:48–07:00), 10 fps dentro.
24 muestras se sustituyen solo en la variante por 120 frames nuevos:
1.080 frames/máscaras originales reutilizados + 120 nuevos = 1.200 esperados.
La 019 original y su visor 8783 permanecen intactos.

Se reutilizó el helper de corte ya corregido para EXDEV, generalizado por
block_id, video_stem, intervalo, targets y conteo de frames. Los helpers conservan
el nombre `cut020_*` por compatibilidad, pero cada corrida tiene snapshots
independientes con sus hashes. No se actualizaron archivos de la prueba 020
en ejecución. Fuente montada solo lectura, sin modificar parámetros de máscaras
o criterios geométricos. Mantiene ventana temporal 10 s y candidatos de cierre,
guardas intactas, 4 CPU/40 GiB, sparse-only; sin densa/malla/autoaprobación.
Se añadieron pruebas para el intervalo 019: seis tests OK.

Estado local: `.state/campaigns/barranco-019-cut10fps-20261116/`:
`assignments.json`, `bindings.json`, `launch.json`. No repetir lanzamiento.
Monitor: **019 corte 10fps** en `make barranco-status`.

## Puerto 8783 cambiado a 019 por petición del usuario

Se recogió la sparse terminada de 019 con SHA256 verificado:
`/data/barranco/review/barranco-running-20261116/019-seq20-loop/`.
Un componente, **1.104 vistas y 654.330 puntos**. Solo sparse/metadatos;
sin fotos, features, densa, alineación o aprobación automáticas.
Recibos de campaña: `sparse-019-manifest.json`, `sparse-019-collected.json`.

**http://127.0.0.1:8783/ ahora muestra 019**, servicio `barranco-sparse-019.service`.
Se detuvo únicamente el visor de usuario `barranco-sparse-020.service`.
El dataset 020, sus marcas de navegador y el worker de corrección no se tocaron.
La 021 continúa en 8784. Comprobados HTTP / y /api/models de 8783.
Recargar Ctrl+F5 para dejar de ver la 020 en una pestaña antigua de ese puerto.
Las referencias anteriores a 020 en 8783 son históricas.

## Recuperación de la prueba 020: EXDEV en merge_frames

La prueba terminó timing_check, extra_frames y extra_masks, pero falló antes
de SfM al intentar un hardlink desde la fuente montada RO al bind de la corrida:
`OSError: [Errno 18] Invalid cross-device link`.
No fue un fallo térmico ni evidencia de geometría incorrecta en la variante.

El usuario autorizó corregir/reanudar. Se modificó `cut020_steps.py`:
hardlink si es posible; exclusivamente ante EXDEV, copia temporal en el destino
con SHA256 y publicación sin sobrescritura. Destinos existentes se reutilizan
solo si su hash coincide; otros errores no se ocultan. merge admite sus
directorios existentes. No se borran ni modifican fuentes.

Se archivaron helper anterior, spec/estado y logs en
`attempt-history/<timestamp>-before-exdev-fix/` de la prueba. Se actualizó
solo el hash del helper en su spec, con execution_amendment documentado;
bundle original local conservado. Cinco tests (incluido EXDEV simulado,
no sobrescritura y conservación del soporte temporal) OK.
Se reanudó desde merge_frames, reutilizando las tres etapas completadas,
sin repetir frames/máscaras ni cambiar parámetros científicos, potencia o guardas.
Recibos locales: `repair-exdev-bindings.json`, `recovery-exdev-launch.json`;
recibo remoto `recovery-exdev.json`. No repetir esa recuperación automáticamente.

## Prueba 020: densidad temporal local 10 fps autorizada

Selección del usuario:
A = imágenes 549/550, B = 547/548, nombres `phone/manzana_20_000<ID>.jpg`.
Se investigó SOLO la 020 original, sin cambiarla:

- El par 548–549 tiene 1.021 inliers almacenados: no es ausencia total de matches.
- Paso entre sus centros: 1,5214 unidades SfM locales; mediana vecina 0,041595,
  razón 36,58. No convertir estas unidades en metros.
- Verificación por reextracción FFmpeg desde el origen, con fase original fps=2:
  547→273,0 s, 548→273,5 s, 549→274,0 s, 550→274,5 s.
  Se verificaron píxeles idénticos. Son tiempos PTS del filtro de salida,
  no una afirmación de PTS exacto del frame original decodificado.
- Contact sheet muestra furgoneta dominante y pared poco texturada.
  No se determinó si el vehículo está en movimiento. No se añadió máscara de
  vehículos ni se atribuyó la causa definitivamente.

El usuario autorizó una prueba derivada. Se inició en L507_005, a **100 W**:
`/data/photogrammetry/campaigns/barranco-020-cut10fps-20261116/cuadra-020`.
Estado local: `.state/campaigns/barranco-020-cut10fps-20261116/`.
Se mantiene la 020 original y el visor 8783 intactos.

Muestreo variante:
- 2 fps fuera de [268,280) segundos (04:28–04:40).
- 10 fps dentro: 120 frames nuevos sustituyen SOLO EN LA VARIANTE los 24
  originales de ese tramo; originales conservados en la corrida fuente.
- Resultado esperado: 946 frames/máscaras reutilizados + 120 nuevos = 1.066.
  Esto evita mezclar fases de muestreo de 2 y 10 fps dentro del intervalo.
- Máscaras SegFormer + SAM3 con la misma configuración; se generan solo para
  los frames nuevos. No se alteró la política de clases.
- Matching secuencial base=20 y pares explícitos en ventana temporal de 10 s
  para no acortar el soporte temporal al aumentar fps. Candidatos de cierre
  inicio–fin conservados mediante muestras de los frames originales extremos.
  Presupuesto 80.000 candidatos, criterios geométricos sin relajar.
- Reconstrucción sparse nueva, sin congelar poses cuestionadas, sin densa/malla.
  No se usó el modelo original como geometría ya aprobada.

Workers nuevos: `lab-deploy/tools/cut020_worker.py` y `cut020_steps.py`,
snapshots con hashes por corrida, código certificado intacto y fuente montada
solo lectura. Configuración, lineage y nombres nuevos se guardan; IDs de imágenes
de la variante NO deben confundirse con IDs de la original.
Dos tests de construcción temporal/pares OK.
Último estado observado: timing_check y extra_frames completos, extra_masks activo,
worker vivo y sin error. No declarar el corte corregido hasta comparar geometría.

El monitor añade **020 corte 10fps**. No relanzar este experimento al leer el relevo.
Diagnósticos locales: `diagnostics/cut-contact-sheet.png`, `timing-check.json`,
`baseline-inspection.json`; recibo de lanzamiento `launch.json`.

## Marcado de cámaras para investigar el corte de 020

El usuario describió visualmente la 021 como correcta y un posible corte/pérdida
de tracking en 020. No se convirtió esa observación en aprobación/alineación
automática ni se ejecutó una recuperación geométrica.

Se añadió al frontend `home/sparse-review/index.html`:
selección de centros de cámaras en lados A/B, etiquetas con ID de imagen,
nombres exactos, búsqueda, modo Solo cámaras, copiado de informe y exportación
JSON. Borrador únicamente en localStorage por dataset/componente.
Los centros del JSON siguen en coordenadas SfM originales.
No se añadieron rutas de escritura ni se modificaron binarios.
No hizo falta reiniciar los visores: el HTML se sirve sin caché desde disco.
Usuario debe hacer Ctrl+F5 en http://127.0.0.1:8783/.

Se probó en Chrome con perfil temporal aislado: selección por clic proyectado,
A/B, arrastre sin selección accidental, IDs/nombres, clipboard simulado,
exportación JSON, persistencia tras reload y limpieza de marcas.
Tres tests de lectura originales OK.
La selección NO fuerza correspondencias; después de recibirla habrá que
investigar solape/poses/tracks antes de decidir extracción más densa o rematching.

## Visores 020 y 021 publicados

A petición del usuario se verificó SfM terminado (`awaiting_review/sparse_review`)
y se recogieron SOLO binarios sparse de todos los componentes y metadatos:

- 020: un componente, 970 vistas, 562.041 puntos.
- 021: un componente, 884 vistas, 526.355 puntos.

Copias locales con SHA256 verificado:
`/data/barranco/review/barranco-running-20261116/{020,021}-seq20-loop/`.
Recibos `collection.json`; manifiestos y colección en el estado de campaña
`sparse-020-021-{manifest,collected}.json`. No se recogieron fotos/features/densas.

Visores independientes de solo lectura (HTTP / y /api/models comprobados):

| URL en la maestra | Servicio de usuario |
|---|---|
| http://127.0.0.1:8783/ | barranco-sparse-020.service |
| http://127.0.0.1:8784/ | barranco-sparse-021.service |

Se utilizó `home/sparse-review/app.py` sin cambiar la app principal ni sus revisiones.
Cada modelo sigue en su marco local; no se alineó ni aprobó geometría.
El visor muestrea hasta 250.000 puntos para representar; los binarios completos
permanecen intactos. Arrastrar gira, Mayús+arrastrar desplaza, rueda zoom.

## Diagnóstico adicional autorizado: 006 horizontal SIN máscaras

El usuario solicitó comparar la 006 horizontal sin máscaras y SOLO SfM.
Se inició una corrida separada en L507_010:
`/data/photogrammetry/campaigns/barranco-006-horizontal-nomasks-20261116/cuadra-006`.
Se reutilizaron por hardlinks los **1.665 frames** y el vídeo `manzana_06.mp4`
del intento anterior, con inventario y SHA256 de cada frame.
El intento anterior fallido y sus máscaras permanecen intactos.

Se preservó la configuración SfM original: 2 fps, matching secuencial overlap=10,
loop_detection=false y sus demás parámetros. Único cambio científico solicitado:
masking.enabled=false. No se añadió el overlay de cierre de las otras manzanas.
No se generan máscaras, undistort, densa, alineación ni malla.
Se conservan guardas térmicas; no se cambió la potencia de L507_010 (145 W).
Worker: `lab-deploy/tools/sparse_nomasks_worker.py`.
Estado local: `.state/campaigns/barranco-006-horizontal-nomasks-20261116/`,
incluyendo `launch.json`, `assignments.json` y snapshots `bindings.json`.
No relanzar al leer este registro.
El monitor añade **006 horiz s/m**, sin ocultar la fila del intento anterior.

## Recuperación posterior autorizada: diez hijas a 100 W

El usuario autorizó explícitamente bajar a **100 W** las diez GPU de esta
campaña y reanudar. Se aplicó y verificó en 002,004,005,007,008,009,011,015,021,022;
no se tocaron las hijas 006/010/019 de campañas anteriores.
No se elevaron umbrales ni se cambió el código de la guarda térmica.

Se comprobó que cualquier trabajo GPU presente perteneciera al contenedor de
esta corrida antes de cambiar potencia. 011 (bloque, hija 015) continuaba activo:
se mantuvo su PID, sin duplicarlo. Las otras nueve estaban fallidas en máscaras
por parada térmica y se reanudaron desde esa etapa, reutilizando frames.
**El pipeline borra/regenera masks/**: antes de reanudar se MOVIERON los parciales
a `attempt-history/<timestamp>-before-100w/partial-masks`, y se archivaron estado,
configuración y logs. No se borraron los parciales ni las fuentes.
No hay reintentos automáticos ante otro fallo.

Recibos locales: `recovery-100w-bindings.json`, `power-100w.json`,
`recovery-100w-launch.json`; recibos de política de potencia y recuperación por
corrida en cada hija. El límite de potencia no se configuró persistente al reinicio.
`make barranco-status` ahora muestra también el límite de potencia ACTUAL.
La sección de incidentes de abajo describe el intento anterior a 145 W.

## Última actualización: 016-023 terrestre y consulta manual

El usuario autorizó lanzar lo pendiente. Se inició SOLO `manzana_16y23.mp4`
en L507_022, mediante snapshot por hardlinks, sin modificar el paquete de
16 archivos descargados ni incluir todavía los DJI.
Raíz: `/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-016-023-terrestrial`.
Recibos: `terrestrial-bindings.json`, `terrestrial-preparation.json`,
`terrestrial-launch.json` en el estado local de la campaña.
Perfil idéntico sparse-only seq20 + candidatos de cierre, guardas intactas.
Última observación: worker vivo, frames completos, etapa masks.

**Incidentes térmicos actuales:** los bloques 014,015,019,020,021,022,027
se detuvieron en máscaras con SAFETY STOP por 80–83 °C sostenidos.
No se reanudaron ni se cambiaron potencia/guardas.
010 y 011 continuaban en máscaras en la última consulta; no asumir que
seguirán vivos sin consultar. La 006 multivídeo anterior continúa SfM,
026 sigue awaiting_review/dense_complete; horizontal anterior sigue fallida.

Comando desde `/home/exitoso`: **`make barranco-status`**
(alias `make pipeline-status`; JSON: `make barranco-status-json`).
Implementación persistente: `lab-deploy/tools/barranco_status.py`.
Consulta SSH paralela con identidad tag/MAC y host keys estrictas.
Lee únicamente recibos; no escribe snapshots, recoge sparse ni inicia/reintenta
trabajos. Distingue temperatura GPU actual del fallo térmico histórico.
Incluye diez bloques nuevos y tres corridas anteriores.
Se comprobó con consultas reales y tres tests unitarios.

## Actualización posterior: nueve SfM autorizados e iniciados

El usuario autorizó después lanzar SfM en las manzanas de un único vídeo
ya descargado: **010,011,014,015,019,020,021,022,027**.
Se iniciaron nueve workers independientes con `sparse-launch.json` y
`sparse-bindings.json` en la campaña local. No relanzarlos al leer este documento.
La autorización nueva NO comprende densa, malla ni alineación automáticas.
016-023 quedó aparte de este lanzamiento; no asumir que su reconstrucción comenzó.

Perfil: 2 fps nativos, cámara por fuente, matching secuencial lineal overlap=20
(quadratic_overlap=0), máscaras existentes y criterios geométricos sin relajar.
Overlay por corrida añade antes del mapper hasta 14.400 pares candidatos de
cierre entre las primeras/últimas <=240 imágenes, muestreadas a <=120 por lado.
Los pares requieren matching/verificación normal; no son conexiones impuestas.
Se conservan todos los componentes, se detiene tras SfM para revisión.
No se prometió ausencia de huecos por continuidad del vídeo.

Archivos nuevos: `lab-deploy/tools/sparse_review_worker.py` y
`lab-deploy/tools/sparse_loop_overlay.py`. Snapshots y hashes por corrida,
checkout certificado sin cambios. 4 CPU/40 GiB/swap adicional=0 en contenedores,
guardas térmicas existentes intactas, sin cambio de potencia.
Supervisión de solo lectura: helper `/tmp/opencode/barranco_sparse_status.py`
con transporte y bindings de la campaña. No usar un recolector que lance/reintente.

## Alcance inicial autorizado y estado previo al lanzamiento SfM

Se autorizó limpiar las diez hijas elegidas preservando thesis/tesis_cava,
resolver fwupd en 015, preparar PyCOLMAP 3.11.1 en la maestra y descargar
los insumos nuevos directamente a /data. **No se lanzó SfM ni densa.**
No hay encadenamiento automático descarga → reconstrucción.
Las 14 anclas y la colocación manual de 026 se preservaron.

Campaña: `/home/exitoso/lab-deploy/.state/campaigns/barranco-running-20261116/`.
`assignments.json` es el inventario congelado de Drive con IDs y tamaños exactos.
`download-launch.json` y `download-status.json` contienen arranque y observación.
En la última consulta los diez workers estaban vivos, descargando y sin error.
No interpretar ese estado como descarga terminada.

## Reparto

| Bloque | Hija |
|---|---|
|010|L507_007|
|011|L507_015|
|014|L507_021|
|015|L507_009|
|019|L507_004|
|020|L507_005|
|021|L507_002|
|022|L507_011|
|016-023|L507_022|
|027|L507_008|

Origen: Drive `PRIVATE_DRIVE_ID`, diez carpetas `_running`.
Total: 25 archivos, 42.359.446.371 bytes; 17 MP4, siete SRT y un PNG.
Se excluyeron `old` y proxies LRF. 016-023 incluye teléfono y siete MP4 DJI.
Raíz por hija:
`/data/photogrammetry/campaigns/barranco-running-20261116/cuadra-<bloque>`.
Cada descarga valida tamaño, cabecera y SHA256 calculado; sin SHA remoto
conocido no afirmar comparación contra un hash independiente de Drive.
El worker es snapshot de `drive_download_worker.py`, con reservas de
50 GiB en /data y 3,75 GiB en /. Es download-only.

## Limpieza y preparación

- Se limpiaron cachés APT en las diez; no se desinstalaron paquetes por limpieza.
- 004: eliminados los ZIP/parciales académicos autorizados de Descargas,
  63,159 GiB recuperados, tras revisar nombres protegidos y archivos abiertos.
- Limpieza acotada de cachés pip/uv/CUDA y archivos de paquetes Conda antiguos:
  no se borraron entornos ni paquetes extraídos, proyectos o modelos HuggingFace.
- 007: caché de navegador, tres instaladores Chrome y revisiones Snap
  desactivadas code/278, firefox/8568 y snapd-desktop-integration/387.
  **/ sigue ajustado: 5,31 GiB libres**, frente a 2,9 GiB iniciales.
  Se preservaron env_isaaclab y todo thesis/TESIS_NO_BORRAR.
- 021: / pasó a 9,43 GiB libres.
- Docker/containerd se arrancaron en las diez, sin habilitar arranque automático.
  DockerRootDir verificado en `/data/photogrammetry/runtime/docker`.
- Se comprobaron los IDs de las imágenes certificadas y pruebas efímeras
  de importación PyCOLMAP/CLI COLMAP y operación mínima CUDA con PyTorch.
  Sin descarga de imágenes, sin reconstrucción y sin contenedores de prueba vivos.
- Se hizo daemon-reload en 008 para resolver advertencias de unidades pendientes.
- 004 conserva fallos de servicios gráficos: aceptados por el usuario;
  CUDA dentro de la imagen certificada funciona.
- 015: fwupd 1.9.33 y libfwupd2 1.9.34 eran incompatibles.
  Se actualizó únicamente fwupd a 2.0.20 y se añadió libfwupd3 2.0.20;
  no hubo eliminaciones. Servicio activo, compile/runtime coincidentes,
  `dpkg --audit` limpio. **No se instaló firmware ni se reinició el equipo.**
- PID 1206750 de 015 ya había desaparecido antes de actuar.
  Era train.py de A2Summ_baseline (resumen vídeo/texto), no Barranco.

## Versiones: NO confundir instalación con migración completa

Las imágenes certificadas usan **PyCOLMAP 3.11.1**, no 3.13.
Se creó `/data/barranco/runtime/alignment311/` en la maestra con
pycolmap 3.11.1, numpy 2.4.6, scipy 1.17.1, shapely 2.2.0 y Pillow 13.0.0.
Lee la 026 original en solo lectura: 1.577 imágenes / 751.619 puntos.
La campaña nueva registra ese Python como runtime de referencia.

**La app/worker de alineación NO se migró:** sigue en alignment313.
El código exige 3.13 y usa Rig; las pruebas bajo 3.11.1 tuvieron
12 errores en 44 tests por ausencia de `pycolmap.Rig`.
No se rebajó el guard ni se reemplazó el runtime 3.13 en uso.
Migrar toda la maestra requiere adaptar/probar el motor y binario CLI,
no basta con cambiar pip o rutas. No afirmar estandarización completa.
La app respondió ready y la colocación 026 sigue manual_unvalidated,
job_id=null, geometry_changed=false.

## Restricciones y siguiente paso

La autorización posterior de nueve SfM se detalla arriba; no iniciar otras
reconstrucciones al terminar descargas.
016-023: primero sparse terrestre, revisión y después incorporación incremental DJI.
No tocar campañas existentes de 006/026, energía, potencia ni guardas térmicas.
Los recibos de preparación/limpieza están en `preflight-receipts/` de esta campaña.
Los helpers administrativos están en `/tmp/opencode/barranco_*.py`.
