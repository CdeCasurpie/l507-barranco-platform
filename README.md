# L507 Barranco Platform

Toolkit de laboratorio, orquestación distribuida y aplicaciones de revisión
fotogramétrica del proyecto Barranco.

**No es el pipeline fotogramétrico ni el motor externo de alineación.**
Este repositorio los integra como dependencias separadas.

## Componentes

| Ruta | Contenido |
|---|---|
| `Makefile`, `lab/` | Inventario, monitor de red y herramientas explícitas de administración L507 |
| `lab-deploy/labdeploy/` | Coordinador de despliegue, identidad de nodos, volúmenes, transporte y estado |
| `lab-deploy/tools/` | Workers y herramientas de campañas, guardas, sparse, recogida y diagnósticos |
| `lab-deploy/releases/` | Manifiesto del pipeline externo y sus imágenes certificadas, fijados por hash |
| `home/barranco-roi/` | App ROI y editor de colocación/alineación manual |
| `home/sparse-review/` | Visor sparse y catálogo multimanana en un solo puerto |
| `phone-run/` | Helpers de las campañas iniciales, conservados como código histórico |
| `operations/legacy-session-20261116/` | Helpers recuperados de la sesión operativa; no son una CLI portable |
| `operations/manual-editor-20261117/` | Helpers históricos de triangulación fija, dense, RGB, entregas y renders |
| `home/*.md`, `docs/` | Decisiones, historial, seguridad y documentación operativa |

## Seguridad antes de ejecutar

- **Clonar este repositorio no autoriza ninguna operación remota.**
- Consultar estado no autoriza energía, potencia, limpieza o reintentos.
- La maestra nunca es objetivo de apagado/reinicio.
- Guardas GPU: **80 °C sostenidos durante 30 s; 85 °C inmediato**.
- Nuevas pruebas sparse se detienen para revisión; una salida completa no implica
  geometría correcta ni autorización de densa, malla, textura o alineación.
- No sobrescribir originales, máscaras, BD/features, revisiones o Blender editable.
- Los programas `start`, `resume`, `recover`, `cleanup` y scripts históricos
  pueden modificar datos. Leer su código y acordar acción/nodos antes de usarlos.
- `review_experiments.py` también recoge resultados: **no es solo un monitor**.

## Configuración local

La copia pública contiene IPs de documentación `192.0.2.0/24`, MACs de ejemplo
localmente administradas y referencias Drive redactadas. **No son un inventario
operativo y no deben sustituir la configuración del laboratorio existente.**

1. Consultar [instalación y dependencias](docs/INSTALLATION.md).
2. Preparar, fuera de Git, `lab-deploy/config/site.json` a partir de
   `lab-deploy/config/site.example.json`.
3. Configurar el proveedor local de credenciales descrito en
   `lab-deploy/README.md`. Nunca poner claves en comandos, commits o incidencias.
4. Configurar registro MAC, claves de host confiables, rutas y almacenamiento
   `/data`. No copiar `.state/` desde otro laboratorio como configuración pública.

La consolidación conserva el código en uso, incluidos paths de la instalación
original. **No es todavía una migración automática ni una instalación portable
de un solo comando.** Véase [auditoría de consolidación](docs/CONSOLIDATION.md).

## Dependencias externas

- Pipeline: <https://github.com/AaronCS25/photogrammetry-pipeline>,
  commit de la release `a45d44258f5199b06aa57f7d6ae947f40c5326ed`.
- Motor numérico de alineación: repositorio `Alineacion-point-cloud`, externo.
  El código del editor manual se incluye; su backend numérico no.
- COLMAP/PyCOLMAP, imágenes Docker, pesos de segmentación y vocabularios se
  provisionan explícitamente; **no se distribuyen aquí**.

La app de alineación usa el runtime 3.13. Su compatibilidad completa con
PyCOLMAP 3.11 **no está implementada** (`Rig`). Los workers de campañas usan su
runtime certificado separado.

## Pruebas sin ejecutar campañas

Los cambios del editor y las entregas están documentados en
[Editor manual y entregas](docs/MANUAL-EDITOR-DELIVERY.md).

Consultar [pruebas](docs/TESTING.md). No ejecutar scripts operativos para
comprobar si “funcionan”: varias herramientas actúan al importar o arrancar.

## Alcance del respaldo

Se publica un snapshot nuevo del código, no el historial Git de los repositorios
de origen ni datos de campañas. Sus repositorios e historiales originales se
conservan localmente. `docs/SOURCE-SNAPSHOT.json` registra procedencia y hashes.

No incluye credenciales, inventarios reales, estados, revisiones manuales,
fotografías, BD, pesos, nubes, densas, mallas ni `.blend`. Su respaldo científico
es una tarea separada.

No se asigna una licencia nueva a código existente sin confirmar sus derechos.
Las dependencias externas conservan sus propias licencias.
