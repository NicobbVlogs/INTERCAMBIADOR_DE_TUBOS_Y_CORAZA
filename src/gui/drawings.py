# -*- coding: utf-8 -*-
"""
drawings.py - Vistas esquematicas 2D parametricas (Canvas de Tkinter).

Todo lo que se dibuja proviene de las cotas calculadas en src/mechanical y
src/thermo: no hay imagenes estaticas ni dimensiones inventadas. Cada funcion
devuelve un diccionario {tag: texto_de_cota} para que la aplicacion muestre
pop-ups interactivos al hacer clic sobre una pieza.

Los esquemas de cabezales y corazas siguen la Figura N-1.2 del estandar TEMA
("Table of TEMA types"), incluida en los PDF de la carpeta del proyecto:

    Cabezal frontal : A (canal + cubierta), B (bonete), C (canal integral con
                      espejo, haz extraible), D (cierre especial alta presion),
                      N (canal integral con espejo, espejo fijo)
    Carcasa         : E, F, G, H, J, K, X
    Cabezal trasero : L, M, N (espejo fijo), P, S, T, W (flotantes),
                      U (haz en U)

La vista «5 · Catálogo TEMA» reproduce el diagrama completo de la Fig. N-1.2
con la seleccion actual resaltada.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

AZUL = "#1f3b57"
MORADO_TITULO = "#5e2b8c"   # coherente con la paleta de la interfaz
ACERO = "#8fa6bb"
ACERO_CLARO = "#d7e1ea"
COBRE = "#c08457"
FLUIDO = "#2f7fb5"
COTA = "#a33"
DESTACADO = "#fff3cd"
BORDE_DESTACADO = "#b04a4a"
MAX_TUBOS_DIBUJADOS = 900


# =============================================================================
# 1. UTILIDADES DE ESCALA Y ACOTADO
# =============================================================================
class Lienzo:
    """Mapea coordenadas del modelo (metros) a pixeles del canvas."""

    def __init__(self, canvas, ancho_m: float, alto_m: float,
                 margen: int = 70) -> None:
        self.c = canvas
        W = canvas.winfo_width()
        H = canvas.winfo_height()
        if W < 50 or H < 50:                      # aun no mapeado en pantalla
            W, H = int(canvas["width"]), int(canvas["height"])
        self.W, self.H = W, H
        self.s = min((W - 2 * margen) / max(ancho_m, 1e-6),
                     (H - 2 * margen) / max(alto_m, 1e-6))
        self.cx, self.cy = W / 2.0, H / 2.0

    def p(self, x: float, y: float) -> Tuple[float, float]:
        """Modelo (m, origen al centro, +y arriba) -> pixel."""
        return (self.cx + x * self.s, self.cy - y * self.s)

    # ------------------------------------------------------------ primitivas
    def rect(self, x0, y0, x1, y1, **kw):
        a, b = self.p(x0, y0)
        c, d = self.p(x1, y1)
        return self.c.create_rectangle(a, b, c, d, **kw)

    def linea(self, x0, y0, x1, y1, **kw):
        a, b = self.p(x0, y0)
        c, d = self.p(x1, y1)
        return self.c.create_line(a, b, c, d, **kw)

    def circulo(self, xc, yc, r, **kw):
        a, b = self.p(xc - r, yc + r)
        c, d = self.p(xc + r, yc - r)
        return self.c.create_oval(a, b, c, d, **kw)

    def arco(self, xc, yc, r, inicio, ext, **kw):
        """Arco de `ext` grados desde `inicio` (0 = +x, sentido antihorario).

        Se dibuja como polilinea (no como `create_arc`) para que la geometria
        sea identica en cualquier plataforma de Tk. Acepta `outline` (color
        del borde) y `fill` (relleno del sector circular).
        """
        pasos = max(int(abs(ext) / 6.0) + 2, 3)
        pts = []
        for i in range(pasos + 1):
            ang = math.radians(inicio + ext * i / pasos)
            a, b = self.p(xc + r * math.cos(ang), yc + r * math.sin(ang))
            pts.extend((a, b))
        borde = kw.pop("outline", kw.get("fill", AZUL))
        relleno = kw.pop("fill", "")
        tags = kw.get("tags")
        if relleno:
            xc_p, yc_p = self.p(xc, yc)
            self.c.create_polygon(*pts, xc_p, yc_p, fill=relleno,
                                  outline="", tags=tags)
        kw["fill"] = borde
        kw.setdefault("smooth", True)
        return self.c.create_line(*pts, **kw)

    def texto(self, x, y, txt, **kw):
        a, b = self.p(x, y)
        kw.setdefault("font", ("Segoe UI", 8))
        kw.setdefault("fill", AZUL)
        return self.c.create_text(a, b, text=txt, **kw)

    # ----------------------------------------------------------- acotaciones
    def cota_h(self, x0: float, x1: float, y: float, texto: str) -> None:
        a, b = self.p(x0, y)
        c, d = self.p(x1, y)
        self.c.create_line(a, b, c, d, fill=COTA, arrow="both", width=1)
        self.c.create_line(a, b - 6, a, b + 6, fill=COTA)
        self.c.create_line(c, d - 6, c, d + 6, fill=COTA)
        self.c.create_text((a + c) / 2, b - 9, text=texto, fill=COTA,
                           font=("Segoe UI", 8, "bold"))

    def cota_v(self, y0: float, y1: float, x: float, texto: str) -> None:
        a, b = self.p(x, y0)
        c, d = self.p(x, y1)
        self.c.create_line(a, b, c, d, fill=COTA, arrow="both", width=1)
        self.c.create_line(a - 6, b, a + 6, b, fill=COTA)
        self.c.create_line(c - 6, d, c + 6, d, fill=COTA)
        self.c.create_text(a - 6, (b + d) / 2, text=texto, fill=COTA,
                           angle=90, font=("Segoe UI", 8, "bold"))


def mm(valor_m: float) -> str:
    return f"{valor_m * 1000.0:.1f} mm"


def _titulo(canvas, texto: str, subtitulo: str = "") -> None:
    canvas.create_text(14, 14, text=texto, anchor="nw", fill=MORADO_TITULO,
                       font=("Segoe UI", 11, "bold"))
    if subtitulo:
        canvas.create_text(14, 34, text=subtitulo, anchor="nw",
                           fill="#6d5b95", font=("Segoe UI", 8))


def _sin_datos(canvas, mensaje: str) -> Dict[str, str]:
    canvas.delete("all")
    canvas.create_text(canvas.winfo_width() / 2 or 400,
                       canvas.winfo_height() / 2 or 250,
                       text=mensaje, fill="#8795a1",
                       font=("Segoe UI", 10), width=420, justify="center")
    return {}


# =============================================================================
# 2. POSICIONES DEL HAZ DE TUBOS (geometria de dibujo, no de calculo)
# =============================================================================
def posiciones_tubos(P_T: float, D_ctl: float, layout: int,
                     n_max: int) -> List[Tuple[float, float]]:
    """Centros de tubo sobre el arreglo, recortados al circulo D_ctl."""
    r_lim = D_ctl / 2.0
    dy = P_T * math.sqrt(3.0) / 2.0 if layout in (30, 60) else P_T
    filas = int(r_lim / dy) + 2
    cols = int(r_lim / P_T) + 2
    puntos: List[Tuple[float, float]] = []
    for i in range(-filas, filas + 1):
        y = i * dy
        desfase = (P_T / 2.0) if (layout in (30, 60) and i % 2) else 0.0
        for j in range(-cols, cols + 1):
            x = j * P_T + desfase
            if math.hypot(x, y) <= r_lim + 1e-9:
                puntos.append((x, y))
    puntos.sort(key=lambda t: math.hypot(t[0], t[1]))
    return puntos[:n_max]


def dibujar_haz_tubos(lz: Lienzo, puntos: List[Tuple[float, float]],
                      r: float, tags: Tuple[str, ...],
                      fill: str, outline: str = AZUL,
                      limite_px: float = 2.2) -> int:
    """
    Dibuja el conjunto de tubos de forma económica. Devuelve el numero de
    tubos REPRESENTADOS (el total real siempre va en las cotas).

    Si el diametro del tubo a escala cae por debajo de `limite_px`, los
    circulos individuales quedan subpixel y no aportan informacion: se
    sustituyen por un disco macizo (el haz embalado) con el anillo exterior
    muestreado. Mismo aspecto a esa escala, con ~1800 objetos menos en el
    Canvas: el redibujado al redimensionar la ventana vuelve a ser fluido.
    """
    if not puntos:
        return 0
    if 2.0 * r * lz.s >= limite_px:
        for (x, y) in puntos:
            lz.circulo(x, y, r, outline=outline, fill=fill, tags=tags)
        return len(puntos)

    r_b = max(math.hypot(x, y) for x, y in puntos) + r
    lz.circulo(0.0, 0.0, r_b, outline=outline, fill=fill, tags=tags)
    anillo = [p for p in puntos if math.hypot(p[0], p[1]) > 0.70 * r_b]
    for (x, y) in anillo[:60]:
        lz.circulo(x, y, r, outline=outline, fill="", tags=tags)
    return len(puntos)


# =============================================================================
# 3. DIAGRAMAS DE TIPO TEMA (Figura N-1.2)
# =============================================================================
def _noquilla(lz: Lienzo, x: float, y_base: float, signo: float, d: float,
              largo: float, tags: Tuple[str, ...] = ("nozzle",)) -> None:
    """Boquilla simple (tubo + brida) saliendo de la pared de la coraza."""
    lz.rect(x - d / 2.0, y_base, x + d / 2.0, y_base + signo * largo,
            fill=ACERO_CLARO, outline=AZUL, tags=tags)
    lz.rect(x - d * 0.8, y_base + signo * largo,
            x + d * 0.8, y_base + signo * (largo + d * 0.18),
            fill=ACERO, outline=AZUL, tags=tags)


def dibujar_cuerpo_coraza(lz: Lienzo, x0: float, x1: float,
                          D_s: float, D_o: float) -> None:
    """Dos franjas de pared de coraza + lineas punteadas del D_s."""
    for signo in (1, -1):
        lz.rect(x0, signo * D_s / 2.0, x1, signo * D_o / 2.0,
                fill=ACERO, outline=AZUL, width=1, tags=("carcasa",))
    lz.linea(x0, D_s / 2.0, x1, D_s / 2.0, fill=AZUL, dash=(2, 2))
    lz.linea(x0, -D_s / 2.0, x1, -D_s / 2.0, fill=AZUL, dash=(2, 2))


def dibujar_nozzles_coraza(lz: Lienzo, tipo: str, x0: float, x1: float,
                           D_s: float, D_o: float) -> None:
    """
    Boquillas segun el tipo de coraza (Fig. N-1.2):
        E: entrada arriba (extremo caliente) y salida abajo (extremo frio)
        F: entrada y salida en el MISMO extremo + deflector longitudinal
        G: entrada y salida al centro (flujo partido) + deflector central
        H: dos pares de boquillas (flujo doble partido)
        J: entrada al centro, dos salidas (flujo dividido)
        K: boquillas sobre el cuerpo ampliado de la caldera
        X: entrada y salida al centro (flujo cruzado, sin deflectores)
    """
    L = x1 - x0
    d_noz = min(D_o * 0.22, L * 0.10)
    largo = D_o * 0.30
    if tipo == "E":
        _noquilla(lz, x0 + L * 0.18, D_o / 2.0, +1, d_noz, largo, ("boq_s_in",))
        _noquilla(lz, x1 - L * 0.18, -D_o / 2.0, -1, d_noz, largo, ("boq_s_out",))
    elif tipo == "F":
        _noquilla(lz, x0 + L * 0.18, D_o / 2.0, +1, d_noz, largo, ("boq_s_in",))
        _noquilla(lz, x0 + L * 0.18, -D_o / 2.0, -1, d_noz, largo, ("boq_s_out",))
    elif tipo == "G":
        _noquilla(lz, (x0 + x1) / 2.0, D_o / 2.0, +1, d_noz, largo, ("boq_s_in",))
        _noquilla(lz, (x0 + x1) / 2.0, -D_o / 2.0, -1, d_noz, largo, ("boq_s_out",))
    elif tipo == "H":
        for fx in (0.25, 0.75):
            _noquilla(lz, x0 + L * fx, D_o / 2.0, +1, d_noz, largo, ("boq_s_in",))
            _noquilla(lz, x0 + L * fx, -D_o / 2.0, -1, d_noz, largo, ("boq_s_out",))
    elif tipo == "J":
        _noquilla(lz, (x0 + x1) / 2.0, D_o / 2.0, +1, d_noz, largo, ("boq_s_in",))
        for fx in (0.25, 0.75):
            _noquilla(lz, x0 + L * fx, -D_o / 2.0, -1, d_noz, largo, ("boq_s_out",))
    elif tipo == "K":
        _noquilla(lz, x0 + L * 0.55, D_o * 0.85, +1, d_noz, largo, ("boq_s_in",))
        _noquilla(lz, x0 + L * 0.45, -D_o * 0.85, -1, d_noz, largo, ("boq_s_out",))
    else:  # X
        _noquilla(lz, (x0 + x1) / 2.0, D_o / 2.0, +1, d_noz, largo, ("boq_s_in",))
        _noquilla(lz, (x0 + x1) / 2.0, -D_o / 2.0, -1, d_noz, largo, ("boq_s_out",))


def dibujar_deflectores_coraza(lz: Lienzo, tipo: str, x0: float, x1: float,
                               D_s: float, N_B: int, L_bc: float,
                               L_bi: float, e_baffle: float,
                               corte: float) -> None:
    """Deflectores segmentados (E/F/K), placas (X/G/H/J) y deflector de F/G."""
    L = x1 - x0
    if tipo in ("F", "G"):
        # Deflector longitudinal (soldado/sellado): linea horizontal central.
        lz.linea(x0 + L * 0.02, 0.0, x1 - L * 0.02, 0.0, fill="#b04a4a",
                 width=2, dash=(6, 3), tags=("baffles",))
    if tipo == "H":
        for fx in (0.30, 0.70):
            lz.linea(x0 + L * (fx - 0.12), 0.0, x0 + L * (fx + 0.12), 0.0,
                     fill="#b04a4a", width=2, dash=(6, 3), tags=("baffles",))

    h_baffle = D_s * (1.0 - corte) if tipo != "X" else D_s * 0.92
    for i in range(N_B):
        x = x0 + L_bi + i * L_bc
        if x >= x1:
            break
        arriba = (i % 2 == 0) and tipo != "X"
        if tipo == "X":
            lz.rect(x - e_baffle / 2.0, -D_s / 2.0, x + e_baffle / 2.0,
                    D_s / 2.0, fill="#c9d4de", outline=AZUL, tags=("baffles",))
            continue
        y_a = D_s / 2.0 if arriba else -D_s / 2.0
        y_b = y_a - h_baffle if arriba else y_a + h_baffle
        lz.rect(x - e_baffle / 2.0, y_a, x + e_baffle / 2.0, y_b,
                fill="#44607a", outline=AZUL, tags=("baffles",))


def _bloque_cabezal(lz: Lienzo, x0: float, x1: float, D_o: float,
                    clave: str, fill: str = ACERO_CLARO) -> None:
    lz.rect(min(x0, x1), -D_o / 2.0, max(x0, x1), D_o / 2.0,
            fill=fill, outline=AZUL, width=2, tags=(clave,))


def dibujar_cabezal_frontal(lz: Lienzo, tipo: str, xh0: float, xh1: float,
                            D_o: float, D_s: float, T_c: float,
                            n_pasos: int, clave: str = "cab_front") -> None:
    """
    Cabezal frontal segun Fig. N-1.2 (xh0 = extremo lejano, xh1 = junto al
    espejo). lado = -1 (la coraza queda a la derecha).
    """
    ancho = xh1 - xh0
    d_noz = min(D_o * 0.20, ancho * 0.35)
    if tipo == "B":
        # Bonete (cubierta integral): cuerpo + fondo redondeado hacia afuera.
        lz.rect(xh0 + ancho * 0.35, -D_o / 2.0, xh1, D_o / 2.0,
                fill=ACERO_CLARO, outline=AZUL, width=2, tags=(clave,))
        lz.arco(xh0 + ancho * 0.35, 0.0, D_o / 2.0, 90, 180,
                fill=ACERO_CLARO, outline=AZUL, width=2, tags=(clave,))
    elif tipo == "D":
        # Cierre especial de alta presion: bloque forjado con camara interior.
        lz.rect(xh0, -D_o * 0.62, xh1, D_o * 0.62,
                fill=ACERO, outline=AZUL, width=2, tags=(clave,))
        lz.rect(xh0 + ancho * 0.30, -D_s / 2.0, xh1 - ancho * 0.05, D_s / 2.0,
                fill="white", outline=AZUL, tags=(clave,))
        lz.rect(xh0, -D_s * 0.28, xh0 + ancho * 0.30, D_s * 0.28,
                fill="#6f8296", outline=AZUL, tags=(clave,))
    else:
        # A / C / N: canal con cubierta plana desmontable a la izquierda.
        _bloque_cabezal(lz, xh0 + T_c * 1.2, xh1, D_o, clave)
        lz.rect(xh0, -D_o * 0.56, xh0 + T_c * 1.2, D_o * 0.56,
                fill="#6f8296", outline=AZUL, width=2, tags=(clave,))
        # pernos de la cubierta (marcas verticales)
        for frac in (-0.38, -0.13, 0.13, 0.38):
            lz.linea(xh0 + T_c * 0.2, frac * D_o, xh0 + T_c * 1.1, frac * D_o,
                     fill=AZUL, width=1, tags=(clave,))
        if tipo == "C":
            # Junta de brida de corona: el haz se extrae por un extremo.
            lz.linea(xh1 - ancho * 0.10, -D_o / 2.0, xh1 - ancho * 0.10,
                     D_o / 2.0, fill=AZUL, width=2, tags=(clave,))
            lz.texto((xh0 + xh1) / 2.0, D_o * 0.62, "haz extraíble",
                     font=("Segoe UI", 7), fill="#5a6b7b")
        if tipo == "N":
            lz.rect(xh1 - ancho * 0.06, -D_o / 2.0, xh1, D_o / 2.0,
                    fill="#6f8296", outline=AZUL, tags=(clave,))

    # boquilla superior + particion de pasos (punteada)
    _noquilla(lz, (xh0 + xh1) / 2.0, D_o / 2.0, +1, d_noz, D_o * 0.22,
              ("cab_front",))
    if n_pasos >= 2:
        lz.linea(xh0 + T_c * 1.2, 0.0, xh1, 0.0, fill="#b04a4a", width=2,
                 dash=(5, 3), tags=("particion",))


def dibujar_cabezal_trasero(lz: Lienzo, tipo: str, xh0: float, xh1: float,
                            D_o: float, D_s: float, T_c: float,
                            clave: str = "cab_tras") -> None:
    """
    Cabezal trasero segun Fig. N-1.2 (xh0 = junto al espejo, xh1 = extremo
    lejano). lado = +1 (la coraza queda a la izquierda).
    """
    ancho = xh1 - xh0
    if tipo == "U":
        # Haz en U: tubos curvados, sin espejo ni cubierta trasera.
        for i, r in enumerate((D_s * 0.10, D_s * 0.22, D_s * 0.34)):
            lz.arco(xh0, 0.0, r, -90, 180, outline=COBRE, width=2,
                    tags=(clave,))
        return
    if tipo in ("L", "N"):
        _bloque_cabezal(lz, xh0, xh1 - T_c * 1.2, D_o, clave)
        lz.rect(xh1 - T_c * 1.2, -D_o * 0.56, xh1, D_o * 0.56,
                fill="#6f8296", outline=AZUL, width=2, tags=(clave,))
        for frac in (-0.38, -0.13, 0.13, 0.38):
            lz.linea(xh1 - T_c * 1.1, frac * D_o, xh1 - T_c * 0.2, frac * D_o,
                     fill=AZUL, width=1, tags=(clave,))
    elif tipo == "M":
        lz.rect(xh0, -D_o / 2.0, xh1 - ancho * 0.35, D_o / 2.0,
                fill=ACERO_CLARO, outline=AZUL, width=2, tags=(clave,))
        lz.arco(xh1 - ancho * 0.35, 0.0, D_o / 2.0, -90, 180,
                outline=AZUL, width=2, tags=(clave,))
        lz.rect(xh1 - ancho * 0.35, -D_o / 2.0, xh0 + ancho * 0.0, D_o / 2.0,
                fill=ACERO_CLARO, outline="", tags=(clave,))
    elif tipo == "P":
        # Cabezal flotante con prensaestopas exterior.
        _bloque_cabezal(lz, xh0, xh0 + ancho * 0.35, D_o, clave)
        lz.rect(xh0 + ancho * 0.12, -D_o * 0.34, xh0 + ancho * 0.55,
                D_o * 0.34, fill="#6f8296", outline=AZUL, tags=(clave,))
        for signo in (1, -1):
            lz.rect(xh0 + ancho * 0.02, signo * D_s * 0.30,
                    xh0 + ancho * 0.16, signo * D_s * 0.52,
                    fill="#44607a", outline=AZUL, tags=(clave,))
    elif tipo == "S":
        # Cabezal flotante con anillo de retencion (backing device).
        _bloque_cabezal(lz, xh0, xh0 + ancho * 0.30, D_o, clave)
        lz.rect(xh0 + ancho * 0.30, -D_s * 0.42, xh0 + ancho * 0.62,
                D_s * 0.42, fill="#6f8296", outline=AZUL, tags=(clave,))
        lz.linea(xh0 + ancho * 0.62, -D_s * 0.42, xh0 + ancho * 0.62,
                 D_s * 0.42, fill="#b04a4a", width=3, tags=(clave,))
    elif tipo == "T":
        # Cabezal flotante de paso por la coraza (pull through).
        _bloque_cabezal(lz, xh0, xh0 + ancho * 0.25, D_o, clave)
        lz.rect(xh0 + ancho * 0.25, -D_s * 0.55, xh0 + ancho * 0.75,
                D_s * 0.55, fill="#6f8296", outline=AZUL, width=2,
                tags=(clave,))
        lz.linea(xh0 + ancho * 0.75, -D_s * 0.55, xh1, -D_s * 0.55,
                 fill=AZUL, dash=(4, 3), tags=(clave,))
        lz.linea(xh0 + ancho * 0.75, D_s * 0.55, xh1, D_s * 0.55,
                 fill=AZUL, dash=(4, 3), tags=(clave,))
    elif tipo == "W":
        # Espejo flotante sellado exteriormente (anillo linterna).
        _bloque_cabezal(lz, xh0, xh0 + ancho * 0.45, D_o, clave)
        for signo in (1, -1):
            lz.rect(xh0 + ancho * 0.05, signo * D_s * 0.28,
                    xh0 + ancho * 0.30, signo * D_s * 0.50,
                    fill="#44607a", outline=AZUL, tags=(clave,))
        lz.linea(xh0 + ancho * 0.45, -D_s * 0.36, xh1, -D_s * 0.36,
                 fill=AZUL, dash=(4, 3), tags=(clave,))
        lz.linea(xh0 + ancho * 0.45, D_s * 0.36, xh1, D_s * 0.36,
                 fill=AZUL, dash=(4, 3), tags=(clave,))


# =============================================================================
# 4. VISTA 1: CARCASA (ELEVACION LONGITUDINAL)
# =============================================================================
def dibujar_carcasa(canvas, g: Dict[str, object]) -> Dict[str, str]:
    """Corte longitudinal: carcasa, espejos, baffles, tubos y boquillas."""
    canvas.delete("all")
    if not g:
        return _sin_datos(canvas, "Ejecute primero un cálculo en la pestaña "
                                  "Design para generar el dibujo.")

    D_s, D_o = g["D_s"], g["D_o"]
    L, L_ts = g["L"], g["L_ts"]
    L_tot = g["L_total"]
    tipo_coraza = str(g.get("tipo_carcasa", "E")).upper()
    cab_frontal = str(g.get("cab_frontal", "A")).upper()
    cab_trasero = str(g.get("cab_trasero", "M")).upper()
    lz = Lienzo(canvas, L_tot * 1.35, max(D_o * 3.4, 0.25))
    cotas: Dict[str, str] = {}

    x0, x1 = -L / 2.0, L / 2.0
    e = (D_o - D_s) / 2.0        # espesor de carcasa

    # --- cuerpo de carcasa -------------------------------------------------
    dibujar_cuerpo_coraza(lz, x0, x1, D_s, D_o)
    if tipo_coraza == "K":
        # Caldera: el cuerpo se amplia sobre el haz (espacio de separacion de
        # vapor) con una transicion inclinada, como en la Fig. N-1.2.
        x_a = x0 + L * 0.28
        x_b = x0 + L * 0.45
        for signo in (1, -1):
            lz.linea(x_a, signo * D_o / 2.0, x_b, signo * D_o * 0.85,
                     fill=AZUL, width=2, tags=("carcasa",))
            lz.rect(x_b, signo * D_o / 2.0, x1, signo * D_o * 0.85,
                    fill=ACERO, outline=AZUL, width=1, tags=("carcasa",))
        lz.linea(x_b, D_o * 0.85, x1, D_o * 0.85, fill=AZUL, width=1)
        lz.linea(x_b, -D_o * 0.85, x1, -D_o * 0.85, fill=AZUL, width=1)
        lz.linea(x0 + L * 0.80, -D_o * 0.30, x0 + L * 0.80, -D_o * 0.05,
                 fill="#b04a4a", dash=(3, 2), tags=("carcasa",))
    cotas["carcasa"] = (
        f"CARCASA TEMA tipo {tipo_coraza}\n"
        f"  {g.get('desc_carcasa', '')}\n"
        f"  Diámetro interior D_s  = {mm(D_s)}\n"
        f"  Espesor de pared  t_s  = {mm(e)}\n"
        f"  Diámetro exterior D_o  = {mm(D_o)}\n"
        f"  Longitud total del equipo = {L_tot:.3f} m\n"
        f"  Material: {g['material']}")

    # --- espejos de tubos ---------------------------------------------------
    for signo in (-1, 1):
        xa = signo * (L / 2.0)
        xb = xa + signo * L_ts
        lz.rect(min(xa, xb), -D_o / 2.0, max(xa, xb), D_o / 2.0,
                fill="#6f8296", outline=AZUL, tags=("espejo",))
    cotas["espejo"] = (f"ESPEJO DE TUBOS (tubesheet)\n"
                       f"  Espesor L_ts = {mm(L_ts)}  (TEMA C-7.1.1)\n"
                       f"  Perforado para {g['N_tt']} tubos de "
                       f"{mm(g['d_o'])} Ø")

    # --- tubos --------------------------------------------------------------
    n_lineas = min(9, max(3, int(D_s / max(g["P_T"], 1e-4))))
    paso = D_s * 0.80 / (n_lineas - 1) if n_lineas > 1 else 0.0
    for i in range(n_lineas):
        y = -D_s * 0.40 + i * paso
        lz.linea(x0, y, x1, y, fill=COBRE, width=2, tags=("tubos",))
    cotas["tubos"] = (f"HAZ DE TUBOS\n"
                      f"  N.º total de tubos N_tt = {g['N_tt']}\n"
                      f"  Ø exterior = {mm(g['d_o'])}   pitch = {mm(g['P_T'])}\n"
                      f"  Longitud efectiva L = {L:.3f} m\n"
                      f"  Pasos por tubos = {g['n_pasos']}\n"
                      f"  Límite exterior del haz D_otl = {mm(g['D_otl'])}")

    # --- deflectores segun tipo de coraza -----------------------------------
    N_B, L_bc = int(g["N_B"]), g["L_bc"]
    dibujar_deflectores_coraza(lz, tipo_coraza, x0, x1, D_s, N_B, L_bc,
                               g["L_bi"], g["e_baffle"], g["corte"])
    cotas["baffles"] = (
        f"{'PLACAS SOPORTE' if tipo_coraza == 'X' else 'PLACAS DEFLECTORAS'}\n"
        f"  Cantidad N_B = {N_B}\n"
        f"  Espaciado central L_bc = {mm(L_bc)}\n"
        f"  Espaciado entrada/salida L_bi = {mm(g['L_bi'])}\n"
        f"  Corte = {g['corte']*100:.0f} %  "
        f"(altura {mm(g['altura_corte'])})\n"
        f"  Espesor de placa = {mm(g['e_baffle'])}  (TEMA CB-4.4.1)")

    # --- boquillas de coraza segun tipo -------------------------------------
    dibujar_nozzles_coraza(lz, tipo_coraza, x0, x1, D_s, D_o)
    info = g.get("boq_s")
    if info:
        cotas["boq_s_in"] = cotas["boq_s_out"] = (
            f"BOQUILLAS DE CORAZA ({tipo_coraza})\n"
            f"  Tubería comercial: {info['nps']}\n"
            f"  Ø interior = {mm(info['D_i'])}   Ø exterior = {mm(info['D_e'])}\n"
            f"  Espesor = {mm(info['espesor'])}\n"
            f"  Velocidad real = {info['V_real']:.2f} m/s "
            f"(máx. admisible {info['V_max']:.2f} m/s)")

    # --- cabezales (diagrama por tipo TEMA) ---------------------------------
    largo_cab = max((L_tot - L - 2 * L_ts) / 2.0, D_s * 0.35)
    xh0_f = -L / 2.0 - L_ts - largo_cab
    xh1_f = -L / 2.0 - L_ts
    dibujar_cabezal_frontal(lz, cab_frontal, xh0_f, xh1_f, D_o, D_s,
                            g.get("T_c", D_s * 0.06), int(g["n_pasos"]))
    lz.texto((xh0_f + xh1_f) / 2.0, -D_o * 0.95, cab_frontal,
             font=("Segoe UI", 11, "bold"))

    xh0_t = L / 2.0 + L_ts
    xh1_t = L / 2.0 + L_ts + largo_cab
    dibujar_cabezal_trasero(lz, cab_trasero, xh0_t, xh1_t, D_o, D_s,
                            g.get("T_c_tras", g.get("T_c", D_s * 0.06)))
    lz.texto((xh0_t + xh1_t) / 2.0, -D_o * 0.95, cab_trasero,
             font=("Segoe UI", 11, "bold"))

    cotas["cab_front"] = (
        f"CABEZAL FRONTAL TEMA «{cab_frontal}»\n"
        f"  {g.get('desc_cab_frontal', '')}\n"
        f"  Tipo de cubierta: {g.get('tipo_cubierta', '–')}\n"
        f"  Espesor de cubierta T_c = {mm(g.get('T_c', 0.0))}\n"
        f"  Reparte el flujo en {g['n_pasos']} paso(s).")
    cotas["cab_tras"] = (
        f"CABEZAL TRASERO TEMA «{cab_trasero}»\n"
        f"  {g.get('desc_cab_trasero', '')}\n"
        f"  Tipo de cubierta: {g.get('tipo_cubierta_tras', '–')}\n"
        f"  Espesor de cubierta = {mm(g.get('T_c_tras', 0.0))}\n"
        f"  Ø interior de carcasa = {mm(D_s)}")
    cotas["particion"] = (f"PLACAS DE PARTICIÓN DE PASO\n"
                          f"  {g['n_pasos']} pasos por el lado de tubos.")

    # --- acotaciones --------------------------------------------------------
    lz.cota_h(-L_tot / 2.0, L_tot / 2.0, -D_o * 1.25, f"L total = {L_tot:.3f} m")
    lz.cota_h(x0, x1, -D_o * 0.85, f"L tubos = {L:.3f} m")
    lz.cota_v(-D_o / 2.0, D_o / 2.0, -L_tot / 2.0 - D_s * 0.22, mm(D_o))

    _titulo(canvas,
            f"Vista 1 · Carcasa — corte longitudinal (tipo TEMA "
            f"{cab_frontal}{tipo_coraza}{cab_trasero})",
            "Haga clic sobre cualquier pieza para ver sus cotas exactas.")
    return cotas


# =============================================================================
# 5. VISTA 2: DISTRIBUCION DE TUBOS (SECCION TRANSVERSAL)
# =============================================================================
def dibujar_layout(canvas, g: Dict[str, object]) -> Dict[str, str]:
    canvas.delete("all")
    if not g:
        return _sin_datos(canvas, "Ejecute primero un cálculo en la pestaña "
                                  "Design para generar el dibujo.")

    D_s, D_o = g["D_s"], g["D_o"]
    lz = Lienzo(canvas, D_o * 1.5, D_o * 1.25)
    cotas: Dict[str, str] = {}

    lz.circulo(0, 0, D_o / 2.0, outline=AZUL, width=2, fill=ACERO,
               tags=("carcasa",))
    lz.circulo(0, 0, D_s / 2.0, outline=AZUL, width=2, fill="white",
               tags=("carcasa",))
    lz.circulo(0, 0, g["D_otl"] / 2.0, outline="#b04a4a", dash=(4, 3),
               tags=("otl",))
    cotas["carcasa"] = (f"CARCASA (sección transversal)\n"
                        f"  D_s = {mm(D_s)}   D_o = {mm(D_o)}\n"
                        f"  Espesor = {mm((D_o - D_s) / 2.0)}")
    cotas["otl"] = (f"LÍMITE EXTERIOR DEL HAZ\n"
                    f"  D_otl = {mm(g['D_otl'])}\n"
                    f"  D_ctl (centros periféricos) = {mm(g['D_ctl'])}\n"
                    f"  Claro carcasa–haz = {mm((D_s - g['D_otl']) / 2.0)}")

    n_dib = min(int(g["N_tt"]), MAX_TUBOS_DIBUJADOS)
    puntos = posiciones_tubos(g["P_T"], g["D_ctl"], int(g["layout"]), n_dib)
    r = g["d_o"] / 2.0
    dibujar_haz_tubos(lz, puntos, r, ("tubos",), COBRE)
    cotas["tubos"] = (
        f"ARREGLO DE TUBOS — layout {g['layout']}°\n"
        f"  N.º total de tubos = {g['N_tt']}  (dibujados {len(puntos)})\n"
        f"  Ø exterior d_o = {mm(g['d_o'])}\n"
        f"  Pitch P_T = {mm(g['P_T'])}   P_T/d_o = {g['P_T']/g['d_o']:.2f}\n"
        f"  Claro entre tubos = {mm(g['P_T'] - g['d_o'])}")

    # Particiones de paso (canal del cabezal).
    n_p = int(g["n_pasos"])
    if n_p >= 2:
        lz.linea(-D_s / 2.0, 0, D_s / 2.0, 0, fill="#b04a4a", width=3,
                 tags=("particion",))
    if n_p >= 4:
        lz.linea(0, -D_s / 2.0, 0, D_s / 2.0, fill="#b04a4a", width=3,
                 tags=("particion",))
    if n_p >= 2:
        cotas["particion"] = (f"PLACAS DE PARTICIÓN DE PASO\n"
                              f"  {n_p} pasos por el lado de tubos.\n"
                              "  Reducen el área útil del espejo (constante "
                              "C_TP del conteo de tubos).")

    lz.cota_h(-D_s / 2.0, D_s / 2.0, -D_o * 0.60, f"D_s = {mm(D_s)}")
    if len(puntos) > 1:
        lz.texto(0, D_o * 0.60,
                 f"{len(puntos)} tubos representados · escala "
                 f"{lz.s:.0f} px/m", fill="#5a6b7b")

    _titulo(canvas, "Vista 2 · Distribución de tubos (espejo)",
            "Clic sobre un tubo, la carcasa o el límite del haz para sus cotas.")
    return cotas


# =============================================================================
# 6. VISTA 3: PLACA DEFLECTORA (BAFFLE)
# =============================================================================
def dibujar_baffle(canvas, g: Dict[str, object]) -> Dict[str, str]:
    canvas.delete("all")
    if not g:
        return _sin_datos(canvas, "Ejecute primero un cálculo en la pestaña "
                                  "Design para generar el dibujo.")

    D_b = g["D_baffle"]
    lz = Lienzo(canvas, D_b * 1.6, D_b * 1.35)
    cotas: Dict[str, str] = {}

    y_corte = D_b / 2.0 - g["altura_corte"]
    lz.circulo(0, 0, D_b / 2.0, outline=AZUL, width=2, fill=ACERO_CLARO,
               tags=("placa",))

    # Perforaciones para los tubos (dibujo económico: ver dibujar_haz_tubos).
    n_dib = min(int(g["N_tt"]), MAX_TUBOS_DIBUJADOS)
    r = (g["d_o"] + g.get("luz_tubo", 0.0)) / 2.0 if "luz_tubo" in g \
        else g["d_o"] / 2.0
    puntos = posiciones_tubos(g["P_T"], g["D_ctl"], int(g["layout"]), n_dib)
    dibujar_haz_tubos(lz, puntos, r, ("perforacion",), "white",
                      outline="#6f8296")

    # Segmento cortado (zona de paso del fluido): se pinta ENCIMA de las
    # perforaciones, de modo que el corte tape los tubos de esa franja.
    a, b = lz.p(-D_b / 2.0, D_b / 2.0)
    c, d = lz.p(D_b / 2.0, y_corte)
    canvas.create_rectangle(a, b, c, d, outline="", fill="white",
                            tags=("corte",))
    lz.circulo(0, 0, D_b / 2.0, outline=AZUL, width=2, tags=("placa",))
    lz.linea(-D_b / 2.0, y_corte, D_b / 2.0, y_corte, fill="#b04a4a",
             width=2, tags=("corte",))

    cotas["placa"] = (f"PLACA DEFLECTORA SEGMENTADA\n"
                      f"  Ø de placa = {mm(D_b)}\n"
                      f"  Espesor = {mm(g['e_baffle'])}  (TEMA CB-4.4.1)\n"
                      f"  Claro placa–carcasa = {mm((g['D_s'] - D_b) / 2.0)}"
                      f"  (TEMA RCB-4.3)\n"
                      f"  Cantidad instalada = {int(g['N_B'])}")
    cotas["corte"] = (f"CORTE DEL BAFFLE\n"
                      f"  Fracción de corte = {g['corte']*100:.0f} % de D_s\n"
                      f"  Altura del segmento = {mm(g['altura_corte'])}\n"
                      "  Es la ventana por donde el fluido de coraza "
                      "cruza de un compartimento al siguiente.\n"
                      "  (Orientaciones posibles según TEMA RCB-4.1: "
                      "horizontal, vertical o rotada.)")
    cotas["perforacion"] = (f"PERFORACIONES\n"
                            f"  Ø nominal del tubo = {mm(g['d_o'])}\n"
                            f"  Tramo máximo sin soporte = "
                            f"{g['luz_sin_soporte']:.3f} m")

    # Varillas tensores (TEMA CB-4.7.1) alrededor del haz.
    tie = g.get("tie_rods")
    if tie:
        n, d_rod = int(tie.get("cantidad", 0)), float(tie.get("d", 0.0))
        if n > 0:
            r_rod = D_b * 0.44
            for i in range(n):
                ang = 2.0 * math.pi * i / n + math.pi / n
                lz.circulo(r_rod * math.cos(ang), r_rod * math.sin(ang),
                           d_rod / 2.0, outline=AZUL, fill="#44607a",
                           tags=("tie_rod",))
            cotas["tie_rod"] = (f"VARILLAS TENSORES Y ESPACIADORES\n"
                                f"  Cantidad = {n}\n"
                                f"  Ø de varilla = {mm(d_rod)}\n"
                                "  Retienen todas las placas en su posición "
                                "(TEMA CB-4.7.1).")

    lz.cota_h(-D_b / 2.0, D_b / 2.0, -D_b * 0.62, f"Ø = {mm(D_b)}")
    lz.cota_v(y_corte, D_b / 2.0, D_b * 0.62, mm(g["altura_corte"]))

    _titulo(canvas, "Vista 3 · Placa deflectora (baffle segmentado)",
            "La zona blanca superior es el corte; abajo, las perforaciones.")
    return cotas


# =============================================================================
# 7. VISTA 4: CABEZAL Y BRIDA
# =============================================================================
def dibujar_cabezal(canvas, g: Dict[str, object]) -> Dict[str, str]:
    canvas.delete("all")
    if not g:
        return _sin_datos(canvas, "Ejecute primero un cálculo en la pestaña "
                                  "Design para generar el dibujo.")

    D_F, D_BC, D_o, D_s = g["D_F"], g["D_BC"], g["D_o"], g["D_s"]
    cab_frontal = str(g.get("cab_frontal", "A")).upper()
    lz = Lienzo(canvas, D_F * 2.3, D_F * 1.3)
    cotas: Dict[str, str] = {}

    # --- Izquierda: brida de frente ----------------------------------------
    cx = -D_F * 0.55
    lz.circulo(cx, 0, D_F / 2.0, outline=AZUL, width=2, fill=ACERO,
               tags=("brida",))
    lz.circulo(cx, 0, D_o / 2.0, outline=AZUL, fill=ACERO_CLARO,
               tags=("brida",))
    lz.circulo(cx, 0, D_s / 2.0, outline=AZUL, fill="white", tags=("brida",))
    lz.circulo(cx, 0, D_BC / 2.0, outline="#b04a4a", dash=(3, 3),
               tags=("pernos",))
    n_pernos = int(g["n_pernos"])
    for i in range(n_pernos):
        ang = 2.0 * math.pi * i / n_pernos
        x = cx + (D_BC / 2.0) * math.cos(ang)
        y = (D_BC / 2.0) * math.sin(ang)
        lz.circulo(x, y, g["d_perno"] / 2.0, outline=AZUL, fill="#44607a",
                   tags=("pernos",))
    lz.texto(cx, -D_F * 0.60, "Brida de carcasa (vista frontal)")

    # --- Derecha: canal tipo TEMA en corte ---------------------------------
    x0 = D_F * 0.18
    largo = D_s * 0.60
    lz.rect(x0, -D_o / 2.0, x0 + g["f_w"], D_o / 2.0, fill=ACERO,
            outline=AZUL, tags=("brida",))
    lz.rect(x0 + g["f_w"], -D_s / 2.0, x0 + largo, D_s / 2.0,
            fill="white", outline=AZUL, width=2, tags=("canal",))
    if cab_frontal == "B":
        lz.arco(x0 + largo, 0.0, D_s / 2.0, -90, 180, outline=AZUL, width=2,
                tags=("cubierta",))
    else:
        lz.rect(x0 + largo, -D_o / 2.0, x0 + largo + g["T_c"], D_o / 2.0,
                fill="#6f8296", outline=AZUL, tags=("cubierta",))
    if int(g["n_pasos"]) >= 2:
        lz.linea(x0 + g["f_w"], 0, x0 + largo, 0, fill="#b04a4a", width=3,
                 tags=("particion",))
        cotas["particion"] = (f"PLACA DE PARTICIÓN DEL CANAL\n"
                              f"  Divide el cabezal en {int(g['n_pasos'])} pasos.")
    lz.texto(x0 + largo / 2.0, -D_F * 0.60,
             f"Cabezal TEMA «{cab_frontal}» en corte")

    cotas["brida"] = (f"BRIDA DE CARCASA\n"
                      f"  Ancho radial f_w = {mm(g['f_w'])}\n"
                      f"  Ø exterior D_F = {mm(D_F)}\n"
                      f"  Ø círculo de pernos D_BC = {mm(D_BC)}")
    cotas["pernos"] = (f"PERNOS\n"
                       f"  Cantidad = {n_pernos}\n"
                       f"  Ø de perno = {mm(g['d_perno'])}  (mín. TEMA C: "
                       f"12.7 mm)\n"
                       f"  Ø círculo de pernos = {mm(D_BC)}")
    cotas["cubierta"] = (f"CUBIERTA DEL CABEZAL\n"
                         f"  Tipo: {g['tipo_cubierta']}\n"
                         f"  Espesor T_c = {mm(g['T_c'])}")
    cotas["canal"] = (f"CANAL (cabezal TEMA «{cab_frontal}»)\n"
                      f"  {g.get('desc_cab_frontal', '')}\n"
                      f"  Ø interior = {mm(D_s)}\n"
                      f"  Pasos por tubos = {int(g['n_pasos'])}")

    lz.cota_h(x0, x0 + largo + g["T_c"], -D_F * 0.52, "cabezal")
    lz.cota_v(-D_F / 2.0, D_F / 2.0, cx - D_F * 0.62, f"D_F = {mm(D_F)}")

    _titulo(canvas, "Vista 4 · Cabezal, brida y pernos",
            "Clic sobre la brida, los pernos o la cubierta para sus cotas.")
    return cotas


# =============================================================================
# 8. VISTA 5: CATALOGO TEMA (FIGURA N-1.2)
# =============================================================================
def _simbolo(lz: Lienzo, cx: float, cy: float, w: float, h: float,
             letra: str, seleccionado: bool, tags: Tuple[str, ...]) -> None:
    """Marco de celda del catalogo con la letra del tipo."""
    fondo = DESTACADO if seleccionado else "white"
    borde = BORDE_DESTACADO if seleccionado else "#9fb2c2"
    lz.rect(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2,
            fill=fondo, outline=borde, width=3 if seleccionado else 1,
            tags=tags)
    lz.texto(cx - w / 2 + 8, cy, letra, font=("Segoe UI", 10, "bold"),
             fill=BORDE_DESTACADO if seleccionado else AZUL, tags=tags)


def _mini_cabezal(lz: Lienzo, cx: float, cy: float, s: float, tipo: str,
                  tags) -> None:
    """Simbolo miniatura de un cabezal (frontal o trasero) estilo Fig. N-1.2."""
    if tipo == "U":
        for r in (0.35, 0.55, 0.75):
            lz.arco(cx + 0.1 * s, cy, r * s, -90, 180, outline=AZUL,
                    width=2, tags=tags)
        lz.rect(cx - 1.1 * s, cy - 0.85 * s, cx - 0.9 * s, cy + 0.85 * s,
                outline=AZUL, fill=ACERO_CLARO, tags=tags)
        return
    ancho = 1.5 * s
    x0 = cx - ancho / 2
    x1 = cx + ancho / 2
    if tipo in ("B", "M"):
        lz.rect(x0, cy - 0.75 * s, x1 - 0.45 * s, cy + 0.75 * s,
                outline=AZUL, fill=ACERO_CLARO, width=2, tags=tags)
        lz.arco(x1 - 0.45 * s, cy, 0.75 * s, -90, 180, outline=AZUL,
                width=2, tags=tags)
    elif tipo == "D":
        lz.rect(x0, cy - 0.85 * s, x1, cy + 0.85 * s, outline=AZUL,
                fill=ACERO, width=2, tags=tags)
        lz.rect(x0 + 0.45 * s, cy - 0.45 * s, x1, cy + 0.45 * s,
                outline=AZUL, fill="white", tags=tags)
    else:
        # canal con cubierta (A / C / N / L) o cabezales flotantes (P/S/T/W)
        lz.rect(x0 + 0.22 * s, cy - 0.75 * s, x1, cy + 0.75 * s,
                outline=AZUL, fill=ACERO_CLARO, width=2, tags=tags)
        lz.rect(x0, cy - 0.85 * s, x0 + 0.22 * s, cy + 0.85 * s,
                outline=AZUL, fill="#6f8296", width=2, tags=tags)
        if tipo in ("C", "N"):
            lz.rect(x1 - 0.18 * s, cy - 0.85 * s, x1, cy + 0.85 * s,
                    outline=AZUL, fill="#6f8296", tags=tags)
        if tipo in ("P", "S", "T", "W"):
            lz.rect(x1 - 0.55 * s, cy - 0.42 * s, x1, cy + 0.42 * s,
                    outline=AZUL, fill="#6f8296", tags=tags)
    # boquilla superior (comun a todos)
    lz.rect(cx - 0.12 * s, cy + 0.75 * s, cx + 0.12 * s, cy + 1.15 * s,
            outline=AZUL, fill=ACERO_CLARO, tags=tags)
    if tipo in ("A", "B", "C", "N", "D", "L", "M"):
        lz.linea(x0 + 0.22 * s, cy, x1, cy, fill="#b04a4a", dash=(3, 2),
                 tags=tags)


def _mini_coraza(lz: Lienzo, cx: float, cy: float, s: float, tipo: str,
                 tags) -> None:
    """Simbolo miniatura de una coraza estilo Fig. N-1.2."""
    w, h = 1.9 * s, 0.75 * s
    d_noz = 0.10 * s
    largo = 0.38 * s
    if tipo == "K":
        lz.rect(cx - w / 2, cy - h * 0.5, cx - w * 0.12, cy + h * 0.35,
                outline=AZUL, fill="white", width=2, tags=tags)
        lz.rect(cx - w * 0.12, cy - h, cx + w / 2, cy + h,
                outline=AZUL, fill="white", width=2, tags=tags)
        lz.arco(cx + w / 2, cy, h, -90, 90, outline=AZUL, width=2, tags=tags)
        lz.rect(cx + w * 0.15 - d_noz, cy + h, cx + w * 0.15 + d_noz,
                cy + h + largo, outline=AZUL, fill=ACERO_CLARO, tags=tags)
        lz.rect(cx + w * 0.30 - d_noz, cy - h - largo, cx + w * 0.30 + d_noz,
                cy - h, outline=AZUL, fill=ACERO_CLARO, tags=tags)
        return

    lz.rect(cx - w / 2, cy - h, cx + w / 2, cy + h, outline=AZUL,
            fill="white", width=2, tags=tags)
    for sx in (-1, 1):
        lz.rect(cx + sx * w / 2 - 0.06 * s, cy - h - 0.06 * s,
                cx + sx * w / 2 + 0.06 * s, cy + h + 0.06 * s,
                outline=AZUL, fill=ACERO, tags=tags)

    def _nz(x, arriba):
        y0 = cy + h if arriba else cy - h
        y1 = y0 + (largo if arriba else -largo)
        lz.rect(x - d_noz, min(y0, y1), x + d_noz, max(y0, y1),
                outline=AZUL, fill=ACERO_CLARO, tags=tags)

    if tipo == "E":        # boquillas en extremos opuestos
        _nz(cx - w * 0.30, True)
        _nz(cx + w * 0.30, False)
    elif tipo == "F":      # ambas en el mismo extremo + deflector longitudinal
        _nz(cx - w * 0.30, True)
        _nz(cx - w * 0.30, False)
        lz.linea(cx - w * 0.42, cy, cx + w * 0.35, cy, fill="#b04a4a",
                 dash=(4, 2), width=2, tags=tags)
    elif tipo == "G":      # centradas + deflector longitudinal
        _nz(cx, True)
        _nz(cx, False)
        lz.linea(cx - w * 0.38, cy, cx + w * 0.38, cy, fill="#b04a4a",
                 dash=(4, 2), width=2, tags=tags)
    elif tipo == "H":      # dos pares + dos tramos de deflector
        for fx in (-0.28, 0.28):
            _nz(cx + w * fx, True)
            _nz(cx + w * fx, False)
            lz.linea(cx + w * (fx - 0.10), cy, cx + w * (fx + 0.10), cy,
                     fill="#b04a4a", dash=(4, 2), width=2, tags=tags)
    elif tipo == "J":      # una entrada central, dos salidas
        _nz(cx, True)
        for fx in (-0.28, 0.28):
            _nz(cx + w * fx, False)
    else:                  # X: centradas, sin deflectores
        _nz(cx, True)
        _nz(cx, False)


def dibujar_catalogo_tema(canvas, g: Dict[str, object]) -> Dict[str, str]:
    """
    Reproduce la Figura N-1.2 del estandar TEMA: las tres columnas de tipos
    (cabezal frontal / coraza / cabezal trasero) con la seleccion actual
    resaltada.
    """
    canvas.delete("all")
    sel_front = str(g.get("cab_frontal", "A")).upper()
    sel_shell = str(g.get("tipo_carcasa", "E")).upper()
    sel_rear = str(g.get("cab_trasero", "M")).upper()

    W = canvas.winfo_width() or 760
    H = canvas.winfo_height() or 470
    cotas: Dict[str, str] = {}

    columnas = [
        ("FRONT END STATIONARY HEAD TYPES", ("A", "B", "C", "N", "D"),
         sel_front, "cab_frontal"),
        ("SHELL TYPES", ("E", "F", "G", "H", "J", "K", "X"),
         sel_shell, "tipo_carcasa"),
        ("REAR END HEAD TYPES", ("L", "M", "N", "P", "S", "T", "U", "W"),
         sel_rear, "cab_trasero"),
    ]
    etiquetas = {
        "A": "Channel and removable cover",
        "B": "Bonnet (integral cover)",
        "C": "Channel integral w/ tubesheet, removable cover (bundle out)",
        "D": "Special high pressure closure",
        "N": "Channel integral w/ tubesheet and removable cover",
        "E": "One pass shell",
        "F": "Two pass shell with longitudinal baffle",
        "G": "Split flow",
        "H": "Double split flow",
        "J": "Divided flow",
        "K": "Kettle type",
        "X": "Cross flow",
        "L": "Fixed tubesheet like «A» stationary head",
        "M": "Fixed tubesheet like «B» stationary head",
        "P": "Outside packed floating head",
        "S": "Floating head with backing device",
        "T": "Pull through floating head",
        "U": "U-tube bundle",
        "W": "Externally sealed floating tubesheet",
    }
    descripciones = {
        "cab_frontal": DESCRIPCIONES.get("cab_frontal", {}),
        "tipo_carcasa": DESCRIPCIONES.get("tipo_carcasa", {}),
        "cab_trasero": DESCRIPCIONES.get("cab_trasero", {}),
    }

    col_w = W / 3.0
    pz = LienzoPixeles(canvas)
    y_top = 78.0                      # deja libre el titulo de la vista
    for ci, (titulo, tipos, sel, clave) in enumerate(columnas):
        cx_col = ci * col_w + col_w / 2.0
        canvas.create_text(cx_col, y_top - 26, text=titulo, fill=AZUL,
                           font=("Segoe UI", 9, "bold"))
        canvas.create_text(cx_col, y_top - 11,
                           text=f"seleccionado: {sel}",
                           fill=BORDE_DESTACADO, font=("Segoe UI", 8, "bold"))
        n = len(tipos)
        celda_h = (H - y_top - 6) / n
        for i, t in enumerate(tipos):
            cy = y_top + celda_h * (i + 0.5)
            w = min(col_w * 0.66, 165)
            h = celda_h * 0.86
            tags = (f"cat_{clave}_{t}",)
            _simbolo(pz, cx_col, cy, w, h, t, t == sel, tags)
            s = min(w * 0.26, h * 0.26)
            if clave == "tipo_carcasa":
                _mini_coraza(pz, cx_col + w * 0.14, cy - h * 0.10, s, t, tags)
            else:
                _mini_cabezal(pz, cx_col + w * 0.14, cy - h * 0.10, s, t, tags)
            canvas.create_text(cx_col, cy + h / 2 - 10,
                               text=etiquetas.get(t, t), fill="#5a6b7b",
                               font=("Segoe UI", 6), width=w + 30,
                               anchor="center")
            cotas[f"cat_{clave}_{t}"] = (
                f"TIPO TEMA «{t}» — {titulo.title()}\n"
                f"  {etiquetas.get(t, '')}\n"
                f"  {descripciones.get(clave, {}).get(t, '')}\n"
                + ("  ✔ ES LA SELECCIÓN ACTUAL" if t == sel else
                   "  (para elegirlo: menú desplegable de la pestaña Design)")
            )

    _titulo(canvas, "Vista 5 · Catálogo de tipos TEMA (Fig. N-1.2)",
            "Diagramas del estándar TEMA; el tipo activo aparece resaltado en "
            "amarillo. Clic sobre un diagrama para su descripción.")
    return cotas


class LienzoPixeles(Lienzo):
    """Lienzo identidad (1 unidad = 1 px): primitivas en pixeles del canvas."""

    def __init__(self, canvas) -> None:
        self.c = canvas
        self.s = 1.0
        self.W = canvas.winfo_width() or 760
        self.H = canvas.winfo_height() or 470
        self.cx = self.cy = 0.0

    def p(self, x: float, y: float) -> Tuple[float, float]:
        return (x, y)


# Descripciones por tipo (para los pop-ups del catalogo).
DESCRIPCIONES = {
    "cab_frontal": {
        "A": "Canal con cubierta desmontable: permite abrir el lado de tubos "
             "para limpiar sin mover el haz.",
        "B": "Bonete integral: económico y robusto, pero impide limpiar el "
             "interior de los tubos por ese extremo.",
        "C": "Canal integral con el espejo y cubierta desmontable: el haz se "
             "extrae por un extremo (típico con cabezal flotante).",
        "D": "Cierre especial de alta presión: para servicios muy exigentes; "
             "su diseño requiere análisis específico (ASME VIII Div. 2).",
        "N": "Canal integral con el espejo y cubierta desmontable: espejo "
             "fijo, sin extracción del haz.",
    },
    "tipo_carcasa": {
        "E": "Una pasada por la coraza: el estándar, con baffles segmentados.",
        "F": "Dos pasadas con deflector longitudinal: duplica la velocidad de "
             "coraza, Δp mucho mayor.",
        "G": "Flujo partido: entrada central que se divide en dos corrientes.",
        "H": "Flujo doble partido: cuatro boquillas, Δp mínima.",
        "J": "Flujo dividido: una entrada central y dos salidas.",
        "K": "Caldera: haz en un cuerpo ampliado (ebullición de un servicio "
             "de recalentamiento).",
        "X": "Flujo cruzado puro: solo placas soporte, sin baffles.",
    },
    "cab_trasero": {
        "L": "Espejo fijo con canal tipo «A».",
        "M": "Espejo fijo con bonete tipo «B».",
        "N": "Espejo fijo tipo «N» (canal integral con el espejo).",
        "P": "Cabezal flotante con prensaestopas exterior: absorbe la "
             "dilatación térmica del haz.",
        "S": "Cabezal flotante con anillo de retención (backing device).",
        "T": "Cabezal flotante de paso por la coraza: el haz se extrae "
             "entero para limpieza.",
        "U": "Haz en U: los tubos se curvan en el extremo trasero; sin "
             "espejo trasero ni cabezal.",
        "W": "Espejo flotante sellado exteriormente con anillo linterna.",
    },
}


VISTAS = {
    "1 · Carcasa (corte longitudinal)": dibujar_carcasa,
    "2 · Distribución de tubos": dibujar_layout,
    "3 · Placa deflectora (baffle)": dibujar_baffle,
    "4 · Cabezal y brida": dibujar_cabezal,
    "5 · Catálogo TEMA (Fig. N-1.2)": dibujar_catalogo_tema,
}
