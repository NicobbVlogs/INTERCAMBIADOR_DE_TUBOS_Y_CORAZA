# -*- coding: utf-8 -*-
"""
Pruebas de los proyectos .he distribuidos en ejemplos/: deben calcular sin
error, sin advertencias y usando las etiquetas canonicas de fluido exactas
(la GUI las descartaria al cargarlas en los menus desplegables).
"""
from __future__ import annotations

import os
from importlib.resources import files

import pytest

# Proyectos .he empaquetados con el codigo (intercambiador/ejemplos).
DIR_EJEMPLOS = str(files("intercambiador") / "ejemplos")


def _archivos_ejemplo():
    if not os.path.isdir(DIR_EJEMPLOS):
        return []
    from intercambiador.gui import io_state

    return sorted(
        a for a in os.listdir(DIR_EJEMPLOS) if a.endswith(io_state.EXTENSION)
    )


EJEMPLOS = _archivos_ejemplo()


def test_existe_la_carpeta_ejemplos():
    assert os.path.isdir(DIR_EJEMPLOS), "existe la carpeta ejemplos/"


def test_hay_al_menos_4_proyectos_de_ejemplo():
    assert len(EJEMPLOS) >= 4, f"hay {len(EJEMPLOS)} proyectos de ejemplo"


def test_los_ejemplos_usan_las_etiquetas_de_fluido_canonicas():
    from intercambiador.core.thermo_data import ThermoDatabase
    from intercambiador.gui import io_state

    canon = set(ThermoDatabase().list_fluids())
    malos = []
    for archivo in EJEMPLOS:
        datos = io_state.abrir(os.path.join(DIR_EJEMPLOS, archivo))
        for clave in ("fluido_cal", "fluido_fri"):
            if datos.get(clave) not in canon:
                malos.append(f"{archivo}:{clave}={datos.get(clave)!r}")
    assert not malos, "los ejemplos usan las etiquetas de fluido canónicas: " + "; ".join(malos)


@pytest.mark.parametrize("archivo", EJEMPLOS or ["(sin ejemplos)"])
def test_cada_ejemplo_calcula_sin_advertencias(archivo, caso_base):
    if not EJEMPLOS:
        pytest.skip("no hay proyectos de ejemplo distribuidos")

    from intercambiador.gui import controller as ctrl
    from intercambiador.gui import io_state
    from intercambiador.gui.app import VALORES_DEFECTO

    ruta = os.path.join(DIR_EJEMPLOS, archivo)
    crudo = io_state.abrir(ruta)
    datos = {}
    for clave, valor in crudo.items():
        if clave in ("fluido_cal", "fluido_fri", "lado_tubos", "layout",
                     "n_pasos", "mat_tubo", "tipo_carcasa",
                     "cab_frontal", "cab_trasero", "mat_carcasa"):
            datos[clave] = valor
        else:
            datos[clave] = float(valor) if str(valor).strip() else None

    faltan = set(VALORES_DEFECTO) - set(datos)
    assert not faltan, f"{archivo}: completo, faltan {faltan}"

    r = ctrl.correr_sizing(datos)
    m = ctrl.correr_mecanico(datos, r.D_s, r.N_tt, r.T_h_out, r.T_c_out)
    adv = len(r.advertencias) + len(m.advertencias)
    assert adv == 0, (
        f"{archivo}: q={r.q / 1000:.0f} kW, {r.N_tt} tubos, "
        f"D_s={r.D_s * 1000:.0f} mm, sin advertencias ({adv} advertencias)"
    )
