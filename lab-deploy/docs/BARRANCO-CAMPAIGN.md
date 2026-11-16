# Barranco: campaña 4K supervisada

## Entradas y configuración

Campaña `barranco-full-v1`: 15 manzanas, 68 MP4 con SRT, todas 3840×2160.
`TODO` permanece sin procesar en L507_019. Las carpetas vacías no se lanzan.
Entradas y asignaciones de descarga no se sobrescriben.

Cada hija usa `/data/photogrammetry/campaigns/barranco-full-v1/cuadra-NNN`.
La maestra mantiene el estado bajo `/data/barranco/campaigns/barranco-full-v1`.
El pipeline certificado sigue en `a45d44258f5199b06aa57f7d6ae947f40c5326ed`;
los nuevos scripts son una capa de ejecución y exportación independiente.

- Videos completos a 2 fps, sin resize; SIFT admite 4K y undistort no reduce
  deliberadamente la resolución. Las imágenes rectificadas pueden cambiar de
  dimensiones debido al modelo de distorsión.
- SIMPLE_RADIAL, SIFT, matching exhaustivo por manzana.
- SegFormer 2048 y SAM 3 con pasada global y teselas 2×2 para postes/cables;
  máscaras nativas verificadas y remapeadas con la cámara real.
- Frame→video→PTS registrado. Dos frames por clip se vuelven a decodificar y
  se comparan píxel a píxel contra los seleccionados antes de usar GPS.
- Sparse global inmutable; sin georef/ROI que recorte las conexiones vecinas.
- No se ejecutan malla, refinado ni textura en esta campaña.

## Recursos y protecciones

Una reconstrucción por hija, lock global del nodo. Contenedores sin red, raíz
de solo lectura, código/modelos de solo lectura, temporales y cachés en /data.
6 CPUs, 40 GiB RAM, sin swap adicional, 1024 procesos como máximo, logs Docker
acotados. La 025 piloto original usó 8 CPUs; su snapshot conserva esa procedencia.

Después de observar picos de 79 °C GPU y 90 °C CPU en el piloto completo se
adoptó 6 CPUs y un límite GPU temporal de 120 W (rango reportado 100–145 W).
`power-limit.json` conserva UUID, límite anterior y aplicado. Se restaura al
terminar, sin sobreescribir cambios de potencia hechos por otro operador.
No se almacenan contraseñas en manifiestos ni scripts.

Supervisor local cada ~5 s, independiente de SSH:

| Variable | Aviso | Parada del trabajo |
|---|---|---|
| GPU | 75 °C | 80 °C durante 30 s o 85 °C inmediata |
| CPU | 85 °C | 90 °C durante 30 s o 95 °C inmediata |
| SSD Composite | 65 °C | 70 °C durante 30 s o 80 °C inmediata |
| RAM disponible del host | 10 GiB | menos de 8 GiB durante 30 s |
| Raíz libre | 3,5 GiB | menos de 3 GiB |
| Datos libres | 75 GiB | menos de 50 GiB |

Para la admisión: GPU<65 °C, CPU<75 °C, SSD<60 °C, RAM disponible≥52 GiB,
datos libres≥100 GiB y raíz≥3,75 GiB. La 007 con 4,24 GiB pasa; 5 GiB no es
un requisito de COLMAP. Se comprueban identidad tag/MAC, montaje, pesos,
imágenes, código y hashes de entradas antes de cada intento.

Las paradas afectan solo al contenedor de la ejecución, validando sus labels.
No se apagan/reinician máquinas, no se cierran sesiones, no se cambian drivers.
Los fallos de recursos no tienen reintento automático. El único reintento
automático especial es el hold documentado de los pilotos antiguos antes de
la fusión grande, para activar el motor por lotes expresamente autorizado.

## Densa 4K con memoria acotada

OpenMVS 2.3 carga los mapas completos al fusionar: cientos de imágenes 4K no
caben en 40 GiB. Hasta 96 cámaras se conserva el método monolítico probado
con la 025 (92). Por encima se utilizan núcleos de 40 cámaras más hasta 24
vecinas por covisibilidad, máximo 64 cámaras por lote.

La selección de subconjuntos usa `colmap image_deleter`, sin BA, normalización
ni cambio de coordenadas. Se comparan poses, intrínsecos y XYZ con el modelo
global antes de procesar cada lote. Cada cámara pertenece a un núcleo y puede
aparecer como halo en otros lotes. Todos los lotes mantienen 4K.

Se conservan las escenas nativas y PLY de cada lote. Los PLY escalares se
concatenan en el marco global original; **no es una fusión global deduplicada**.
Pueden quedar superficies redundantes en los solapes. `dense-batches.json`
documenta los rangos de vértices y la procedencia. La escena global `scene.mvs`
es la cámara original, y las escenas realmente densificadas están en `chunks/`;
no se fabrica un `scene_dense.mvs` global para fingir fusión.

La prueba real del motor usó 20 imágenes, 3 lotes de hasta 12 cámaras, verificó
las coordenadas y completó las tres densificaciones y su ensamblaje.

## Productos y recolección

Éxito completo: ≥95% de frames registrados, ≥80% por clip, un componente SfM,
densa no vacía y procedencia sparse→densa comprobada. Otros resultados válidos
se publican como `partial`, con sus componentes y cobertura, sin esconder pérdidas.

`collect_reconstruction.py` adquiere un lock único, prepara un snapshot estable,
transfiere con rsync reanudable, comprueba todos los SHA256 y publica por rename.
Destino: `/data/barranco/results/barranco-full-v1/NNN/EXPERIMENTO`.

Por decisión del usuario se recopilan productos finales y paquete de alineación:
sparse, BD consistente, frames, máscaras, GPS, escenas, métricas y registros.
Se conserva una densa escalar XYZ/RGB/normales por manzana, no copias duplicadas
de esos mismos puntos. Los `.dmap`, la densa nativa con visibilidad y los PLY
individuales de lote permanecen intactos en las hijas y se enumeran en el recibo.

Siempre queda una reserva de 50 GiB en la maestra. Un problema de capacidad
bloquea la recolección correspondiente, no borra los resultados de las hijas.

## Alineación local

Runtime aislado: `/data/barranco/runtime/alignment313` (Python 3.11,
COLMAP/PyCOLMAP 3.13.0). No se instala Docker ni se cambian drivers en la maestra.
`import_alignment_run.py` importa 3.11→3.13 sin SfM/BA: verifica XYZ, poses,
intrínsecos, IDs, observaciones y bytes de features. Registra el hash del
adaptador y el fingerprint sparse generador del activo denso.

La copia local de Alineacion-point-cloud tiene una extensión explícita para
aceptar contextos locales dentro de scopes systemd realmente limitados
(8 CPUs, RAM≤40 GiB, swap=0), sin simular IDs Slurm. La publicación local usa
rename en /data para no duplicar temporalmente las exportaciones grandes.
Los controles científicos de los kernels y del grafo no se relajan.

El coordinador ejecuta auditoría/campaña y exporta la componente mayor, además
de la sparse coloreada por manzana. El reporte enumera las componentes e islas;
GPS por sí solo no justifica declararlas alineadas. Las densas se colocan con
`world_from_sparse @ sparse_from_dense` y normales rotadas, no mediante BA nuevo.

## Operación

Desde `/home/exitoso/lab-deploy`:

```bash
python3 -B tools/reconstruct_campaign.py status
python3 -B tools/reconstruct_campaign.py status --blocks 025 --profile diagnostic
python3 -B tools/reconstruct_campaign.py cancel --blocks 007
```

Estado global y logs:

- `/data/barranco/campaigns/barranco-full-v1/execution-status.json`
- `/data/barranco/campaigns/barranco-full-v1/execution-manager.log`
- En cada hija: `reconstruction-full-status.json`, `logs/reconstruction/full/`
  y `outputs/cuadra-NNN/barranco_4k_2fps_combined_v1/mvs/dense-batches-progress.json`.

Para impedir nuevas incorporaciones, crear el archivo
`/data/barranco/campaigns/barranco-full-v1/STOP_EXPANSION`. Esto no cancela los
trabajos que ya tienen supervisor local. Para cancelarlos se usa el comando
anterior; después de comprobar su estado terminal puede restaurarse el límite
de potencia con `python3 -B tools/campaign_power.py --blocks 007 --restore`.

Durante la ampliación, la 003 osciló en 79–80 °C con 120 W. Se redujo el techo
de las doce ejecuciones activas a **100 W**, mínimo reportado por sus GPU,
conservando 4K y los parámetros geométricos. Cada recibo registra el ajuste
120→100 y conserva 145 W como valor original a restaurar. Para una reanudación
posterior puede fijarse el mismo techo con
`python3 -B tools/campaign_power.py --blocks 007 --watts 100`.

## Recuperaciones revisadas durante la ejecución

- **007:** el mapper produjo componentes de 182 y 148 imágenes, con 20 vistas
  compartidas y unión exacta de 310. Se conservó el resultado parcial v1. Un
  candidato derivado se fusionó y ajustó explícitamente en un scope local:
  310/310 vistas, error medio 2,745→0,993 px, p90 1,975 px, referencias recíprocas
  y pérdida de observaciones inferior al 5%. La nueva ejecución está en
  `cuadra-007-recovery`, experimento `barranco_4k_2fps_007_recovered_v2`.
  Reutiliza únicamente raw/frames/máscaras originales y regenera undistort y
  toda la densa desde el modelo derivado. No se transforma la densa antigua
  como si hubiera sido generada por el nuevo sparse.
- **023:** el supervisor detuvo dos intentos por lecturas CPU de 96 y 99 °C.
  La cuota media por sí sola no restringe la afinidad instantánea de las
  bibliotecas nativas. Después de revisar la carga y esperar enfriamiento se
  fijaron 3 CPUs y `--cpuset-cpus 8,9,10`, núcleos eficientes de su Ultra 9 285K.
  Se mantienen los mismos límites térmicos. Los intentos previos se conservan
  en `attempt-history`; no se relajan los umbrales para completar un trabajo.

`execution-overrides.json` identifica la revisión recuperada de 007; la
asignación e importación antiguas se conservan como evidencia, pero el mapa
final consume exclusivamente la nueva revisión cuando está publicada.

## Resultado publicado

Directorio de entrega: `/data/barranco/exports/barranco-full-v1/`.

- 15 reconstrucciones recopiladas y verificadas, 15 bloques conectados por
  17 aristas aceptadas, 0 fallos técnicos de alineación y 0 auditorías rechazadas.
- Sparse combinada: 4.065.767 puntos.
- Densa combinada: 5.675.791.302 puntos, 164.597.948.033 bytes (153,29 GiB),
  con RGB original, normales y block_id. Se conserva redundancia de solapes.
- SHA256 global: `deeb3115a2ff1df28e8bc1ca150f9d42f77805d088d032780bf21b2695e257cc`.
- Preview densa: 4.996.296 puntos; contiene las 15 etiquetas, coordenadas y
  normales finitas. Se verificó el layout completo y el checksum al recorrer
  el archivo global, sin cargarlo entero en memoria.
- `overview_xy_focus.png` presenta la distribución con tracks>=3 y error<2 px;
  solo limita los ejes del gráfico, no cambia las nubes originales.
- La 023 conserva la advertencia 468/480 vistas (97,5%). Un intento de registro
  con la estructura final no recuperó las doce vistas sin correspondencias
  suficientes; no se rebajaron tolerancias para forzarlas.
- El coordinador finaliza en `partial` por ese criterio de cobertura, aunque
  la alineación y ambas exportaciones sí abarcan las 15 manzanas.
- Las 15 GPU se comprobaron de nuevo a su límite predeterminado de 145 W,
  con temperaturas de reposo de 31–33 °C. La maestra conserva unos 64 GiB libres.

`report.json`, `RESUMEN.md` y `resultados_por_manzana.csv` son el resumen de
entrega. `node-bundles/` en el directorio de campaña archiva los bundles
vigentes de las hijas con sus hashes verificados; revisiones anteriores
permanecen en los historiales de preparación de los nodos.

Un reinicio del coordinador requiere reconciliar trabajos activos; no se
reenvían ciegamente ejecuciones fallidas. El procesamiento es reanudable por
etapas verificadas y por lotes densos publicados, no necesariamente dentro de
una extracción de máscaras o una operación SfM interrumpida.

## Auditoría de tiempos y siguiente experimento

La retrospectiva, con fuentes y limitaciones, se resume en
[`BARRANCO-TIMINGS.md`](BARRANCO-TIMINGS.md). Los CSV y evidencias originales
están en `/data/barranco/reports/baseline-v1/` y se regeneran mediante
`python3 -B tools/report_campaign_timings.py`.

El plan de superficie/textura, teselas y comparación sparse/dense está en
[`MESH-AND-BENCHMARK-PLAN.md`](MESH-AND-BENCHMARK-PLAN.md).
