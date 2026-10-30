# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
"""
RATING TERMICO - Metodo de Kern (busqueda de raices sobre las temperaturas)
=============================================================================
La geometria ya existe y es INMUTABLE (N_tt, D_s, L, pitch, baffles). Solo se
conocen los caudales y las dos temperaturas de ENTRADA. El problema es evaluar
que desempeno entrega el equipo fuera de su punto de diseno.

Algoritmo (INSTRUCCIONES_THERMO.md, seccion 3):
    1. Se fija el area y las areas de flujo transversales (geometria dada).
    2. Se supone T_co; T_ho sale del balance de energia.
    3. Con esas temperaturas se evaluan propiedades, velocidades REALES por
       continuidad (G = m_dot / A_flujo) y el U riguroso de Kern.
    4. Se busca la raiz de  R(T_co) = q(T_co) - U*A*F*LMTD(T_co) = 0.
    5. Se detiene cuando el intervalo de temperatura es menor a la tolerancia.

R(T_co) es monotona creciente: al subir T_co el calor demandado q sube y la
LMTD disponible baja. Por eso basta un bracket [T_ci, limite termodinamico] y
un hibrido secante/biseccion, que converge siempre sin derivadas.

Aqui NUNCA se asume una velocidad: el area de flujo es un dato fijo, de modo
que la velocidad queda determinada por la conservacion de masa.
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

try:
    from src.core.errores import ErrorDiseno
    from src.core.thermo_data import FluidState, ThermoDatabase
except ImportError:  # ejecucion directa: `python src/thermo/rating.py`
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.core.errores import ErrorDiseno
    from src.core.thermo_data import FluidState, ThermoDatabase

from src.thermo.sizing import (
    INCERTIDUMBRE_U, RE_KERN_MAX, RE_KERN_MIN, V_CORAZA_MAX, V_CORAZA_MIN,
    V_TUBO_MAX, V_TUBO_MIN, ShellGeometry, Stream, TubeGeometry,
    aviso_tipo_carcasa, caida_presion_coraza, caida_presion_tubos,
    chequeo_cercania_fase, chequeo_saturacion, coeficiente_global,
    diametro_equivalente, factor_correccion_F, lmtd_contracorriente, mu_pared,
    nusselt_coraza, nusselt_tubos, resistencia_ensuciamiento,
    validar_temperatura,
)

db = ThermoDatabase()

F_MIN_ACEPTABLE = 0.75
EFECTIVIDAD_ALTA = 0.95     # Arriba de esto el equipo trabaja contra el pinch.


# =============================================================================
# 1. CONTENEDORES DE DATOS
# =============================================================================
@dataclass
class ExchangerGeometry:
    """Equipo ya construido: lo que entrega el sizing o una hoja de datos."""
    tubos: TubeGeometry
    coraza: ShellGeometry
    N_tt: int                # Numero total de tubos
    D_s: float               # Diametro interior de coraza [m]

    @property
    def A_o(self) -> float:
        """Area de transferencia externa instalada [m2]."""
        return self.N_tt * math.pi * self.tubos.D_o * self.tubos.L

    @property
    def a_flujo_tubos(self) -> float:
        """Area de flujo por paso de tubos [m2] (fija: define la velocidad)."""
        return self.N_tt * self.tubos.a_tubo / self.tubos.n_pasos

    @property
    def n_corazas(self) -> int:
        """Corazas efectivas para F y area de flujo (TEMA F -> 2, resto -> 1)."""
        return 2 if self.coraza.tipo.upper() == "F" else 1

    @property
    def a_flujo_coraza(self) -> float:
        """Area de flujo cruzado en el eje de la coraza [m2] (Kern)."""
        return (self.D_s * (self.tubos.P_T - self.tubos.D_o)
                * self.coraza.B / self.tubos.P_T) / self.n_corazas


@dataclass
class RatingResult:
    """Punto de operacion convergido del equipo existente."""
    q: float                 # Calor transferido real [W]
    U: float                 # Coef. global sucio referido a A_o [W/m2.K]
    A: float                 # Area instalada [m2]
    T_h_out: float
    T_c_out: float
    LMTD: float
    F: float
    efectividad: float       # q / q_max  [-]
    NTU: float
    C_r: float               # C_min / C_max
    h_i: float
    h_o: float
    Re_t: float
    Re_s: float
    v_t: float
    v_s: float
    D_e: float
    f_t: float               # Factor de friccion Darcy en tubos [-]
    f_s: float               # Factor de friccion Kern en coraza [-]
    dp_t: float              # Caida de presion lado tubos [Pa]
    dp_s: float              # Caida de presion lado coraza [Pa]
    iteraciones: int
    regimen_tubo: str
    regimen_coraza: str
    residual: float          # Cierre del balance |q - U*A*F*LMTD| [W]
    advertencias: List[str] = field(default_factory=list)


@dataclass
class _Punto:
    """Estado termohidraulico completo para un T_co supuesto (uso interno)."""
    T_c_out: float
    T_h_out: float
    q: float
    U: float
    LMTD: float
    F: float
    h_i: float
    h_o: float
    Re_t: float
    Re_s: float
    v_t: float
    v_s: float
    f_t: float
    f_s: float
    dp_t: float
    dp_s: float
    regimen: str
    regimen_s: str
    C_c: float
    C_h: float


# =============================================================================
# 2. BALANCE DE ENERGIA PARA UN T_co SUPUESTO
# =============================================================================
def _cierra_balance(caliente: Stream, fria: Stream, T_c_out: float,
                    tol: float = 1e-6, max_iter: int = 30
                    ) -> Tuple[float, float, float, float]:
    """
    Dado un T_co supuesto, devuelve (q, T_h_out, C_c, C_h).

    El cp depende de la temperatura media, que a su vez depende de la salida
    buscada: se resuelve por sustitucion sucesiva sobre T_h_out.
    """
    cp_c = db.get_fluid_state(fria.fluido,
                              0.5 * (fria.T_in + T_c_out), "C").cp
    C_c = fria.m_dot * cp_c
    q = C_c * (T_c_out - fria.T_in)

    T_h_out = caliente.T_in - 20.0
    C_h = 0.0
    for _ in range(max_iter):
        cp_h = db.get_fluid_state(caliente.fluido,
                                  0.5 * (caliente.T_in + T_h_out), "C").cp
        C_h = caliente.m_dot * cp_h
        nuevo = caliente.T_in - q / C_h
        if abs(nuevo - T_h_out) < tol:
            T_h_out = nuevo
            break
        T_h_out = nuevo
    return q, T_h_out, C_c, C_h


# =============================================================================
# 3. TERMOHIDRAULICA CON GEOMETRIA FIJA (VELOCIDAD POR CONTINUIDAD)
# =============================================================================
def _coeficientes(geom: ExchangerGeometry, por_tubos: Stream, por_coraza: Stream,
                  T_t_m: float, T_s_m: float, D_e: float,
                  tol: float = 1e-5, max_iter: int = 15
                  ) -> Tuple[float, float, float, float, float, float, float,
                             str, str, float, float, float, float]:
    """
    Coeficientes de pelicula y U para unas temperaturas medias dadas.

    La geometria es inmutable, asi que G = m_dot / A_flujo es la unica
    velocidad admisible (conservacion de masa). El lazo interno solo refina la
    correccion por viscosidad de pared (mu/mu_w)^0.14, que necesita conocer T_w.

    Devuelve (U, h_i, h_o, Re_t, Re_s, v_t, v_s, regimen, regimen_s,
              dp_t, dp_s, f_t, f_s).
    """
    est_t: FluidState = db.get_fluid_state(por_tubos.fluido, T_t_m, "C")
    est_s: FluidState = db.get_fluid_state(por_coraza.fluido, T_s_m, "C")
    metal = db.get_material(geom.tubos.material)
    tb = geom.tubos
    R_fi = resistencia_ensuciamiento(por_tubos, metal.R_f)
    R_fo = resistencia_ensuciamiento(por_coraza, metal.R_f)

    # --- Velocidades reales: impuestas por la continuidad, no por el disenador
    G_t = por_tubos.m_dot / geom.a_flujo_tubos
    v_t = G_t / est_t.rho
    Re_t = G_t * tb.D_i / est_t.mu

    G_s = por_coraza.m_dot / geom.a_flujo_coraza
    v_s = G_s / est_s.rho
    Re_s = G_s * D_e / est_s.mu

    phi_t = phi_s = 1.0
    U = h_i = h_o = 0.0
    regimen = regimen_s = ""
    for _ in range(40):
        Nu_t, regimen = nusselt_tubos(Re_t, est_t.Pr, tb.D_i, tb.L, phi_t,
                                 calentando=(T_t_m < T_s_m))
        Nu_s, regimen_s = nusselt_coraza(Re_s, est_s.Pr, phi_s, D_e,
                                         geom.coraza.B)
        h_i = Nu_t * est_t.k / tb.D_i
        h_o = Nu_s * est_s.k / D_e

        h_io = h_i * tb.D_i / tb.D_o
        T_w = (h_io * T_t_m + h_o * T_s_m) / (h_io + h_o)
        phi_t_n = (est_t.mu / mu_pared(por_tubos.fluido, T_w)) ** 0.14
        phi_s_n = (est_s.mu / mu_pared(por_coraza.fluido, T_w)) ** 0.14

        U_new = coeficiente_global(h_i, h_o, tb.D_i, tb.D_o,
                                   metal.k_m, R_fi, R_fo)
        if not math.isfinite(U_new) or U_new <= 0.0:
            raise ErrorDiseno(
                titulo="Coeficiente global no físico durante el rating",
                que_paso=f"El cálculo devolvió U = {U_new:.3e} W/m²·K.",
                por_que="U es el inverso de una suma de resistencias térmicas "
                        "positivas; no puede ser nulo ni negativo.",
                solucion="Revise la geometría cargada (N_tt, D_s, espesor de "
                         "pared) y los caudales.",
                referencia="U = 1/Σ R_térmicas (Kern, cap. 7)",
            )
        converge = (abs(U_new - U) / U_new < tol
                    and abs(phi_t_n - phi_t) < 1e-9
                    and abs(phi_s_n - phi_s) < 1e-9)
        U = U_new
        phi_t, phi_s = phi_t_n, phi_s_n
        if converge:
            break

    # Caídas de presión acopladas (Kern, cap. 7) con el mismo estado.
    N_baffles = max(int(math.floor(geom.tubos.L / geom.coraza.B + 1e-9)) - 1, 0)
    dp_t, f_t = caida_presion_tubos(
        Re_t, est_t.rho, v_t, tb.L, tb.D_i, tb.n_pasos, phi_t, metal.epsilon)
    dp_s, f_s = caida_presion_coraza(
        Re_s, est_s.rho, G_s, geom.D_s, D_e, N_baffles, phi_s, geom.n_corazas)
    return (U, h_i, h_o, Re_t, Re_s, v_t, v_s, regimen, regimen_s,
            dp_t, dp_s, f_t, f_s)


def _evaluar_punto(T_c_out: float, caliente: Stream, fria: Stream,
                   geom: ExchangerGeometry, lado_tubos: str,
                   D_e: float) -> _Punto:
    """Resuelve todo el estado del equipo para un T_co supuesto."""
    q, T_h_out, C_c, C_h = _cierra_balance(caliente, fria, T_c_out)
    T_h_m = 0.5 * (caliente.T_in + T_h_out)
    T_c_m = 0.5 * (fria.T_in + T_c_out)

    por_tubos = fria if lado_tubos == "frio" else caliente
    por_coraza = caliente if lado_tubos == "frio" else fria
    T_t_m = T_c_m if lado_tubos == "frio" else T_h_m
    T_s_m = T_h_m if lado_tubos == "frio" else T_c_m

    (U, h_i, h_o, Re_t, Re_s, v_t, v_s, regimen, regimen_s,
     dp_t, dp_s, f_t, f_s) = _coeficientes(
        geom, por_tubos, por_coraza, T_t_m, T_s_m, D_e)

    dT_lm = lmtd_contracorriente(caliente.T_in, T_h_out, fria.T_in, T_c_out)
    F = factor_correccion_F(caliente.T_in, T_h_out, fria.T_in, T_c_out,
                            geom.tubos.n_pasos, geom.coraza.tipo)
    return _Punto(T_c_out=T_c_out, T_h_out=T_h_out, q=q, U=U, LMTD=dT_lm, F=F,
                  h_i=h_i, h_o=h_o, Re_t=Re_t, Re_s=Re_s, v_t=v_t, v_s=v_s,
                  regimen=regimen, regimen_s=regimen_s, C_c=C_c, C_h=C_h,
                  f_t=f_t, f_s=f_s, dp_t=dp_t, dp_s=dp_s)


# =============================================================================
# 4. BUSQUEDA DE RAICES: HIBRIDO SECANTE / BISECCION
# =============================================================================
def _buscar_raiz(f: Callable[[float], float], lo: float, hi: float,
                 f_lo: float, f_hi: float, tol: float,
                 max_iter: int) -> Tuple[float, int]:
    """
    Raiz de f en [lo, hi] con f(lo) < 0 < f(hi).

    Se prueba el paso de la secante; si cae fuera del 95 % central del bracket
    se usa el punto medio. Asi se conserva la garantia de la biseccion con la
    velocidad de la secante. Criterio de parada: ancho del bracket < tol.
    """
    x = 0.5 * (lo + hi)
    for it in range(1, max_iter + 1):
        if hi - lo < tol:
            return x, it
        x = (lo * f_hi - hi * f_lo) / (f_hi - f_lo)       # secante
        margen = 0.025 * (hi - lo)
        if not (lo + margen) < x < (hi - margen):         # fuera de rango util
            x = 0.5 * (lo + hi)                           # biseccion segura
        fx = f(x)
        if fx == 0.0:
            return x, it
        if fx < 0.0:
            lo, f_lo = x, fx
        else:
            hi, f_hi = x, fx
    raise ErrorDiseno(
        titulo="La búsqueda de la temperatura de salida no convergió",
        que_paso=f"Tras {max_iter} iteraciones el intervalo restante es "
                 f"{hi - lo:.4f} °C, más ancho que la tolerancia pedida.",
        por_que="La función residual es muy plana o muy ruidosa en este caso "
                "(típico con regímenes laminares, donde U es muy sensible a la "
                "temperatura).",
        solucion="Aumente `max_iter` o relaje `tol_T`; si el flujo es "
                 "laminar, interprete el resultado con la banda de "
                 "incertidumbre que se reporta en las advertencias.",
        referencia="Búsqueda de raíces secante/bisección sobre T_c,out",
    )


# =============================================================================
# 5. ALGORITMO PRINCIPAL
# =============================================================================
def evaluar(caliente: Stream, fria: Stream, geom: ExchangerGeometry,
            lado_tubos: str = "frio", tol_T: float = 0.01,
            max_iter: int = 60) -> RatingResult:
    """
    Evalua (rating) un intercambiador existente en condiciones dadas.

    Parametros
    ----------
    caliente, fria : Stream   Solo se usan `fluido`, `m_dot` y `T_in`;
                              cualquier `T_out` cargado se ignora (es la
                              incognita que resuelve este modulo).
    geom           : ExchangerGeometry   Equipo fijo.
    lado_tubos     : 'frio' o 'caliente'.
    tol_T          : tolerancia en grados C sobre la temperatura de salida.
    """
    if lado_tubos not in ("frio", "caliente"):
        raise ValueError("lado_tubos debe ser 'frio' o 'caliente'.")
    if geom.N_tt < geom.tubos.n_pasos:
        raise ErrorDiseno(
            titulo="Geometría incoherente",
            que_paso=f"El equipo tiene {geom.N_tt} tubos repartidos en "
                     f"{geom.tubos.n_pasos} pasos.",
            por_que="Cada paso debe contener al menos un tubo; con menos tubos "
                    "que pasos el reparto es imposible.",
            solucion=f"Cargue al menos {geom.tubos.n_pasos} tubos o reduzca el "
                     "número de pasos por tubos.",
            referencia="Geometría del haz de tubos",
        )
    if caliente.T_in <= fria.T_in:
        raise ErrorDiseno(
            titulo="Violación de la 2.ª Ley de la Termodinámica",
            que_paso=f"El fluido «caliente» entra a {caliente.T_in:.1f} °C y el "
                     f"«frío» entra a {fria.T_in:.1f} °C.",
            por_que="El calor fluye espontáneamente solo de la zona más caliente "
                    "a la más fría: sin diferencia de temperatura motriz no hay "
                    "transferencia posible.",
            solucion="Revise qué corriente es cada una o corrija las "
                     "temperaturas de entrada.",
            referencia="Segunda Ley de la Termodinámica",
        )
    # Cada temperatura de ENTRADA debe caer en la ventana de su fluido.
    validar_temperatura(caliente.fluido, caliente.T_in,
                        "Temperatura de entrada del fluido caliente")
    validar_temperatura(fria.fluido, fria.T_in,
                        "Temperatura de entrada del fluido frío")

    adv: List[str] = []
    D_e = diametro_equivalente(geom.tubos.P_T, geom.tubos.D_o, geom.tubos.layout)
    A = geom.A_o
    dT_max = caliente.T_in - fria.T_in

    # --- Bracket superior: limite termodinamico + limite de fase del fluido --
    # Capacidades calorificas estimadas a las entradas (solo para el bracket).
    cp_c0 = db.get_fluid_state(fria.fluido, fria.T_in, "C").cp
    cp_h0 = db.get_fluid_state(caliente.fluido, caliente.T_in, "C").cp
    C_c0, C_h0 = fria.m_dot * cp_c0, caliente.m_dot * cp_h0
    # q_max = C_min * dT_max  =>  tope de T_co por 1a y 2a Ley.
    T_co_termo = fria.T_in + min(C_h0 / C_c0, 1.0) * dT_max
    T_max_frio = db.get_limits(fria.fluido, "C")[1]
    T_co_fase = T_max_frio - 1e-3

    hi = min(T_co_termo, T_co_fase) - 1e-3
    lo = fria.T_in + 1e-4
    if hi <= lo:
        raise ErrorDiseno(
            titulo="El fluido frío ya está al límite de su ventana",
            que_paso=f"«{fria.fluido}» no admite temperaturas por encima de "
                     f"{T_max_frio:.1f} °C en su fase actual y ya entra a "
                     f"{fria.T_in:.1f} °C.",
            por_que="Cualquier calor que reciba lo llevaría fuera del rango "
                    "donde existe como líquido/gas en el modelo.",
            solucion=f"Baje la temperatura de entrada del frío (máximo "
                     f"{T_max_frio:.1f} °C) o elija otro fluido.",
            referencia="src/core/thermo_data.py · ventana de validez por fluido",
        )

    # --- Residual R(T_co) = q - U*A*F*LMTD ----------------------------------
    cache: List[Optional[_Punto]] = [None]
    FUERA = 1.0e30   # valor finito grande: la secante no admite inf/inf

    def residual(T_co: float) -> float:
        try:
            p = _evaluar_punto(T_co, caliente, fria, geom, lado_tubos, D_e)
        except ValueError:
            # T_co inalcanzable para este arreglo (cruce de temperaturas o
            # limite del factor F): empuja la busqueda hacia abajo.
            return FUERA
        cache[0] = p
        return p.q - p.U * A * p.F * p.LMTD

    f_lo = residual(lo)
    f_hi = residual(hi)
    if f_lo > 0.0:
        raise ErrorDiseno(
            titulo="El balance de energía no cierra ni con calor nulo",
            que_paso=f"Incluso suponiendo T_c,salida ≈ {lo:.1f} °C (casi sin "
                     f"calor transferido) el residual sigue siendo positivo.",
            por_que="Las propiedades o los caudales cargados hacen que el lado "
                    "frío absorba más calor del que el equipo puede entregar "
                    "incluso en el límite inferior de la búsqueda.",
            solucion="Revise los caudales (kg/s) y las temperaturas de entrada: "
                     "el más sospechoso es un caudal frío demasiado pequeño.",
            referencia="q = ṁ·cp·ΔT vs. q = U·A·F·LMTD",
        )
    if f_hi < 0.0:
        # El equipo entregaria mas calor del que permite el tope del bracket.
        if hi < T_co_termo - 1e-3:
            raise ErrorDiseno(
                titulo=f"«{fria.fluido}» saldría fuera de su ventana de fase",
                que_paso=f"El equipo llevaría al fluido frío por encima de "
                         f"{T_max_frio:.1f} °C, donde deja de existir en esa "
                         f"fase (límite superior de su ventana).",
                por_que="El modelo de Kern de este programa es monofásico: no "
                        "describe ebullición ni condensación, por lo que se "
                        "niega a calcular fuera de la ventana del fluido.",
                solucion="Reduzca el caudal caliente, baje su temperatura de "
                         "entrada, o use un área menor (menos tubos / menor "
                         "longitud).",
                referencia="src/core/thermo_data.py · ventana de validez",
            )
        adv.append(
            "El equipo alcanza el limite termodinamico (efectividad ~ 1): "
            "sobra area y el resultado queda pegado al pinch."
        )
        punto = _evaluar_punto(hi, caliente, fria, geom, lado_tubos, D_e)
        it = 0
    else:
        T_sol, it = _buscar_raiz(residual, lo, hi, f_lo, f_hi, tol_T, max_iter)
        punto = cache[0] if (cache[0] and
                             abs(cache[0].T_c_out - T_sol) < 1e-9) else \
            _evaluar_punto(T_sol, caliente, fria, geom, lado_tubos, D_e)

    # La solucion tambien debe respetar la ventana de fase de AMBOS fluidos.
    validar_temperatura(caliente.fluido, punto.T_h_out,
                        "Temperatura de salida calculada del fluido caliente")
    validar_temperatura(fria.fluido, punto.T_c_out,
                        "Temperatura de salida calculada del fluido frío")

    # --- Metricas de desempeno (epsilon - NTU) ------------------------------
    C_min, C_max = min(punto.C_c, punto.C_h), max(punto.C_c, punto.C_h)
    efectividad = punto.q / (C_min * dT_max)
    NTU = punto.U * A / C_min
    residuo = abs(punto.q - punto.U * A * punto.F * punto.LMTD)

    # --- Sanity checks -------------------------------------------------------
    if punto.F < F_MIN_ACEPTABLE:
        adv.append(
            f"F = {punto.F:.3f} < {F_MIN_ACEPTABLE}: el arreglo "
            f"1-{geom.tubos.n_pasos} opera en zona inestable para este servicio."
        )
    if efectividad > EFECTIVIDAD_ALTA:
        adv.append(
            f"Efectividad = {efectividad*100:.1f} %: el equipo trabaja contra el "
            "pinch termico; la salida es muy sensible a cualquier ensuciamiento."
        )
    if punto.v_t < V_TUBO_MIN:
        adv.append(
            f"Velocidad en tubos baja: {punto.v_t:.2f} m/s (< {V_TUBO_MIN} m/s). "
            "Acelera el ensuciamiento y hunde h_i."
        )
    elif punto.v_t > V_TUBO_MAX:
        adv.append(
            f"Velocidad en tubos excesiva: {punto.v_t:.2f} m/s "
            f"(> {V_TUBO_MAX} m/s). Riesgo de erosion."
        )
    if punto.v_s < V_CORAZA_MIN:
        adv.append(
            f"Velocidad en coraza baja: {punto.v_s:.2f} m/s "
            f"(< {V_CORAZA_MIN} m/s). Riesgo de zonas muertas y bypass."
        )
    elif punto.v_s > V_CORAZA_MAX:
        adv.append(
            f"Velocidad en coraza excesiva: {punto.v_s:.2f} m/s "
            f"(> {V_CORAZA_MAX} m/s). Riesgo de vibracion inducida (TEMA)."
        )
    for flu, T_pico in ((caliente.fluido, caliente.T_in),
                        (fria.fluido, punto.T_c_out)):
        aviso = chequeo_cercania_fase(flu, T_pico)
        if aviso:
            adv.append(aviso)
        aviso = chequeo_saturacion(flu, T_pico)
        if aviso:
            adv.append(aviso)
    for lado, regimen_x, Re_x in (("tubos", punto.regimen, punto.Re_t),
                                  ("coraza", punto.regimen_s, punto.Re_s)):
        if regimen_x == "turbulento":
            continue
        adv.append(
            f"Flujo en {lado} en régimen {regimen_x} "
            f"(Re = {Re_x:,.0f}): el programa lo cubre con las correlaciones "
            "específicas para este régimen (Hausen y Gnielinski en tubos, "
            "Kern laminar con dependencia de Graetz en coraza); la dispersión "
            f"de U llega a ±{INCERTIDUMBRE_U[regimen_x]:.0f} %."
        )
    banda = max(INCERTIDUMBRE_U[punto.regimen], INCERTIDUMBRE_U[punto.regimen_s])
    if banda > 15.0:
        adv.append(
            f"Resultado U = {punto.U:,.1f} W/m²·K con banda de incertidumbre "
            f"estimada de ±{banda:.0f} % (régimen tubos: {punto.regimen}, "
            f"coraza: {punto.regimen_s}). En laminar/transición las "
            "correlaciones de Hausen y Gnielinski ya son las adecuadas, pero "
            "la dispersión sigue siendo mayor que en turbulento: contraste "
            "con Bell-Delaware o datos de servicio antes de tomar decisiones "
            "de diseño."
        )
    if punto.regimen_s == "turbulento" and not RE_KERN_MIN <= punto.Re_s <= RE_KERN_MAX:
        adv.append(
            f"Re de coraza = {punto.Re_s:,.0f} fuera del rango de la correlacion "
            f"de Kern ({RE_KERN_MIN:,.0f} - {RE_KERN_MAX:,.0f}): h_o extrapolado."
        )
    adv.extend(aviso_tipo_carcasa(geom.coraza.tipo))

    return RatingResult(
        q=punto.q, U=punto.U, A=A, T_h_out=punto.T_h_out, T_c_out=punto.T_c_out,
        LMTD=punto.LMTD, F=punto.F, efectividad=efectividad, NTU=NTU,
        C_r=C_min / C_max, h_i=punto.h_i, h_o=punto.h_o, Re_t=punto.Re_t,
        Re_s=punto.Re_s, v_t=punto.v_t, v_s=punto.v_s, D_e=D_e,
        f_t=punto.f_t, f_s=punto.f_s, dp_t=punto.dp_t, dp_s=punto.dp_s,
        iteraciones=it, regimen_tubo=punto.regimen,
        regimen_coraza=punto.regimen_s, residual=residuo,
        advertencias=adv,
    )


# =============================================================================
# 6. PRUEBA RAPIDA - ESCENARIO FUERA DE DISENO
# =============================================================================
if __name__ == "__main__":
    # Geometria congelada: la que entrego el sizing del caso base.
    haz = TubeGeometry(D_o=0.0127, espesor=0.001651, P_T=0.024, L=2.0,
                       layout=60, n_pasos=2, material="Cobre")
    equipo = ExchangerGeometry(tubos=haz, coraza=ShellGeometry(B=0.25, tipo="E"),
                               N_tt=780, D_s=0.7439)

    # Fuera de diseno: menos agua (2.0 vs 2.5 kg/s) y glicol mas frio (150 C).
    agua = Stream(fluido="Agua", m_dot=2.0, T_in=15.0)
    glicol = Stream(fluido="Etilenglicol", m_dot=5.19, T_in=150.0)

    r = evaluar(caliente=glicol, fria=agua, geom=equipo, lado_tubos="frio")

    print("=" * 66)
    print(" RATING KERN - Operacion fuera de diseno")
    print("=" * 66)
    print(f" Equipo  : {equipo.N_tt} tubos, L = {haz.L:.1f} m, "
          f"D_s = {equipo.D_s*1000:.1f} mm, A = {r.A:.2f} m2")
    print(f" Entradas: agua {agua.m_dot:.1f} kg/s @ {agua.T_in:.0f} C  |  "
          f"glicol {glicol.m_dot:.2f} kg/s @ {glicol.T_in:.0f} C")
    print("-" * 66)
    print(f" T_salida agua   (T_co) = {r.T_c_out:.2f} C")
    print(f" T_salida glicol (T_ho) = {r.T_h_out:.2f} C")
    print(f" q = {r.q/1000:,.2f} kW")
    print("-" * 66)
    print(f" U = {r.U:.2f} W/m2.K    LMTD = {r.LMTD:.2f} C    F = {r.F:.4f}")
    print(f" Efectividad = {r.efectividad*100:.1f} %   NTU = {r.NTU:.3f}   "
          f"C_r = {r.C_r:.3f}")
    print(f" h_i = {r.h_i:,.1f} W/m2.K  Re_t = {r.Re_t:,.0f} ({r.regimen_tubo})"
          f"  v_t = {r.v_t:.2f} m/s")
    print(f" h_o = {r.h_o:,.1f} W/m2.K  Re_s = {r.Re_s:,.0f}"
          f"  v_s = {r.v_s:.2f} m/s")
    print(f" Cierre del balance |q - U*A*F*LMTD| = {r.residual:.2f} W "
          f"({r.iteraciones} iteraciones)")
    if r.advertencias:
        print("-" * 66)
        print(" ADVERTENCIAS:")
        for a in r.advertencias:
            print(f"  [!] {a}")
    print("=" * 66)
