# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
"""
DISENO MECANICO - Estandar TEMA Clase "C" (+ ASME VIII Div. 1 para espesores)
================================================================================
Recibe la geometria termica resuelta por `src/thermo/sizing.py` (D_s, N_tt, L,
d_o, pitch) y devuelve las dimensiones de fabricacion del equipo:

    carcasa  ->  espesor T_s y diametro externo D_o
    haz      ->  limites de tubos D_otl / D_ctl
    espejos  ->  espesor L_ts
    baffles  ->  numero N_B, espesor, corte y diametro de la placa
    varillas ->  tensores y espaciadores (CB-4.7.1)
    boquillas->  diametro interior minimo (criterio rho*V^2)
    bridas   ->  ancho f_w, diametro exterior D_F, circulo y numero de pernos
    cabezales->  espesor de cubierta T_c y descripcion por tipo TEMA

TODOS los tipos de la Figura N-1.2 del estandar TEMA estan soportados:
    Carcasa:      E, F, G, H, J, K, X
    Cabezal frontal: A, B, C, D, N
    Cabezal trasero: L, M, N, P, S, T, U, W

Referencias (verificadas contra los PDF incluidos en la carpeta del proyecto):
    TEMA 10th ed. Figura N-1.2  - Table of TEMA types (diagramas de cada tipo)
    TEMA 10th ed. Tabla CB-3.1.3  - espesor minimo de coraza (Clase C/B)
    TEMA 10th ed. Tabla RCB-4.3   - holgura baffle-coraza
    TEMA 10th ed. Tabla CB-4.4.1  - espesor de deflectores (Clase C/B)
    TEMA 10th ed. Parrafo RCB-4.5.1 - espaciado minimo de baffles (D_s/5 o 2 in)
    TEMA 10th ed. Tabla RCB-4.5.2  - luz maxima sin soporte del tubo
    TEMA 10th ed. Parrafo RCB-4.6.1 - rho*V^2 en boquillas de coraza
    TEMA 10th ed. Parrafo RCB-4.6.3 - rho*V^2 en boquillas de tubos
    TEMA 10th ed. Tabla CB-4.7.1  - varillas tensores (Clase C/B)
    TEMA 10th ed. Parrafo C-7.1.1 - espesor minimo de espejo (Clase C)
    TEMA 10th ed. Parrafo C-11.1  - perno minimo 1/2 in (Clase C)
    TEMA 10th ed. Parrafo RCB-11.2.2 - paso maximo entre pernos
    ASME BPVC Seccion VIII Div. 1: UG-27 (cilindros), UG-32 (cabezas
    toriesfericas), UG-34 (cubiertas planas).
    Tan & Fok (2006), ecuaciones 19-32 de dimensionamiento mecanico.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    from src.core.errores import ErrorDiseno
except ImportError:  # ejecucion directa: `python src/mechanical/design.py`
    import os
    import sys
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.core.errores import ErrorDiseno

# =============================================================================
# 1. CONSTANTES Y TABLAS TEMA / ASME
# =============================================================================
IN = 0.0254  # 1 pulgada en metros

# --- RCB-4.6.1: limites de rho*V^2 en la boquilla de entrada de coraza ------
#   1500 lbm/(ft*s^2) = 2232.25 Pa : fluido monofasico no abrasivo
#     (liquidos, gases o vapores)
#   500  lbm/(ft*s^2) =  744 Pa : los demas liquidos, incluido el que opera a
#     su temperatura de ebullicion
# Conversion exacta: 1 lbm/(ft*s^2) = 0.45359237/0.3048 = 1.48816 Pa.
RHO_V2_CORAZA = 1500.0 * 0.45359237 / 0.3048   # 2232.25 Pa exactos
RHO_V2_CORAZA_HIERVIENDO = 744.0     # Pa
# --- RCB-4.6.3: liquido en la boquilla de entrada de tubos ------------------
RHO_V2_TUBOS = 8928.0                # Pa (6000 lbm/(ft*s^2))

V_BOQUILLA_MAX_PRACTICO = 3.0  # m/s, tope practico para liquidos (erosion)
V_BOQUILLA_MIN_PRACTICO = 0.6  # m/s, por debajo hay riesgo real de
                               # sedimentacion en la boquilla (los saltos de
                               # tuberia comercial impiden ir mas cerca de
                               # V_max sin excederlo)

# Esfuerzo admisible S [Pa] a temperatura moderada (<= 150 C) [valores tipicos]
S_ADMISIBLE: Dict[str, float] = {
    "Acero al carbono": 138.0e6,   # SA-516 Gr.70
    "Acero inoxidable 304": 115.0e6,
    "Acero inoxidable 316": 115.0e6,
    "Cobre": 46.0e6,               # C12200 recocido
    "Laton Almirantazgo": 55.0e6,
}

# --- CB-3.1.3: espesor minimo nominal de coraza, Clase C/B -----------------
# (diametro interior maximo [m], espesor minimo [m]) para acero al carbono.
# Hasta 12 in la norma pide tuberia comercial (Sch-40 en 6 in, Sch-30 en
# 8-12 in): se toma la pared Sch-40 de 6 in (7.1 mm) como minimo comun.
_T_MIN_CARCASA: List[Tuple[float, float]] = [
    (0.305, 7.1e-3),    # 6-12 in   -> tuberia Sch-40/Sch-30
    (0.584, 7.9e-3),    # 13-23 in  -> placa 5/16 in
    (0.737, 7.9e-3),    # 24-29 in  -> placa 5/16 in
    (0.991, 9.5e-3),    # 30-39 in  -> placa 3/8 in
    (1.524, 11.1e-3),   # 40-60 in  -> placa 7/16 in
    (2.032, 12.7e-3),   # 61-80 in  -> placa 1/2 in
    (2.540, 12.7e-3),   # 81-100 in -> placa 1/2 in
    (9.999, 12.7e-3),
]

# --- RCB-4.3: holgura diametral carcasa-baffle (D_i de diseno - D_baffle) ---
_HOLGURA_BAFFLE: List[Tuple[float, float]] = [
    (0.432, 3.2e-3),   # 6-17 in  -> 1/8 in
    (0.991, 4.8e-3),   # 18-39 in -> 3/16 in
    (1.372, 6.4e-3),   # 40-54 in -> 1/4 in
    (1.753, 7.9e-3),   # 55-69 in -> 5/16 in
    (2.134, 9.5e-3),   # 70-84 in -> 3/8 in
    (9.999, 11.1e-3),  # 85-100 in -> 7/16 in
]

# --- CB-4.4.1: espesor de baffle (Clase C/B), en metros ---------------------
# Filas: (diametro nominal de coraza maximo [m], tupla de espesores).
# Columnas: luz sin soporte entre baffles centrales de
#   <= 12 in (305) | >12-24 (610) | >24-36 (914) | >36-48 (1219)
#   | >48-60 (1524) | > 60 in (1524)
# (los espacios de entrada/salida no se consideran para esta tabla).
_ESPESOR_BAFFLE: List[Tuple[float, Tuple[float, ...]]] = [
    (0.356, (1.6e-3, 3.2e-3, 4.8e-3, 6.4e-3, 9.5e-3, 9.5e-3)),    # 6-14 in
    (0.711, (3.2e-3, 4.8e-3, 6.4e-3, 9.5e-3, 9.5e-3, 12.7e-3)),   # 15-28 in
    (0.965, (4.8e-3, 6.4e-3, 7.9e-3, 9.5e-3, 12.7e-3, 15.9e-3)),  # 29-38 in
    (1.524, (6.4e-3, 6.4e-3, 9.5e-3, 12.7e-3, 15.9e-3, 15.9e-3)), # 39-60 in
    (2.540, (6.4e-3, 9.5e-3, 12.7e-3, 15.9e-3, 19.1e-3, 19.1e-3)),# 61-100 in
]
_LUZ_BAFFLE_LIMITES = (0.305, 0.610, 0.914, 1.219, 1.524)  # m

# --- RCB-4.5.2: luz maxima sin soporte del tubo recto, en metros ------------
# (diametro exterior del tubo [m], (luz grupo 1 [m], luz grupo 2 [m])).
# Grupo 1: acero al carbono y aleaciones de alta resistencia, acero de baja
#   aleacion, niquel-cobre, niquel y niquel-cromo-hierro (<= 750 F / 399 C).
# Grupo 2: aluminio y sus aleaciones, cobre y sus aleaciones, titanio.
_LUZ_MAX_TUBO: List[Tuple[float, Tuple[float, float]]] = [
    (0.00635, (0.660, 0.559)),   # 1/4 in
    (0.00953, (0.889, 0.762)),   # 3/8 in
    (0.01270, (1.118, 0.965)),   # 1/2 in
    (0.01588, (1.321, 1.143)),   # 5/8 in
    (0.01905, (1.524, 1.321)),   # 3/4 in
    (0.02223, (1.753, 1.524)),   # 7/8 in
    (0.02540, (1.880, 1.626)),   # 1 in
    (0.03175, (2.235, 1.930)),   # 1-1/4 in
    (0.03810, (2.540, 2.210)),   # 1-1/2 in
    (0.05080, (3.175, 2.794)),   # 2 in
    (0.06350, (3.175, 2.794)),   # 2-1/2 in
    (0.07620, (3.175, 2.794)),   # 3 in
]
# Materiales del "grupo 2" de la tabla RCB-4.5.2 (menor luz admisible).
_MATERIALES_GRUPO_B = ("cobre", "laton", "aluminio", "copper", "brass",
                       "aluminum", "aluminium", "titanio", "titanium")

# --- CB-4.7.1: varillas tensores (Clase C/B) --------------------------------
# (diametro de coraza maximo [m], diametro de varilla [m], cantidad minima)
_TIE_RODS: List[Tuple[float, float, int]] = [
    (0.381, 0.00635, 4),    # 6-15 in  -> 1/4 in, 4
    (0.686, 0.00953, 6),    # 16-27 in -> 3/8 in, 6
    (0.838, 0.01270, 6),    # 28-33 in -> 1/2 in, 6
    (1.219, 0.01270, 8),    # 34-48 in -> 1/2 in, 8
    (1.524, 0.01270, 10),   # 49-60 in -> 1/2 in, 10
    (2.540, 0.01588, 12),   # 61-100 in -> 5/8 in, 12
    (9.999, 0.01588, 12),
]

# Holgura diametral carcasa - limite exterior del haz (D_s - D_otl), en metros.
# Depende del tipo de cabezal trasero TEMA [valores tipicos Bell-Delaware].
HOLGURA_HAZ: Dict[str, float] = {
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

# --- Figura N-1.2 del estandar TEMA: tipos soportados y su descripcion ------
TIPOS_CARCASA = ("E", "F", "G", "H", "J", "K", "X")
CABEZALES_FRONTALES = ("A", "B", "C", "D", "N")
CABEZALES_TRASEROS = ("L", "M", "N", "P", "S", "T", "U", "W")

DESCRIPCION_CARCASA: Dict[str, str] = {
    "E": "Una pasada por la coraza (one pass shell)",
    "F": "Dos pasadas con deflector longitudinal (two pass shell)",
    "G": "Flujo partido (split flow)",
    "H": "Flujo doble partido (double split flow)",
    "J": "Flujo dividido (divided flow)",
    "K": "Caldera (kettle type)",
    "X": "Flujo cruzado puro (cross flow)",
}

DESCRIPCION_CABEZAL: Dict[str, str] = {
    "A": "Canal con cubierta desmontable",
    "B": "Bonete (cubierta integral)",
    "C": "Canal integral con el espejo y cubierta desmontable (haz extraíble por un extremo)",
    "D": "Cierre especial de alta presión",
    "N": "Canal integral con el espejo y cubierta desmontable (espejo fijo)",
    "L": "Espejo fijo con canal tipo «A»",
    "M": "Espejo fijo con bonete tipo «B»",
    "P": "Cabezal flotante con prensaestopas exterior",
    "S": "Cabezal flotante con anillo de retención (backing device)",
    "T": "Cabezal flotante de paso por la coraza (pull through)",
    "U": "Haz en U (tubos curvados en el extremo trasero)",
    "W": "Espejo flotante sellado exteriormente (anillo linterna)",
}

# Tipos de cabeza segun la forma de la cubierta (para el espesor T_c).
_CUBIERTA_TORIESFERICA = ("B", "M")          # bonete integral
_CUBIERTA_NINGUNA = ("U",)                    # haz en U: no hay cubierta trasera

CORROSION_DEFECTO = 3.2e-3   # 1/8 in, margen de corrosion tipico TEMA Clase C
EFICIENCIA_JUNTA = 0.85      # E, soldadura a tope con radiografia por puntos

# Tolerancia del chequeo de empaquetamiento del haz. El conteo de tubos del
# sizing termico proviene de una correlacion empirica (Serth, con C_L y C_TP)
# y el de aqui de un cociente de areas: ambos son estimaciones y difieren en
# los efectos de borde, dominantes en corazas pequenas. Por debajo de esta
# tolerancia la discrepancia se reporta como advertencia, no como error.
TOL_EMPAQUE = 0.05           # 5 %

# Factor de junta de la junta plana para el paso maximo entre pernos
# (RCB-11.2.2: B_max = 2*d_B + 6t/(m+0.5)); m = 3.0 es tipico de junta
# elastomerica o de fibra comprimida.
GASKET_FACTOR_M = 3.0


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

    rho_s: float = 1000.0      # Densidad del fluido de coraza [kg/m3]
    rho_t: float = 1000.0      # Densidad del fluido de tubos [kg/m3]
    m_dot_s: float = 0.0       # Caudal masico lado coraza [kg/s]
    m_dot_t: float = 0.0       # Caudal masico lado tubos [kg/s]

    P_diseno_s: float = 1.0e6  # Presion de diseno lado coraza [Pa]
    P_diseno_t: float = 1.0e6  # Presion de diseno lado tubos [Pa]
    material: str = "Acero al carbono"
    material_tubo: str = "Acero al carbono"
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
    rho_v2: float = 0.0   # Producto rho*V^2 real [Pa] (RCB-4.6.1 / 4.6.3)


@dataclass
class Brida:
    """Resultado del dimensionamiento de la brida de carcasa."""
    f_w: float            # Ancho radial de brida [m]
    D_F: float            # Diametro exterior de brida [m]
    D_BC: float           # Diametro del circulo de pernos [m]
    n_pernos: int
    d_perno: float
    paso_pernos: float = 0.0   # Paso real entre pernos [m] (RCB-11.2.2)


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
    soportes_simples: bool = False   # True en coraza X (sin corte)


@dataclass
class TieRods:
    """Varillas tensores y espaciadores (TEMA CB-4.7.1)."""
    cantidad: int
    d: float              # Diametro de la varilla [m]


@dataclass
class Cabezal:
    """Descripcion y cubierta de un cabezal TEMA (frontal o trasero)."""
    tipo: str
    posicion: str         # 'frontal' | 'trasero'
    descripcion: str
    tipo_cubierta: str    # 'Plana apernada' | 'Toriesferica (bonete)' | 'No aplica'
    T_c: float            # Espesor de cubierta [m] (0 si no hay cubierta)
    espejo_fijo: bool     # True si el espejo de ese extremo es fijo
    nota: str = ""


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
    tipo_carcasa: str
    cab_frontal: Cabezal
    cab_trasero: Cabezal
    tie_rods: TieRods
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


def _luz_maxima_tubo(d_o: float, material_tubo: str = "Acero al carbono") -> float:
    """Luz maxima sin soporte (RCB-4.5.2) para el tubo y material dados."""
    fila = min(_LUZ_MAX_TUBO, key=lambda t: abs(t[0] - d_o))
    nombre = (material_tubo or "").lower()
    grupo = 1 if any(clave in nombre for clave in _MATERIALES_GRUPO_B) else 0
    return fila[1][grupo]


def seleccionar_tuberia(D_min: float) -> Tuple[str, float, float]:
    """Primera tuberia Sch-40 comercial cuyo D_i alcanza el minimo requerido."""
    for nps, d_i, d_e in _NPS_SCH40:
        if d_i >= D_min:
            return nps, d_i, d_e
    raise ErrorDiseno(
        titulo="Caudal excesivo para una única boquilla",
        que_paso=f"El diámetro interior mínimo de la boquilla resulta "
                 f"{D_min*1000:.0f} mm y la mayor tubería comercial tabulada "
                 f"es 24 in (610 mm).",
        por_que="La velocidad admisible (criterio ρ·V² de TEMA) no da abasto "
                "con una sola abertura para este caudal.",
        solucion="Divida el caudal en dos (o más) boquillas de entrada/salida "
                 "o use una boquilla cónica fabricada a medida.",
        referencia="TEMA RCB-4.6.1 · tubería comercial Sch-40",
    )


def _validar_material(material: str) -> float:
    if material not in S_ADMISIBLE:
        raise ErrorDiseno(
            titulo=f"Material «{material}» sin esfuerzo admisible tabulado",
            que_paso=f"Se pidió calcular con el material «{material}».",
            por_que="Los espesores se calculan con ASME VIII Div. 1, que "
                    "necesita el esfuerzo admisible S del material a la "
                    "temperatura de diseño.",
            solucion=f"Use uno de los materiales tabulados: "
                     f"{', '.join(S_ADMISIBLE)}.",
            referencia="ASME BPVC VIII Div. 1 · UG-27 / UG-34",
        )
    return S_ADMISIBLE[material]


def _espesor_min_baffle(D_s: float, luz: float) -> float:
    """Espesor minimo de placa (CB-4.4.1) por D_s y luz sin soporte."""
    fila = next(v for lim, v in _ESPESOR_BAFFLE if D_s <= lim)
    idx = 0
    for lim in _LUZ_BAFFLE_LIMITES:
        if luz > lim:
            idx += 1
    return fila[idx]


# =============================================================================
# 4. CARCASA: ESPESOR Y DIAMETRO EXTERNO  (Eqs. 19-20 / CB-3.1.3)
# =============================================================================
def espesor_carcasa(D_s: float, P: float, material: str,
                    corrosion: float = CORROSION_DEFECTO,
                    E: float = EFICIENCIA_JUNTA) -> float:
    """
    Espesor de pared de la carcasa cilindrica.

    ASME VIII Div.1 UG-27(c)(1), esfuerzo circunferencial:
        T_s = P*R / (S*E - 0.6*P)   + margen de corrosion
    El resultado se acota por el espesor minimo nominal de la Tabla CB-3.1.3
    del estandar TEMA (Clase C/B).
    """
    if D_s <= 0:
        raise ErrorDiseno(
            titulo="Diámetro de coraza no válido",
            que_paso=f"D_s = {D_s:.4f} m no es un diámetro positivo.",
            por_que="El dimensionamiento mecánico necesita un diámetro "
                    "interior de coraza real (resultado del sizing térmico).",
            solucion="Ejecute primero un dimensionamiento térmico (F5) y "
                     "revise que devuelva un D_s positivo.",
            referencia="ASME BPVC VIII Div. 1 · UG-27",
        )
    if P <= 0:
        raise ErrorDiseno(
            titulo="Presión de diseño no válida",
            que_paso=f"P = {P/1e5:.2f} bar no es una presión positiva.",
            por_que="Los espesores se calculan para la presión de diseño del "
                    "lado correspondiente; una presión nula o negativa no "
                    "define ninguna condición de servicio.",
            solucion="Cargue la presión de diseño (en bar) en la pestaña "
                     "Design, bloque «Diseño mecánico».",
            referencia="ASME BPVC VIII Div. 1 · UG-27",
        )

    S = _validar_material(material)
    if P >= 0.385 * S * E:
        raise ErrorDiseno(
            titulo="Presión excesiva para pared delgada",
            que_paso=f"La presión de diseño ({P/1e5:.1f} bar) supera el límite "
                     f"0.385·S·E = {0.385*S*E/1e5:.1f} bar de la fórmula de "
                     f"pared delgada de UG-27 con {material}.",
            por_que="Por encima de ese límite la distribución de esfuerzos "
                    "atraves de el espesor deja de ser lineal y UG-27(c)(1) "
                    "no es aplicable.",
            solucion="Use un material con mayor S, aumente la eficiencia de "
                     "junta o realice el análisis de pared gruesa (ASME VIII "
                     "Div. 1, Apéndice 1-2), fuera del alcance de esta "
                     "herramienta.",
            referencia="ASME BPVC VIII Div. 1 · UG-27(c)(1)",
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
    if cabezal_trasero not in HOLGURA_HAZ:
        raise ErrorDiseno(
            titulo=f"Cabezal trasero TEMA «{cabezal_trasero}» no reconocido",
            que_paso=f"Se pidió el tipo de cabezal trasero "
                     f"«{cabezal_trasero}».",
            por_que="La Figura N-1.2 del estándar TEMA define los tipos de "
                    f"cabezal trasero: {', '.join(CABEZALES_TRASEROS)}.",
            solucion=f"Seleccione uno de: {', '.join(CABEZALES_TRASEROS)}.",
            referencia="TEMA, Figura N-1.2 (Table of TEMA types)",
        )
    D_otl = D_s - HOLGURA_HAZ[cabezal_trasero]
    D_ctl = D_otl - d_o
    if D_ctl <= 0:
        raise ErrorDiseno(
            titulo="La coraza es demasiado pequeña para el haz",
            que_paso=f"D_ctl resulta negativo: con D_s = {D_s*1000:.0f} mm, "
                     f"tubo de {d_o*1000:.1f} mm y la holgura del cabezal "
                     f"«{cabezal_trasero}» no queda espacio para el anillo "
                     f"exterior de tubos.",
            por_que="El círculo de centros periféricos (D_ctl) debe quedar "
                    "dentro de la coraza con la holgura que fija el tipo de "
                    "cabezal trasero.",
            solucion="Aumente D_s en el sizing térmico (más tubos por paso o "
                     "mayor pitch) o use tubos más delgados.",
            referencia="Tan & Fok (2006), Eqs. 21-22",
        )
    return D_otl, D_ctl


# =============================================================================
# 6. ESPEJO DE TUBOS  (Eq. 23 / TEMA C-7.1.1)
# =============================================================================
def espesor_espejo(D_s: float, d_o: float,
                   corrosion: float = CORROSION_DEFECTO) -> float:
    """
    Espesor del espejo de tubos.

    TEMA C-7.1.1 (Clase C): en las zonas donde los tubos se expanden, el
    espesor total MENOS el margen de corrosion no puede ser menor que
        3/4 * d_o           para d_o <= 1 in (25.4 mm)
        7/8 in (22.2 mm)    para d_o = 1-1/4 in
        1 in   (25.4 mm)    para d_o = 1-1/2 in
        1-1/4 in (31.8 mm)  para d_o = 2 in
    y el espesor total (con corrosion) nunca baja de 3/4 in (19.1 mm).

    Se combina con la regla practica L_ts = 0.1 * D_s (Tan & Fok, Eq. 23).
    """
    if d_o <= 0.0254:
        t_min_C = 0.75 * d_o
    elif d_o <= 0.03175:
        t_min_C = 0.0222
    elif d_o <= 0.0381:
        t_min_C = 0.0254
    else:
        t_min_C = 0.0318
    return max(0.1 * D_s, t_min_C + corrosion, 0.0191)


# =============================================================================
# 7. BOQUILLAS  (Eqs. 24-26 / TEMA RCB-4.6.1 y RCB-4.6.3)
# =============================================================================
def dimensionar_boquilla(lado: str, m_dot: float, rho: float,
                         P: float, material: str,
                         corrosion: float = CORROSION_DEFECTO,
                         E: float = EFICIENCIA_JUNTA) -> Boquilla:
    """
    Diametro interior minimo de boquilla que evita erosion del haz.

    Criterio TEMA RCB-4.6.1 (lado coraza, fluido monofasico no abrasivo):
        rho * V^2 <= 2232 Pa   (1500 lbm/ft*s^2)
    y tope practico de 3 m/s para liquidos (erosion de la abertura).
    En lado tubos el criterio de erosion de los extremos (RCB-4.6.3) es
    rho * V^2 <= 8928 Pa (6000 lbm/ft*s^2), verificado aparte.

        A_n = m_dot / (rho * V_max)  ->  D_min = sqrt(4*A_n/pi)

    Luego se escoge la primera tuberia Sch-40 comercial con D_i >= D_min y se
    verifica su espesor con UG-27.
    """
    if m_dot <= 0:
        raise ErrorDiseno(
            titulo=f"Caudal nulo en la boquilla de {lado}",
            que_paso=f"El caudal másico del lado {lado} es {m_dot} kg/s.",
            por_que="Sin caudal no hay área de abertura que dimensionar; un "
                    "caudal negativo no es físico.",
            solucion="Cargue un caudal másico positivo para ambas corrientes.",
            referencia="TEMA RCB-4.6.1",
        )
    if rho <= 0:
        raise ErrorDiseno(
            titulo=f"Densidad no válida en el lado {lado}",
            que_paso=f"rho = {rho} kg/m³.",
            por_que="La densidad entra directamente en el criterio ρ·V² y en "
                    "la conversión caudal → velocidad.",
            solucion="Revise los datos de la corriente; la densidad se evalúa "
                     "a la temperatura media del lado.",
            referencia="TEMA RCB-4.6.1",
        )

    # RCB-4.6.1: 2232 Pa para fluido monofasico no abrasivo. Para liquidos se
    # acota ademas a 3 m/s por erosion practica de la abertura.
    V_max = math.sqrt(RHO_V2_CORAZA / rho)
    if rho >= 50.0:                     # liquidos
        V_max = min(V_max, V_BOQUILLA_MAX_PRACTICO)
    A_n = m_dot / (rho * V_max)
    D_min = math.sqrt(4.0 * A_n / math.pi)

    nps, D_i, D_e = seleccionar_tuberia(D_min)
    V_real = m_dot / (rho * math.pi * D_i ** 2 / 4.0)

    S = _validar_material(material)
    t = P * (D_i / 2.0) / (S * E - 0.6 * P) + corrosion
    t = max(t, (D_e - D_i) / 2.0)   # nunca menor que la pared Sch-40 real

    return Boquilla(lado=lado, V_max=V_max, D_min=D_min, nps=nps,
                    D_i=D_i, D_e=D_e, espesor=t, V_real=V_real,
                    rho_v2=rho * V_real ** 2)


# =============================================================================
# 8. BRIDAS  (Eqs. 27-28 / TEMA C-11.1 y RCB-11.2.2)
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
    pernos, redondeado al multiplo de 4 superior (minimo 8). El paso real
    resultante se reporta para poder contrastarlo con el maximo de
    RCB-11.2.2:  B_max = 2*d_B + 6t/(m + 0.5).

    TEMA C-11.1 (Clase C): perno minimo recomendado 1/2 in (12.7 mm).
    """
    if d_perno <= 0:
        raise ErrorDiseno(
            titulo="Diámetro de perno no válido",
            que_paso=f"d_B = {d_perno*1000:.1f} mm.",
            por_que="Los pernos de la brida de carcasa deben ser positivos y "
                    "cumplir el mínimo de la norma.",
            solucion="Cargue un diámetro de perno ≥ 12.7 mm (1/2 in).",
            referencia="TEMA C-11.1",
        )
    if d_perno < 0.5 * IN:
        raise ErrorDiseno(
            titulo="Perno por debajo del mínimo TEMA Clase C",
            que_paso=f"El perno cargado es de {d_perno*1000:.1f} mm y la "
                     f"Clase C exige al menos 1/2 in (12.7 mm).",
            por_que="Pernos más finos no garantizan el apriete uniforme de la "
                    "junta de la brida (Clase R exige 3/4 in, Clase B 5/8 in).",
            solucion="Cambie el «Ø de perno de brida» a 12.7 mm o más.",
            referencia="TEMA C-11.1 (mínimo Clase C)",
        )

    f_w = 3.0 * (1.5 * d_perno)
    D_F = D_o + 2.0 * f_w + 0.004
    D_BC = D_o + f_w

    n = math.ceil(math.pi * D_BC / (4.0 * d_perno))
    n = max(8, int(math.ceil(n / 4.0) * 4))
    paso = math.pi * D_BC / n

    return Brida(f_w=f_w, D_F=D_F, D_BC=D_BC, n_pernos=n, d_perno=d_perno,
                 paso_pernos=paso)


# =============================================================================
# 9. PLACAS DEFLECTORAS  (Eqs. 29-30 / TEMA RCB-4.3, RCB-4.4.1, RCB-4.5)
# =============================================================================
def dimensionar_baffles(D_s: float, L: float, d_o: float, L_bc: float,
                        corte: float = 0.25,
                        tipo_carcasa: str = "E",
                        material_tubo: str = "Acero al carbono") -> Baffles:
    """
    Deflectores segmentados simples (segmento transversal) o placas soporte.

        N_B = L / L_bc - 1
        altura del corte = corte * D_s
        D_baffle = D_s - holgura diametral (RCB-4.3)

    En carcasa tipo X (flujo cruzado puro) no hay deflectores transversales;
    solo placas soporte, espaciadas por la luz maxima sin soporte RCB-4.5.2.
    En G, H y J el flujo es partido/dividido y el baffle es de apoyo: se
    mantiene el segmental simple como aproximacion conservadora.
    """
    tipo_carcasa = tipo_carcasa.upper()
    if tipo_carcasa not in TIPOS_CARCASA:
        raise ErrorDiseno(
            titulo=f"Tipo de coraza TEMA «{tipo_carcasa}» no soportado",
            que_paso=f"Se pidió el tipo de coraza «{tipo_carcasa}».",
            por_que="La Figura N-1.2 del estándar TEMA solo define los tipos "
                    f"{', '.join(TIPOS_CARCASA)}.",
            solucion=f"Seleccione uno de: {', '.join(TIPOS_CARCASA)}.",
            referencia="TEMA, Figura N-1.2 (Table of TEMA types)",
        )
    if L <= 0:
        raise ErrorDiseno(
            titulo="Longitud de tubos no válida",
            que_paso=f"L = {L:.3f} m.",
            por_que="La longitud efectiva del tubo determina el número de "
                    "deflectores y la luz sin soporte.",
            solucion="Cargue una longitud de tubo positiva (0.3 – 12 m).",
            referencia="TEMA RCB-2.1 (longitudes comerciales: 2.438 / 3.048 / "
                       "3.658 / 4.877 / 6.096 m)",
        )
    if L_bc <= 0:
        raise ErrorDiseno(
            titulo="Espaciado de baffles no válido",
            que_paso=f"L_bc = {L_bc:.3f} m.",
            por_que="El espaciado entre deflectores no puede ser nulo ni "
                    "negativo (RCB-4.5.1 exige como mínimo D_s/5 o 2 in, lo "
                    "mayor).",
            solucion="Cargue un espaciado de baffles positivo; el botón "
                     "«½·D_s» lo ajusta tras el primer cálculo.",
            referencia="TEMA RCB-4.5.1",
        )

    luz_max = _luz_maxima_tubo(d_o, material_tubo)

    if tipo_carcasa == "X":
        # Sin deflectores: solo soportes al maximo tramo permitido.
        L_bc = min(L_bc, luz_max)
        N_B = max(int(math.ceil(L / L_bc)) - 1, 0)
        corte = 0.0
    else:
        if not (0.15 <= corte <= 0.45):
            raise ErrorDiseno(
                titulo="Corte de baffle fuera de rango",
                que_paso=f"El corte pedido es {corte*100:.0f} % de D_s y el "
                         f"rango práctico es 15 – 45 %.",
                por_que="El corte define el área de la ventana por donde el "
                        "fluido de coraza cruza de un compartimento al "
                        "siguiente: el óptimo de Kern está entre 20 y 25 %.",
                solucion="Cambie el «Corte de baffle» a un valor entre 15 y "
                         "45 % (estándar: 25 %).",
                referencia="TEMA RCB-4.1 (baffle cuts)",
            )
        if not (D_s / 5.0 <= L_bc <= D_s):
            raise ErrorDiseno(
                titulo="Espaciado de baffles fuera del rango TEMA",
                que_paso=f"L_bc = {L_bc*1000:.0f} mm y el rango permitido para "
                         f"esta coraza (D_s = {D_s*1000:.0f} mm) es "
                         f"[{D_s/5*1000:.0f} mm ; {D_s*1000:.0f} mm].",
                por_que="RCB-4.5.1 prohíbe espaciar los baffles a menos de "
                        "D_s/5 (o 2 in) ni a más de un diámetro de coraza.",
                solucion=f"Use el botón «½·D_s» para fijar B = "
                         f"{D_s*500:.0f} mm y vuelva a calcular.",
                referencia="TEMA RCB-4.5.1",
            )
        # floor + 1e-9 evita el truncamiento IEEE-754 (p. ej. 0.6/0.2 = 2.9999...)
        N_B = max(int(math.floor(L / L_bc + 1e-9)) - 1, 0)

    # Espaciado de entrada/salida: absorbe la longitud sobrante de los extremos.
    L_bi = (L - (N_B - 1) * L_bc) / 2.0 if N_B >= 1 else L / 2.0

    # Tramo sin soporte: en la ventana el tubo salta un deflector.
    luz = 2.0 * L_bc if tipo_carcasa != "X" else L_bc
    if luz > luz_max:
        raise ErrorDiseno(
            titulo="Luz sin soporte excesiva (riesgo de vibración)",
            que_paso=f"El tramo de tubo sin soporte resulta "
                     f"{luz*1000:.0f} mm y el máximo de RCB-4.5.2 para tubos "
                     f"de {d_o*1000:.1f} mm ({material_tubo}) es "
                     f"{luz_max*1000:.0f} mm.",
            por_que="Un tubo tan largo entre apoyos vibra con el flujo de "
                    "coraza y puede romperse por fatiga (TEMA RCB-4.5.6).",
            solucion=f"Reduzca el espaciado de baffles a {luz_max*1000/2:.0f} "
                     "mm o menos, o agregue placas soporte.",
            referencia="TEMA Tabla RCB-4.5.2 (luz máxima sin soporte)",
        )

    # Espesor de placa segun D_s y la luz sin soporte (CB-4.4.1).
    espesor = _espesor_min_baffle(D_s, luz)
    D_baffle = D_s - _buscar_rango(_HOLGURA_BAFFLE, D_s)

    return Baffles(N_B=N_B, L_bc=L_bc, L_bi=L_bi, espesor=espesor,
                   D_baffle=D_baffle, altura_corte=corte * D_s,
                   luz_sin_soporte=luz, soportes_simples=(tipo_carcasa == "X"))


# =============================================================================
# 10. VARILLAS TENSORES  (TEMA CB-4.7.1)
# =============================================================================
def dimensionar_tie_rods(D_s: float) -> TieRods:
    """Varillas tensores y espaciadores minimos (CB-4.7.1, Clase C/B)."""
    for limite, d, n in _TIE_RODS:
        if D_s <= limite:
            return TieRods(cantidad=n, d=d)
    return TieRods(cantidad=12, d=0.01588)


# =============================================================================
# 11. CABEZALES: ESPESOR DE CUBIERTA  (Eqs. 31-32 / UG-32, UG-34)
# =============================================================================
def _espesor_cubierta_plana(D_s: float, P: float, material: str,
                            corrosion: float, E: float) -> float:
    """UG-34: cubierta plana apernada, T_c = D_s*sqrt(C*P/(S*E)) + corrosion."""
    S = _validar_material(material)
    C = 0.3   # cubierta plana apernada con junta en todo el ancho
    return D_s * math.sqrt(C * P / (S * E)) + corrosion


def _espesor_cubierta_toriesferica(D_s: float, P: float, material: str,
                                   corrosion: float, E: float) -> float:
    """UG-32(e): bonete toriesferico de relacion 6 %."""
    S = _validar_material(material)
    if P >= 0.665 * S * E:
        raise ErrorDiseno(
            titulo="Presión excesiva para un bonete toriesférico",
            que_paso=f"La presión de diseño ({P/1e5:.1f} bar) supera el límite "
                     f"0.665·S·E = {0.665*S*E/1e5:.1f} bar de UG-32 para este "
                     f"material.",
            por_que="Fuera de ese límite la cabeza de pared delgada deja de "
                    "ser válida según el Código.",
            solucion="Use un cabezal plano reforzado (tipo A/C/N) o un "
                     "material con mayor esfuerzo admisible.",
            referencia="ASME BPVC VIII Div. 1 · UG-32(e)",
        )
    return 0.885 * P * D_s / (S * E - 0.1 * P) + corrosion


def espesor_cubierta(D_s: float, P: float, material: str,
                     cabezal: str = "A",
                     corrosion: float = CORROSION_DEFECTO,
                     E: float = EFICIENCIA_JUNTA) -> Tuple[float, str]:
    """
    Espesor T_c de la cubierta del cabezal. Devuelve (espesor, descripcion).

    Cabezal B o M (bonete toriesferico) -> ASME UG-32(e), relacion 6 %.
    Cualquier otro (A, C, N, D y cabezales flotantes P/S/T/W) -> ASME UG-34
    con cubierta plana apernada, C = 0.3.
    El tipo D (cierre especial de alta presion) se estima igual pero se marca
    con advertencia: la norma exige un analisis propio del cierre.
    """
    cabezal = cabezal.upper()
    if cabezal == "D":
        t = _espesor_cubierta_plana(D_s, P, material, corrosion, E)
        return t, "Plana apernada, cierre especial de alta presión (tipo D)"
    if cabezal in _CUBIERTA_TORIESFERICA:
        t = _espesor_cubierta_toriesferica(D_s, P, material, corrosion, E)
        return t, f"Toriesférica (bonete tipo {cabezal})"
    if cabezal in ("A", "C", "N"):
        t = _espesor_cubierta_plana(D_s, P, material, corrosion, E)
        return t, f"Plana apernada (canal tipo {cabezal})"
    if cabezal in ("L", "P", "S", "T", "W"):
        t = _espesor_cubierta_plana(D_s, P, material, corrosion, E)
        return t, f"Plana apernada (cabezal trasero tipo {cabezal})"
    if cabezal in _CUBIERTA_NINGUNA:
        return 0.0, "No aplica (haz en U)"
    raise ErrorDiseno(
        titulo=f"Cabezal TEMA «{cabezal}» no reconocido",
        que_paso=f"Se pidió calcular la cubierta del tipo «{cabezal}».",
        por_que="La Figura N-1.2 del estándar TEMA define los tipos frontales "
                f"({', '.join(CABEZALES_FRONTALES)}) y los traseros "
                f"({', '.join(CABEZALES_TRASEROS)}).",
        solucion="Seleccione el cabezal desde el menú desplegable "
                 "correspondiente de la pestaña Design.",
        referencia="TEMA, Figura N-1.2 (Table of TEMA types)",
    )


def construir_cabezal(posicion: str, tipo: str, D_s: float, D_otl: float,
                      P: float, material: str,
                      corrosion: float, E: float) -> Cabezal:
    """Arma la ficha completa (descripcion + cubierta) de un cabezal TEMA."""
    tipo = tipo.upper()
    valido = CABEZALES_FRONTALES if posicion == "frontal" else CABEZALES_TRASEROS
    if tipo not in valido:
        raise ErrorDiseno(
            titulo=f"Cabezal {posicion} TEMA «{tipo}» no reconocido",
            que_paso=f"Se pidió el tipo «{tipo}» para el cabezal {posicion}.",
            por_que=f"Los tipos válidos ({posicion}) son: "
                    f"{', '.join(valido)} (Figura N-1.2 del estándar TEMA).",
            solucion=f"Seleccione uno de: {', '.join(valido)}.",
            referencia="TEMA, Figura N-1.2 (Table of TEMA types)",
        )
    # Base de calculo de la cubierta: el canal fijo se calcula sobre D_s; los
    # cabezales flotantes P/S/T/W apoyan sobre el limite del haz (D_otl).
    base = D_otl if tipo in ("P", "S", "T", "W") else D_s
    T_c, tipo_cubierta = espesor_cubierta(base, P, material, tipo,
                                          corrosion, E)
    if tipo in _CUBIERTA_NINGUNA:
        T_c, tipo_cubierta = 0.0, "No aplica (haz en U)"

    espejo_fijo = tipo in ("A", "B", "C", "D", "N", "L", "M")
    nota = ""
    if tipo == "D":
        nota = ("Cierre especial de alta presión: el espesor mostrado es una "
                "estimación por UG-34; la norma exige un análisis específico "
                "del cierre (ASME VIII Div. 1, Apéndice 2 / Div. 2).")
    elif tipo == "U":
        nota = ("Haz en U: los tubos se curvan en el extremo trasero, no hay "
                "espejo ni cubierta trasera. La limpieza interior de los tubos "
                "solo es posible por el extremo frontal.")
    elif tipo in ("P", "S", "T", "W"):
        nota = ("Cabezal flotante: absorbe la dilatación térmica diferencial "
                "entre haz y coraza; requiere verificación del conjunto "
                "flotante (apriete, apoyo del haz y extracción).")
    return Cabezal(tipo=tipo, posicion=posicion,
                   descripcion=DESCRIPCION_CABEZAL.get(tipo, tipo),
                   tipo_cubierta=tipo_cubierta, T_c=T_c,
                   espejo_fijo=espejo_fijo, nota=nota)


# =============================================================================
# 12. ORQUESTADOR
# =============================================================================
def disenar_mecanico(inp: MechanicalInput) -> MechanicalResult:
    """Ejecuta el dimensionamiento mecanico completo y valida la coherencia."""
    # --- Sanity checks de entrada ---------------------------------------
    if inp.D_s <= 0 or inp.L <= 0:
        raise ErrorDiseno(
            titulo="Geometría térmica incompleta",
            que_paso=f"D_s = {inp.D_s:.4f} m, L = {inp.L:.3f} m.",
            por_que="El dimensionamiento mecánico parte del D_s y la longitud "
                    "que entrega el sizing térmico.",
            solucion="Ejecute primero el dimensionamiento térmico (F5).",
            referencia="Flujo de trabajo: sizing → mecánico",
        )
    if inp.N_tt <= 0:
        raise ErrorDiseno(
            titulo="Número de tubos no válido",
            que_paso=f"N_tt = {inp.N_tt}.",
            por_que="El empaque del haz se verifica contra el número de tubos "
                    "del cálculo térmico.",
            solucion="Ejecute el sizing (F5) y compruebe que devuelva un "
                     "número de tubos entero positivo.",
            referencia="Tan & Fok (2006), Eqs. 21-22",
        )
    if inp.d_o <= 0 or inp.P_T <= inp.d_o:
        raise ErrorDiseno(
            titulo="Pitch incompatible con el tubo",
            que_paso=f"Pitch P_T = {inp.P_T*1000:.1f} mm y diámetro exterior "
                     f"del tubo = {inp.d_o*1000:.1f} mm.",
            por_que="El pitch debe ser mayor que el diámetro exterior del tubo "
                    "para que exista claro de paso de fluido; TEMA exige "
                    "P_T ≥ 1.25·d_o.",
            solucion=f"Cargue un pitch ≥ {1.25*inp.d_o*1000:.1f} mm.",
            referencia="TEMA RCB-2.2 (pitch ≥ 1.25·d_o)",
        )

    advertencias: List[str] = []
    L_bc = inp.L_bc if inp.L_bc > 0 else 0.5 * inp.D_s
    tipo_carcasa = inp.tipo_carcasa.upper()

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
    L_ts = espesor_espejo(inp.D_s, inp.d_o, inp.corrosion)

    # Verificacion de empaquetamiento. El area disponible para las celdas de
    # tubo es la del circulo que ENVUELVE a los tubos perifericos (D_otl): el
    # circulo que pasa por sus centros (D_ctl) recorta media celda de todo el
    # anillo exterior y subestima el conteo frente a la correlacion de Serth
    # del sizing termico, que se referencia a D_s.
    area_disponible = math.pi * D_otl ** 2 / 4.0
    area_por_tubo = (math.sqrt(3) / 2.0) * inp.P_T ** 2  # celda triangular
    n_max = int(area_disponible / area_por_tubo)
    if inp.N_tt > n_max * (1.0 + TOL_EMPAQUE):
        raise ErrorDiseno(
            titulo="Los tubos no caben dentro de la coraza",
            que_paso=f"No caben {inp.N_tt} tubos con pitch "
                     f"{inp.P_T*1000:.1f} mm dentro de D_otl = "
                     f"{D_otl*1000:.0f} mm (máximo geométrico ≈ {n_max}, "
                     f"exceso {100.0*(inp.N_tt/n_max - 1.0):.0f} %).",
            por_que="El área del círculo que envuelve a los tubos periféricos "
                    "no da abasto para el número de tubos pedido con ese "
                    "pitch.",
            solucion=f"Aumente D_s en el sizing térmico (o reduzca el pitch a "
                     f"al menos {1.25*inp.d_o*1000:.1f} mm) hasta que quepan "
                     f"unos {n_max} tubos.",
            referencia="Tan & Fok (2006), Eqs. 21-22 · chequeo de empaque",
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
                                  inp.corte_baffle, tipo_carcasa,
                                  inp.material_tubo)

    # --- Varillas tensores (CB-4.7.1) ------------------------------------
    tie_rods = dimensionar_tie_rods(inp.D_s)

    # --- Bridas ----------------------------------------------------------
    brida = dimensionar_brida(D_o, inp.d_perno)
    # RCB-11.2.2: paso maximo entre pernos B_max = 2*d_B + 6t/(m+0.5).
    t_fl = max(T_s, 1.5 * inp.d_perno)
    B_max = 2.0 * inp.d_perno + 6.0 * t_fl / (GASKET_FACTOR_M + 0.5)
    if brida.paso_pernos > B_max:
        advertencias.append(
            f"El paso entre pernos ({brida.paso_pernos*1000:.0f} mm) supera el "
            f"máximo recomendado RCB-11.2.2 ({B_max*1000:.0f} mm con t ≈ "
            f"{t_fl*1000:.0f} mm): aumente el número de pernos o el espesor "
            "de la brida."
        )

    # --- Boquillas -------------------------------------------------------
    boq_s = boq_t = None
    if inp.m_dot_s > 0:
        boq_s = dimensionar_boquilla("coraza", inp.m_dot_s, inp.rho_s,
                                     inp.P_diseno_s, inp.material,
                                     inp.corrosion)
        if boq_s.D_i > inp.D_s / 3.0:
            advertencias.append(
                f"La boquilla de coraza ({boq_s.nps}) supera D_s/3: requiere "
                f"placa de impacto y refuerzo de abertura (TEMA RCB-4.6.2)."
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
        if inp.rho_t >= 50.0 and boq_t.rho_v2 > RHO_V2_TUBOS:
            advertencias.append(
                f"El líquido en la boquilla de tubos supera ρ·V² = 6000 "
                f"lb/ft·s² ({boq_t.rho_v2:.0f} Pa): TEMA RCB-4.6.3 exige "
                "protección contra erosión en los extremos de los tubos."
            )

    # --- Cabezales (Figura N-1.2) ---------------------------------------
    cab_f = construir_cabezal("frontal", inp.cabezal_frontal, inp.D_s, D_otl,
                              inp.P_diseno_t, inp.material, inp.corrosion,
                              EFICIENCIA_JUNTA)
    cab_t = construir_cabezal("trasero", inp.cabezal_trasero, inp.D_s, D_otl,
                              inp.P_diseno_s, inp.material, inp.corrosion,
                              EFICIENCIA_JUNTA)
    T_c, tipo_cubierta = cab_f.T_c, cab_f.tipo_cubierta

    # --- Compatibilidades y avisos por tipo TEMA -------------------------
    if tipo_carcasa == "F":
        advertencias.append(
            "Carcasa tipo F: debe agregarse un deflector longitudinal "
            "soldado o sellado; la caida de presion sera ~8 veces la de una E."
        )
    elif tipo_carcasa in ("G", "H", "J"):
        advertencias.append(
            f"Carcasa tipo {tipo_carcasa} (flujo partido/dividido): la caída "
            "de presión del lado coraza será mucho menor que en una E y el "
            "coeficiente se calcula con las correlaciones de baffles "
            "segmentados como aproximación."
        )
    elif tipo_carcasa == "K":
        advertencias.append(
            "Carcasa tipo K (caldera): el diámetro de la caldera depende de la "
            "separación de vapor (espacio libre sobre el haz), no del empaque "
            "de tubos; aquí solo se dimensiona el haz. Las calderas K suelen "
            "llevar cabezal flotante extraíble (T) o con anillo partido (S)."
        )
    if tipo_carcasa == "K" and inp.cabezal_trasero in ("L", "M", "N"):
        advertencias.append(
            "Caldera K con espejo fijo: el haz no podrá extraerse para "
            "limpieza. Considere un cabezal trasero T o S."
        )
    if cab_f.espejo_fijo and cab_t.espejo_fijo and inp.cabezal_frontal == "N" \
            and inp.cabezal_trasero == "N":
        advertencias.append(
            "Disposición NEN (canal y cabezal trasero integrales con los "
            "espejos, ambos fijos): es la más rígida del estándar TEMA. La "
            "dilatación térmica diferencial entre haz y coraza carga los "
            "tubos y los espejos; si ΔT es grande, use un cabezal flotante "
            "(P/S/T/W), haz en U (U) o una junta de expansión."
        )
    if inp.cabezal_frontal == "D":
        advertencias.append(cab_f.nota)
    if inp.cabezal_trasero == "U":
        advertencias.append(cab_t.nota)

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
        tipo_carcasa=tipo_carcasa, cab_frontal=cab_f, cab_trasero=cab_t,
        tie_rods=tie_rods, baffles=baffles, brida=brida,
        boquilla_coraza=boq_s, boquilla_tubos=boq_t,
        advertencias=advertencias,
    )


# =============================================================================
# 13. PRUEBA RAPIDA
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
        material_tubo="Acero al carbono",
        tipo_carcasa="E", cabezal_frontal="A", cabezal_trasero="M",
    )

    r = disenar_mecanico(caso)

    print("=" * 66)
    print(" DISENO MECANICO TEMA Clase 'C' - caso de prueba")
    print("=" * 66)
    print(f" Supuestos: P_dis = {caso.P_diseno_s/1e5:.0f} bar | "
          f"{caso.material} | m_s = {caso.m_dot_s:.0f} kg/s | "
          f"m_t = {caso.m_dot_t:.0f} kg/s")
    print(f" Tipo TEMA: coraza {r.tipo_carcasa} - frontal "
          f"{r.cab_frontal.tipo} - trasero {r.cab_trasero.tipo}")
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
    print(f"   Varillas tensores = {r.tie_rods.cantidad} de "
          f"{r.tie_rods.d*mm:.1f} mm (CB-4.7.1)")
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
