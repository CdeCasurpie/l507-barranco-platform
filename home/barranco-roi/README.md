# Barranco · ROI sparse y alineación manual multiancla

Aplicación local: **http://127.0.0.1:8765**. No usa CDN, npm ni servicios externos.
No genera mallas, no rellena huecos y no altera reconstrucciones originales.
Se conserva la decisión de reparación manual y posterior reproyección de fotos:
[`../DECISIONES-MALLA-BARRANCO.md`](../DECISIONES-MALLA-BARRANCO.md).

## Inicio

Después de montar `/data`, comprobar si la instancia ya está ejecutándose:

```bash
systemctl --user status barranco-roi
```

Si no está activa:

```bash
systemd-run --user --unit=barranco-roi --working-directory=/home/exitoso/home/barranco-roi -p MemoryMax=4G -p MemorySwapMax=0 -p CPUQuota=200% -p Nice=10 /data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/app.py
```

Solo escucha en loopback. No inicia automáticamente al arrancar. La web y el
motor usan el runtime existente COLMAP/PyCOLMAP 3.13, NumPy, SciPy, Shapely y PIL.
La transferencia opcional usa el Python del sistema y el transporte SSH
existente (`pexpect`, `rsync`, host keys e inventario verificado).

## Polígonos / ROI

- Al abrir o recargar no hay manzana activa: el contexto conserva sus colores
  RGB originales, sin un bloque resaltado. En **Controles ROI** se puede elegir
  una manzana o volver a **Sin manzana activa**. Esto no borra polígonos guardados.
- Los controles ROI son un panel flotante plegable; el visor no pierde ancho.
- Vista cenital, contexto de manzanas y sparse completa de la activa.
- Dibujar, editar, deshacer/rehacer, guardar y descargar JSON.
- Rueda: zoom; arrastrar: desplazar. Espacio/botón central: pan durante dibujo.
- Interior y borde incluidos, a todas las alturas; no se filtra ruido interior.
- Las revisiones históricas se conservan byte por byte. La compatibilidad con
  selecciones anteriores se comprueba mediante hashes sparse, matriz y origen,
  sin leer ni exigir su antigua densa.
- Se retiraron del servidor y de la interfaz el análisis, preview y exportación
  de densa. Los scripts batch históricos y sus resultados no se borraron.
- Guardar prepara `state/exports/roi_<revision>.json`; no lo envía ni malla.

## Alinear una reconstrucción

Interfaz monocromática, visor a todo el ancho y panel **Controles** cerrado al
abrir una escena. Abrirlo no redimensiona ni reencuadra la nube. Las herramientas
esenciales están en la barra flotante inferior; **Vista** y **Visualización**
despliegan las opciones de cámara y apariencia. Existe botón de pantalla completa.

1. La página abre el selector **Alineación** sin cargar ninguna nube. Elegir
   corrida/componente y las manzanas adyacentes; **Abrir alineación** carga solo
   esa selección. **Cambiar nubes** permite modificarla conservando el borrador.
2. **Mover (G)**: arrastrar directamente la nube o las flechas de sus ejes.
   **Girar (R)**: arrastrar alrededor del pivote. **Escalar (S)**: arrastre
   horizontal. También hay sliders para giro X/Y/Z, escala y altura. Mayús permite
   movimientos finos. Espacio, botón central o derecho desplazan la vista.
   **F** encuadra la selección. Ctrl+Z / Ctrl+Mayús+Z deshacen/rehacen gestos completos.
   XYZ y la matriz quedan en **Valores exactos y matriz**. XYZ representa el pivote
   elegido; cambiar pivote no cambia la colocación.
3. Usar la vista cenital, laterales o 3D ortográfica. Botón derecho en 3D gira
   la vista; no gira la nube.
4. Abrir la pestaña **Vistas**. En cada referencia seleccionada:
   - **Nueva → ancla**: elegir exactamente las M imágenes/vistas a localizar.
   - **Ancla → nueva**: opcionalmente elegir N vistas en dirección inversa.
   - Elegir las vistas desde el mapa o galería. Una vista es una foto registrada,
     no una calibración compartida.
   - Reservar vistas para validación; una misma query mantiene su rol entre anclas.
5. Proponer pares con radio, dirección y presupuesto; revisar, quitar o añadir
   pares explícitos. Son sugerencias, no evidencia de solape. No se sustituye
   ninguna query. Cambiar el prior invalida las propuestas.
6. Guardar crea una sesión inmutable con matriz exacta, revisiones, vistas, roles,
   pares y política. Nada se ejecuta al guardar.
7. **Matching y ajuste Sim(3)** procesa exclusivamente esos pares, localiza con
   PnP y resuelve una única transformación contra todas las anclas fijas.
8. Revisar errores por vista/ancla y comparar resultado con prior. Las vistas
   fallidas siguen figurando en el informe. Aprobar es una acción separada.
9. Aprobar publica una colocación nueva y abre el ROI. Cada revisión tiene su
   clave propia: una colocación posterior no reutiliza el polígono anterior.

Se puede aprobar manualmente sin matching, con confirmación explícita y etiqueta
**manual sin validación**. No equivale a una alineación validada.

Por defecto no hay selección ni resaltado: se muestran los RGB originales.
**Seleccionar nube móvil** o G/R/S habilitan su manipulación y resaltado.
**Deseleccionar / Esc** retira el resaltado y los ejes sin modificar la matriz
ni la selección de vistas puente. La selección visual no se restaura al recargar,
aunque se conserve el borrador y la caché de geometría.

### Rendimiento y caché visual

- Sin petición de `/api/overview` ni carga del ROI al entrar en alineación.
  ROI se inicializa solo al abrir su pestaña.
- WebGL con buffers residentes: mover/girar cambia uniforms, no recorre ni
  transforma los puntos en JavaScript. El modo sin WebGL utiliza proyección
  sin asignaciones por punto y nivel de detalle adaptativo durante el gesto.
- El encuadre usa ocho esquinas por nube, no ordena todos los puntos.
- Los movimientos de puntero se consolidan por frame; al soltar se aplica siempre
  la posición final exacta. El zoom interpola solo la cámara, nunca la matriz
  guardada. Paneles animados mediante transform/opacity, sin animar el tamaño
  del canvas. `prefers-reduced-motion` desactiva transiciones y suavizado.
- Paquetes visuales binarios: XYZ Float32 relativos a un origen Float64 y RGBA,
  hasta 80.000 puntos por nube. **Solo afecta a la representación**, no a
  las matrices Float64, matching, sparse originales ni conteos ROI completos.
- Cachés de navegador en RAM e IndexedDB, por ID y revisión geométrica,
  limitadas a 24 entradas / 64 MiB. Peticiones simultáneas se deduplican.
  Recargar la página puede recuperar las nubes sin transferirlas otra vez.
- ETag y URLs de revisión para caché HTTP; caché de paquetes en servidor
  limitada a 12 entradas / 64 MiB. Un cambio de inode/tamaño/mtime/ctime invalida
  la revisión. El worker sigue verificando los hashes originales.
- Fotos en páginas de 24, carga diferida, miniaturas cacheadas y decode JPEG
  reducido. Elegir otra vista no desmonta y recarga toda la galería.
- Borradores locales de hasta cuatro reconstrucciones se recuperan con matriz,
  vistas y roles. **No sustituyen Guardar revisión ni aprueban alineaciones.**
- La caché solo contiene derivados visuales. No se borra ni modifica una fuente.

### Anclas y pendientes

Fuente de las 14 iniciales: `/data/barranco/active/manifest.json`.
Se fijan matrices, origen `map_world` y hashes de geometría:
`001,002,003,004,005,007,008,009,012,013,017,018,024,025`.
**023 está rechazada y no se ofrece.**

Los componentes de `/data/barranco/review/*/*/colmap/sparse/*` se registran
individualmente. Un componente no comparte transformación con otro por tener
el mismo número de manzana. También se admiten snapshots locales.
Una colocación aprobada se puede usar como otra referencia fija, mostrando su
procedencia y si fue manual o calculada. No puede ser su propia ancla.

### Insumos de matching

Ver sparse y colocar solo requiere `cameras.bin`, `images.bin`, `points3D.bin`.
Matching necesita fotos **originales**, keypoints/descriptores SIFT e índices
compatibles. No se mezclan features originales con fotografías rectificadas.

Los snapshots locales se adjuntan mediante un JSON:

```json
{
  "block_id": "026",
  "sparse": {"model_uri": "/data/barranco/.../model"},
  "features": {"database_uri": "/data/barranco/.../features.db", "family": "sift"},
  "images": {"root_uri": "/data/barranco/.../frames"}
}
```

Este contrato manual no exige ni inventa GPS. El API automático antiguo de
BlockAlign conserva su contrato geográfico; no se falsea para admitir teléfonos.

**Traer fotos y features desde su hija** requiere confirmación, copia solo
entradas, comprueba etiqueta/MAC y la revisión sparse, verifica hashes y exige
50 GiB de reserva. No modifica la hija, no enciende máquinas ni reanuda corridas.
Una base con WAL activo se rechaza, no se altera. Si cambió la sparse remota,
se rechaza la transferencia: debe registrarse esa otra revisión.
Los parciales propios quedan para diagnóstico; no se eliminan datos del usuario.

### Bundle adjustment restringido

Acción opcional y explícita: **Matching + Sim(3) + BA restringido**.

- Primero exige una Sim(3) validada.
- Optimiza reproyección de poses/puntos seleccionados del bloque nuevo.
- Cámaras y geometría originales de las anclas nunca son variables ni se fusionan.
- Intrínsecos fijos. Las vistas reservadas se excluyen del objetivo.
- Presupuesto inicial: 48 poses, 3.000 puntos, 40 evaluaciones; techo de 150.000
  observaciones. Informa IDs de poses variables y conteos.
- Rechaza degradación de reproyección, deriva de cámaras >2 m/5° y deformación
  de puntos p95 >2 m.
- Después vuelve a localizar las vistas reservadas contra la geometría resultante.
- Publica una sparse derivada en `map_world`. **La densa anterior requiere
  regeneración**, no se etiqueta como corregida ni se borra.

Sim(3) conserva la geometría interna y puede reutilizar una densa del mismo
linaje verificado. BA no descubre correspondencias y no puede resolver falta de
solape. Los umbrales actuales no certifican precisión topográfica absoluta.
La validación es condicional a la SfM original; frames cercanos y matching
recíproco pueden estar correlacionados.

## Estado, supervisión y seguridad

Desde `/home/exitoso`, ejecutar **`make barranco-status`** para consultar el
pipeline de las hijas (descarga, etapa, worker vivo, error, temperatura GPU
actual y espacio en `/`). Alias: `make pipeline-status`; salida estructurada:
`make barranco-status-json`. Es solo consulta: no recoge resultados, reintenta
ni inicia trabajos. Una parada térmica sigue visible aunque la GPU ya esté fría.
La campaña nueva y sus incidencias están en
[`../OPERACION-20261116-PREFLIGHT-DESCARGAS.md`](../OPERACION-20261116-PREFLIGHT-DESCARGAS.md).

`state/alignment/` contiene:

- `anchors.json`: snapshot fijo; si cambia, se exige otro estado.
- `reconstructions/`: identidades de corrida/componente y hashes.
- `sessions/`: revisiones inmutables elegidas por el usuario.
- `jobs/`: solicitud, snapshot del código, progreso, pares, auditorías,
  localizaciones, errores y resultados.
- `placements/`: aprobaciones, siempre revisiones nuevas.

Workers independientes en servicios `barranco-align-j-*` con 4 CPU, 40 GiB,
swap=0, 4 h y grupo de procesos propio. Hay comprobación real de cgroup y guarda
térmica. Cancelar detiene solo ese servicio y sus hijos. Cerrar el navegador o
reiniciar la web no cancela el worker; el historial permite recuperarlo. La
interrupción/OOM no se interpreta como éxito. No se reutilizan mediciones de
otras selecciones: cada solicitud fija sus entradas y código.

Los POST requieren origen local y cabecera del editor. No hay servidor general
de archivos ni rutas arbitrarias. El acceso a entradas se restringe a
`/data/barranco` y derivados propios.

## Pruebas

```bash
/data/barranco/runtime/alignment313/bin/python -B -m unittest discover -s /home/exitoso/home/barranco-roi/tests -v
cd /data/repos/Alineacion-point-cloud
PATH=/data/barranco/runtime/alignment313/bin:$PATH PYTHONPATH=src /data/barranco/runtime/alignment313/bin/python -B -m pytest tests -q
/data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/tests/alignment_browser_check.py
/data/barranco/runtime/alignment313/bin/python -B /home/exitoso/home/barranco-roi/tests/alignment_browser_check.py --fallback
```

Incluyen matching/PnP/BA nativos sobre datos sintéticos, multiancla bidireccional,
conservación de originales, vistas reservadas, servicio supervisado real,
compatibilidad de polígonos y navegador real con estado diagnóstico aislado.
No alinean ni aprueban automáticamente reconstrucciones reales.
La prueba de navegador comprueba carga exclusiva de las vecinas, gestos,
buffers reutilizados, recuperación desde IndexedDB tras recarga y ausencia de
peticiones de nubes mientras se giran/mueven. Escribe métricas diagnósticas en
`/tmp/opencode/alignment-perf-{gpu,fallback}.json`.
