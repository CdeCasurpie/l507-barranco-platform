# Campaña Delaunay por manzana — 12 de noviembre de 2026

Autorización: ejecutar las 15 manzanas con sus polígonos reales, en paralelo,
montando solo volúmenes pendientes y respetando los trabajos de otros usuarios.

## Selecciones e insumos

- Las 15 selecciones vigentes se fijan en `state/mesh-campaign-20261112/selections/`.
- `manifest.json` de esa carpeta registra asignaciones, matrices, IDs, huellas,
  rutas, recursos y direcciones observadas, con verificación de tag y MAC por SSH.
- Solo 023 usa la transformación manual relativa a 025.
- La 025 conserva su selección original y reutiliza el Delaunay del piloto,
  verificando polígono, transformación, resolución y SHA256 del resultado.
- No se crean polígonos diagnósticos en el estado real.

## Máquinas y recursos

| Manzana | Hija | Hilos CPU | Límite RAM |
|---|---|---:|---:|
|001|L507_001|2|24 GiB|
|002|L507_002|6|40 GiB|
|003|L507_003|6|40 GiB|
|004|L507_004|6|40 GiB|
|005|L507_005|6|40 GiB|
|007|L507_007|6|40 GiB|
|008|L507_008|6|40 GiB|
|009|L507_009|6|40 GiB|
|012|L507_012|6|40 GiB|
|013|L507_006|6|40 GiB|
|017|L507_010|6|40 GiB|
|018|L507_011|2|24 GiB|
|023|L507_023|6|40 GiB|
|024|L507_024|6|40 GiB|
|025|L507_015|—|Piloto reutilizado|

Durante el inventario había trabajos de GPU en 001 y 011, con unos 17 GiB
de VRAM ocupados cada uno. No se detienen ni reconfiguran. La reconstrucción
Delaunay autorizada usa CPU (`--cuda-device -2`), sin VRAM de cómputo.
La memoria disponible observada fue de 57,78 a 60,14 GiB por hija.

El volumen de 001 permanece en `/mnt/datos`, sin desmontarlo, remontarlo ni
cambiar sus rutas. Los volúmenes ya montados no se modificaron. Se ejecutó el
montaje de pendientes con el helper existente, sin iniciar Docker.

## Procesamiento

`roi/mvs_interface.py` lee las tablas de cámaras MVSI. Cada lote se relaciona
por nombre de imagen con la escena global y verifica poses e intrínsecos.
Se comprueba también que la densificación no haya cambiado el orden de cámaras.
La escena derivada conserva las cámaras globales y usa rutas absolutas de fotos.

`runtime/tools/mesh_roi.cpp` recorre las nativas de todos los lotes y compara
**cada registro escalar** con la nube global seleccionada, siguiendo los rangos
de `dense-batches.json`. Calcula SHA256 de toda esa nube y debe coincidir con
el JSON ROI. Conserva un punto original por vóxel mundial de 0,10 m, con origen
de cuadrícula `[0,0,0]`, y remapea sus vistas y pesos a las cámaras globales.
La cuadrícula es explícita; el piloto 025 utilizó un origen dependiente de su
muestra. Ambas resoluciones son 10 cm, sin prometer muestras idénticas.

OpenMVS 2.3: min-point-distance 0, constant-weight false, decimation 1,
remove-spurious 0, remove-spikes 0, close-holes 0, smooth 0, crop-to-roi 0.
El filtrado final conserva solo triángulos cubiertos por el polígono y con
aristas de hasta 0,45 m. Incluye las concavidades y caras verticales.
RGB procede de los puntos originales, no de un atlas fotográfico nuevo.

Cada hija ejecuta su propio servicio `barranco-mesh-NNN-20261112` con cuota,
swap desactivada, Nice=10 y IOWeight=20. Se usa el lease de reconstrucción.
El worker detiene **solo su proceso** si alcanza 95 °C, permanece a 90 °C
durante 30 s, quedan menos de 8 GiB de RAM disponible o se alcanza la reserva
de 50 GiB de disco. No elimina insumos ni resultados ajenos.

## Estado y resultados

En la maestra:

```bash
python3 -B mesh_campaign.py status
systemctl --user status barranco-mesh-launch-20261112
systemctl --user status barranco-mesh-watch-20261112
```

Directorio de trabajo: `/home/exitoso/home/barranco-roi`.

- Inventario: `state/mesh-campaign-20261112/inventory.json`.
- Arranque: `state/mesh-campaign-20261112/launch.json`.
- Estado remoto: `state/mesh-campaign-20261112/status.json`.
- Recepción: `state/mesh-campaign-20261112/collection.json`.
- Resultados: `exports/mesh-campaign-20261112/NNN/manzana_NNN_world.ply`.
- Metadatos por resultado: JSON ROI, auditoría de cámaras, muestreo, comando y
  resultado con conteos, tamaños y SHA256. La recepción verifica el hash.

Las hijas guardan los intermedios bajo
`MOUNT/photogrammetry/roi-campaigns/mesh-20261112/NNN/`.
El watcher de la maestra recibe las mallas terminadas y mantiene el manifiesto.
No habilita arranque automático. Los errores quedan registrados y no se
ocultan mediante parámetros de menor calidad o reconstrucciones alternativas.

Entrega: objetos separados, alineados en `map_world`, para costuras y reparación
manual en Blender. Después se podrá reproyectar las fotografías sobre la
geometría aprobada. El tamaño de 2–3 GB es un objetivo, no una cifra garantizada.

## Verificación de implementación

25 unittest del conjunto aprobados inicialmente y tres casos específicos del
flujo nuevo aprobados tras las correcciones (26 casos en total):
remapeo entre lotes, deduplicación por vóxel, SHA de la nube, rechazo ante una
discrepancia escalar y filtrado de triángulos que cruzan concavidades, manteniendo
una cara vertical válida. Preflight de todas las tablas de cámaras de las 14
manzanas multilote aprobado antes de enviar los trabajos.
