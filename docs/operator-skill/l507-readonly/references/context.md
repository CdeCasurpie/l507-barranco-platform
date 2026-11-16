# Contexto persistente del laboratorio

## Objetivo del toolkit

Administrar desde una maestra las estaciones clonadas del laboratorio UTEC L507.
Se construyó un Makefile para inventario, monitorización, reinicio, control de
sesiones gráficas, Wake-on-LAN y apagado remoto. **La skill l507-readonly solo
autoriza la consulta: no hereda permisos para las otras operaciones.**

El trabajo actual consiste en conservar y observar el toolkit ya funcional.
El usuario pidió ordenar los scripts sin cambiar su lógica y mantener respaldo
Git local. No hay publicación en GitHub como parte de ese trabajo.

## Infraestructura conocida

- Maestra: cuenta `exitoso`, home `/home/exitoso`, interfaz cableada observada
  `enp128s31f6`, IP histórica `192.0.2.76`, MAC `02:00:00:00:00:02`.
  La IP es un dato histórico, no una constante de identidad.
- Hijas: usuario SSH `utec_alumno`, etiquetas en archivos `L507_XXX.txt` del home.
- Subred cableada `192.0.2.0/25`, broadcast `192.0.2.127`.
  Wi-Fi y ZeroTier no forman parte del alcance normal del monitor.
- Las credenciales no están en el repositorio. Los scripts las cargan desde un
  archivo privado local; no hace falta que el agente lea ese archivo.
- El registro `.lab_wake_macs.json` contiene 19 etiquetas: 001–012, 014, 015,
  019 y 021–024. Ese conteo indica MACs registradas, no equipos encendidos.
- El usuario informó que 013, 016, 017, 018 y 020 estaban malogradas. No tratarlas
  como reparables mediante encendido, ni inferir su estado actual solo de eso.

## Últimas IPs conocidas: referencia histórica

No usar esta tabla como autorización para conectar o cambiar estado. Las IPs
pueden reasignarse. Consultar `make check` y la caché local para datos actuales.

| Tag | Última IP observada |
| --- | --- |
| 001 | 192.0.2.56 |
| 002 | 192.0.2.54 |
| 003 | 192.0.2.55 |
| 004 | 192.0.2.44 |
| 005 | 192.0.2.58 |
| 006 | 192.0.2.64 |
| 007 | 192.0.2.71 |
| 008 | 192.0.2.77 |
| 009 | 192.0.2.78 |
| 010 | 192.0.2.66 |
| 011 | 192.0.2.65 |
| 012 | 192.0.2.53 |
| 014 | 192.0.2.59 |
| 015 | 192.0.2.61 |
| 019 | 192.0.2.63 |
| 021 | 192.0.2.80 |
| 022 | 192.0.2.67 |
| 023 | 192.0.2.72 |
| 024 | 192.0.2.68 |

También se observó `192.0.2.49`, MAC `02:00:00:00:00:03`, sin acceso SSH.
**No está identificada**: no asignarla a la 013 ni a otra etiqueta por descarte.
La ausencia de SSH no demuestra que no tenga archivo TXT.

## Cambios históricos ya realizados

- Se corrigieron drivers NVIDIA en varias hijas, especialmente 006 y 008.
  Se observaron versiones diferentes funcionales; no unificarlas por iniciativa
  propia. El inventario actual es la fuente para comprobar GPU/driver.
- Se dejó Ubuntu como entrada por defecto de GRUB en las hijas revisadas.
  La 009 tenía `GRUB_DEFAULT=4`: se cambió a `0`, se generó GRUB y se reinició;
  se comprobó Ubuntu, SSH, autologin y driver NVIDIA `615.71.09`.
- La 010 ya tenía `GRUB_DEFAULT=0`, autologin y driver `595.99.02`.
- Las MACs de 009 y 010 se confirmaron por sus etiquetas y se registraron:
  `02:00:00:00:00:04` y `02:00:00:00:00:05`, respectivamente.
- El autologin GDM de las hijas revisadas quedó habilitado para `utec_alumno`
  por decisión del usuario. No deshabilitarlo como supuesto endurecimiento.
- Se probó un ciclo de apagado y WoL en la 019, MAC `02:00:00:00:00:06`.
  Volvió a SSH en unos 48 s en una prueba. Es un dato histórico: **no repetir
  la prueba ni inferir que todas las NIC/BIOS estén configuradas igual**.
- Las operaciones gráficas usan loginctl/DBus; el desbloqueo puede reiniciar
  GDM como alternativa. No son consultas inocuas y quedan fuera de esta skill.

## Respaldo y organización

- Commit `0bcad8b`: respaldo inicial del toolkit, con claves separadas por
  autorización explícita del usuario.
- Commit `c652208`: traslado a `lab/scripts/`, documentación y nuevas rutas del
  Makefile. Git reconoció los nueve archivos Python como movimientos al 100%.
- Durante la reorganización se verificaron sintaxis, imports, credenciales
  locales, overrides de Make y equivalencia de los 13 objetivos por ejecución
  en seco. Eso no equivale a una prueba nueva de apagado/reinicio de las hijas.
- El marcador de la maestra, registro MAC y caché quedaron en sus rutas
  originales para preservar el comportamiento. `.gitignore` excluye el resto
  de archivos personales del home y los secretos.
- Hay duplicación preexistente de SSH, colores, sondeos y lectura de JSON.
  Se documentó en `lab/docs/architecture.md`; eliminarla exige otra tarea con
  autorización para refactorizar, no solo reorganizar posiciones de archivos.
