# L507 Lab Deploy

La campaña de reconstrucción 4K, sus límites de recursos, densificación por
lotes y operación están documentados en
[`docs/BARRANCO-CAMPAIGN.md`](docs/BARRANCO-CAMPAIGN.md). La preparación de
releases y la ejecución de reconstrucciones son operaciones distintas.

El siguiente experimento y el protocolo de evaluación de tesis están en
[`docs/MESH-AND-BENCHMARK-PLAN.md`](docs/MESH-AND-BENCHMARK-PLAN.md).

Controlador independiente para preparar hijas GPU y desplegar releases desde la
maestra. Proyecto Git propio: **no modifica `/home/exitoso/Makefile` ni refactoriza
el toolkit del laboratorio**. La maestra coordina; las hijas almacenan imágenes,
pesos y resultados y ejecutan las pruebas.

## Inicio rápido

Requisitos en la maestra: Python >=3.11, OpenSSH y `pexpect`. En esta instalación
ya están disponibles. El perfil de preparación de hijas soporta Ubuntu 24.04,
Python del sistema, una partición ext4 existente de 400–600 GiB y GPU NVIDIA con
driver operativo. No instala/reemplaza drivers ni formatea particiones.

```bash
cd /home/exitoso/lab-deploy
python3 -m labdeploy releases
python3 -m labdeploy discover
python3 -m labdeploy mount --all
python3 -m labdeploy plan --targets 014,015 --release l507-segmentation-v1
python3 -m labdeploy deploy --targets 015 --release l507-segmentation-v1
python3 -m labdeploy status
python3 -m labdeploy wait
```

`mount` solo monta e inspecciona la partición de datos (400–600 GiB) y también se
ejecuta automáticamente dentro de `deploy`. `deploy` devuelve un identificador y
continúa en segundo plano, incluso si se cierra la terminal. `--wait` permite
seguirlo en primer plano. Los workers remotos también sobreviven a desconexiones
SSH; un reinicio interrumpe el worker y se recupera con una orden de reintento,
sin guardar contraseñas para autoarrancar. Los índices y la caché de APT se
guardan en el volumen de datos, y los bloqueos de otros procesos APT se esperan
hasta 10 minutos por defecto.

Para las hijas registradas y accesibles:

```bash
python3 -m labdeploy plan --all --release l507-segmentation-v1
python3 -m labdeploy deploy --all --release l507-segmentation-v1 --parallel 2
```

La maestra nunca es un objetivo. Las no accesibles se reportan; no se encienden,
reinician, bloquean ni cierran sesiones. Una ejecución con nodos bloqueados o no
accesibles termina como `partial`, no como éxito de toda la flota.

## Consulta y recuperación

```bash
python3 -m labdeploy status --run ID --refresh
python3 -m labdeploy status --run ID --details
python3 -m labdeploy logs --node L507_015 --run ID
python3 -m labdeploy retry --failed --run ID --wait
python3 -m labdeploy rollback --targets 014 --release l507-segmentation-v1
python3 -m labdeploy audit --targets 014,015
```

`status` sin ID consulta el último despliegue enviado; si hay varias ejecuciones
simultáneas, usar sus IDs. `discover` muestra también el release activo de los
volúmenes abiertos. `--refresh` consulta el worker real. Los reintentos vuelven a
descubrir IPs y pueden reconectarse al worker que siga ejecutándose, en vez de
lanzar otro. Tras un fallo de origen, el reintento prefiere el otro seed disponible.

El rollback exige una versión completa y saludable ya presente. Cambia el
puntero de activación para próximas ejecuciones. No desinstala Docker, no revierte
el kernel ni borra experimentos. Las migraciones del almacenamiento del host
tienen respaldos independientes y no se deshacen reemplazando bases de datos en
caliente.

## Identidad, credenciales y alcance

`config/site.json` contiene la lista pública tag/MAC, la subred, el usuario SSH,
los orígenes y las rutas. No contiene claves. Por defecto se integran las
funciones de descubrimiento de `~/lab/scripts/lab_inventory.py`, sin editarlo;
hay sondeo TCP propio de respaldo si ese toolkit no existe.

Se reutiliza el proveedor local `lab_config.py` del toolkit. Fuera de ese entorno,
pueden suministrarse `LAB_SSH_PASSWORD` y `LAB_SUDO_PASSWORD` en el entorno del
coordinador. No ponerlas en argumentos, manifiestos o Git. Se transmiten mediante
prompts privados y permanecen en memoria; no se distribuyen archivos de claves a
las hijas. El token HF no hace falta para copiar pesos ya descargados.

En cada acción se comprueban el TXT del usuario remoto y la MAC esperada. La IP
descubierta no es identidad suficiente. La selección por `--all` está limitada al
registro de hijas. Un tag duplicado, desconocido o contradictorio queda fuera.

Configurar otra maestra: clonar este proyecto, instalarlo opcionalmente en un
venv con `pip install -e .`, adaptar `site.json`/un archivo local y proporcionar
el adaptador de credenciales o las variables de entorno. Puede usarse `labctl`
como entry point si se instala el paquete; `python3 -m labdeploy` no necesita esa
instalación. `--site ARCHIVO` y `--state DIRECTORIO` son opciones globales, antes
del subcomando. Nunca copiar `.state/` como si fuese configuración pública.

## Qué hace el despliegue

1. Verifica identidad y disponibilidad de driver, y rechaza cargas Docker/GPU
   activas antes de preparar el host.
2. Descubre la partición por filesystem/tamaño y comprueba su montaje. No asume
   número de partición ni unicidad de UUID entre PCs clonadas. Una partición
   montada en otro lugar o con contenido no enrolado necesita inspección manual.
3. Inspecciona inicialmente en solo lectura cuando corresponde; crea el área
   privada del proyecto y guarda configuración y lista de paquetes anteriores.
4. Instala Docker/Toolkit si faltan, con versiones del perfil certificado. Antes
   de APT instala condiciones de montaje; bloquea temporalmente el autoinicio de
   servicios. Simula APT y rechaza cambios de driver/kernel. Restaura cualquier
   `policy-rc.d` preexistente incluso si APT falla.
5. Configura Docker **y containerd** en el volumen. Si hay runtime previo y debe
   moverse, exige inactividad, realiza copia fría y verifica con rsync checksum
   antes de cambiar sus rutas. Conserva el almacenamiento original y respaldos;
   no lo elimina para recuperar espacio automáticamente.
6. Adopta una instalación certificada compatible, o copia únicamente recursos que
   falten mediante SSH/rsync directo desde los seeds. No pasan archivos grandes
   por el disco de la maestra. Descargas parciales se conservan y verifican.
7. Prepara código y configuración de un release separado. Ejecuta sus comandos de
   diagnóstico y prueba como el usuario de la hija, no como root.
8. Solo tras pasar las comprobaciones cambia atómicamente el release activo.

Un bloqueo por nodo evita dos despliegues concurrentes. Ese bloqueo también
protege el helper nuevo de volumen. Los seeds son 014 y 012; si el controlador
necesita abrir uno cerrado, registra ese hecho y trata de cerrarlo al finalizar.
Si pierde certeza sobre un worker vivo, conserva el origen abierto y lo reporta
en vez de cortarle la transferencia. Los montajes que ya estaban abiertos se
mantienen abiertos.

## Rutas de una hija

```text
/var/lib/lab-deploy/
  status.json                   # estado legible del último worker
  backups/initial/              # respaldo privilegiado previo
  job-<id>.log                  # log privado, consultable con labctl logs
  deployment.lock               # lease de nodo

/data/photogrammetry/
  runtime/{docker,containerd}/   # compartido por los releases del host
  .lab-deploy/
    cache/<sha256>              # contenido verificado; .part si está incompleto
    releases/<release>/
      code/                    # checkout limpio, commit fijo
      data/{models,datasets,outputs,scratch,logs}/
      node.env
      meta.json
      release.json
      verify-N.log
    current -> releases/<release>
```

Los modelos y videos se enlazan al caché en el mismo filesystem, evitando otra
copia de sus bytes. No editar esos recursos en sitio: para datos/modelos nuevos,
usar hashes y un release/escena nuevos. Un release antiguo conserva sus recursos
y resultados al cambiar de versión. Las imágenes Docker siguen siendo globales
al host, pero cada release fija IDs y los verifica antes de activarse.

Las instalaciones legacy pueden conservar código, datos y `node.env` en sus rutas
originales (caso 014). `meta.json` contiene las rutas reales, por lo que no se
debe asumir que todo código legacy está dentro de `current/code`.

En una instalación nueva, para ejecutar otro video se usa el checkout de
`current/code`, el entorno `current/node.env` y una escena nueva bajo
`current/data/datasets/raw/`. Consultar el README del pipeline para sus parámetros.
Un usuario que ya tenía una sesión SSH antes de añadirse al grupo Docker debe
abrir una nueva conexión para recoger esa pertenencia.

## Cambiar de pipeline o versión

El controlador y sus releases están separados del código del pipeline. En
`releases/*.json` se declaran:

- Nombre único e inmutable del release.
- URL GitHub HTTPS pública y commit exacto ya publicado.
- Imágenes: tag de distribución, ID esperado y archivo certificado.
- Artefactos: SHA256, tamaño, rutas de origen por seed y destino relativo de datos.
- Variables no secretas del entorno.
- Comandos de verificación como listas de argumentos.
- JSON de métricas y expectativas opcionales, adaptables a otros pipelines.

```bash
# Crear/editar un manifiesto con nombre y commit nuevos.
python3 -m labdeploy check-release --release releases/mi-pipeline-v2.json
python3 -m labdeploy plan --targets 014 --release releases/mi-pipeline-v2.json
python3 -m labdeploy deploy --targets 014 --release releases/mi-pipeline-v2.json --wait
# Tras comprobar el canario:
python3 -m labdeploy deploy --all --release releases/mi-pipeline-v2.json
```

Si solo cambia Git, se reutilizan imágenes y pesos. Los pesos se catalogan por
archivo: cambiar SegFormer no obliga a copiar SAM 3. Una imagen distinta se
transfiere como archivo completo en esta versión; no hay registry de capas.
Si cambia el ID de una imagen, usar también un tag de versión nuevo (por ejemplo
`:l507-v2`): el controlador rechaza sobrescribir el tag de un release guardado,
para conservar el rollback. Actualizar sus variables de entorno en el manifiesto.
Los recursos nuevos deben prepararse en un seed y declararse con tamaño/hash
reales. No sobrescribir los recursos de un release anterior ni subir pesos a Git.

`tools/import_catalog.py` crea el manifiesto inicial desde la 014 certificada;
no sobrescribe un manifiesto existente. `tools/lifecycle_probe.py` crea un canario
local en `.state/` para probar actualizaciones sin publicar una versión falsa.

## Pruebas y límites de esta versión

```bash
python3 -m unittest discover -s tests -v
```

Las pruebas incluyen identidad, paths, particiones con UUID repetidos, caché
corrupto, rsync real sobre copia interrumpida, estado atómico, recuperación de
policy, restauración de fuentes y reconexión de workers. La validación real usa
014 para adopción/actualización/rollback y 015 para instalación nueva.

No es todavía un planificador de videos ni un servicio de autoactualización.
El despliegue inicial es pesado en una red de 100 Mb/s: puede tardar decenas de
minutos por hija. Los orígenes y workers deben permanecer encendidos; el
controlador no ejecuta acciones de energía. Un corte de energía durante una
migración/instalación requiere consultar el estado y reintentar; los respaldos y
runtime original se conservan para recuperación administrativa.
