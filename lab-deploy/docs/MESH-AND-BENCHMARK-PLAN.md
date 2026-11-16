# Barranco: plan de malla texturizada y evaluación de tesis

Estado: propuesta técnica; parámetros iniciales sujetos a un piloto medido.
La campaña actual termina en nubes alineadas. Malla y textura aún no tienen
tiempos medidos. Este documento define el siguiente experimento y la entrega.

## 1. Producto y punto de partida

El producto final será una superficie urbana navegable con texturas fotográficas,
LOD y carga espacial progresiva. Una nube con RGB no equivale a una malla
texturizada: faltan caras, parametrización UV, atlas y asignación de imágenes.
Delaunay es parte de la reconstrucción geométrica; no realiza esos pasos de textura.

Activos existentes:

- 15 bloques en un marco común, 5.691 cámaras registradas; 023 conserva 468/480.
- Sparse: 4.065.767 puntos. Densa global: 5.675.791.302 puntos, 153,29 GiB.
  La concatenación mantiene redundancia entre lotes y manzanas.
- Transformaciones y manifiestos en `/data/barranco/exports/barranco-full-v1/`.
  Marco local métrico EPSG:32718; origen proyectado
  `[279932.4471962734, 8657453.760760272, 116.53700000000002]`.
- Maestra: última capacidad registrada ~64 GiB libres; no alcanza para duplicar
  la densa global y sus intermedios. El procesamiento debe ser distribuido y acotado.
- Las hijas conservan escenas OpenMVS, mapas de profundidad y puntos con
  visibilidad por lote. El PLY escalar global **no conserva esa visibilidad**.
  No usarlo como único insumo para un método que necesita rayos cámara→punto.

Los errores de alineación entre pares no son exactitud absoluta contra terreno.
Antes de cerrar tolerancias de costura, revisar su distribución y la referencia
disponible; el máximo holdout observado de 1,330 m impide prometer costuras
centimétricas sin verificar las zonas concretas.

## 2. Piloto mínimo representativo

Seleccionar tres recortes en el mapa común: una zona interior de fachada/suelo,
un cruce entre dos manzanas y una zona con oclusiones, cables o vegetación.
Incluir la 023 o documentar expresamente su cobertura en una revisión adicional.
Usar exactamente los mismos recortes para los métodos comparados.

Antes del cálculo, inventariar los archivos nativos de los lotes participantes,
sus hashes, cámaras e imágenes. Comprobar que cada punto visible referencia una
cámara válida. Para 007, consumir exclusivamente la revisión recuperada v2.
Conservar los originales y escribir candidatos en directorios nuevos.

Primera exploración propuesta: núcleos de tesela de 25–50 m y halos de 5–10 m.
Son valores de arranque, no una garantía de memoria o calidad. El halo debe
incluir geometría y cámaras con soporte suficiente a ambos lados del borde;
aumentarlo si hay estructuras grandes o incertidumbre de alineación.
Medir memoria y ajustar antes de expandir el área.

## 3. Reconstrucción y continuidad espacial

1. **Partición común.** Crear una grilla global con IDs estables, núcleo,
   halo y regla de propiedad de caras. No particionar solo por etiqueta de
   manzana: los edificios y calles atraviesan esos límites.
2. **Adaptación de escenas.** Preparar escenas derivadas en el marco común,
   transformando puntos, centros y orientaciones de cámaras con la misma Sim(3).
   Mantener coherentes imágenes rectificadas e intrínsecos; probar proyecciones
   antes/después. Las distancias de mapas de profundidad deben escalarse si se
   reutilizan bajo cambio de escala; no basta transformar los centros.
3. **Resolver visibilidad entre lotes.** Los índices de cámara de cada escena son
   locales. Crear un mapeo explícito y auditable al combinar escenas; no concatenar
   listas de visibilidad como si compartieran IDs. Verificar si la versión concreta
   de OpenMVS permite la composición requerida; si no, implementar/probar el
   adaptador o usar la ruta por escenas individuales con reconciliación de bordes.
4. **Densa→superficie.** Ejecutar reconstrucción Delaunay con visibilidad sobre
   escenas nativas relevantes. ReconstructMesh de OpenMVS es el candidato inicial,
   sujeto a comprobar formato, opciones y consumo de esta versión. Fusionar
   redundancia con tolerancia medida, preservando superficies delgadas y aristas.
   No promediar automáticamente fachadas dobles separadas por error de alineación.
5. **Limpieza.** Retirar caras degeneradas, duplicados e islas sin soporte;
   detectar orientaciones incoherentes, agujeros, autointersecciones y puentes
   artificiales entre fachadas. Documentar filtros y cambios de cobertura.
6. **Costuras.** Reconstruir con halo y recortar al núcleo usando planos comunes.
   Recortar por sí solo no iguala las triangulaciones: crear vértices de borde
   compartidos y retriangular/soldar con tolerancias verificadas, o usar parches
   de transición derivados de la región común. Publicar cada cara una sola vez.
   Si los residuos exceden el presupuesto, revisar alineación y soporte, no
   esconder el error con una soldadura de gran radio.
7. **Refinado opcional.** Solo si mejora métricas/inspección con recursos acotados.
   Medir su coste por separado y conservar la versión previa.

Todo el piloto sigue los límites térmicos y de recursos documentados en
`BARRANCO-CAMPAIGN.md`. La maestra recibe candidatos compactos y métricas;
las escenas y temporales voluminosos permanecen en las hijas.

## 4. Textura y entrega ligera

- Seleccionar imágenes por visibilidad, ángulo, resolución y nitidez, usando
  máscaras para evitar objetos dinámicos y regiones sin soporte.
- Generar UV/atlas, reproyectar las fotografías y equilibrar exposición/color
  entre cámaras y teselas. Revisar dobles bordes, fantasmas y costuras cromáticas.
- Definir densidad de texel por distancia de visualización. Probar atlas 2K/4K
  en el piloto, medir legibilidad y tamaño; evitar muchos atlas 8K por defecto.
- Simplificar con preservación de bordes y siluetas; construir varios LOD.
  Si cambia la parametrización, rebakear texturas sobre la malla simplificada.
  Congelar bordes compartidos o generar transiciones compatibles entre LOD.
- Entregar teselas GLB/glTF y un manifiesto espacial; para navegación geográfica,
  evaluar 3D Tiles con transformaciones explícitas y bounding volumes correctos.
  Mantener vértices locales para precisión numérica, sin introducir coordenadas
  UTM grandes en float32 por vértice.
- Evaluar KTX2/BasisU para texturas y meshopt o Draco para geometría, verificando
  soporte del visor y artefactos de cuantización. Las texturas comprimidas y el
  presupuesto de caras se miden por separado.

Objetivo provisional del piloto: cargar una tesela cercana en menos de 2 s desde
SSD local en el equipo de visualización definido, y sostener al menos 30 FPS
en el recorrido acordado. Objetivo provisional de entrega completa: 1–5 GiB,
carga progresiva, memoria del visor ≤4 GiB. No son resultados logrados: se
ajustan con calidad medida, cobertura y equipo documentados antes de escalar.

Un entorno como GTA usa activos seleccionados/simplificados, texturas, LOD,
culling y streaming. No mantiene todas las muestras de reconstrucción en pantalla.
La cantidad de puntos intermedios no determina el tamaño de la entrega ni su
detalle útil. La reducción debe validarse visual y geométricamente.

## 5. Comparación justa sparse→malla frente a dense→malla

**A — referencia densa:** imágenes/máscaras → SfM → profundidad/densa →
superficie → simplificación → UV/textura → entrega navegable.

**B — alternativa sparse directa:** mismo SfM/cámaras/imágenes → reconstrucción
de superficie con puntos sparse y visibilidad de tracks → simplificación →
el mismo protocolo UV/textura → entrega navegable. No calcular profundidad
densa oculta dentro de B. Si se añade refinado fotométrico, declararlo como
variante y contabilizarlo.

Una triangulación Delaunay sin selección de superficie mediante visibilidad
puede cerrar espacios vacíos con caras falsas. La alternativa sparse necesita
un solver adecuado, y puede perder planos sin tracks, detalles y zonas ocluidas.
Texturas fotográficas pueden disimular esa pérdida sin corregir la geometría.

Comparar dos preguntas por separado:

1. **Desde SfM común:** coste marginal de cada ruta hasta la misma entrega;
   no cobrar SfM a una sola alternativa. Fijar los recortes y cámaras.
2. **Extremo a extremo:** entradas locales verificadas → entrega validada,
   incluyendo segmentación/SfM y todos los intermedios necesarios. Reportar
   además descarga, transferencia de productos y tiempo hasta disponibilidad
   en la maestra, sin sumar intervalos que se solapan.

Usar el mismo hardware, cuotas, potencia, límites térmicos y configuración de
textura/visor. Fijar previamente presupuesto geométrico y tamaño de textura;
publicar curvas calidad–tiempo–tamaño si no existe un único punto comparable.
No comparar una nube sin textura contra una malla lista para navegar.

## 6. Métricas y referencia

| Dimensión | Medidas mínimas |
|---|---|
| Geometría | Distancia simétrica a referencia independiente, mediana/p90/p95; exactitud/completitud a umbrales fijados; normales y perfiles de fachada/suelo |
| Cobertura | Área válida, huecos, zonas sin observación, cobertura por recorte; no premiar al método que omite regiones difíciles |
| Costuras | Distancia entre bordes, saltos de normal, caras duplicadas y discontinuidad cromática |
| Imagen | Render de vistas retenidas: SSIM/PSNR en máscaras comunes, nitidez y revisión de fantasmas; informar iluminación/oclusiones |
| Producto | Triángulos por LOD, atlas/texeles, bytes de geometría/textura, tiempo de carga, FPS y memoria en recorrido fijo |
| Recursos | Wall time, CPU time, pico RAM/VRAM, utilización GPU muestreada, disco máximo y bytes transferidos |

Preferir láser/topografía o medidas de campo independientes. Si no existen,
usar checkpoints manuales y distancias verificables; presentar distancia a la
densa como **concordancia con la referencia densa**, no verdad de terreno.
El error de reproyección de SfM no mide por sí solo calidad de superficie.

Retener vistas antes de reconstruir si se usan para evaluación independiente;
no reutilizarlas como imágenes de entrenamiento, BA, densificación o textura.
Mantener idéntica partición para A/B. La campaña existente puede servir de
inspección retrospectiva, pero un holdout independiente exige un experimento
nuevo con esa separación desde el inicio.

## 7. Instrumentación y protocolo de ejecución

- Registrar JSONL append-only por etapa/backend/intento con IDs de campaña,
  nodo, tile, PID, entradas/salidas/hash y estado final. UTC para correlación;
  `monotonic_ns` para duración dentro del mismo host/arranque.
- Eventos start/end y errores para decode, SegFormer, SAM3, SIFT, matching,
  mapper/BA, undistort, profundidad, fusión, ensamblaje, alineación, mesh, refine,
  UV, texturing, compresión, transferencia, verificación y publicación.
- Registrar versiones/commits, parámetros, cuotas/afinidad, potencia, GPU UUID,
  RAM/VRAM pico, temperaturas y razón de espera/parada. Registrar estado de
  sincronización de relojes y offsets observables antes/después.
- Distinguir frío de caliente: pesos cargados, caché de etapas/mapas y caché del
  filesystem. No etiquetar una ejecución como fría sin protocolo verificable.
  No vaciar cachés globales de equipos compartidos como atajo.
- Separar duración útil por etapa, suma de intentos, cola/admisión, recuperación,
  cómputo y entrega. Mantener fallos y ejecuciones descartadas en el registro.
- Primero un piloto instrumentado para comprobar el logger; después, al menos
  tres repeticiones por condición viable, orden A/B alternado y dispersión
  reportada. Una sola corrida queda identificada como tal.
- Medir secuencial y paralelo con el mismo conjunto de tareas y producto final.
  Definir `S(p)=T(1)/T(p)` y `E(p)=S(p)/p` solo con tiempos comparables medidos.
  Con 15 tareas indivisibles, 19 nodos no aportan 19 tareas concurrentes;
  paralelismo por teselas es otro diseño y debe medirse por separado.

La retrospectiva actual está en `/data/barranco/reports/baseline-v1/REPORTE.md`;
se regenera con `python3 -B tools/report_campaign_timings.py`. Sus 20,508 h de
componentes conocidos y la simulación LPT no sustituyen T(1) experimental.

## 8. Criterios para escalar el piloto

Revisar juntos geometría, cobertura, costuras, texturas, recursos y navegación.
Congelar entonces parámetros y presupuestos, registrar la decisión y ampliar
teselas por lotes con reanudación verificable. Antes de cada expansión calcular
espacio de entradas, temporales y salida con margen; conservar la reserva de
50 GiB de la maestra. Publicar únicamente teselas validadas con checksums,
manifiesto, versiones, métricas y advertencias de cobertura.

La siguiente acción operativa propuesta es ese piloto de tres recortes, después
de acordar su área, equipo de visualización y tolerancias de calidad.
