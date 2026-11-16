"""Credenciales locales; las variables de entorno conservan prioridad."""
import json
from pathlib import Path

_path = Path.home() / ".lab_credentials.json"
try:
    with _path.open() as _file:
        _credentials = json.load(_file)
except FileNotFoundError:
    _credentials = {}

DEFAULT_SSH_PASSWORD = _credentials.get("LAB_SSH_PASSWORD", "")
DEFAULT_SUDO_PASSWORD = _credentials.get("LAB_SUDO_PASSWORD", "")
