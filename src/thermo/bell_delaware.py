# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
# Trazabilidad interna BD-JcJlJbJr-9A17 / KERN-7F4-0x444E4242 (origen: src/core/marca.py; uso pasivo, no bloquea nada).
"""
METODO DE BELL-DELAWARE PARA EL LADO CORAZA (monofasico)
========================================================
Alternativa rigurosa al metodo de Kern. En lugar de un unico coeficiente de
coraza, descompone el flujo en cinco corrientes (cruzado ideal B, fugas
A y E, bypass C y F, particion de paso) y corrige el coeficiente ideal de
banco de tubos con los factores Jc, Jl, Jb, Jr (y Js si el espaciado de
deflectores es desigual):

    h_o = h_id * Jc * Jl * Jb * Jr          (Js = 1 con espaciado uniforme)
    h_id = j_i * cp * G_s * Pr^(-2/3) * (mu/mu_w)^0.14

y la caida de presion en tres componentes:

    dp_s = dp_c + dp_w + dp_e
    dp_c = dp_bi (Nb - 1) Rb Rl ;  dp_e = dp_bi (1 + Ncw/Ncc) Rb Rs ;  Rs = 2

Fuentes
-------
* Taborek, J. (1983): coeficientes a1..a4, b1..b4 de los factores ideales
  j_i y f_i por rango de Reynolds y angulo de arreglo.
* Kakac, Liu y Pramuanjaroenkij, "Heat Exchangers: Selection, Rating and
  Thermal Design", 3a ed., CRC Press (2012), seccion 9.4.4.
* Goncalves, Costa y Bagajewicz, AIChE Journal 65(8):e16602 (2019):
  formulacion completa y correlaciones de holguras TEMA.
* Bell, K. J. (1963): metodo original.

Convenciones
------------
* Re_s de Bell-Delaware se evalua con el DIAMETRO EXTERNO (d_o), no con el
  diametro equivalente D_e de Kern: es una diferencia de definicion
  documentada, no un error.
* Angulos de arreglo: 30/60 -> 30 grados; 45 -> 45; 90 -> 90 (cuadrado).
"""
from __future__ import annotations

import math
from typing import Dict, Optional, Tuple

__all__ = [
    "coeficientes_ideales", "coeficientes_friccion", "j_ideal", "f_ideal",
    "geometria_baffle",
    "lado_coraza_bell_delaware",
]

# ---------------------------------------------------------------------------
# 1. COEFICIENTES DE LA CORRELACION IDEAL (Taborek, 1983)
#    (a1, a2, a3, a4, b1, b2, b3, b4) por rango de Re_s y angulo de arreglo.
# ---------------------------------------------------------------------------
_RANGOS = (
    (1.0e4, 1.0e5), (1.0e3, 1.0e4), (1.0e2, 1.0e3), (1.0e1, 1.0e2), (0.0, 1.0e1),
)

_COEFS: Dict[int, Dict[str, object]] = {
    # a3, a4, b3, b4 son PROPIOS del arreglo; a1, a2, b1, b2 del rango de Re
    # (Taborek 1983, reproducido en Kakac & Liu 9.4.4 y en la literatura docente).
    30: {
        "fijos": (1.450, 0.519, 7.000, 0.500),
        "rangos": (
            (0.321, -0.388, 0.372, -0.123),   # 1e5 - 1e4
            (0.321, -0.388, 0.372, -0.123),   # 1e4 - 1e3
            (0.593, -0.477, 4.570, -0.476),   # 1e3 - 1e2
            (1.360, -0.657, 45.100, -0.973),  # 1e2 - 10
            (1.400, -0.667, 48.000, -1.000),  # < 10
        ),
    },
    45: {
        "fijos": (1.930, 0.500, 6.590, 0.520),
        "rangos": (
            (0.370, -0.396, 0.303, -0.126),
            (0.370, -0.396, 0.333, -0.136),
            (0.730, -0.500, 3.500, -0.476),
            (1.300, -0.656, 26.200, -0.913),
            (1.550, -0.667, 32.000, -1.000),
        ),
    },
    90: {
        "fijos": (1.187, 0.370, 6.300, 0.378),
        "rangos": (
            (0.370, -0.395, 0.391, -0.148),
            (0.107, -0.266, 0.0815, 0.022),
            (0.408, -0.460, 6.090, -0.602),
            (0.900, -0.631, 32.100, -0.963),
            (0.970, -0.667, 35.000, -1.000),
        ),
    },
}


def _angulo(layout: int) -> int:
    """Angulo nominal del arreglo (30/60 -> 30, 45 -> 45, 90 -> 90)."""
    if layout in (30, 60):
        return 30
    if layout in (45, 90):
        return layout
    raise ValueError(
        f"Layout {layout} no soportado por Bell-Delaware (use 30/60/45/90).")


def coeficientes_ideales(Re: float, layout: int) -> Tuple[float, float, float, float]:
    """Devuelve (a1, a2, a3, a4) del factor j_i para el Re y arreglo dados."""
    if Re <= 0.0:
        raise ValueError("Re_s debe ser positivo.")
    tabla = _COEFS[_angulo(layout)]
    a3, a4, _, _ = tabla["fijos"]
    for i, (lo, hi) in enumerate(_RANGOS):
        if (lo < Re <= hi) or (i == len(_RANGOS) - 1 and Re <= hi):
            a1, a2, _, _ = tabla["rangos"][i]
            return a1, a2, a3, a4
    a1, a2, _, _ = tabla["rangos"][0]
    return a1, a2, a3, a4


def coeficientes_friccion(Re: float, layout: int) -> Tuple[float, float, float, float]:
    """Devuelve (b1, b2, b3, b4) del factor f_i para el Re y arreglo dados."""
    if Re <= 0.0:
        raise ValueError("Re_s debe ser positivo.")
    tabla = _COEFS[_angulo(layout)]
    _, _, b3, b4 = tabla["fijos"]
    for i, (lo, hi) in enumerate(_RANGOS):
        if (lo < Re <= hi) or (i == len(_RANGOS) - 1 and Re <= hi):
            _, _, b1, b2 = tabla["rangos"][i]
            return b1, b2, b3, b4
    _, _, b1, b2 = tabla["rangos"][0]
    return b1, b2, b3, b4


def j_ideal(Re: float, P_T: float, D_o: float, layout: int) -> float:
    """Factor de Colburn ideal de banco de tubos j_i (Eq. 38-39 de Taborek)."""
    a1, a2, a3, a4 = coeficientes_ideales(Re, layout)
    a = a3 / (1.0 + 0.14 * Re ** a4)
    return a1 * (1.33 / (P_T / D_o)) ** a * Re ** a2


def f_ideal(Re: float, P_T: float, D_o: float, layout: int) -> float:
    """Factor de friccion ideal de banco de tubos f_i (Kirkpatrick)."""
    b1, b2, b3, b4 = coeficientes_friccion(Re, layout)
    b = b3 / (1.0 + 0.14 * Re ** b4)
    return b1 * (1.33 / (P_T / D_o)) ** b * Re ** b2


# ---------------------------------------------------------------------------
# 2. GEOMETRIA DEL DEFLECTOR Y AREAS DE FUGA
# ---------------------------------------------------------------------------
def geometria_baffle(D_s: float, D_o: float, P_T: float, B: float, layout: int,
                     N_tt: int, N_baffles: int, corte: float = 0.25,
                     L_tubo: float = 0.0) -> Dict[str, float]:
    """
    Areas, fracciones y numeros de filas del arreglo Bell-Delaware.

    Parametros
    ----------
    D_s : diametro interior de coraza [m]
    D_o : diametro exterior del tubo [m]
    P_T : pitch [m]
    B   : espaciado de deflectores [m]
    N_tt: numero total de tubos
    N_baffles: numero de deflectores
    corte: fraccion de corte del deflector (0.25 = 25 %)
    """
    if D_s <= 0 or P_T <= 0 or B <= 0 or N_tt <= 0:
        raise ValueError("Geometria invalida para Bell-Delaware.")

    angulo = _angulo(layout)
    # Holguras TEMA (Taborek/Goncalves Eqs. 30-31); Ltb = 1/32 in para tubos
    # pequenos (la holgura de 1/64 in aplica a vanos no soportados > 0.9 m)
    L_bb = 12.8e-3 + 4.8e-3 * D_s          # holgura haz-coraza (diametral)
    L_sb = 3.1e-3 + 4.0e-3 * D_s           # holgura deflector-coraza
    L_tb = 0.8e-3 if (L_tubo <= 0.9 or D_o > 0.03175) else 0.4e-3

    D_ctl = D_s - L_bb - D_o               # circulo de centros del anillo exterior
    if D_ctl <= 0:
        raise ValueError("La coraza no deja espacio para el anillo exterior de tubos.")
    D_otl = D_s - L_bb

    # angulos del corte del deflector
    Bc = corte
    th_Ds = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * Bc)))
    th_ctl = 2.0 * math.acos(max(-1.0, min(1.0, (D_s / D_ctl) * (1.0 - 2.0 * Bc))))

    # filas de tubos cruzadas
    Lpp = {30: 0.866 * P_T, 45: 0.707 * P_T, 90: P_T}[angulo]
    N_tcc = (D_s / Lpp) * (1.0 - 2.0 * Bc)
    N_tcw = (0.8 / Lpp) * (D_s * Bc - 0.5 * (D_s - D_ctl))
    N_c = (N_tcc + N_tcw) * (N_baffles + 1)

    # fraccion de tubos en ventana / en flujo cruzado
    F_w = (th_ctl - math.sin(th_ctl)) / (2.0 * math.pi)
    F_c = max(0.0, 1.0 - 2.0 * F_w)

    # areas
    ltpeff = {30: P_T, 45: 0.707 * P_T, 90: P_T}[angulo]
    S_m = B * (L_bb + (D_ctl / ltpeff) * (P_T - D_o))
    S_wg = (math.pi / 4.0) * D_s ** 2 * (th_Ds - math.sin(th_Ds)) / (2.0 * math.pi)
    N_tw = N_tt * F_w
    S_wt = N_tw * (math.pi / 4.0) * D_o ** 2
    S_w = max(S_wg - S_wt, 1e-6)
    S_sb = math.pi * D_s * (L_sb / 2.0) * (1.0 - th_Ds / (2.0 * math.pi))
    S_tb = N_tt * (1.0 - F_w) * (math.pi / 4.0) * ((D_o + L_tb) ** 2 - D_o ** 2)
    S_b = B * (D_s - D_otl)              # sin franjas de sellado

    r_s = S_sb / (S_sb + S_tb) if (S_sb + S_tb) > 0 else 0.0
    r_lm = (S_sb + S_tb) / S_m if S_m > 0 else 0.0
    F_sbp = S_b / S_m if S_m > 0 else 0.0
    D_w = 4.0 * S_w / (math.pi * D_o * N_tw + math.pi * D_s * th_Ds / (2.0 * math.pi))

    return {
        "N_tcc": N_tcc, "N_tcw": N_tcw, "N_c": N_c, "F_w": F_w, "F_c": F_c,
        "S_m": S_m, "S_w": S_w, "S_sb": S_sb, "S_tb": S_tb, "S_b": S_b,
        "r_s": r_s, "r_lm": r_lm, "F_sbp": F_sbp, "D_w": D_w,
        "L_bb": L_bb, "L_sb": L_sb, "L_tb": L_tb, "D_ctl": D_ctl, "D_otl": D_otl,
        "th_Ds": th_Ds, "th_ctl": th_ctl,
    }


# ---------------------------------------------------------------------------
# 3. COEFICIENTE Y CAIDA DE PRESION
# ---------------------------------------------------------------------------
def lado_coraza_bell_delaware(
        m_dot: float, rho: float, mu: float, cp: float, k: float,
        mu_w: float, D_s: float, D_o: float, P_T: float, B: float,
        layout: int, N_tt: int, N_baffles: int, corte: float = 0.25,
        L_tubo: float = 0.0) -> Dict[str, float]:
    """
    Coeficiente de pelicula y caida de presion del lado coraza (Bell-Delaware).

    Devuelve un dict con h_o, dp_s y todos los factores intermedios para
    poder auditarlos: Re, j_i, f_i, J_c, J_l, J_b, J_r, R_l, R_b y las areas.
    """
    geo = geometria_baffle(D_s, D_o, P_T, B, layout, N_tt, N_baffles,
                           corte, L_tubo)
    S_m = geo["S_m"]
    G_s = m_dot / S_m                       # [kg/m2.s]
    Pr = cp * mu / k
    Re = D_o * G_s / mu                     # Bell-Delaware: con d_o
    if Re <= 0.0:
        raise ValueError("Re_s no positivo: revise caudales y areas.")

    # --- factores de correccion de transferencia ---
    J_c = 0.55 + 0.72 * geo["F_c"]
    r_s, r_lm, F_sbp = geo["r_s"], geo["r_lm"], geo["F_sbp"]
    J_l = 0.44 * (1.0 - r_s) + (1.0 - 0.44 * (1.0 - r_s)) * math.exp(-2.2 * r_lm)
    C_bh = 1.35 if Re <= 100.0 else 1.25
    J_b = math.exp(-C_bh * F_sbp)
    if Re <= 20.0:
        J_r = (10.0 / max(geo["N_c"], 1.0)) ** 0.18
    elif Re <= 100.0:
        Jr1 = (10.0 / max(geo["N_c"], 1.0)) ** 0.18
        J_r = Jr1 + ((20.0 - Re) / 80.0) * (Jr1 - 1.0)
    else:
        J_r = 1.0

    phi_w = (mu / mu_w) ** 0.14 if mu_w > 0 else 1.0
    j_i = j_ideal(Re, P_T, D_o, layout)
    h_id = j_i * cp * G_s * Pr ** (-2.0 / 3.0) * phi_w
    h_o = h_id * J_c * J_l * J_b * J_r

    # --- caida de presion ---
    f_i = f_ideal(Re, P_T, D_o, layout)
    dp_bi = 2.0 * f_i * geo["N_tcc"] * G_s ** 2 / rho
    C_bp = 4.5 if Re <= 100.0 else 3.7
    R_b = math.exp(-C_bp * F_sbp)
    p_exp = -0.15 * (1.0 + r_s) + 0.8
    R_l = math.exp(-1.33 * (1.0 + r_s) * r_lm ** p_exp)

    N_b = max(N_baffles, 1)
    dp_c = dp_bi * max(N_baffles - 1, 1) * R_b * R_l
    G_w = m_dot / math.sqrt(S_m * geo["S_w"])
    if Re < 100.0:
        dp_w = N_b * R_l * (
            26.0 * (G_w * mu / rho) * (geo["N_tcw"] / max(P_T - D_o, 1e-6)
                                       + B / geo["D_w"] ** 2)
            + 2.0 * G_w ** 2 / rho
        )
    else:
        dp_w = N_b * R_l * (2.0 + 0.6 * geo["N_tcw"]) * G_w ** 2 / (2.0 * rho)
    dp_e = dp_bi * (1.0 + geo["N_tcw"] / max(geo["N_tcc"], 1e-6)) * R_b * 2.0
    dp_s = dp_c + dp_w + dp_e

    salida = {
        "h_o": h_o, "h_id": h_id, "dp_s": dp_s, "dp_c": dp_c, "dp_w": dp_w,
        "dp_e": dp_e, "Re": Re, "j_i": j_i, "f_i": f_i,
        "J_c": J_c, "J_l": J_l, "J_b": J_b, "J_r": J_r, "R_l": R_l, "R_b": R_b,
        "G_s": G_s, "Pr": Pr,
    }
    salida.update(geo)
    return salida
