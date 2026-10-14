# -*- coding: utf-8 -*-
"""
verificar.py - Puente de compatibilidad (DEPRECADO).

La suite de verificacion vive ahora en `tests/` y se ejecuta con pytest,
el runner oficial del proyecto:

    uv run pytest

Este archivo se conserva para no romper costumbres antiguas (`py verificar.py`)
y simplemente delega en pytest. Quitelo cuando ya no lo necesite.
"""
from __future__ import annotations

import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RAIZ)


def main() -> int:
    print("AVISO: verificar.py esta deprecado. Use  uv run pytest  en su lugar.\n")
    try:
        import pytest  # noqa: F401
    except ImportError:
        print("pytest no esta instalado en este interprete.\n"
              "Ejecute:  uv sync   (o:  uv run pytest)")
        return 1
    return subprocess.call([sys.executable, "-m", "pytest", *sys.argv[1:]],
                           cwd=RAIZ)


if __name__ == "__main__":
    sys.exit(main())
