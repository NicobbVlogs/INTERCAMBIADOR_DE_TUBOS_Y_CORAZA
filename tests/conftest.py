# -*- coding: utf-8 -*-
"""
conftest.py - Fixtures compartidas de la suite de pruebas.

La suite sustituye a verificar.py: cubre las cuatro fases del programa
(core, termico, mecanico, GUI), los ejemplos distribuidos y la robustez.

El paquete `intercambiador` se importa desde el entorno del proyecto
(`uv sync` lo instala en .venv); no se manipula sys.path aqui.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def caso_base():
    """Caso base de arranque (agua-agua) con la T_out fria como incognita."""
    pytest.importorskip("tkinter")
    from intercambiador.gui.app import VALORES_DEFECTO

    datos = dict(VALORES_DEFECTO)
    datos["tout_fri"] = None
    return datos


@pytest.fixture(scope="session")
def resultado_sizing(caso_base):
    """Dimensionamiento del caso base (Metodo de Kern)."""
    from intercambiador.gui import controller as ctrl

    return ctrl.correr_sizing(caso_base)


@pytest.fixture(scope="session")
def resultado_rating(caso_base, resultado_sizing):
    """Rating del mismo equipo que devuelve el sizing del caso base."""
    from intercambiador.gui import controller as ctrl

    datos = dict(
        caso_base,
        n_tt=resultado_sizing.N_tt,
        d_s_mm=resultado_sizing.D_s * 1000.0,
    )
    return ctrl.correr_rating(datos)


@pytest.fixture(scope="session")
def resultado_mecanico(caso_base, resultado_sizing):
    """Diseno mecanico TEMA Clase C a partir del resultado termico."""
    from intercambiador.gui import controller as ctrl

    return ctrl.correr_mecanico(
        caso_base,
        resultado_sizing.D_s,
        resultado_sizing.N_tt,
        resultado_sizing.T_h_out,
        resultado_sizing.T_c_out,
    )
