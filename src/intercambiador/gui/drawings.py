# -*- coding: utf-8 -*-
"""
drawings.py - Vistas esquematicas 2D parametricas (Canvas de Tkinter).

Todo lo que se dibuja proviene de las cotas calculadas en
intercambiador.mechanical y intercambiador.thermo: no hay imagenes estaticas
ni dimensiones inventadas. Cada funcion
devuelve un diccionario {tag: texto_de_cota} para que la aplicacion muestre
pop-ups interactivos al hacer clic sobre una pieza.
"""
from __future__ import annotations

import math
from typing import Dict, List, Tuple

AZUL = "#1f3b57"
ACERO = "#8fa6bb"
ACERO_CLARO = "#d7e1ea"
COBRE = "#c08457"
FLUIDO = "#2f7fb5"
COTA = "#a33"
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
    canvas.create_text(14, 14, text=texto, anchor="nw", fill=AZUL,
                       font=("Segoe UI", 11, "bold"))
    if subtitulo:
        canvas.create_text(14, 34, text=subtitulo, anchor="nw",
                           fill="#5a6b7b", font=("Segoe UI", 8))


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


# =============================================================================
# 3. VISTA 1: CARCASA (ELEVACION LONGITUDINAL)
# =============================================================================
def dibujar_carcasa(canvas, g: Dict[str, float]) -> Dict[str, str]:
    """Corte longitudinal: carcasa, espejos, baffles, tubos y boquillas."""
    canvas.delete("all")
    if not g:
        return _sin_datos(canvas, "Ejecute primero un cálculo en la pestaña "
                                  "Design para generar el dibujo.")

    D_s, D_o = g["D_s"], g["D_o"]
    L, L_ts = g["L"], g["L_ts"]
    L_tot = g["L_total"]
    lz = Lienzo(canvas, L_tot * 1.35, max(D_o * 3.4, 0.25))
    cotas: Dict[str, str] = {}

    x0, x1 = -L / 2.0, L / 2.0
    e = (D_o - D_s) / 2.0        # espesor de carcasa

    # --- cuerpo de carcasa (dos franjas de pared) ---------------------------
    for signo in (1, -1):
        lz.rect(x0, signo * D_s / 2.0, x1, signo * D_o / 2.0,
                fill=ACERO, outline=AZUL, width=1, tags=("carcasa",))
    lz.linea(x0, D_s / 2.0, x1, D_s / 2.0, fill=AZUL, dash=(2, 2))
    lz.linea(x0, -D_s / 2.0, x1, -D_s / 2.0, fill=AZUL, dash=(2, 2))
    cotas["carcasa"] = (
        f"CARCASA TEMA tipo {g['tipo_carcasa']}\n"
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
                       f"  Espesor L_ts = {mm(L_ts)}\n"
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

    # --- baffles ------------------------------------------------------------
    N_B, L_bc = int(g["N_B"]), g["L_bc"]
    h_baffle = D_s * (1.0 - g["corte"])
    for i in range(N_B):
        x = x0 + g["L_bi"] + i * L_bc
        if x >= x1:
            break
        arriba = (i % 2 == 0)
        y_a = D_s / 2.0 if arriba else -D_s / 2.0
        y_b = y_a - h_baffle if arriba else y_a + h_baffle
        lz.rect(x - g["e_baffle"] / 2.0, y_a, x + g["e_baffle"] / 2.0, y_b,
                fill="#44607a", outline=AZUL, tags=("baffles",))
    cotas["baffles"] = (f"PLACAS DEFLECTORAS (segmentadas)\n"
                        f"  Cantidad N_B = {N_B}\n"
                        f"  Espaciado central L_bc = {mm(L_bc)}\n"
                        f"  Espaciado entrada/salida L_bi = {mm(g['L_bi'])}\n"
                        f"  Corte = {g['corte']*100:.0f} %  "
                        f"(altura {mm(g['altura_corte'])})\n"
                        f"  Espesor de placa = {mm(g['e_baffle'])}")

    # --- boquillas ----------------------------------------------------------
    def _boquilla(x, signo, clave, titulo, info):
        if not info:
            return
        d = info["D_i"]
        y0 = signo * D_o / 2.0
        y1 = y0 + signo * D_o * 0.42
        lz.rect(x - d / 2.0, y0, x + d / 2.0, y1,
                fill=ACERO_CLARO, outline=AZUL, tags=(clave,))
        lz.rect(x - d * 0.8, y1, x + d * 0.8, y1 + signo * D_o * 0.05,
                fill=ACERO, outline=AZUL, tags=(clave,))
        lz.texto(x, y1 + signo * D_o * 0.22, titulo, fill=FLUIDO)
        cotas[clave] = (
            f"{titulo}\n"
            f"  Tubería comercial: {info['nps']}\n"
            f"  Ø interior = {mm(info['D_i'])}   Ø exterior = {mm(info['D_e'])}\n"
            f"  Espesor = {mm(info['espesor'])}\n"
            f"  Velocidad real = {info['V_real']:.2f} m/s "
            f"(máx. admisible {info['V_max']:.2f} m/s)")

    _boquilla(x0 + L * 0.12, +1, "boq_s_in", "Entrada coraza", g.get("boq_s"))
    _boquilla(x1 - L * 0.12, -1, "boq_s_out", "Salida coraza", g.get("boq_s"))

    # --- cabezales ----------------------------------------------------------
    largo_cab = (L_tot - L - 2 * L_ts) / 2.0
    for signo, clave, nombre in ((-1, "cab_front", g["cab_frontal"]),
                                 (1, "cab_tras", g["cab_trasero"])):
        xa = signo * (L / 2.0 + L_ts)
        xb = xa + signo * max(largo_cab, D_s * 0.25)
        lz.rect(min(xa, xb), -D_o / 2.0, max(xa, xb), D_o / 2.0,
                fill=ACERO_CLARO, outline=AZUL, width=2, tags=(clave,))
        lz.texto((xa + xb) / 2.0, 0.0, nombre, font=("Segoe UI", 11, "bold"))
    cotas["cab_front"] = (f"CABEZAL FRONTAL TEMA «{g['cab_frontal']}»\n"
                          f"  Espesor de cubierta T_c = {mm(g['T_c'])}\n"
                          f"  Tipo de cubierta: {g['tipo_cubierta']}\n"
                          f"  Reparte el flujo en {g['n_pasos']} paso(s).")
    cotas["cab_tras"] = (f"CABEZAL TRASERO TEMA «{g['cab_trasero']}»\n"
                         f"  Espesor de cubierta T_c = {mm(g['T_c'])}\n"
                         f"  Ø interior de carcasa = {mm(D_s)}")

    # --- acotaciones --------------------------------------------------------
    lz.cota_h(-L_tot / 2.0, L_tot / 2.0, -D_o * 1.25, f"L total = {L_tot:.3f} m")
    lz.cota_h(x0, x1, -D_o * 0.85, f"L tubos = {L:.3f} m")
    lz.cota_v(-D_o / 2.0, D_o / 2.0, -L_tot / 2.0 - D_s * 0.22, mm(D_o))

    _titulo(canvas, "Vista 1 · Carcasa — corte longitudinal",
            "Haga clic sobre cualquier pieza para ver sus cotas exactas.")
    return cotas


# =============================================================================
# 4. VISTA 2: DISTRIBUCION DE TUBOS (SECCION TRANSVERSAL)
# =============================================================================
def dibujar_layout(canvas, g: Dict[str, float]) -> Dict[str, str]:
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
    for (x, y) in puntos:
        lz.circulo(x, y, r, outline=AZUL, fill=COBRE, tags=("tubos",))
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
# 5. VISTA 3: PLACA DEFLECTORA (BAFFLE)
# =============================================================================
def dibujar_baffle(canvas, g: Dict[str, float]) -> Dict[str, str]:
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

    # Segmento cortado (zona de paso del fluido): se raya en diagonal.
    a, b = lz.p(-D_b / 2.0, D_b / 2.0)
    c, d = lz.p(D_b / 2.0, y_corte)
    canvas.create_rectangle(a, b, c, d, outline="", fill="white",
                            tags=("corte",))
    lz.circulo(0, 0, D_b / 2.0, outline=AZUL, width=2, tags=("placa",))
    lz.linea(-D_b / 2.0, y_corte, D_b / 2.0, y_corte, fill="#b04a4a",
             width=2, tags=("corte",))

    # Perforaciones para los tubos.
    n_dib = min(int(g["N_tt"]), MAX_TUBOS_DIBUJADOS)
    r = (g["d_o"] + g["luz_tubo"]) / 2.0 if "luz_tubo" in g else g["d_o"] / 2.0
    for (x, y) in posiciones_tubos(g["P_T"], g["D_ctl"], int(g["layout"]), n_dib):
        if y <= y_corte:
            lz.circulo(x, y, r, outline="#6f8296", fill="white",
                       tags=("perforacion",))

    cotas["placa"] = (f"PLACA DEFLECTORA SEGMENTADA\n"
                      f"  Ø de placa = {mm(D_b)}\n"
                      f"  Espesor = {mm(g['e_baffle'])}\n"
                      f"  Claro placa–carcasa = {mm((g['D_s'] - D_b) / 2.0)}\n"
                      f"  Cantidad instalada = {int(g['N_B'])}")
    cotas["corte"] = (f"CORTE DEL BAFFLE\n"
                      f"  Fracción de corte = {g['corte']*100:.0f} % de D_s\n"
                      f"  Altura del segmento = {mm(g['altura_corte'])}\n"
                      "  Es la ventana por donde el fluido de coraza "
                      "cruza de un compartimento al siguiente.")
    cotas["perforacion"] = (f"PERFORACIONES\n"
                            f"  Ø nominal del tubo = {mm(g['d_o'])}\n"
                            f"  Tramo máximo sin soporte = "
                            f"{g['luz_sin_soporte']:.3f} m")

    lz.cota_h(-D_b / 2.0, D_b / 2.0, -D_b * 0.62, f"Ø = {mm(D_b)}")
    lz.cota_v(y_corte, D_b / 2.0, D_b * 0.62, mm(g["altura_corte"]))

    _titulo(canvas, "Vista 3 · Placa deflectora (baffle segmentado)",
            "La zona blanca superior es el corte; abajo, las perforaciones.")
    return cotas


# =============================================================================
# 6. VISTA 4: CABEZAL Y BRIDA
# =============================================================================
def dibujar_cabezal(canvas, g: Dict[str, float]) -> Dict[str, str]:
    canvas.delete("all")
    if not g:
        return _sin_datos(canvas, "Ejecute primero un cálculo en la pestaña "
                                  "Design para generar el dibujo.")

    D_F, D_BC, D_o, D_s = g["D_F"], g["D_BC"], g["D_o"], g["D_s"]
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

    # --- Derecha: cabezal en corte -----------------------------------------
    x0 = D_F * 0.18
    largo = D_s * 0.60
    lz.rect(x0, -D_o / 2.0, x0 + g["f_w"], D_o / 2.0, fill=ACERO,
            outline=AZUL, tags=("brida",))
    lz.rect(x0 + g["f_w"], -D_s / 2.0, x0 + largo, D_s / 2.0,
            fill="white", outline=AZUL, width=2, tags=("canal",))
    lz.rect(x0 + largo, -D_o / 2.0, x0 + largo + g["T_c"], D_o / 2.0,
            fill="#6f8296", outline=AZUL, tags=("cubierta",))
    if int(g["n_pasos"]) >= 2:
        lz.linea(x0 + g["f_w"], 0, x0 + largo, 0, fill="#b04a4a", width=3,
                 tags=("particion",))
        cotas["particion"] = (f"PLACA DE PARTICIÓN DEL CANAL\n"
                              f"  Divide el cabezal en {int(g['n_pasos'])} pasos.")
    lz.texto(x0 + largo / 2.0, -D_F * 0.60, "Cabezal en corte")

    cotas["brida"] = (f"BRIDA DE CARCASA\n"
                      f"  Ancho radial f_w = {mm(g['f_w'])}\n"
                      f"  Ø exterior D_F = {mm(D_F)}\n"
                      f"  Ø círculo de pernos D_BC = {mm(D_BC)}")
    cotas["pernos"] = (f"PERNOS\n"
                       f"  Cantidad = {n_pernos}\n"
                       f"  Ø de perno = {mm(g['d_perno'])}\n"
                       f"  Ø círculo de pernos = {mm(D_BC)}")
    cotas["cubierta"] = (f"CUBIERTA DEL CABEZAL\n"
                         f"  Tipo: {g['tipo_cubierta']}\n"
                         f"  Espesor T_c = {mm(g['T_c'])}")
    cotas["canal"] = (f"CANAL (cabezal TEMA «{g['cab_frontal']}»)\n"
                      f"  Ø interior = {mm(D_s)}\n"
                      f"  Pasos por tubos = {int(g['n_pasos'])}")

    lz.cota_h(x0, x0 + largo + g["T_c"], -D_F * 0.52, "cabezal")
    lz.cota_v(-D_F / 2.0, D_F / 2.0, cx - D_F * 0.62, f"D_F = {mm(D_F)}")

    _titulo(canvas, "Vista 4 · Cabezal, brida y pernos",
            "Clic sobre la brida, los pernos o la cubierta para sus cotas.")
    return cotas


VISTAS = {
    "1 · Carcasa (corte longitudinal)": dibujar_carcasa,
    "2 · Distribución de tubos": dibujar_layout,
    "3 · Placa deflectora (baffle)": dibujar_baffle,
    "4 · Cabezal y brida": dibujar_cabezal,
}
