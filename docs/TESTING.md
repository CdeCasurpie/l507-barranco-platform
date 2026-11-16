# Pruebas sin campañas reales

No usar scripts `start`, `resume`, `recover`, administración de energía o
recolección como smoke tests. No importar todos los archivos de `tools/`:
algunos helpers históricos ejecutan su operación al importarse.

## Comprobaciones básicas

Desde `lab-deploy/`, con Python y pexpect:

```bash
python3 -B -m unittest discover -s tests -p 'test_controller.py' -v
python3 -B -m unittest discover -s tests -p 'test_manager.py' -v
python3 -B -m unittest discover -s tests -p 'test_barranco_status.py' -v
python3 -B -m unittest discover -s tests -p 'test_glomap_review_worker.py' -v
python3 -B -m unittest discover -s tests -p 'test_loop_vocab_worker.py' -v
```

En `home/sparse-review/`:

```bash
python3 -B -m unittest -v test_app
```

`test_catalog.py` depende actualmente de sparse/manifest externos. No presentarlo
como un test autónomo de un clon vacío.

## Pruebas con dependencias numéricas

Los tests PnP/Sim3 requieren NumPy, SciPy y PyCOLMAP 3.11.1 en un runtime
aislado. Son sintéticos y no escriben modelos de producción.

Los tests de ROI/alineación requieren el backend externo y fixtures de ese
repositorio. Véase el README de la app; no copiar el backend aquí para ocultar
esa dependencia. Las pruebas de navegador requieren Chrome y perfiles aislados.

Un test aprobado no certifica una reconstrucción real.
