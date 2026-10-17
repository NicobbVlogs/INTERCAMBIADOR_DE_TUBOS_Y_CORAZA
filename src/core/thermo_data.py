# -*- coding: utf-8 -*-
"""
thermo_data.py  --  Base de datos termofisica (FASE 1 / CORE)
================================================================================
Unica fuente de verdad de propiedades para el diseno termico (Kern) y mecanico
(TEMA) del intercambiador de tubos y coraza.

API PUBLICA (no leer este archivo desde otros modulos, basta con esto):
--------------------------------------------------------------------------------
    from src.core.thermo_data import db, FluidState, SolidMaterial

    st = db.get_fluid_state("Agua", 25.0, unit="C")   # -> FluidState
    st.cp, st.mu, st.k, st.rho, st.Pr                 # SI: J/kg.K, Pa.s, W/m.K, kg/m3, -
    mat = db.get_material("Acero al carbono")         # -> SolidMaterial
    mat.k_m, mat.rho_m, mat.epsilon, mat.R_f          # W/m.K, kg/m3, m, m2.K/W

    db.list_fluids(), db.list_materials(), db.get_limits("Agua", unit="C")

CONVENCIONES
--------------------------------------------------------------------------------
* Todas las correlaciones reciben T en KELVIN y devuelven unidades SI.
* Los liquidos se evaluan como liquido saturado / comprimido (efecto de P
  despreciable en cp, mu, k, rho para el rango de operacion tipico de un STHE).
* Los gases (Aire, Vapor de agua) evaluan rho con gas ideal a la presion `P`
  (default 1 atm); cp, mu y k se toman a baja presion (independientes de P).

FUENTES DE LOS AJUSTES
--------------------------------------------------------------------------------
* Agua liquida 0-180 C ................ IAPWS-IF97 (tablas de liquido saturado).
* Vapor de agua 1 atm 380-870 K ....... Incropera, Tabla A.4 (vapor de agua).
* Aire 1 atm 200-1000 K ............... Incropera Tabla A.4; mu y k por
                                        correlaciones de Sutherland.
* Alcoholes / hidrocarburos / glicol .. Perry's Chemical Engineers' Handbook
                                        (8a ed.) y correlaciones tipo DIPPR.
* Amoniaco liquido saturado ........... ASHRAE / Perry's (liquido en equilibrio).
Los polinomios y las correlaciones de viscosidad fueron ajustados por minimos
cuadrados a esas tablas; el error maximo dentro del rango declarado es < 2 %
(tipicamente < 0.5 %). FUERA DEL RANGO SE LANZA ValueError: la extrapolacion de
una correlacion empirica NO es fisica.
"""

from __future__ import annotations

import math
import unicodedata
from dataclasses import dataclass
from typing import Dict, List, Tuple

__all__ = ["FluidState", "SolidMaterial", "ThermoDatabase", "db"]

# =============================================================================
# 1. CONSTANTES
# =============================================================================
P_ATM = 101325.0          # Pa
R_UNIV = 8314.462618      # J/kmol.K
M_AIR = 28.9647           # kg/kmol  -> R_aire = 287.05 J/kg.K
M_H2O = 18.01528          # kg/kmol  -> R_vapor = 461.52 J/kg.K
T_ABS_MIN = 1.0e-3        # K, cota fisica inferior


# =============================================================================
# 2. DATACLASSES (contenedores puros de datos)
# =============================================================================
@dataclass
class FluidState:
    """Estado termofisico de un fluido a una temperatura dada (unidades SI)."""
    cp: float    # Calor especifico           [J/kg.K]
    mu: float    # Viscosidad dinamica        [Pa.s]
    k: float     # Conductividad termica      [W/m.K]
    rho: float   # Densidad                   [kg/m3]
    Pr: float    # Numero de Prandtl = cp*mu/k  [-]


@dataclass
class SolidMaterial:
    """Propiedades de un material solido de construccion (tubos / coraza)."""
    k_m: float      # Conductividad termica del metal   [W/m.K]
    rho_m: float    # Densidad del metal                [kg/m3]
    epsilon: float  # Rugosidad absoluta superficial    [m]
    R_f: float      # Factor de ensuciamiento TEMA "C"  [m2.K/W]


# =============================================================================
# 3. HELPERS DE CORRELACION
# =============================================================================
def _poly(T: float, T0: float, c: Tuple[float, ...]) -> float:
    """Polinomio centrado: sum(c[i] * (T - T0)**i). Horner para velocidad."""
    x = T - T0
    r = 0.0
    for ci in reversed(c):
        r = r * x + ci
    return r


def _visc(T: float, A: float, B: float, C: float, D: float = 0.0) -> float:
    """Correlacion tipo DIPPR-101: mu = exp(A + B/T + C*ln(T) + D*T)  [Pa.s]."""
    return math.exp(A + B / T + C * math.log(T) + D * T)


def _rho_gas(T: float, P: float, M: float) -> float:
    """Gas ideal: rho = P*M/(Ru*T)  [kg/m3]."""
    return P * M / (R_UNIV * T)


def _mu_sutherland(T: float) -> float:
    """Viscosidad del aire, Sutherland (S = 110.4 K)  [Pa.s]."""
    return 1.458e-6 * T ** 1.5 / (T + 110.4)


def _k_sutherland(T: float) -> float:
    """Conductividad del aire, Sutherland modificada  [W/m.K]."""
    return 2.646e-3 * T ** 1.5 / (T + 245.4 * 10.0 ** (-12.0 / T))


# =============================================================================
# 4. CORRELACIONES POR FLUIDO  (T en K -> SI)
#    Cada fluido expone 4 lambdas (rho, cp, k, mu) + su ventana de validez.
# =============================================================================
# --- Agua liquida (0 - 180 C) -------------------------------------------------
_W_RHO = (958.59113, -0.72828162, -2.4965284e-03, 5.9318638e-06)
_W_CP = (4214.2189, 1.3269844, 1.2906468e-02, 1.6355491e-06)
_W_K = (0.68065260, 3.5954271e-04, -7.0932343e-06, 1.4032509e-08)
_W_MU = (-277.89087, 10474.536, 44.171694, -0.053434791)

# --- Vapor de agua, 1 atm (380 - 870 K) ---------------------------------------
_S_CP = (2017.6314, 0.58496920, 1.8398917e-03, -6.3336849e-06)
_S_K = (0.042109799, 8.2928126e-05, 1.3815150e-08)
_S_MU = (2.0653148e-05, 3.6077607e-08, 1.1646921e-14)

# --- Aire, 1 atm (200 - 1000 K) -----------------------------------------------
_A_CP = (1050.9133, 0.22572325, 1.4360165e-04, -3.7289302e-07)

# --- Etanol (0 - 75 C) --------------------------------------------------------
_ET_RHO = (772.22756, -0.88135041, -8.5514732e-04)
_ET_CP = (2569.6693, 9.2321596, 2.6316211e-02)
_ET_K = (0.16554785, -2.6607573e-04)
_ET_MU = (8.3073265, 745.10119, -3.0952061)

# --- Metanol (0 - 60 C) -------------------------------------------------------
_ME_RHO = (781.75656, -0.97198090, -1.0309403e-03)
_ME_CP = (2578.2059, 9.6448876, 8.6221900e-02)
_ME_K = (0.20040620, -3.3007752e-04)
_ME_MU = (-26.114396, 1916.5822, 2.1366883)

# --- Etilenglicol (0 - 197 C, DIPPR 260 - 470 K) -------------------------------------------------
_EG_RHO = (1096.5192, -0.68214574)
_EG_CP = (2517.6678, 4.4804272)
_EG_K = (0.25802742, 2.0715627e-04, -2.4601883e-06)
_EG_MU = (-1041.6843, 34874.171, 173.83938, -0.23419830)

# --- Benceno (10 - 80 C) ------------------------------------------------------
_BZ_RHO = (851.95927, -1.0733293)
_BZ_CP = (1825.4520, 4.3191924, 1.1155536e-02)
_BZ_K = (0.13778512, -3.1669512e-04)
_BZ_MU = (-20.351400, 1657.4633, 1.2952872)

# --- Tolueno (-20 - 100 C) ----------------------------------------------------
_TO_RHO = (847.78815, -0.94631752)
_TO_CP = (1757.0307, 3.3497121)
_TO_K = (0.12611988, -3.2273101e-04)
_TO_MU = (-18.355768, 1393.4177, 1.0855822)

# --- n-Hexano (-20 - 60 C) ----------------------------------------------------
_HX_RHO = (650.05078, -0.89264249)
_HX_CP = (2288.8352, 3.8002073)
_HX_K = (0.11860000, -2.8000000e-04)
_HX_MU = (15.812104, -349.41361, -3.9958818)

# --- Amoniaco liquido saturado (-40 - 50 C) -----------------------------------
_NH_RHO = (629.54679, -1.4268135, -2.6992968e-03)
_NH_CP = (4658.1045, 6.8004577, 2.2224240e-02)
_NH_MU = (-34.810406, 1833.6240, 3.4610355)


@dataclass(frozen=True)
class _FluidDef:
    """Definicion interna de un fluido: ventana de validez + correlaciones."""
    label: str
    phase: str
    T_min: float
    T_max: float
    note: str
    rho: object
    cp: object
    k: object
    mu: object


_FLUIDS: Dict[str, _FluidDef] = {
    "agua": _FluidDef(
        "Agua", "liquido", 273.15, 453.15,
        "Liquido saturado/comprimido. A 1 atm hierve a 100 C: por encima de esa "
        "temperatura se requiere presion (IAPWS valido hasta 180 C en este ajuste).",
        lambda T, P: _poly(T, 373.15, _W_RHO),
        lambda T, P: _poly(T, 373.15, _W_CP),
        lambda T, P: _poly(T, 373.15, _W_K),
        lambda T, P: _visc(T, *_W_MU),
    ),
    "vapor de agua": _FluidDef(
        "Vapor de agua", "gas", 373.15, 873.15,
        "Vapor sobrecalentado a baja presion. rho por gas ideal (R = 461.5 J/kg.K); "
        "por debajo de 373 K a 1 atm el agua es liquida.",
        lambda T, P: _rho_gas(T, P, M_H2O),
        lambda T, P: _poly(T, 600.0, _S_CP),
        lambda T, P: _poly(T, 600.0, _S_K),
        lambda T, P: _poly(T, 600.0, _S_MU),
    ),
    "aire": _FluidDef(
        "Aire", "gas", 200.0, 1000.0,
        "Aire seco. rho por gas ideal (R = 287.05 J/kg.K); mu y k por Sutherland.",
        lambda T, P: _rho_gas(T, P, M_AIR),
        lambda T, P: _poly(T, 600.0, _A_CP),
        lambda T, P: _k_sutherland(T),
        lambda T, P: _mu_sutherland(T),
    ),
    "etanol": _FluidDef(
        "Etanol", "liquido", 273.15, 348.15,
        "Liquido. Punto de ebullicion normal: 78.4 C (351.5 K).",
        lambda T, P: _poly(T, 313.15, _ET_RHO),
        lambda T, P: _poly(T, 313.15, _ET_CP),
        lambda T, P: _poly(T, 313.15, _ET_K),
        lambda T, P: _visc(T, *_ET_MU),
    ),
    "metanol": _FluidDef(
        "Metanol", "liquido", 273.15, 333.15,
        "Liquido. Punto de ebullicion normal: 64.7 C (337.8 K).",
        lambda T, P: _poly(T, 303.15, _ME_RHO),
        lambda T, P: _poly(T, 303.15, _ME_CP),
        lambda T, P: _poly(T, 303.15, _ME_K),
        lambda T, P: _visc(T, *_ME_MU),
    ),
    "etilenglicol": _FluidDef(
        "Etilenglicol", "liquido", 273.15, 470.15,
        "Liquido puro (100 %). Hierve a 197.3 C (470.4 K) a 1 atm; se usa como "
        "fluido caliente hasta ~190 C. Muy viscoso en frio: vigilar Re y dP.",
        lambda T, P: _poly(T, 323.15, _EG_RHO),
        lambda T, P: _poly(T, 323.15, _EG_CP),
        lambda T, P: _poly(T, 323.15, _EG_K),
        lambda T, P: _visc(T, *_EG_MU),
    ),
    "benceno": _FluidDef(
        "Benceno", "liquido", 283.15, 353.15,
        "Liquido. Congela a 5.5 C y hierve a 80.1 C (353.2 K) a 1 atm.",
        lambda T, P: _poly(T, 318.15, _BZ_RHO),
        lambda T, P: _poly(T, 318.15, _BZ_CP),
        lambda T, P: _poly(T, 318.15, _BZ_K),
        lambda T, P: _visc(T, *_BZ_MU),
    ),
    "tolueno": _FluidDef(
        "Tolueno", "liquido", 253.15, 373.15,
        "Liquido. Punto de ebullicion normal: 110.6 C (383.8 K).",
        lambda T, P: _poly(T, 313.15, _TO_RHO),
        lambda T, P: _poly(T, 313.15, _TO_CP),
        lambda T, P: _poly(T, 313.15, _TO_K),
        lambda T, P: _visc(T, *_TO_MU),
    ),
    "n-hexano": _FluidDef(
        "n-Hexano", "liquido", 253.15, 333.15,
        "Liquido. Punto de ebullicion normal: 68.7 C (341.9 K).",
        lambda T, P: _poly(T, 303.15, _HX_RHO),
        lambda T, P: _poly(T, 303.15, _HX_CP),
        lambda T, P: _poly(T, 303.15, _HX_K),
        lambda T, P: _visc(T, *_HX_MU),
    ),
    "amoniaco": _FluidDef(
        "Amoniaco (liquido)", "liquido", 233.15, 323.15,
        "Liquido SATURADO (refrigerante): la presion no es 1 atm sino la de "
        "saturacion (p.ej. ~8.6 bar a 20 C). Hierve a -33.3 C a 1 atm.",
        lambda T, P: _poly(T, 280.0, _NH_RHO),
        lambda T, P: _poly(T, 280.0, _NH_CP),
        lambda T, P: 0.5405 - 0.00200 * (T - 273.15),
        lambda T, P: _visc(T, *_NH_MU),
    ),
}

# Alias aceptados por el buscador (clave normalizada -> clave canonica).
_FLUID_ALIASES: Dict[str, str] = {
    "water": "agua", "h2o": "agua", "agua liquida": "agua",
    "vapor": "vapor de agua", "steam": "vapor de agua", "vapor de h2o": "vapor de agua",
    "vapor sobrecalentado": "vapor de agua",
    "air": "aire", "aire seco": "aire",
    "ethanol": "etanol", "alcohol etilico": "etanol",
    "methanol": "metanol", "alcohol metilico": "metanol",
    "etilen glicol": "etilenglicol", "etileno glicol": "etilenglicol",
    "glicol": "etilenglicol", "ethylene glycol": "etilenglicol", "meg": "etilenglicol",
    "benzene": "benceno", "toluene": "tolueno",
    "hexano": "n-hexano", "n hexano": "n-hexano", "hexane": "n-hexano",
    "amoniaco liquido": "amoniaco", "amonio": "amoniaco", "nh3": "amoniaco",
    "ammonia": "amoniaco",
}


# =============================================================================
# 4b. ENSUCIAMIENTO TIPICO POR FLUIDO (TEMA RGP-T-2.4, en m2.K/W)
#     (1 hr.ft2.F/Btu = 0.17611 m2.K/W). Claves = claves canonicas de _FLUIDS.
# =============================================================================
_FLUID_FOULING: Dict[str, float] = {
    "agua": 1.761e-4,           # Agua tratada de enfriamiento (0.001 hr.ft2.F/Btu)
    "vapor de agua": 0.881e-4,  # Vapor limpio sin aceite (0.0005 hr.ft2.F/Btu)
    "aire": 3.522e-4,           # Aire industrial (0.002 hr.ft2.F/Btu)
    "etanol": 1.761e-4,         # Liquido organico ligero
    "metanol": 1.761e-4,
    "etilenglicol": 3.522e-4,   # Solucion de glicol / fluido termico
    "benceno": 1.761e-4,
    "tolueno": 1.761e-4,
    "n-hexano": 1.761e-4,
    "amoniaco": 1.761e-4,       # Refrigerante liquido
}


# =============================================================================
# 5. MATERIALES SOLIDOS (TEMA Clase "C")
#    k_m y rho_m a ~300 K. epsilon: tubo estirado vs. acero comercial.
#    R_f: resistencia de ensuciamiento TOTAL tipica de diseno
#         (1 hr.ft2.F/Btu = 0.17611 m2.K/W).
# =============================================================================
_MATERIALS: Dict[str, Tuple[str, SolidMaterial]] = {
    "cobre": ("Cobre", SolidMaterial(k_m=386.0, rho_m=8933.0, epsilon=1.5e-6, R_f=1.761e-4)),
    "acero al carbono": ("Acero al carbono",
                         SolidMaterial(k_m=60.5, rho_m=7854.0, epsilon=4.6e-5, R_f=3.522e-4)),
    "acero inox 304": ("Acero inoxidable AISI 304",
                       SolidMaterial(k_m=14.9, rho_m=7900.0, epsilon=1.5e-6, R_f=1.761e-4)),
    "laton admiralty": ("Laton Admiralty (70Cu-29Zn-1Sn)",
                        SolidMaterial(k_m=111.0, rho_m=8530.0, epsilon=1.5e-6, R_f=1.761e-4)),
    "aluminio": ("Aluminio", SolidMaterial(k_m=237.0, rho_m=2702.0, epsilon=1.5e-6, R_f=1.761e-4)),
}

_MATERIAL_ALIASES: Dict[str, str] = {
    "copper": "cobre", "cu": "cobre",
    "acero carbono": "acero al carbono", "acero": "acero al carbono",
    "carbon steel": "acero al carbono", "sa-214": "acero al carbono",
    "acero inoxidable": "acero inox 304", "acero inoxidable 304": "acero inox 304",
    "inox": "acero inox 304", "inox 304": "acero inox 304", "ss304": "acero inox 304",
    "aisi 304": "acero inox 304", "304": "acero inox 304",
    "laton": "laton admiralty", "admiralty": "laton admiralty",
    "laton de almirantazgo": "laton admiralty", "brass": "laton admiralty",
    "aluminum": "aluminio", "aluminium": "aluminio", "al": "aluminio",
}


# =============================================================================
# 6. NORMALIZACION Y CONVERSION DE UNIDADES
# =============================================================================
def _norm(text: str) -> str:
    """Minusculas, sin tildes, sin espacios redundantes ('Amoníaco ' -> 'amoniaco')."""
    if not isinstance(text, str):
        raise TypeError(f"El nombre debe ser una cadena de texto, se recibio {type(text).__name__}.")
    s = unicodedata.normalize("NFKD", text.strip().lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.replace("_", " ").split())


def _build_lookup(aliases: Dict[str, str], labels: Dict[str, str]) -> Dict[str, str]:
    """
    Tabla de busqueda final: claves canonicas + alias + etiquetas publicas.
    Incluir las etiquetas garantiza que lo que devuelven `list_fluids()` /
    `list_materials()` (lo que la GUI muestra en un combo) sea siempre un
    nombre valido de entrada (round-trip).
    """
    table = {key: key for key in labels}
    table.update(aliases)
    for key, label in labels.items():
        table.setdefault(_norm(label), key)
    return table


_FLUID_LOOKUP = _build_lookup(_FLUID_ALIASES, {k: v.label for k, v in _FLUIDS.items()})
_MATERIAL_LOOKUP = _build_lookup(_MATERIAL_ALIASES, {k: v[0] for k, v in _MATERIALS.items()})


def _to_kelvin(T: float, unit: str) -> float:
    """Convierte T a Kelvin. Acepta 'K', 'C' y 'F' (insensible a mayusculas)."""
    try:
        T = float(T)
    except (TypeError, ValueError):
        raise TypeError(f"La temperatura debe ser numerica, se recibio '{T}'.") from None
    if not math.isfinite(T):
        raise ValueError("La temperatura no puede ser NaN ni infinita.")

    u = _norm(unit).replace("°", "").replace("deg", "").strip()
    if u in ("k", "kelvin"):
        T_K = T
    elif u in ("c", "celsius", "centigrados"):
        T_K = T + 273.15
    elif u in ("f", "fahrenheit"):
        T_K = (T - 32.0) * 5.0 / 9.0 + 273.15
    else:
        raise ValueError(f"Unidad de temperatura '{unit}' no reconocida. Use 'K', 'C' o 'F'.")

    if T_K <= T_ABS_MIN:
        raise ValueError(
            f"Temperatura absoluta invalida: {T_K:.2f} K. "
            "No existen temperaturas iguales o menores al cero absoluto (0 K = -273.15 C)."
        )
    return T_K


# =============================================================================
# 7. BASE DE DATOS
# =============================================================================
class ThermoDatabase:
    """Acceso unico a propiedades de fluidos y materiales. Instancia global: `db`."""

    # ---------------------------------------------------------------- fluidos
    def list_fluids(self) -> List[str]:
        """Nombres canonicos de los 10 fluidos disponibles."""
        return [f.label for f in _FLUIDS.values()]

    def _resolve_fluid(self, name: str) -> Tuple[str, _FluidDef]:
        key = _FLUID_LOOKUP.get(_norm(name), "")
        if key not in _FLUIDS:
            raise ValueError(
                f"Fluido '{name}' no existe en la base de datos.\n"
                f"   Fluidos disponibles: {', '.join(self.list_fluids())}."
            )
        return key, _FLUIDS[key]

    def get_limits(self, name: str, unit: str = "K") -> Tuple[float, float]:
        """Ventana de validez (T_min, T_max) del fluido, en la unidad pedida."""
        _, f = self._resolve_fluid(name)
        u = _norm(unit).replace("\u00b0", "").replace("deg", "").strip()
        if u in ("k", "kelvin"):
            return (f.T_min, f.T_max)
        if u in ("c", "celsius", "centigrados"):
            return (f.T_min - 273.15, f.T_max - 273.15)
        if u in ("f", "fahrenheit"):
            return ((f.T_min - 273.15) * 9.0 / 5.0 + 32.0,
                    (f.T_max - 273.15) * 9.0 / 5.0 + 32.0)
        raise ValueError(f"Unidad de temperatura '{unit}' no reconocida. Use 'K', 'C' o 'F'.")

    def get_fouling(self, name: str) -> float:
        """Resistencia de ensuciamiento tipica TEMA del fluido [m2.K/W] (parche 5.1)."""
        key, _ = self._resolve_fluid(name)
        return _FLUID_FOULING[key]

    def get_fluid_state(self, name: str, T: float, unit: str = "K",
                        P: float = P_ATM) -> FluidState:
        """
        Devuelve el `FluidState` (cp, mu, k, rho, Pr) del fluido a la temperatura T.

        Parametros
        ----------
        name : str   Nombre del fluido (acepta alias y mayusculas/tildes).
        T    : float Temperatura.
        unit : str   Unidad de T: 'K' (default), 'C' o 'F'.
        P    : float Presion absoluta [Pa], solo afecta rho de los gases.

        Lanza ValueError si T esta fuera del rango donde el fluido existe en esa
        fase, o si alguna propiedad calculada resulta no fisica.
        """
        key, f = self._resolve_fluid(name)
        T_K = _to_kelvin(T, unit)

        # --- SANITY CHECK 1: ventana de validez de la correlacion / fase ------
        if not (f.T_min <= T_K <= f.T_max):
            raise ValueError(
                f"[{f.label}] Temperatura fuera de rango: {T_K:.2f} K "
                f"({T_K - 273.15:.2f} C).\n"
                f"   Rango valido: {f.T_min:.2f} - {f.T_max:.2f} K "
                f"({f.T_min - 273.15:.2f} - {f.T_max - 273.15:.2f} C), fase '{f.phase}'.\n"
                f"   Motivo: {f.note}\n"
                f"   Extrapolar una correlacion empirica fuera de su rango da "
                f"propiedades sin sentido fisico; corrija la temperatura de "
                f"entrada o seleccione otro fluido."
            )

        # --- SANITY CHECK 2: presion valida (afecta rho de gases) -------------
        if f.phase == "gas":
            if not math.isfinite(P) or P <= 0.0:
                raise ValueError(
                    f"[{f.label}] Presion absoluta invalida: {P} Pa. "
                    "Debe ser un valor finito y positivo."
                )

        rho = float(f.rho(T_K, P))
        cp = float(f.cp(T_K, P))
        k = float(f.k(T_K, P))
        mu = float(f.mu(T_K, P))

        # --- SANITY CHECK 3: ninguna propiedad puede ser <= 0 o no finita -----
        for prop, val, uni in (("rho", rho, "kg/m3"), ("cp", cp, "J/kg.K"),
                               ("k", k, "W/m.K"), ("mu", mu, "Pa.s")):
            if not math.isfinite(val) or val <= 0.0:
                raise ValueError(
                    f"[{f.label}] La correlacion de '{prop}' devolvio un valor no "
                    f"fisico ({val} {uni}) a {T_K:.2f} K. Ninguna propiedad "
                    f"termofisica puede ser cero, negativa o indefinida. "
                    f"Revise la temperatura de entrada."
                )

        Pr = cp * mu / k

        # --- SANITY CHECK 4: Prandtl en un orden de magnitud creible ----------
        if not (1.0e-3 < Pr < 1.0e5):
            raise ValueError(
                f"[{f.label}] Numero de Prandtl absurdo (Pr = {Pr:.3e}) a "
                f"{T_K:.2f} K. Pr = cp*mu/k debe caer entre ~0.001 (metales "
                f"liquidos) y ~1e4 (aceites muy viscosos). Resultado descartado."
            )

        return FluidState(cp=cp, mu=mu, k=k, rho=rho, Pr=Pr)

    # ------------------------------------------------------------- materiales
    def list_materials(self) -> List[str]:
        """Nombres canonicos de los 5 materiales disponibles."""
        return [label for label, _ in _MATERIALS.values()]

    def get_material(self, name: str) -> SolidMaterial:
        """Devuelve el `SolidMaterial` (k_m, rho_m, epsilon, R_f) del metal pedido."""
        key = _MATERIAL_LOOKUP.get(_norm(name), "")
        if key not in _MATERIALS:
            raise ValueError(
                f"Material '{name}' no existe en la base de datos.\n"
                f"   Materiales disponibles: {', '.join(self.list_materials())}."
            )
        return _MATERIALS[key][1]


# Instancia global compartida por todo el proyecto.
db = ThermoDatabase()


# =============================================================================
# 8. PRUEBAS RAPIDAS
# =============================================================================
if __name__ == "__main__":
    # 1) Propiedades del agua liquida a 25 C (referencia: cp = 4181 J/kg.K).
    agua = db.get_fluid_state("Agua", 25.0, unit="C")
    print(f"1) Agua a 25 C -> cp = {agua.cp:.1f} J/kg.K | rho = {agua.rho:.1f} kg/m3 "
          f"| mu = {agua.mu:.3e} Pa.s | k = {agua.k:.4f} W/m.K | Pr = {agua.Pr:.2f}")

    # 2) Sanity check: agua liquida a 400 C a 1 atm no existe -> debe fallar.
    try:
        db.get_fluid_state("Agua", 400.0, unit="C")
        print("2) ERROR: no se lanzo la excepcion esperada.")
    except ValueError as e:
        print(f"2) ValueError capturado OK -> {str(e).splitlines()[0]}")

    # 3) Conductividad del acero al carbono.
    acero = db.get_material("Acero al carbono")
    print(f"3) Acero al carbono -> k_m = {acero.k_m:.1f} W/m.K | "
          f"rho_m = {acero.rho_m:.0f} kg/m3 | eps = {acero.epsilon:.1e} m | "
          f"R_f = {acero.R_f:.3e} m2.K/W")
