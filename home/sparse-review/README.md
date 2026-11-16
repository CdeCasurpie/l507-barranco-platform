# Revisión sparse local

## Catálogo de todas las sparse (16-nov-2026)

**http://127.0.0.1:8790/** — `barranco-sparse-catalog.service`.
Selector de manzana/variante y visor con selector de componente, en un solo
puerto. Incluye las 14 anclas preservadas en su marco local, las variantes
históricas locales y las colecciones verificadas bajo
`/data/barranco/review/catalog-20261116-134343/`.
No aplica colocaciones ni modifica anclas, sparse, máscaras o revisiones.
Cada nube sigue en su marco independiente: no comparar escalas de pantalla.

La galería solo publica nuevas colecciones después de verificar SHA256 y
escribir su recibo. Recargar la galería actualiza la lista; no realiza descargas.
011 y 006 multivídeo seguían en SfM durante la consulta de esta colección:
no se copian sus modelos en escritura. El intento horizontal con máscaras
falló antes de SfM y no ofrece una sparse de esa corrida.
Las selecciones A/B quedan separadas por ruta del dataset y componente.

Código: `catalog_app.py`; pruebas: `python3 -B -m unittest -v test_catalog test_app`.
Los visores anteriores no se detuvieron ni sustituyeron.

Abrir **http://127.0.0.1:8780** en la maestra. Servidor de solo lectura, ligado
a loopback, sin CDN ni dependencias Python adicionales. Servicio:
`barranco-sparse-review.service` del usuario.

Cada componente se muestra por separado en su marco SfM original. La cámara de
visualización centra y escala únicamente el buffer de pantalla, sin cambiar
puntos, cámaras ni transformaciones fuente. La escala aparente de dos
componentes no debe compararse como si ya compartieran unidades.

Arrastrar gira; Mayús+arrastrar o botón derecho desplaza; rueda acerca.
Naranja indica centros de cámaras, no una trayectoria ordenada ni frustums.
Error máximo y track mínimo filtran solo la visualización. Hasta 250.000 puntos
muestreados uniformemente por componente; el número mostrado y original se
indican por separado.

Los binarios COLMAP y la nube completa no se modifican. La web no fusiona,
optimiza, elimina puntos ni guarda colocaciones manuales. Para reparar una
separación hay que validar solape visual y calcular conexiones o una colocación
Sim(3); una unión visual sola no actualiza el modelo fotogramétrico.

Ejecutar pruebas: `python3 -B -m unittest -v test_app`.
Ejecutar sin systemd: `python3 -B app.py`.
Otro dataset: `python3 -B app.py --dataset /ruta/revision --port 8781`.

## Señalar un corte mediante cámaras A/B

Disponible también en el visor actual 019 (`http://127.0.0.1:8783/`) y
021 (`http://127.0.0.1:8784/`). Recargar con Ctrl+F5 para la interfaz nueva.

1. Acercar la zona del corte; opcionalmente activar **Solo cámaras**.
2. Elegir **Lado A** y hacer clic corto en varias cámaras de ese lado.
3. Elegir **Lado B** y marcar las del lado que debería continuar.
4. **Copiar cámaras A/B** genera un informe con IDs de imagen y nombres exactos
   de frames, listo para pegar en el chat. **Descargar selección JSON** incluye
   además dataset, componente y centros en las coordenadas SfM originales.

Pasar el cursor muestra ID y nombre. Arrastrar continúa girando; Mayús+arrastrar
desplaza y la rueda acerca. Para cámaras superpuestas, buscar por ID numérico
exacto o por parte del nombre y usar **Añadir vista de la lista**.
Cada vista pertenece como máximo a un lado. ID de imagen/vista no es ID de
intrínsecos. Las marcas son anotaciones; no indican correspondencias verificadas.

La selección se conserva en localStorage del navegador por dataset/componente.
No se escribe en el servidor ni se cambian puntos, poses, matrices o aprobaciones.
La selección es por proximidad al centro proyectado en pantalla; las marcas
seleccionadas se dibujan encima de la nube. No es una comprobación de visibilidad.
Los visores no tienen las fotografías originales descargadas.

El puerto 8783 mostraba antes 020; se cambió a 019 por petición del usuario.
La 020 original y su corrección siguen conservadas. El puerto no identifica
permanentemente una manzana: comprobar el título y dataset del visor.

Prueba específica de 020 con perfil aislado y sin escribir estado servidor:
`python3 -B browser_selection_check.py` (requiere el visor 020 en 8783 y Chrome).
