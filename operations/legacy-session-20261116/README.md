# Helpers operativos históricos

Fuentes rescatadas de `/tmp/opencode/` durante la consolidación. Se conservan
para no perder transporte, preparación, colección y recuperación de campañas.

**No ejecutarlos como una secuencia ni importarlos indiscriminadamente.**
Varios ejecutan operaciones en el nivel superior, esperan `BINDINGS` o
`NODE_TAG` inyectados y usan rutas/recibos locales no incluidos.

La copia pública está sanitizada: IPs/MACs/Drive de ejemplo no son destinos
reales. Algunas referencias a otros helpers mantienen paths históricos.
Para reutilizar un procedimiento, revisar fuente, reconstruir configuración
explícita, validar identidad/host keys/montajes/locks/espacio y generar un bundle
nuevo. No copiar un estado antiguo para simular una ejecución nueva.

Los helpers de limpieza/potencia/energía se conservan como historial de código,
no como permiso para repetir acciones. Originales y recibos privados permanecen
en su instalación de origen.
