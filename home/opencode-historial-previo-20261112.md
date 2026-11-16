# Archivo histórico de continuidad — Barranco

Este es el documento anterior, preservado como referencia histórica. Contiene
estados y pendientes ya superados. Para continuar, leer primero el documento
vigente: `/home/exitoso/home/opencode.md`.

Este documento permite continuar en otro chat sin reconstruir toda la conversación.
Actualizado al cierre de esta sesión, 11 de noviembre de 2026.
**Leer primero las secciones 1, 2 y 3: describen la prioridad y el estado REAL.**

## Actualización operativa — 12 de noviembre de 2026

**Último avance: piloto de simplificación 025 implementado y verificado.**
El usuario autorizó planos/simplificación con tolerancia de 5–7 cm.
Código y comandos en `barranco-roi/SIMPLIFIED.md` y `simplify_meshes.py`.
Resultado publicado:
`exports/mesh-campaign-20261112/simplified/025/manzana_025_simplified.ply`.
Tiene 2.356.676 vértices, 4.671.110 caras y 96.074.876 bytes; reducción de caras
9,58 %. RANSAC: 32 planos/89 regiones; 115 fragmentos diminutos retirados.
Se verificaron todos los vértices en ambos sentidos, más muestras de superficies:
P99 peor 2,10 cm; máximo observado 6,81 cm. Dos iteraciones protegieron las
zonas que excedían 7 cm. El máximo no es una cota exhaustiva sobre todos los
interiores de triángulos. El piloto final tardó 91,05 s, incluyendo validaciones;
el ensayo comparativo previo tardó 176,48 s. Los informes definitivos están
en `simplified/025/report.json` y `REPORTE.md`; los diagnósticos v1/v2 contienen
candidatos rechazados. Las otras 14 mallas aún no están simplificadas.

La sección 3 inferior describe el arranque anterior, **ya completado**:
`/data` está montado, el selector multiman-zana está activo en el puerto 8765,
y el usuario ya guardó polígonos reales vigentes para **las 15 manzanas**.

El usuario autorizó después montar todos los volúmenes pendientes y ejecutar
las mallas en paralelo, respetando trabajos de un compañero. Se montaron los
pendientes sin modificar los montajes existentes; 001 sigue en `/mnt/datos`.
Las 15 hijas asignadas están accesibles. Hay trabajos ajenos de GPU en
L507_001 y L507_011; no se tocaron. Nuestros workers usan solo CPU.

Se generalizó el flujo nativo multilote y se lanzaron **14 workers en paralelo**;
025 se reutiliza del piloto con verificación. Los JSON se fijaron antes de lanzar.
El estado cambia durante la ejecución: **consultarlo, no asumir que siguen
corriendo ni volver a lanzar todo**.

Continuidad de esta campaña:
`/home/exitoso/home/barranco-roi/MESH-CAMPAIGN-20261112.md`.
Comando de consulta desde ese proyecto: `python3 -B mesh_campaign.py status`.
El servicio maestro `barranco-mesh-watch-20261112` recibe las mallas verificadas
en `exports/mesh-campaign-20261112/NNN/manzana_NNN_world.ply`.
`state/mesh-campaign-20261112/collection.json` registra lo ya recibido.

Durante el arranque se corrigieron rutas derivadas y el filtro de soporte de
color: OpenMVS puede desplazar algunos vértices al separar zonas no manifold.
Se mantiene el filtrado geométrico por polígono y arista máxima de 0,45 m.
`filter-update.json` registra los binarios corregidos; no se repitieron los
mallados ya terminados para corregir únicamente la publicación/coloreado.
No se rellenan huecos ni se aplica suavizado. Las mallas siguen separadas.

No se almacenaron contraseñas proporcionadas en el chat. El acceso sigue
usando el adaptador privado existente del laboratorio.

## 1. Petición actual y decisiones vigentes

El usuario quiere, como prioridad inmediata, abrir una web **en la propia maestra**
y seleccionar progresivamente una región de conservación para cada manzana:

1. Ver las 15 reconstrucciones sparse alineadas como contexto.
2. Elegir qué manzana está activa y enfocarla desde arriba.
3. Dibujar/editar un polígono XY que conserve únicamente la región deseada de esa manzana.
4. Guardar un JSON independiente por manzana, con su transformación y máquina asignada.
5. Poder cambiar de manzana y continuar, sin mezclar ni perder selecciones.
6. Después, enviar/configurar esos JSON en las hijas y generar mallas Delaunay.

**No usar polígonos inventados ni lanzar las 14 mallas restantes sin las selecciones del usuario.**
Actualmente solo existe un polígono REAL del usuario: el de la 025.

Decisiones de producto:

- Solo la **023** lleva una corrección manual, relativa a la **025**, que es el ancla.
- Las otras 14 transformaciones se conservan.
- Se acepta mallar por manzana: el usuario quiere corregir solapes y coserlas manualmente.
- La entrega debe conservar **objetos/mallas separados por manzana**, alineados en el mismo marco.
- El usuario hará en Blender las costuras, merges de vértices, nuevos triángulos y reparación de huecos.
- **No ejecutar completado automático de huecos**, Poisson de cierre ni reparación automática de superficies ausentes.
- Tras la edición manual, la ruta preferida de texturizado es **reproyección de fotografías originales** con cámaras coherentes.
- Si no hay fotos útiles de una superficie añadida, señalarla para decisión del usuario; no inventar textura.
- Objetivo orientativo: **2–3 GB para la geometría**, texturas comprimidas presupuestadas aparte. No es tamaño ya garantizado.

El profesor había pedido nube global→malla global. Se explicó la diferencia metodológica.
El usuario aclaró repetidamente que él solucionará manualmente los solapes y eligió
el flujo **mallas por manzana + ensamblado/edición manual**. No volver a bloquear el
trabajo discutiendo esa elección; documentar correctamente lo que se ejecuta.

Documento específico de decisiones:
`/home/exitoso/home/DECISIONES-MALLA-BARRANCO.md`.

## 2. Estado real al terminar: IMPORTANTE

### Aplicación

Proyecto: **`/home/exitoso/home/barranco-roi/`**.

La ampliación a 15 manzanas **YA ESTÁ IMPLEMENTADA Y PROBADA EN ESTADO AISLADO**:

- Catálogo de los 15 resultados activos.
- Colocación manual exclusiva de la 023.
- Vista del conjunto sparse alineado, con contexto muestreado y etiquetas.
- Desplegable de manzana activa y enfoque individual.
- Sparse completa de la activa; solo esa manzana se recorta.
- Polígonos y revisiones aislados por manzana.
- JSON `roi_NNN.json` preparado para cada máquina asignada.
- Descarga de JSON desde la web.
- Conservación de borradores al cambiar de manzana durante una sesión.
- Comprobación densa en segundo plano, pudiendo seguir seleccionando otra manzana.
- Protección contra respuestas de una manzana que lleguen tarde y pinten sobre otra.
- Compatibilidad del polígono, IDs, huella y galería históricos de la 025.

**NO se ha arrancado aún la versión ampliada sobre el estado de producción.**
Los tests de navegador se ejecutaron con `--state-dir` temporal, sin contaminar las selecciones reales.

### Montaje y servicio, última comprobación

Al finalizar la escritura de este documento se comprobó:

- **`/data` de la maestra está DESMONTADO.** `findmnt --mountpoint /data` no devuelve montaje.
- `lsblk` identifica `/dev/nvme0n1p6`, ext4, PARTUUID
  `5359ec76-59f3-43fa-84e8-3b49af017460`, actualmente sin mountpoint.
- `df /data` muestra el filesystem raíz `/dev/nvme0n1p7`, **no el volumen de datos**.
- `barranco-roi.service`: `LoadState=not-found`, `ActiveState=inactive`.
- El runtime Python está dentro de `/data`: antes de montar, su ejecutable y los datasets no estarán visibles.
- El usuario ha autorizado montar `/data` en la maestra y en las hijas necesarias/todas las registradas.
- No guardar contraseñas en este documento, código, configuración ni Git. Si sudo necesita autenticación, usar un mecanismo privado o la terminal del usuario.

No confundir este desmontaje con pérdida de datos. No crear datasets nuevos sobre
el `/data` vacío de la raíz ni iniciar exportaciones sin verificar el montaje.

### Producción persistida en el home

`state/` contiene actualmente:

```text
jobs/
selections/
server.lock
```

Solo hay una selección real:
`state/selections/s-1794364122096131540.json` (025).

`state/exports/`, `state/blocks/`, `state/alignment-review.json` y
`state/effective-transforms.json` todavía no se han generado en producción.
Los generará el nuevo servidor al iniciar/guardar. No asumir que existen ya.

### Última acción interrumpida por la petición de este resumen

Se intentó un patch que corregía CSS y actualizaba README, pero **el patch completo falló por contexto**.
Ninguno de esos cambios se aplicó. Pendientes:

1. En `web/multi.css`, corregir el checkbox de contexto: el CSS general
   `input:not([type=range])` le aplica `width:100%`, haciendo que el texto se envuelva innecesariamente.
   Añadir/ajustar:
   ```css
   .context-bar label { white-space: nowrap; }
   .context-bar input[type=checkbox] { width:auto; flex:none; margin:0; accent-color:#65e4b1; }
   ```
   En móvil permitir `white-space:normal`.
2. Actualizar `README.md`: todavía describe solo la 025 y está desactualizado para la versión multiman-zana.
3. Arrancar la nueva aplicación en producción tras montar `/data`.
4. Verificar HTTP y abrir el navegador de la maestra para el usuario.

## 3. Próximos pasos concretos: continuar aquí

1. Comprobar `/data` y el dispositivo antes de montar; verificar que no se oculten archivos de la raíz.
   Montaje esperado, desde una terminal con autorización sudo:
   ```bash
   sudo mount -t ext4 -o nodev,nosuid /dev/disk/by-partuuid/5359ec76-59f3-43fa-84e8-3b49af017460 /data
   findmnt --mountpoint /data
   df -h /data
   ```
2. Corregir el pequeño CSS y actualizar README. No rehacer la aplicación: la ampliación está hecha.
3. Arrancar la instancia local, con límites, sin habilitar arranque automático:
   ```bash
   systemd-run --user --unit=barranco-roi --working-directory=/home/exitoso/home/barranco-roi -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=200% -p Nice=10 /data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/app.py
   ```
   Si el servicio ya existe, inspeccionarlo antes de decidir `restart` o un nombre nuevo.
4. Verificar `/api/health`, `/api/blocks`, `/api/alignment`, `/api/overview` y los JSON de la 025.
5. URL para el usuario: **http://127.0.0.1:8765** en la maestra.
6. Confirmar que producción sigue teniendo solo su selección real 025 y no polígonos de tests.
7. Dejar al usuario recortar y guardar las otras 14 regiones.

**La prioridad del usuario ahora es poder seleccionar los polígonos. No distraerse
implementando antes todo el coordinador de mallado distribuido.**

## 4. Código actual y organización

```text
/home/exitoso/home/barranco-roi/
  app.py                         servidor HTTP local; puerto 8765
  config/manual_alignment_023.json
  roi/core.py                    PLY escalar, polígonos, recorte, BlockDataset
  roi/catalog.py                 catálogo, matrices Blender, parser sparse, cache
  roi/multi.py                   estado por manzana, preservación legacy 025
  roi/service.py                 guardado, JSON por nodo, jobs de análisis/export
  web/index.html
  web/app.js                     editor Canvas, catálogo, contexto, borradores, carreras
  web/style.css                  estilos originales
  web/multi.css                  estilos nuevos; checkbox cosmético pendiente
  tests/test_core.py
  tests/test_http.py
  tests/test_multi.py
  tests/test_pilot.py
  tests/browser_check.py         prueba Chrome completa con estado aislado
  tests/pilot_browser_check.py   comprobación de galería histórica publicada
  pilot.py                       piloto de mallado, aún especializado en 025
  pilot_remote.py                preparación nativa remota, aún especializado en 025
  pilot_gallery.py
  pilot_finish.py
  PILOT-025.md
  runtime/                       runtimes/bibliotecas/herramientas aisladas
  state/                         datos de usuario, NO versionar
```

`pilot.py` y `pilot_remote.py` NO son todavía workers generales para las 15 manzanas:
contienen selección, rutas, cámara máxima 92 y otros valores específicos de la 025.
No ejecutarlos indiscriminadamente como si ya generalizaran el mallado multilote.

### Backend multiman-zana

- `BlockCatalog` obtiene las rutas activas del CSV de resultados y el atlas original.
- Usa recuperación v2 de 007.
- `read_sparse_points()` lee `points3D.bin` directamente (`<QdddBBBdQ`, 51 bytes + tracks),
  sin cargar todas las observaciones de cámaras con PyCOLMAP.
- `BlockDataset` verifica hashes de los modelos y `dense-lineage.json`, mantiene
  el marco sparse→dense identidad y construye el sparse en `map_world`.
- Cache LRU de 2 datasets completos; `DatasetProxy` evita retener los 15 payloads.
- Contexto de conjunto: máximo ~8.000 puntos por manzana, no las densas.
- `MultiReviewService` conserva 025 en el layout histórico; las demás usan `state/blocks/NNN/`.
- Un `BoundedSemaphore(1)` limita las lecturas densas pesadas de la maestra a una globalmente.
  No impide seguir dibujando y guardando otra manzana.
- Revisiones ordenadas por `created_at`, NO por nombre de archivo: IDs nuevos incluyen bloque
  y los IDs legacy no; orden lexicográfico rompería la 025.

### API

El identificador se pasa mediante **`?block=NNN`**, no `/api/blocks/NNN`.
La ausencia de `block` mantiene 025 por compatibilidad.

```text
GET  /api/health
GET  /api/blocks                         resumen y progreso de las 15
GET  /api/overview                       contexto alineado + polígonos guardados
GET  /api/alignment                      procedencia/matrices de corrección 023
GET  /api/dataset?block=023               sparse completa de una manzana
POST /api/validate?block=023
GET  /api/selections?block=023
POST /api/selections?block=023
GET  /api/selections/ID?block=023
GET  /api/roi.json?block=023              JSON vigente para la máquina
GET  /api/roi.json?block=023&selection_id=ID
POST /api/jobs?block=023                  analyze o export, no mallado
GET  /api/jobs?block=023
GET  /api/jobs/ID?block=023
GET  /api/jobs/ID/preview?block=023
POST /api/jobs/ID/cancel?block=023
GET  /pilot/                             galería histórica del piloto 025
```

POST requiere JSON y `X-ROI-Client: local-editor`, origen/Host local coherente.
Se verifica que URL, cuerpo, fingerprint y selección correspondan a la misma manzana.

### JSON por manzana

Guardar crea una revisión y actualiza:
`/home/exitoso/home/barranco-roi/state/exports/roi_NNN.json`.

Incluye: bloque, selección, vértices XY, marco/origen, `world_from_block`, hashes,
etiqueta de máquina, ruta nativa en la hija, parámetros Delaunay del piloto y
procedencia de alineación. **`deployment_status: not_submitted`** es intencional:
guardar prepara el envío; todavía no hay envío/mallado distribuido en esta API.

Parámetros previstos: voxel 0,1 m; min-point-distance 0; constant-weight false;
decimation 1; close-holes false; smoothing false; max_edge 0,45 m.

### Frontend

- Vista inicial del conjunto, con 025 activa; dropdown permite elegir/enfocar cualquier manzana.
- Activa completa en RGB, otras como contexto de color. Ocultar contexto es posible.
- Solo la activa participa en la selección, aun si el polígono cubre visualmente otra.
- Al empezar a dibujar desde conjunto, enfoca la activa.
- Vértices arrastrables, inserción por doble clic en un lado, Supr, undo/redo.
- Borradores por manzana en memoria; JSON guardado persistente entre sesiones.
- Recuperación de la última revisión al entrar en una manzana.
- `state.epoch`, seriales y `poll(id, block)` impiden mezclar respuestas al cambiar rápido.
- Se arregló una carrera al cargar revisiones: borrar selección activa al iniciar,
  comprobar serial y esperar validación antes de habilitar análisis.
- `window.roiApp` expone estado y helpers para checks locales de navegador.

## 5. Transformación manual de 023, proporcionada por el usuario

Los objetos de Blender eran sparse originales locales. Solo se cambia 023.
Convención Blender Euler **XYZ**, vectores columna, `T @ Rz @ Ry @ Rx @ S`.

```python
M23 = construir_matriz(
    (-1.8037, 2.8536, 1.4279),
    (213.6, -1.3603, 498.69),
    (1.232, 1.232, 1.232))
M25 = construir_matriz(
    (-0.19817, 2.5601, 4.3394),
    (-131.02, 13.859, -0.42814),
    (1.0, 1.0, 1.0))
M_rel = inverse(M25) @ M23
T23_nueva = T25_original_mundo @ M_rel
```

Matriz relativa calculada:

```text
[-0.911100854694,  0.803452358568, -0.205386319134, -0.863474457496]
[-0.382207368226, -0.136046084399,  1.163285429546,  2.238514476209]
[ 0.735959754505,  0.924002040274,  0.349867788342,  2.320380546798]
[ 0,               0,               0,               1             ]
```

`world_from_023` efectivo del catálogo:

```text
[ 5.144270412820,  23.589047006042, -14.061106532081,  335.440215313858]
[27.451225180745,  -4.017579135827,   3.303129970709, -115.739241876971]
[ 0.766871329373, -14.423497941696, -23.916437634608,   17.721270500089]
[ 0,                0,                0,                 1             ]
```

Para un producto 023 YA en el mundo anterior, usar
`Delta23 = T23_nueva @ inverse(T23_anterior)`, no aplicar M_rel directamente.
No aplicar dos veces la colocación.

El atlas original y los archivos de puntos no se modificaron. La corrección está
en el catálogo del nuevo visor y en los JSON derivados. La antigua nube global
de 153 GiB y galerías anteriores todavía usan la alineación anterior.

Para futuros mallados/reproyección, respetar la transformación del JSON seleccionado;
no sustituirla por la entrada antigua del atlas para la 023. Mantener puntos,
cámaras y superficies coherentes. No reoptimizar automáticamente la 023 hacia su
antigua alineación: el cambio es manual y deliberado.

## 6. Pruebas realizadas sobre la ampliación

**23 unittest aprobados**, incluyendo:

- Polígonos cóncavos, borde incluido y rechazo de contornos cruzados/no finitos.
- Transformación correcta antes de seleccionar; XYZ local no es la vertical real.
- Recorte PLY preservando registros, SHA, cancelación, no sobrescritura y reserva de disco.
- API local, revisión antigua 025 y orden temporal de nuevas revisiones.
- Aislamiento 001/023 y rechazo de cuerpos/fingerprints de otra manzana.
- JSON para nodo correcto y matriz manual 023.
- El gate de análisis no impide guardar otro polígono.
- Validación de caras: vértices+centroide interiores no bastan si el triángulo cruza una concavidad.
- Caras verticales con proyección XY degenerada admitidas si quedan dentro.

```bash
/data/barranco/runtime/alignment313/bin/python -B -m unittest discover -s tests -v
```

Directorio de trabajo: `/home/exitoso/home/barranco-roi`.

**Chrome headless real aprobado**, con estado temporal aislado:

```bash
systemd-run --user --scope --unit=roi-browser-check-NUEVO --quiet -p MemoryMax=6G -p MemorySwapMax=0 -p CPUQuota=200% /data/barranco/runtime/alignment313/bin/python -B tests/browser_check.py
```

Resultado del último ensayo exitoso:

- Cargó las 15 manzanas en el dropdown.
- Dibujó con ratón, movió/insertó/eliminó vértices y probó undo/redo.
- Guardó y recuperó tras recargar.
- Comprobó la densa completa de 025 con SHA correcto.
- Guardó polígonos diferentes de 001 y 023, y sus JSON correctos por máquina.
- Verificó cambio rápido 003→023 sin contaminación de geometría.
- Analizó la densa 001 mientras se seguía guardando 023: el resultado no sobrescribió la vista 023.
- Cero excepciones JavaScript.
- No creó exportación densa de pruebas en producción.

Capturas de pruebas, **no selecciones del usuario**, en `/tmp/opencode/` cuando ese
directorio temporal siga existiendo:
`roi-selector-all-blocks.png`, `roi-selector-manual-023.png`,
`roi-selector-initial.png`, `roi-selector-selection.png`, `roi-selector-dense.png`.
Los contornos `ISOLATED BROWSER…` / `PRUEBA AUTOMÁTICA…` eran temporales; jamás usarlos como ROI real.

No hace falta repetir todas las lecturas densas costosas si solo se corrige CSS/README.
Sí realizar una comprobación de arranque en producción y HTTP/navegador.

## 7. Datos, rutas y hardware

Maestra: usuario `exitoso`, Linux, 24 CPUs, ~60,9 GiB RAM física, GPU RTX PRO 4000
Blackwell de ~24 GiB. Ethernet observado a 100 Mbps (~9,6 MiB/s en transferencias).
No cambiar drivers, potencia, kernel ni configuraciones de arranque.

Cuando `/data` estuvo montado en la última auditoría:

- `/data`: ~480 GiB de filesystem, ~404 GiB usados, **51,42 GiB libres**.
- `/home/exitoso` comparte raíz; ~24 GiB libres actualmente.
- Nubes activas escalares por manzana: **142,72 GiB**.
- Exportación global adicional: **153,29 GiB**, 5.675.791.302 puntos.
- `results/`: ~218 GiB; `alignment/`: ~154 GiB; `alignment-inputs/`: ~14 GiB;
  mallas anteriores ~12 GiB; runtime ~5,4 GiB; piloto ROI ~1,3 GiB.
- Reserva implementada en `/data`: **50 GiB**. No rebajar ni limpiar originales silenciosamente.
- Para futuras mallas finales de unos pocos GB se propuso usar
  `/home/exitoso/home/barranco-roi/exports/`, evitando llenar `/data`; aún no implementado.
- El amigo del usuario hizo respaldo en **Google Drive**, no en un disco. No se verificó ubicación/integridad.
  No borrar la nube global ni datos originales basándose solo en esa afirmación.

Rutas maestras:

```text
/data/barranco/results/barranco-full-v1/NNN/EXPERIMENTO/
/data/barranco/alignment-inputs/barranco-full-v1/NNN/EXPERIMENTO/
/data/barranco/exports/barranco-full-v1/
/data/barranco/campaigns/barranco-full-v1/
/data/barranco/roi/025/s-1794364122096131540/
```

En cada resultado: sparse seleccionado por `colmap/best_model.txt`,
`mvs/scene_dense_scalar.ply`, `dense-lineage.json`, recibos/hashes,
`colmap/undistorted/images`, cámaras y máscaras.

**Las nubes escalares no tienen visibilidad por punto.** Los PLY nativos con listas
de vistas/pesos y los `.dmap` quedaron en las hijas. Los `.mvs` copiados a la maestra
son principalmente escenas de cámaras/sparse: el nombre `scene_dense.mvs` NO
significa que contengan toda la densa. En 025 guarda 70.788 puntos sparse frente
a 60.755.108 densos del PLY nativo.

La nube global `exports/barranco-full-v1/dense_global.ply` es un **symlink** a
`alignment/barranco-full-v1/exports/66186b5be08bcc8c9061c3998bf98f39c1d69c2b6fab867452b9b893448a894d/combined.ply`.
Borrar solo el symlink casi no libera espacio.

Marco: `map_world` métrico local, EPSG:32718, origen proyectado:
`[279932.4471962734, 8657453.760760272, 116.53700000000002]`.
Sumar el origen para coordenadas proyectadas; no usar UTM grande en float32 por vértice innecesariamente.
En el JSON ROI se guarda explícitamente el marco local, no GeoJSON WGS84.

## 8. Asignaciones de manzana a hija

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

Fuente: `/data/barranco/exports/barranco-full-v1/resultados_por_manzana.csv`.
Identidad por tag+MAC, no por IP DHCP. Registro público:
`/home/exitoso/lab-deploy/config/site.json`.

Última observación de laboratorio ANTERIOR al desmontaje final de la maestra:

- 18 hijas accesibles, 17 con `/data` montado.
- L507_001 tiene la partición en **`/mnt/datos`**, con otros datos/uso. No mover ni desmontar a ciegas.
  Adaptar el acceso tras verificar sus rutas, marcador e identidad.
- L507_005 no apareció; el usuario dijo que estaban recuperando conexión. Volver a observar, no asumir apagada.
- No encender, apagar, reiniciar ni cerrar sesiones sin orden específica.
- La autorización actual sí cubre montar los volúmenes necesarios/todas las hijas registradas.
- No modificar `/home/exitoso/Makefile`.

Toolkit existente:
`/home/exitoso/lab-deploy/` tiene descubrimiento, SSH con adaptador de credenciales y helpers de volumen.
`python3 -B -m labdeploy mount --all` descubre y monta, pero reporta el caso 001 montado en otro lugar.
Helper `volume open` también inicia Docker/containerd; usarlo solo para las operaciones necesarias autorizadas.
`make check` desde `/home/exitoso` consulta el estado sin administrar energía.
No leer/volcar archivos de contraseñas ni escribir secretos en scripts.

## 9. Piloto real terminado de 025

Selección real: **`s-1794364122096131540`**, 22 vértices, **11.054,384 m²**.
Captura original del usuario:
`/home/exitoso/Imágenes/Capturas de pantalla/Captura desde 2026-11-10 21-29-13.png`.

IDs:

- Análisis: `j-1794364222258069538-1d3747`.
- Exportación: `j-1794364335553248746-4dc292`.
- Densa original: 60.755.108 puntos.
- Conservados: **26.860.347**; descartados: 33.894.761.
- Recorte completo: **725.229.689 bytes**, registros originales preservados.
- Muestra común final: **5.204.407 puntos**, un representante original por vóxel global de 10 cm.

Datos y resultados:

```text
/data/barranco/roi/025/s-1794364122096131540/
  j-1794364335553248746-4dc292/dense_roi_local.ply
  pilot-v1/
    common.npz
    common_world.ply
    common_roi_indices.bin
    prepare.json
    native_input.json
    native-verification.json
    delaunay_world.ply
    ball_pivoting_world.ply
    ransac_planar_world.ply
    comparison.json
    REPORTE.md
    gallery.html
    RESUMEN.jpg
    pilot-report.json
    checksums.json
    publication-checks.json
```

| Método | Caras | Archivo | Duración etapa exitosa | Muestra densa a ≤20 cm |
|---|---:|---:|---:|---:|
|Delaunay + visibilidad|5.165.895|101,30 MiB|237,22 s|93,51%|
|BPA por teselas 3D|9.352.039|186,20 MiB|522,08 s|99,93%|
|Solo parches RANSAC|593.731|12,49 MiB|3,20 s|25,17%|

La evaluación usó la misma muestra fija de 100.226 puntos de la densa completa.
Es concordancia con esa nube, no exactitud frente a terreno ni prueba de topología correcta.
BPA reproduce más muestras, incluido ruido interior. Delaunay es más ligero.
Se recomendó **Delaunay como método principal** dado el buen resultado visual y coste.
RANSAC detectó 18 planos, explicó solo 7,3% de los puntos comunes; no sustituye toda la reconstrucción.

Importante: BPA global fue demasiado lento; se detuvieron intentos y se conservaron sus logs.
El BPA final es por teselas 3D con halo interno 0,5 m y IDs de vértice compartidos.
No presentarlo como una ejecución global equivalente ni sus 522 s como tiempo total de la campaña.

Delaunay piloto: OpenMVS 2.3, min-point-distance 0, constant-weight 0, decimate 1,
remove-spurious 0, remove-spikes 0, close-holes 0, smooth 0, crop-to-roi 0;
filtrado posterior por polígono y aristas máximas 0,45 m.
5,2 M puntos generaron ~33,9 M tetraedros; log informó ~11 GiB de pico virtual,
que no equivale a máximo de RAM residente.

Las imágenes de galería usan RGB por punto/vértice, **no atlas fotográficos nuevos**.
Se verificaron 25 imágenes en cinco cámaras y tres mallas, con SHA y tolerancia
de redondeo float32 en el contorno (~4,54 micrómetros máximo observado).

L507_015 se montó con permiso para obtener la muestra nativa con visibilidad.
Se verificaron todos los 5.204.407 XYZ/RGB contra la muestra escalar:
0 discrepancias RGB, redondeo ≤0,0000153 m, índices de cámaras válidos.
Se desmontó entonces al terminar; luego el usuario autorizó montar todas para la campaña.
El estado actual de las hijas debe consultarse de nuevo.

## 10. Dependencias y ejecuciones

Python para la aplicación:
`/data/barranco/runtime/alignment313/bin/python` (3.11).
NumPy 2.4.6, Shapely 2.2.0, SciPy, Pillow y PyCOLMAP 3.13 disponibles ahí.
El Python del sistema **no tiene NumPy**. No arrancar estos módulos con el Python incorrecto.

Runtime de mallado aislado:

- `barranco-roi/runtime/meshdeps/`: PyMeshLab **2025.7.post1** instalado localmente.
- `barranco-roi/runtime/openmvs/bin/`: ReconstructMesh, InterfaceCOLMAP, TextureMesh **2.3.0**.
- Dependencias bajo `runtime/openmvs/lib/`; pasar `LD_LIBRARY_PATH` solo al proceso OpenMVS.
- Se extrajeron del contenedor de campaña, sin instalar Docker ni cambiar bibliotecas/drivers de la maestra.
- `runtime/native-025/`: insumos y scratch del piloto.
- `runtime/tools/`: C++ `crop_native.cpp`, `verify_native.cpp` y binarios.
- El C++ del piloto contiene límites específicos de 025/92 cámaras. Generalizar antes de usar en otras.

Render GPU por ModernGL/EGL: dependencias estaban en `/tmp/opencode/render-deps`.
**Es temporal y puede haber desaparecido.** No instalar ni descargar nada para el editor:
el editor Canvas no depende de ModernGL. Solo reponerlo si se necesitan nuevos renders.
Chrome está instalado y se utilizó vía CDP con un cliente WebSocket estándar incluido en tests,
sin Selenium ni Playwright. MeshLab GUI está instalado. Blender no fue necesario para el piloto.

## 11. Trabajo que aún falta DESPUÉS de entregar la web

- El usuario dibujará las 14 regiones restantes. No sustituirlas por contornos automáticos.
- Generalizar preparación de nativos para los 14 casos multilote (la 025 era monolítica).
- Usar `dense-batches.json/ranges` para correspondencia de puntos y lotes.
- Remapear índices locales de cámara mediante identidades/nombres/poses a una escena coherente por manzana.
  No concatenar listas de visibilidad sin ese mapa.
- Verificar coordenadas/intrínsecos/poses y conteos como en 025 antes de mallar.
- Resolver acceso a 001 en `/mnt/datos` y disponibilidad de 005 sin interrumpir trabajo ajeno.
- Ejecutar en cada hija asignada, con límites térmicos/memoria y solo trabajos propios.
- La maestra recibe mallas y renders; intermedios grandes permanecen en hijas/scratch controlado.
- Reutilizar el Delaunay 025 ya validado si no cambian polígono/parámetros.
- Exportar alineadas, separadas, con revisión de transformación 023; conservar procedencia para Blender y fotos.
- Medir suma final de geometría. No prometer <3 GB por extrapolar solo la 025, la más pequeña.
- No asumir tiempos: 30–90 min en paralelo fue solo un presupuesto provisional,
  excluyendo desarrollo, selección y validación multilote; no una medición del conjunto.
- No eliminar ni sobreescribir la nube global anterior sin verificar el respaldo de Drive.

## 12. Historial anterior útil, no la prioridad inmediata

- Campaña original: 15 reconstrucciones, 5.703 frames extraídos, 5.691 registrados.
- 023: 468/480, parcial de cobertura; no forzar registros ni ocultar el aviso.
- 007: recuperación derivada v2, modelo 310/310; el original parcial se conserva.
- Alineación original: 15 bloques conectados, 17 aristas; 023↔025 fue rechazado
  por falta de vistas puente y 023 quedó conectada por 017. Por eso la corrección manual.
- Repo alineador: `/data/repos/Alineacion-point-cloud`, commit local `ca4a771`.
- Controlador: `/home/exitoso/lab-deploy`, commit local `12858c6`, sin push en aquella sesión.
- App ROI: archivos en el home, **sin commit solicitado/hecho**. El Git padre puede
  ignorar `home/`; `git status` vacío no significa que estos archivos estén versionados.
- Reporte de tiempos retrospectivo: `/data/barranco/reports/baseline-v1/REPORTE.md`.
  9,10 h de ventana de reconstrucción, 14,74 h hasta exportación; no benchmark de 19 nodos simultáneos.
- Mallas previas del amigo: `/data/barranco/mesh/barranco-full-v1/`, incluyendo
  `textured15/`. Algunas tenían caras estiradas, costuras y fuerte simplificación al 5%.
  No confundirlas con las mallas nuevas del piloto ROI.

## 13. Instrucción práctica para la siguiente sesión

El usuario pidió este resumen para abrir otro chat porque el anterior era grande.
No continuar haciendo cambios operativos como parte de escribir el resumen.
Al retomar: **montar/verificar el volumen, terminar CSS/README y arrancar la web multiman-zana ya probada**.
Después dejar que el usuario seleccione y guarde sus regiones.

Mantener comunicación en español, concreta. No volver a proponer un plan extenso
en vez de arrancar lo que ya está implementado. Si el entorno está en modo Plan,
respetar ese modo; para editar/arrancar se necesita modo de ejecución.
