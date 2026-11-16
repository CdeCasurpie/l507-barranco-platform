# Validación del controlador v0.1

## Independencia de la maestra

- Proyecto y repositorio Git propios: `/home/exitoso/lab-deploy`.
- `/home/exitoso/Makefile` conserva el SHA256 inicial:
  `6875bd663996c661f805d3df3ca404a979b72e124a0ec36de79a118b54843c86`.
- El proyecto está ignorado por el repositorio padre, sin editar su `.gitignore`.
- No se instalaron paquetes del SO de la maestra. Se comprobó también la
  instalación normal de un wheel en un entorno temporal, fuera del checkout.

## Comprobaciones automatizadas

30 pruebas del controlador cubren registro e identidad, exclusión de la maestra,
selección de disco con UUID clonado, caminos relativos, secretos en manifiestos,
imagen/tag de versiones, caché corrupto, escritura atómica concurrente, política
de servicios, permisos con umask privado, snapshot de archivos inicialmente
ausentes, activación y retorno de versión, fuentes temporales, conexión perdida,
reconexión sin worker duplicado y una copia rsync real con prefijo incorrecto.

Las pruebas se ejecutan con `python3 -m unittest discover -s tests -v`.

## Pruebas reales en L507_014

- Adopción de la instalación certificada, sin sustituir su checkout ni su
  `node.env` original. Primera ejecución: `a1804c5f10e1`.
- Segunda ejecución sin cambios ni transferencias/reconstrucción:
  `58091cc96a0f`, `changed=false`.
- Release canario separado `labctl-lifecycle-smoke`: la primera validación
  detectó permisos incorrectos de archivos/directorios creados por root. El
  candidato no se activó. Se corrigieron propiedad y creación de padres.
- `retry --failed` reutilizó archivos y completó la validación real del canario:
  `6c2cf2cfda68`, después del intento `f3463ec15326`.
- Rollback real a `l507-segmentation-v1`, preservando código, entorno y resultados
  originales. El canario permanece aparte como evidencia.

## Instalación real desde cero en L507_015

Ejecución `ed338961c69b`, worker `8bbcbb732e9e`:

- IP observada 192.0.2.61, MAC 02:00:00:00:00:01; identidad comprobada en cada RPC.
- Driver 595.99.02 conservado. Docker, containerd y Toolkit instalados con el
  perfil certificado. Almacenamiento en `/data/photogrammetry/runtime`.
- Imágenes y pesos transferidos directamente desde 014, reanudables y verificados
  por SHA256. La mayor parte del tiempo fue transferencia sobre 100 Mb/s.
- Git fijado al commit `a45d44258f5199b06aa57f7d6ae947f40c5326ed`.
- Ambos doctor pasan; las 26 pruebas del pipeline pasan.
- Segmentación SegFormer + SAM 3 y reconstrucción hasta OpenMVS correctas:

| Medida | Resultado |
|---|---:|
| Frames | 20, primeros 10 s de cuadra 025, 1280 px |
| Cámaras registradas | 20/20 |
| Puntos sparse | 16603 |
| Puntos densos | 1496347 |
| Error medio de reproyección | 0.349491 px |
| Píxeles excluidos, media | 12.77% |
| Tiempo de etapas | 43.53 s |

- Las etapas se ejecutaron en los dos IDs de imagen certificados, sin red.
- Durante la transferencia, un segundo `start` real fue rechazado por el lease
  antes de poder modificar el nodo.
- Cierre/reapertura real del volumen, y segundo deploy `da3d3bdbd208`:
  `success`, `changed=false`, sin repetir inferencia ni reconstrucción.

Código y datos activos:

```text
/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1/code/
/data/photogrammetry/.lab-deploy/releases/l507-segmentation-v1/data/
```

## Fuente cerrada y pipeline de verificación genérico

Se publicó un archivo canario pequeño en el caché de 014 y se cerró su volumen.
La ejecución `30dcec6a0651`, release local `labctl-source-cycle-smoke`, demostró:

1. Apertura bajo demanda del origen 014.
2. Copia y checksum del recurso faltante, reutilizando el resto del caché de 015.
3. Un comando de verificación de archivo ajeno a fotogrametría, con su entorno de
   release, sin exigir métricas de COLMAP a un pipeline genérico.
4. Restauración efectiva del origen a cerrado; comprobada por una consulta real.
5. Rollback de 015 a `l507-segmentation-v1`.

Después se volvió a abrir 014 para devolverla al estado abierto que tenía antes
de esta prueba. Los manifiestos de estos canarios están en `.state/`, no en el
catálogo público de releases de producción.

## Preservación del host

Auditoría real después de las pruebas:

| Nodo | Paquetes driver/kernel comprobados | Cambios | fstab | Política APT | Servicios al arrancar |
|---|---:|---|---|---|---|
| 014 | 60 | ninguno | idéntico | restaurada | Docker/socket/containerd disabled |
| 015 | 39 | ninguno | idéntico | restaurada | Docker/socket/containerd disabled |

Los backups tempranos del desarrollo sin registro de ausencias se reconocen como
`legacy_unsealed`; no se reinterpretan ni se sobrescriben sus datos anteriores.
Las instalaciones nuevas sellan el snapshot inicial, incluidas las rutas que
no existían, para que un reintento no registre configuraciones nuevas como antiguas.

Los reportes completos, métricas y logs permanecen en `.state/` y en los nodos;
no incluyen contraseñas y no se versionan. No se ha ejecutado un despliegue masivo:
la configuración real de esta implementación se limitó a los canarios 014 y 015.

## Despliegue masivo del laboratorio (2026-11-08)

Se montaron las 19 particiones de datos (488.29 GiB ext4 por nodo) y se desplegó
`l507-segmentation-v1` en todas las hijas registradas. La 012 conservó su
instalación piloto y sus resultados originales; el release administrado quedó
aparte, bajo `.lab-deploy`.

| Ejecución | Nodos | Resultado |
|---|---|---|
| `7ae3e447e40f` | 001, 002, 003 | 3/3 éxito |
| `350540526dc6` | 004, 005, 006, 008, 009 (007 no observada) | 4/5 éxito; 008 bloqueada por APT ajeno |
| `0dc636440406` | 007, 008, 010, 011, 019, 021, 022, 023, 024, 012 | 6/10; 012 adoptada y validada; reintento para 4 |
| `621e3401e486` | 007, 008, 011, 023 | 3/4; 007 con repositorio ROS sin clave |
| `e3741c250b68` | 007 | éxito |

Estado final verificado con `discover` y `audit --all`:

- 19/19 disponibles, volumen montado, Docker activo y release
  `l507-segmentation-v1` activa.
- 19/19 demos correctas: 20/20 cámaras, 12.77% de píxeles excluidos y entre
  1,496,347 y 1,498,671 puntos densos (la 014 conserva el smoke de su canario,
  1,496,017, con el mismo código e imágenes; su meta adoptado no repite smoke).
- 0 cambios de paquetes de driver/kernel en los 19 nodos; `fstab` sin cambios,
  política de servicios restaurada y Docker/socket/containerd deshabilitados al
  arranque. La maestra no fue objetivo en ningún momento.

Incidencias corregidas durante el despliegue:

- Raíz llena en 007 y 008 (0 bytes libres): se liberaron journal (límite 200 MiB),
  caché/índices de APT y revisiones antiguas de snap. El instalador ahora guarda
  índices y paquetes de APT en `$DATA_ROOT/.lab-deploy/apt` y exige 1.5 GiB libres
  en raíz antes de instalar.
- Repositorio ROS 2 preexistente sin clave GPG en 007: `apt-get update` devuelve
  100 por repositorios ajenos; el instalador tolera ese fallo y valida después con
  la simulación de instalación de los paquetes fijados.
- Bloqueos de APT de otros procesos (actualizaciones del sistema) en 008 y 023:
  el instalador espera hasta 10 minutos por los bloqueos y, si persisten, el nodo
  se reintenta sin intervención destructiva.
- Descubrimiento intermitente de 007: se reintentó con tag/MAC verificados.
- Espacio raíz resultante ajustado en 007 (1.3 GiB), 008 (2.3 GiB), 023 (2.9 GiB)
  y 024 (3.3 GiB); conviene vigilarlo antes de futuras actualizaciones.

Las transferencias fueron directas entre hijas desde 014, 012, 015 y nodos ya
desplegados, reanudables y verificadas por SHA256. No se instaló nada en la
maestra ni se modificó su `Makefile` (verificado con su SHA256 original).
