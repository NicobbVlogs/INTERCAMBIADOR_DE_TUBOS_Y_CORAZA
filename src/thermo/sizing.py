"""
SIZING TERMICO - Metodo de Kern (iteracion sobre el coeficiente global U)
=============================================================================
Dado el servicio termico (caudales + temperaturas) y las restricciones
geometricas (tubo, pitch, longitud, espaciado de baffles), devuelve el area
de transferencia, el numero de tubos y el diametro de coraza requeridos.

Algoritmo (INSTRUCCIONES_THERMO.md, seccion 2):
    1. Balance de energia puro  ->  q  y  la temperatura de salida faltante.
    2. Se asume un U inicial.
    3. A = q/(U*F*LMTD)  ->  N_tt  ->  D_s   (constantes TEMA C_L / C_TP).
    4. Re, Pr, Nu  ->  h_i (tubos, Sieder-Tate/Hausen) y h_o (coraza, Kern).
    5. Se recalcula U y se repite hasta error relativo < tolerancia.

Referencias: D.Q. Kern, "Process Heat Transfer" (cap. 7 y 11);
             R.W. Serth, "Process Heat Transfer: Principles & Applications";
             TEMA Clase "C".
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

try:
    from src.core.thermo_data import FluidState, ThermoDatabase
except ImportError:  # ejecucion directa: `python src/thermo/sizing.py`
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.core.thermo_data import FluidState, ThermoDatabase

db = ThermoDatabase()

# =============================================================================
# 1. CONSTANTES TEMA Y LIMITES DE BUENA PRACTICA
# =============================================================================
# Constante de layout C_L: fraccion de area del arreglo ocupada por el paso
# de tubos (Serth, tabla de constantes de conteo de tubos).
_C_L = {30: 0.87, 60: 0.87, 45: 1.00, 90: 1.00}

# Constante de conteo de tubos C_TP: penalizacion por las particiones de paso.
_C_TP = {1: 0.93, 2: 0.90, 4: 0.85, 6: 0.85, 8: 0.85}

# Velocidades recomendadas (TEMA / Kern) para liquidos sin cambio de fase.
V_TUBO_MIN, V_TUBO_MAX = 0.9, 2.4     # m/s  (erosion / vibracion arriba)
V_CORAZA_MIN, V_CORAZA_MAX = 0.3, 1.5  # m/s

F_MIN_ACEPTABLE = 0.75   # Debajo de esto el arreglo 1-n es inadmisible.
RE_KERN_MIN = 2.0e3      # Validez inferior de la correlacion de coraza.
RE_KERN_MAX = 1.0e6


# =============================================================================
# 2. CONTENEDORES DE DATOS
# =============================================================================
@dataclass
class TubeGeometry:
    """Geometria del haz de tubos (todo en metros)."""
    D_o: float                  # Diametro exterior del tubo
    espesor: float              # Espesor de pared
    P_T: float                  # Pitch (centro a centro)
    L: float                    # Longitud efectiva del tubo
    layout: int = 30            # 30/60 = triangular, 45/90 = cuadrado
    n_pasos: int = 2            # Pasos por tubos
    material: str = "Cobre"

    @property
    def D_i(self) -> float:
        return self.D_o - 2.0 * self.espesor

    @property
    def PR(self) -> float:
        """Relacion de pitch P_T/D_o (tipica 1.25 - 1.50)."""
        return self.P_T / self.D_o

    @property
    def a_tubo(self) -> float:
        """Area de flujo interna de un tubo [m2]."""
        return math.pi * self.D_i ** 2 / 4.0


@dataclass
class ShellGeometry:
    """Geometria de la coraza."""
    B: float                    # Espaciado de baffles [m]
    tipo: str = "E"             # TEMA E (1 paso por coraza)
    corte_baffle: float = 0.25  # Fraccion de corte (25 % estandar)


@dataclass
class Stream:
    """Corriente de proceso. T en grados Celsius, m_dot en kg/s."""
    fluido: str
    m_dot: float
    T_in: float
    T_out: Optional[float] = None   # None => incognita del balance
    R_f: Optional[float] = None     # Ensuciamiento [m2.K/W]; None => valor TEMA del fluido


@dataclass
class SizingResult:
    """Resultado convergido del dimensionamiento."""
    q: float                 # Carga termica [W]
    U: float                 # Coef. global sucio referido a A_o [W/m2.K]
    A: float                 # Area de transferencia requerida [m2]
    A_real: float            # Area instalada con N_tt entero [m2]
    sobre_area: float        # Exceso de superficie [%]
    N_tt: int                # Numero total de tubos
    D_s: float               # Diametro interior de coraza [m]
    N_baffles: int
    LMTD: float
    F: float
    T_h_out: float
    T_c_out: float
    h_i: float
    h_o: float
    Re_t: float
    Re_s: float
    v_t: float
    v_s: float
    D_e: float               # Diametro equivalente de coraza [m]
    f_t: float               # Factor de friccion Darcy en tubos [-]
    f_s: float               # Factor de friccion Kern en coraza [-]
    dp_t: float              # Caida de presion lado tubos [Pa]
    dp_s: float              # Caida de presion lado coraza [Pa]
    iteraciones: int
    regimen_tubo: str
    advertencias: List[str] = field(default_factory=list)


# =============================================================================
# 3. BLOQUES DE CALCULO ELEMENTALES
# =============================================================================
def balance_energia(caliente: Stream, fria: Stream,
                    tol: float = 1e-5, max_iter: int = 50
                    ) -> Tuple[float, float, float]:
    """
    Balance de energia termico en estado estacionario (Kern, 1950, Cap. 5):
        q = m_dot_h * cp_h * (T_h_in - T_h_out) = m_dot_c * cp_c * (T_c_out - T_c_in)
    Con validacion de limites de fase en entradas y salidas.

    Exactamente una de las dos temperaturas de salida debe ser desconocida.
    Como cp depende de la T media (que depende de la salida buscada), se
    resuelve por sustitucion sucesiva.

    Devuelve (q [W], T_h_out [C], T_c_out [C]).
    """
    if caliente.m_dot <= 0.0 or fria.m_dot <= 0.0:
        raise ValueError("Los caudales masicos deben ser estrictamente positivos.")

    incognitas = [s.T_out is None for s in (caliente, fria)]
    if sum(incognitas) != 1:
        raise ValueError(
            "Balance de energia mal planteado: debe conocerse exactamente UNA "
            "temperatura de salida (la otra se calcula).\n"
            "   Indique T_out en una sola de las dos corrientes."
        )
    if caliente.T_in <= fria.T_in:
        raise ValueError(
            "Violacion de la 2a Ley: el fluido 'caliente' entra a "
            f"{caliente.T_in:.1f} C y el 'frio' a {fria.T_in:.1f} C.\n"
            "   El calor no fluye espontaneamente de frio a caliente."
        )

    # Validar que las temperaturas conocidas esten dentro del rango de fase
    db.get_fluid_state(caliente.fluido, caliente.T_in, "C")
    db.get_fluid_state(fria.fluido, fria.T_in, "C")

    # Lado con las dos temperaturas conocidas -> fija la carga termica q.
    conocida, buscada = (fria, caliente) if caliente.T_out is None else (caliente, fria)
    db.get_fluid_state(conocida.fluido, conocida.T_out, "C")

    if conocida is caliente and conocida.T_out >= conocida.T_in:
        raise ValueError("El fluido caliente debe enfriarse (T_h,out < T_h,in).")
    if conocida is fria and conocida.T_out <= conocida.T_in:
        raise ValueError("El fluido frio debe calentarse (T_c,out > T_c,in).")

    cp_k = db.get_fluid_state(
        conocida.fluido, 0.5 * (conocida.T_in + conocida.T_out), "C"
    ).cp
    q = abs(conocida.m_dot * cp_k * (conocida.T_out - conocida.T_in))

    # Sustitucion sucesiva inicializada en T_in (garantizado dentro del rango
    # valido del fluido); T media acotada a la ventana de validez.
    signo = -1.0 if buscada is caliente else 1.0
    T_min_b, T_max_b = db.get_limits(buscada.fluido, "C")
    T_out = buscada.T_in
    convergio = False

    for _ in range(max_iter):
        T_med = min(max(0.5 * (buscada.T_in + T_out), T_min_b + 1e-3), T_max_b - 1e-3)
        cp_b = db.get_fluid_state(buscada.fluido, T_med, "C").cp
        nuevo = buscada.T_in + signo * q / (buscada.m_dot * cp_b)
        if abs(nuevo - T_out) < tol:
            T_out = nuevo
            convergio = True
            break
        T_out = nuevo

    if not convergio:
        raise ValueError(
            "El balance de energia no convergio en el numero maximo de iteraciones."
        )

    # Validar que la temperatura de salida calculada respete los limites de fase
    db.get_fluid_state(buscada.fluido, T_out, "C")

    T_h_out = T_out if buscada is caliente else caliente.T_out
    T_c_out = T_out if buscada is fria else fria.T_out

    if T_h_out <= fria.T_in:
        raise ValueError(
            "Cruce de temperaturas imposible en contracorriente: el caliente "
            f"saldria a {T_h_out:.1f} C, por debajo de la entrada del frio "
            f"({fria.T_in:.1f} C).\n"
            "   Reduzca la carga termica o aumente el caudal caliente."
        )
    if T_c_out >= caliente.T_in:
        raise ValueError(
            f"Cruce de temperaturas imposible: el frio saldria a {T_c_out:.1f} C, "
            f"por encima de la entrada del caliente ({caliente.T_in:.1f} C)."
        )
    return q, T_h_out, T_c_out


def lmtd_contracorriente(T_h_in: float, T_h_out: float,
                         T_c_in: float, T_c_out: float) -> float:
    """
    Diferencia media logaritmica de temperatura (LMTD) en contracorriente puro:
        LMTD = (dT1 - dT2) / ln(dT1 / dT2)   (Kern, 1950, Cap. 5, Eq. 5.14)
    donde:
        dT1 = T_h_in - T_c_out
        dT2 = T_h_out - T_c_in
    Para R = 1 (dT1 = dT2) se remueve la singularidad 0/0 mediante el limite LMTD = dT1.
    """
    dT1 = T_h_in - T_c_out
    dT2 = T_h_out - T_c_in
    if dT1 <= 0.0 or dT2 <= 0.0:
        raise ValueError(
            "LMTD indefinida: existe un cruce de temperaturas "
            f"(dT1 = {dT1:.2f} C, dT2 = {dT2:.2f} C). Revise el balance termico."
        )
    # Singularidad 0/0 cuando dT1 = dT2 (R = 1 en contracorriente): tolerancia
    # RELATIVA (la absoluta pierde cifras en log(dT1/dT2) ~ 0). El limite de
    # la LMTD es la media aritmetica de ambos extremos.
    if abs(dT1 - dT2) <= 1e-6 * max(dT1, dT2):
        return 0.5 * (dT1 + dT2)
    return (dT1 - dT2) / math.log(dT1 / dT2)


def factor_correccion_F(T_h_in: float, T_h_out: float,
                        T_c_in: float, T_c_out: float,
                        n_pasos: int, n_corazas: int = 1) -> float:
    """
    Factor de correccion F_LMTD de Bowman-Mueller-Nagle para configuraciones
    de 1-2n y N_s corazas en serie (Kern, 1950, Cap. 5; estandares TEMA):
        q = U * A * F * LMTD
    Para 1-2 (1 coraza, 2 o mas pasos pares de tubos):
        F = (sqrt(R^2 + 1) / (R - 1)) * ln((1 - P)/(1 - P*R)) / ln((2/P - 1 - R + sqrt(R^2+1))/(2/P - 1 - R - sqrt(R^2+1)))
    donde P = (T_c_out - T_c_in)/(T_h_in - T_c_in) y R = (T_h_in - T_h_out)/(T_c_out - T_c_in).
    Para N_s corazas en serie (ej. carcasa TEMA F con deflector longitudinal, N_s=2),
    se reduce P segun la formula de corazas multiples de Bowman (Kern Eq. 7.42).
    """
    if n_pasos == 1:
        return 1.0
    if n_pasos < 2 or n_pasos % 2 != 0:
        raise ValueError(f"n_pasos debe ser 1 o un entero par >= 2 (recibido: {n_pasos}).")
    if n_corazas < 1:
        raise ValueError(f"n_corazas debe ser >= 1 (recibido: {n_corazas}).")

    dT_max = T_h_in - T_c_in
    dT_c = T_c_out - T_c_in
    dT_h = T_h_in - T_h_out
    if dT_max <= 0.0 or dT_c <= 0.0 or dT_h <= 0.0:
        raise ValueError("Temperaturas incoherentes para el calculo del factor F.")

    P = dT_c / dT_max
    R = dT_h / dT_c

    if P >= 1.0 or P * R >= 1.0:
        raise ValueError(
            f"Cruce termodinamico absoluto alcanzado (P={P:.3f}, R={R:.3f})."
        )

    # Reduccion de N_s corazas en serie (p. ej. Carcasa TEMA F -> n_corazas = 2)
    if n_corazas > 1:
        if abs(R - 1.0) < 1e-6:
            P = P / (n_corazas - (n_corazas - 1.0) * P)
        else:
            ratio = ((1.0 - P * R) / (1.0 - P)) ** (1.0 / n_corazas)
            P = (ratio - 1.0) / (ratio - R)

    raiz = math.sqrt(R * R + 1.0)
    arg_den = 2.0 / P - 1.0 - R
    num_ln = arg_den + raiz
    den_ln = arg_den - raiz
    if den_ln <= 0.0 or num_ln <= 0.0:
        raise ValueError(
            f"Arreglo {n_corazas}-{n_pasos} termodinamicamente imposible para este "
            f"servicio (P_efectivo = {P:.3f}, R = {R:.3f}).\n"
            "   Use mas pasos por coraza o un intercambiador en contracorriente puro."
        )
    log_term = math.log(num_ln / den_ln)

    if abs(R - 1.0) < 1e-6:
        return P * raiz / ((1.0 - P) * log_term)
    return (raiz / (R - 1.0)) * math.log((1.0 - P) / (1.0 - P * R)) / log_term


def diametro_equivalente(P_T: float, D_o: float, layout: int) -> float:
    """
    Diametro equivalente hidraulico D_e para flujo cruzado en coraza (Kern, 1950, Cap. 7):
    Basado en el perimetro mojado de transferencia de calor: D_e = 4 * A_libre / perimetro.

    - Arreglo cuadrado (layout 45 o 90 deg, Kern Eq. 7.2):
        D_e = 4 * (P_T^2 - pi * D_o^2 / 4) / (pi * D_o)
    - Arreglo triangular (layout 30 o 60 deg, Kern Eq. 7.3):
        D_e = 4 * ((sqrt(3)/4) * P_T^2 - (pi/8) * D_o^2) / (pi * D_o / 2)
    """
    if layout in (30, 60):   # Triangular: medio triangulo equilatero
        area_libre = (math.sqrt(3.0) / 4.0) * P_T ** 2 - (math.pi / 8.0) * D_o ** 2
        perimetro = math.pi * D_o / 2.0
    elif layout in (45, 90):  # Cuadrado: un cuadrado completo = 1 tubo
        area_libre = P_T ** 2 - (math.pi / 4.0) * D_o ** 2
        perimetro = math.pi * D_o
    else:
        raise ValueError(
            f"Layout '{layout}' no reconocido. Use 30 o 60 (triangular), "
            "45 o 90 (cuadrado)."
        )
    if area_libre <= 0.0:
        raise ValueError(
            f"Pitch P_T = {P_T*1000:.1f} mm demasiado pequeno para tubos de "
            f"D_o = {D_o*1000:.1f} mm: los tubos se solapan.\n"
            "   TEMA exige P_T >= 1.25 * D_o."
        )
    return 4.0 * area_libre / perimetro


def nusselt_tubos(Re: float, Pr: float, D_i: float, L: float,
                  phi: float) -> Tuple[float, str]:
    """
    Numero de Nusselt interno en tubos: Nu_t = h_i * D_i / k (Kern, 1950, Cap. 6).
    Continuo en las fronteras Re = 2100 y Re = 10000. Devuelve (Nu, regimen).

    - Re < 2100 (laminar):
        Sieder & Tate con piso Nu = 3.66 (T_w constante):
        Nu_lam = max(1.86 * (Re * Pr * D_i / L)^(1/3) * phi, 3.66)   (Kern Eq. 6.2)
    - Re >= 10000 (turbulento):
        Sieder & Tate turbulento:
        Nu_turb = 0.027 * Re^0.8 * Pr^(1/3) * phi                   (Kern Eq. 6.3)
    - 2100 <= Re < 10000 (transicion):
        Interpolacion continua monótona entre Nu_lam(2100) y Nu_turb(10000)
        garantizando continuidad C0 (salto medido ~ 10^-7).
    """
    if Re <= 0.0:
        raise ValueError("El numero de Reynolds en tubos debe ser positivo.")

    def _nu_lam(re: float) -> float:
        return max(1.86 * (re * Pr * D_i / L) ** (1.0 / 3.0) * phi, 3.66)

    def _nu_turb(re: float) -> float:
        return 0.027 * (re ** 0.8) * (Pr ** (1.0 / 3.0)) * phi

    if Re < 2100.0:
        return _nu_lam(Re), "laminar"
    if Re >= 1.0e4:
        return _nu_turb(Re), "turbulento"

    w = (Re - 2100.0) / (1.0e4 - 2100.0)
    return (1.0 - w) * _nu_lam(2100.0) + w * _nu_turb(1.0e4), "transicion"


def factor_friccion_tubos(Re: float, epsilon: float, D_i: float) -> float:
    """Factor de friccion de Darcy-Weisbach para el lado tubos."""
    if Re <= 0.0:
        raise ValueError("El numero de Reynolds debe ser positivo.")
    if Re < 2100.0:
        return 64.0 / Re
    # Correlacion explicita de Haaland (aproxima Colebrook-White para tubos rugosos)
    rug_rel = max(epsilon / D_i, 0.0)
    inv_sqrt_f = -1.8 * math.log10((rug_rel / 3.7) ** 1.11 + 6.9 / Re)
    return 1.0 / (inv_sqrt_f ** 2)


def caida_presion_tubos(Re: float, rho: float, v_t: float, L: float,
                        D_i: float, n_pasos: int, phi_t: float,
                        epsilon: float) -> Tuple[float, float]:
    """
    Caida de presion total en el lado tubos (Kern, 1950, Cap. 7, Eq. 7.43 y 7.45/7.46):
        dp_total = dp_friccion + dp_retorno
    donde:
        dp_friccion = n_pasos * f_t * (L / D_i) * (0.5 * rho * v_t^2) / phi_corr
        dp_retorno  = 4.0 * n_pasos * (0.5 * rho * v_t^2)
    (incluye 4 cabezas de velocidad por paso debido al giro en cabezales).
    Devuelve (dp_t [Pa], f_t [-]).
    """
    f_t = factor_friccion_tubos(Re, epsilon, D_i)
    exponente_m = 0.14 if Re >= 2100.0 else 0.25
    phi_corr = (phi_t ** (exponente_m / 0.14)) if phi_t > 0.0 else 1.0
    cabeza_dinamica = 0.5 * rho * (v_t ** 2)
    dp_friccion = n_pasos * f_t * (L / D_i) * cabeza_dinamica / phi_corr
    dp_retorno = 4.0 * n_pasos * cabeza_dinamica
    return dp_friccion + dp_retorno, f_t


def factor_friccion_coraza(Re_s: float) -> float:
    """
    Factor de friccion de Darcy equivalente para el lado coraza (Kern Fig. 29),
    adimensional: f = exp(0.576 - 0.19 ln Re).
    En regimen laminar profundo (Re_s < 400) empalma con ley hiperbolica laminar.
    """
    if Re_s <= 0.0:
        raise ValueError("Re_s debe ser positivo.")
    f_kern_400 = math.exp(0.576 - 0.19 * math.log(400.0))
    if Re_s < 400.0:
        return f_kern_400 * (400.0 / Re_s)
    return math.exp(0.576 - 0.19 * math.log(Re_s))


def caida_presion_coraza(Re_s: float, rho_s: float, G_s: float, D_s: float,
                         D_e: float, N_baffles: int, phi_s: float,
                         n_corazas: int = 1) -> Tuple[float, float]:
    """
    Caida de presion en lado coraza [Pa] (Kern, 1950, Cap. 7, Eq. 7.44):
        dp_s = n_corazas * f_s * G_s^2 * D_s * (N_baffles + 1) / (2 * rho_s * D_e * phi_s)
    donde:
        N_baffles = L / B - 1
        G_s = m_dot_s / A_s
    Devuelve (dp_s [Pa], f_s [-]).
    """
    f_s = factor_friccion_coraza(Re_s)
    dp_s = (n_corazas * f_s * (G_s ** 2) * D_s * (N_baffles + 1)
            / (2.0 * rho_s * D_e * max(phi_s, 1e-6)))
    return dp_s, f_s


def nusselt_coraza(Re: float, Pr: float, phi: float) -> float:
    """
    Correlacion de Kern para flujo cruzado en coraza con baffles segmentados al 25% (Kern, 1950, Eq. 7.4):
        Nu_s = 0.36 * Re_s^0.55 * Pr^(1/3) * phi_s
    donde Re_s = G_s * D_e / mu_s.
    """
    return 0.36 * Re ** 0.55 * Pr ** (1.0 / 3.0) * phi


def mu_pared(fluido: str, T_w: float) -> float:
    """Viscosidad a la temperatura de pared, acotada al rango valido del fluido."""
    T_min, T_max = db.get_limits(fluido, "C")
    T_w = min(max(T_w, T_min + 0.01), T_max - 0.01)
    return db.get_fluid_state(fluido, T_w, "C").mu


# Presion de saturacion del agua [bar] segun IAPWS-IF97. El core modela agua
# liquida hasta 180 C (servicio presurizado), por lo que el usuario debe saber
# que presion minima necesita para que no hierva dentro del equipo.
_P_SAT_AGUA = ((100.0, 1.013), (110.0, 1.433), (120.0, 1.985), (130.0, 2.701),
               (140.0, 3.615), (150.0, 4.762), (160.0, 6.182), (170.0, 7.922),
               (180.0, 10.028))
_ALIAS_AGUA = {"agua", "water", "h2o", "agua liquida"}


def presion_saturacion_agua(T: float) -> float:
    """
    Presion de saturacion del agua [bar] entre 100 y 180 C.

    Interpolacion lineal en ln(P) frente a T (la relacion de Clausius-Clapeyron
    es casi recta en esa forma): error < 0.5 % dentro del rango tabulado.
    """
    if T <= _P_SAT_AGUA[0][0]:
        return _P_SAT_AGUA[0][1]
    if T >= _P_SAT_AGUA[-1][0]:
        return _P_SAT_AGUA[-1][1]
    for (T1, P1), (T2, P2) in zip(_P_SAT_AGUA, _P_SAT_AGUA[1:]):
        if T1 <= T <= T2:
            f = (T - T1) / (T2 - T1)
            return math.exp(math.log(P1) + f * (math.log(P2) - math.log(P1)))
    return _P_SAT_AGUA[-1][1]   # inalcanzable, defensivo


def chequeo_saturacion(fluido: str, T_max_op: float) -> Optional[str]:
    """
    Advertencia (no error) si un liquido opera por encima de su ebullicion a
    1 atm: el calculo sigue siendo valido, pero exige presurizar el equipo.

    Devuelve None si no aplica. Solo el agua tiene tabla cargada; para los
    demas fluidos el rango declarado en el core ya acota la fase liquida.
    """
    if fluido.strip().lower() not in _ALIAS_AGUA or T_max_op <= 100.0:
        return None
    P_sat = presion_saturacion_agua(T_max_op)
    return (
        f"El agua alcanza {T_max_op:.1f} C: a 1 atm ya habria hervido. El equipo "
        f"debe operar por encima de ~{P_sat:.1f} bar (presion de saturacion) "
        "para mantenerla liquida; por debajo, el modelo monofasico de Kern "
        "deja de aplicar."
    )


def resistencia_ensuciamiento(corriente: Stream, R_f_metal: float) -> float:
    """
    Resistencia de ensuciamiento de UNA corriente [m2.K/W].
    Prioridad: dato del usuario > valor TEMA del fluido (parche 5.1) >
    mitad del R_f total del material (respaldo del parche 5.2.2).
    """
    if corriente.R_f is not None:
        if corriente.R_f < 0.0:
            raise ValueError(
                f"El factor de ensuciamiento de {corriente.fluido} no puede "
                f"ser negativo (R_f = {corriente.R_f:.3e} m2.K/W).")
        return corriente.R_f
    try:
        return db.get_fouling(corriente.fluido)
    except (KeyError, ValueError):
        return R_f_metal * 0.5


def coeficiente_global(h_i: float, h_o: float, D_i: float, D_o: float,
                       k_m: float, R_fi: float, R_fo: float) -> float:
    """
    Coeficiente global sucio U_o referido al area EXTERNA de los tubos:
        1 / U_o = 1 / h_o + R_fo + (D_o * ln(D_o / D_i)) / (2 * k_m) + (D_o / D_i) * R_fi + (D_o / D_i) * (1 / h_i)
    (Kern, 1950, Cap. 6, Eq. 6.11; estandares TEMA Clase C).
    """
    R_total = (D_o / (D_i * h_i)              # conveccion interna
               + R_fi * D_o / D_i             # ensuciamiento interno
               + D_o * math.log(D_o / D_i) / (2.0 * k_m)   # pared cilindrica
               + R_fo                         # ensuciamiento externo
               + 1.0 / h_o)                   # conveccion externa
    return 1.0 / R_total


# =============================================================================
# 4. ALGORITMO PRINCIPAL: ITERACION SOBRE U
# =============================================================================
def dimensionar(caliente: Stream, fria: Stream,
                tubos: TubeGeometry, coraza: ShellGeometry,
                lado_tubos: str = "frio",
                U_inicial: float = 700.0,
                tol: float = 1e-4,
                max_iter: int = 100) -> SizingResult:
    """
    Dimensiona un intercambiador de tubos y coraza por el Metodo de Kern (Kern, 1950, Cap. 7):
    Itera sobre el coeficiente global U acoplando transferencia y perdida de carga:
        1. Balance de energia: q = m_dot * cp * dT (Cap. 5).
        2. Area de flujo coraza: A_s = (D_s * C * B) / (P_T * n_corazas)  (Eq. 7.1, con C = P_T - D_o).
        3. Flujo en tubos: a_t = N_tt * a_tubo / n_pasos, u_m = m_dot / (rho * a_t).
        4. Velocidades masicas: G_s = m_dot_s / A_s, G_t = m_dot_t / a_t.
        5. Conveccion y caidas de presion: Nu_t (Eq. 6.2/6.3), Nu_s (Eq. 7.4), dp_t (Eq. 7.43), dp_s (Eq. 7.44).

    Parametros
    ----------
    caliente, fria : Stream   Corrientes (una con T_out = None).
    tubos, coraza  : geometria impuesta por el disenador.
    lado_tubos     : 'frio' o 'caliente' -> que corriente va por los tubos.
    U_inicial      : semilla del coeficiente global [W/m2.K].
    tol            : error relativo de U para declarar convergencia.
    """
    # --- 0. Validacion geometrica -------------------------------------------
    if tubos.D_i <= 0.0:
        raise ValueError(
            f"Espesor de pared ({tubos.espesor*1000:.2f} mm) mayor o igual al "
            f"radio del tubo: el diametro interno resulta {tubos.D_i*1000:.2f} mm."
        )
    if tubos.n_pasos not in _C_TP:
        raise ValueError(
            f"Numero de pasos por tubos no estandar: {tubos.n_pasos}. "
            f"Valores admitidos: {sorted(_C_TP)}."
        )
    C_L = _C_L[tubos.layout] if tubos.layout in _C_L else None
    if C_L is None:
        raise ValueError(
            f"Layout '{tubos.layout}' no reconocido. Use 30/60 (triangular) "
            "o 45/90 (cuadrado)."
        )
    C_TP = _C_TP[tubos.n_pasos]

    # Validacion dimensional contra entradas en milimetros por error de unidades:
    if not (0.003 <= tubos.D_o <= 0.150):
        raise ValueError(
            f"Diametro de tubo D_o = {tubos.D_o} m fuera de rango fisico [0.003, 0.150] m. "
            "Verifique que las dimensiones esten en METROS y no en milimetros."
        )
    if not (0.1 <= tubos.L <= 30.0) or not (0.01 <= coraza.B <= 10.0):
        raise ValueError(
            f"Longitud L = {tubos.L} m o espaciado B = {coraza.B} m fuera de rango en metros."
        )

    # Corazas efectivas: TEMA F (deflector longitudinal) se modela como 2 pasos
    # de coraza en serie (reduccion de F de Bowman y area de flujo por paso).
    n_corazas = 2 if coraza.tipo.upper() == "F" else 1

    adv: List[str] = []
    if tubos.PR < 1.25:
        adv.append(
            f"Pitch ratio P_T/D_o = {tubos.PR:.2f} < 1.25: TEMA exige al menos "
            "1.25 para poder limpiar mecanicamente y mandrilar el tubo."
        )

    # --- 1. Balance de energia ----------------------------------------------
    q, T_h_out, T_c_out = balance_energia(caliente, fria)
    T_h_m = 0.5 * (caliente.T_in + T_h_out)
    T_c_m = 0.5 * (fria.T_in + T_c_out)

    dT_lm = lmtd_contracorriente(caliente.T_in, T_h_out, fria.T_in, T_c_out)
    F = factor_correccion_F(caliente.T_in, T_h_out, fria.T_in, T_c_out,
                            tubos.n_pasos, n_corazas)
    if F < F_MIN_ACEPTABLE:
        adv.append(
            f"F = {F:.3f} < {F_MIN_ACEPTABLE}: el arreglo 1-{tubos.n_pasos} es "
            "muy sensible; cualquier desviacion termica lo inutiliza. Divida el "
            "servicio en varias corazas en serie."
        )

    # --- 2. Propiedades a la temperatura media de cada corriente ------------
    if lado_tubos not in ("frio", "caliente"):
        raise ValueError("lado_tubos debe ser 'frio' o 'caliente'.")
    por_tubos = fria if lado_tubos == "frio" else caliente
    por_coraza = caliente if lado_tubos == "frio" else fria
    T_t_m = T_c_m if lado_tubos == "frio" else T_h_m
    T_s_m = T_h_m if lado_tubos == "frio" else T_c_m

    est_t: FluidState = db.get_fluid_state(por_tubos.fluido, T_t_m, "C")
    est_s: FluidState = db.get_fluid_state(por_coraza.fluido, T_s_m, "C")
    metal = db.get_material(tubos.material)

    D_e = diametro_equivalente(tubos.P_T, tubos.D_o, tubos.layout)
    C_libre = tubos.P_T - tubos.D_o            # claro entre tubos [m]
    area_unit = math.pi * tubos.D_o * tubos.L  # area externa de 1 tubo [m2]

    # Factores de ensuciamiento individuales por corriente (no duplicar el del
    # metal): ver resistencia_ensuciamiento().
    R_fi = resistencia_ensuciamiento(por_tubos, metal.R_f)
    R_fo = resistencia_ensuciamiento(por_coraza, metal.R_f)

    def _refinar_h(Re_t: float, Re_s: float):
        """Refina T_w, phi_t y phi_s ANTES de evaluar U (punto fijo, 4 pasadas)."""
        phi_t = phi_s = 1.0
        for _ in range(4):
            Nu_t, reg = nusselt_tubos(Re_t, est_t.Pr, tubos.D_i, tubos.L, phi_t)
            h_i = Nu_t * est_t.k / tubos.D_i
            h_o = nusselt_coraza(Re_s, est_s.Pr, phi_s) * est_s.k / D_e
            h_io = h_i * tubos.D_i / tubos.D_o
            T_w = (h_io * T_t_m + h_o * T_s_m) / (h_io + h_o)
            phi_t = (est_t.mu / mu_pared(por_tubos.fluido, T_w)) ** 0.14
            phi_s = (est_s.mu / mu_pared(por_coraza.fluido, T_w)) ** 0.14
        # Ultimo (h_i, h_o) fue calculado con phi de la pasada previa: se
        # reevalua una vez con el phi final para que h y phi sean consistentes.
        Nu_t, reg = nusselt_tubos(Re_t, est_t.Pr, tubos.D_i, tubos.L, phi_t)
        h_i = Nu_t * est_t.k / tubos.D_i
        h_o = nusselt_coraza(Re_s, est_s.Pr, phi_s) * est_s.k / D_e
        return h_i, h_o, phi_t, phi_s, reg

    # --- 3-5. Lazo iterativo sobre U ----------------------------------------
    U = U_inicial
    phi_t = phi_s = 1.0
    h_i = h_o = Re_t = Re_s = v_t = v_s = N_tt_f = D_s = 0.0
    regimen = ""
    it = 0
    convergio = False

    for it in range(1, max_iter + 1):
        # 3. Area, numero de tubos y diametro de coraza
        A = q / (U * F * dT_lm)
        N_tt_f = A / area_unit
        # D_s despejado de N_tt = (pi/4)*(C_TP/C_L)*(D_s/P_T)^2 (equivale a
        # la constante 0.637 = 2/pi del texto original)
        D_s = (2.0 / math.pi) * math.sqrt(C_L / C_TP) * math.sqrt(
            A * (tubos.PR ** 2) * tubos.D_o / tubos.L)

        # 4a. Lado tubos: continuidad -> G_t -> Re
        a_t = N_tt_f * tubos.a_tubo / tubos.n_pasos      # area de flujo por paso
        G_t = por_tubos.m_dot / a_t                      # [kg/m2.s]
        v_t = G_t / est_t.rho
        Re_t = G_t * tubos.D_i / est_t.mu

        # 4b. Lado coraza: area de flujo cruzado (por coraza/paso en TEMA F)
        A_s = (D_s * C_libre * coraza.B / tubos.P_T) / n_corazas
        G_s = por_coraza.m_dot / A_s
        v_s = G_s / est_s.rho
        Re_s = G_s * D_e / est_s.mu

        # 5. h, phi (refinados) y nuevo U
        h_i, h_o, phi_t, phi_s, regimen = _refinar_h(Re_t, Re_s)
        U_new = coeficiente_global(h_i, h_o, tubos.D_i, tubos.D_o,
                                   metal.k_m, R_fi, R_fo)
        if not math.isfinite(U_new) or U_new <= 0.0:
            raise ValueError(
                "El coeficiente global calculado no es fisico "
                f"(U = {U_new:.3e} W/m2.K). Revise geometria y caudales.")
        error = abs(U_new - U) / U_new
        # Sub-relajacion (0.7) tras 5 ciclos: estabilidad cerca de transiciones
        U = 0.7 * U_new + 0.3 * U if it > 5 else U_new
        if error < tol:
            U = U_new
            convergio = True
            break

    if not convergio:
        raise ValueError(
            f"La iteracion sobre U no convergio en {max_iter} ciclos "
            f"(ultimo U = {U:.1f} W/m2.K).\n"
            "   Pruebe otra semilla U_inicial o revise la geometria impuesta.")

    # --- 6. Cierre consistente con N_tt entero y calculo hidraulico ---------
    A = q / (U * F * dT_lm)
    N_tt = max(int(math.ceil(A / area_unit)), tubos.n_pasos)
    if N_tt % tubos.n_pasos:                      # reparto equitativo por paso
        N_tt += tubos.n_pasos - (N_tt % tubos.n_pasos)
    A_real = N_tt * area_unit
    D_s = tubos.P_T * math.sqrt((4.0 / math.pi) * (C_L / C_TP) * N_tt)
    # floor + 1e-9 evita el truncamiento IEEE-754 (p. ej. 0.6/0.2 = 2.9999...)
    N_baffles = max(int(math.floor(tubos.L / coraza.B + 1e-9)) - 1, 0)

    # Recalcular velocidades, Re, h, U y caidas de presion para el haz REAL:
    a_t = N_tt * tubos.a_tubo / tubos.n_pasos
    G_t = por_tubos.m_dot / a_t
    v_t = G_t / est_t.rho
    Re_t = G_t * tubos.D_i / est_t.mu

    A_s = (D_s * C_libre * coraza.B / tubos.P_T) / n_corazas
    G_s = por_coraza.m_dot / A_s
    v_s = G_s / est_s.rho
    Re_s = G_s * D_e / est_s.mu

    h_i, h_o, phi_t, phi_s, regimen = _refinar_h(Re_t, Re_s)
    U = coeficiente_global(h_i, h_o, tubos.D_i, tubos.D_o, metal.k_m, R_fi, R_fo)

    dp_t, f_t = caida_presion_tubos(
        Re_t, est_t.rho, v_t, tubos.L, tubos.D_i, tubos.n_pasos, phi_t,
        metal.epsilon)
    dp_s, f_s = caida_presion_coraza(
        Re_s, est_s.rho, G_s, D_s, D_e, N_baffles, phi_s, n_corazas)

    # Area requerida con el U del haz instalado (coherente con A_real)
    A = q / (U * F * dT_lm)
    sobre_area = 100.0 * (A_real - A) / A
    if sobre_area < 0.0:
        adv.append(
            f"Tras redondear a {N_tt} tubos enteros la velocidad cae y el U "
            f"final deja un deficit de area de {-sobre_area:.1f} %. Aumente L "
            "o el numero de tubos.")

    # --- 7. Sanity checks hidrodinamicos y de fabricacion -------------------
    if v_t < V_TUBO_MIN:
        adv.append(
            f"Velocidad en tubos baja: {v_t:.2f} m/s (< {V_TUBO_MIN} m/s). "
            "Favorece el ensuciamiento y degrada h_i; considere mas pasos."
        )
    elif v_t > V_TUBO_MAX:
        adv.append(
            f"Velocidad en tubos excesiva: {v_t:.2f} m/s (> {V_TUBO_MAX} m/s). "
            "Riesgo de erosion y caida de presion elevada."
        )
    if v_s < V_CORAZA_MIN:
        adv.append(
            f"Velocidad en coraza baja: {v_s:.2f} m/s (< {V_CORAZA_MIN} m/s). "
            "Hay riesgo de estratificacion y zonas muertas; reduzca el "
            "espaciado de baffles B o el pitch."
        )
    elif v_s > V_CORAZA_MAX:
        adv.append(
            f"Velocidad en coraza excesiva: {v_s:.2f} m/s (> {V_CORAZA_MAX} m/s). "
            "Riesgo de vibracion inducida por flujo (TEMA)."
        )
    if regimen != "turbulento":
        adv.append(
            f"Flujo en tubos en regimen {regimen} (Re = {Re_t:,.0f}). "
            "La transferencia es ineficiente y la correlacion pierde precision."
        )
    if not RE_KERN_MIN <= Re_s <= RE_KERN_MAX:
        adv.append(
            f"Re de coraza = {Re_s:,.0f} fuera del rango de validez de la "
            f"correlacion de Kern ({RE_KERN_MIN:,.0f} - {RE_KERN_MAX:,.0f}). "
            "h_o es una extrapolacion."
        )
    for flu, T_pico in ((caliente.fluido, caliente.T_in),
                        (fria.fluido, T_c_out)):
        aviso = chequeo_saturacion(flu, T_pico)
        if aviso:
            adv.append(aviso)
    if not (D_s / 5.0) <= coraza.B <= D_s:
        adv.append(
            f"Espaciado de baffles B = {coraza.B:.3f} m fuera del rango TEMA "
            f"[D_s/5 = {D_s/5:.3f} m ; D_s = {D_s:.3f} m]."
        )
    if tubos.L / D_s > 15.0 or tubos.L / D_s < 3.0:
        adv.append(
            f"Relacion L/D_s = {tubos.L/D_s:.1f} fuera del rango practico 3 - 15. "
            "El equipo resulta desproporcionado para su fabricacion."
        )

    return SizingResult(
        q=q, U=U, A=A, A_real=A_real, sobre_area=sobre_area, N_tt=N_tt,
        D_s=D_s, N_baffles=N_baffles, LMTD=dT_lm, F=F,
        T_h_out=T_h_out, T_c_out=T_c_out, h_i=h_i, h_o=h_o,
        Re_t=Re_t, Re_s=Re_s, v_t=v_t, v_s=v_s, D_e=D_e,
        f_t=f_t, f_s=f_s, dp_t=dp_t, dp_s=dp_s,
        iteraciones=it, regimen_tubo=regimen, advertencias=adv,
    )


# =============================================================================
# 5. PRUEBA RAPIDA - CASO BASE DEL BENCHMARK
# =============================================================================
if __name__ == "__main__":
    agua = Stream(fluido="Agua", m_dot=2.5, T_in=15.0, T_out=85.0)
    glicol = Stream(fluido="Etilenglicol", m_dot=5.19, T_in=160.0, T_out=None)

    haz = TubeGeometry(D_o=0.0127, espesor=0.001651, P_T=0.024, L=2.0,
                       layout=60, n_pasos=2, material="Cobre")
    casco = ShellGeometry(B=0.25, tipo="E")

    r = dimensionar(caliente=glicol, fria=agua, tubos=haz, coraza=casco,
                    lado_tubos="frio", U_inicial=700.0)

    print("=" * 66)
    print(" SIZING KERN - Agua (tubos) / Etilenglicol (coraza)")
    print("=" * 66)
    print(f" Entrada : agua {agua.T_in:.0f} -> {agua.T_out:.0f} C  |  "
          f"glicol {glicol.T_in:.0f} -> {r.T_h_out:.2f} C")
    print(f" q       = {r.q/1000:,.2f} kW")
    print(f" LMTD    = {r.LMTD:.2f} C      F = {r.F:.4f}")
    print(f" U       = {r.U:.2f} W/m2.K   (convergido en {r.iteraciones} iteraciones)")
    print(f" A       = {r.A:.3f} m2       (instalada {r.A_real:.3f} m2, "
          f"+{r.sobre_area:.1f} %)")
    print(f" N_tt    = {r.N_tt} tubos     D_s = {r.D_s*1000:.1f} mm  "
          f"({r.N_baffles} baffles)")
    print("-" * 66)
    print(f" h_i = {r.h_i:,.1f} W/m2.K   Re_t = {r.Re_t:,.0f} ({r.regimen_tubo})"
          f"   v_t = {r.v_t:.2f} m/s")
    print(f" h_o = {r.h_o:,.1f} W/m2.K   Re_s = {r.Re_s:,.0f}"
          f"   v_s = {r.v_s:.2f} m/s   D_e = {r.D_e*1000:.1f} mm")
    if r.advertencias:
        print("-" * 66)
        print(" ADVERTENCIAS:")
        for a in r.advertencias:
            print(f"  [!] {a}")
    print("=" * 66)
