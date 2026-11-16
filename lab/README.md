# Administración del laboratorio L507

Repositorio Git local en `/home/exitoso`. El Makefile sigue siendo la entrada
desde la carpeta principal; los scripts están agrupados en `lab/scripts/`.

## Estructura

```text
/home/exitoso/
├── Makefile
├── L507_MAESTRA.txt
├── .lab_wake_macs.json          # Registro de MACs, versionado
├── .lab_monitor_cache.json      # Estado dinámico local, ignorado
├── .lab_credentials.json        # Claves locales, ignoradas (permisos 600)
└── lab/
    ├── README.md
    ├── requirements.txt
    ├── config/credentials.example.json
    ├── docs/architecture.md
    └── scripts/
        ├── lab_config.py
        ├── lab_inventory.py
        ├── lab_monitor.py
        ├── lab_restart_all.py
        ├── lab_lock_all.py
        ├── lab_unlock.py
        ├── lab_logout.py
        ├── lab_wake.py
        └── lab_turnoff.py
```

## Comandos existentes

Ejecutar desde `/home/exitoso`:

| Comando | Función |
| --- | --- |
| `make` | Ayuda |
| `make check` | Inventario de red, etiquetas, GPU y discos |
| `make monitor` | Monitor de 24 posiciones; salir con Ctrl-C |
| `make restart-all` | Reiniciar hijas accesibles |
| `make lock-all` | Bloquear sesiones gráficas |
| `make unlock-all` / `make unlock IP=192.0.2.63` | Desbloquear sesiones |
| `make logout-all` / `make logout IP=192.0.2.63` | Cerrar sesiones gráficas |
| `make wake NUM=019` / `make wake-all` | Encender por Wake-on-LAN |
| `make turn-off NUM=019` / `make turn-off-all` | Apagar por SSH |

La sintaxis existente para seleccionar número es `NUM=019`.
Los IDs sin MAC registrada producen un aviso y no reciben paquetes WoL.

## Dependencias y credenciales

Se utiliza Python 3 con `pexpect`, además de los comandos del sistema ya usados
por los scripts: `ssh`, `ip`, `ping`, `base64` y utilidades de Ubuntu.
La dependencia Python se enumera en `lab/requirements.txt`.

Las claves están en `~/.lab_credentials.json`, fuera de Git. Para restaurar el
toolkit en otra cuenta, crear ese archivo con la estructura de
`lab/config/credentials.example.json`, completar las claves y asignarle permisos
`600`. `LAB_SSH_PASSWORD` y `LAB_SUDO_PASSWORD` conservan prioridad sobre el
archivo local, incluso cuando se pasan como variables de Make.

El registro de MACs sí se guarda en Git. La caché de IPs permanece en
`~/.lab_monitor_cache.json` y se puede reconstruir mediante `make monitor` cuando
las hijas sean accesibles. `make check` muestra el inventario, pero actualmente
no escribe esa caché.

## Historial local

```bash
git log --oneline
git status
git diff
```

El primer commit conserva los scripts antes de moverlos, con la única excepción
autorizada de separar las claves. La reorganización posterior mantiene esos
scripts byte por byte y cambia únicamente sus rutas en el Makefile.

El repositorio usa una lista de inclusión en `.gitignore` para que los archivos
personales del directorio principal no entren por accidente al respaldo.
El archivo de claves debe respaldarse por separado si se migra la máquina.

## Contexto para OpenCode

La skill de proyecto `l507-readonly` está en
`.opencode/skills/l507-readonly/SKILL.md`. Incluye contexto histórico en
`references/context.md` e instrucciones de consulta con `make check` y
`make monitor`. Prohíbe cambiar el estado de las máquinas durante el diagnóstico;
cualquier operación de energía o sesión exige consentimiento explícito y una
tarea separada. Es una instrucción del agente, no una regla de permisos del SO.

Tras añadir o actualizar la skill, cerrar y reiniciar OpenCode para que vuelva
a descubrirla.
