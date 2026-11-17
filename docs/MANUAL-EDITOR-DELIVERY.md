# Editor manual, sparse y entregas ligeras

## Aplicaciones

- Puerto 8790: editor de deformación de cámaras por grafo; revisiones inmutables,
  selección circular, exclusiones, deshacer/rehacer y ejes locales de rotación.
- La generación de candidatos usa PyCOLMAP 3.11.1 de bajo nivel:
  `CorrespondenceGraph` + `IncrementalTriangulator`. No usa la función de alto
  nivel que incorpora BA. No ejecuta matching. Se comprueba que las poses
  editadas permanezcan fijas; las candidatas no se aprueban automáticamente.
- Puerto 8765: colocación manual con escala uniforme; selección explícita de
  revisiones, nombres legibles y publicación de la matriz guardada al mapa ROI.
  Las anclas previas no se sobrescriben.
- Pestaña «Visualizador sparse»: WebGL de solo lectura, ortográfica/perspectiva,
  RGB o color por manzana, tamaño de puntos, cuadrícula y visibilidad por capa.
  Usa sparse muestreadas del mapa. No envía operaciones de escritura.

## Operaciones históricas

`operations/manual-editor-20261117/` conserva los helpers de la sesión.
No constituyen una CLI portable: contienen rutas heredadas y dependencias entre
scripts. Las IP/MAC públicas son ejemplos, no identidades operativas.
**No importar ni ejecutar estos lanzadores para probar el repositorio.**

- Triangulación fija y densificación OpenMVS en contenedores por máquina,
  con entradas originales preservadas y límites de RAM/CPU/disco/temperatura.
- Densificación por lotes: cada lote produce su propia escena y nube. Mallado
  Delaunay con `-p scene_dense.ply` explícito; no confundir la escena que puede
  conservar sparse con la nube densa externa.
- RGB por vértice transferido desde la nube densa; no es un atlas fotográfico.
- QEM con protección de topología, bordes y normales. La reducción del 70 %
  conserva aproximadamente el 30 % de caras; el presupuesto ligero posterior
  usa la mediana de caras de la entrega de referencia. No equivale a certificar
  una densidad métrica sin conocer escala y área.
- Unión por concatenación con índices corregidos: conserva solapes. No suelda
  vértices, no fusiona superficies y no deforma automáticamente.
- Exportación en la matriz manual guardada, un objeto editable por manzana,
  renders de geometría real y galería local.
- Ensayo RefineMesh aislado: sin relleno y con cierre de huecos pequeños.
  No se declara mejora sin revisión visual; puede cerrar aberturas verdaderas.
- Render superior 8K desde sparse completas, RGB original y fondo negro.

## Limpieza y conservación

La limpieza requiere autorización separada. El helper de mapas borra únicamente
`.dmap` regulares de lotes terminados después de comprobar los hashes de las
nubes nativa y escalar y conservar la escena. Registra cada archivo eliminado.
No debe ampliarse a una máquina o campaña excluida por el operador.

El helper específico de instaladores elimina solo dos archivos identificados por
hash y tamaño, verificando que las imágenes Docker ya estén instaladas.
No ejecuta `docker prune`. Su presencia aquí no autoriza repetir la operación.

## Dependencias y validación

No se incluyen modelos, binarios, fotos, bases de datos, resultados, revisiones,
colocaciones privadas, pesos, contenedores o entornos Python.

Las pruebas sintéticas de `home/sparse-review/test_graph_edit.py` requieren el
runtime PyCOLMAP 3.11.1. Las pruebas de alineación requieren el motor externo y
el runtime 3.13 compatible con él. Las pruebas de navegador requieren Chrome y
se ejecutan con perfiles aislados. Las validaciones numéricas no certifican
calidad científica ni autorizan dense/malla por sí solas.
