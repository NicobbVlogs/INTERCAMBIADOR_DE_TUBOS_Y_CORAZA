"""
DISENO MECANICO - Estandar TEMA Clase "C" (+ ASME VIII Div. 1 para espesores)
=============================================================================
Recibe la geometria termica resuelta por `src/thermo/sizing.py` (D_s, N_tt, L,
d_o, pitch) y devuelve las dimensiones de fabricacion del equipo:

    carcasa  ->  espesor T_s y diametro externo D_o
    haz      ->  limites de tubos D_otl / D_ctl
    espejos  ->  espesor L_ts
    baffles  ->  numero N_B, espesor, corte y diametro de la placa
    boquillas->  diametro interior minimo (criterio de vibracion rho*V^2)
    bridas   ->  ancho f_w, diametro exterior D_F, circulo y numero de pernos
    cabezal  ->  espesor de cubierta T_c (plana o toriesferica)

Referencias:
    TEMA 9th ed., secciones RCB-3 (carcasa), RCB-4 (baffles y soportes),
    RCB-7 (espejos), RCB-11 (bridas/pernos) y RCB-4.61 (rho*V^2 en boquillas).
    ASME BPVC Seccion VIII Div. 1: UG-27 (cilindros), UG-32 (cabezas
    toriesfericas), UG-34 (cubiertas planas).
    Tan & Fok (2006), ecuaciones 19-32 de dimensionamiento mecanico.

NOTA SOBRE LAS TABLAS: los valores tabulados marcados con "[TEMA~]" son los
valores tipicos de Clase "C" usados en la practica docente. Para un diseno
certificado deben verificarse contra la edicion vigente del estandar.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# =============================================================================
# 1. CONSTANTES Y TABLAS TEMA / ASME
# =============================================================================
IN = 0.0254  # 1 pulgada en metros

# TEMA RCB-4.61: para fluidos monofasicos no corrosivos ni abrasivos el
# producto rho*V^2 en la boquilla no debe superar 1500 lbm/(ft*s^2).
# Conversion exacta a SI: 1500 * 0.45359237 / 0.3048 = 2232.25 Pa.
#   ->  V_ns_max = sqrt(RHO_V2_MAX / rho_s)
# (El criterio se escribe a veces como "2250/sqrt(rho)"; esa forma NO es
#  dimensionalmente consistente y da velocidades de ~68 m/s en liquidos.)
RHO_V2_MAX = 1500.0 * 0.45359237 / 0.3048   # 2232.25 Pa (NO 3348.6 Pa)
V_BOQUILLA_MAX_PRACTICO = 3.0  # m/s, tope practico para liquidos (erosion)
V_BOQUILLA_MIN_PRACTICO = 0.9  # m/s, debajo de esto la boquilla queda enorme

# Esfuerzo admisible S [Pa] a temperatura moderada (<= 150 C) [valores tipicos]
S_ADMISIBLE: Dict[str, float] = {
    "Acero al carbono": 138.0e6,   # SA-516 Gr.70
    "Acero inoxidable 304": 115.0e6,
    "Acero inoxidable 316": 115.0e6,
    "Cobre": 46.0e6,               # C12200 recocido
    "Laton Almirantazgo": 55.0e6,
}

# Espesor minimo de carcasa por diametro, Clase "C" [TEMA~ RCB-3.13], en metros
_T_MIN_CARCASA: List[Tuple[float, float]] = [
    # (D_s maximo [m], espesor minimo [m])
    (0.330, 3.2e-3),    # hasta 13 in  -> tuberia comercial
    (0.610, 4.8e-3),    # 13 - 24 in   -> 3/16 in
    (0.760, 6.4e-3),    # 24 - 30 in   -> 1/4 in
    (1.000, 7.9e-3),    # 30 - 39 in   -> 5/16 in
    (1.520, 9.5e-3),    # 39 - 60 in   -> 3/8 in
    (9.999, 11.1e-3),   # > 60 in      -> 7/16 in
]

# Holgura diametral carcasa-baffle [TEMA~ RCB-4.3], en metros
_HOLGURA_BAFFLE: List[Tuple[float, float]] = [
    (0.432, 2.54e-3),   # hasta 17 in -> 0.100 in
    (1.000, 3.18e-3),   # 18 - 39 in  -> 0.125 in
    (1.380, 3.81e-3),   # 40 - 54 in  -> 0.150 in
    (9.999, 4.45e-3),   # > 54 in     -> 0.175 in
]

# Espesor de baffle segun D_s y luz sin soporte [TEMA~ RCB-4.41], en metros.
# Clave: D_s maximo [m]; valor: espesores para tramos sin soporte de
# [< 0.61 m, < 0.91 m, < 1.22 m, < 1.52 m, >= 1.52 m]
_ESPESOR_BAFFLE: List[Tuple[float, Tuple[float, ...]]] = [
    (0.350, (3.2e-3, 4.8e-3, 6.4e-3, 9.5e-3, 9.5e-3)),
    (0.435, (4.8e-3, 6.4e-3, 9.5e-3, 11.1e-3, 12.7e-3)),
    (0.585, (6.4e-3, 9.5e-3, 11.1e-3, 12.7e-3, 15.9e-3)),
    (0.990, (6.4e-3, 9.5e-3, 12.7e-3, 15.9e-3, 15.9e-3)),
    (1.370, (7.9e-3, 12.7e-3, 15.9e-3, 15.9e-3, 19.1e-3)),
    (9.999, (9.5e-3, 12.7e-3, 15.9e-3, 19.1e-3, 19.1e-3)),
]
_LUZ_BAFFLE_LIMITES = (0.61, 0.91, 1.22, 1.52)  # m

# Maxima luz sin soporte de tubos, materiales grupo A (acero) [TEMA~ RCB-4.52]
# Clave: diametro exterior del tubo [m] -> luz maxima [m]
_LUZ_MAX_TUBO: Dict[float, float] = {
    0.00635: 0.660,   # 1/4 in
    0.00953: 0.889,   # 3/8 in
    0.01270: 1.118,   # 1/2 in
    0.01588: 1.321,   # 5/8 in
    0.01905: 1.524,   # 3/4 in
    0.02223: 1.727,   # 7/8 in
    0.02540: 1.880,   # 1 in
    0.03175: 2.235,   # 1-1/4 in
    0.03810: 2.540,   # 1-1/2 in
    0.05080: 3.175,   # 2 in
}

# Holgura diametral carcasa - limite exterior del haz (D_s - D_otl), en metros.
# Depende del tipo de cabezal trasero TEMA [valores tipicos Bell-Delaware].
_HOLGURA_HAZ: Dict[str, float] = {
    "L": 0.011, "M": 0.011, "N": 0.011,   # espejo fijo
    "U": 0.015,                            # haz en U
    "W": 0.015,                            # anillo linterna empaquetado
    "P": 0.038,                            # cabezal flotante empaquetado
    "S": 0.045,                            # cabezal flotante con anillo partido
    "T": 0.092,                            # cabezal flotante extraible
}

# Tuberia comercial Schedule 40: NPS -> (diametro interior, exterior) [m]
_NPS_SCH40: List[Tuple[str, float, float]] = [
    ('1"', 0.02664, 0.03340),
    ('1-1/4"', 0.03505, 0.04216),
    ('1-1/2"', 0.04089, 0.04830),
    ('2"', 0.05250, 0.06033),
    ('2-1/2"', 0.06271, 0.07303),
    ('3"', 0.07793, 0.08890),
    ('4"', 0.10226, 0.11430),
    ('6"', 0.15405, 0.16830),
    ('8"', 0.20272, 0.21910),
    ('10"', 0.25451, 0.27310),
    ('12"', 0.30323, 0.32390),
    ('14"', 0.33334, 0.35560),
    ('16"', 0.38100, 0.40640),
    ('18"', 0.42866, 0.45720),
    ('20"', 0.47782, 0.50800),
    ('24"', 0.57465, 0.61000),
]

TIPOS_CARCASA = ("E", "F", "X")
CABEZALES_FRONTALES = ("A", "B", "C")
CABEZALES_TRASEROS = ("L", "M", "N", "P", "S", "T", "U", "W")

CORROSION_DEFECTO = 3.2e-3   # 1/8 in, margen de corrosion tipico TEMA Clase C
EFICIENCIA_JUNTA = 0.85      # E, soldadura a tope con radiografia por puntos

# Tolerancia del chequeo de empaquetamiento del haz. El conteo de tubos del
# sizing termico proviene de una correlacion empirica (Serth, con C_L y C_TP)
# y el de aqui de un cociente de areas: ambos son estimaciones y difieren en
# los efectos de borde, dominantes en corazas pequenas. Por debajo de esta
# tolerancia la discrepancia se reporta como advertencia, no como error.
TOL_EMPAQUE = 0.05           # 5 %


# =============================================================================
# 2. CONTENEDORES DE DATOS
# =============================================================================
@dataclass
class MechanicalInput:
    """Geometria termica + condiciones de diseno que alimentan este modulo."""
    D_s: float                 # Diametro interior de coraza [m]
    N_tt: int                  # Numero total de tubos
    L: float                   # Longitud de tubos [m]
    d_o: float = 0.01905       # Diametro exterior del tubo [m]
    P_T: float = 0.0238        # Pitch [m]
    L_bc: float = 0.0          # Espaciado central de baffles [m]; 0 -> 0.5*D_s
    corte_baffle: float = 0.25  # Fraccion de corte del segmento
    layout: int = 30           # 30/60 = triangular, 45/90 = cuadrado

    rho_s: float = 1000.0      # Densidad del fluido de coraza [kg/m3]
    rho_t: float = 1000.0      # Densidad del fluido de tubos [kg/m3]
    m_dot_s: float = 0.0       # Caudal masico lado coraza [kg/s]
    m_dot_t: float = 0.0       # Caudal masico lado tubos [kg/s]

    P_diseno_s: float = 1.0e6  # Presion de diseno lado coraza [Pa]
    P_diseno_t: float = 1.0e6  # Presion de diseno lado tubos [Pa]
    material: str = "Acero al carbono"
    corrosion: float = CORROSION_DEFECTO

    tipo_carcasa: str = "E"
    cabezal_frontal: str = "A"
    cabezal_trasero: str = "M"
    d_perno: float = 0.01905   # Diametro de perno [m] (3/4 in, minimo TEMA)


@dataclass
class Boquilla:
    """Resultado del dimensionamiento de una boquilla."""
    lado: str
    V_max: float          # Velocidad maxima admisible [m/s]
    D_min: float          # Diametro interior minimo requerido [m]
    nps: str              # Tuberia comercial seleccionada
    D_i: float            # Diametro interior real [m]
    D_e: float            # Diametro exterior real [m]
    espesor: float        # Espesor de pared requerido [m]
    V_real: float         # Velocidad con la tuberia seleccionada [m/s]


@dataclass
class Brida:
    """Resultado del dimensionamiento de la brida de carcasa."""
    f_w: float            # Ancho radial de brida [m]
    D_F: float            # Diametro exterior de brida [m]
    D_BC: float           # Diametro del circulo de pernos [m]
    n_pernos: int
    d_perno: float


@dataclass
class Baffles:
    """Resultado del dimensionamiento de las placas deflectoras."""
    N_B: int
    L_bc: float           # Espaciado central [m]
    L_bi: float           # Espaciado de entrada/salida [m]
    espesor: float        # Espesor de placa [m]
    D_baffle: float       # Diametro exterior de la placa [m]
    altura_corte: float   # Altura del segmento cortado [m]
    luz_sin_soporte: float  # Tramo maximo de tubo sin soporte [m]


@dataclass
class MechanicalResult:
    """Paquete completo de dimensiones de fabricacion."""
    D_s: float
    T_s: float            # Espesor de carcasa [m]
    D_o: float            # Diametro exterior de carcasa [m]
    D_otl: float          # Limite exterior del haz [m]
    D_ctl: float          # Circulo por centros de tubos perifericos [m]
    L_ts: float           # Espesor de espejo de tubos [m]
    T_c: float            # Espesor de cubierta del cabezal [m]
    tipo_cubierta: str
    L_total: float        # Longitud total del equipo (tubos + espejos) [m]
    baffles: Baffles
    brida: Brida
    boquilla_coraza: Optional[Boquilla]
    boquilla_tubos: Optional[Boquilla]
    advertencias: List[str] = field(default_factory=list)


# =============================================================================
# 3. UTILIDADES DE TABLA
# =============================================================================
def _buscar_rango(tabla: List[Tuple[float, float]], x: float) -> float:
    """Devuelve el valor de la primera fila cuyo limite superior supera a x."""
    for limite, valor in tabla:
        if x <= limite:
            return valor
    return tabla[-1][1]


def _luz_maxima_tubo(d_o: float) -> float:
    """Luz maxima sin soporte para el tubo mas cercano en la tabla TEMA."""
    clave = min(_LUZ_MAX_TUBO, key=lambda d: abs(d - d_o))
    return _LUZ_MAX_TUBO[clave]


def seleccionar_tuberia(D_min: float) -> Tuple[str, float, float]:
    """Primera tuberia Sch-40 comercial cuyo D_i alcanza el minimo requerido."""
    for nps, d_i, d_e in _NPS_SCH40:
        if d_i >= D_min:
            return nps, d_i, d_e
    raise ValueError(
        f"El diametro de boquilla requerido ({D_min*1000:.0f} mm) excede la "
        f"mayor tuberia tabulada (24 in). Divida el caudal en dos boquillas "
        f"o use una boquilla conica fabricada a medida."
    )


def _validar_material(material: str) -> float:
    if material not in S_ADMISIBLE:
        raise ValueError(
            f"Material '{material}' sin esfuerzo admisible tabulado. "
            f"Opciones: {', '.join(S_ADMISIBLE)}."
        )
    return S_ADMISIBLE[material]


# =============================================================================
# 4. CARCASA: ESPESOR Y DIAMETRO EXTERNO  (Eqs. 19-20)
# =============================================================================
def espesor_carcasa(D_s: float, P: float, material: str,
                    corrosion: float = CORROSION_DEFECTO,
                    E: float = EFICIENCIA_JUNTA) -> float:
    """
    Espesor de pared de la carcasa cilindrica.

    ASME VIII Div.1 UG-27(c)(1), esfuerzo circunferencial:
        T_s = P*R / (S*E - 0.6*P)   + margen de corrosion
    El resultado se acota por el espesor minimo de fabricacion TEMA Clase C.
    """
    if D_s <= 0:
        raise ValueError("El diametro de coraza debe ser positivo.")
    if P <= 0:
        raise ValueError("La presion de diseno debe ser positiva.")

    S = _validar_material(material)
    if P >= 0.385 * S * E:
        raise ValueError(
            f"Presion de diseno {P/1e5:.1f} bar demasiado alta para pared "
            f"delgada con {material}. UG-27 exige el analisis de pared gruesa "
            f"(Apendice 1-2); fuera del alcance de esta herramienta."
        )

    t_calc = P * (D_s / 2.0) / (S * E - 0.6 * P) + corrosion
    t_min = _buscar_rango(_T_MIN_CARCASA, D_s)
    return max(t_calc, t_min)


def diametro_externo(D_s: float, T_s: float) -> float:
    """D_o = D_s + 2*T_s  (Eq. 19)."""
    return D_s + 2.0 * T_s


# =============================================================================
# 5. HAZ DE TUBOS: LIMITES D_otl Y D_ctl  (Eqs. 21-22)
# =============================================================================
def limites_haz(D_s: float, d_o: float, cabezal_trasero: str) -> Tuple[float, float]:
    """
    D_otl: diametro del circulo que envuelve los tubos mas externos.
    D_ctl: diametro del circulo que pasa por los CENTROS de esos tubos.

        D_otl = D_s - holgura(tipo de cabezal trasero)
        D_ctl = D_otl - d_o
    """
    cabezal_trasero = cabezal_trasero.upper()
    if cabezal_trasero not in _HOLGURA_HAZ:
        raise ValueError(
            f"Cabezal trasero '{cabezal_trasero}' no reconocido. "
            f"Use uno de: {', '.join(sorted(_HOLGURA_HAZ))}."
        )
    D_otl = D_s - _HOLGURA_HAZ[cabezal_trasero]
    D_ctl = D_otl - d_o
    if D_ctl <= 0:
        raise ValueError(
            f"D_ctl negativo: la coraza (D_s = {D_s*1000:.0f} mm) es demasiado "
            f"pequena frente al tubo y la holgura del cabezal "
            f"'{cabezal_trasero}'. Revise el sizing termico."
        )
    return D_otl, D_ctl


# =============================================================================
# 6. ESPEJO DE TUBOS  (Eq. 23)
# =============================================================================
def espesor_espejo(D_s: float, d_o: float) -> float:
    """
    Espesor del espejo de tubos:  L_ts = 0.1 * D_s  (INSTRUCCIONES_MECH, Eq.23)

    Acotado inferiormente por el minimo de fabricacion TEMA RCB-7.13: con
    juntas de tubo mandrinadas el espesor no debe ser menor que el diametro
    exterior del tubo, y nunca inferior a 3/4 in.
    """
    L_ts = 0.1 * D_s
    return max(L_ts, d_o, 0.75 * IN)


# =============================================================================
# 7. BOQUILLAS  (Eqs. 24-26)
# =============================================================================
def dimensionar_boquilla(lado: str, m_dot: float, rho: float,
                         P: float, material: str,
                         corrosion: float = CORROSION_DEFECTO,
                         E: float = EFICIENCIA_JUNTA) -> Boquilla:
    """
    Diametro interior minimo de boquilla que evita vibracion de tubos.

    Criterio TEMA RCB-4.61 (fluido monofasico, no abrasivo):
        rho * V^2 <= 2232.25 Pa      ->  V_max = sqrt(2232.25 / rho)
    Se toma ademas el tope practico de 3 m/s para liquidos.

        A_n = m_dot / (rho * V_max)  ->  D_min = sqrt(4*A_n/pi)

    Luego se escoge la primera tuberia Sch-40 comercial con D_i >= D_min y se
    verifica su espesor con UG-27.
    """
    if m_dot <= 0:
        raise ValueError(
            f"Caudal masico del lado {lado} nulo o negativo: no es posible "
            f"dimensionar la boquilla."
        )
    if rho <= 0:
        raise ValueError(f"Densidad del lado {lado} debe ser positiva.")

    V_max = min(math.sqrt(RHO_V2_MAX / rho), V_BOQUILLA_MAX_PRACTICO)
    A_n = m_dot / (rho * V_max)
    D_min = math.sqrt(4.0 * A_n / math.pi)

    nps, D_i, D_e = seleccionar_tuberia(D_min)
    V_real = m_dot / (rho * math.pi * D_i ** 2 / 4.0)

    S = _validar_material(material)
    t = P * (D_i / 2.0) / (S * E - 0.6 * P) + corrosion
    t = max(t, (D_e - D_i) / 2.0)   # nunca menor que la pared Sch-40 real

    return Boquilla(lado=lado, V_max=V_max, D_min=D_min, nps=nps,
                    D_i=D_i, D_e=D_e, espesor=t, V_real=V_real)


# =============================================================================
# 8. BRIDAS  (Eqs. 27-28)
# =============================================================================
def dimensionar_brida(D_o: float, d_perno: float = 0.01905) -> Brida:
    """
    Brida de carcasa (INSTRUCCIONES_MECH, Eqs. 27-28):

        f_w = 3 * (1.5 * d_B)            ancho radial de la brida
        D_F = D_o + 2*f_w + 0.004        diametro exterior (4 mm de holgura)

    El ancho se reparte en tres tramos iguales de 1.5*d_B (borde interior,
    agujero, borde exterior), de modo que el eje del perno queda a
    2.25*d_B del borde -> D_BC = D_o + f_w.

    El numero de pernos sale del paso tipico de 4*d_B sobre el circulo de
    pernos, redondeado al multiplo de 4 superior (minimo 8, TEMA RCB-11).
    """
    if d_perno <= 0:
        raise ValueError("El diametro de perno debe ser positivo.")
    if d_perno < 0.5 * IN:
        raise ValueError(
            f"Perno de {d_perno*1000:.1f} mm por debajo del minimo TEMA "
            f"RCB-11.1 (1/2 in = 12.7 mm)."
        )

    f_w = 3.0 * (1.5 * d_perno)
    D_F = D_o + 2.0 * f_w + 0.004
    D_BC = D_o + f_w

    n = math.ceil(math.pi * D_BC / (4.0 * d_perno))
    n = max(8, int(math.ceil(n / 4.0) * 4))

    return Brida(f_w=f_w, D_F=D_F, D_BC=D_BC, n_pernos=n, d_perno=d_perno)


# =============================================================================
# 9. PLACAS DEFLECTORAS  (Eqs. 29-30)
# =============================================================================
def dimensionar_baffles(D_s: float, L: float, d_o: float, L_bc: float,
                        corte: float = 0.25,
                        tipo_carcasa: str = "E") -> Baffles:
    """
    Deflectores segmentados simples (segmento transversal).

        N_B = L / L_bc - 1
        altura del corte = corte * D_s
        D_baffle = D_s - holgura diametral TEMA

    En carcasa tipo X (flujo cruzado puro) no hay deflectores transversales;
    solo placas soporte, espaciadas por la luz maxima sin soporte TEMA.
    """
    tipo_carcasa = tipo_carcasa.upper()
    if tipo_carcasa not in TIPOS_CARCASA:
        raise ValueError(
            f"Tipo de carcasa '{tipo_carcasa}' no soportado. "
            f"Use E, F o X."
        )
    if L <= 0:
        raise ValueError("La longitud de tubos debe ser positiva.")
    if L_bc <= 0:
        raise ValueError("El espaciado de baffles L_bc debe ser positivo.")

    luz_max = _luz_maxima_tubo(d_o)

    if tipo_carcasa == "X":
        # Sin deflectores: solo soportes al maximo tramo permitido.
        L_bc = min(L_bc, luz_max)
        N_B = max(int(math.ceil(L / L_bc)) - 1, 0)
        corte = 0.0
    else:
        if not (0.15 <= corte <= 0.45):
            raise ValueError(
                f"Corte de baffle {corte*100:.0f} % fuera del rango practico "
                f"15 - 45 %. El optimo de Kern esta entre 20 y 25 %."
            )
        if not (D_s / 5.0 <= L_bc <= D_s):
            raise ValueError(
                f"Espaciado de baffles L_bc = {L_bc*1000:.0f} mm fuera del "
                f"rango TEMA RCB-4.52 [D_s/5 = {D_s/5*1000:.0f} mm ; "
                f"D_s = {D_s*1000:.0f} mm]."
            )
        N_B = max(int(math.floor(L / L_bc + 1e-9)) - 1, 0)

    # Espaciado de entrada/salida: absorbe la longitud sobrante de los extremos.
    L_bi = (L - (N_B - 1) * L_bc) / 2.0 if N_B >= 1 else L / 2.0

    # Tramo sin soporte: en la ventana el tubo salta un deflector; ademas el
    # tramo de entrada/salida (L_bi) mas el primer espaciado central no debe
    # exceder la luz maxima.
    luz = max(2.0 * L_bc, L_bi + L_bc) if tipo_carcasa != "X" else L_bc
    if luz > luz_max:
        raise ValueError(
            f"Tramo de tubo sin soporte = {luz*1000:.0f} mm supera la luz "
            f"maxima TEMA RCB-4.52 de {luz_max*1000:.0f} mm para tubo de "
            f"{d_o*1000:.1f} mm. Reduzca L_bc o agregue placas soporte."
        )

    # Espesor de placa segun D_s y la luz sin soporte.
    fila = next(v for lim, v in _ESPESOR_BAFFLE if D_s <= lim)
    idx = sum(1 for lim in _LUZ_BAFFLE_LIMITES if luz >= lim)
    espesor = fila[idx]

    D_baffle = D_s - _buscar_rango(_HOLGURA_BAFFLE, D_s)

    return Baffles(N_B=N_B, L_bc=L_bc, L_bi=L_bi, espesor=espesor,
                   D_baffle=D_baffle, altura_corte=corte * D_s,
                   luz_sin_soporte=luz)


# =============================================================================
# 10. CABEZALES: ESPESOR DE CUBIERTA  (Eqs. 31-32)
# =============================================================================
def espesor_cubierta(D_s: float, P: float, material: str,
                     cabezal: str = "A",
                     corrosion: float = CORROSION_DEFECTO,
                     E: float = EFICIENCIA_JUNTA) -> Tuple[float, str]:
    """
    Espesor T_c de la cubierta del cabezal. Devuelve (espesor, descripcion).

    Cabezal A o C (canal con cubierta plana desmontable) -> ASME UG-34:
        T_c = D_s * sqrt(C*P / (S*E)) + corrosion,  C = 0.3 (apernada)

    Cabezal B (bonete toriesferico) -> ASME UG-32(e), relacion 6 %:
        T_c = 0.885*P*L_corona / (S*E - 0.1*P) + corrosion,  L_corona = D_s
    """
    cabezal = cabezal.upper()
    if cabezal not in CABEZALES_FRONTALES:
        raise ValueError(
            f"Cabezal frontal '{cabezal}' no reconocido. Use A, B o C."
        )
    S = _validar_material(material)

    if cabezal == "B":
        if P >= 0.665 * S * E:
            raise ValueError(
                "Presion excesiva para una cabeza toriesferica de pared "
                "delgada (ASME UG-32); use un cabezal plano reforzado."
            )
        t = 0.885 * P * D_s / (S * E - 0.1 * P) + corrosion
        return t, "Toriesferica (bonete tipo B)"

    C = 0.3  # cubierta plana apernada con junta en todo el ancho
    t = D_s * math.sqrt(C * P / (S * E)) + corrosion
    return t, f"Plana apernada (canal tipo {cabezal})"


# =============================================================================
# 11. ORQUESTADOR
# =============================================================================
def disenar_mecanico(inp: MechanicalInput) -> MechanicalResult:
    """Ejecuta el dimensionamiento mecanico completo y valida la coherencia."""
    # --- Sanity checks de entrada ---------------------------------------
    if inp.D_s <= 0 or inp.L <= 0:
        raise ValueError("D_s y L deben ser positivos.")
    if inp.N_tt <= 0:
        raise ValueError("El numero de tubos debe ser un entero positivo.")
    if inp.d_o <= 0 or inp.P_T <= inp.d_o:
        raise ValueError(
            f"Pitch P_T = {inp.P_T*1000:.1f} mm debe ser mayor que el "
            f"diametro exterior del tubo ({inp.d_o*1000:.1f} mm)."
        )
    if inp.layout not in (30, 45, 60, 90):
        raise ValueError(
            f"Layout '{inp.layout}' no reconocido. Use 30/60 (triangular) "
            "o 45/90 (cuadrado)."
        )
    if inp.P_diseno_s < 1.0e4 or inp.P_diseno_t < 1.0e4:
        raise ValueError(
            f"Presion de diseno ({min(inp.P_diseno_s, inp.P_diseno_t):.1f} Pa) "
            "anormalmente baja (< 0.1 bar). Verifique que la presion este en "
            "PASCALES [Pa] y no en bar o kPa."
        )

    advertencias: List[str] = []
    L_bc = inp.L_bc if inp.L_bc > 0 else 0.5 * inp.D_s

    # --- Carcasa ---------------------------------------------------------
    T_s = espesor_carcasa(inp.D_s, inp.P_diseno_s, inp.material, inp.corrosion)
    D_o = diametro_externo(inp.D_s, T_s)
    if T_s > inp.D_s / 10.0:
        advertencias.append(
            "El espesor de carcasa supera D_s/10: la hipotesis de pared "
            "delgada de UG-27 ya no es valida."
        )

    # --- Haz y espejos ---------------------------------------------------
    D_otl, D_ctl = limites_haz(inp.D_s, inp.d_o, inp.cabezal_trasero)
    L_ts = espesor_espejo(inp.D_s, inp.d_o)

    # Verificacion de empaquetamiento. El area disponible para las celdas de
    # tubo es la del circulo que ENVUELVE a los tubos perifericos (D_otl): el
    # circulo que pasa por sus centros (D_ctl) recorta media celda de todo el
    # anillo exterior y subestima el conteo frente a la correlacion de Serth
    # del sizing termico, que se referencia a D_s.
    area_disponible = math.pi * D_otl ** 2 / 4.0
    factor_celda = (math.sqrt(3.0) / 2.0) if inp.layout in (30, 60) else 1.0
    area_por_tubo = factor_celda * (inp.P_T ** 2)   # celda triangular o cuadrada
    n_max = int(area_disponible / area_por_tubo)
    if inp.N_tt > n_max * (1.0 + TOL_EMPAQUE):
        raise ValueError(
            f"No caben {inp.N_tt} tubos con pitch {inp.P_T*1000:.1f} mm dentro "
            f"de D_otl = {D_otl*1000:.0f} mm (maximo geometrico ~{n_max}, "
            f"exceso {100.0*(inp.N_tt/n_max - 1.0):.0f} %). "
            f"Aumente D_s o reduzca el pitch en el sizing termico."
        )
    if inp.N_tt > n_max:
        advertencias.append(
            f"El conteo del sizing ({inp.N_tt} tubos) excede en "
            f"{100.0*(inp.N_tt/n_max - 1.0):.1f} % el maximo geometrico "
            f"estimado ({n_max}) dentro de D_otl = {D_otl*1000:.0f} mm. "
            "La diferencia cabe en la incertidumbre de las correlaciones de "
            "conteo (efectos de borde): levante el plano del espejo antes de "
            "fabricar."
        )

    # --- Baffles ---------------------------------------------------------
    baffles = dimensionar_baffles(inp.D_s, inp.L, inp.d_o, L_bc,
                                  inp.corte_baffle, inp.tipo_carcasa)
    if inp.tipo_carcasa.upper() == "F":
        advertencias.append(
            "Carcasa tipo F: debe agregarse un deflector longitudinal "
            "soldado o sellado; la caida de presion sera ~8 veces la de una E."
        )

    # --- Bridas ----------------------------------------------------------
    brida = dimensionar_brida(D_o, inp.d_perno)

    # --- Boquillas -------------------------------------------------------
    boq_s = boq_t = None
    if inp.m_dot_s > 0:
        boq_s = dimensionar_boquilla("coraza", inp.m_dot_s, inp.rho_s,
                                     inp.P_diseno_s, inp.material,
                                     inp.corrosion)
        if boq_s.D_i > inp.D_s / 3.0:
            advertencias.append(
                f"La boquilla de coraza ({boq_s.nps}) supera D_s/3: requiere "
                f"placa de impacto y refuerzo de abertura (TEMA RCB-4.6)."
            )
        if boq_s.V_real < V_BOQUILLA_MIN_PRACTICO:
            advertencias.append(
                f"Velocidad en boquilla de coraza baja "
                f"({boq_s.V_real:.2f} m/s): favorece deposicion de solidos."
            )
    if inp.m_dot_t > 0:
        boq_t = dimensionar_boquilla("tubos", inp.m_dot_t, inp.rho_t,
                                     inp.P_diseno_t, inp.material,
                                     inp.corrosion)

    # --- Cabezal ---------------------------------------------------------
    T_c, tipo_cubierta = espesor_cubierta(inp.D_s, inp.P_diseno_t,
                                          inp.material, inp.cabezal_frontal,
                                          inp.corrosion)

    # Longitud total: tubos + los dos espejos.
    L_total = inp.L + 2.0 * L_ts

    if not (3.0 <= inp.L / inp.D_s <= 15.0):
        advertencias.append(
            f"Relacion L/D_s = {inp.L/inp.D_s:.1f} fuera del rango practico "
            f"de fabricacion 3 - 15."
        )

    return MechanicalResult(
        D_s=inp.D_s, T_s=T_s, D_o=D_o, D_otl=D_otl, D_ctl=D_ctl,
        L_ts=L_ts, T_c=T_c, tipo_cubierta=tipo_cubierta, L_total=L_total,
        baffles=baffles, brida=brida,
        boquilla_coraza=boq_s, boquilla_tubos=boq_t,
        advertencias=advertencias,
    )


# =============================================================================
# 12. PRUEBA RAPIDA
# =============================================================================
if __name__ == "__main__":
    mm = 1000.0

    caso = MechanicalInput(
        D_s=0.50,          # dato del enunciado
        N_tt=150,          # dato del enunciado
        L=3.0,             # dato del enunciado
        rho_s=1110.0,      # dato del enunciado (fluido de coraza)
        # --- supuestos del ejemplo (no venian en el enunciado) ---
        d_o=0.01905,       # tubo 3/4 in
        P_T=0.0238,        # pitch triangular 1.25 * d_o
        L_bc=0.25,         # 0.5 * D_s
        rho_t=995.0,       # agua en tubos
        m_dot_s=30.0,      # kg/s
        m_dot_t=25.0,      # kg/s
        P_diseno_s=1.0e6,  # 10 bar
        P_diseno_t=1.0e6,
        material="Acero al carbono",
        tipo_carcasa="E", cabezal_frontal="A", cabezal_trasero="M",
    )

    r = disenar_mecanico(caso)

    print("=" * 66)
    print(" DISENO MECANICO TEMA Clase 'C' - caso de prueba")
    print("=" * 66)
    print(f" Supuestos: P_dis = {caso.P_diseno_s/1e5:.0f} bar | "
          f"{caso.material} | m_s = {caso.m_dot_s:.0f} kg/s | "
          f"m_t = {caso.m_dot_t:.0f} kg/s")
    print("-" * 66)
    print(" CARCASA")
    print(f"   D_s interior        = {r.D_s*mm:7.1f} mm")
    print(f"   Espesor T_s         = {r.T_s*mm:7.2f} mm")
    print(f"   D_o EXTERIOR FINAL  = {r.D_o*mm:7.1f} mm")
    print(f"   Longitud total      = {r.L_total*mm:7.1f} mm")
    print("-" * 66)
    print(" HAZ Y ESPEJOS")
    print(f"   D_otl (limite haz)  = {r.D_otl*mm:7.1f} mm")
    print(f"   D_ctl (centros)     = {r.D_ctl*mm:7.1f} mm")
    print(f"   ESPESOR ESPEJO L_ts = {r.L_ts*mm:7.2f} mm  (x2 espejos)")
    print(f"   Cubierta cabezal T_c= {r.T_c*mm:7.2f} mm  [{r.tipo_cubierta}]")
    print("-" * 66)
    b = r.baffles
    print(" DEFLECTORES")
    print(f"   N_B = {b.N_B} placas   L_bc = {b.L_bc*mm:.0f} mm   "
          f"L_bi = {b.L_bi*mm:.0f} mm")
    print(f"   Espesor = {b.espesor*mm:.2f} mm   D_baffle = {b.D_baffle*mm:.1f} mm")
    print(f"   Altura de corte = {b.altura_corte*mm:.1f} mm   "
          f"luz sin soporte = {b.luz_sin_soporte*mm:.0f} mm")
    print("-" * 66)
    f = r.brida
    print(" BRIDA DE CARCASA")
    print(f"   Ancho f_w = {f.f_w*mm:.1f} mm   D_F = {f.D_F*mm:.1f} mm")
    print(f"   Circulo de pernos = {f.D_BC*mm:.1f} mm   "
          f"{f.n_pernos} pernos de {f.d_perno*mm:.1f} mm")
    print("-" * 66)
    print(" BOQUILLAS")
    for boq in (r.boquilla_coraza, r.boquilla_tubos):
        if boq is None:
            continue
        print(f"   Lado {boq.lado:7s}: {boq.nps:8s} Sch-40  "
              f"D_i = {boq.D_i*mm:6.1f} mm  D_e = {boq.D_e*mm:6.1f} mm")
        print(f"               espesor = {boq.espesor*mm:4.2f} mm   "
              f"V_max = {boq.V_max:.2f} m/s   V_real = {boq.V_real:.2f} m/s")
    print("=" * 66)
    if r.advertencias:
        print(" ADVERTENCIAS")
        for a in r.advertencias:
            print(f"   - {a}")
    else:
        print(" Sin advertencias: todas las dimensiones dentro de rango TEMA.")
    print("=" * 66)
