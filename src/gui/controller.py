# -*- coding: utf-8 -*-
"""
controller.py - Puente MVC entre la GUI y los modulos de calculo.

Unica responsabilidad: traducir el diccionario plano del formulario a los
dataclasses de `src.thermo` / `src.mechanical`, invocar sus funciones y
devolver los objetos resultado tal cual. Aqui NO se calcula fisica: solo
conversion de unidades de entrada (mm->m, bar->Pa) y despacho.

Si alguno de los modulos de calculo falta o falla al importarse, se activa un
modo *dummy* que levanta un ValueError educativo, de modo que la GUI siga
siendo ejecutable y muestre el mensaje en un pop-up.
"""
from __future__ import annotations

import os
import sys
from typing import Any, Dict, List, Optional, Tuple

try:
    from src.core.thermo_data import ThermoDatabase
except ImportError:  # ejecucion directa: `python src/gui/app.py`
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.core.thermo_data import ThermoDatabase

db = ThermoDatabase()

# --- Modulos de calculo (reales si existen; dummy educativo si no) -----------
MODULOS_OK = True
ERROR_IMPORT = ""
try:
    from src.thermo.sizing import (F_MIN_ACEPTABLE, V_CORAZA_MAX, V_CORAZA_MIN,
                                   V_TUBO_MAX, V_TUBO_MIN, ShellGeometry,
                                   SizingResult, Stream, TubeGeometry,
                                   dimensionar)
    from src.thermo.rating import ExchangerGeometry, RatingResult, evaluar
    from src.mechanical.design import (S_ADMISIBLE, MechanicalInput,
                                       MechanicalResult, disenar_mecanico)
except Exception as exc:  # pragma: no cover - red de seguridad para la GUI
    MODULOS_OK = False
    ERROR_IMPORT = str(exc)
    S_ADMISIBLE = {"Acero al carbono": 0.0}
    V_TUBO_MIN = V_TUBO_MAX = V_CORAZA_MIN = V_CORAZA_MAX = 0.0
    F_MIN_ACEPTABLE = 0.0

# Las ventanas de buena practica (velocidades, factor F) se reexportan desde
# `src.thermo.sizing`: la GUI las PINTA pero no las define. Una sola fuente de
# verdad evita que el resaltado ambar contradiga al motor de calculo.


# =============================================================================
# 1. CATALOGOS PARA LOS MENUS DESPLEGABLES
# =============================================================================
LAYOUTS = {"Triangular 30°": 30, "Triangular 60°": 60,
           "Cuadrado 45° (rotado)": 45, "Cuadrado 90°": 90}
PASOS = ["1", "2", "4", "6", "8"]
TIPOS_CARCASA = ["E", "F", "G", "H", "J", "K", "X"]
CABEZAL_FRONTAL = ["A", "B", "C", "D", "N"]
CABEZAL_TRASERO = ["L", "M", "N", "P", "S", "T", "U", "W"]
LADOS = ["frio", "caliente"]


def fluidos() -> List[str]:
    return db.list_fluids()


def materiales_tubo() -> List[str]:
    return db.list_materials()


def materiales_carcasa() -> List[str]:
    return list(S_ADMISIBLE)


def limites_fluido(nombre: str) -> Tuple[float, float]:
    """Ventana de validez (T_min, T_max) en grados Celsius."""
    return db.get_limits(nombre, unit="C")


def densidad(fluido: str, T_celsius: float) -> float:
    """rho [kg/m3] a la temperatura media; usado por el diseno mecanico."""
    return db.get_fluid_state(fluido, T_celsius, unit="C").rho


# =============================================================================
# 2. CONSTRUCCION DE LAS ENTRADAS DE CALCULO
# =============================================================================
def _exigir_modulos() -> None:
    if not MODULOS_OK:
        raise ValueError(
            "Los módulos de cálculo no pudieron importarse.\n\n"
            f"Detalle técnico: {ERROR_IMPORT}\n\n"
            "Verifique que existan src/thermo/sizing.py, src/thermo/rating.py "
            "y src/mechanical/design.py, y ejecute la aplicación desde la "
            "carpeta raíz del proyecto.")


def _corrientes(d: Dict[str, Any]) -> Tuple[Any, Any]:
    """Arma las dos corrientes. T en °C, caudal en kg/s."""
    caliente = Stream(fluido=d["fluido_cal"], m_dot=d["m_cal"],
                      T_in=d["tin_cal"], T_out=d.get("tout_cal"))
    fria = Stream(fluido=d["fluido_fri"], m_dot=d["m_fri"],
                  T_in=d["tin_fri"], T_out=d.get("tout_fri"))
    # La regla "exactamente una T_out incognita" la impone y explica
    # balance_energia() en src/thermo/sizing.py: no se duplica aqui.
    return caliente, fria


def _geometria(d: Dict[str, Any]) -> Tuple[Any, Any]:
    tubos = TubeGeometry(
        D_o=d["d_o_mm"] / 1000.0,
        espesor=d["esp_mm"] / 1000.0,
        P_T=d["pitch_mm"] / 1000.0,
        L=d["long_m"],
        layout=LAYOUTS[d["layout"]],
        n_pasos=int(d["n_pasos"]),
        material=d["mat_tubo"])
    coraza = ShellGeometry(
        B=d["baffle_mm"] / 1000.0,
        tipo=d["tipo_carcasa"],
        corte_baffle=d["corte_pct"] / 100.0)
    return tubos, coraza


# =============================================================================
# 3. DESPACHO DE CALCULOS
# =============================================================================
def correr_sizing(d: Dict[str, Any]):
    """Metodo de Kern: itera sobre U hasta converger el area requerida."""
    _exigir_modulos()
    caliente, fria = _corrientes(d)
    tubos, coraza = _geometria(d)
    return dimensionar(caliente, fria, tubos, coraza,
                       lado_tubos=d["lado_tubos"],
                       U_inicial=d["u_inicial"])


def correr_rating(d: Dict[str, Any]):
    """Evalua un equipo ya construido: itera sobre las T de salida."""
    _exigir_modulos()
    caliente, fria = _corrientes_rating(d)
    tubos, coraza = _geometria(d)
    geom = ExchangerGeometry(tubos=tubos, coraza=coraza,
                             N_tt=int(d["n_tt"]), D_s=d["d_s_mm"] / 1000.0)
    return evaluar(caliente, fria, geom, lado_tubos=d["lado_tubos"])


def _corrientes_rating(d: Dict[str, Any]) -> Tuple[Any, Any]:
    """En rating las T de salida son la incognita: se ignoran si vienen."""
    caliente = Stream(fluido=d["fluido_cal"], m_dot=d["m_cal"],
                      T_in=d["tin_cal"], T_out=None)
    fria = Stream(fluido=d["fluido_fri"], m_dot=d["m_fri"],
                  T_in=d["tin_fri"], T_out=None)
    return caliente, fria


def correr_mecanico(d: Dict[str, Any], D_s: float, N_tt: int,
                    T_med_cal: float, T_med_fri: float):
    """Dimensiones de fabricacion TEMA Clase C a partir del resultado termico."""
    _exigir_modulos()
    lado_tubos = d["lado_tubos"]
    # Que fluido va por cada lado lo decide el usuario en el formulario.
    if lado_tubos == "frio":
        f_t, m_t, T_t = d["fluido_fri"], d["m_fri"], T_med_fri
        f_s, m_s, T_s = d["fluido_cal"], d["m_cal"], T_med_cal
    else:
        f_t, m_t, T_t = d["fluido_cal"], d["m_cal"], T_med_cal
        f_s, m_s, T_s = d["fluido_fri"], d["m_fri"], T_med_fri

    inp = MechanicalInput(
        D_s=D_s,
        N_tt=int(N_tt),
        L=d["long_m"],
        d_o=d["d_o_mm"] / 1000.0,
        P_T=d["pitch_mm"] / 1000.0,
        L_bc=d["baffle_mm"] / 1000.0,
        corte_baffle=d["corte_pct"] / 100.0,
        rho_s=densidad(f_s, T_s),
        rho_t=densidad(f_t, T_t),
        m_dot_s=m_s,
        m_dot_t=m_t,
        P_diseno_s=d["p_coraza_bar"] * 1.0e5,
        P_diseno_t=d["p_tubos_bar"] * 1.0e5,
        material=d["mat_carcasa"],
        corrosion=d["corrosion_mm"] / 1000.0,
        tipo_carcasa=d["tipo_carcasa"],
        cabezal_frontal=d["cab_frontal"],
        cabezal_trasero=d["cab_trasero"],
        d_perno=d["d_perno_mm"] / 1000.0)
    return disenar_mecanico(inp)
