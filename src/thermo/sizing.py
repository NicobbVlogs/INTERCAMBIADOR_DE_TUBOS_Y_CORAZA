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
    from src.core.errores import ErrorDiseno
    from src.core.thermo_data import FluidState, ThermoDatabase
except ImportError:  # ejecucion directa: `python src/thermo/sizing.py`
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.core.errores import ErrorDiseno
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

# Tipos de coraza TEMA (Figura N-1.2 del estandar). El calculo termico de
# este modulo es monofasico y de una pasada por coraza; los tipos de flujo
# partido (G, H, J) y la caldera K se aproximan con el mismo modelo de Kern
# y se marcan con advertencia explicita (ver `aviso_tipo_carcasa`).
TEMA_CARCASAS = ("E", "F", "G", "H", "J", "K", "X")

# Incertidumbre tipica de U cuando el flujo NO es turbulento: Kern calibro sus
# correlaciones en regimen turbulento; fuera de el, la dispersion de las
# correlaciones laminar/transicion se traslada al coeficiente global.
INCERTIDUMBRE_U = {"turbulento": 15.0, "transicion": 25.0, "laminar": 40.0}


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
    regimen_coraza: str
    advertencias: List[str] = field(default_factory=list)


# =============================================================================
# 3. BLOQUES DE CALCULO ELEMENTALES
# =============================================================================
def validar_temperatura(fluido: str, T: float, descripcion: str) -> None:
    """
    Comprueba que UN punto de temperatura cae dentro de la ventana de validez
    del fluido (fase declarada en la base termofisica).

    Es la pieza que faltaba para que ninguna combinacion de temperaturas se
    cuele por la validacion de temperaturas MEDIAS: si un fluido entra a 95 C
    y sale a 45 C su media (70 C) parece valida, pero el punto de entrada ya
    esta fuera de rango. Aqui se valida cada punto, uno por uno.
    """
    T_min, T_max = db.get_limits(fluido, "C")
    if T_min <= T <= T_max:
        return
    raise ErrorDiseno(
        titulo=f"«{fluido}» fuera de su ventana de temperatura",
        que_paso=f"{descripcion} = {T:.1f} °C y el rango válido de «{fluido}» "
                 f"es {T_min:.0f} – {T_max:.0f} °C (fase líquida/gas declarada).",
        por_que="Las correlaciones termofísicas (cp, μ, k, ρ) están ajustadas "
                "solo dentro de ese rango. Fuera de él el fluido cambia de fase "
                "o deja de existir en esa fase, y extrapolar la correlación "
                "produce propiedades sin sentido físico.",
        solucion=f"Ajuste esa temperatura al intervalo {T_min:.0f} – "
                 f"{T_max:.0f} °C, o elija un fluido cuya ventana lo cubra "
                 "(el menú de la pestaña Design muestra la validez bajo cada "
                 "fluido).",
        referencia="src/core/thermo_data.py · ventana de validez por fluido",
    )


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
        raise ErrorDiseno(
            titulo="Balance de energía mal planteado",
            que_paso="Se han indicado las DOS temperaturas de salida, o ninguna "
                     "de las dos (debe quedar exactamente una vacía).",
            por_que="El calor intercambiado es q = ṁ·cp·ΔT en cada lado. Si las "
                    "cuatro temperaturas son datos, el sistema está sobre-"
                    "especificado y dos balances distintos se contradecirían.",
            solucion="Deje VACÍA una de las dos casillas de «T salida» (la "
                     "incógnita que usted quiere que el programa calcule) y "
                     "deje la otra con su valor.",
            referencia="q = ṁ·cp·ΔT (balance de energía)",
        )
    if caliente.T_in <= fria.T_in:
        raise ErrorDiseno(
            titulo="Violación de la 2.ª Ley de la Termodinámica",
            que_paso=f"El fluido «caliente» entra a {caliente.T_in:.1f} °C y el "
                     f"«frío» entra a {fria.T_in:.1f} °C.",
            por_que="El calor fluye espontáneamente solo de la zona más caliente "
                    "a la más fría. Si el llamado «caliente» entra más frío que "
                    "el «frío», no existe fuerza motriz térmica alguna.",
            solucion="Revise qué corriente es cada una: cambie los fluidos de "
                     "lado (o sus temperaturas de entrada) de modo que la "
                     "corriente caliente entre a mayor temperatura.",
            referencia="Segunda Ley de la Termodinámica",
        )

    # --- Validacion de los puntos de temperatura CONOCIDOS, uno por uno ------
    validar_temperatura(caliente.fluido, caliente.T_in, "Temperatura de entrada del fluido caliente")
    validar_temperatura(fria.fluido, fria.T_in, "Temperatura de entrada del fluido frío")

    # Lado con las dos temperaturas conocidas -> fija la carga termica q.
    conocida, buscada = (fria, caliente) if caliente.T_out is None else (caliente, fria)
    if conocida.T_out is not None:
        if conocida is caliente and conocida.T_out > conocida.T_in:
            raise ErrorDiseno(
                titulo="El fluido «caliente» se estaría calentando",
                que_paso=f"La corriente caliente entra a {conocida.T_in:.1f} °C y "
                         f"se pide que salga a {conocida.T_out:.1f} °C (más caliente).",
                por_que="En un intercambiador la corriente caliente CIEDE calor; "
                        "su salida no puede estar por encima de su entrada.",
                solucion="Corrija la temperatura de salida del lado caliente "
                         "(debe ser menor que la de entrada) o canjee las "
                         "corrientes de lado.",
                referencia="Balance de energía del lado caliente",
            )
        if conocida is fria and conocida.T_out < conocida.T_in:
            raise ErrorDiseno(
                titulo="El fluido «frío» se estaría enfriando",
                que_paso=f"La corriente fría entra a {conocida.T_in:.1f} °C y se "
                         f"pide que salga a {conocida.T_out:.1f} °C (más fría).",
                por_que="En un intercambiador la corriente fría GANA calor; su "
                        "salida no puede estar por debajo de su entrada.",
                solucion="Corrija la temperatura de salida del lado frío (debe "
                         "ser mayor que la de entrada) o canjee las corrientes.",
                referencia="Balance de energía del lado frío",
            )
        validar_temperatura(conocida.fluido, conocida.T_out,
                            "Temperatura de salida del fluido "
                            + ("caliente" if conocida is caliente else "frío"))
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

    # La temperatura CALCULADA tambien debe caer en la ventana de su fluido:
    # es el punto donde suelen aparecer los excesos (p. ej. etanol > 75 C).
    validar_temperatura(buscada.fluido, T_h_out if buscada is caliente else T_c_out,
                        "Temperatura de salida calculada del fluido "
                        + ("caliente" if buscada is caliente else "frío"))

    if T_h_out <= fria.T_in:
        raise ErrorDiseno(
            titulo="Cruce de temperaturas imposible",
            que_paso=f"El fluido caliente saldría a {T_h_out:.1f} °C, por debajo "
                     f"de la entrada del fluido frío ({fria.T_in:.1f} °C).",
            por_que="Eso implicaría transferir calor hacia una zona más caliente "
                    "en el extremo frío del equipo: violaría la 2.ª Ley en "
                    "contracorriente.",
            solucion=f"Reduzca la carga térmica, aumente el caudal caliente o "
                     f"baje la temperatura de entrada del frío hasta que "
                     f"T_h,salida > {fria.T_in:.1f} °C.",
            referencia="LMTD en contracorriente: ΔT₂ = T_h,out − T_c,in > 0",
        )
    if T_c_out >= caliente.T_in:
        raise ErrorDiseno(
            titulo="Cruce de temperaturas imposible",
            que_paso=f"El fluido frío saldría a {T_c_out:.1f} °C, por encima de "
                     f"la entrada del fluido caliente ({caliente.T_in:.1f} °C).",
            por_que="El fluido frío no puede superar la temperatura que lo está "
                    "calentando: la diferencia de temperatura motriz llegaría a "
                    "ser negativa.",
            solucion=f"Reduzca la carga térmica o aumente el caudal frío hasta "
                     f"que T_c,salida < {caliente.T_in:.1f} °C.",
            referencia="LMTD en contracorriente: ΔT₁ = T_h,in − T_c,out > 0",
        )
    return q, T_h_out, T_c_out


def lmtd_contracorriente(T_h_in: float, T_h_out: float,
                         T_c_in: float, T_c_out: float) -> float:
    """Diferencia media logaritmica de temperatura para flujo a contracorriente."""
    dT1 = T_h_in - T_c_out
    dT2 = T_h_out - T_c_in
    if dT1 <= 0.0 or dT2 <= 0.0:
        raise ErrorDiseno(
            titulo="LMTD indefinida (cruce de temperaturas)",
            que_paso=f"Las diferencias de temperatura en los extremos son "
                     f"ΔT₁ = {dT1:.2f} °C y ΔT₂ = {dT2:.2f} °C; al menos una es "
                     f"negativa o nula.",
            por_que="La media logarítmica solo existe cuando ambas diferencias "
                    "extremas son positivas. Un signo negativo significa que las "
                    "curvas de temperatura se cruzan dentro del equipo.",
            solucion="Revise el balance térmico: reduzca la carga o modifique "
                     "las temperaturas de entrada hasta que ninguna diferencia "
                    "extrema sea negativa.",
            referencia="LMTD = (ΔT₁ − ΔT₂)/ln(ΔT₁/ΔT₂)",
        )
    if abs(dT1 - dT2) < 1e-9:
        return dT1
    return (dT1 - dT2) / math.log(dT1 / dT2)


def factor_correccion_F(T_h_in: float, T_h_out: float,
                        T_c_in: float, T_c_out: float,
                        n_pasos: int, tipo_carcasa: str = "E") -> float:
    """
    Factor de correccion F de Bowman, segun el tipo de coraza TEMA (Fig. N-1.2).

    E          : 1 pasada por coraza   -> F de Bowman 1-n (o F = 1 con 1 paso).
    F          : 2 pasadas por coraza en serie -> se reduce el P por pasada y
                 se aplica la misma expresion 1-2 a cada pasada.
    G, H, J    : flujo partido/dividido -> cada rama trabaja casi en
                 contracorriente, F = 1 (aproximacion conservadora usual).
    K          : caldera (lado coraza isotermico en ebullicion) -> F = 1.
    X          : flujo cruzado puro, una pasada -> F = 1.
    """
    tipo = tipo_carcasa.upper()
    if tipo not in TEMA_CARCASAS:
        raise ErrorDiseno(
            titulo=f"Tipo de coraza TEMA «{tipo}» desconocido",
            que_paso=f"Se pidió el tipo de coraza «{tipo}».",
            por_que="La Figura N-1.2 del estándar TEMA solo define los tipos "
                    f"{', '.join(TEMA_CARCASAS)}.",
            solucion=f"Seleccione uno de: {', '.join(TEMA_CARCASAS)}.",
            referencia="TEMA, Figura N-1.2 (Table of TEMA types)",
        )
    if n_pasos == 1 or tipo in ("G", "H", "J", "K", "X"):
        # Contracorriente puro, flujo partido o cruzado: sin penalizacion 1-2.
        return 1.0

    P = (T_c_out - T_c_in) / (T_h_in - T_c_in)
    R = (T_h_in - T_h_out) / (T_c_out - T_c_in)

    Ns = 2 if tipo == "F" else 1          # pasadas por coraza en serie
    if Ns > 1:
        # P efectivo por pasada de coraza (Kern/Bowman: pasadas identicas).
        base = ((1.0 - P * R) / (1.0 - P)) ** (1.0 / Ns)
        if abs(R - base) < 1e-9:
            base = R - 1e-9               # evita 0/0 en el caso degenerado
        P = (1.0 - base) / (R - base)

    raiz = math.sqrt(R * R + 1.0)
    arg_den = 2.0 / P - 1.0 - R
    num_ln = arg_den + raiz
    den_ln = arg_den - raiz
    if den_ln <= 0.0 or num_ln <= 0.0:
        raise ErrorDiseno(
            titulo="Arreglo termodinámicamente imposible",
            que_paso=f"El arreglo {Ns}-{n_pasos} no puede realizarse con "
                     f"P = {P:.3f} y R = {R:.3f}: el factor de corrección F no "
                     f"existe.",
            por_que="La solución de las temperaturas exige que las corrientes se "
                    "crucen más allá de lo que permite el patrón de flujo de "
                    "este arreglo (el F de Bowman se hace negativo o infinito).",
            solucion="Use más pasos por coraza (o por tubos), divida el servicio "
                     "en varias corazas en serie, o un intercambiador en "
                     "contracorriente puro (1 paso por tubos).",
            referencia="Factor F de Bowman (LMTD corregido)",
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

    BANDAS DE MEZCLA: al cruzar Re = 2100 o Re = 1e4 las correlaciones se
    diferencian ~10-14 %, y ese salto se traslada a U y lo hace oscilar en la
    iteracion. En dos franjas estrechas se mezclan las ramas adyacentes en
    escala logaritmica, de modo que Nu(Re) queda CONTINUA sin alterar las
    formulas clasicas fuera de las franjas.
    """
    def _laminar() -> float:
        return max(1.86 * (Re * Pr * D_i / L) ** (1.0 / 3.0) * phi, 3.66)

    def _hausen() -> float:
        return max(0.116 * (Re ** (2.0 / 3.0) - 125.0) * Pr ** (1.0 / 3.0)
                   * (1.0 + (D_i / L) ** (2.0 / 3.0)) * phi, 3.66)

    def _turbulento() -> float:
        return 0.023 * Re ** 0.8 * Pr ** (1.0 / 3.0) * phi

    def _mezcla(nu_a: float, nu_b: float, w: float) -> float:
        return math.exp((1.0 - w) * math.log(max(nu_a, 1e-12))
                        + w * math.log(max(nu_b, 1e-12)))

    if Re < 1900.0:
        return _laminar(), "laminar"
    if Re < 2300.0:                       # banda laminar -> Hausen
        w = (Re - 1900.0) / 400.0
        return _mezcla(_laminar(), _hausen(), w), "laminar"
    if Re < 8000.0:
        return _hausen(), "transicion"
    if Re < 1.2e4:                        # banda Hausen -> turbulento
        w = (Re - 8000.0) / 4000.0
        return _mezcla(_hausen(), _turbulento(), w), "transicion"
    return _turbulento(), "turbulento"


def nusselt_coraza(Re: float, Pr: float, phi: float,
                   D_e: Optional[float] = None,
                   L_b: Optional[float] = None) -> Tuple[float, str]:
    """
    Correlacion de Kern para el lado coraza con baffles segmentados al 25 %.
    Devuelve (Nu, regimen).

    Re >= 2e3      : Kern turbulento, Nu = 0.36 Re^0.55 Pr^(1/3) phi.
    Re < 100       : Kern laminar,  Nu = 1.72 (Re Pr D_e/L_b)^(1/3) phi,
                     con piso Nu = 3.66 (pared isotermica).
    100 <= Re < 2e3: transicion - interpolacion log-log entre ambas ramas
                     (ninguna de las dos correlaciones es valida ahi).

    La rama laminar SIEMPRE requiere D_e y L_b (espaciado de baffles): en
    laminar el desarrollo termico depende de la longitud del canal de flujo
    cruzado, no solo del Reynolds. Sin esos datos se degrada al piso Nu = 3.66.
    """
    if Re >= 2.0e3:
        return 0.36 * Re ** 0.55 * Pr ** (1.0 / 3.0) * phi, "turbulento"

    def _laminar(Re_x: float) -> float:
        if D_e is None or L_b is None or L_b <= 0.0:
            return 3.66
        return max(1.72 * (Re_x * Pr * D_e / L_b) ** (1.0 / 3.0) * phi, 3.66)

    if Re < 100.0:
        return _laminar(Re), "laminar"

    # Transicion 100 - 2000: interpolacion log-log entre ramas extremas.
    lam_100 = max(_laminar(100.0), 1e-12)
    turb_2000 = max(0.36 * (2.0e3) ** 0.55 * Pr ** (1.0 / 3.0) * phi, 1e-12)
    w = math.log(Re / 100.0) / math.log(2000.0 / 100.0)
    Nu = math.exp((1.0 - w) * math.log(lam_100) + w * math.log(turb_2000))
    return Nu, "transicion"


def mu_pared(fluido: str, T_w: float) -> float:
    """Viscosidad a la temperatura de pared, acotada al rango valido del fluido."""
    T_min, T_max = db.get_limits(fluido, "C")
    T_w = min(max(T_w, T_min + 0.01), T_max - 0.01)
    return db.get_fluid_state(fluido, T_w, "C").mu


# Advertencia (no error) si un liquido opera demasiado cerca del extremo de su
# ventana de validez: el calculo sigue siendo valido, pero la minima
# perturbacion del proceso lo sacaria del modelo monofasico.
MARGEN_FASE = 5.0   # C


def chequeo_cercania_fase(fluido: str, T_pico: float,
                          margen: float = MARGEN_FASE) -> Optional[str]:
    """
    Devuelve una advertencia si T_pico esta a menos de `margen` grados del
    limite superior de la ventana del fluido, o None si no aplica.

    Ejemplo tipico: agua con un pico a 97 C, a 3 C de su ebullicion a 1 atm.
    """
    try:
        _, T_max = db.get_limits(fluido, "C")
    except ValueError:
        return None
    if T_pico <= T_max - margen:
        return None
    return (
        f"El pico de temperatura de «{fluido}» es {T_pico:.1f} °C: solo "
        f"{T_max - T_pico:.1f} °C por debajo del límite de su ventana "
        f"({T_max:.0f} °C, donde cambia de fase a 1 atm). Cualquier "
        "perturbación del proceso lo sacaría del modelo monofásico de Kern."
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
                max_iter: int = 100,
                holgura_haz: float = 0.0) -> SizingResult:
    """
    Dimensiona un intercambiador de tubos y coraza por el Metodo de Kern.

    Parametros
    ----------
    caliente, fria : Stream   Corrientes (una con T_out = None).
    tubos, coraza  : geometria impuesta por el disenador.
    lado_tubos     : 'frio' o 'caliente' -> que corriente va por los tubos.
    U_inicial      : semilla del coeficiente global [W/m2.K].
    tol            : error relativo de U para declarar convergencia.
    holgura_haz    : holgura diametral haz-coraza que exige el cabezal trasero
                     TEMA elegido (HOLGURA_HAZ en src/mechanical/design.py).
                     La correlacion de conteo de tubos da el diametro del HAZ;
                     la coraza debe ser mas ancha en esa holgura. Si se deja en
                     0, el resultado subestima D_s con cabezales flotantes.
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
    if holgura_haz < 0.0:
        raise ErrorDiseno(
            titulo="Holgura haz-coraza negativa",
            que_paso=f"holgura_haz = {holgura_haz:.4f} m.",
            por_que="La holgura diametral entre el haz y la coraza es una "
                    "consecuencia del tipo de cabezal trasero TEMA y no puede "
                    "ser negativa.",
            solucion="No cargue la holgura a mano: se toma del tipo de "
                     "cabezal trasero elegido en el formulario.",
            referencia="TEMA, Figura N-1.2 · holguras típicas Bell-Delaware",
        )
    if holgura_haz > 0.05:
        adv.append(
            f"Holgura haz–coraza grande ({holgura_haz*1000:.0f} mm, típica de "
            "cabezales flotantes extraíbles tipo T): el bypass de fluido por "
            "el claro carcasa–haz puede degradar h_o. El método de Kern no lo "
            "modela; en un diseño real verifíquelo con Bell–Delaware."
        )

    # --- 1. Balance de energia ----------------------------------------------
    q, T_h_out, T_c_out = balance_energia(caliente, fria)
    T_h_m = 0.5 * (caliente.T_in + T_h_out)
    T_c_m = 0.5 * (fria.T_in + T_c_out)

    dT_lm = lmtd_contracorriente(caliente.T_in, T_h_out, fria.T_in, T_c_out)
    F = factor_correccion_F(caliente.T_in, T_h_out, fria.T_in, T_c_out,
                            tubos.n_pasos, coraza.tipo)
    if coraza.tipo.upper() not in TEMA_CARCASAS:
        raise ErrorDiseno(
            titulo=f"Tipo de coraza TEMA «{coraza.tipo}» desconocido",
            que_paso=f"Se pidió el tipo de coraza «{coraza.tipo}».",
            por_que="La Figura N-1.2 del estándar TEMA solo define los tipos "
                    f"{', '.join(TEMA_CARCASAS)}.",
            solucion=f"Seleccione uno de: {', '.join(TEMA_CARCASAS)}.",
            referencia="TEMA, Figura N-1.2 (Table of TEMA types)",
        )
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

    # --- 3-5. Lazo sobre U: U = U_calc(U) resuelto por biseccion -------------
    # Por que biseccion y no iteracion directa: el area sale de A = q/(U·F·LMTD)
    # y luego U depende de las velocidades que ese area impone, de modo que
    # U_calc(U) ~ C·U^beta con beta < 1. La iteracion directa converge lento y
    # su punto final depende de la semilla U_inicial (sobre todo en laminar).
    # La ecuacion U_calc(U) - U = 0 tiene una unica raiz en un bracket amplio:
    # resolverla por biseccion da el MISMO resultado con cualquier semilla y
    # con un residuo numerico controlado.
    estado: dict = {}

    def U_de(U_trial: float) -> float:
        """U_calc(U_trial): geometria -> Re, Nu -> h -> U, con phi de pared."""
        A_t = q / (U_trial * F * dT_lm)
        N_tt_f = A_t / area_unit
        # La correlacion de conteo da el diametro del HAZ; la coraza se abre
        # ademas en la holgura que exige el cabezal trasero (D_otl + holgura).
        D_s_t = holgura_haz + 0.637 * math.sqrt(C_L / C_TP) * math.sqrt(
            A_t * tubos.PR ** 2 * tubos.D_o / tubos.L)

        # 4a. Lado tubos: continuidad -> G_t -> Re -> Nu -> h_i
        a_t = N_tt_f * tubos.a_tubo / tubos.n_pasos      # area de flujo por paso
        G_t = por_tubos.m_dot / a_t                      # [kg/m2.s]
        v_t = G_t / est_t.rho
        Re_t = G_t * tubos.D_i / est_t.mu

        # 4b. Lado coraza: area de flujo cruzado en el eje -> G_s -> Re -> h_o
        A_s = D_s_t * C_libre * coraza.B / tubos.P_T
        G_s = por_coraza.m_dot / A_s
        v_s = G_s / est_s.rho
        Re_s = G_s * D_e / est_s.mu

        # 5. Correccion por viscosidad de pared (lazo interno acotado y
        #    determinista: se repite hasta que phi deja de moverse).
        phi_t = phi_s = 1.0
        Nu_t, regimen = nusselt_tubos(Re_t, est_t.Pr, tubos.D_i, tubos.L, phi_t)
        Nu_s, regimen_s = nusselt_coraza(Re_s, est_s.Pr, phi_s, D_e, coraza.B)
        h_i = h_o = 0.0
        for _ in range(40):
            Nu_t, regimen = nusselt_tubos(Re_t, est_t.Pr, tubos.D_i, tubos.L,
                                          phi_t)
            Nu_s, regimen_s = nusselt_coraza(Re_s, est_s.Pr, phi_s, D_e,
                                             coraza.B)
            h_i = Nu_t * est_t.k / tubos.D_i
            h_o = Nu_s * est_s.k / D_e
            h_io = h_i * tubos.D_i / tubos.D_o
            T_w = (h_io * T_t_m + h_o * T_s_m) / (h_io + h_o)
            phi_t_n = (est_t.mu / mu_pared(por_tubos.fluido, T_w)) ** 0.14
            phi_s_n = (est_s.mu / mu_pared(por_coraza.fluido, T_w)) ** 0.14
            if abs(phi_t_n - phi_t) < 1e-9 and abs(phi_s_n - phi_s) < 1e-9:
                phi_t, phi_s = phi_t_n, phi_s_n
                break
            phi_t, phi_s = phi_t_n, phi_s_n

        U_new = coeficiente_global(h_i, h_o, tubos.D_i, tubos.D_o,
                                   metal.k_m, metal.R_f, metal.R_f)
        if not math.isfinite(U_new) or U_new <= 0.0:
            raise ErrorDiseno(
                titulo="Coeficiente global no físico",
                que_paso=f"El cálculo devolvió U = {U_new:.3e} W/m²·K.",
                por_que="U es el inverso de una suma de resistencias térmicas "
                        "positivas; no puede ser nulo, negativo ni infinito. "
                        "Un valor así solo sale de geometría degenerada "
                        "(área de flujo nula, diámetros iguales, etc.).",
                solucion="Revise el espesor de pared del tubo (debe ser menor "
                         "que el radio), el pitch y los caudales cargados.",
                referencia="U = 1/Σ R_térmicas (Kern, cap. 7)",
            )
        estado.update(D_s=D_s_t, N_tt_f=N_tt_f, v_t=v_t, v_s=v_s,
                      Re_t=Re_t, Re_s=Re_s, h_i=h_i, h_o=h_o,
                      regimen=regimen, regimen_s=regimen_s)
        return U_new

    # Bracket de la raiz de R(U) = U_calc(U) - U  (R > 0 abajo, R < 0 arriba).
    # El bracket es FIJO (no depende de U_inicial) para que el resultado
    # convergido sea exactamente el mismo con cualquier semilla.
    U_lo, U_hi = 1.0, 5.0e3
    if U_de(U_lo) - U_lo < 0.0:
        raise ErrorDiseno(
            titulo="No existe un coeficiente global físico para este servicio",
            que_paso="Incluso con U → 0 el área requerida no produce un "
                     "coeficiente global coherente.",
            por_que="La combinación de caudales, temperaturas y geometría impone "
                    "condiciones extremas (velocidades ínfimas o Re fuera de "
                    "todo rango) para las que el modelo de Kern no tiene "
                    "solución.",
            solucion="Aumente los caudales, reduzca la longitud del tubo o "
                     "revise las temperaturas cargadas.",
            referencia="Método de Kern (iteración sobre U)",
        )
    while U_de(U_hi) - U_hi > 0.0 and U_hi < 1.0e7:
        U_hi *= 2.0

    U = U_inicial
    it = 0
    convergio = False
    for it in range(1, max_iter + 1):
        U_med = 0.5 * (U_lo + U_hi)
        R_med = U_de(U_med) - U_med
        if R_med > 0.0:
            U_lo = U_med
        else:
            U_hi = U_med
        U = U_med
        if (U_hi - U_lo) <= tol * max(U_med, 1.0):
            convergio = True
            break

    if not convergio:
        raise ErrorDiseno(
            titulo="La iteración sobre U no convergió",
            que_paso=f"Tras {max_iter} ciclos el intervalo de búsqueda sigue "
                     f"siendo [{U_lo:.1f}, {U_hi:.1f}] W/m²·K.",
            por_que="La tolerancia pedida sobre U es más fina de lo que el "
                    "modelo permite con este número de iteraciones.",
            solucion="Aumente el máximo de iteraciones o relaje la tolerancia "
                     "(el parámetro `tol`); revise también la geometría impuesta.",
            referencia="Método de Kern (iteración sobre U)",
        )

    # Estado final exacto con el U convergido.
    U = U_de(U)

    # --- 6. Cierre: area final y conteo entero de tubos ---------------------
    A = q / (U * F * dT_lm)
    N_tt = max(int(math.ceil(A / area_unit)), tubos.n_pasos)
    if N_tt % tubos.n_pasos:                      # reparto equitativo por paso
        N_tt += tubos.n_pasos - N_tt % tubos.n_pasos
    A_real = N_tt * area_unit
    sobre_area = 100.0 * (A_real - A) / A
    N_baffles = max(int(tubos.L / coraza.B) - 1, 0)

    D_s = estado["D_s"]
    v_t, v_s = estado["v_t"], estado["v_s"]
    Re_t, Re_s = estado["Re_t"], estado["Re_s"]
    h_i, h_o = estado["h_i"], estado["h_o"]
    regimen, regimen_s = estado["regimen"], estado["regimen_s"]

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

    # --- Regimen de flujo e incertidumbre de los coeficientes ---------------
    for lado, regimen_x, Re_x in (("tubos", regimen, Re_t),
                                  ("coraza", regimen_s, Re_s)):
        if regimen_x == "turbulento":
            continue
        adv.append(
            f"Flujo en {lado} en régimen {regimen_x} (Re = {Re_x:,.0f}). "
            "Las correlaciones de Kern están calibradas para flujo turbulento: "
            f"en {regimen_x} la incertidumbre de los coeficientes puede llegar a "
            f"±{INCERTIDUMBRE_U[regimen_x]:.0f} % sobre U."
        )
    banda = max(INCERTIDUMBRE_U[regimen], INCERTIDUMBRE_U[regimen_s])
    if banda > 15.0:
        adv.append(
            f"Resultado U = {U:,.1f} W/m²·K con banda de incertidumbre estimada "
            f"de ±{banda:.0f} % (régimen tubos: {regimen}, coraza: {regimen_s}). "
            "En laminar/transición el método de Kern es indicativo: contraste "
            "con Bell-Delaware, ε-NTU o datos de servicio antes de fabricar."
        )

    if not RE_KERN_MIN <= Re_s <= RE_KERN_MAX and regimen_s == "turbulento":
        adv.append(
            f"Re de coraza = {Re_s:,.0f} fuera del rango de validez de la "
            f"correlacion de Kern ({RE_KERN_MIN:,.0f} - {RE_KERN_MAX:,.0f}). "
            "h_o es una extrapolacion."
        )
    for flu, T_pico in ((caliente.fluido, caliente.T_in),
                        (fria.fluido, T_c_out)):
        aviso = chequeo_cercania_fase(flu, T_pico)
        if aviso:
            adv.append(aviso)

    # --- Tipos de coraza TEMA con limitaciones del modelo monofasico --------
    adv.extend(aviso_tipo_carcasa(coraza.tipo))

    if not (D_s / 5.0) <= coraza.B <= D_s:
        adv.append(
            f"Espaciado de baffles B = {coraza.B:.3f} m fuera del rango TEMA "
            f"[D_s/5 = {D_s/5:.3f} m ; D_s = {D_s:.3f} m] (RCB-4.5.1)."
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
        iteraciones=it, regimen_tubo=regimen, regimen_coraza=regimen_s,
        advertencias=adv,
    )


def aviso_tipo_carcasa(tipo: str) -> List[str]:
    """
    Advertencias propias de cada tipo de coraza TEMA (Fig. N-1.2) cuando el
    modelo monofasico de Kern solo lo aproxima.
    """
    tipo = tipo.upper()
    avisos = []
    if tipo == "F":
        avisos.append(
            "Coraza tipo F (dos pasadas con deflector longitudinal): el "
            "deflector longitudinal debe ir sellado o soldado; la caída de "
            "presión del lado coraza será unas 8 veces la de una coraza E."
        )
    elif tipo in ("G", "H", "J"):
        avisos.append(
            f"Coraza tipo {tipo} (flujo partido/dividido): Kern no calibró sus "
            "correlaciones para este patrón. La corrección F = 1 es "
            "conservadora y la caída de presión es mucho menor que en una E; "
            "para un diseño real use análisis de corrientes (Bell-Delaware)."
        )
    elif tipo == "K":
        avisos.append(
            "Coraza tipo K (caldera): el cálculo es monofásico. Para servicio "
            "de ebullición (recalentador de caldera) el haz se dimensiona con "
            "los métodos de vaporización (Kern cap. 9 / Bell-Delaware), y el "
            "diámetro de la caldera depende de la separación de vapor, no del "
            "haz. Los resultados aquí son solo la parte sensible."
        )
    elif tipo == "X":
        avisos.append(
            "Coraza tipo X (flujo cruzado puro): no hay deflectores "
            "transversales, solo placas soporte. La correlación de coraza de "
            "Kern es para baffles segmentados; h_o es una aproximación."
        )
    return avisos


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
