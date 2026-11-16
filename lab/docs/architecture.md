# Organización y dependencias actuales

## Punto de entrada

El Makefile de `/home/exitoso` conserva los mismos objetivos, argumentos y
opciones. Cada receta apunta ahora a `lab/scripts/`.

## Responsabilidades

| Script | Responsabilidad |
| --- | --- |
| `lab_inventory.py` | Inventario y utilidades ya compartidas de descubrimiento, sondeo y presentación |
| `lab_monitor.py` | Monitor, lectura de etiquetas y persistencia de IPs |
| `lab_restart_all.py` | Envío de reinicio y espera de retorno |
| `lab_lock_all.py` | Bloqueo de sesiones gráficas |
| `lab_unlock.py` | Desbloqueo y alternativa de autologin mediante GDM |
| `lab_logout.py` | Cierre de sesiones gráficas |
| `lab_wake.py` | Envío de Magic Packets y comprobación de arranque |
| `lab_turnoff.py` | Apagado remoto y comprobación de caída de SSH |
| `lab_config.py` | Lectura de los valores locales de credenciales |

Reinicio, bloqueo, desbloqueo y cierre de sesión ya dependen de
`lab_inventory.py`. Mantener todos los scripts como hermanos conserva la
resolución de esos imports al ejecutarlos por ruta, sin paquetes, wrappers ni
modificaciones a `PYTHONPATH`.

## Alcance de esta reorganización

Se han movido los archivos completos. No se han extraído funciones ni cambiado
los comandos remotos, filtros, tiempos de espera, protocolos o selección de
máquinas. La única modificación previa autorizada fue sustituir claves literales
por valores de un archivo local ignorado, respetando las variables de entorno.

Los archivos de estado siguen en sus rutas originales bajo el home porque los
scripts las utilizan directamente. El marcador `L507_MAESTRA.txt` también queda
en el home: el inventario identifica la maestra buscando allí su etiqueta.

## Redundancias detectadas

Hay implementaciones repetidas de autenticación SSH con pexpect, detección de
subred, comprobación del puerto 22, colores ANSI y lectura de JSON. Son
duplicaciones preexistentes; agrupar archivos no elimina código duplicado.

Una extracción futura podría separar transporte SSH, red, presentación y
persistencia en módulos comunes. Requiere autorización para refactorizar y
verificación específica: hay diferencias entre los sondeos y sus tiempos de
espera, así como entre los formatos devueltos por cada descubrimiento de red.
En esta fase se preservan esas diferencias para mantener el comportamiento.
