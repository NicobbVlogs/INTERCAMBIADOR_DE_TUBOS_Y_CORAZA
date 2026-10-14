# -*- coding: utf-8 -*-
"""
Pruebas de la base de datos termofisica (intercambiador/core/thermo_data.py).

Propiedades en puntos de referencia conocidos y rechazo de entradas
fuera de la ventana de validez de cada correlacion.
"""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def db():
    from intercambiador.core.thermo_data import ThermoDatabase

    return ThermoDatabase()


def test_catalogo_de_10_fluidos(db):
    fluidos = db.list_fluids()
    assert len(fluidos) == 10, f"catalogo de 10 fluidos: {len(fluidos)}"


def test_catalogo_de_5_materiales(db):
    materiales = db.list_materials()
    assert len(materiales) == 5, f"catalogo de 5 materiales: {len(materiales)}"


def test_agua_20_c_densidad(db):
    agua = db.get_fluid_state("Agua", 20.0, "C")
    assert 960 < agua.rho < 1005, f"densidad del agua a 20 C = {agua.rho:.1f} kg/m3"


def test_agua_20_c_calor_especifico(db):
    agua = db.get_fluid_state("Agua", 20.0, "C")
    assert 4150 < agua.cp < 4220, f"cp del agua a 20 C = {agua.cp:.0f} J/kg.K"


def test_agua_20_c_conductividad(db):
    agua = db.get_fluid_state("Agua", 20.0, "C")
    assert 0.55 < agua.k < 0.65, f"k del agua a 20 C = {agua.k:.3f} W/m.K"


def test_agua_20_c_viscosidad(db):
    agua = db.get_fluid_state("Agua", 20.0, "C")
    assert 0.9e-3 < agua.mu < 1.1e-3, (
        f"viscosidad del agua a 20 C = {agua.mu * 1000:.3f} mPa.s"
    )


def test_viscosidad_del_agua_disminuye_con_la_temperatura(db):
    agua = db.get_fluid_state("Agua", 20.0, "C")
    mu80 = db.get_fluid_state("Agua", 80.0, "C").mu
    assert mu80 < agua.mu, "la viscosidad del agua disminuye con la temperatura"


def test_rechaza_un_fluido_inexistente(db):
    with pytest.raises(ValueError):
        db.get_fluid_state("Mercurio", 20.0, "C")
