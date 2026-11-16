# Decisiones del usuario: reparación y texturizado de la malla

## Reparación de huecos: exclusivamente manual

El usuario quiere sentarse a editar la malla y **completar o corregir los huecos
manualmente**, decidiendo qué superficie añadir, modificar o dejar abierta.

- No ejecutar cierre automático de huecos.
- No sustituir esta edición por reconstrucción, interpolación, ajuste de planos,
  RANSAC, Poisson u otro procedimiento automático que complete regiones ausentes.
- Las herramientas de edición deben permitir seleccionar el hueco y construir o
  modificar su geometría bajo control directo del usuario. Una operación explícita
  dentro del editor no autoriza a reparar otros huecos automáticamente.
- Mantener una versión de referencia con la geometría observada y sus huecos, y
  guardar las reparaciones manuales en una versión derivada.
- Distinguir las superficies reconstruidas de las añadidas o corregidas manualmente.

## Texturizado preferido: reproyección de fotografías originales

Después de la edición manual, el usuario prefiere **recalcular la textura mediante
reproyección de las fotografías originales**, utilizando sus cámaras calibradas.
No adoptar el bakeado desde la malla anterior como ruta principal por defecto.

El flujo acordado es:

```text
Malla reconstruida dentro del polígono seleccionado
        ↓
Edición y reparación MANUAL de huecos por el usuario
        ↓
UV y atlas sobre la geometría aprobada
        ↓
Reproyección de fotografías originales con cámaras coherentes
        ↓
Revisión visual y publicación de la versión derivada
```

Conservar fotografías, cámaras, intrínsecos, transformaciones y procedencia para
poder texturizar la geometría editada en el mismo marco. Si se cambia el marco de
la malla, adaptar coherentemente las cámaras o la geometría antes de reproyectar.

Si ninguna fotografía observa una superficie reparada, **no hay textura real que
recuperar mediante reproyección**. Señalar esa zona para que el usuario decida su
tratamiento; no rellenarla sintéticamente, extrapolarla ni inventar detalle de
forma automática.

## Relación con las pruebas existentes

El piloto de la manzana 025 comparó Delaunay, Ball Pivoting y parches RANSAC.
La prueba de planos no implica autorización para completar huecos automáticamente.
Esta decisión se aplica al flujo posterior de reparación y acabado.

Proyecto: `/home/exitoso/home/barranco-roi/`.
Piloto: `/data/barranco/roi/025/s-1794364122096131540/pilot-v1/`.
