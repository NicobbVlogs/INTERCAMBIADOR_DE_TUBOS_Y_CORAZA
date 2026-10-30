# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
# Trazabilidad interna BD-JcJlJbJr-9A17 / KERN-7F4-0x444E4242 (origen: src/core/marca.py; uso pasivo, no bloquea nada).
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
    from src.thermo.sizing import (F_MIN_ACEPTABLE, RE_KERN_MAX, RE_KERN_MIN,
                                   V_CORAZA_MAX, V_CORAZA_MIN,
                                   V_TUBO_MAX, V_TUBO_MIN, ShellGeometry,
                                   SizingResult, Stream, TubeGeometry,
                                   dimensionar)
    from src.thermo.rating import ExchangerGeometry, RatingResult, evaluar
    from src.mechanical.design import (S_ADMISIBLE, HOLGURA_HAZ,
                                       MechanicalInput, MechanicalResult,
                                       disenar_mecanico)
except Exception as exc:  # pragma: no cover - red de seguridad para la GUI
    MODULOS_OK = False
    ERROR_IMPORT = str(exc)
    S_ADMISIBLE = {"Acero al carbono": 0.0}
    HOLGURA_HAZ = {}
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


def desc_carcasa(tipo: str) -> str:
    """Descripcion del tipo de coraza TEMA (Fig. N-1.2)."""
    try:
        from src.mechanical.design import DESCRIPCION_CARCASA
        return DESCRIPCION_CARCASA.get(str(tipo).upper(), "")
    except Exception:
        return ""


def desc_cabezal(posicion: str, tipo: str) -> str:
    """Descripcion del tipo de cabezal TEMA (Fig. N-1.2)."""
    try:
        from src.mechanical.design import DESCRIPCION_CABEZAL
        return DESCRIPCION_CABEZAL.get(str(tipo).upper(), "")
    except Exception:
        return ""


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
def modo_calculo(d: Dict[str, Any]) -> str:
    """«rating» si el proyecto es de evaluacion; «sizing» si tiene T de salida.

    Un proyecto de rating define la geometria de un equipo existente y deja
    las DOS temperaturas de salida vacias: su incognita es el comportamiento
    del equipo, no el area. Sobre esos datos el sizing no tiene balance que
    resolver, asi que el camino natural es el rating (F6).
    """

    def _vacia(v: object) -> bool:
        return v is None or v == ""

    if _vacia(d.get("tout_cal")) and _vacia(d.get("tout_fri")):
        return "rating"
    return "sizing"


# --- Criterios de verificación del diseño (método de Kern / TEMA) -----------
# Guías de diseño para líquidos: tubos 0.9-2.4 m/s (3-8 ft/s), coraza
# 0.3-1.5 m/s; espaciado de baffles 0.2-1.0·D_s (TEMA RCB-4.5.1: mínimo D_s/5
# o 2 in); corte 15-45 % (25 % estándar de Kern); 3 <= L/D_s <= 15;
# F >= 0.75 para operación estable; Re_coraza en 2·10³-10⁶ (validez de Kern).
# Δp admisible típica para líquidos: 35 kPa (µ < 1 mN·s/m²), 50-70 kPa si son
# viscosos. Referencias: Kern (1950), TEMA y guías de diseño de la literatura.
def verificaciones_diseno(modo: str, d: Dict[str, Any], r,
                          m=None) -> List[Tuple[str, str, str]]:
    """Checklist de verificación del diseño, adaptado al modo de cálculo.

    Devuelve filas (verificación, estado, detalle) con estado «OK» o «AVISO».
    El conjunto depende del modo: el SIZING se verifica como PROPUESTA de un
    equipo nuevo (sobre-área, geometría TEMA, ventanas de velocidad) y el
    RATING como EVALUACIÓN de un equipo ya construido (cierre del balance,
    efectividad y proximidad al pinch). Ambos comparten la verificación
    hidráulica: caídas de presión frente a los límites permisibles cargados
    por el usuario.
    """
    filas: List[Tuple[str, str, str]] = []

    def fila(nombre: str, ok: bool, detalle: str, detalle_aviso: str) -> None:
        filas.append((nombre, "OK" if ok else "AVISO",
                      detalle if ok else detalle_aviso))

    def _lim(clave: str) -> Optional[float]:
        return _limite_delta_p(d, clave)

    # ---------------- verificación hidráulica común -----------------------
    lim_t = _lim("dp_t_max")
    lim_t_txt = (f"{lim_t:,.0f} Pa" if lim_t is not None
                 else "sin límite cargado")
    fila("Δp en tubos ≤ límite permisible",
         lim_t is None or r.dp_t <= lim_t,
         f"Δp = {r.dp_t:,.0f} Pa (límite: {lim_t_txt})",
         f"Δp = {r.dp_t:,.0f} Pa supera el límite {lim_t_txt}: "
         f"más pasos, mayor diámetro o menor longitud")
    lim_s = _lim("dp_s_max")
    lim_s_txt = (f"{lim_s:,.0f} Pa" if lim_s is not None
                 else "sin límite cargado")
    fila("Δp en coraza ≤ límite permisible",
         lim_s is None or r.dp_s <= lim_s,
         f"Δp = {r.dp_s:,.0f} Pa (límite: {lim_s_txt})",
         f"Δp = {r.dp_s:,.0f} Pa supera el límite {lim_s_txt}: "
         f"amplíe el espaciado de baffles, el pitch o el corte")
    fila("Velocidad en tubos en la ventana de diseño (0.9–2.4 m/s)",
         V_TUBO_MIN <= r.v_t <= V_TUBO_MAX,
         f"v_t = {r.v_t:.2f} m/s",
         f"v_t = {r.v_t:.2f} m/s fuera de la ventana: riesgo de ensuciamiento "
         f"(baja) o de erosión (alta)")
    fila("Velocidad en coraza en la ventana de diseño (0.3–1.5 m/s)",
         V_CORAZA_MIN <= r.v_s <= V_CORAZA_MAX,
         f"v_s = {r.v_s:.2f} m/s",
         f"v_s = {r.v_s:.2f} m/s fuera de la ventana: zonas muertas (baja) o "
         f"vibración inducida (alta)")
    fila("Factor de corrección F ≥ 0.75",
         r.F >= F_MIN_ACEPTABLE,
         f"F = {r.F:.3f}",
         f"F = {r.F:.3f}: el arreglo es térmicamente sensible; divida el "
         f"servicio en varias corazas en serie")
    fila("Re de coraza en la validez de Kern (2·10³–10⁶)",
         RE_KERN_MIN <= r.Re_s <= RE_KERN_MAX,
         f"Re_s = {r.Re_s:,.0f}",
         f"Re_s = {r.Re_s:,.0f}: h_o es una extrapolación de la correlación")
    fila("Régimen de flujo en tubos turbulento",
         r.regimen_tubo == "turbulento",
         f"régimen {r.regimen_tubo} (Re_t = {r.Re_t:,.0f})",
         f"régimen {r.regimen_tubo} (Re_t = {r.Re_t:,.0f}): la incertidumbre "
         f"de U crece y la transferencia decae")

    # ---------------- verificaciones propias del SIZING -------------------
    if modo == "sizing":
        fila("Sobre-área del haz no negativa",
             r.sobre_area >= 0.0,
             f"sobre-área = {r.sobre_area:+.1f} %",
             f"sobre-área = {r.sobre_area:+.1f} %: el haz instalado no cubre "
             f"el área requerida; aumente L o el número de tubos")
        fila("Sobre-área razonable (≤ 30 %)",
             r.sobre_area <= 30.0,
             f"sobre-área = {r.sobre_area:+.1f} %",
             f"sobre-área = {r.sobre_area:+.1f} %: el equipo está "
             f"sobredimensionado; revise B, L o el layout")
        pr = float(d.get("pitch_mm") or 0) / max(float(d.get("d_o_mm") or 1), 1e-9)
        fila("Pitch ratio P_T/d_o ≥ 1.25 (TEMA)",
             pr >= 1.25, f"P_T/d_o = {pr:.2f}",
             f"P_T/d_o = {pr:.2f}: sin luz para limpiar ni mandrilar los tubos")
        B = float(d.get("baffle_mm") or 0) / 1000.0
        fila("Espaciado de baffles 0.2·D_s ≤ B ≤ D_s (TEMA RCB-4.5.1)",
             0.2 * r.D_s <= B <= r.D_s,
             f"B = {B*1000:.0f} mm · D_s = {r.D_s*1000:.0f} mm",
             f"B = {B*1000:.0f} mm fuera de [0.2·D_s, D_s] = "
             f"[{0.2*r.D_s*1000:.0f}, {r.D_s*1000:.0f}] mm")
        fila("Relación L/D_s entre 3 y 15",
             3.0 <= float(d.get("long_m") or 0) / r.D_s <= 15.0,
             f"L/D_s = {float(d.get('long_m') or 0) / r.D_s:.1f}",
             f"L/D_s = {float(d.get('long_m') or 0) / r.D_s:.1f}: el equipo "
             f"resulta desproporcionado para fabricar")
        corte = float(d.get("corte_pct") or 0)
        fila("Corte de baffle 15–45 % (estándar Kern: 25 %)",
             15.0 <= corte <= 45.0,
             f"corte = {corte:.0f} %",
             f"corte = {corte:.0f} % fuera de [15, 45] %")

    # ---------------- verificaciones propias del RATING -------------------
    if modo == "rating":
        rel = abs(getattr(r, "residual", 0.0)) / max(r.q, 1.0)
        fila("Cierre del balance |q − U·A·F·LMTD| ≤ 0.5 % de q",
             rel <= 0.005,
             f"residual = {rel*100:.3f} % de q",
             f"residual = {rel*100:.3f} % de q: la solución no cierra el "
             f"balance; afine la tolerancia del rating")
        ef = getattr(r, "efectividad", 0.0)
        fila("Efectividad térmica ε ≤ 95 % (alejado del pinch)",
             ef <= 0.95,
             f"ε = {ef*100:.1f} %",
             f"ε = {ef*100:.1f} %: el equipo trabaja contra el pinch; la "
             f"salida es muy sensible al ensuciamiento")
        fila("Segunda ley: sin cruce de temperaturas",
             r.T_c_out < float(d.get("tin_cal") or 1e9)
             and r.T_h_out > float(d.get("tin_fri") or -1e9),
             f"T_c,out = {r.T_c_out:.1f} °C < T_h,in · "
             f"T_h,out = {r.T_h_out:.1f} °C > T_c,in",
             "cruce de temperaturas: revise caudales y temperaturas de entrada")

    # ---------------- verificación de boquillas (si hay mecánico) ---------
    if m is not None and getattr(m, "boquilla_coraza", None):
        bn = m.boquilla_coraza
        fila("ρV² en boquilla de coraza ≤ 2232 Pa (TEMA RCB-4.6.1)",
             bn.rho_v2 <= 2232.25,
             f"ρV² = {bn.rho_v2:,.0f} Pa",
             f"ρV² = {bn.rho_v2:,.0f} Pa: riesgo de erosión del haz")
    return filas


def _limite_delta_p(d: Dict[str, Any], clave: str) -> Optional[float]:
    """Limite permisible de caida de presion cargado por el usuario [Pa].

    Vacio o <= 0 significa «sin limite»: la alerta no se evalua.
    """
    v = d.get(clave)
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0.0 else None


def _alertas_delta_p(d: Dict[str, Any], r) -> None:
    """Verificacion hidraulica: Δp calculada vs. limite permisible del usuario.

    Si alguna caida de presion supera el limite establecido, se advierte que
    debe revisarse o redimensionarse el equipo (requisito de entrega 2.1.4).
    """
    for clave, dp, lado, ref in (
            ("dp_t_max", r.dp_t, "tubos", "Kern Eq. 7.43/7.45"),
            ("dp_s_max", r.dp_s, "coraza", "Kern Eq. 7.44")):
        limite = _limite_delta_p(d, clave)
        if limite is not None and dp > limite:
            r.advertencias.append(
                f"Caída de presión en {lado} = {dp:,.0f} Pa supera el límite "
                f"permisible ({limite:,.0f} Pa): revise el diseño o "
                f"redimensione el equipo (más pasos, mayor diámetro o menor "
                f"longitud). Cálculo según {ref}.")


METODOS_CORAZA = ("kern", "bell_delaware")
METODOS_CORAZA_UI = ("Kern (clásico)", "Bell-Delaware")


def _metodo_coraza(d: Dict[str, Any]) -> str:
    """Metodo de coraza pedido en el proyecto (por defecto Kern)."""
    m = str(d.get("metodo_coraza") or "kern").strip().lower()
    if "bell" in m:
        return "bell_delaware"
    return m if m in METODOS_CORAZA else "kern"


def correr_sizing(d: Dict[str, Any]):
    """Metodo de Kern: itera sobre U hasta converger el area requerida."""
    _exigir_modulos()
    caliente, fria = _corrientes(d)
    tubos, coraza = _geometria(d)
    # La holgura haz-coraza la fija el tipo de cabezal trasero TEMA elegido:
    # sin reservarla, el haz no cabe en la coraza (tipos flotantes P/S/T/W).
    holgura = HOLGURA_HAZ.get(str(d.get("cab_trasero", "M")).upper(), 0.0)
    r = dimensionar(caliente, fria, tubos, coraza,
                    lado_tubos=d["lado_tubos"],
                    U_inicial=d["u_inicial"],
                    holgura_haz=holgura,
                    metodo_coraza=_metodo_coraza(d))
    _alertas_delta_p(d, r)
    return r


def correr_rating(d: Dict[str, Any]):
    """Evalua un equipo ya construido: itera sobre las T de salida."""
    _exigir_modulos()
    caliente, fria = _corrientes_rating(d)
    tubos, coraza = _geometria(d)
    geom = ExchangerGeometry(tubos=tubos, coraza=coraza,
                             N_tt=int(d["n_tt"]), D_s=d["d_s_mm"] / 1000.0)
    r = evaluar(caliente, fria, geom, lado_tubos=d["lado_tubos"],
                metodo_coraza=_metodo_coraza(d))
    _alertas_delta_p(d, r)
    return r


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
        material_tubo=d["mat_tubo"],
        corrosion=d["corrosion_mm"] / 1000.0,
        tipo_carcasa=d["tipo_carcasa"],
        cabezal_frontal=d["cab_frontal"],
        cabezal_trasero=d["cab_trasero"],
        d_perno=d["d_perno_mm"] / 1000.0)
    return disenar_mecanico(inp)
