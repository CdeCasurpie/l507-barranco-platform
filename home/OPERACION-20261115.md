# Operación 15/nov/2026: revisión de nuevas capturas y limpieza central

## Cambio posterior: 006 de un solo vídeo y matching secuencial

Por petición explícita del usuario se canceló únicamente la corrida 006-all de
L507_010 y se borró su salida actual (23.337 archivos, 11.902.650.390 bytes).
Los tres MP4 originales y los registros se conservaron. Recibo remoto:
`cuadra-006-all/discard-receipt.json`, dentro de la campaña original.

Se preparó y lanzó un experimento nuevo en esa misma hija con SOLO
`VID20261114142304.mp4`: 2.032.723.786 bytes, 1920x1080, duración 1064,523 s.
2 fps, aproximadamente 2.129 frames; matching secuencial con overlap=10,
sin matching exhaustivo y sin loop detection que requiera vocabulario.
Una cámara compartida para este único clip. Segmentación personas/postes/cables;
sin mallado ni alineación automática, parada después de densificación.

Raíz remota:
`/data/photogrammetry/campaigns/barranco-single006-sequential-20261115/cuadra-006`

Estado de la maestra:
`/home/exitoso/lab-deploy/.state/campaigns/barranco-single006-sequential-20261115`

Preparación: `tools/prepare_single006.py`.
Lanzador: `tools/start_review_experiments.py --assignments RUTA/assignments.json --sequential`.
Supervisión: `tools/review_experiments.py --state RUTA --watch`.
Se comprobó `running / frames` tras lanzar. Límite GPU temporal de 100 W con
guard de restauración. Las otras dos corridas originales no se modificaron.

### Resultado del experimento secuencial

Terminó en `awaiting_review` después de 9.867,73 s (2 h 44 min 28 s).
2.129 frames; máscaras 5.126,32 s; SfM 3.330,98 s, de los cuales
matching secuencial 139,40 s y mapper 3.120,22 s. El temporizador principal de
metrics no incluye la densificación personalizada por lotes: no usar su suma
como tiempo total del experimento.

Se encontraron seis componentes sparse (modelos 0–5). El seleccionado es el 2:
1.119 imágenes de 2.129 (52,56 %), 363.246 puntos, error medio de reproyección
1,034824 px. No representa todavía una reconstrucción conectada de toda la
captura; requiere revisión del usuario.

Densa del componente seleccionado: 63.063.293 puntos, 28/28 lotes terminados,
sin mallado. Concatenación con redundancia de solapes, no nube deduplicada.
Sparse y métricas recibidas y verificadas en:
`/data/barranco/review/barranco-inputs-20261115/006-single14nov-sequential/`.
Densa y escenas nativas permanecen en L507_010. No se alineó con el mapa.

### Intento de conectar componentes con COLMAP

El usuario confirmó solape y autorizó un intento en la hija. Se lanzó un trabajo
derivado en L507_010, no sobre la BD original:

`/data/photogrammetry/campaigns/barranco-006-bridges-20261115/cuadra-006`

Control: `tools/start_reconnect006.py`; worker: `tools/reconnect006_worker.py`.
Estado: `.state/campaigns/barranco-006-bridges-20261115/`.
Se verificó ejecución de `bridge-matching`. Se copian las features mediante
SQLite backup; se añaden pares entre keyframes de componentes distintos y
vecindades temporales, con presupuesto máximo de 100.000 pares. COLMAP continúa
el componente principal con poses existentes fijas y calibración fija. No se
repiten máscaras ni se generan densa/malla. El candidato requiere revisión; una
densa anterior no debe presentarse como generada por las cámaras nuevas.

### Estado de las otras corridas al iniciar ese intento

- L507_006, 006-14nov: sigue en SfM después de finalizar matching exhaustivo;
  registro incremental y ajustes globales en CPU, aún sin resultado terminal.
- L507_019, 026-all: SfM produjo un componente de 1.577 imágenes. El worker falló
  en `undistort` con código 137. El log de COLMAP alcanza el final de la
  rectificación; falta diagnosticar qué parte de esa etapa recibió SIGKILL.
  No atribuirlo a OOM sin evidencia y no afirmar que hay densa.
- La sparse 026 se recogió y verificó en
  `/data/barranco/review/barranco-inputs-20261115/026-all`.

### Recuperación autorizada de 026

El kernel confirmó OOM del contenedor: proceso Python con aproximadamente
41.839.484 KiB de memoria anónima al remapear máscaras. COLMAP había terminado
de rectificar las 1.577 imágenes. `pipeline/mask_geometry.py` mantenía sin límite
una matriz de remuestreo por pareja de cámaras, especialmente costosa con
intrínsecos separados por imagen. Había 959 máscaras escritas al caer.

Se preparó un overlay aislado al proceso de esta corrida: máximo dos mapas en
caché, misma matemática de proyección y mismo muestreo de las máscaras. No se
modificó el checkout certificado compartido ni se elevó el límite de 40 GiB.
Implementación/recibo: `tools/park_memory_recovery.py`, y en la raíz de la hija
`mask_geometry_bounded.py`, `mask-memory-patch.json`, `pipeline_bounded.py`.
Un primer arranque de ese wrapper falló por no incluir `/work` en sys.path; se
corrigió y se validó la CLI dentro de la imagen antes de relanzar.

Se guardó el historial y se reanudó desde `undistort`; frames, máscaras originales
y SfM se reutilizan. Estado comprobado: `running / undistort`, worker vivo, sin
error, etapas previas completas. Límite GPU temporal de 100 W con restauración.
La supervisión original sigue activa. No afirmar éxito de densa hasta ver
`awaiting_review`.

## Alcance autorizado

Tres experimentos independientes hasta densificación, sin mallado, sin
simplificación y sin incorporarlos automáticamente al mapa. El usuario revisará
sus sparse y decidirá posteriormente la alineación y ROI.

| Hija | IP observada | Entrada |
|---|---|---|
| L507_006 | 192.0.2.64 | 006: dos vídeos del 14/nov |
| L507_010 | 192.0.2.100 | 006: tres vídeos, todos |
| L507_019 | 192.0.2.63 | 026: dos vídeos del parque |

Raíces remotas:

`/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-006-14nov`

`/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-006-all`

`/data/photogrammetry/campaigns/barranco-inputs-20261115/cuadra-026-all`

Descargas completadas y verificadas mediante CRC32C publicado por Drive y SHA256
local. Los vídeos preexistentes se reutilizaron por hardlink.

## Lanzamiento y supervisión

Controlador: `/home/exitoso/lab-deploy/tools/start_review_experiments.py`.
Consulta/recolección: `tools/review_experiments.py`, con `--watch` para supervisar.
No repetir el lanzamiento mientras un worker siga activo.

Estado persistente:

`/home/exitoso/lab-deploy/.state/campaigns/barranco-inputs-20261115/`

Cada worker ejecuta frames, máscaras, SfM, rectificación, densa y métricas.
Perfil: 2 fps, resolución nativa, personas/postes/cables; sin telemetría
inventada ni eliminación de vegetación. Docker existente, sin reconstruir
imágenes ni actualizar drivers. Límites heredados de CPU/RAM/temperatura/disco.
El estado terminal esperado es `awaiting_review`; no equivale a aprobación
científica del usuario.

El recolector recibe sparse/metadata, no densas. Destino:

`/data/barranco/review/barranco-inputs-20261115/`

Los tres arrancaron y terminaron extracción de frames. El primer intento se
detuvo durante máscaras por GPU >=80 °C sostenida (81–82 °C). Se conservó el
historial, se aplicó temporalmente el mínimo admitido de 100 W (antes 145 W) y se
reintentaron explícitamente las tres ejecuciones, reutilizando frames completos.
No se elevaron los umbrales térmicos. Un guard independiente por hija restaura
145 W al terminar el nuevo intento si ningún operador cambió el límite; recibos
en `/var/lib/lab-deploy/review-power-L507_*.json`.
Consultar el estado persistido antes de afirmar terminación o calidad.

## Paquete vigente de 14 manzanas

`/data/barranco/active/manifest.json`

Se preservaron 14 mallas actuales, transformaciones, sparse, escenas OpenMVS y
5.223 imágenes rectificadas, verificadas mediante SHA256. Las imágenes y sparse
están preservadas por hardlinks; borrar otra ruta no elimina su contenido.
Las mallas y el `.blend` original siguen en el home, en la entrega 70 %.
No se sobrescribió el `.blend` de 15 objetos ni se alteró geometría.

023 está excluida del catálogo activo y pendiente de nueva captura. No se
recalcularon las colocaciones de las otras manzanas. El modo histórico del
catálogo permite consultar también revisiones rechazadas.

La web ROI ya no exige una densa local para visualizar sparse, validar polígonos
o guardarlos. Análisis/exportación densa local se rechazan con explicación cuando
la fuente solo está en la hija. El análisis denso remoto queda pendiente de
integración. El importador admite `--sparse-only`.

## Limpieza realizada

Recibo:
`/data/barranco/active/cleanup-1794729639320349624.json`

Se eliminaron 1.221 archivos explícitamente enumerados: nube densa global
obsoleta, copias centrales `scene_dense_scalar.ply` y archivos multimedia de la
campaña antigua de mallas/texturas. 312,395 GiB lógicos.

`df` posterior: /data, 92 GiB usados y 364 GiB libres (antes 404/52).
Se conservaron scripts de la campaña antigua, código, imágenes necesarias,
sparse, features/BD, metadatos históricos, runtime y las fuentes de las hijas.

Los antiguos informes que describen la nube densa global siguen siendo
históricos: ese archivo ya no está disponible localmente. Sus metadatos y
transformaciones sí se conservan. No intentar reexportar densas centrales sin
recuperar sus fuentes.

## Pendientes fuera del lanzamiento actual

Editor web general de colocación Sim(3), integración incremental con base fija,
ROI remoto, validación de simplificación OpenMVS en las hijas y texturizado de la
geometría corregida. Nada de ello debe activarse automáticamente al terminar las
tres densificaciones.
