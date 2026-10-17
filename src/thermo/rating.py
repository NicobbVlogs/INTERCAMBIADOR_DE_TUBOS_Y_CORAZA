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
    from src.core.thermo_data import FluidState, ThermoDatabase
except ImportError:  # ejecucion directa: `python src/thermo/rating.py`
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.core.thermo_data import FluidState, ThermoDatabase

from src.thermo.sizing import (
    RE_KERN_MAX, RE_KERN_MIN, V_CORAZA_MAX, V_CORAZA_MIN, V_TUBO_MAX,
    V_TUBO_MIN, ShellGeometry, Stream, TubeGeometry, chequeo_saturacion,
    coeficiente_global, diametro_equivalente, factor_correccion_F,
    lmtd_contracorriente, mu_pared, nusselt_coraza, nusselt_tubos,
    resistencia_ensuciamiento,
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
    iteraciones: int
    regimen_tubo: str
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
    regimen: str
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
                  ) -> Tuple[float, float, float, float, float, float, float, str]:
    """
    Coeficientes de pelicula y U para unas temperaturas medias dadas.

    La geometria es inmutable, asi que G = m_dot / A_flujo es la unica
    velocidad admisible (conservacion de masa). El lazo interno solo refina la
    correccion por viscosidad de pared (mu/mu_w)^0.14, que necesita conocer T_w.

    Devuelve (U, h_i, h_o, Re_t, Re_s, v_t, v_s, regimen).
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
    regimen = ""
    for _ in range(max_iter):
        Nu_t, regimen = nusselt_tubos(Re_t, est_t.Pr, tb.D_i, tb.L, phi_t)
        h_i = Nu_t * est_t.k / tb.D_i
        h_o = nusselt_coraza(Re_s, est_s.Pr, phi_s) * est_s.k / D_e

        h_io = h_i * tb.D_i / tb.D_o
        T_w = (h_io * T_t_m + h_o * T_s_m) / (h_io + h_o)
        phi_t = (est_t.mu / mu_pared(por_tubos.fluido, T_w)) ** 0.14
        phi_s = (est_s.mu / mu_pared(por_coraza.fluido, T_w)) ** 0.14

        U_new = coeficiente_global(h_i, h_o, tb.D_i, tb.D_o,
                                   metal.k_m, R_fi, R_fo)
        if not math.isfinite(U_new) or U_new <= 0.0:
            raise ValueError(
                f"Coeficiente global no fisico (U = {U_new:.3e} W/m2.K) durante "
                "el rating. Revise la geometria cargada."
            )
        convergio = abs(U_new - U) / U_new < tol
        U = U_new
        if convergio:
            break
    return U, h_i, h_o, Re_t, Re_s, v_t, v_s, regimen


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

    U, h_i, h_o, Re_t, Re_s, v_t, v_s, regimen = _coeficientes(
        geom, por_tubos, por_coraza, T_t_m, T_s_m, D_e)

    dT_lm = lmtd_contracorriente(caliente.T_in, T_h_out, fria.T_in, T_c_out)
    F = factor_correccion_F(caliente.T_in, T_h_out, fria.T_in, T_c_out,
                            geom.tubos.n_pasos, geom.n_corazas)
    return _Punto(T_c_out=T_c_out, T_h_out=T_h_out, q=q, U=U, LMTD=dT_lm, F=F,
                  h_i=h_i, h_o=h_o, Re_t=Re_t, Re_s=Re_s, v_t=v_t, v_s=v_s,
                  regimen=regimen, C_c=C_c, C_h=C_h)


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
    raise ValueError(
        f"La busqueda de T_salida no convergio en {max_iter} iteraciones "
        f"(intervalo final {hi - lo:.4f} C). Revise los datos de entrada."
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
        raise ValueError(
            f"Geometria incoherente: {geom.N_tt} tubos para "
            f"{geom.tubos.n_pasos} pasos."
        )
    if caliente.T_in <= fria.T_in:
        raise ValueError(
            "Violacion de la 2a Ley: el fluido 'caliente' entra a "
            f"{caliente.T_in:.1f} C y el 'frio' a {fria.T_in:.1f} C.\n"
            "   Sin diferencia de temperatura motriz no hay transferencia."
        )

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
        raise ValueError(
            f"El fluido frio ({fria.fluido}) no admite temperaturas por encima "
            f"de {T_max_frio:.1f} C en esta fase, y ya entra a {fria.T_in:.1f} C."
        )

    # --- Residual R(T_co) = q - U*A*F*LMTD ----------------------------------
    cache: List[Optional[_Punto]] = [None]

    def residual(T_co: float) -> float:
        try:
            p = _evaluar_punto(T_co, caliente, fria, geom, lado_tubos, D_e)
        except ValueError:
            # T_co inalcanzable para este arreglo (cruce de temperaturas o
            # limite del factor F): empuja la busqueda hacia abajo.
            return float("inf")
        cache[0] = p
        return p.q - p.U * A * p.F * p.LMTD

    f_lo = residual(lo)
    f_hi = residual(hi)
    if f_lo > 0.0:
        raise ValueError(
            "Residual positivo en el limite inferior: el balance de energia no "
            "cierra ni con calor nulo. Revise caudales y temperaturas."
        )
    if f_hi < 0.0:
        # El equipo entregaria mas calor del que permite el tope del bracket.
        if hi < T_co_termo - 1e-3:
            raise ValueError(
                f"El equipo llevaria al {fria.fluido} por encima de "
                f"{T_max_frio:.1f} C, donde cambia de fase.\n"
                "   El modelo de Kern monofasico no aplica: reduzca el caudal "
                "caliente, su temperatura de entrada, o use un area menor."
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
        aviso = chequeo_saturacion(flu, T_pico)
        if aviso:
            adv.append(aviso)
    if punto.regimen != "turbulento":
        adv.append(
            f"Flujo en tubos en regimen {punto.regimen} "
            f"(Re = {punto.Re_t:,.0f}): transferencia pobre."
        )
    if not RE_KERN_MIN <= punto.Re_s <= RE_KERN_MAX:
        adv.append(
            f"Re de coraza = {punto.Re_s:,.0f} fuera del rango de la correlacion "
            f"de Kern ({RE_KERN_MIN:,.0f} - {RE_KERN_MAX:,.0f}): h_o extrapolado."
        )

    return RatingResult(
        q=punto.q, U=punto.U, A=A, T_h_out=punto.T_h_out, T_c_out=punto.T_c_out,
        LMTD=punto.LMTD, F=punto.F, efectividad=efectividad, NTU=NTU,
        C_r=C_min / C_max, h_i=punto.h_i, h_o=punto.h_o, Re_t=punto.Re_t,
        Re_s=punto.Re_s, v_t=punto.v_t, v_s=punto.v_s, D_e=D_e,
        iteraciones=it, regimen_tubo=punto.regimen, residual=residuo,
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
