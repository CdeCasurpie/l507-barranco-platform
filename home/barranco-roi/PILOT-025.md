# Piloto de superficie de la 025 — selección del usuario

Selección: `s-1794364122096131540`. Contorno de 22 vértices, 11.054,384 m².
Fuente: resultado `barranco_4k_2fps_combined_v1`, con 92 cámaras.

## Entradas verificadas

- 60.755.108 puntos originales → **26.860.347 puntos interiores**.
- Recorte escalar completo: `j-1794364335553248746-4dc292/dense_roi_local.ply`.
- La exportación conserva los registros originales byte por byte y verifica
  el SHA256 completo de la fuente.
- Muestra común: **5.204.407 puntos**, primer registro original en cada vóxel
  de **10 cm** en `map_world`. No se promedian superficies. El recorte completo
  permanece intacto para futuros ensayos de mayor resolución.
- Una preparación inicial a 5 cm dio 15.787.427 puntos; se sustituyeron solo
  esos intermedios derivados por la muestra de 10 cm para acotar el piloto.
  Sus parámetros se conservan en `prepare-0.05-history.json`.
- El PLY nativo de L507_015 fue verificado contra su SHA256 y filtrado con el
  mismo polígono y exactamente los mismos índices de representantes.
- `verify_native.cpp` comprobó todos los XYZ/RGB de los 5.204.407 representantes:
  0 discrepancias RGB, error de redondeo float32 ≤0,0000153 m, índices de
  visibilidad válidos para las 92 cámaras.

## Implementaciones

`pilot.py prepare`: muestreo común, coordenadas métricas y normales rotadas.

`pilot.py delaunay`: OpenMVS 2.3 certificado, ejecutado localmente en un runtime
aislado. PLY con visibilidad nativa. Sin filtrado adicional por distancia en
píxeles (`--min-point-distance 0`), cierre de huecos, suavizado o decimación.
Pesos de visibilidad conservados (`--constant-weight 0`). Se conservan el
comando y los logs completos. Scratch en `runtime/native-025/` del proyecto.

`pilot.py ball`: PyMeshLab 2025.7.post1 instalado aisladamente en
`runtime/meshdeps/`. Ball Pivoting sobre la muestra común con normales.
El primer intento con agrupamiento 0 se detuvo por coste elevado; su contabilidad
queda en `ball-attempt1.json`. El ensayo posterior utiliza radio de 14 cm y
agrupamiento estándar del 20 % del radio. Los intentos global y de teselas XY de
20 m también se detuvieron por coste elevado (`ball-resource-attempts.json`).
La candidata acotada se ejecuta con `pilot.py ball-3d`: teselas iniciales de 5 m,
subdivisión hasta 1,25 m cuando superan 20.000 puntos locales, y halo interno de
0,5 m. Todos los puntos proceden del mismo conjunto común interior. Se fusionan
los IDs originales de vértice y se asignan caras por su centroide al núcleo de
una tesela; pueden quedar costuras abiertas. No se afirma equivalencia exacta
con un único BPA global ni se cierran huecos posteriormente.

`pilot.py planes`: hipótesis RANSAC guiadas por normales, ajuste por mínimos
cuadrados y asignación con tolerancia de 8 cm / 20°. Triangulación 2D por plano
con rechazo de aristas largas y comprobaciones de soporte. No completa sólidos.
Es una candidata **solo planar**: los puntos no asignados no se interpretan como
ruido ni se reconstruyen automáticamente. No equivale a una malla completa.

## Restricción de caras

Para Delaunay/BPA se rechazan caras con aristas >45 cm; para parches, >35 cm.
Esto es un parámetro del piloto, no una garantía universal de conservación de
cualquier hueco. El soporte planar usa distancias de 10 cm en muestras del
interior/aristas. Se comprueba el triángulo proyectado completo contra el
polígono, incluidas caras verticales de proyección XY degenerada. No basta
comprobar centroide o vértices. Los bordes quedan abiertos, sin tapas.

Los PLY finales están en **map_world métrico**, con RGB por vértice. No contienen
atlas UV. La galería utiliza colores de puntos/interpolación sobre triángulos;
el texturizado fotográfico se evaluará después de aprobar la geometría.

## Archivos y recursos

Resultados: `/data/barranco/roi/025/s-1794364122096131540/pilot-v1/`.

- `prepare.json`, `native_input.json`, `native-verification.json`: procedencia.
- `common.npz`, `common_world.ply`, `common_roi_indices.bin`: muestra común.
- `*_world.ply`, `*.json`, logs: resultados por método.
- `comparison.json`: concordancia con una muestra fija ~100.000 puntos del
  recorte denso completo. No es exactitud independiente frente al terreno.
- `gallery.html`, `RESUMEN.jpg`: comparación desde las mismas cámaras.

Los tiempos de las etapas no incluyen instalación, transferencia, intentos
descartados ni la preparación común; no son un benchmark end-to-end.

Límites usados: BPA 20 GiB RAM, Delaunay 28 GiB, planos 10 GiB; swap=0 y cuota
CPU=200% por proceso. Las nuevas etapas se fijan a CPUs 8–11 si están disponibles.
Se mantienen 50 GiB de reserva en `/data`. No se cambiaron drivers ni potencia.

Se montó L507_015 únicamente con autorización para preparar los insumos. Una vez
copiados, se cerró su volumen con el helper enrolado y se verificó `mounted=false`,
restaurando su estado anterior. El recibo está en `source-volume-restored.json`.

La extracción del runtime conserva ejecutables y dependencias en el proyecto;
no modifica las bibliotecas del sistema. El controlador de credenciales existente
se usa solo en `pilot_remote.py`; no se almacenan contraseñas.
