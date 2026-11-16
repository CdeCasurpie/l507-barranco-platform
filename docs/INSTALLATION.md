# Preparación de otra maestra

Esta es una guía de dependencias, no un instalador que opere automáticamente.

## Toolkit y orquestador

- Linux, Python >=3.11, Git, OpenSSH, rsync y utilidades de red del toolkit.
- `lab/requirements.txt` y `lab-deploy/pyproject.toml` describen dependencias.
- El entorno, cachés e imágenes pesadas deben estar en `/data`.
- `lab-deploy/config/site.json`, `.lab_wake_macs.json`, identificación de la
  maestra y claves de host son configuración local fuera de Git.
- El proveedor de credenciales usa un archivo local privado o variables cargadas
  por el operador. Nunca distribuirlo a las hijas ni pegar tokens en el chat.

La estructura histórica esperaba `~/lab`, `~/lab-deploy`, `~/home` y
`~/phone-run`. Un clon anidado no crea esas rutas automáticamente. Antes de
adaptarlas, revisar conflictos y respaldar la configuración local; no reemplazar
directorios ni enlaces de una instalación existente de forma masiva.

## Hijas

- Identidad por etiqueta + MAC, no solamente dirección DHCP.
- Volumen `/data` montado, espacio y RAM suficientes.
- Docker con almacenamiento en `/data`, imágenes fijadas por ID y drivers
  compatibles. No instalar o actualizar drivers como parte de una consulta.
- Los manifests externos describen el pipeline certificado.
- Cada ejecución tiene configuración, código y hashes propios. No reutilizar
  specs de una instalación distinta sin verificar su procedencia.

## Apps

- ROI: NumPy, SciPy, Shapely, Pillow y runtime COLMAP/PyCOLMAP 3.13 para el
  alineador integrado. Backend `Alineacion-point-cloud` externo requerido para
  matching/Sim3/BA del editor.
- Visor sparse: Python estándar, binarios COLMAP y manifiestos locales.
- Fotos, features, matrices, ROI y revisiones son entradas externas privadas.
- Arranques y límites están en los README de cada app. Verificar servicios y
  puertos antes de iniciar; no sustituir un servicio existente.

No copiar runtimes completos a Git. Registrar versiones, hashes y orígenes de
las dependencias; descargarlas solo cuando la operación lo requiera y autorice.
