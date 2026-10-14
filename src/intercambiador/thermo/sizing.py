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
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from intercambiador.core.thermo_data import FluidState, ThermoDatabase

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
    iteraciones: int
    regimen_tubo: str
    advertencias: List[str] = field(default_factory=list)


# =============================================================================
# 3. BLOQUES DE CALCULO ELEMENTALES
# =============================================================================
def balance_energia(caliente: Stream, fria: Stream,
                    tol: float = 1e-4, max_iter: int = 50
                    ) -> Tuple[float, float, float]:
    """
    Balance de energia puro: q = m*cp*dT en ambos lados.

    Exactamente una de las dos temperaturas de salida debe ser desconocida.
    Como cp depende de la T media (que depende de la salida buscada), se
    resuelve por sustitucion sucesiva.

    Devuelve (q [W], T_h_out [C], T_c_out [C]).
    """
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

    # Lado con las dos temperaturas conocidas -> fija la carga termica q.
    conocida, buscada = (fria, caliente) if caliente.T_out is None else (caliente, fria)
    cp_k = db.get_fluid_state(conocida.fluido,
                              0.5 * (conocida.T_in + conocida.T_out), "C").cp
    q = abs(conocida.m_dot * cp_k * (conocida.T_out - conocida.T_in))

    # Sustitucion sucesiva sobre la salida desconocida (cp = f(T_media)).
    signo = -1.0 if buscada is caliente else 1.0
    T_out = buscada.T_in + signo * 20.0
    for _ in range(max_iter):
        cp_b = db.get_fluid_state(buscada.fluido,
                                  0.5 * (buscada.T_in + T_out), "C").cp
        nuevo = buscada.T_in + signo * q / (buscada.m_dot * cp_b)
        if abs(nuevo - T_out) < tol:
            T_out = nuevo
            break
        T_out = nuevo

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
    """Diferencia media logaritmica de temperatura para flujo a contracorriente."""
    dT1 = T_h_in - T_c_out
    dT2 = T_h_out - T_c_in
    if dT1 <= 0.0 or dT2 <= 0.0:
        raise ValueError(
            "LMTD indefinida: existe un cruce de temperaturas "
            f"(dT1 = {dT1:.2f} C, dT2 = {dT2:.2f} C). Revise el balance termico."
        )
    if abs(dT1 - dT2) < 1e-9:
        return dT1
    return (dT1 - dT2) / math.log(dT1 / dT2)


def factor_correccion_F(T_h_in: float, T_h_out: float,
                        T_c_in: float, T_c_out: float,
                        n_pasos: int) -> float:
    """
    Factor de correccion F de Bowman para 1 paso por coraza y n pasos por tubos.

    Con 1 paso por tubos el flujo es contracorriente puro => F = 1.
    Para n par se usa la expresion clasica 1-2 (Kern la aplica a 1-2n).
    """
    if n_pasos == 1:
        return 1.0

    P = (T_c_out - T_c_in) / (T_h_in - T_c_in)
    R = (T_h_in - T_h_out) / (T_c_out - T_c_in)
    raiz = math.sqrt(R * R + 1.0)

    arg_den = 2.0 / P - 1.0 - R
    num_ln = arg_den + raiz
    den_ln = arg_den - raiz
    if den_ln <= 0.0 or num_ln <= 0.0:
        raise ValueError(
            f"Arreglo 1-{n_pasos} termodinamicamente imposible para este servicio "
            f"(P = {P:.3f}, R = {R:.3f}).\n"
            "   Use mas pasos por coraza o un intercambiador en contracorriente puro."
        )
    log_term = math.log(num_ln / den_ln)

    if abs(R - 1.0) < 1e-6:
        return P * raiz / ((1.0 - P) * log_term)
    return (raiz / (R - 1.0)) * math.log((1.0 - P) / (1.0 - P * R)) / log_term


def diametro_equivalente(P_T: float, D_o: float, layout: int) -> float:
    """
    Diametro equivalente de Kern para el lado coraza (basado en el perimetro
    mojado de transferencia de calor, NO en el perimetro hidraulico completo).
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
    Nusselt interno de tubos. Devuelve (Nu, regimen).

    Re >= 1e4        : Sieder-Tate turbulento.
    2100 <= Re < 1e4 : Hausen (transicion).
    Re < 2100        : Sieder-Tate laminar, con piso Nu = 3.66 (T_w constante).
    """
    if Re >= 1.0e4:
        return 0.023 * Re ** 0.8 * Pr ** (1.0 / 3.0) * phi, "turbulento"
    if Re >= 2100.0:
        Nu = (0.116 * (Re ** (2.0 / 3.0) - 125.0) * Pr ** (1.0 / 3.0)
              * (1.0 + (D_i / L) ** (2.0 / 3.0)) * phi)
        return max(Nu, 3.66), "transicion"
    Nu = 1.86 * (Re * Pr * D_i / L) ** (1.0 / 3.0) * phi
    return max(Nu, 3.66), "laminar"


def nusselt_coraza(Re: float, Pr: float, phi: float) -> float:
    """Correlacion de Kern para el lado coraza con baffles segmentados al 25 %."""
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


def coeficiente_global(h_i: float, h_o: float, D_i: float, D_o: float,
                       k_m: float, R_fi: float, R_fo: float) -> float:
    """Coeficiente global sucio U_o referido al area EXTERNA de los tubos."""
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
    Dimensiona un intercambiador de tubos y coraza por el Metodo de Kern.

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
                            tubos.n_pasos)
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
        # D_s despejado de N_tt = 0.785*(C_TP/C_L)*D_s^2/(PR^2*D_o^2)
        D_s = 0.637 * math.sqrt(C_L / C_TP) * math.sqrt(
            A * tubos.PR ** 2 * tubos.D_o / tubos.L)

        # 4a. Lado tubos: continuidad -> G_t -> Re -> Nu -> h_i
        a_t = N_tt_f * tubos.a_tubo / tubos.n_pasos      # area de flujo por paso
        G_t = por_tubos.m_dot / a_t                      # [kg/m2.s]
        v_t = G_t / est_t.rho
        Re_t = G_t * tubos.D_i / est_t.mu
        Nu_t, regimen = nusselt_tubos(Re_t, est_t.Pr, tubos.D_i, tubos.L, phi_t)
        h_i = Nu_t * est_t.k / tubos.D_i

        # 4b. Lado coraza: area de flujo cruzado en el eje -> G_s -> Re -> h_o
        A_s = D_s * C_libre * coraza.B / tubos.P_T
        G_s = por_coraza.m_dot / A_s
        v_s = G_s / est_s.rho
        Re_s = G_s * D_e / est_s.mu
        h_o = nusselt_coraza(Re_s, est_s.Pr, phi_s) * est_s.k / D_e

        # 5. Correccion por viscosidad de pared y nuevo U
        h_io = h_i * tubos.D_i / tubos.D_o
        T_w = (h_io * T_t_m + h_o * T_s_m) / (h_io + h_o)
        phi_t = (est_t.mu / mu_pared(por_tubos.fluido, T_w)) ** 0.14
        phi_s = (est_s.mu / mu_pared(por_coraza.fluido, T_w)) ** 0.14

        U_new = coeficiente_global(h_i, h_o, tubos.D_i, tubos.D_o,
                                   metal.k_m, metal.R_f, metal.R_f)
        if not math.isfinite(U_new) or U_new <= 0.0:
            raise ValueError(
                "El coeficiente global calculado no es fisico "
                f"(U = {U_new:.3e} W/m2.K). Revise geometria y caudales."
            )
        error = abs(U_new - U) / U_new
        U = U_new
        if error < tol:
            convergio = True
            break

    if not convergio:
        raise ValueError(
            f"La iteracion sobre U no convergio en {max_iter} ciclos "
            f"(ultimo U = {U:.1f} W/m2.K).\n"
            "   Pruebe otra semilla U_inicial o revise la geometria impuesta."
        )

    # --- 6. Cierre: area final y conteo entero de tubos ---------------------
    A = q / (U * F * dT_lm)
    N_tt = max(int(math.ceil(A / area_unit)), tubos.n_pasos)
    if N_tt % tubos.n_pasos:                      # reparto equitativo por paso
        N_tt += tubos.n_pasos - N_tt % tubos.n_pasos
    A_real = N_tt * area_unit
    sobre_area = 100.0 * (A_real - A) / A
    N_baffles = max(int(tubos.L / coraza.B) - 1, 0)

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
