# Consolidación de fuentes — 16 noviembre 2026

## Qué se hizo

Se reunió código previamente distribuido entre el toolkit del home, un Git de
orquestación independiente, apps ignoradas por ese Git y helpers de sesión.
Se incluyeron archivos recientes sin seguimiento, tests y documentación.
Los repositorios, servicios y campañas originales no se movieron ni reemplazaron.
No se incorporó el repositorio externo de alineación ni el pipeline externo.

La copia es un snapshot de código con un historial nuevo deliberadamente:
importar historiales sin auditar podría publicar secretos o archivos antiguos
que ya no aparecen en el árbol actual.

## Sanitización pública

- No se copian ficheros de credenciales, claves de host, entornos o estados.
- Inventario real reemplazado por `site.example.json`.
- MACs completas y LAN del laboratorio reemplazadas por ejemplos coherentes.
- Identificadores Drive conocidos de las asignaciones redactados.
- Colocaciones manuales reales, matrices de estado y revisiones no se publican.
- Archivos binarios, imágenes, logs y resultados quedan fuera del snapshot.

La sanitización afecta la copia pública. Los originales en uso no cambian.
Hashes de bundles históricos publicados en la documentación describen las
ejecuciones originales, **no autorizan ejecutar las copias sanitizadas**.

## Limitaciones detectadas que no se ocultan

1. Hay rutas absolutas heredadas (`/home/exitoso`, `/data/barranco`,
   `/tmp/opencode`). Hay que adaptar y validar antes de otro despliegue.
2. Los helpers de `operations/legacy-session-20261116/` contienen parámetros de
   campañas históricas y algunas dependencias en otros helpers. No se ejecutan
   por defecto ni se presentan como una API genérica.
3. Algunos lanzadores usan specs de `phone-run/m3/006/` que son estado local,
   deliberadamente excluido. Esas entradas deben regenerarse, no inventarse.
4. El editor manual depende de cambios del motor externo que, al consolidar,
   tenían modificaciones locales no publicadas. Este snapshot no convierte
   esa dependencia externa en reproducible desde un clon público.
5. Las aplicaciones necesitan el manifiesto activo y sparse externas. El código
   por sí solo no reproduce el mapa ni las colocaciones del usuario.
6. Los scripts históricos pueden incluir acciones destructivas o de energía.
   Su conservación no los convierte en acciones aprobadas.
7. `home/opencode.md` y los historiales son fotografías de una instalación
   anterior; no son telemetría actual de quien clone el repositorio.

## Próxima migración, separada de este respaldo

Adaptaciones pequeñas realizadas solo en la copia:
- El lookup de manifests del orquestador reconoce el checkout por `releases/`,
  sin exigir publicar una configuración privada `site.json`.
- Los tests del controlador usan explícitamente `site.example.json`.
- Se añadió un gate estático de publicación y CI de tests sin hardware.

Comprobación local inicial:39tests aprobados (25controlador,5manager,3monitor,
2GLOMAP,1workerdevocabulario y3lector sparse). No se ejecutaron campañas ni
tests de navegador sobre los servicios de producción.

Centralizar paths en configuración, convertir helpers de sesión en CLI con
argumentos/validaciones, ampliar tests sin hardware y fijar la versión publicada
del backend externo. Hacerlo sin modificar los despliegues existentes hasta
validar cada componente.
