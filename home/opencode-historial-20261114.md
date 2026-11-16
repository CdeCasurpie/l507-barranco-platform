# HISTÓRICO hasta 14/nov/2026 — Barranco: ROI, 15 mallas y simplificación

> Archivo conservado íntegro como antecedente. Sus estados «actuales» y próximos
> pasos NO son los vigentes. Leer primero `/home/exitoso/home/opencode.md`.

> **Actualización operativa 15/nov/2026:** leer primero
> [`OPERACION-20261115.md`](OPERACION-20261115.md). El conjunto activo excluye 023,
> se preservaron entradas de texturizado en `/data/barranco/active/`, se retiraron
> las densas centrales y la campaña antigua de mallas, y se lanzaron tres
> experimentos de celular hasta densa. Los estados de disco y disponibilidad de
> densas descritos abajo son históricos.

**Actualizado: 14 de noviembre de 2026, después de investigar y planificar el
texturizado fotográfico de la malla actual y de futuras reparaciones manuales.**
Documento principal para continuar en otro chat. Leer primero las secciones
1–3: son el estado actual, no el estado del arranque de la conversación anterior.
Comunicación con el usuario: español, concreta y orientada a resultados.

## 0. Lectura rápida para otra IA

**El trabajo de generación está terminado.** Se completaron los 15 polígonos,
las 15 mallas Delaunay, la simplificación aprobada del 70 % y la entrega
multiobjeto. Después, el usuario pidió investigar y planificar la reproyección
de los fotogramas originales sobre esta malla, incluidos triángulos que añada
manualmente en Blender. **La investigación y el plan están documentados en 10b;
todavía no se ha ejecutado el texturizado.** La petición más reciente fue
actualizar este `.md` con esa información para continuar en otra sesión.

### Qué abrir primero

- Contexto principal: **`/home/exitoso/home/opencode.md`**.
- Proyecto/código: **`/home/exitoso/home/barranco-roi/`**.
- Entrega vigente:
  **`/home/exitoso/home/barranco-roi/exports/mesh-campaign-20261112/simplified_70pct_blocks/`**.
- Archivo único editable de Blender:
  **`barranco_15_manzanas_70pct.blend`**, 815,66 MB, **15 objetos independientes**.
- Proyecto MeshLab: **`barranco_15_manzanas_70pct.mlp`**, con sus 15 PLY en
  **`meshes/`**; estos suman 600,76 MB.
- Instrucciones de entrega: **`LEEME.md`** en esa misma carpeta.

### Fuentes de verdad y orden de lectura

1. `simplified_70pct_blocks/delivery.json`: entrega completada, pesos exactos,
   hashes, conteos y archivos individuales.
2. `simplified_70pct_blocks/blender-audit.json`: comprobación después de reabrir
   el `.blend`, 15 objetos, 15 mallas únicas, geometría y colores verificados.
3. `simplified_70pct_blocks/reports/NNN.json`: parámetros, tiempos y distancias
   por manzana. El modo final **no rechaza resultados por distancia**.
4. Secciones 1–3 y 10a de este documento: estado y decisiones de la entrega final;
   sección **10b**: investigación y plan nuevo de texturizado fotográfico.
5. Las secciones del piloto conservador y el archivo histórico explican el
   desarrollo previo; no sustituyen el estado final ni sus informes.

La última revisión de este contexto contrastó los metadatos de entrega y
auditoría; no volvió a ejecutar el lote ni a modificar las mallas.

### Restricción principal de edición

El usuario hizo énfasis en que las manzanas se pudieran editar individualmente
en Blender: **15 objetos, 15 datablocks de malla, sin instancias ni fusión de
geometría entre bloques**. Un único material RGB compartido no comparte la malla.
Las coordenadas ya están alineadas; no volver a aplicar las transformaciones.

La nueva intención es preparar el texturizado fotográfico y la reproyección tras
ediciones manuales; el siguiente paso propuesto es un piloto en 025 (sección 10b).
Antes de
reutilizar un archivo entregado en una sesión futura, comprobar si el usuario
lo ha editado; no reemplazar su trabajo por una regeneración del pipeline.

## 1. Estado actual y última intención del usuario

### Ya completado

1. Se terminó el CSS pendiente y se actualizó el README del selector web.
2. Se montó `/data` de la maestra y se arrancó el selector de las 15 manzanas.
3. **El usuario dibujó y guardó polígonos reales para las 15 manzanas.**
4. Se montaron los volúmenes pendientes de las hijas, respetando los montajes
   existentes y los trabajos de un compañero.
5. Se generalizó el procesamiento nativo multilote, se ejecutaron 14 Delaunay
   en paralelo y se reutilizó el piloto 025 después de verificarlo.
6. **Las 15 mallas terminaron y se recibieron en la maestra, sin fallos pendientes.**
7. Se creó un PLY combinado con las 15 para verlas juntas.
8. Se implementó y ejecutó un piloto de simplificación sobre **025**:
   normales PCA locales, RANSAC, regularización planar y decimación QEM.
9. Se publicó una versión conservadora de 025 con error medido hasta 7 cm.
10. Después, el usuario pidió probar **eliminar el 50 % de las caras sin rechazo
    por distancia**, y luego **eliminar el 70 %**. Ambas pruebas existen y se
    abrieron correctamente en MeshLab.
11. El usuario aprobó la prueba 70 % y autorizó aplicarla a todas. **Las 15 ya
    están simplificadas y entregadas**, con la 025 aprobada reutilizada exactamente.
12. Se creó y reabrió un **`.blend` autocontenido con 15 objetos de malla
     independientes**, 15 datablocks únicos, cero instancias y geometría/colores
     verificados. También hay un proyecto MeshLab de 15 capas y 15 PLY individuales.
13. El 14/Nov se investigó la viabilidad de texturizar la malla actual y caras
    añadidas manualmente usando fotogramas y cámaras originales. Se consultaron
    las 15 tablas de cámaras: **5.691 imágenes registradas, sin rutas de imagen
    faltantes en esas escenas**. Se localizó `TextureMesh` y se revisó su código
    upstream 2.3.0. Se propuso un plan por fases; **no se ejecutó ningún piloto
    ni se modificaron mallas, UV, materiales o imágenes**.

### Punto exacto para retomar

**La última petición quedó completada: 70 % de caras eliminadas en las 15,
sin rechazo por distancia, reunidas como bloques editables independientes.**
El usuario hizo énfasis en que no estuvieran fusionadas ni como instancias.

Lo anterior es la entrega geométrica completada. **La intención nueva es
texturizarla con las fotografías originales y poder reproyectar después de añadir
triángulos manualmente.** Se pidió investigar y planificar; el plan está en 10b.
El último pedido de esta sesión es conservar ese contexto en este documento.

Entrega actual: `exports/mesh-campaign-20261112/simplified_70pct_blocks/`.
Abrir **`barranco_15_manzanas_70pct.blend`** en Blender. Son 15 objetos
`Manzana_NNN`, cada uno con su propia malla y un único usuario, sin padres ni
instancias. Peso: **815.655.675 bytes (815,66 MB)**. Se auditó después de reabrir.

MeshLab: `barranco_15_manzanas_70pct.mlp`, con 15 capas referenciadas en `meshes/`.
Suma de PLY: **600.760.986 bytes (600,76 MB)**. Total: **15.023.874 vértices,
28.876.792 triángulos**. `delivery.json`, `LEEME.md` y `pesos_por_manzana.csv`
contienen pesos individuales, hashes y trazabilidad. Finalizó a las **03:36:56**
del 12/Nov/2026; tiempo total de servicio **12 min 3 s**, pico de memoria 10,2 GiB.

El PLY combinado anterior de 1,99 GB sigue siendo el conjunto Delaunay original;
para editar los bloques simplificados usar el `.blend` nuevo, no ese PLY unido.
Los pilotos conservadores y los previews anteriores quedan como antecedentes.

## 2. Rutas para abrir los resultados ahora

Proyecto y directorio de trabajo de los comandos:
**`/home/exitoso/home/barranco-roi/`**.

### 15 mallas Delaunay y combinado

Raíz de entrega: `/home/exitoso/home/barranco-roi/exports/mesh-campaign-20261112/`.

```text
exports/mesh-campaign-20261112/
  manifest.json                         15 resultados, selecciones y hashes
  001/manzana_001_world.ply
  ...
  025/manzana_025_world.ply
  barranco_15_manzanas_world.ply          combinado de las 15 originales
  barranco_15_manzanas_world.json         hash y rangos por manzana
  simplified_70pct_blocks/               ENTREGA ACTUAL: LAS 15 SIMPLIFICADAS
    barranco_15_manzanas_70pct.blend      un archivo, 15 objetos y mallas únicos
    barranco_15_manzanas_70pct.mlp        15 capas MeshLab; referencia meshes/
    meshes/manzana_NNN_simplified_70pct.ply
    reports/NNN.json                    métricas individuales y distancias sin rechazo
    delivery.json                       pesos finales, hashes y 15/15 completadas
    pesos_por_manzana.csv
    LEEME.md
    blender-audit.json                  auditoría después de reabrir el .blend
    blender-build.json
    blender-inputs.json, blender-inputs/ auxiliares binarios de construcción
    work/NNN/                           referencias retenidas, progreso y logs
  simplified/
    report.json                         índice del piloto conservador (solo 025)
    025/
      manzana_025_simplified.ply         variante conservadora verificada
      comparacion_025.mlp                proyecto MeshLab con original y derivado
      report.json
      REPORTE.md
      roi_025.json
    pilot_025_5cm_v1/                    primer diagnóstico; candidatos históricos
    pilot_025_5cm_v2/                    comparación y verificaciones posteriores
    pilot_025_5cm_v2_guarded/             refinamiento que produjo la versión verificada
    previews/
      025_50pct_no_distance_limit/
        manzana_025_50pct_preview.ply
        comparacion_025_50pct.mlp
        report.json
        REPORTE.md
      025_70pct_no_distance_limit/
        manzana_025_70pct_preview.ply     prueba aprobada y reutilizada para 025
        comparacion_025_70pct.mlp         original, conservadora, 50 % y 70 %
        generation.json
        planes.json
        report.json
        REPORTE.md
```

Los `.mlp` contienen rutas relativas a las mallas y matrices identidad:
permiten comparar activando/desactivando capas. Conservar la estructura de
directorios si se trasladan estos proyectos.

### Métricas de geometría

Tamaños MB/GB en esta tabla son decimales, no MiB/GiB.

| Resultado | Vértices | Triángulos | Bytes |
|---|---:|---:|---:|
| Suma de las 15 mallas separadas | — | — | 1.985.740.526 |
| PLY combinado de las 15 | 48.846.291 | 96.387.817 | 1.985.736.366 |
| Suma PLY de las 15 simplificadas 70 % | 15.023.874 | 28.876.792 | 600.760.986 |
| Blender con 15 objetos simplificados | 15.023.874 | 28.876.792 | 815.655.675 |
| 025 original | 2.604.307 | 5.165.895 | 106.221.538 |
| 025 conservadora verificada | 2.356.676 | 4.671.110 | 96.074.876 |
| 025 prueba eliminar 50 % | 1.312.490 | 2.582.738 | 53.263.250 |
| 025 prueba eliminar 70 % | 795.942 | 1.549.642 | 32.084.781 |

La diferencia de bytes entre suma y combinado es principalmente de cabeceras.
El combinado concatena geometría alineada, corrige índices y conserva RGB:
**no suelda costuras ni elimina automáticamente solapes entre manzanas**.
Su JSON permite localizar cada manzana mediante rangos de vértices y caras.

### Hashes de referencia

| Archivo | SHA256 |
|---|---|
| Combinado de las 15 | `4119f419e9a7a36612af7a35bb110ab2ec97f01f14e69b0cc40e0679e4a85c3a` |
| 025 original | `e8ca206850e6127b272179f977fc622c1eab4df8f90b4128ece4e29f7368ddd9` |
| 025 conservadora | `98123f1fdd1c94c1e1406a11f947461b1d56307cb5b8da5fe6cd5b43d76aafec` |
| 025 prueba 50 % | `94ea254df8a70fabc794e016a073efcd2de7f448fb5d4fcb6774056936c7b17e` |
| 025 prueba 70 % | `bcb7e42226f4b42c457d7dc61299cf78f61b1192535480f1ce18c060a7ecbd77` |
| `.blend` de las 15 simplificadas | `a32eb1eb50098111351950efa87df49d07f06607899349b1d4b598ae1aa6d1e0` |

## 3. Decisiones vigentes y siguiente trabajo posible

- Mantener las mallas separadas además de los combinados para visualización.
- El usuario hará las costuras, merges, nuevos triángulos y reparación de huecos
  manualmente en Blender.
- **No completar automáticamente huecos ni inventar superficies/texturas.**
- Después de la edición, la ruta preferida es reproyectar las fotografías
  originales sobre la geometría aprobada, con cámaras coherentes.
- Las mallas actuales tienen **RGB por vértice**, no un atlas fotográfico nuevo.
- Solo **023** usa colocación manual relativa a **025**, el ancla. Las otras
  transformaciones permanecen como estaban.
- Los productos `*_world.ply` y `*_simplified.ply` ya están en `map_world`:
  **no volver a aplicar `world_from_block` al importarlos**.
- El usuario primero aceptó probar 5–7 cm; luego autorizó expresamente las
  pruebas de eliminación del 50 % y 70 % **sin rechazo por error de distancia**.
  Son modos diferentes, ambos conservados; no presentar el 70 % como si cumpliera 7 cm.
- En las pruebas agresivas se desactiva el rechazo por error posterior a QEM.
  La detección de planos conserva su tolerancia de 5 cm: no son la misma cosa.
- El usuario **ya aprobó el 70 % para todas**. Se completó el lote en la maestra
  con dos procesos simultáneos. La restricción central de esta entrega es
  conservar objetos y geometría de cada manzana independientes para Blender.

Pendientes posibles, según lo que pida el usuario:
1. Retomar el plan de 10b: validar cámaras y coordenadas y realizar un piloto de
   texturizado de 025 cuando el usuario pida ejecutarlo.
2. Probar reproyección sobre una reparación manual observada por las cámaras;
   después de revisión visual, extender el procedimiento a las 15 manzanas.
3. Confirmar el renderizador/FPS reales de la sesión si vuelve a consultar fluidez.

**No volver a pedir polígonos ni relanzar mallado o simplificación: las tres
etapas ya terminaron. Consultar primero `simplified_70pct_blocks/delivery.json`.**

## 4. Estado operativo comprobado al escribir este resumen

- `/data` de la maestra está montado en `/dev/nvme0n1p6`, ext4,
  opciones `rw,nosuid,nodev,relatime`.
- PARTUUID: `5359ec76-59f3-43fa-84e8-3b49af017460`.
- Espacio observado después de la entrega (`df -h`): aproximadamente **52 GiB
  libres en `/data`** y **15 GiB en el home**.
- Reserva implementada en `/data`: **50 GiB**. Evitar escribir allí derivados
  grandes; los resultados nuevos de esta sesión van a `home/barranco-roi/exports/`.
- El selector estuvo activo y `/api/health` respondió `ready` con las 15; en la
  última consulta posterior al lote el servicio aparece **inactivo**. Si se
  necesita volver a seleccionar, inspeccionar y arrancar la instancia local.
- URL local del selector: **http://127.0.0.1:8765**.
- El watcher de mallas ya terminó correctamente: `collection.json` contiene
  `collected: 15`, `failed: {}`. Recepción final: **12/Nov/2026 01:05:58**.
- Los servicios transitorios del watcher y del último visor ahora aparecen
  inactivos/no encontrados. Eso no significa que se perdieran los resultados.
- `barranco-simplify-all-70.service` terminó con `Result=success`; no quedan
  trabajos de este lote. No volver a ejecutar `run` solo para abrir los archivos.
- Las hijas no se volvieron a inventariar para redactar este resumen: el inventario
  de campaña es una observación histórica, no una garantía de disponibilidad actual.
- No se habilitó inicio automático de estos servicios.

Comprobaciones locales de consulta:

```bash
findmnt --mountpoint /data
df -h /home/exitoso /data
systemctl --user status barranco-roi
curl --fail --silent --show-error http://127.0.0.1:8765/api/health
```

Si en otra sesión `/data` estuviera desmontado, comprobar primero dispositivo y
contenido del punto de montaje; no ocultar archivos existentes. Montaje autorizado:

```bash
sudo mount -t ext4 -o nodev,nosuid /dev/disk/by-partuuid/5359ec76-59f3-43fa-84e8-3b49af017460 /data
```

Para arrancar la web **solo si no está activa**, después de verificar el servicio:

```bash
systemd-run --user --unit=barranco-roi --working-directory=/home/exitoso/home/barranco-roi -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=200% -p Nice=10 /data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/app.py
```

## 5. Código y runtimes: qué hace cada archivo

Todas las rutas de esta sección son relativas al proyecto, salvo indicación.

| Archivo/directorio | Función |
|---|---|
| `app.py` | Servidor HTTP local del selector; puerto 8765; `--state-dir` para pruebas aisladas |
| `roi/core.py` | PLY escalar, geometría XY, recorte y utilidades de estado |
| `roi/catalog.py` | Catálogo activo, lectura sparse, matrices y colocación exclusiva de 023 |
| `roi/multi.py`, `roi/service.py` | Revisiones, JSON por manzana, jobs y aislamiento de datos |
| `web/` | Editor Canvas local; contexto de 15 bloques, enfoque, dibujo y guardado |
| `mesh_campaign.py` | Inventario, fijación de JSON, despliegue, consulta y recepción de campaña |
| `mesh_worker.py` | Worker autónomo en cada hija; stdlib y binarios propios |
| `roi/mvs_interface.py` | Lectura de cámaras MVSI, remapeo entre lotes y reubicación de rutas de fotos |
| `runtime/tools/mesh_roi.cpp`, `mesh_roi` | Muestreo nativo en streaming y filtrado/publicación de mallas |
| `combine_meshes.py` | Concatenación de las 15 PLY; validación y desplazamiento de índices |
| `simplify_meshes.py` | Pilotos por bloque, QEM, planos, mediciones, feedback y publicación verificada |
| `preview_simplification.py` | Pruebas sin rechazo por distancia; porcentajes de reducción; **especializado en 025** |
| `batch_simplify_70.py` | Lote aprobado para 15 bloques; 025 exacta reutilizada, dos workers locales, medición y empaquetado |
| `package_simplified_blocks.py` | Proyectos MeshLab, buffers para Blender, CSV y manifiesto de entrega |
| `blender_blocks.py` | Se ejecuta dentro de Blender; construye y audita 15 objetos únicos; solo stdlib, sin NumPy |
| `tests/test_block_delivery.py` | Prueba real de guardado y reapertura en Blender, con geometría y RGB de 15 objetos |
| `pilot.py`, `pilot_remote.py` | Piloto histórico 025; siguen especializados, no usar como workers generales |
| `runtime/openmvs/` | OpenMVS 2.3 aislado: ejecutables y bibliotecas |
| `runtime/meshdeps/` | PyMeshLab 2025.7.post1 aislado |
| `state/` | Selecciones y estado reales; no versionar ni reemplazar por fixtures |

Python para NumPy/SciPy/Shapely/PyMeshLab:
**`/data/barranco/runtime/alignment313/bin/python`** (Python 3.11).
El nombre del entorno no cambia la versión. El Python del sistema no tiene
las dependencias científicas necesarias. Los scripts de campaña/SSH usan
`python3` del sistema y el adaptador existente con `pexpect`.

OpenMVS necesita `LD_LIBRARY_PATH` apuntando a `runtime/openmvs/lib` **solo en
su proceso**; el worker lo configura. No cambiar bibliotecas/drivers del sistema.

## 6. Selector, JSON y coordenadas

Las 15 selecciones quedaron fijadas para la campaña en:
`state/mesh-campaign-20261112/selections/roi_NNN.json`.

- Estado vivo de 025: `state/selections/*.json` (layout histórico).
- Estado vivo de las otras: `state/blocks/NNN/selections/*.json`.
- JSON vigente de la web: `state/exports/roi_NNN.json`.
- Matrices y procedencia: `state/effective-transforms.json`, `state/alignment-review.json`.
- Las selecciones fijadas de campaña son la referencia de esas mallas, aunque
  posteriormente se edite una revisión en la web.
- El JSON ROI de la web puede seguir indicando `deployment_status: not_submitted`:
  el estado del lanzamiento separado está en la campaña, no se debe inferir de ese campo.

API: la manzana se pasa con **`?block=NNN`**, no `/api/blocks/NNN`.

```text
GET /api/blocks
GET /api/alignment
GET /api/overview
GET /api/dataset?block=023
GET /api/selections?block=023
GET /api/roi.json?block=023
POST /api/validate?block=023
POST /api/selections?block=023
POST /api/jobs?block=023
GET /api/jobs?block=023
GET /pilot/                         galería histórica 025
```

POST exige JSON y `X-ROI-Client: local-editor`, con Host/Origin local coherentes.
Ausencia de `block` conserva compatibilidad con 025. Guardar no lanza mallas.

Marco métrico local: `map_world`, EPSG:32718. Origen proyectado:
`[279932.4471962734, 8657453.760760272, 116.53700000000002]`.
Se suma ese origen para obtener coordenadas proyectadas. No sustituir el marco
local por coordenadas UTM grandes en float32 ni interpretar los JSON como WGS84.

Corrección 023: configuración en `config/manual_alignment_023.json`.
Convención Blender XYZ, columnas: `T @ Rz @ Ry @ Rx @ S`.
`T23_efectiva = T25_original @ inverse(M25_capturada) @ M23_capturada`.
Para un producto 023 ya colocado con la matriz antigua se necesita el delta
`T23_efectiva @ inverse(T23_antigua)`; los PLY world actuales ya usan la efectiva.
Las matrices numéricas completas y capturas originales están en el archivo histórico.

## 7. Campaña Delaunay: máquinas, ejecución y trazabilidad

| Manzana | Máquina | Lotes densos |
|---|---|---:|
|001|L507_001|7|
|002|L507_002|4|
|003|L507_003|13|
|004|L507_004|8|
|005|L507_005|17|
|007|L507_007|8|
|008|L507_008|10|
|009|L507_009|12|
|012|L507_012|13|
|013|L507_006|12|
|017|L507_010|9|
|018|L507_011|10|
|023|L507_023|12|
|024|L507_024|11|
|025|L507_015|1|

Se observaron trabajos ajenos de GPU en **L507_001 y L507_011**, usando unos
17 GiB de VRAM cada uno. No se detuvieron. Nuestros workers usaron CPU:
6 hilos/40 GiB de límite en las libres y 2 hilos/24 GiB en las compartidas,
swap desactivada, Nice=10, IOWeight=20. L507_001 permanece en `/mnt/datos`:
sus rutas de campaña se adaptaron sin mover el montaje ni crear otro.

Detalles del procesamiento:
- Se comparan poses/intrínsecos y nombres para mapear las cámaras de cada lote
  a la escena global. No concatenar índices locales de visibilidad directamente.
- Se recorre cada PLY nativo comparando **cada registro escalar** con la nube
  escalar global en el orden de `dense-batches.json/ranges`; se verifica su SHA.
- Se conserva un punto original por vóxel mundial de **10 cm**, con vistas y
  pesos originales remapeados. Cuadrícula multilote anclada en `[0,0,0]`.
- El piloto histórico 025 usaba un origen de cuadrícula dependiente de su muestra;
  misma resolución, sin afirmar que el muestreo sea idéntico.
- OpenMVS: Delaunay + visibilidad, min-point-distance=0, constant-weight=0,
  decimate=1, remove-spurious=0, remove-spikes=0, close-holes=0, smooth=0,
  crop-to-roi=0, `--cuda-device -2`.
- Filtrado final por polígono completo, incluidas concavidades, y aristas de
  hasta **0,45 m**. Se admiten caras verticales válidas.
- OpenMVS puede mover/separar algunos vértices en su limpieza interna no manifold;
  no exigir identidad exacta de todos los vértices de la malla con los puntos
  muestreados. Los filtros iniciales de soporte de color se corrigieron.
- `filter-update.json` registra actualizaciones de ese binario. Se reutilizaron
  las reconstrucciones terminadas al corregir solo filtrado/publicación.

Los workers vigilan temperatura (95 °C inmediata o 90 °C durante 30 s), 8 GiB
de RAM disponible y reserva de disco de 50 GiB, deteniendo solo procesos propios.
El límite de memoria de un cgroup incluye caché: no confundir `MemoryPeak` con
RSS exclusivo del algoritmo.

Estado persistido:

```text
state/mesh-campaign-20261112/
  manifest.json                       asignaciones y JSON fijados
  selections/                         15 snapshots ROI
  inventory.json                      recursos y montajes observados
  camera-preflight-NNN.json            comprobaciones previas
  runtime.json, runtime.tar.gz         bundle y huellas
  launch.json                         lanzamientos
  status.json                         última consulta a workers
  collection.json                     15 recibidas; hashes y resultados
  filter-update.json                  parche de publicación de mallas
```

En cada hija: `MOUNT/photogrammetry/roi-campaigns/mesh-20261112/NNN/`:
`assignment.json`, `status.json`, `camera-audit.json`, `sampling.json`,
`native_10cm.ply`, `scene.mvs`, `mesh_local.ply`, `delaunay.log`, `filtering.log`,
`result.json` y `manzana_NNN_world.ply`. Intermedios grandes permanecen allí.

Comandos del coordinador, desde el proyecto:

```bash
python3 -B mesh_campaign.py status
```

`inspect`, `prepare`, `launch`, `watch` y `repair-filter` también existen.
`inspect` guarda un inventario nuevo; `prepare` fija datos/bundle; `launch`
despliega e inicia workers; `watch` consulta y recibe; `repair-filter` actualiza
nuestro binario y puede reanudar workers propios fallidos. **No ejecutarlos de
nuevo por leer este resumen: la campaña terminó.**

`mesh_campaign.py` está especializado en la campaña/fecha actual y contiene IPs
observadas el 12/Nov/2026. DHCP puede cambiarlas. Antes de reutilizarlo para
operaciones remotas, descubrir y verificar identidad por tag+MAC mediante el
toolkit del laboratorio. No confiar solo en IPs viejas.

El C++ se compiló así, cuando fue necesario:

```bash
g++ -O3 -std=c++17 -Wall -Wextra -static-libstdc++ -static-libgcc runtime/tools/mesh_roi.cpp -lcrypto -o runtime/tools/mesh_roi
```

Sus modos son `sample CONFIG BATCHES SCALAR OUTPUT` y
`finish CONFIG NATIVE MESH OUTPUT`; el worker construye los archivos de entrada.
No usar `crop_native.cpp` del piloto antiguo como si ya fuera general: conserva
suposiciones particulares de 025/92 cámaras.

## 8. Combinar las mallas

`combine_meshes.py` verifica los 15 hashes, copia XYZ/RGB sin transformarlos,
concatena caras desplazando los índices, comprueba todos los índices finales
y publica el PLY más JSON con rangos por bloque.

Se ejecutó con memoria acotada (2 GiB) y cuota de 200 %. El archivo ya existe.
El script **rechaza sobrescribirlo**; para generar otro conjunto/otra variante
hay que adaptar las rutas/manifiesto y elegir un nombre nuevo.

Invocación usada, para referencia, no para repetir ahora:

```bash
systemd-run --user --scope --unit=barranco-combine --quiet -p MemoryMax=2G -p MemorySwapMax=0 -p CPUQuota=200% nice -n 10 /data/barranco/runtime/alignment313/bin/python -B combine_meshes.py
```

En `--scope`, `Nice=10` no es una propiedad admitida aquí: usar `nice -n 10`
como arriba. En servicios normales `systemd-run --user`, `-p Nice=10` sí funcionó.

## 9. Simplificación conservadora: método, medición y uso

Detalle adicional: `barranco-roi/SIMPLIFIED.md`.

Proceso implementado:
1. Verificar fuente y retirar componentes solo si cumplen **ambas** condiciones:
   diámetro <0,20 m y área <0,02 m². En 025: 115 componentes, 417 caras,
   1,6208 m² de superficie sumada. Esta eliminación se contabiliza por separado.
2. Normales PCA con 24 vecinos; las normales crudas de triángulos eran demasiado
   irregulares para detectar buenos planos.
3. RANSAC (semilla 25), hasta 32 modelos, tolerancia 5 cm, normales 12°.
   Regiones conectadas por caras, con al menos 2 m² y 100 caras.
4. Regularizar solo interiores inequívocos, factor 0,65, protegiendo bordes y
   cambios de superficie. Movimiento planar máximo preliminar: **3,25 cm**.
5. QEM con preservación de bordes, normales y topología y ponderación planar.
   El filtro no tiene un umbral directo de error en centímetros: hay que medirlo.
6. Filtrar contra el ROI y transferir RGB desde la referencia. No rellenar huecos.
7. Si hay puntos fuera de 7 cm, congelar sus vecindarios y dos anillos de caras;
   repetir la decimación solo en el resto seleccionado, hasta cuatro iteraciones.
   Se comprueba que QEM no haya movido los vértices congelados.

Las aristas de una malla decimada pueden superar 0,45 m en superficies planas:
no reaplicar el límite de arista de reconstrucción para anular la simplificación.

### Medición correcta y correcciones del piloto

- Distancias de puntos a **triángulos**, en ambos sentidos; no distancias entre
  vértices como sustituto de error superficial.
- Primera evaluación con muestras de caras/aristas; la definitiva recorre todos
  los vértices y añade muestras de superficies, usando las posiciones float32
  que se publican realmente.
- En PyMeshLab, `samplevert=True` **no significa todos los vértices**: se solicita
  una pasada separada con `samplenum=N_vertices`, solo vértices, y se verifica
  `all_vertex_samples == N_vertices`; después otra pasada de caras/aristas.
- MeshLab guarda tanto puntos muestreados como puntos más cercanos, con valores
  duplicados de distancia: contar solo la capa `Hausdorff Sample Point`.
- Los informes v1/v2 contienen aceptaciones **preliminares** ya superadas por
  comprobaciones más completas. La autoridad final es `simplified/025/report.json`
  y la verificación de `pilot_025_5cm_v2_guarded/`.
- En 025 se midieron 2.603.860 vértices de referencia retenida y 2.356.676 de salida,
  además de unas 200.000 muestras de caras/aristas por sentido.
- Resultado conservador final: P99 peor **2,097 cm**, máximo observado **6,810 cm**.
  No es una prueba exhaustiva del máximo continuo dentro de cada triángulo.

### CLI de simplificación

Todos los comandos científicos se ejecutan con el Python del runtime. Ejemplos
para un **ensayo nuevo**, con un ID nuevo; no repetir sobre carpetas existentes:

```bash
/data/barranco/runtime/alignment313/bin/python -B simplify_meshes.py --block 025 --tolerance 0.05 --outer-tolerance 0.07 --run-id NUEVO_ID
/data/barranco/runtime/alignment313/bin/python -B simplify_meshes.py --block 025 --tolerance 0.05 --outer-tolerance 0.07 --run-id NUEVO_ID --verify-run
/data/barranco/runtime/alignment313/bin/python -B simplify_meshes.py --block 025 --tolerance 0.05 --outer-tolerance 0.07 --run-id NUEVO_ID --refine-run
```

`--refine-run` usa los puntos medidos fuera de tolerancia de la variante planar,
crea `NUEVO_ID_guarded`, valida completamente y publica solo si pasa.
`--publish-run` verifica y publica una variante ya validada; comprueba hashes,
conteos y el número real de vértices evaluados. No interpreta previews agresivas
como versiones que cumplen el límite de 7 cm.

Los pilotos se ejecutaron en servicios propios con **24 GiB de RAM, swap=0,
CPUQuota=400 %, Nice=10**. Las etapas se registran en `status.json`,
`comparison.json`, `verification.json` y `REPORTE.md`. No hay aceleración CUDA
en QEM de PyMeshLab: este trabajo fue CPU, aunque la maestra tenga RTX disponible.

## 10. Pruebas agresivas 50 % y 70 %: última línea de trabajo

`preview_simplification.py` es un generador de **pruebas de 025**, no un batch
genérico para las 15. `--reduction 70` significa **eliminar 70 %, conservar 30 %**.
Admite porcentajes de 1 a 95. Para generalizarlo hay que parametrizar bloque,
fuente, referencia, ROI y nombres de salida; ahora contiene 025 explícitamente.

- 50 %: reutiliza el candidato planar/QEM ya generado en el piloto v2 y verifica SHA.
- Otros porcentajes: recalcula normales/planos y QEM desde la referencia retenida.
- Preserva bordes/normales/topología y recorta el ROI, pero **no aplica el rechazo
  por error posterior ni el feedback de congelación por exceder 7 cm**.
- Mide y reporta distancias completas igualmente; `distance_gate_enabled: false`
  y `classification: visual_preview` distinguen estos resultados.

| Variante 025 | P99 peor | Máximo observado | Tiempo |
|---|---:|---:|---|
| Conservadora verificada | 2,10 cm | 6,81 cm | refinamiento final 91,05 s, incluidas validaciones |
| Eliminar 50 % sin rechazo | 6,03 cm | 25,70 cm | candidato reutilizado; medición adicional 16,68 s |
| Eliminar 70 % sin rechazo | 8,34 cm | 38,37 cm | generación 58,46 s + medición 14,03 s |

La regularización conserva su tolerancia de detección de planos de 5 cm en
ambas pruebas. Lo que cambió por petición del usuario es el rechazo de la
simplificación por distancia, no el umbral de consenso de RANSAC.

Comando usado para el 70 %, con límites:

```bash
systemd-run --user --scope --unit=barranco-preview-025-70-generate --quiet -p MemoryMax=12G -p MemorySwapMax=0 -p CPUQuota=400% nice -n 10 env OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 /data/barranco/runtime/alignment313/bin/python -B -u preview_simplification.py --reduction 70
```

El archivo ya existe. Una nueva ejecución lo reutiliza si su huella coincide
con `generation.json`, pero vuelve a medir y escribir informes; no hacerlo solo
para abrirlo. Para visualizar basta abrir el PLY/MLP existente en MeshLab.

Opcionalmente `--desktop-pid PID` toma únicamente las variables de display de
un proceso `bash` o `meshlab` del mismo usuario y lanza un visor separado con
límites. **Los PID de esta conversación ya pueden no existir**; no copiarlos.
Si el visor usado como ancla se cerró, usar una terminal propia actual con display
válido o abrir el archivo manualmente. No acceder a sesiones de otros usuarios.

## 10a. Entrega final del 70 %: 15 objetos independientes

El usuario aprobó explícitamente el aspecto del preview 025 y pidió el mismo
tratamiento para las demás, con un conjunto editable por bloques. Se completó
en la maestra, reutilizando la 025 byte por byte; la huella coincide con el preview.

Directorio: `exports/mesh-campaign-20261112/simplified_70pct_blocks/`.

- **Blender:** `barranco_15_manzanas_70pct.blend`, **815,66 MB**, autocontenido.
- **MeshLab:** `barranco_15_manzanas_70pct.mlp`, 2.480 bytes, proyecto de 15 capas
  que necesita la carpeta `meshes/` a su lado.
- **PLY individuales:** `meshes/manzana_NNN_simplified_70pct.ply`, **600,76 MB** sumados.
- Geometría total: **15.023.874 vértices / 28.876.792 triángulos**.
- Pesos por manzana: `LEEME.md`, `pesos_por_manzana.csv` y `delivery.json`.
- Métricas y tiempos de cada bloque: `reports/NNN.json`; logs y referencias:
  `work/NNN/`. Distancias medidas en ambos sentidos, pero sin rechazo por error.

| Manzana | Tamaño PLY (MB decimales) |
|---|---:|
|001|25,71|
|002|29,34|
|003|35,90|
|004|7,36|
|005|56,21|
|007|12,77|
|008|38,93|
|009|46,11|
|012|38,57|
|013|51,42|
|017|59,42|
|018|54,01|
|023|41,74|
|024|71,19|
|025|32,08|

`batch_simplify_70.py` es la generalización para las 15:
verifica cada fuente, retira solo fragmentos diminutos con los mismos criterios
del piloto, calcula normales/planos y ejecuta QEM con la misma configuración.
Dos procesos locales simultáneos. El objetivo real de caras resultó cercano al
70 % eliminado en todas (pequeñas diferencias por la limpieza previa).

El servicio se inició con 40 GiB de memoria, swap=0, CPUQuota=800 % y Nice=10.
La simplificación tardó **701,22 s**; empaquetado, construcción y auditoría llevaron
el total del servicio a **12 min 3 s**, pico de memoria observado **10,2 GiB**.
Construir el `.blend` tardó **12,28 s**. Terminó el 12/Nov/2026 a las **03:36:56**.

### Formato Blender y verificación de independencia

Blender instalado: **5.0.1**. Su Python no tenía NumPy. Se implementó el importador
`blender_blocks.py` con `array`, `hashlib` y `bpy`, sin instalar dependencias.
`package_simplified_blocks.py` prepara buffers XYZ, índices y RGBA en
`blender-inputs/`, descritos en `blender-inputs.json`.

- Hay 15 objetos `Manzana_NNN` y **15 datablocks de malla distintos**.
- Cada malla tiene un solo usuario; `instance_type=NONE`, sin parent.
- Coordenadas y matrices identidad conservan `map_world` sin volver a transformar.
- Color por vértice en atributo `Color`; material y vista sólida configurados
  para ese atributo. Un material compartido no comparte la geometría.
- No se unen vértices ni se sueldan bloques. Cada objeto es seleccionable y editable.
- Se guardó comprimido y se **reabrió en otro proceso Blender**.
- La auditoría verificó conteos, coordenadas e índices completos mediante hashes
  y los colores. `blender-audit.json`: `objects=15`, `unique_mesh_data=15`,
  `geometry_hashes_verified=true`, `colors_verified=true`.

Una prueba de integración adicional creó 15 mallas pequeñas, guardó/reabrió un
`.blend` comprimido y verificó estas mismas condiciones; está en
`tests/test_block_delivery.py` y pasó antes de construir el conjunto real.

### Comandos y continuidad del lote

Desde el proyecto, `batch_simplify_70.py run` coordina todos los workers y la
entrega; `worker --block NNN` procesa una sola manzana. Los resultados ya están
hechos: no ejecutar `run` solo para verlos, porque rehace auxiliares e informes
y podría sustituir tiempos de la ejecución histórica por tiempos de caché.

La finalización llama a:
`package_simplified_blocks.py` → `blender_blocks.py ... build` →
reapertura con `blender_blocks.py ... audit` →
`package_simplified_blocks.py --finalize`.
Blender requiere `--python-exit-code 1` para que errores Python den código de fallo.
El lote está fijado a la campaña y porcentaje actuales; para otra variante elegir
rutas nuevas y revisar `batch_config.json` en vez de sobrescribir esta entrega.

Para transportar solo el archivo editable, basta el `.blend`. Para MeshLab,
copiar `.mlp` y `meshes/` conservando sus rutas relativas. `work/` y
`blender-inputs/` son auxiliares, no necesarios para abrir la entrega.

## 10b. Investigación y plan de texturizado fotográfico (14/Nov/2026)

### Petición del usuario y alcance real de esta sesión

El usuario preguntó si se puede poner textura a cada triángulo de la malla actual
usando los frames originales y las proyecciones de sus cámaras, y si se puede
reproyectar un triángulo nuevo añadido en Blender. Pidió **investigar y planificar**.
Después pidió actualizar este contexto general con lo investigado y planeado.

**Respuesta: sí, es viable**, siempre que la superficie esté observada por alguna
imagen calibrada y su geometría permita una proyección coherente. No es necesario
que la cara haya existido en la reconstrucción original. Crear una cara en Blender
no actualiza automáticamente la textura: habrá que ejecutar una reproyección.

Estado al cerrar esta sesión: investigación de solo lectura y documentación del
plan. **No se han generado atlas, UV ni texturas; no se ha probado `TextureMesh`
sobre nuestra malla, ni se han editado los archivos entregados.** Las fases que
siguen son propuestas, no resultados completados ni una ejecución autorizada
por el mero hecho de actualizar este documento.

### Datos comprobados localmente

Se leyeron `roi/catalog.py`, `roi/mvs_interface.py`, `delivery.json` y
`/home/exitoso/home/DECISIONES-MALLA-BARRANCO.md`. Se consultaron las escenas
`record['run']/mvs/scene.mvs` de las 15 manzanas con `camera_table`, usando
`BlockCatalog` y el Python científico con `-B` (sin escribir bytecode).

| Manzana | Imágenes registradas | Dimensiones declaradas en la tabla de cámaras |
|---|---:|---|
|001|244|3763 × 2116|
|002|142|3765 × 2117|
|003|505|3766 × 2118|
|004|294|3762 × 2116|
|005|663|3762 × 2115|
|007|310|3765 × 2117|
|008|396|3765 × 2117|
|009|468|3764 × 2116|
|012|520|3764 × 2117|
|013|478|3766 × 2118|
|017|334|3761 × 2115|
|018|361|3763 × 2116|
|023|468|3754 × 2111|
|024|416|3763 × 2116|
|025|92|3771 × 2121|
|**Total**|**5.691**|Imágenes de aproximadamente 3,76K × 2,12K|

Todas las rutas de imagen referenciadas por esas escenas existen (`is_file`),
resolviendo las relativas respecto a la carpeta de la escena. **No se decodificaron
ni revisaron visualmente las 5.691 imágenes**: existencia de ruta no es una
auditoría de integridad o calidad fotográfica. Son las imágenes registradas en
estas escenas, no necesariamente todos los fotogramas extraídos originalmente.

Las tablas contienen intrínsecos `K`, rotación `R` y centro `C`; no solo posiciones.
Se dispone de imágenes corregidas de distorsión en el flujo COLMAP/OpenMVS.
Hay que usar cada imagen con sus intrínsecos y resolución correspondientes, sin
mezclar imágenes sin corregir con calibraciones de las corregidas. El lector
existente contempla intrínsecos normalizados; no asumir siempre `K` en píxeles.

Las transformaciones efectivas de `BlockCatalog` son similitudes de escala
uniforme positiva (comprobado mediante sus valores singulares), no necesariamente
transformaciones rígidas de escala 1. Incluyen la corrección vigente de 023.

Para 025 se observaron `colmap/undistorted/`, `mvs/images/`, `mvs/scene.mvs` y
`mvs/scene_dense.mvs` en:
`/data/barranco/results/barranco-full-v1/025/barranco_4k_2fps_combined_v1/`.

### Herramienta localizada y revisión técnica

Existe el ejecutable:
`/home/exitoso/home/barranco-roi/runtime/openmvs/bin/TextureMesh`.
También están `InterfaceCOLMAP` y `ReconstructMesh` en ese directorio.

Se revisó el código upstream de OpenMVS **v2.3.0**, no se ejecutó el texturizador:
https://github.com/cdcseacave/openMVS/blob/v2.3.0/apps/TextureMesh/TextureMesh.cpp

Ese código admite escena de cámaras e imágenes más una malla externa
(`--mesh-file`), exportación OBJ/GLB/glTF, selección de vistas, ajustes de costuras
y varios atlas limitados por `--max-texture-size` (8192 por defecto).
El piloto debe confirmar el comportamiento del binario local y su salida.
Usar `LD_LIBRARY_PATH` del runtime solamente en su proceso, como en sección 5.

Configuración propuesta para conservar la geometría: `--decimate 1` y
`--close-holes 0`, con salida nueva. No aplicar reconstrucción, refinamiento,
limpieza geométrica ni reparación automática como parte del texturizado.
Aunque el código permita importar mallas externas, su conservación real y la
correspondencia de caras deben verificarse en el piloto.

### Cómo funcionará la textura y qué ocurre con caras nuevas

La posición de cada punto de superficie se proyecta en las imágenes mediante
las cámaras calibradas. Hay que considerar encuadre, orientación, oclusiones,
resolución proyectada, nitidez y elementos transitorios (personas, vehículos).
La selección de vistas y los ajustes de costuras no garantizan por sí solos
eliminar todos esos problemas: hace falta revisión visual.

No se propone un material ni una imagen independiente por triángulo. Las caras
vecinas se agrupan en parches con UV y se empaquetan en atlas. Cada triángulo
recibe detalle fotográfico dentro de su superficie, conservando los 15 objetos
independientes. El muestreo debe respetar la proyección de cámara; una asignación
ingenua de colores a vértices no equivale a texturizado fotográfico.

- Cara nueva visible y bien colocada: puede recibir textura desde los frames.
- Cara visible pero con profundidad/inclinación incorrectas: puede presentar
  textura desplazada o estirada.
- Cara no observada o siempre oculta: no hay textura real recuperable. Identificar
  explícitamente la falta de cobertura; no inventar ni extrapolar detalle.

La prueba deberá comprobar oclusiones usando geometría suficiente: una malla
recortada puede omitir obstáculos reales; en bordes, solapes o reparaciones entre
manzanas considerar geometría vecina y la coherencia de las cámaras antes de
incorporar otras vistas.

### Plan propuesto por fases

**A. Validar cámaras y marcos de coordenadas.**

1. Comprobar si el usuario ha editado el `.blend` desde la entrega y partir de su
   versión vigente. Incluir las transformaciones actuales de los objetos.
2. Mantener la edición en `map_world`. Preparar una copia temporal de cada manzana
   en el marco local de sus cámaras mediante la inversa de la transformación
   efectiva `world_from_block`; no transformar de nuevo el archivo entregado.
3. Validar la proyección en varios fotogramas sobre fachadas, esquinas y tejados.
   Comprobar convenciones de cámara, intrínsecos, escala y corrección de 023.
4. Devolver el resultado a `map_world` conservando la colocación de Blender.

**B. Piloto sobre 025.**

- Usar la malla simplificada actual y sus 92 cámaras; no relanzar simplificación.
- Ejecutar `TextureMesh` con decimación y cierre de huecos desactivados, usando
  nuevas rutas de trabajo/salida y límites de recursos adecuados.
- Probar selección de vistas y ajustes de costuras; atlas de máximo 8192 × 8192
  como punto de partida, permitiendo varios. No se ha fijado aún la resolución
  final ni el número de atlas: dependerá de cobertura, detalle y memoria.
- Evaluar nitidez, alineación de ventanas y bordes, exposición, costuras,
  imágenes dobles y superficies sin cobertura; medir tiempo, RAM y peso.
- Verificar que no cambió la geometría, salvo representaciones equivalentes
  necesarias para UV/exportación. Aumentar el atlas no crea detalle fotográfico.

**C. Prueba de reparación manual.**

- Sobre una copia de 025, incorporar una cara que el usuario añada en un hueco
  realmente observado por las cámaras y marcar su procedencia manual.
- Repetir el texturizado y comprobar cobertura, oclusiones y alineación.
- Esta prueba no autoriza completar automáticamente otros huecos.

**D. Integración en Blender.**

- Crear una versión derivada con UV, materiales y texturas por manzana,
  manteniendo 15 objetos y 15 mallas independientes.
- Conservar el atributo RGB actual como referencia, la identificación de caras
  añadidas y las zonas sin cobertura.
- Transferir UV/materiales verificando la correspondencia de caras y esquinas;
  no asumir que OBJ/GLB conservan índices o número de vértices. Las costuras UV
  pueden requerir duplicaciones de representación sin alterar la superficie.
- Registrar imágenes, cámaras, transformaciones, parámetros y procedencia.
- Validar guardado y reapertura con texturas disponibles; decidir el empaquetado
  final tras medir el tamaño real del piloto.

**E. Flujo repetible de edición y reproyección.**

```text
Usuario edita una manzana en Blender y guarda una versión derivada
    → se exporta su geometría vigente
    → se recalculan visibilidad, UV y atlas desde imágenes calibradas
    → se integra y revisa el resultado en Blender
```

Primera versión recomendada: **retexturizar la manzana editada completa**.
No asumir que OpenMVS permite actualizar solo caras nuevas conservando intactos
los UV/atlas anteriores. Esa actualización incremental requeriría desarrollar
gestión adicional de caras, UV, parches y dependencias de oclusión; queda como
mejora posterior, no como funcionalidad implementada. Si la edición cruza bloques,
habrá que revisar también las dependencias con sus vecinos.

### Limitación geométrica y siguiente paso

La textura no corrige posiciones de la malla. La simplificación del 70 % fue
aprobada sin rechazo por distancia; en 025 el máximo observado fue 38,37 cm.
No significa que toda la malla tenga ese error, pero puede haber desajustes
fotográficos locales que requieran reparación manual. El piloto debe evaluar
alineación además de nitidez.

**Siguiente paso recomendado, todavía pendiente:** validación de coordenadas y
piloto 025 → prueba con una cara añadida manualmente → revisión/aprobación visual
del usuario → extensión a las 15 manzanas. No hay estimaciones medidas de tiempo,
memoria, calidad final ni tamaño de textura hasta ejecutar ese piloto.

## 11. Tiempos reales, pruebas y renderizado

### Tiempos medidos, sin confundir cómputo con desarrollo/espera de decisiones

- Mallado: los 14 workers efectivos arrancaron aproximadamente a las **00:52:38**;
  las 15 mallas, incluida 025 reutilizada, estaban recibidas a las **01:05:58**.
  Ese intervalo de unos 13 min 20 s incluye cómputo y transferencia, **no** todo
  el desarrollo/preparación previo. Los intentos iniciales de arranque fueron antes.
- La estimación inicial 30–90 min se refinó al observar los trabajos; no usarla
  como tiempo real medido de campaña.
- 025: primer diagnóstico de simplificación **137,13 s**; comparación con normales
  PCA **176,48 s**; validación reforzada intermedia **20,46 s**; comprobación
  posterior realmente de todos los vértices **unos 41 s**; refinamiento protegido
  final **91,05 s**, con dos validaciones que suman **39,45 s dentro de esos 91 s**.
  No volver a sumar esas validaciones como si fueran tiempo adicional.
- 70 %: normales/planos **18,71 s**, QEM **37,80 s**, ROI/color/guardado **1,82 s**;
  generación total **58,46 s** y medición **14,03 s**.

### Pruebas ejecutadas

- Se verificó en Chrome real que la web cargaba 15 manzanas, recuperaba los
  22 vértices originales de 025 y cargaba la colocación manual de 023, sin
  excepciones JavaScript ni crear selecciones de prueba en producción.
- La suite general aprobó 25 pruebas en aquel punto del desarrollo.
- Las pruebas posteriores del pipeline nativo y del de simplificación se
  ejecutaron de forma dirigida: remapeo de cámaras, igualdad escalar, hashes,
  concavidades y caras verticales, MVSI con rutas de imágenes anidadas,
  eliminación de fragmentos por ambas condiciones, bordes protegidos y distancia
  a superficie (malla gruesa y fina del mismo plano deben dar error casi cero).
- `tests/test_simplify.py`: tres casos aprobados, incluyendo conteo de todos los
  vértices y no duplicación de las observaciones de distancia.

Comando general, si un cambio nuevo justifica repetir pruebas:

```bash
/data/barranco/runtime/alignment313/bin/python -B -m unittest discover -s tests -v
```

### MeshLab y GPU

Maestra: RTX PRO 4000 Blackwell, aproximadamente 24 GiB, 24 CPUs y 60,9 GiB RAM.
MeshLab GUI está instalado. Los PLY se abrieron; el log del preview 70 % confirmó
carga en **2,3 s**, el del preview 50 % en **1,3 s**. Eso es carga, no FPS.

Se dio una orientación de 30–60 FPS o más para 1,55 M triángulos con sombreado
sencillo usando realmente la RTX, **no un benchmark**. No hay medición de FPS.
El log solo decía OpenGL 4.5, sin identificar el renderer. La sesión puede
usar otro dispositivo/renderizado remoto/software; hace falta comprobarlo.
En la última consulta sobre GPU estaba al 0 % con ~172 MiB usados, pero ya no
había MeshLab en nuestra sesión: ese dato no demuestra rendimiento ni fallo.
No se cambiaron drivers, potencia, kernel ni configuración de arranque.

## 12. Datos originales, laboratorio y autenticación

Rutas maestras importantes:

```text
/data/barranco/results/barranco-full-v1/NNN/EXPERIMENTO/
/data/barranco/alignment-inputs/barranco-full-v1/NNN/EXPERIMENTO/
/data/barranco/exports/barranco-full-v1/resultados_por_manzana.csv
/data/barranco/exports/barranco-full-v1/transforms_atlas.json
/data/barranco/roi/025/s-1794364122096131540/pilot-v1/
/data/repos/Alineacion-point-cloud/
/home/exitoso/lab-deploy/
```

En cada resultado: `colmap/best_model.txt`, sparse seleccionado,
`colmap/undistorted/`, `dense-lineage.json`, `mvs/scene_dense_scalar.ply`,
`mvs/dense-batches.json`, recibos y hashes. Los nativos con visibilidad y `.dmap`
grandes están en las hijas; **un `scene_dense.mvs` no necesariamente contiene
toda la nube densa**. Las nubes escalares no tienen listas de vistas/pesos.

025 original: selección real `s-1794364122096131540`, 22 vértices,
11.054,384 m², densa original de 60.755.108 puntos, recorte de 26.860.347,
muestra de 5.204.407 a 10 cm. Se conserva el piloto comparativo histórico de
Delaunay/BPA/RANSAC y su galería; detalles completos en el archivo histórico.
El RANSAC de **reconstrucción histórica** no es el mismo ensayo que la
**regularización planar de la malla** implementada aquí.

La nube global previa de ~153 GiB sigue siendo otro producto. Su symlink
`/data/barranco/exports/barranco-full-v1/dense_global.ply` apunta a la nube
combinada de la alineación anterior, que no incorpora la nueva colocación manual
de 023. No eliminarla por asumir que el respaldo de Google Drive está verificado.

Historial de calidad: 007 usa recuperación v2; 023 tiene cobertura parcial
(468/480 imágenes registradas). No inventar superficies para cubrir lo ausente.

Laboratorio: identidad por tag+MAC. Registro público:
`/home/exitoso/lab-deploy/config/site.json`.
Consulta de máquinas mediante `make check`, directorio `/home/exitoso`.
Montaje autorizado anterior mediante `python3 -B -m labdeploy mount --all`,
directorio `/home/exitoso/lab-deploy`; no remonta los que ya estaban montados,
y reporta 001 como montado en otra ruta. No usar `volume open` innecesariamente:
también inicia Docker/containerd. No modificar `/home/exitoso/Makefile`.
No encender, apagar, reiniciar ni cerrar sesiones sin orden específica.

SSH se hace con el adaptador existente `labdeploy.ssh.credentials` y
`tools/drive_download_campaign.remote`, con known_hosts del toolkit.
**No se guardan contraseñas del chat en este documento, código, configuración
ni Git; no leer ni volcar archivos privados de credenciales.**

No se solicitó ni hizo commit/push de estos cambios. El Git padre puede ignorar
`home/`: un `git status` vacío no demuestra que las aplicaciones o el estado estén
versionados. Conservar los resultados y JSON persistentes como datos del usuario.

## 13. Documentos complementarios e historial preservado

- [`barranco-roi/README.md`](barranco-roi/README.md): selector web y uso.
- [`barranco-roi/MESH-CAMPAIGN-20261112.md`](barranco-roi/MESH-CAMPAIGN-20261112.md):
  arquitectura y recursos de la campaña. Su parte de seguimiento describe el
  funcionamiento durante la ejecución; el estado actual es 15/15 recibidas.
- [`barranco-roi/SIMPLIFIED.md`](barranco-roi/SIMPLIFIED.md): simplificación y
  validación conservadora. Para las pruebas 50/70 sin rechazo, usar la sección 10
  de este documento y sus informes propios.
- [`DECISIONES-MALLA-BARRANCO.md`](DECISIONES-MALLA-BARRANCO.md): decisiones de
  costuras manuales, huecos y reproyección fotográfica.
- [`opencode-historial-previo-20261112.md`](opencode-historial-previo-20261112.md):
  **documento anterior completo preservado**, con matrices numéricas de 023,
  detalles del piloto inicial, campañas previas, métricas y antecedentes.
  Sus estados de desmontaje, falta de polígonos y pendientes de arranque están
  superados: no ejecutarlos como instrucciones actuales.

### Para el siguiente chat

Leer este documento y `simplified_70pct_blocks/LEEME.md` o `delivery.json`.
La petición de aplicar el 70 % a todas y entregar objetos separados ya terminó.
Retomar desde el `.blend` de 15 objetos y el plan de texturizado de **10b**:
se investigaron 5.691 imágenes/cámaras y se propuso piloto 025 y reproyección de
caras nuevas. **No se ha ejecutado texturizado.** Comprobar primero si el usuario
editó el archivo. No volver a lanzar mallado ni simplificación por este plan.

Mensaje sugerido para retomar:

> Lee `/home/exitoso/home/opencode.md`, especialmente las secciones 0, 1, 10a y 10b.
> La entrega de las 15 manzanas simplificadas al 70 % ya está terminada y verificada.
> Tenemos un plan para texturizar con las cámaras/fotogramas originales y reproyectar
> caras que añada manualmente. Todavía no se ha ejecutado. Continúa desde mi `.blend`
> vigente de 15 objetos independientes y mi nueva petición.
