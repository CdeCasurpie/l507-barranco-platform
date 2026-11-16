# Tiempos auditados de Barranco full-v1

Retrospectiva generada el 9 de noviembre de 2026. Evidencia detallada y CSV:
`/data/barranco/reports/baseline-v1/REPORTE.md`.

Regeneración local desde `/home/exitoso/lab-deploy`:

```bash
python3 -B tools/report_campaign_timings.py
```

El comando consume resultados/evidencia existentes; `--refresh` vuelve a
consultar metadatos de las hijas por SSH. El reporte es específico de esta
campaña y requiere sus directorios locales, inventario y journal archivado.

## Duraciones y alcance

| Medida | Valor | Interpretación |
|---|---:|---|
| Campaña creada → exportación final | 14,743 h | Tiempo calendario, incluye preparación y entrega |
| Primera reconstrucción → última validada | 9,097 h | Ventana calendario con esperas/recuperaciones |
| Descarga/configuración de cola | 23,69 min | Envolvente de estado, no tiempo puro de red |
| Descargas terminadas → inicio de reconstrucción | 99,69 min | Preparación, pruebas y piloto |
| Última reconstrucción → exportación final | 3,589 h | Cola de recolección/alineación/exportación |
| Segmentación combinada | 4,340 h-nodo | Temporizador masks; SegFormer/SAM3 separados N/D |
| SfM | 5,888 h-nodo | Incluye sus subetapas; no volver a sumarlas |
| OpenMVS cómputo/fusión internos | 9,582 h-nodo | Primer timer exitoso por lote; coste frío incompleto |
| Carga principal conocida | 20,508 h-nodo | Suma parcial, no ejecución secuencial medida |
| Transferencia/verificación | 6,193 h acumuladas | Envolventes por directorio; solapan cómputo |
| Alineación incremental | 25,14 min acumulados | Scopes durante recolección |
| Alineación final | 124,161 s | Scope con cachés; no alineación desde cero |
| Exportación densa / sparse | 477,540 / 4,273 s | Scopes systemd |
| Malla / textura | N/D | Etapas aún no ejecutadas |

Se recopilaron 208,79 GiB de productos finales, con enlace de maestra de
100 Mbps (~9,6 MiB/s observados). La suma de ventanas de transferencia incluye
verificación, pausas y reintentos; no debe añadirse a la ventana de reconstrucción
como una fase enteramente serial.

15 tareas, pico observado de 12 workers; 147 lotes densos únicos y 148 llamadas
exitosas (191,937 s internos adicionales por repetición). Las 9.436 instancias
de cámara incluyen halos para 5.691 vistas fuente. Los 5.675.791.302 puntos de
la entrega conservan redundancia: no representan muestras independientes.

## Interpretación para la tesis

La simulación LPT, usando únicamente los costes parciales conservados, da:

| Nodos | Duración modelada (h) |
|---:|---:|
| 1 | 20,508 |
| 2 | 10,379 |
| 4 | 5,303 |
| 8 | 2,832 |
| 15 | 2,832 |
| 19 | 2,832 |

Estos son escenarios modelados, sin preparación/red y con tareas indivisibles;
no mediciones de T(1) o T(p). El máximo parcial por tarea es 2,832 h. No permite
afirmar un speedup experimental. No se ejecutó una campaña uniforme de 19 nodos
simultáneos ni una corrida secuencial equivalente.

Las recuperaciones de 007, los intentos térmicos y cachés de 023, algunos status
sobrescritos y la ausencia de offsets históricos de reloj limitan la auditoría.
Las fechas de logs OpenMVS inferidas mediante HH:MM:SS y mtime son aproximadas;
los timers internos de duración tienen evidencia independiente de esa fecha.

El [plan de malla y benchmark](MESH-AND-BENCHMARK-PLAN.md) define medición
instrumentada por etapa, réplicas y comparación hasta el mismo producto final.
