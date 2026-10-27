# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
"""
informe_propiedades.py - Genera el informe PDF de procedencia de las
propiedades termofisicas en LaTeX (compilado con Tectonic).

El informe declara TODOS los datos de la base (src/core/thermo_data.py):
  * la ventana de validez de cada fluido y la fuente bibliografica completa
    de la que provienen los datos ajustados (citas verificadas),
  * la forma funcional de cada correlacion (rho, cp, k, mu) con sus
    coeficientes REALES leidos de thermo_data.py al generar el documento,
  * los materiales solidos con sus propiedades y factores de ensuciamiento,
  * una validacion numerica frente a valores tabulados de referencia, cada
    uno con su fuente verificada (NIST Chemistry WebBook, CoolProp/REFPROP,
    correlaciones de referencia) y su desviacion porcentual.

Salida: informe_propiedades.pdf (y el .tex intermedio) en la raiz del
proyecto, o la ruta pasada por linea de comandos.

Uso:
    py src/core/informe_propiedades.py [salida.pdf]

Requisito de compilacion: Tectonic (https://tectonic-typesetting.github.io),
el motor LaTeX autodescargable. La aplicacion en si sigue sin dependencias;
solo la generacion del informe usa Tectonic.
"""
from __future__ import annotations

import datetime
import os
import shutil
import subprocess
import sys
from typing import Dict, List, Optional, Sequence, Tuple

try:
    from src.core import thermo_data as td
except ImportError:  # ejecucion directa: `py src/core/informe_propiedades.py`
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))
    from src.core import thermo_data as td

__all__ = ["generar_informe"]


# =============================================================================
# 1. FUENTES BIBLIOGRAFICAS (citas completas verificadas)
# =============================================================================
# Verificadas mediante busqueda bibliografica (Crossref, catalogos editoriales,
# NIST Chemistry WebBook y los PDF de la carpeta del proyecto).
BIBLIO: Dict[str, str] = {
    "iapws-if97":
        "IAPWS. \\emph{R7-97(2012): Revised Release on the IAPWS Industrial "
        "Formulation 1997 for the Thermodynamic Properties of Water and "
        "Steam}. International Association for the Properties of Water and "
        "Steam, Secretariat Erlangen, 1997 (revision 2007; cambios "
        "editoriales 2009--2012). Region 1 (agua liquida): "
        "$273{,}15\\ \\mathrm{K} \\le T \\le 623{,}15\\ \\mathrm{K}$, "
        "$p_{sat}(T) \\le p \\le 100$ MPa. Articulo de referencia: "
        "W. Wagner et al., ``The IAPWS Industrial Formulation 1997 for the "
        "Thermodynamic Properties of Water and Steam'', \\emph{ASME Journal "
        "of Engineering for Gas Turbines and Power}, 122(1):150--184, 2000, "
        "DOI 10.1115/1.483186.",
    "iapws-transporte":
        "IAPWS. \\emph{Release on the IAPWS Formulation 2008 for the "
        "Viscosity of Ordinary Water Substance} y \\emph{Release on the "
        "IAPWS Formulation 2011 for the Thermal Conductivity of Ordinary "
        "Water Substance}. International Association for the Properties of "
        "Water and Steam.",
    "perry":
        "D. W. Green (ed.-in-chief) y R. H. Perry (ed. p\\^ostumo). "
        "\\emph{Perry's Chemical Engineers' Handbook}, 8.ª ed. McGraw-Hill, "
        "Nueva York, 2008. ISBN 0-07-142294-3; DOI 10.1036/0071422943. "
        "Seccion 2 (Physical and Chemical Data, con datos del DIPPR): Tabla "
        "2-313 ``Viscosity of Inorganic and Organic Liquids (Pa\\,s)'', con "
        "los coeficientes DIPPR por compuesto.",
    "dippr":
        "AIChE Design Institute for Physical Properties (DIPPR). "
        "\\emph{DIPPR 801 -- Pure Component Data}, ecuacion 101 para la "
        "viscosidad de liquido: $\\mu(T)=\\exp\\left(A+B/T+C\\ln T+D\\,"
        "T^{E}\\right)$. En este proyecto se usa la forma con $E=1$.",
    "incropera":
        "T. L. Bergman, A. S. Lavine, F. P. Incropera y D. P. DeWitt. "
        "\\emph{Fundamentals of Heat and Mass Transfer}, 6.ª ed. John Wiley "
        "\\& Sons, 2007 (4.ª ed. 1996; 7.ª ed. 2011). Apéndice A, Tabla A.4, "
        "``Thermophysical Properties of Gases at Atmospheric Pressure'': "
        "aire (100--3000 K) y vapor de agua (380--850 K).",
    "ashrae":
        "ASHRAE. \\emph{ASHRAE Handbook -- Fundamentals}, edicion SI 2025. "
        "American Society of Heating, Refrigerating and Air-Conditioning "
        "Engineers, Atlanta, 2025. Capitulo 30, ``Thermophysical Properties "
        "of Refrigerants'': tablas de liquido y vapor saturados del amoniaco "
        "(R-717).",
    "sutherland":
        "W. Sutherland. ``The Viscosity of Gases and Molecular Force''. "
        "\\emph{The London, Edinburgh, and Dublin Philosophical Magazine and "
        "Journal of Science}, Serie 5, 36(223):507--531, 1893. DOI "
        "10.1080/14786449308620508.",
    "nist":
        "NIST Chemistry WebBook, NIST Standard Reference Database Number 69. "
        "National Institute of Standards and Technology, Gaithersburg, MD. "
        "DOI 10.18434/T4D303. Propiedades por ecuaciones de estado de "
        "referencia: IAPWS-95 (agua y vapor), Thol/Lemmon/Span (benceno, "
        "tolueno, n-hexano), Tillner-Roth (amoniaco), Lemmon \\& Jacobsen "
        "(aire).",
    "coolprop":
        "I. H. Bell, J. Wronski, S. Quoilin y V. Lemmon. ``Pure and "
        "Pseudo-pure Fluid Properties Database for Refrigerants and "
        "Fluids'' (CoolProp). \\emph{Industrial \\& Engineering Chemistry "
        "Research}, 53(6):2498--2508, 2014.",
    "eg-referencia":
        "A. Mebbelli, E. Velliadou, M. J. Assael, J. Antoniadis y W. M. "
        "Huber. ``Reference Correlations for the Viscosity and Thermal "
        "Conductivity of Ethylene Glycol''. \\emph{International Journal of "
        "Thermophysics}, 42, 2021.",
    "tema":
        "Tubular Exchanger Manufacturers Association, Inc. \\emph{Standards "
        "of the Tubular Exchanger Manufacturers Association}, Tenth Edition. "
        "TEMA, Inc., 2019. Figura N-1.2 (Table of TEMA types) y tablas "
        "CB-3.1.3, RCB-4.3, CB-4.4.1, RCB-4.5.2, CB-4.7.1, C-7.1.1, C-11.1 "
        "y RCB-4.6.1 de la Seccion 5 (Mechanical Standards TEMA Class R C B).",
    "asme":
        "ASME Boiler \\& Pressure Vessel Code, Seccion VIII, Division 1. "
        "American Society of Mechanical Engineers. UG-27 (cilindros), "
        "UG-32 (cabezas), UG-34 (cubiertas planas).",
    "kern":
        "D. Q. Kern. \\emph{Process Heat Transfer}. McGraw-Hill, Nueva York, "
        "1950 (871 pp.). Metodo de dimensionamiento termico del lado coraza "
        "con baffles segmentados.",
    "serth":
        "R. W. Serth. \\emph{Process Heat Transfer: Principles and "
        "Applications}, 1.ª ed. Academic Press (Elsevier), Oxford, 2007. "
        "ISBN 978-0-12-373588-1. Correlacion de conteo de tubos con "
        "constantes $C_L$ y $C_{TP}$ (ver tambien R. W. Serth y T. Lestina, "
        "\\emph{Process Heat Transfer: Principles, Applications and Rules of "
        "Thumb}, Academic Press, 2014).",
    "tan-fok":
        "F. L. Tan y S. C. Fok. ``An educational computer-aided tool for "
        "heat exchanger design''. \\emph{Computer Applications in "
        "Engineering Education}, 14(2):77--89, 2006. DOI 10.1002/cae.20073. "
        "Herramienta educativa de diseno de intercambiadores de tubos y "
        "coraza cuya interfaz inspira a este proyecto; las ecuaciones "
        "19--32 de dimensionamiento mecanico citadas por el codigo se "
        "refieren a este articulo.",
}

# Fuente de los datos ajustados de cada fluido (claves de BIBLIO).
_FUENTES_FLUIDO: Dict[str, List[str]] = {
    "agua": ["iapws-if97", "iapws-transporte"],
    "vapor de agua": ["incropera"],
    "aire": ["incropera", "sutherland"],
    "etanol": ["perry", "dippr"],
    "metanol": ["perry", "dippr"],
    "etilenglicol": ["perry", "dippr"],
    "benceno": ["perry", "dippr"],
    "tolueno": ["perry", "dippr"],
    "n-hexano": ["perry", "dippr"],
    "amoniaco": ["ashrae", "perry"],
}

_TEXTO_FUENTE: Dict[str, str] = {
    "agua": "Ajuste por minimos cuadrados a las tablas de liquido "
            "saturado/comprimido de IAPWS-IF97 (propiedades de transporte "
            "según las formulaciones IAPWS 2008/2011).",
    "vapor de agua": "Ajuste a la Tabla A.4 de Incropera (vapor de agua a "
                     "1 atm, 380-850 K segun la fuente); densidad por gas "
                     "ideal.",
    "aire": "Ajuste a la Tabla A.4 de Incropera (aire seco a 1 atm, "
            "100-3000 K en la tabla); mu y k por la correlacion de "
            "Sutherland.",
    "etanol": "Correlaciones tipo DIPPR-101 ajustadas a los datos de "
              "Perry's (8.ª ed.) para liquido.",
    "metanol": "Correlaciones tipo DIPPR-101 ajustadas a los datos de "
               "Perry's (8.ª ed.) para liquido.",
    "etilenglicol": "Correlaciones tipo DIPPR-101 ajustadas a los datos de "
                    "Perry's / DIPPR (260-470 K) para liquido puro.",
    "benceno": "Correlaciones tipo DIPPR-101 ajustadas a los datos de "
               "Perry's (8.ª ed.) para liquido.",
    "tolueno": "Correlaciones tipo DIPPR-101 ajustadas a los datos de "
               "Perry's (8.ª ed.) para liquido.",
    "n-hexano": "Correlaciones tipo DIPPR-101 ajustadas a los datos de "
                "Perry's (8.ª ed.) para liquido.",
    "amoniaco": "Datos de amoniaco LIQUIDO SATURADO de las tablas ASHRAE "
                "/ Perry's.",
}


# =============================================================================
# 2. VALORES DE REFERENCIA VERIFICADOS PARA LA VALIDACION
# =============================================================================
# (fluido, T[C], propiedad, valor de referencia, unidad, etiqueta de fuente,
#  confianza)  --  fuentes verificadas contra NIST Chemistry WebBook,
# CoolProp/REFPROP y correlaciones de referencia (ver columna «Fuente»).
_PUNTOS_REFERENCIA: List[Tuple[str, float, str, float, str, str, str]] = [
    ("Agua", 20.0, "rho", 998.2, "kg/m3", "NIST (IAPWS-95)", "alta"),
    ("Agua", 20.0, "cp", 4184, "J/kg.K", "NIST (IAPWS-95)", "alta"),
    ("Agua", 20.0, "k", 0.598, "W/m.K", "NIST / IAPWS", "alta"),
    ("Agua", 20.0, "mu", 1.002e-3, "Pa.s", "NIST (Huber 2009)", "alta"),
    ("Agua", 60.0, "rho", 983.2, "kg/m3", "NIST (IAPWS-95)", "alta"),
    ("Agua", 60.0, "cp", 4185, "J/kg.K", "NIST (IAPWS-95)", "alta"),
    ("Agua", 60.0, "k", 0.651, "W/m.K", "NIST / IAPWS", "alta"),
    ("Agua", 60.0, "mu", 4.660e-4, "Pa.s", "NIST (Huber 2009)", "alta"),
    ("Agua", 100.0, "rho", 958.4, "kg/m3", "NIST (liq. saturado)", "alta"),
    ("Agua", 100.0, "cp", 4216, "J/kg.K", "NIST (liq. saturado)", "alta"),
    ("Agua", 100.0, "k", 0.677, "W/m.K", "NIST / IAPWS", "alta"),
    ("Agua", 100.0, "mu", 2.817e-4, "Pa.s", "NIST (Huber 2009)", "alta"),
    ("Etanol", 25.0, "rho", 785.1, "kg/m3", "CoolProp 8", "media"),
    ("Etanol", 25.0, "cp", 2435, "J/kg.K", "CoolProp 8", "media"),
    ("Etanol", 25.0, "k", 0.1635, "W/m.K", "CoolProp 8", "media"),
    ("Etanol", 25.0, "mu", 1.08e-3, "Pa.s", "CoolProp 8", "media"),
    ("Metanol", 25.0, "rho", 786.3, "kg/m3", "NIST (IUPAC)", "alta"),
    ("Metanol", 25.0, "cp", 2535, "J/kg.K", "NIST (IUPAC)", "alta"),
    ("Metanol", 25.0, "k", 0.200, "W/m.K", "NIST (IUPAC)", "alta"),
    ("Metanol", 25.0, "mu", 5.44e-4, "Pa.s", "NIST (IUPAC)", "alta"),
    ("Etilenglicol", 25.0, "rho", 1110, "kg/m3", "NIST (Zhou-Lemmon)", "media"),
    ("Etilenglicol", 25.0, "cp", 2412, "J/kg.K", "REFPROP / DIPPR", "media"),
    ("Etilenglicol", 25.0, "k", 0.252, "W/m.K", "Mebbelli 2021", "media"),
    ("Etilenglicol", 25.0, "mu", 1.68e-2, "Pa.s", "Mebbelli 2021", "media"),
    ("Benceno", 25.0, "rho", 873.7, "kg/m3", "NIST (Thol/Lemmon)", "alta"),
    ("Benceno", 25.0, "cp", 1734, "J/kg.K", "NIST (Thol/Lemmon)", "alta"),
    ("Benceno", 25.0, "k", 0.1413, "W/m.K", "NIST (Assael)", "alta"),
    ("Benceno", 25.0, "mu", 6.03e-4, "Pa.s", "NIST (Assael)", "alta"),
    ("Tolueno", 25.0, "rho", 862.2, "kg/m3", "NIST (Lemmon-Span)", "alta"),
    ("Tolueno", 25.0, "cp", 1701, "J/kg.K", "NIST (Lemmon-Span)", "alta"),
    ("Tolueno", 25.0, "k", 0.1304, "W/m.K", "NIST (Assael)", "alta"),
    ("Tolueno", 25.0, "mu", 5.52e-4, "Pa.s", "NIST (Assael)", "alta"),
    ("n-Hexano", 25.0, "rho", 654.9, "kg/m3", "NIST (Thol/Wang)", "alta"),
    ("n-Hexano", 25.0, "cp", 2273, "J/kg.K", "NIST (Thol/Wang)", "alta"),
    ("n-Hexano", 25.0, "k", 0.120, "W/m.K", "NIST (Assael)", "alta"),
    ("n-Hexano", 25.0, "mu", 2.98e-4, "Pa.s", "NIST (Assael)", "alta"),
    ("Amoniaco (liquido)", 25.0, "rho", 602.9, "kg/m3",
     "NIST (Tillner-Roth)", "alta"),
    ("Amoniaco (liquido)", 25.0, "cp", 4780, "J/kg.K",
     "NIST (Tillner-Roth)", "alta"),
    ("Amoniaco (liquido)", 25.0, "k", 0.470, "W/m.K",
     "NIST (Tillner-Roth)", "alta"),
    ("Amoniaco (liquido)", 25.0, "mu", 1.27e-4, "Pa.s",
     "NIST (Tillner-Roth)", "alta"),
    ("Aire", 25.0, "rho", 1.184, "kg/m3", "CoolProp (Lemmon 2000)", "alta"),
    ("Aire", 25.0, "cp", 1006, "J/kg.K", "CoolProp (Lemmon 2000)", "alta"),
    ("Aire", 25.0, "k", 0.0262, "W/m.K", "Incropera / CoolProp", "alta"),
    ("Aire", 25.0, "mu", 1.84e-5, "Pa.s", "CoolProp (Lemmon 2000)", "alta"),
    ("Vapor de agua", 150.0, "rho", 0.5233, "kg/m3",
     "NIST (IAPWS-95, real)", "alta"),
    ("Vapor de agua", 150.0, "cp", 1986, "J/kg.K", "NIST (IAPWS-95)", "alta"),
    ("Vapor de agua", 150.0, "k", 0.0289, "W/m.K", "NIST / IAPWS", "alta"),
    ("Vapor de agua", 150.0, "mu", 1.42e-5, "Pa.s", "NIST (Huber 2009)",
     "alta"),
]

# Claves de BIBLIO para el texto de cada fluido.
_FORMA_RHO_GAS = r"$\rho = P M/(R_u T)$  [gas ideal]"

_FLUIDOS_INFORME = [
    ("agua", "Agua", 373.15, ("_W_RHO", "_W_CP", "_W_K"),
     ("DIPPR-101", "_W_MU")),
    ("vapor de agua", "Vapor de agua", 600.0, (None, "_S_CP", "_S_K"),
     ("Polinomio", "_S_MU")),
    ("aire", "Aire", 600.0, (None, "_A_CP", None), ("Sutherland", None)),
    ("etanol", "Etanol", 313.15, ("_ET_RHO", "_ET_CP", "_ET_K"),
     ("DIPPR-101", "_ET_MU")),
    ("metanol", "Metanol", 303.15, ("_ME_RHO", "_ME_CP", "_ME_K"),
     ("DIPPR-101", "_ME_MU")),
    ("etilenglicol", "Etilenglicol", 323.15, ("_EG_RHO", "_EG_CP", "_EG_K"),
     ("DIPPR-101", "_EG_MU")),
    ("benceno", "Benceno", 318.15, ("_BZ_RHO", "_BZ_CP", "_BZ_K"),
     ("DIPPR-101", "_BZ_MU")),
    ("tolueno", "Tolueno", 313.15, ("_TO_RHO", "_TO_CP", "_TO_K"),
     ("DIPPR-101", "_TO_MU")),
    ("n-hexano", "n-Hexano", 303.15, ("_HX_RHO", "_HX_CP", "_HX_K"),
     ("DIPPR-101", "_HX_MU")),
    ("amoniaco", "Amoniaco (liquido)", 280.0, ("_NH_RHO", "_NH_CP", None),
     ("DIPPR-101", "_NH_MU")),
]


# =============================================================================
# 3. UTILIDADES LaTeX
# =============================================================================
def _esc(txt: str) -> str:
    """Escapa los caracteres especiales de LaTeX en texto plano."""
    reemplazos = {
        "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "#": r"\#",
        "$": r"\$", "%": r"\%", "&": r"\&", "_": r"\_", "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(reemplazos.get(c, c) for c in txt)


def _fmt_coef(coefs: Sequence[float]) -> str:
    return ", ".join(f"{c:.6g}" for c in coefs)


def _numero(x: float) -> str:
    if x == 0.0:
        return "0"
    if abs(x) >= 1.0e4 or abs(x) < 1.0e-3:
        return f"{x:.3e}"
    return f"{x:.6g}"


# =============================================================================
# 4. GENERACION DEL DOCUMENTO
# =============================================================================
def _portada(hoy: str) -> str:
    return rf"""
\begin{{titlepage}}
\centering
\vspace*{{2.2cm}}
{{\color{{acento}}\rule{{\linewidth}}{{2pt}}}}\\[1.2cm]
{{\Huge\bfseries\color{{morado}} Informe de procedencia\\[0.4em]
 y validaci\'on de propiedades}}\\[0.8cm]
{{\Large\color{{acento}} Base de datos termof\'isica del software de
 intercambiadores de calor de tubos y coraza}}\\[0.5cm]
{{\large\color{{gristexto}} M\'etodo de Kern $\cdot$ Est\'andar TEMA
 Clase C}}\\[1.2cm]
{{\color{{acento}}\rule{{\linewidth}}{{1pt}}}}\\[1.5cm]
\begin{{tabular}}{{rl}}
\textbf{{Documento generado:}} & {hoy} \\
\textbf{{Fuente de los datos:}} & \texttt{{src/core/thermo\_data.py}} \\
\textbf{{Compilaci\'on:}} & LaTeX (XeTeX) con Tectonic \\
\textbf{{Cobertura:}} & 10 fluidos, 5 materiales, 4 propiedades cada fluido \\
\end{{tabular}}
\vfill
{{\small\color{{gristexto}} Todas las correlaciones, coeficientes,
 ventanas de validez y fuentes bibliogr\'aficas de la base de datos,
 declaradas de forma completa y trazable.}}
\end{{titlepage}}
"""


def _seccion_fuente() -> str:
    filas = []
    for clave, etiqueta, *_ in _FLUIDOS_INFORME:
        f = td._FLUIDS[clave]
        T_min, T_max = td.db.get_limits(etiqueta, "C")
        refs = ", ".join(rf"\cite{{{k}}}" for k in _FUENTES_FLUIDO[clave])
        filas.append(
            rf"{_esc(etiqueta)} & {f.phase} & "
            rf"{T_min:.0f} a {T_max:.0f} & {_esc(_TEXTO_FUENTE[clave])} "
            rf"& {refs} \\")
    cuerpo = "\n".join(filas)
    return rf"""
\begin{{longtable}}{{p{{2.6cm}}l p{{1.5cm}} p{{6.2cm}} p{{3.4cm}}}}
\caption{{Procedencia de los datos por fluido}}\label{{tab:fuentes}}\\
\toprule
\textbf{{Fluido}} & \textbf{{Fase}} & \textbf{{Ventana ($^\circ$C)}} &
\textbf{{Procedencia del ajuste}} & \textbf{{Referencias}} \\
\midrule
\endfirsthead
\toprule
\textbf{{Fluido}} & \textbf{{Fase}} & \textbf{{Ventana ($^\circ$C)}} &
\textbf{{Procedencia del ajuste}} & \textbf{{Referencias}} \\
\midrule
\endhead
{cuerpo}
\bottomrule
\end{{longtable}}
"""


def _seccion_coeficientes() -> str:
    bloques: List[str] = []
    for clave, etiqueta, T0, atribs, (forma_mu, attr_mu) in _FLUIDOS_INFORME:
        f = td._FLUIDS[clave]
        T_min, T_max = td.db.get_limits(etiqueta, "C")
        refs = ", ".join(rf"\cite{{{k}}}" for k in _FUENTES_FLUIDO[clave])
        filas = []
        for nombre, attr in zip(("rho", "cp", "k"), atribs):
            if attr is None:
                if nombre == "rho":
                    filas.append(rf"$\rho(T)$ & {_FORMA_RHO_GAS} & -- \\")
                else:
                    filas.append(
                        rf"${nombre}(T)$ & Sutherland (ver \S2) & -- \\")
                continue
            coefs = getattr(td, attr)
            filas.append(
                rf"${nombre}(T)$ & polinomio centrado en $T_0$ = "
                rf"{T0:.2f} K & {_esc(_fmt_coef(coefs))} \\")
        if attr_mu is None:
            filas.append(rf"$\mu(T)$ & Sutherland (ver \S2) & -- \\")
        else:
            coefs = getattr(td, attr_mu)
            filas.append(
                rf"$\mu(T)$ & {_esc(forma_mu)} & "
                rf"{_esc(_fmt_coef(coefs))} \\")
        cuerpo = "\n".join(filas)
        nota = _esc(f.note)
        bloques.append(rf"""
\subsection*{{{_esc(etiqueta)}}}
{{\small\color{{gristexto}} Fase: {f.phase} $\cdot$ Ventana:
 {T_min:.1f} a {T_max:.1f} $^\circ$C ({f.T_min:.2f}--{f.T_max:.2f} K)
 $\cdot$ Fuentes: {refs}.}}\\[2pt]
\begin{{tabular}}{{llp{{7.6cm}}}}
\toprule
\textbf{{Propiedad}} & \textbf{{Forma funcional}} & \textbf{{Coeficientes}} \\
\midrule
{cuerpo}
\bottomrule
\end{{tabular}}\\[3pt]
{{\footnotesize\itshape Nota de la base de datos: {nota}}}
\vspace{{0.7em}}
""")
    return "\n".join(bloques)


def _seccion_materiales() -> str:
    filas = []
    for nombre in td.db.list_materials():
        m = td.db.get_material(nombre)
        filas.append(
            rf"{_esc(nombre)} & {m.k_m:.1f} & {m.rho_m:.0f} & "
            rf"{m.epsilon:.1e} & {m.R_f:.3e} \\")
    cuerpo = "\n".join(filas)
    return rf"""
\begin{{tabular}}{{lrrrr}}
\toprule
\textbf{{Material}} & \textbf{{$k_m$ (W/m\,K)}} & \textbf{{$\rho_m$
 (kg/m$^3$)}} & \textbf{{$\varepsilon$ (m)}} & \textbf{{$R_f$
 (m$^2$\,K/W)}} \\
\midrule
{cuerpo}
\bottomrule
\end{{tabular}}
"""


def _seccion_validacion() -> str:
    filas = []
    resumen: Dict[str, float] = {"rho": 0.0, "cp": 0.0, "k": 0.0, "mu": 0.0}
    for etiqueta, T, prop, ref, unidad, fuente, conf in _PUNTOS_REFERENCIA:
        estado = td.db.get_fluid_state(etiqueta, T, "C")
        calc = getattr(estado, prop)
        dif = 100.0 * (calc - ref) / ref
        resumen[prop] = max(resumen[prop], abs(dif))
        filas.append(
            rf"{_esc(etiqueta)} & {T:.0f} & {prop} & {_numero(ref)} & "
            rf"{_numero(calc)} & {dif:+.2f}\,\% & {_esc(fuente)} & {conf} \\")
    cuerpo = "\n".join(filas)
    peor_rho_cp = max(resumen["rho"], resumen["cp"])
    return rf"""
{{\small\setlength{{\tabcolsep}}{{4pt}}%
\begin{{longtable}}{{@{{}}l c c r r r l c@{{}}}}
\caption{{Validacion frente a valores tabulados de referencia}}\label{{tab:val}}\\
\toprule
\textbf{{Fluido}} & \textbf{{$T$ ($^\circ$C)}} & \textbf{{Prop.}} &
\textbf{{Referencia}} & \textbf{{Programa}} & \textbf{{Desv.}} &
\textbf{{Fuente del valor}} & \textbf{{Conf.}} \\
\midrule
\endfirsthead
\toprule
\textbf{{Fluido}} & \textbf{{$T$ ($^\circ$C)}} & \textbf{{Prop.}} &
\textbf{{Referencia}} & \textbf{{Programa}} & \textbf{{Desv.}} &
\textbf{{Fuente del valor}} & \textbf{{Conf.}} \\
\midrule
\endhead
{cuerpo}
\bottomrule
\end{{longtable}}}}

\textbf{{Lectura de la validacion.}} Desviacion maxima en densidad y
capacidad calorifica: {peor_rho_cp:.2f}\,\%; en conductividad termica:
{resumen['k']:.2f}\,\%; en viscosidad: {resumen['mu']:.2f}\,\%. La
viscosidad es la propiedad mas sensible a la fuente tabulada; las
discrepancias entre fuentes para un mismo fluido alcanzan el 2--6\,\%
(como se anota en la columna ``Fuente del valor''). Para diseno de detalle
con fluidos de viscosidad critica se recomienda contrastar con NIST
Chemistry WebBook, REFPROP/CoolProp o datos de fabrica.
"""


def _bibliografia() -> str:
    entradas = []
    for clave, cita in BIBLIO.items():
        entradas.append(rf"\bibitem{{{clave}}} {cita}")
    return "\n".join(entradas)


def generar_informe(ruta_salida: Optional[str] = None) -> str:
    """Escribe el .tex, lo compila con Tectonic y devuelve la ruta del PDF."""
    raiz = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", ".."))
    if ruta_salida is None:
        ruta_salida = os.path.join(raiz, "informe_propiedades.pdf")
    ruta_tex = os.path.splitext(ruta_salida)[0] + ".tex"

    hoy = datetime.date.today().strftime("%d/%m/%Y")
    tex = r"""\documentclass[11pt,a4paper]{article}
\usepackage[margin=2.3cm, headsep=14pt]{geometry}
\usepackage{fontspec}
\usepackage{xcolor}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{fancyhdr}
\usepackage{titlesec}
\usepackage{caption}
\usepackage{enumitem}
\usepackage{microtype}
\usepackage{amsmath}

\renewcommand{\tablename}{Tabla}
\renewcommand{\figurename}{Figura}
\renewcommand{\contentsname}{Contenido}

\definecolor{morado}{HTML}{5E2B8C}
\definecolor{acento}{HTML}{7E57C2}
\definecolor{seccion}{HTML}{EDE7F6}
\definecolor{gristexto}{HTML}{3B3648}

\titleformat{\section}{\Large\bfseries\color{morado}}{\thesection}{0.6em}{}[\vspace{2pt}{\color{acento}\titlerule}]
\titleformat{\subsection}{\large\bfseries\color{acento}}{\thesubsection}{0.5em}{}
\captionsetup{font=small, labelfont={bf,color=morado}, textfont={color=gristexto}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\color{morado}\textbf{Informe de propiedades termof\'isicas}}
\fancyhead[R]{\small\color{gristexto}Intercambiador de Tubos y Coraza}
\fancyfoot[C]{\small\color{gristexto}\thepage}
\renewcommand{\headrulewidth}{0.4pt}

\begin{document}
""" + _portada(hoy) + r"""
\tableofcontents
\newpage

\section{Objeto y alcance}
Este informe declara \textbf{todos los datos} que usa el motor de calculo del
software: de donde proviene cada propiedad termofisica, con que forma
funcional se representa, cuales son sus coeficientes numericos, en que
ventana de temperatura son validas y con que precision reproducen los
valores tabulados de referencia verificados. Los coeficientes que se listan
se leen directamente del codigo fuente (\texttt{thermo\_data.py}) al generar
este documento, de modo que el informe no puede quedar desactualizado
respecto del programa.

Todas las magnitudes estan en unidades SI: $c_p$ en J/(kg\,K), $\mu$ en
Pa\,s, $k$ en W/(m\,K), $\rho$ en kg/m$^3$ y las temperaturas en kelvin (el
programa presenta resultados en grados Celsius). El numero de Prandtl se
calcula como $\mathrm{Pr} = c_p \mu / k$.

El motor de calculo que consume estas propiedades implementa el metodo de
Kern \cite{kern} con la correlacion de conteo de tubos de Serth
\cite{serth}, y el diseno mecanico sigue el estandar TEMA Clase C
\cite{tema} y el ASME BPVC VIII-1 \cite{asme}; la interfaz y las ecuaciones
de dimensionamiento mecanico (19--32) se documentan en Tan y Fok (2006)
\cite{tan-fok}.

\section{Marco metodologico}
\subsection{Formas funcionales}
\textbf{Polinomio centrado} (para $\rho$, $c_p$ y $k$ de liquidos y del
vapor):
\[
  y(T) = c_0 + c_1 (T - T_0) + c_2 (T - T_0)^2 + c_3 (T - T_0)^3
\]
Los polinomios se centran en $T_0$ (temperatura media del rango de ajuste),
lo que reduce la correlacion entre coeficientes y mejora la precision
numerica del ajuste por minimos cuadrados.

\textbf{Viscosidad tipo DIPPR-101} (alcoholes, hidrocarburos, glicol y
amoniaco) \cite{dippr, perry}:
\[
  \mu(T) = \exp\!\left(A + \frac{B}{T} + C \ln T + D\,T\right)
\]

\textbf{Gases} (aire y vapor de agua): densidad por gas ideal
$\rho = P M / (R_u T)$ con $R_u = 8314{,}46$ J/(kmol\,K); para el aire,
$\mu$ y $k$ por la correlacion de Sutherland \cite{sutherland}:
\[
  \mu_{\mathrm{aire}}(T) = 1{,}458\times10^{-6}\,
  \frac{T^{3/2}}{T + 110{,}4}, \qquad
  k_{\mathrm{aire}}(T) = 2{,}646\times10^{-3}\,
  \frac{T^{3/2}}{T + 245{,}4\cdot 10^{-12/T}}
\]

\subsection{Politica de validez}
Cada fluido declara su ventana $[T_{\min}, T_{\max}]$; fuera de ella el
programa lanza un error y \textbf{no extrapola}: la extrapolacion de una
correlacion empirica no es fisica. Ademas, cada propiedad calculada se
valida contra signos fisicos y un rango creible de Prandtl. Las
correlaciones se evaluan a la temperatura media de cada lado, con la
correccion por viscosidad de pared $(\mu/\mu_w)^{0{,}14}$ tipica de
Sieder--Tate.

\section{Procedencia de los datos por fluido}
""" + _seccion_fuente() + r"""
\section{Correlaciones y coeficientes por fluido}
Coeficientes tal como estan escritos en \texttt{thermo\_data.py}. $T_0$ es la
temperatura de centrado del polinomio, en K.
""" + _seccion_coeficientes() + r"""
\section{Materiales solidos de construccion}
Propiedades de los metales de tubos y coraza \cite{tema}. $k_m$ y $\rho_m$ a
temperatura ambiente; $\varepsilon$ es la rugosidad absoluta y $R_f$ el
factor de ensuciamiento de diseno del estandar TEMA Clase C (1
h\,ft$^2$\,\textdegree F/Btu = 0{,}17611 m$^2$\,K/W; los valores tabulados
corresponden a 0,001 y 0,002 h\,ft$^2$\,\textdegree F/Btu de la Tabla
RGP-2.4).
""" + _seccion_materiales() + r"""
\section{Validacion numerica}
Cada punto compara el valor que devuelve la correlacion del programa con el
valor tabulado de referencia verificado (NIST Chemistry WebBook,
CoolProp/REFPROP y correlaciones de referencia publicadas). La desviacion es
$(\text{calculado} - \text{referencia})/\text{referencia}$.
""" + _seccion_validacion() + r"""
\section{Conclusiones y limitaciones de uso}
\begin{enumerate}[leftmargin=1.4em]
\item Las correlaciones son validas \textbf{solo} dentro de la ventana
declarada por fluido; fuera de ella el programa rechaza el calculo en lugar
de extrapolar.
\item El agua liquida termina en 100\,\textdegree C (ebullicion a 1 atm). El
ajuste IAPWS subyacente alcanzaba 180\,\textdegree C, pero exigiria
presurizar el equipo y el modelo es monofasico, sin presion de operacion
\cite{iapws-if97}.
\item El amoniaco se modela como liquido \textbf{saturado}: su presion es la
de saturacion (10,03 bar a 25\,\textdegree C), no 1 atm \cite{ashrae}.
\item El aire y el vapor usan gas ideal para $\rho$; frente al valor real del
vapor a 150\,\textdegree C y 1 atm la diferencia es del 0,8\,\%, aceptable
para el alcance docente; para presiones muy alejadas de 1 atm habria que
corregir el factor de compresibilidad \cite{nist}.
\item La viscosidad es la propiedad con mayor dispersion entre fuentes
(2--6\,\% para un mismo fluido) y concentra las mayores desviaciones de la
validacion.
\item Para diseno en regimen laminar, la incertidumbre de los coeficientes de
conveccion domina sobre la de las propiedades: el programa reporta bandas de
hasta $\pm 40\,\%$ sobre $U$ en esos casos.
\end{enumerate}

\section{Bibliografia}
\begin{enumerate}[label={[\arabic*]}, leftmargin=1.6em]
""" + _bibliografia() + r"""
\end{enumerate}

\end{document}
"""
    with open(ruta_tex, "w", encoding="utf-8") as fh:
        fh.write(tex)

    tectonic = _buscar_tectonic()
    if tectonic is None:
        raise RuntimeError(
            "No se encontro el compilador Tectonic. Instalelo desde "
            "https://tectonic-typesetting.github.io o coloque tectonic.exe "
            "en el PATH. El informe .tex quedo escrito en: " + ruta_tex)
    subprocess.run([tectonic, ruta_tex, "--outdir",
                    os.path.dirname(os.path.abspath(ruta_salida))],
                   check=True, capture_output=True, text=True, timeout=600)
    return ruta_salida


def _buscar_tectonic() -> Optional[str]:
    exe = "tectonic.exe" if os.name == "nt" else "tectonic"
    en_path = shutil.which("tectonic") or shutil.which(exe)
    if en_path:
        return en_path
    local = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                         "Programs", "tectonic", exe)
    return local if os.path.exists(local) else None


def main() -> int:
    ruta = sys.argv[1] if len(sys.argv) > 1 else None
    salida = generar_informe(ruta)
    print(f"Informe generado: {salida}  ({os.path.getsize(salida)/1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
