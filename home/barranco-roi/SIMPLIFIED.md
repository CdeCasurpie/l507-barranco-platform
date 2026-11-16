# Simplificación local por manzana

## Entrega actual: las 15 manzanas al 70 %

El usuario aprobó el preview 025 y se completó el lote para las 15, sin rechazo
por distancia. Resultado en `exports/mesh-campaign-20261112/simplified_70pct_blocks/`:
`barranco_15_manzanas_70pct.blend` (815,66 MB, 15 objetos/mallas únicos) y
`barranco_15_manzanas_70pct.mlp` (15 capas que referencian `meshes/`).
Los PLY individuales suman 600,76 MB. Ver `LEEME.md`, `delivery.json` y
`pesos_por_manzana.csv` en esa carpeta. Se reabrió el `.blend` y se verificaron
geometría, colores, 15 datablocks únicos y ausencia de instancias.
Código del lote: `batch_simplify_70.py`, `package_simplified_blocks.py` y
`blender_blocks.py`. El resto de este documento describe el piloto conservador
previo, que se conserva como referencia independiente.

Implementación: `simplify_meshes.py`. Python del runtime `alignment313`, NumPy,
SciPy, Shapely y PyMeshLab 2025.7 aislado en `runtime/meshdeps`.
Ejecución CPU; no requiere instalar dependencias ni utilizar CUDA.

## Salidas

Todo se escribe bajo `exports/mesh-campaign-20261112/simplified/`:

- `pilot_025_5cm_v1/`: primer diagnóstico; las normales individuales de los
  triángulos no dieron soporte planar suficiente.
- `pilot_025_5cm_v2/`: piloto con normales PCA locales, comparación de variantes,
  intentos al 50/75/90 % de caras y sus mediciones.
- `pilot_025_5cm_v2_guarded/`: refinamiento por realimentación geométrica.
- `025/manzana_025_simplified.ply`: se publica únicamente si supera la
  verificación completa de vértices y las muestras de superficies.
- `025/report.json`: geometría, reducción, parámetros, tiempos, origen y
  validación de la versión publicada.

Cada intento tiene un nombre independiente. Los candidatos rechazados conservan
sus métricas para diagnóstico y no son el resultado publicado.

## Método

1. Verificar SHA256, esquema, índices y coordenadas de la malla de origen.
2. Retirar componentes únicamente cuando cumplen **ambas** condiciones:
   diámetro menor de 0,20 m y área menor de 0,02 m². Registrar lo retirado.
3. Estimar normales mediante PCA en vecindarios de 24 vértices. Proteger
   bordes abiertos/no manifold, cambios de orientación y una franja adicional.
4. Detectar hasta 32 planos con RANSAC reproducible (semilla 25), tolerancia
   de 5 cm y orientación de 12°. Separar regiones por conectividad real de
   caras y exigir al menos 2 m² y 100 caras por región.
5. Regularizar solo vértices interiores inequívocos de las regiones: acercamiento
   parcial al plano, factor 0,65, manteniendo intactos los vértices protegidos.
6. Comparar QEM conservador y planar + QEM. Proteger topología, bordes y
   normales, y ponderar las zonas de detalle frente a las superficies planas.
7. Filtrar caras contra el polígono real y transferir RGB de la referencia.
8. Validar posiciones **float32**, iguales a las que tendrá el PLY publicado.

La regularización planar sustituye el suavizado global en este piloto.
No se ejecuta completado de huecos. Las aristas de la malla simplificada pueden
ser más largas que 0,45 m dentro de superficies representadas por menos caras;
la arista máxima de reconstrucción no se reutiliza como criterio de decimación.

## Error geométrico y refinamiento

La distancia se mide de puntos a **triángulos de la superficie**, en ambos
sentidos. No se usa distancia entre vértices como sustituto.

- Comprobación preliminar: muestras de caras y aristas.
- Comprobación definitiva: una pasada específica con tantos vértices como
  tiene la malla fuente, verificando que se evaluaron **todos**, y otra pasada
  adicional de caras y aristas. Se repite en ambos sentidos.
- No se duplican las observaciones: MeshLab guarda el punto muestreado y su
  punto más cercano, con la misma distancia en ambos.
- Umbrales: P99 hasta 5 cm y máximo observado hasta 7 cm.
- El máximo sobre todos los vértices y las muestras no es una demostración
  matemática del máximo continuo sobre todos los interiores de triángulos.

Si la comprobación completa identifica puntos fuera de tolerancia, se protegen
sus vecindarios y dos anillos de caras. La decimación siguiente actúa solo
sobre el resto seleccionado. Se verifica además que los vértices congelados
mantengan su posición. Se permiten hasta cuatro iteraciones antes de informar
que no hay un resultado publicable con esos parámetros.

La referencia de las métricas es la malla tras retirar los componentes diminutos
explicitados en el informe; su eliminación se contabiliza por separado.

## Comandos

Desde `/home/exitoso/home/barranco-roi`, usando límites de recursos mediante
`systemd-run --user` como en las ejecuciones registradas:

```bash
/data/barranco/runtime/alignment313/bin/python -B simplify_meshes.py --block 025 --tolerance 0.05 --outer-tolerance 0.07 --run-id NUEVO_ID
/data/barranco/runtime/alignment313/bin/python -B simplify_meshes.py --block 025 --tolerance 0.05 --outer-tolerance 0.07 --run-id NUEVO_ID --verify-run
/data/barranco/runtime/alignment313/bin/python -B simplify_meshes.py --block 025 --tolerance 0.05 --outer-tolerance 0.07 --run-id NUEVO_ID --refine-run
```

`--refine-run` utiliza los puntos medidos fuera de tolerancia de la variante
planar, crea una carpeta nueva terminada en `_guarded` y publica solo si pasa.
`--publish-run` permite publicar una variante que ya tenga verificación completa
aprobada; comprueba conteos, huellas y el número de vértices evaluados.

La prueba se ejecuta con 4 hilos/cuota de 400 %, límite de RAM de 24 GiB,
swap desactivada y prioridad Nice=10. Los tiempos reales se registran por etapa
en `status.json`, `comparison.json` y `REPORTE.md`.
