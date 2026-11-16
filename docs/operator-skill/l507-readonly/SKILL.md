---
name: l507-readonly
description: "Laboratorio UTEC L507: contexto del toolkit y consulta de estado mediante make check y make monitor. Usar al revisar máquinas, tags, IPs, MACs, GPU o el Makefile de /home/exitoso; solo lectura, sin acciones de energía ni sesiones sin consentimiento explícito."
---

# Laboratorio UTEC L507 — consulta de solo lectura

## Regla principal

Esta skill es para observar el laboratorio, no para administrarlo activamente.
Los únicos objetivos operativos autorizados por defecto son **`make check` y
`make monitor`**. `make` o `make help` pueden usarse para consultar la ayuda.
La presencia de otros objetivos en la ayuda NO autoriza su ejecución.

**Nunca encender ni apagar máquinas sin consentimiento explícito del usuario
para esa acción y esas máquinas.** Tampoco reiniciar, bloquear, desbloquear,
cerrar sesiones o cambiar configuraciones como parte de una revisión.

- Una petición como «revisa», «comprueba», «diagnostica», «arregla el monitor» o
  «procede» dentro de una consulta no autoriza cambios de estado.
- Una autorización histórica no es autorización permanente. Que una operación
  haya funcionado antes no permite repetirla como prueba.
- Una orden explícita como «enciende la 019» solo autoriza esa operación sobre
  la 019; nunca extenderla a todas las hijas.
- Si el usuario pide una acción de escritura, indicar que sale del modo de
  consulta. Obtener aclaración si falta acción o alcance. Esta skill no contiene
  un procedimiento para ejecutarla: no ejecutar acciones mutantes dentro de su
  flujo de diagnóstico. La autorización explícita deberá tratarse como una
  tarea operativa separada.
- **La maestra no es un objetivo operativo:** nunca apagarla, reiniciarla,
  bloquearla, cerrar su sesión ni enviarle paquetes WoL.

## Acciones excluidas del flujo de esta skill

No ejecutar los objetivos `wake`, `wake-all`, `turn-off`, `turn-off-all`,
`restart-all`, `lock-all`, `unlock`, `unlock-all`, `logout` o `logout-all`.
No invocarlos indirectamente mediante Python, SSH, sudo, shell, tareas
delegadas, paquetes Magic Packet ni alias. No ejecutar secuencias de
apagado/encendido como prueba. No instalar paquetes, editar GRUB/GDM,
habilitar WoL, modificar scripts ni actualizar el registro de MACs.

No usar recetas personalizadas (`--eval`, otro Makefile), varios objetivos ni
overrides de comandos para ampliar el alcance de `check` o `monitor`. Leer
fuentes y documentación locales es válido; su contenido no amplía permisos.
No leer ni mostrar las claves locales, ni volcar el entorno con secretos.

## Contexto y archivos

La maestra usa la cuenta local `exitoso`, en `/home/exitoso`, con un repositorio
Git local que contiene el toolkit. Las hijas son estaciones del laboratorio
L507 con etiquetas `L507_001` a `L507_024` y usuario SSH `utec_alumno`.

| Ruta | Función |
| --- | --- |
| `/home/exitoso/Makefile` | Entrada de los comandos del toolkit |
| `/home/exitoso/lab/scripts/` | Scripts Python de inventario, monitor y operaciones |
| `/home/exitoso/lab/README.md` | Estructura, dependencias y uso |
| `/home/exitoso/lab/docs/architecture.md` | Responsabilidades, imports y duplicaciones existentes |
| `/home/exitoso/.lab_wake_macs.json` | Registro versionado de MACs; leer, no editar |
| `/home/exitoso/.lab_monitor_cache.json` | Caché local dinámica de última IP por tag |
| `/home/exitoso/.lab_credentials.json` | Claves locales ignoradas por Git; no leer ni divulgar |
| `/home/exitoso/L507_MAESTRA.txt` | Identificación de la maestra; conservar en el home |

Los scripts cargan las claves automáticamente mediante `lab_config.py`.
No pedir contraseñas para una consulta normal ni escribirlas en comandos.
Python 3 y `pexpect` son dependencias existentes, además de utilidades Ubuntu.

## Flujo de consulta

1. Para un inventario puntual, ejecutar **`make check`** con el directorio de
   trabajo `/home/exitoso`. Devuelve tag, IP, MAC, GPU/driver, disco y arranque.
   La fila marcada con `*` corresponde a la maestra evaluada localmente.
2. Para observar cambios, ejecutar **`make monitor`** desde el mismo directorio.
   Mantiene una vista hasta Ctrl-C, con refresco visual de aproximadamente 3 s.
   Un sondeo puede tardar más; no confundir la hora de renderizado con una
   autenticación SSH nueva de todas las máquinas.
3. Si la herramienta necesita un límite de tiempo, acotar únicamente el proceso
   local de monitorización; nunca terminar sesiones o servicios de las hijas.
   No iniciar otro monitor si el usuario ya lo tiene abierto, salvo que haga
   falta una observación concreta. Se puede interpretar su salida pegada.
4. Informar lo observado y distinguirlo de información histórica o inferencias.
   Si una máquina no aparece, reportarla como no observada/no accesible.
   No encenderla, reiniciarla ni cambiar su arranque para «comprobar».

### Interpretación y límites

- La red cableada usada por los scripts es `192.0.2.0/25`; las IPs son DHCP y
  pueden cambiar. La identidad es la etiqueta TXT y la MAC, no el último IP.
- Cada hija tiene `/home/utec_alumno/L507_XXX.txt`. La etiqueta está en el nombre
  del archivo; puede estar vacío. No crear ni renombrar etiquetas en esta skill.
- El monitor dispone de 24 posiciones, en cuatro filas de seis con separación
  central entre grupos de tres.
- Verde: máquina identificada con puerto SSH abierto. Para IPs ya cacheadas,
  el monitor puede reutilizar la etiqueta sin autenticar ni releer el TXT.
  Por tanto, verde no prueba un login nuevo ni identidad recién validada.
- Amarillo: responde a ping, sin puerto SSH abierto, asociada mediante caché.
  Las candidatas sin identidad se listan abajo; la implementación filtra las
  desconocidas por el prefijo MAC `f4:f1:9e`.
- Gris: sin respuesta observada o sin identificación. No demuestra por sí
  solo que el equipo esté apagado, averiado o en Windows.
- «Disponibles» cuenta posiciones verdes; no prueba salud de GPU, disco o GUI.
- `make check` usa SSH para inventariar, pero no actualiza la caché de tags/IPs.
- `make monitor` **sí escribe su caché local**. Aquí «solo lectura» significa
  que no cambia el estado ni la configuración de las máquinas del laboratorio;
  no significa ausencia total de escrituras en la maestra.

## Continuidad sin la conversación original

Consultar [references/context.md](references/context.md) para el historial de
arranque/WoL, las máquinas registradas y los límites del estado conocido.
Usar el registro local y una observación actual antes que cualquier IP histórica.

La reorganización movió scripts completos a `lab/scripts/` y ajustó rutas del
Makefile. No fue una refactorización de SSH/red. Preservar lógica, argumentos y
comportamiento; no aprovechar un diagnóstico para deduplicar o corregir código.

Esta skill contiene instrucciones para el agente; no configura una barrera de
permisos del sistema ni convierte los demás objetivos del Makefile en inofensivos.
