# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
"""
app.py - Ventana principal del software educativo de intercambiadores
         de tubos y coraza (Método de Kern / estándar TEMA Clase C).

Arquitectura MVC estricta:
    VISTA        -> este archivo + widgets.py + drawings.py
    CONTROLADOR  -> controller.py
    MODELO       -> src/core, src/thermo, src/mechanical

Esta capa NO calcula física: captura datos, delega y renderiza. Todo
`ValueError` que suba desde el modelo se atrapa y se convierte en un pop-up
educativo, sin cerrar la aplicación.

Ejecución:  python src/gui/app.py      (desde la raíz del proyecto)
"""
from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional

if __package__ in (None, ""):                 # ejecución directa del archivo
    sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")))

from src.gui import controller as ctrl
from src.gui import drawings, io_state
from src.core.errores import ErrorDiseno
from src.core import marca
import customtkinter as ctk

from src.gui.widgets import (COLOR_ACENTO, COLOR_BORDE, COLOR_CARMESI,
                             COLOR_CARMESI_CLARO, COLOR_FONDO, COLOR_NARANJA,
                             COLOR_NOTA,
                             COLOR_SECCION, COLOR_TITULO, CampoInvalido,
                             CampoLista, CampoNumerico, Formulario, MarcoScroll,
                             Tooltip, bloque, boton, llenar_tabla, rotulo,
                             tabla_resultados)

TITULO = "Intercambiador de Tubos y Coraza · Método de Kern / TEMA"
if getattr(sys, "frozen", False):          # empaquetado con PyInstaller
    RAIZ = sys._MEIPASS                    # los datos viajan dentro del .exe
else:
    RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DIR_EJEMPLOS = os.path.join(RAIZ, "ejemplos")

# Caso base de arranque: agua-agua, tubos de cobre 3/4 in BWG 16, pitch 1 in
# triangular. Converge sin advertencias y supera el chequeo de empaquetamiento
# del modulo mecanico, de modo que el usuario vea un diseno completo al abrir.
VALORES_DEFECTO: Dict[str, Any] = {
    "fluido_cal": "Agua", "m_cal": 40.0, "tin_cal": 80.0, "tout_cal": 50.0,
    "fluido_fri": "Agua", "m_fri": 80.0, "tin_fri": 20.0, "tout_fri": "",
    "lado_tubos": "frio",
    "d_o_mm": 19.05, "esp_mm": 1.65, "pitch_mm": 25.4, "long_m": 3.66,
    "layout": "Triangular 30°", "n_pasos": "2", "mat_tubo": "Cobre",
    "tipo_carcasa": "E", "baffle_mm": 305.0, "corte_pct": 25.0,
    "u_inicial": 700.0,
    "dp_t_max": "", "dp_s_max": "",
    "cab_frontal": "A", "cab_trasero": "M",
    "p_coraza_bar": 10.0, "p_tubos_bar": 10.0,
    "mat_carcasa": "Acero al carbono", "corrosion_mm": 3.2, "d_perno_mm": 19.05,
    "n_tt": 500, "d_s_mm": 630.0,
    "metodo_coraza": "Automático (recomendado)",
}

# Ayudas del modo de trabajo (paso 1 de la hoja de diseño).
AYUDAS_MODO = {
    "sizing": (
        "Modo SIZING — el programa propone la geometría (n.º de tubos, coraza "
        "y área). Necesita: corrientes con temperaturas de entrada y UNA «T "
        "salida» (deje vacía la incógnita del balance q = ṁ·cp·ΔT), la "
        "geometría de tubo deseada, baffles, configuración TEMA, condiciones "
        "mecánicas, la semilla de U y las caídas de presión máximas "
        "permisibles."),
    "rating": (
        "Modo RATING — evalúa un equipo YA CONSTRUIDO. Necesita: corrientes "
        "con las DOS «T salida» vacías (el programa las calcula), la "
        "geometría existente (N.º de tubos y Ø interior de coraza) y el resto "
        "de datos geométricos, TEMA y mecánicos."),
    "avanzado": (
        "Modo AVANZADO («otras») — formulario completo con todos los campos, "
        "igual que la hoja original: útil para controlar sizing y rating a la "
        "vez o para trabajar con proyectos mixtos."),
}


class Aplicacion(ctk.CTk):
    # ------------------------------------------------------------------ init
    def __init__(self) -> None:
        super().__init__()
        self.title(TITULO)
        # Icono de la aplicacion (ventana y barra de tareas). En el .exe
        # empaquetado viaja junto al programa dentro del bundle.
        try:
            self.iconbitmap(os.path.join(RAIZ, "MIQUITO.ico"))
        except tk.TclError:
            pass
        self.geometry("1180x780")
        self.minsize(1020, 660)
        self.configure(bg=COLOR_FONDO)

        self.form = Formulario()
        self.res_termico = None        # SizingResult | RatingResult
        self.res_mecanico = None       # MechanicalResult
        self.modo: str = ""            # 'sizing' | 'rating'
        self.ruta_actual: Optional[str] = None
        self.cotas: Dict[str, str] = {}
        self.ultimo_D_s: Optional[float] = None   # para el botón «½·D_s»

        # --- estado de fluidez de la interfaz -----------------------------
        self._trabajo: Optional[threading.Thread] = None   # cálculo en curso
        self._botones_calculo = []                         # botones F5/F6
        self._job_redibujo: Optional[str] = None           # debounce del canvas
        self._ultimo_tamano = (0, 0)                       # último tamaño pintado
        self._ultimo_chequeo_cursor = 0.0                  # throttle del hover
        self._cursor_canvas = ""

        self._estilo()
        self._crear_menu()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._tab_design()
        self._tab_analysis()
        self._tab_drawing()
        self._tab_help()

        self.estado = tk.StringVar(value="Listo. Elija el modo de trabajo "
                                         "arriba y complete los datos.")
        rotulo(self, textvariable=self.estado, style="Estado.TLabel",
                  anchor="w").pack(fill="x", padx=8, pady=(0, 8))

        self._restaurar_defecto()
        self.protocol("WM_DELETE_WINDOW", self._salir)

        if not ctrl.MODULOS_OK:
            self.after(300, lambda: messagebox.showerror(
                "Módulos de cálculo no disponibles",
                "La interfaz se abrió, pero no pudo importar los módulos de "
                "cálculo:\n\n" + ctrl.ERROR_IMPORT))

    def _estilo(self) -> None:
        ctk.set_appearance_mode("light")
        estilo = ttk.Style(self)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure(".", background=COLOR_FONDO, font=("Segoe UI", 12))
        estilo.configure("TNotebook.Tab", padding=(16, 7),
                         font=("Segoe UI", 12, "bold"),
                         background="#e4daf2", foreground=COLOR_TITULO)
        estilo.map("TNotebook.Tab",
                   background=[("selected", COLOR_ACENTO)],
                   foreground=[("selected", "white")])
        estilo.configure("TLabelframe", background=COLOR_FONDO, borderwidth=1)
        estilo.configure("TLabelframe.Label", foreground=COLOR_TITULO,
                         font=("Segoe UI", 12, "bold"))
        estilo.configure("TFrame", background=COLOR_FONDO)
        estilo.configure("TLabel", background=COLOR_FONDO)
        estilo.configure("Accion.TButton", font=("Segoe UI", 12, "bold"),
                         padding=(12, 7), background=COLOR_ACENTO,
                         foreground="white", borderwidth=0)
        estilo.map("Accion.TButton",
                   background=[("active", "#9575cd"),
                               ("disabled", "#cbb8e8")],
                   foreground=[("disabled", "#7a6a95")])
        estilo.configure("TButton", padding=(8, 5), background="#e4daf2")
        estilo.map("TButton", background=[("active", "#d7c7ee")])
        estilo.configure("Treeview", rowheight=21, fieldbackground="white")
        estilo.configure("Treeview.Heading", font=("Segoe UI", 12, "bold"),
                         background=COLOR_ACENTO, foreground="white")
        estilo.configure("Titulo.TLabel", foreground=COLOR_TITULO,
                         font=("Segoe UI", 16, "bold"))
        estilo.configure("Subtitulo.TLabel", foreground=COLOR_NOTA,
                         font=("Segoe UI", 12))
        estilo.configure("Nota.TLabel", foreground=COLOR_NOTA,
                         font=("Segoe UI", 11))
        estilo.configure("Designacion.TLabel", foreground=COLOR_ACENTO,
                         font=("Segoe UI", 12, "bold"))
        # Tarjetas y banner del encabezado.
        estilo.configure("Banner.TLabel", background=COLOR_TITULO,
                         foreground="white", font=("Segoe UI", 14, "bold"))
        estilo.configure("BannerNota.TLabel", background=COLOR_TITULO,
                         foreground="#d9c9f2", font=("Segoe UI", 12))
        # Botones de acción con hover.
        estilo.configure("Accion2.TButton", font=("Segoe UI", 12, "bold"),
                         padding=(12, 7), background="white",
                         foreground=COLOR_TITULO, borderwidth=1)
        estilo.map("Accion2.TButton",
                   background=[("active", "#ede7f6")],
                   foreground=[("active", COLOR_TITULO)])
        estilo.configure("Suave.TButton", font=("Segoe UI", 12),
                         padding=(10, 6), background="#e4daf2")
        estilo.map("Suave.TButton", background=[("active", "#d7c7ee")])
        estilo.configure("Estado.TLabel", background="#ede7f6",
                         foreground=COLOR_TITULO, font=("Segoe UI", 12, "bold"),
                         relief="sunken", padding=(8, 4))
        estilo.configure("TNotebook", borderwidth=0)

    # ------------------------------------------------------------------ menú
    def _crear_menu(self) -> None:
        barra = tk.Menu(self)

        m_file = tk.Menu(barra, tearoff=0)
        m_file.add_command(label="Nuevo", accelerator="Ctrl+N",
                           command=self._nuevo)
        m_file.add_command(label="Abrir…", accelerator="Ctrl+O",
                           command=self._abrir)
        m_file.add_cascade(label="Abrir ejemplo validado",
                           menu=self._menu_ejemplos(m_file))
        m_file.add_command(label="Guardar", accelerator="Ctrl+S",
                           command=self._guardar)
        m_file.add_command(label="Guardar como…", command=self._guardar_como)
        m_file.add_separator()
        m_file.add_command(label="Salir", command=self._salir)
        barra.add_cascade(label="File", menu=m_file)

        m_design = tk.Menu(barra, tearoff=0)
        m_design.add_command(label="Ir a la hoja de diseño",
                             command=lambda: self.nb.select(0))
        m_design.add_separator()
        m_design.add_command(label="Restaurar caso base",
                             command=self._restaurar_defecto)
        barra.add_cascade(label="Design", menu=m_design)

        m_an = tk.Menu(barra, tearoff=0)
        m_an.add_command(label="Dimensionar (Sizing)  ·  F5",
                         command=lambda: self._calcular_async("sizing"))
        m_an.add_command(label="Evaluar equipo (Rating)  ·  F6",
                         command=lambda: self._calcular_async("rating"))
        m_an.add_separator()
        m_an.add_command(label="Ir a resultados",
                         command=lambda: self.nb.select(1))
        barra.add_cascade(label="Analysis", menu=m_an)

        m_dib = tk.Menu(barra, tearoff=0)
        for nombre in drawings.VISTAS:
            m_dib.add_command(label=nombre,
                              command=lambda n=nombre: self._ir_a_vista(n))
        barra.add_cascade(label="Drawing", menu=m_dib)

        m_help = tk.Menu(barra, tearoff=0)
        m_help.add_command(label="Tutorial de uso",
                           command=lambda: self.nb.select(3))
        m_help.add_command(label="Acerca de…", command=self._acerca_de)
        barra.add_cascade(label="Help", menu=m_help)

        self.config(menu=barra)
        self.bind("<Control-n>", lambda e: self._nuevo())
        self.bind("<Control-o>", lambda e: self._abrir())
        self.bind("<Control-s>", lambda e: self._guardar())
        self.bind("<F5>", lambda e: self._tecla_calcular("sizing"))
        self.bind("<F6>", lambda e: self._tecla_calcular("rating"))

    def _menu_ejemplos(self, padre) -> tk.Menu:
        """Submenú con los proyectos .bb verificados: sizing y rating."""
        menu = tk.Menu(padre, tearoff=0)
        encontrados = False
        for carpeta, etiqueta in (("sizing", "Sizing (dimensionar)"),
                                  ("rating", "Rating (evaluar)")):
            ruta_grupo = os.path.join(DIR_EJEMPLOS, carpeta)
            try:
                archivos = sorted(a for a in os.listdir(ruta_grupo)
                                  if a.endswith(io_state.EXTENSION))
            except OSError:
                archivos = []
            if not archivos:
                continue
            encontrados = True
            sub = tk.Menu(menu, tearoff=0)
            for archivo in archivos:
                ruta = os.path.join(ruta_grupo, archivo)
                texto = io_state.descripcion_de(ruta) or archivo
                sub.add_command(label=texto,
                                command=lambda r=ruta: self._cargar_ejemplo(r))
            menu.add_cascade(label=etiqueta, menu=sub)
        if not encontrados:
            menu.add_command(label="(no se encontró la carpeta «ejemplos»)",
                             state="disabled")
        return menu

    def _cargar_ejemplo(self, ruta: str) -> None:
        """Carga un ejemplo, elige su modo (sizing/rating) y lo calcula."""
        resultado = {"modo": "sizing", "ok": False}

        def accion():
            datos = io_state.abrir(ruta)
            self.form.cargar(datos)
            resultado["modo"] = ctrl.modo_calculo(datos)
            resultado["ok"] = True
            self.ruta_actual = None        # evita sobrescribir el ejemplo
            self._cambiar_modo(resultado["modo"])
            self._actualizar_limites()
            self._actualizar_designacion_tema()
            self.title(f"{TITULO}  —  {os.path.basename(ruta)}")
        self._blindar(accion, "Apertura del ejemplo")
        if not resultado["ok"]:
            return
        if resultado["modo"] == "rating":
            self._calcular_rating()
        else:
            self._calcular_sizing()

    # =================================================================== tabs
    def _tab_design(self) -> None:
        contenedor = MarcoScroll(self.nb)
        self.nb.add(contenedor, text="  Design  ")
        raiz = contenedor.interior
        raiz.columnconfigure(0, weight=1, uniform="col")
        raiz.columnconfigure(1, weight=1, uniform="col")

        banner = ctk.CTkFrame(raiz, fg_color=COLOR_TITULO, corner_radius=16)
        banner.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6,
                    pady=(8, 0))
        rotulo(banner, text="Hoja de diseño térmico y mecánico",
               style="Banner.TLabel").pack(anchor="w", padx=18, pady=(14, 0))
        rotulo(banner,
               text="Método de Kern o Bell-Delaware   ·   TEMA Clase C   "
                    "·   Unidades SI",
               style="BannerNota.TLabel").pack(anchor="w", padx=18,
                                               pady=(2, 12))
        # Barra de acento bicolor: carmesí + naranja.
        acento = ctk.CTkFrame(banner, fg_color="transparent", height=6)
        acento.pack(fill="x", side="bottom")
        ctk.CTkFrame(acento, fg_color=COLOR_CARMESI, height=6,
                     corner_radius=0).pack(side="left", fill="x", expand=True)
        ctk.CTkFrame(acento, fg_color=COLOR_NARANJA, height=6,
                     corner_radius=0).pack(side="left", fill="x", expand=True)

        # --- Paso 1: la interfaz pregunta primero el modo de trabajo -------
        self._bloque_modo(raiz, fila=1)

        self._bloque_corrientes(raiz, fila=2)      # 1 · 2
        self._bloque_tubos(raiz, fila=3)           # 3  (columna 0)
        self._bloque_coraza(raiz, fila=3)          # 4  (columna 1)
        self._bloque_tema(raiz, fila=4)            # 5  (columna 0)
        self._bloque_mecanico(raiz, fila=4)        # 6  (columna 1)
        self._bloque_sizing(raiz, fila=5)          # A  (columna 0)
        self._bloque_rating(raiz, fila=5)          # B  (columna 1)
        self._bloque_botones(raiz, fila=6)
        self._cambiar_modo()                       # aplica el modo inicial

    # ------------------------------------------------------- modo de trabajo
    def _bloque_modo(self, padre, fila: int) -> None:
        """Paso 1: el usuario elige Sizing, Rating u Otras (formulario completo)."""
        marco = bloque(
            padre, text="1 · ¿Qué desea hacer?", padding=(10, 8))
        marco.grid(row=fila, column=0, columnspan=2, sticky="ew", padx=6,
                   pady=(2, 4))
        for c in range(3):
            marco.columnconfigure(c, weight=1)

        self.modo_var = tk.StringVar(value="sizing")
        self._tarjetas_modo: Dict[str, tuple] = {}
        tarjetas = (
            ("sizing", "DIMENSIONAR",
             "un equipo nuevo  ·  Sizing",
             "El programa propone la geometría: n.º de tubos, coraza y área."),
            ("rating", "EVALUAR",
             "un equipo existente  ·  Rating",
             "El programa calcula las temperaturas de salida del equipo."),
            ("avanzado", "OTRAS",
             "formulario completo  ·  avanzado",
             "Todos los campos a la vez, como en el menú clásico."),
        )
        for i, (valor, titulo, sub, nota) in enumerate(tarjetas):
            tarjeta = ctk.CTkFrame(marco, fg_color="white", corner_radius=14,
                                   border_width=2, border_color=COLOR_BORDE,
                                   cursor="hand2")
            tarjeta.grid(row=0, column=i, sticky="nsew", padx=5, pady=4)
            lineas = []
            for texto, fuente, color in (
                    (titulo, ("Segoe UI", 14, "bold"),
                     COLOR_TITULO),
                    (sub, ("Segoe UI", 12, "bold"), COLOR_CARMESI),
                    (nota, ("Segoe UI", 11), COLOR_NOTA)):
                lin = ctk.CTkLabel(tarjeta, text=texto, fg_color="white",
                                   text_color=color, font=fuente,
                                   cursor="hand2", justify="left",
                                   wraplength=270)
                lin.pack(anchor="w", padx=14,
                         pady=((12, 0) if not lineas else (0, 0)))
                lineas.append(lin)
            lineas[-1].pack_configure(pady=(2, 12))
            self._tarjetas_modo[valor] = (tarjeta, lineas)
            for wdg in (tarjeta, *lineas):
                wdg.bind("<Button-1>",
                         lambda e, v=valor: self._elegir_modo(v))
                wdg.bind("<Enter>",
                         lambda e, v=valor: self._hover_tarjeta(v, True))
                wdg.bind("<Leave>",
                         lambda e, v=valor: self._hover_tarjeta(v, False))

        self.lbl_ayuda_modo = rotulo(
            marco, style="Nota.TLabel", wraplength=1020, justify="left")
        self.lbl_ayuda_modo.grid(row=1, column=0, columnspan=3,
                                 sticky="w", padx=6, pady=(8, 0))
        self._cambiar_modo()

    def _elegir_modo(self, modo: str) -> None:
        self.modo_var.set(modo)
        self._cambiar_modo()

    def _hover_tarjeta(self, modo: str, entra: bool) -> None:
        """Resalta la tarjeta bajo el cursor (sin cambiar la selección)."""
        if self.modo_var.get() == modo:
            return
        tarjeta, _ = self._tarjetas_modo[modo]
        tarjeta.configure(border_color=COLOR_NARANJA if entra
                          else COLOR_BORDE)

    def _pintar_tarjetas(self) -> None:
        """Pinta la tarjeta del modo elegido (selección tipo tarjeta)."""
        for valor, (tarjeta, lineas) in self._tarjetas_modo.items():
            activa = self.modo_var.get() == valor
            fondo = COLOR_CARMESI_CLARO if activa else "white"
            tarjeta.configure(fg_color=fondo,
                              border_color=COLOR_CARMESI if activa
                              else COLOR_BORDE,
                              border_width=2 if activa else 1)
            for i, lin in enumerate(lineas):
                if i == 0:
                    color = COLOR_CARMESI if activa else COLOR_TITULO
                elif i == 1:
                    color = COLOR_NARANJA if activa else COLOR_CARMESI
                else:
                    color = COLOR_NOTA
                lin.configure(fg_color=fondo, text_color=color)

    def _cambiar_modo(self, modo: Optional[str] = None) -> None:
        """Aplica el modo elegido: muestra solo los bloques de datos que tocan."""
        if modo:
            self.modo_var.set(modo)
        m = self.modo_var.get()
        self.lbl_ayuda_modo.configure(text=AYUDAS_MODO.get(m, ""))
        if hasattr(self, "_tarjetas_modo"):
            self._pintar_tarjetas()
        self._empaquetar_botones()
        if not hasattr(self, "marco_sizing"):
            return                    # aún se están creando los bloques
        if m == "rating":
            self.marco_sizing.grid_remove()
            self.marco_rating.grid()
        elif m == "sizing":
            self.marco_sizing.grid()
            self.marco_rating.grid_remove()
        else:                                    # «otras»: todo, como antes
            self.marco_sizing.grid()
            self.marco_rating.grid()
        if hasattr(self, "estado"):
            self.estado.set(
                f"Modo {m.upper()} · {AYUDAS_MODO.get(m, '')[:110]}…")

    # ---------------------------------------------------------- bloques UI
    def _marco(self, padre, titulo: str, fila: int, columna: int,
               colspan: int = 1) -> ttk.LabelFrame:
        marco = bloque(padre, text=titulo, padding=(8, 6))
        marco.grid(row=fila, column=columna, columnspan=colspan, sticky="nsew",
                   padx=6, pady=5)
        marco.columnconfigure(1, weight=1)
        return marco

    def _bloque_corrientes(self, padre, fila: int) -> None:
        f = self.form
        fluidos = ctrl.fluidos()

        cal = self._marco(padre, "2 · Corriente CALIENTE", fila, 0)
        f.add("fluido_cal", CampoLista(
            cal, 0, "Fluido", fluidos, ayuda="Base de datos termofísica de "
            "alta fidelidad (src/core).", comando=self._actualizar_limites))
        self.lbl_lim_cal = rotulo(cal, style="Nota.TLabel", text="")
        self.lbl_lim_cal.grid(row=1, column=0, columnspan=3, sticky="w", padx=6)
        f.add("m_cal", CampoNumerico(cal, 2, "Caudal másico", "kg/s",
                                     minimo=1e-6, grupo="corriente caliente",
                                     ayuda="ṁ del lado caliente."))
        f.add("tin_cal", CampoNumerico(cal, 3, "T entrada", "°C",
                                       grupo="corriente caliente"))
        f.add("tout_cal", CampoNumerico(
            cal, 4, "T salida", "°C", opcional=True, grupo="corriente caliente",
            ayuda="Opcional: deje vacío si es la incógnita del balance."))

        fri = self._marco(padre, "3 · Corriente FRÍA", fila, 1)
        f.add("fluido_fri", CampoLista(
            fri, 0, "Fluido", fluidos, valor="Agua",
            comando=self._actualizar_limites))
        self.lbl_lim_fri = rotulo(fri, style="Nota.TLabel", text="")
        self.lbl_lim_fri.grid(row=1, column=0, columnspan=3, sticky="w", padx=6)
        f.add("m_fri", CampoNumerico(fri, 2, "Caudal másico", "kg/s",
                                     minimo=1e-6, grupo="corriente fría"))
        f.add("tin_fri", CampoNumerico(fri, 3, "T entrada", "°C",
                                       grupo="corriente fría"))
        f.add("tout_fri", CampoNumerico(fri, 4, "T salida", "°C",
                                        opcional=True, grupo="corriente fría"))

    def _bloque_tubos(self, padre, fila: int) -> None:
        f = self.form
        m = self._marco(padre, "4 · Haz de tubos", fila, 0)
        f.add("lado_tubos", CampoLista(
            m, 0, "Fluido por los TUBOS", ctrl.LADOS, valor="frio",
            ayuda="Por los tubos suele ir el fluido más sucio, corrosivo o "
                  "de mayor presión."))
        f.add("d_o_mm", CampoNumerico(m, 1, "Ø exterior del tubo", "mm",
                                      minimo=5.0, maximo=60.0,
                                      ayuda="Estándar TEMA: 3/4 in = 19.05 mm."))
        f.add("esp_mm", CampoNumerico(m, 2, "Espesor de pared", "mm",
                                      minimo=0.3, maximo=10.0,
                                      ayuda="BWG 16 ≈ 1.65 mm."))
        f.add("pitch_mm", CampoNumerico(m, 3, "Pitch P_T", "mm", minimo=5.0,
                                        ayuda="TEMA exige P_T ≥ 1.25·d_o."))
        f.add("long_m", CampoNumerico(m, 4, "Longitud del tubo", "m",
                                      minimo=0.3, maximo=12.0,
                                      ayuda="Comerciales: 2.44 / 3.66 / 4.88 / "
                                            "6.10 m."))
        f.add("layout", CampoLista(m, 5, "Arreglo (layout)",
                                   list(ctrl.LAYOUTS),
                                   ayuda="Triangular: más área por volumen. "
                                         "Cuadrado: permite limpieza mecánica."))
        f.add("n_pasos", CampoLista(m, 6, "Pasos por tubos", ctrl.PASOS,
                                    valor="2"))
        f.add("mat_tubo", CampoLista(m, 7, "Material del tubo",
                                     ctrl.materiales_tubo(), valor="Cobre"))

    def _bloque_coraza(self, padre, fila: int) -> None:
        f = self.form
        m = self._marco(padre, "5 · Coraza y deflectores", fila, 1)
        f.add("baffle_mm", CampoNumerico(
            m, 0, "Espaciado de baffles B", "mm", minimo=10.0,
            ayuda="Buena práctica: 0.3·D_s ≤ B ≤ 1.0·D_s. Como D_s es un "
                  "RESULTADO del sizing, B se ajusta iterando: use el botón "
                  "«½·D_s» tras el primer cálculo."))
        # B es dato de entrada del térmico pero su ventana válida depende de
        # D_s, que es resultado: este botón cierra el lazo a mano, sin que la
        # GUI calcule nada.
        boton(m, text="½·D_s", width=6, command=self._ajustar_baffle
                   ).grid(row=0, column=3, padx=(0, 6))
        f.add("corte_pct", CampoNumerico(m, 1, "Corte de baffle", "%",
                                         minimo=15.0, maximo=45.0,
                                         ayuda="Estándar: 25 %."))

    def _bloque_sizing(self, padre, fila: int) -> None:
        """A · Datos que solo necesita el dimensionamiento (sizing)."""
        f = self.form
        self.marco_sizing = m = self._marco(
            padre, "A · SOLO DIMENSIONAR (Sizing)", fila, 0)
        f.add("u_inicial", CampoNumerico(
            m, 0, "U inicial (semilla)", "W/m²K", minimo=10.0, maximo=10000.0,
            ayuda="Solo es la semilla de la iteración de Kern; no altera el "
                  "resultado convergido."))
        rotulo(m, text="Límites permisibles de Δp (verificación hidráulica)",
                  style="Nota.TLabel").grid(row=1, column=0, columnspan=3,
                                            sticky="w", padx=6)
        f.add("dp_t_max", CampoNumerico(
            m, 2, "Δp máx. en tubos", "Pa", minimo=0.0, opcional=True,
            ayuda="Si la Δp calculada lo supera, el programa advierte que hay "
                  "que revisar o redimensionar el equipo. Vacío o 0 = sin límite."))
        f.add("dp_s_max", CampoNumerico(
            m, 3, "Δp máx. en coraza", "Pa", minimo=0.0, opcional=True,
            ayuda="Misma verificación para el lado coraza. Vacío o 0 = sin límite."))

    def _bloque_rating(self, padre, fila: int) -> None:
        """B · Datos que solo necesita la evaluación (rating)."""
        f = self.form
        self.marco_rating = m = self._marco(
            padre, "B · SOLO EVALUAR (Rating)", fila, 1)
        f.add("n_tt", CampoNumerico(m, 0, "N.º total de tubos", "–",
                                    minimo=1, entero=True, opcional=True,
                                    ayuda="Geometría real del equipo existente. "
                                          "Obligatorio solo en modo rating: en "
                                          "sizing el programa lo calcula."))
        f.add("d_s_mm", CampoNumerico(m, 1, "Ø interior de coraza", "mm",
                                      minimo=50.0, opcional=True,
                                      ayuda="Obligatorio solo en modo rating; "
                                            "en sizing es un resultado."))
        rotulo(m, style="Nota.TLabel", wraplength=430, justify="left",
                  text="Geometría del equipo YA CONSTRUIDO. En modo rating las "
                       "temperaturas de salida son las incógnitas: déjelas "
                       "vacías en las corrientes."
                  ).grid(row=2, column=0, columnspan=3, sticky="w",
                         padx=6, pady=(4, 0))

    def _bloque_tema(self, padre, fila: int) -> None:
        """5 · Tipos TEMA: la designación de tres letras (Fig. N-1.2)."""
        f = self.form
        m = self._marco(padre, "6 · Configuración TEMA (Fig. N-1.2)", fila, 0)
        f.add("tipo_carcasa", CampoLista(
            m, 0, "Carcasa", ctrl.TIPOS_CARCASA, valor="E",
            ayuda="E = una pasada · F = dos con deflector longitudinal · "
                  "G/H/J = flujo partido · K = caldera · X = cruzado.",
            comando=self._actualizar_designacion_tema))
        f.add("cab_frontal", CampoLista(
            m, 1, "Cabezal frontal", ctrl.CABEZAL_FRONTAL, valor="A",
            ayuda="A/B/C/D/N — ver la vista 5 «Catálogo TEMA» en Drawing.",
            comando=self._actualizar_designacion_tema))
        f.add("cab_trasero", CampoLista(
            m, 2, "Cabezal trasero", ctrl.CABEZAL_TRASERO, valor="M",
            ayuda="L/M/N (espejo fijo) · P/S/T/W (flotantes) · U (haz en U).",
            comando=self._actualizar_designacion_tema))
        f.add("metodo_coraza", CampoLista(
            m, 4, "Método coraza", ctrl.METODOS_CORAZA_UI,
            valor="Automático (recomendado)",
            ayuda="Kern: correlación clásica (cap. 7). Bell-Delaware: corrige "
                  "fugas y bypass con Jc, Jl, Jb, Jr (más riguroso)."))
        rotulo(m, text="Designación TEMA:", style="Nota.TLabel"
                  ).grid(row=3, column=0, sticky="w", padx=(6, 8), pady=(6, 0))
        self.lbl_designacion = rotulo(
            m, text="AEM", style="Designacion.TLabel")
        self.lbl_designacion.grid(row=3, column=1, columnspan=2,
                                  sticky="w", pady=(6, 0))

    def _actualizar_designacion_tema(self) -> None:
        """Muestra la designación TEMA de tres letras en vivo (ej. BEM)."""
        try:
            d = self.form.leer()
        except CampoInvalido:
            return
        self.lbl_designacion.configure(
            text=f"{d['cab_frontal']}{d['tipo_carcasa']}{d['cab_trasero']}")

    def _bloque_mecanico(self, padre, fila: int) -> None:
        f = self.form
        m = self._marco(padre, "7 · Condiciones de diseño y materiales",
                        fila, 1)
        for c in (1, 4):
            m.columnconfigure(c, weight=1)
        f.add("p_coraza_bar", CampoNumerico(m, 0, "Presión diseño coraza",
                                            "bar", minimo=0.1, maximo=200.0))
        f.add("p_tubos_bar", CampoNumerico(m, 1, "Presión diseño tubos",
                                           "bar", minimo=0.1, maximo=200.0))
        f.add("mat_carcasa", CampoLista(m, 0, "Material de carcasa",
                                        ctrl.materiales_carcasa(),
                                        valor="Acero al carbono", columna=3,
                                        ancho=22))
        f.add("corrosion_mm", CampoNumerico(
            m, 1, "Sobreespesor de corrosión", "mm", minimo=0.0, maximo=12.0,
            columna=3, ayuda="TEMA Clase C recomienda 3.2 mm (1/8 in)."))
        f.add("d_perno_mm", CampoNumerico(m, 2, "Ø de perno de brida", "mm",
                                          minimo=6.0, maximo=60.0, columna=3))

    def _bloque_botones(self, padre, fila: int) -> None:
        barra = ttk.Frame(padre)
        barra.grid(row=fila, column=0, columnspan=2, sticky="ew", padx=6,
                   pady=(4, 14))
        b_sizing = boton(barra, text="Calcular dimensionamiento   (F5)",
                              style="Accion.TButton",
                              command=lambda: self._calcular_async("sizing"))
        b_rating = boton(barra, text="Calcular evaluación   (F6)",
                              style="Accion2.TButton",
                              command=lambda: self._calcular_async("rating"))
        self.b_sizing, self.b_rating = b_sizing, b_rating
        self._botones_calculo = [b_sizing, b_rating]
        boton(barra, text="Restaurar caso base", style="Suave.TButton",
                   command=self._restaurar_defecto).pack(side="right")
        self._empaquetar_botones()

    def _empaquetar_botones(self) -> None:
        """Modo estricto: cada modo muestra solo su botón de cálculo."""
        if not hasattr(self, "b_sizing"):
            return
        m = self.modo_var.get()
        self.b_sizing.pack_forget()
        self.b_rating.pack_forget()
        if m in ("sizing", "avanzado"):
            self.b_sizing.pack(side="left", padx=(0, 8))
        if m in ("rating", "avanzado"):
            self.b_rating.pack(side="left", padx=8 if m == "avanzado" else 0)

    def _tecla_calcular(self, modo: str) -> None:
        """F5/F6 respetan el modo de trabajo elegido en el paso 1."""
        m = self.modo_var.get()
        if m != "avanzado" and m != modo:
            nombre = ("dimensionamiento" if m == "sizing"
                      else "evaluación")
            self.estado.set(
                f"Está en modo {nombre.upper()}: solo puede calcular "
                f"{nombre}. Use el paso 1 para cambiar de modo "
                f"(u OTRAS para el formulario completo).")
            return
        self._calcular_async(modo)

    # ------------------------------------------------------------- analysis
    def _tab_analysis(self) -> None:
        marco = ttk.Frame(self.nb, padding=8)
        self.nb.add(marco, text="  Analysis  ")
        marco.columnconfigure(0, weight=3)
        marco.columnconfigure(1, weight=2, minsize=540)
        marco.rowconfigure(1, weight=1)

        self.lbl_modo = rotulo(marco, text="Sin resultados todavía",
                                  style="Titulo.TLabel")
        self.lbl_modo.grid(row=0, column=0, columnspan=2, sticky="w",
                           pady=(0, 6))

        izq = bloque(marco, text="Thermal Design", padding=(6, 4))
        izq.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        izq.rowconfigure(0, weight=1)
        izq.columnconfigure(0, weight=1)
        self.tbl_termico = tabla_resultados(izq, altura=18)
        self.tbl_termico.grid(row=0, column=0, sticky="nsew")

        der = ttk.Frame(marco)
        der.grid(row=1, column=1, sticky="nsew")
        der.rowconfigure(0, weight=2)
        der.rowconfigure(1, weight=2)
        der.rowconfigure(2, weight=1)
        der.columnconfigure(0, weight=1)

        hid = bloque(der, text="Hydraulic Design", padding=(6, 4))
        hid.grid(row=0, column=0, sticky="nsew")
        hid.rowconfigure(0, weight=1)
        hid.columnconfigure(0, weight=1)
        self.tbl_hidraulico = tabla_resultados(hid, altura=8)
        self.tbl_hidraulico.grid(row=0, column=0, sticky="nsew")
        rotulo(hid, style="Nota.TLabel", wraplength=330, text=(
            "Caídas de presión Δp por el método de Kern (tubos: fricción + "
            "retorno, Eq. 7.43/7.45; coraza: Eq. 7.44). Son indicativas: antes "
            "de fabricar contrástelas con un cálculo detallado.")
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        ver = bloque(der, text="Verificación del diseño", padding=(6, 4))
        ver.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        ver.rowconfigure(0, weight=1)
        ver.columnconfigure(0, weight=1)
        self.tbl_verif = tabla_resultados(ver, altura=8)
        self.tbl_verif.grid(row=0, column=0, sticky="nsew")
        self.lbl_verif_titulo = rotulo(ver, style="Nota.TLabel", text=(
            "Checklist de verificación según el modo de trabajo."))
        self.lbl_verif_titulo.grid(row=1, column=0, sticky="w", pady=(2, 0))

        adv = bloque(der, text="Advertencias y notas educativas",
                             padding=(6, 4))
        adv.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
        adv.rowconfigure(0, weight=1)
        adv.columnconfigure(0, weight=1)
        self.txt_adv = tk.Text(adv, height=7, wrap="word", relief="solid",
                               bd=1, font=("Segoe UI", 12), bg="white")
        self.txt_adv.grid(row=0, column=0, sticky="nsew")
        self.txt_adv.configure(state="disabled")

    # -------------------------------------------------------------- drawing
    def _tab_drawing(self) -> None:
        marco = ttk.Frame(self.nb, padding=8)
        self.nb.add(marco, text="  Drawing  ")
        # El panel lateral necesita ~540 px para que la tabla de dimensiones
        # muestre sus cuatro columnas (Parámetro/Símbolo/Valor/Unidad) sin
        # recortar los valores.
        marco.columnconfigure(0, weight=3)
        marco.columnconfigure(1, weight=2, minsize=540)
        marco.rowconfigure(1, weight=1)

        cab = ttk.Frame(marco)
        cab.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        rotulo(cab, text="Vista:").pack(side="left", padx=(2, 6))
        self.var_vista = tk.StringVar(value=list(drawings.VISTAS)[0])
        combo = ttk.Combobox(cab, textvariable=self.var_vista, width=32,
                             state="readonly", values=list(drawings.VISTAS))
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self._redibujar())

        # Un clic en el campo abre la lista (no solo la flecha lateral).
        def _abrir_lista(evt, _c=combo):
            if evt.x < _c.winfo_width() - 24:
                _c.tk.call("ttk::combobox::Post", _c)
        combo.bind("<Button-1>", _abrir_lista, add="+")
        boton(cab, text="Redibujar", command=self._redibujar).pack(
            side="left", padx=8)
        rotulo(cab, style="Nota.TLabel",
                  text="Dibujos paramétricos: se generan desde las cotas "
                       "calculadas en src/mechanical.").pack(side="left",
                                                             padx=10)

        self.canvas = tk.Canvas(marco, bg="white", width=760, height=470,
                                relief="solid", bd=1, highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.canvas.bind("<Button-1>", self._clic_dibujo)
        # El redibujado va con debounce: estirar la ventana genera cientos de
        # <Configure> seguidos y se pinta UNA sola vez al dejar de arrastrar.
        self.canvas.bind("<Configure>", self._al_redimensionar_canvas)
        self.canvas.bind("<Motion>", self._al_mover_sobre_canvas)

        lado = bloque(marco, text="Dimensiones de fabricación",
                              padding=(6, 4))
        lado.grid(row=1, column=1, sticky="nsew")
        lado.rowconfigure(0, weight=1)
        lado.columnconfigure(0, weight=1)
        self.tbl_mecanico = tabla_resultados(lado, altura=22)
        self.tbl_mecanico.grid(row=0, column=0, sticky="nsew")
        rotulo(lado, style="Nota.TLabel", wraplength=300,
                  text="Clic sobre una pieza del dibujo para ver sus cotas "
                       "en una ventana emergente.").grid(row=1, column=0,
                                                         sticky="w",
                                                         pady=(4, 0))

    # ----------------------------------------------------------------- help
    def _tab_help(self) -> None:
        marco = ttk.Frame(self.nb, padding=10)
        self.nb.add(marco, text="  Help  ")
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        txt = tk.Text(marco, wrap="word", relief="solid", bd=1,
                      font=("Segoe UI", 12), bg="white", padx=14, pady=12)
        barra = ttk.Scrollbar(marco, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=barra.set)
        txt.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

        txt.tag_configure("h1", font=("Segoe UI", 13, "bold"),
                          foreground=COLOR_TITULO, spacing3=8)
        txt.tag_configure("h2", font=("Segoe UI", 12, "bold"),
                          foreground=COLOR_TITULO, spacing1=10, spacing3=4)
        txt.insert("end", "Guía rápida de uso\n", "h1")
        for titulo, cuerpo in AYUDA:
            txt.insert("end", titulo + "\n", "h2")
            txt.insert("end", cuerpo + "\n")
        txt.configure(state="disabled")

    # ============================================================== acciones
    def _actualizar_limites(self) -> None:
        """Muestra la ventana de validez termofísica de cada fluido."""
        for clave, etiqueta in (("fluido_cal", self.lbl_lim_cal),
                                ("fluido_fri", self.lbl_lim_fri)):
            try:
                t_min, t_max = ctrl.limites_fluido(self.form.campos[clave].get())
                etiqueta.configure(
                    text=f"Validez de la correlación: {t_min:.0f} °C a "
                         f"{t_max:.0f} °C")
            except ValueError:
                etiqueta.configure(text="")

    def _restaurar_defecto(self) -> None:
        self._blindar(lambda: self.form.cargar(VALORES_DEFECTO),
                      "Restauración del caso base")
        self._actualizar_limites()
        self._actualizar_designacion_tema()

    def _ajustar_baffle(self) -> None:
        """Rellena B con la mitad del último D_s calculado (lazo manual)."""
        if not self.ultimo_D_s:
            messagebox.showinfo(
                "Todavía no hay diámetro de coraza",
                "El espaciado de baffles B es un DATO del cálculo térmico, "
                "pero su ventana válida (D_s/5 ≤ B ≤ D_s) depende de D_s, que "
                "es un RESULTADO.\n\n"
                "Ejecute primero un dimensionamiento (F5) con un B tentativo; "
                "después este botón lo ajustará a 0.5·D_s y usted recalcula. "
                "Dos pasadas bastan en la práctica.")
            return
        nuevo = round(self.ultimo_D_s * 500.0, 1)      # 0.5·D_s expresado en mm
        self.form.campos["baffle_mm"].set(nuevo)
        self.estado.set(f"B ajustado a 0.5·D_s = {nuevo} mm "
                        f"(D_s = {self.ultimo_D_s*1000:.0f} mm). "
                        f"Pulse F5 para recalcular con el nuevo espaciado.")

    def _blindar(self, accion, titulo: str) -> None:
        """Ejecuta `accion` atrapando los errores del modelo (sin crash)."""
        try:
            accion()
        except Exception as exc:
            self._mostrar_error(exc, titulo)

    def _mostrar_error(self, exc: BaseException, titulo: str) -> None:
        """Traduce una excepción del modelo al pop-up educativo correspondiente."""
        if isinstance(exc, CampoInvalido):
            messagebox.showwarning("Formulario incompleto", str(exc))
            self.estado.set("Formulario incompleto: revise los campos en rojo.")
        elif isinstance(exc, ErrorDiseno):
            messagebox.showwarning(
                f"Revisión de ingeniería · {exc.titulo}",
                exc.como_dialogo())
            self.estado.set(f"Cálculo detenido: {exc.titulo}.")
        elif isinstance(exc, ValueError):
            messagebox.showwarning(
                f"{titulo} · revisión de ingeniería",
                f"{exc}\n\n— Corrija los datos de entrada y vuelva a calcular.")
            self.estado.set("Cálculo detenido por una condición física "
                            "inadmisible.")
        elif isinstance(exc, ZeroDivisionError):
            messagebox.showwarning(
                f"{titulo} · división por cero",
                "Un dato geométrico o un caudal es nulo. Verifique que ningún "
                "campo valga 0.")
        else:                                     # red de seguridad final
            messagebox.showerror(
                "Error inesperado",
                f"{type(exc).__name__}: {exc}\n\n"
                f"{traceback.format_exc(limit=3)}")
            self.estado.set("Error inesperado; la aplicación sigue activa.")

    # ------------------------------------------------------------- cálculos
    # Rutas de ejecución:
    #   * SINCRONA (`_calcular_sizing` / `_calcular_rating`): la usan las
    #     pruebas y la automatización; calcula y pinta en el mismo llamado.
    #   * ASINCRONA (`_calcular_async`): la usan los botones y F5/F6. El
    #     cálculo del modelo corre en un hilo aparte para que la ventana siga
    #     respondiendo (arrastrar, cambiar de pestaña, ver el dibujo) y los
    #     resultados se aplican en el hilo principal vía `after()`.
    # Ambas comparten `_modelo_*` (cálculo puro, sin widgets) y `_aplicar_*`
    # (pintado, siempre en el hilo principal).

    def _calcular_sizing(self) -> None:
        """Camino síncrono (pruebas / automatización)."""
        self._blindar(self._sizing, "Dimensionamiento")

    def _calcular_rating(self) -> None:
        """Camino síncrono (pruebas / automatización)."""
        self._blindar(self._rating, "Evaluación (Rating)")

    def _sizing(self) -> None:
        datos = self.form.leer()
        paquete = self._modelo_sizing(datos)
        self._aplicar_sizing(datos, *paquete)

    def _rating(self) -> None:
        datos = self.form.leer()
        paquete = self._modelo_rating(datos)
        self._aplicar_rating(datos, *paquete)

    # -- modelo (sin UI): seguro de ejecutar en un hilo aparte -------------
    def _modelo_sizing(self, datos: Dict[str, Any]):
        res = ctrl.correr_sizing(datos)
        res_mec, aviso_mec = self._modelo_mecanico(
            datos, res.D_s, res.N_tt, res.T_h_out, res.T_c_out)
        return res, res_mec, aviso_mec

    def _modelo_rating(self, datos: Dict[str, Any]):
        res = ctrl.correr_rating(datos)
        res_mec, aviso_mec = self._modelo_mecanico(
            datos, datos["d_s_mm"] / 1000.0, int(datos["n_tt"]),
            res.T_h_out, res.T_c_out)
        return res, res_mec, aviso_mec

    def _modelo_mecanico(self, datos: Dict[str, Any], D_s: float, N_tt: int,
                         T_h_out: float, T_c_out: float):
        """El fallo mecánico no debe invalidar el resultado térmico."""
        try:
            T_m_cal = 0.5 * (datos["tin_cal"] + T_h_out)
            T_m_fri = 0.5 * (datos["tin_fri"] + T_c_out)
            return ctrl.correr_mecanico(datos, D_s, N_tt, T_m_cal,
                                        T_m_fri), None
        except ValueError as exc:
            return None, str(exc)

    # -- ejecución en segundo plano ----------------------------------------
    def _calcular_async(self, modo: str) -> None:
        """Lanza sizing/rating sin congelar la ventana (botones y F5/F6)."""
        if self._trabajo is not None and self._trabajo.is_alive():
            self.estado.set("Todavía hay un cálculo en curso… espere un "
                            "momento, ya casi está.")
            return
        try:
            datos = self.form.leer()
        except CampoInvalido as exc:
            self._mostrar_error(exc, "Formulario")
            return
        # Un proyecto SIN temperatura de salida es un caso de evaluación
        # (rating): la geometría ya está definida y la incógnita es el
        # comportamiento del equipo. En ese caso F5 se redirige a F6 para que
        # el usuario vea el resultado en vez de un error de balance.
        if modo == "sizing" and ctrl.modo_calculo(datos) == "rating":
            modo = "rating"
            self.estado.set(
                "Proyecto de evaluación (rating): ninguna «T salida» está "
                "definida porque la incógnita es el comportamiento del equipo "
                "existente. Se ejecutó «Evaluar equipo» (F6).")

        etiqueta = ("Calculando dimensionamiento (Método de Kern)… la ventana "
                    "sigue activa" if modo == "sizing"
                    else "Evaluando equipo (Rating)… la ventana sigue activa")
        self._poner_ocupado(True, etiqueta)
        bandeja: Dict[str, Any] = {}

        def trabajo():
            try:
                if modo == "sizing":
                    bandeja["ok"] = self._modelo_sizing(datos)
                else:
                    bandeja["ok"] = self._modelo_rating(datos)
            except Exception as exc:      # se mostrará en el hilo principal
                bandeja["err"] = exc

        self._trabajo = threading.Thread(target=trabajo, daemon=True)
        self._trabajo.start()
        self.after(40, lambda: self._recoger_trabajo(modo, datos, bandeja))

    def _recoger_trabajo(self, modo: str, datos: Dict[str, Any],
                         bandeja: Dict[str, Any]) -> None:
        """Sondea el hilo de cálculo; al terminar aplica los resultados."""
        if self._trabajo is not None and self._trabajo.is_alive():
            self.after(40, lambda: self._recoger_trabajo(modo, datos, bandeja))
            return
        self._trabajo = None
        self._poner_ocupado(False)
        titulo = ("Dimensionamiento" if modo == "sizing"
                  else "Evaluación (Rating)")
        if "err" in bandeja:
            self._mostrar_error(bandeja["err"], titulo)
            return

        paquete = bandeja["ok"]

        def aplicar():
            if modo == "sizing":
                self._aplicar_sizing(datos, *paquete)
            else:
                self._aplicar_rating(datos, *paquete)
        self._blindar(aplicar, "Presentación de resultados")

    def _poner_ocupado(self, ocupado: bool, etiqueta: str = "") -> None:
        """Cursor de espera + botones deshabilitados mientras corre un cálculo."""
        self.config(cursor="watch" if ocupado else "")
        estado = "disabled" if ocupado else "normal"
        for boton in self._botones_calculo:
            boton.configure(state=estado)
        if etiqueta:
            self.estado.set(etiqueta)
            self.update_idletasks()      # pinta el mensaje antes del trabajo pesado

    # -- aplicación de resultados (siempre en el hilo principal) ------------
    def _aplicar_sizing(self, datos: Dict[str, Any], res, res_mec,
                        aviso_mec: Optional[str]) -> None:
        self.res_termico, self.modo = res, "sizing"
        self.ultimo_D_s = res.D_s
        self.form.campos["n_tt"].set(res.N_tt)
        self.form.campos["d_s_mm"].set(round(res.D_s * 1000.0, 1))
        self._render_sizing(res)
        self._render_verificaciones("sizing", datos, res, res_mec)
        self._aplicar_mecanico(res_mec, aviso_mec)
        self.nb.select(1)
        self.estado.set(
            f"Sizing convergido en {res.iteraciones} iteraciones · "
            f"U = {res.U:.1f} W/m²K · A = {res.A:.2f} m² · "
            f"{res.N_tt} tubos · D_s = {res.D_s*1000:.0f} mm")
        self._avisar_advertencias(res.advertencias)

    def _aplicar_rating(self, datos: Dict[str, Any], res, res_mec,
                        aviso_mec: Optional[str]) -> None:
        self.res_termico, self.modo = res, "rating"
        self.ultimo_D_s = datos["d_s_mm"] / 1000.0
        self._render_rating(res)
        self._render_verificaciones("rating", datos, res, res_mec)
        self._aplicar_mecanico(res_mec, aviso_mec)
        self.nb.select(1)
        self.estado.set(
            f"Rating convergido en {res.iteraciones} iteraciones · "
            f"q = {res.q/1000:.1f} kW · ε = {res.efectividad*100:.1f} % · "
            f"T_h,out = {res.T_h_out:.1f} °C · T_c,out = {res.T_c_out:.1f} °C")
        self._avisar_advertencias(res.advertencias)

    def _aplicar_mecanico(self, res_mec, aviso_mec: Optional[str]) -> None:
        if res_mec is not None:
            self.res_mecanico = res_mec
            self._render_mecanico(res_mec)
        else:
            self.res_mecanico = None
        self._redibujar()
        if aviso_mec:
            messagebox.showwarning(
                "Diseño mecánico no completado",
                f"El cálculo térmico sí convergió, pero el dimensionamiento "
                f"mecánico se detuvo:\n\n{aviso_mec}")

    def _avisar_advertencias(self, advertencias) -> None:
        if advertencias:
            cuerpo = []
            for i, texto in enumerate(advertencias, 1):
                cuerpo.append(f"{i}. {texto}")
            messagebox.showinfo(
                "Advertencias de buena práctica",
                "El cálculo convergió, pero conviene revisar "
                f"({len(advertencias)} nota(s)):\n\n" +
                "\n\n".join(cuerpo) +
                "\n\nEstas notas también quedan en el panel «Advertencias y "
                "notas educativas» de la pestaña Analysis.")

    # ------------------------------------------------------------ renderizado
    def _render_sizing(self, r) -> None:
        self.lbl_modo.configure(
            text="Resultados · Dimensionamiento térmico (Método de Kern)")
        llenar_tabla(self.tbl_termico, [
            ("BALANCE DE ENERGÍA", "", "", "", "titulo"),
            ("Carga térmica", "q", f"{r.q/1000.0:,.2f}", "kW"),
            ("T salida fluido caliente", "T_h,out", f"{r.T_h_out:.2f}", "°C"),
            ("T salida fluido frío", "T_c,out", f"{r.T_c_out:.2f}", "°C"),
            ("MEDIA LOGARÍTMICA", "", "", "", "titulo"),
            ("LMTD en contracorriente", "ΔT_lm", f"{r.LMTD:.2f}", "°C"),
            ("Factor de corrección", "F", f"{r.F:.4f}", "–",
             "" if r.F >= ctrl.F_MIN_ACEPTABLE else "alerta"),
            ("TRANSFERENCIA DE CALOR", "", "", "", "titulo"),
            ("Coef. película interior", "h_i", f"{r.h_i:,.1f}", "W/m²K"),
            ("Coef. película exterior", "h_o", f"{r.h_o:,.1f}", "W/m²K"),
            ("Coef. global sucio", "U_D", f"{r.U:,.2f}", "W/m²K"),
            ("SUPERFICIE Y GEOMETRÍA", "", "", "", "titulo"),
            ("Área requerida", "A_req", f"{r.A:,.3f}", "m²"),
            ("Área instalada", "A_real", f"{r.A_real:,.3f}", "m²"),
            ("Sobre-área de diseño", "%", f"{r.sobre_area:,.1f}", "%",
             "" if r.sobre_area >= 0 else "alerta"),
            ("Número total de tubos", "N_tt", f"{r.N_tt:,d}", "–"),
            ("Ø interior de coraza", "D_s", f"{r.D_s*1000.0:,.1f}", "mm"),
            ("Número de baffles", "N_B", f"{r.N_baffles:,d}", "–"),
            ("Iteraciones hasta converger", "–", f"{r.iteraciones}", "–"),
        ])
        self._render_hidraulico(r)
        self._render_advertencias(r.advertencias)

    def _render_rating(self, r) -> None:
        self.lbl_modo.configure(
            text="Resultados · Evaluación de un equipo existente (Rating)")
        llenar_tabla(self.tbl_termico, [
            ("DESEMPEÑO", "", "", "", "titulo"),
            ("Calor transferido real", "q", f"{r.q/1000.0:,.2f}", "kW"),
            ("T salida fluido caliente", "T_h,out", f"{r.T_h_out:.2f}", "°C"),
            ("T salida fluido frío", "T_c,out", f"{r.T_c_out:.2f}", "°C"),
            ("Efectividad", "ε", f"{r.efectividad*100:.2f}", "%"),
            ("Unidades de transferencia", "NTU", f"{r.NTU:.3f}", "–"),
            ("Relación de capacidades", "C_r", f"{r.C_r:.3f}", "–"),
            ("MEDIA LOGARÍTMICA", "", "", "", "titulo"),
            ("LMTD en contracorriente", "ΔT_lm", f"{r.LMTD:.2f}", "°C"),
            ("Factor de corrección", "F", f"{r.F:.4f}", "–",
             "" if r.F >= ctrl.F_MIN_ACEPTABLE else "alerta"),
            ("TRANSFERENCIA DE CALOR", "", "", "", "titulo"),
            ("Coef. película interior", "h_i", f"{r.h_i:,.1f}", "W/m²K"),
            ("Coef. película exterior", "h_o", f"{r.h_o:,.1f}", "W/m²K"),
            ("Coef. global sucio", "U_D", f"{r.U:,.2f}", "W/m²K"),
            ("Área instalada", "A", f"{r.A:,.3f}", "m²"),
            ("CONVERGENCIA", "", "", "", "titulo"),
            ("Residual del balance", "|Δq|", f"{r.residual:,.2f}", "W"),
            ("Iteraciones", "–", f"{r.iteraciones}", "–"),
        ])
        self._render_hidraulico(r)
        self._render_advertencias(r.advertencias)

    def _render_hidraulico(self, r) -> None:
        # Los umbrales vienen de src/thermo/sizing.py vía el controlador.
        llenar_tabla(self.tbl_hidraulico, [
            ("LADO TUBOS", "", "", "", "titulo"),
            ("Velocidad másica media", "v_t", f"{r.v_t:.3f}", "m/s",
             "" if ctrl.V_TUBO_MIN <= r.v_t <= ctrl.V_TUBO_MAX else "alerta"),
            ("Reynolds", "Re_t", f"{r.Re_t:,.0f}", "–"),
            ("Régimen de flujo", "–", r.regimen_tubo, "",
             "" if r.regimen_tubo == "turbulento" else "alerta"),
            ("LADO CORAZA", "", "", "", "titulo"),
            ("Velocidad media", "v_s", f"{r.v_s:.3f}", "m/s",
             "" if ctrl.V_CORAZA_MIN <= r.v_s <= ctrl.V_CORAZA_MAX
             else "alerta"),
            ("Reynolds", "Re_s", f"{r.Re_s:,.0f}", "–"),
            ("Régimen de flujo", "–", getattr(r, "regimen_coraza", "–"), "",
             "" if getattr(r, "regimen_coraza", "turbulento") == "turbulento"
             else "alerta"),
            ("Ø equivalente de Kern", "D_e", f"{r.D_e*1000.0:,.2f}", "mm"),
            ("CAÍDA DE PRESIÓN", "", "", "", "titulo"),
            ("Δp lado tubos", "Δp_t", f"{r.dp_t:,.0f}", "Pa"),
            ("Δp lado coraza", "Δp_s", f"{r.dp_s:,.0f}", "Pa"),
            ("Fricción tubos (Darcy)", "f_t", f"{r.f_t:.4f}", "–"),
            ("Fricción coraza (Kern)", "f_s", f"{r.f_s:.4f}", "–"),
        ])

    def _render_verificaciones(self, modo: str, datos, res, res_mec) -> None:
        """Checklist de verificación del diseño, distinto para sizing y rating."""
        filas = [("VERIFICACIÓN DEL DISEÑO", "ESTADO", "DETALLE", "", "titulo")]
        for nombre, estado, detalle in ctrl.verificaciones_diseno(
                modo, datos, res, res_mec):
            filas.append((nombre, estado, detalle, "",
                          "ok" if estado == "OK" else "alerta"))
        llenar_tabla(self.tbl_verif, filas)
        self.lbl_verif_titulo.configure(text=(
            f"Modo {modo.upper()}: "
            + ("propuesta de equipo NUEVO — se verifican la sobre-área, la "
               "geometría TEMA y las ventanas de velocidad."
               if modo == "sizing" else
               "evaluación de un equipo EXISTENTE — se verifican el cierre "
               "del balance, la efectividad y la cercanía al pinch.")))

    def _render_advertencias(self, advertencias) -> None:
        self.txt_adv.configure(state="normal")
        self.txt_adv.delete("1.0", "end")
        if advertencias:
            for i, texto in enumerate(advertencias, 1):
                self.txt_adv.insert("end", f"⚠  {i}. {texto}\n\n")
        else:
            self.txt_adv.insert(
                "end", "Sin advertencias: el diseño respeta las ventanas "
                       "de velocidad, el pitch mínimo y el factor F "
                       "recomendados por TEMA / Kern.")
        self.txt_adv.configure(state="disabled")

    def _render_mecanico(self, m) -> None:
        b, br = m.baffles, m.brida
        filas = [
            ("CARCASA", "", "", "", "titulo"),
            ("Tipo TEMA de coraza", "–", m.tipo_carcasa, ""),
            ("Ø interior", "D_s", f"{m.D_s*1000:,.1f}", "mm"),
            ("Espesor de pared", "t_s", f"{m.T_s*1000:,.2f}", "mm"),
            ("Ø exterior", "D_o", f"{m.D_o*1000:,.1f}", "mm"),
            ("Límite exterior del haz", "D_otl", f"{m.D_otl*1000:,.1f}", "mm"),
            ("Ø de centros periféricos", "D_ctl", f"{m.D_ctl*1000:,.1f}", "mm"),
            ("Longitud total", "L_tot", f"{m.L_total:,.3f}", "m"),
            ("ESPEJO Y CABEZALES", "", "", "", "titulo"),
            ("Espesor de espejo", "L_ts", f"{m.L_ts*1000:,.2f}", "mm"),
            (f"Cabezal frontal «{m.cab_frontal.tipo}»", "–",
             m.cab_frontal.descripcion, ""),
            (f"Cabezal trasero «{m.cab_trasero.tipo}»", "–",
             m.cab_trasero.descripcion, ""),
            ("Espesor de cubierta", "T_c", f"{m.T_c*1000:,.2f}", "mm"),
            ("Tipo de cubierta", "–", m.tipo_cubierta, ""),
            ("DEFLECTORES", "", "", "", "titulo"),
            ("Cantidad", "N_B", f"{b.N_B:,d}", "–"),
            ("Espaciado central", "L_bc", f"{b.L_bc*1000:,.1f}", "mm"),
            ("Espaciado entrada/salida", "L_bi", f"{b.L_bi*1000:,.1f}", "mm"),
            ("Espesor de placa", "t_b", f"{b.espesor*1000:,.2f}", "mm"),
            ("Ø de placa", "D_b", f"{b.D_baffle*1000:,.1f}", "mm"),
            ("Altura del corte", "h_c", f"{b.altura_corte*1000:,.1f}", "mm"),
            ("Tramo sin soporte", "L_u", f"{b.luz_sin_soporte:,.3f}", "m"),
            ("Varillas tensores (CB-4.7.1)", "n",
             f"{m.tie_rods.cantidad} × {m.tie_rods.d*1000:,.1f}", "mm"),
            ("BRIDA", "", "", "", "titulo"),
            ("Ancho radial", "f_w", f"{br.f_w*1000:,.1f}", "mm"),
            ("Ø exterior", "D_F", f"{br.D_F*1000:,.1f}", "mm"),
            ("Ø círculo de pernos", "D_BC", f"{br.D_BC*1000:,.1f}", "mm"),
            ("Número de pernos", "n", f"{br.n_pernos:,d}", "–"),
        ]
        for boq, nombre in ((m.boquilla_coraza, "BOQUILLA CORAZA"),
                            (m.boquilla_tubos, "BOQUILLA TUBOS")):
            if boq is None:
                continue
            filas += [
                (nombre, "", "", "", "titulo"),
                ("Tubería comercial", "NPS", boq.nps, ""),
                ("Ø interior", "D_i", f"{boq.D_i*1000:,.1f}", "mm"),
                ("Espesor", "t_n", f"{boq.espesor*1000:,.2f}", "mm"),
                ("Velocidad real", "V", f"{boq.V_real:.2f}", "m/s",
                 "" if boq.V_real <= boq.V_max else "alerta"),
            ]
        llenar_tabla(self.tbl_mecanico, filas)

    # --------------------------------------------------------------- dibujos
    def _datos_tipos(self) -> Dict[str, object]:
        """Solo los tipos TEMA elegidos (para el catálogo, sin calcular)."""
        try:
            d = self.form.leer()
        except CampoInvalido:
            return {}
        return {"tipo_carcasa": d["tipo_carcasa"],
                "cab_frontal": d["cab_frontal"],
                "cab_trasero": d["cab_trasero"]}

    def _datos_dibujo(self) -> Dict[str, object]:
        """Empaqueta las cotas calculadas para drawings.py."""
        m, t = self.res_mecanico, self.res_termico
        if m is None or t is None:
            return {}
        try:
            d = self.form.leer()
        except CampoInvalido:
            return {}
        boq = (lambda b: None if b is None else
               {"nps": b.nps, "D_i": b.D_i, "D_e": b.D_e,
                "espesor": b.espesor, "V_real": b.V_real, "V_max": b.V_max})
        N_tt = t.N_tt if self.modo == "sizing" else int(d["n_tt"])
        return {
            "D_s": m.D_s, "D_o": m.D_o, "L": d["long_m"], "L_ts": m.L_ts,
            "L_total": m.L_total, "D_otl": m.D_otl, "D_ctl": m.D_ctl,
            "T_c": m.T_c, "tipo_cubierta": m.tipo_cubierta,
            "T_c_tras": m.cab_trasero.T_c,
            "tipo_cubierta_tras": m.cab_trasero.tipo_cubierta,
            "desc_cab_frontal": m.cab_frontal.descripcion,
            "desc_cab_trasero": m.cab_trasero.descripcion,
            "desc_carcasa": ctrl.desc_carcasa(d["tipo_carcasa"]),
            "N_B": m.baffles.N_B, "L_bc": m.baffles.L_bc,
            "L_bi": m.baffles.L_bi, "e_baffle": m.baffles.espesor,
            "D_baffle": m.baffles.D_baffle,
            "altura_corte": m.baffles.altura_corte,
            "luz_sin_soporte": m.baffles.luz_sin_soporte,
            "f_w": m.brida.f_w, "D_F": m.brida.D_F, "D_BC": m.brida.D_BC,
            "n_pernos": m.brida.n_pernos, "d_perno": m.brida.d_perno,
            "tie_rods": {"cantidad": m.tie_rods.cantidad, "d": m.tie_rods.d},
            "boq_s": boq(m.boquilla_coraza), "boq_t": boq(m.boquilla_tubos),
            "N_tt": N_tt, "d_o": d["d_o_mm"] / 1000.0,
            "P_T": d["pitch_mm"] / 1000.0, "corte": d["corte_pct"] / 100.0,
            "layout": ctrl.LAYOUTS[d["layout"]], "n_pasos": int(d["n_pasos"]),
            "tipo_carcasa": d["tipo_carcasa"], "material": d["mat_carcasa"],
            "cab_frontal": d["cab_frontal"], "cab_trasero": d["cab_trasero"],
        }

    def _al_redimensionar_canvas(self, _evento=None) -> None:
        """Coalesa los <Configure>: se pinta UNA vez al terminar de arrastrar.

        Sin esto, estirar la ventana dispara cientos de redibujados completos
        (con ~900 tubos cada uno) y el arrastre da tirones.
        """
        if self._job_redibujo is not None:
            self.after_cancel(self._job_redibujo)
        self._job_redibujo = self.after(120, self._redibujar_suave)

    def _redibujar_suave(self) -> None:
        self._job_redibujo = None
        tam = (self.canvas.winfo_width(), self.canvas.winfo_height())
        if tam == self._ultimo_tamano:
            return                       # el tamaño no cambió: no repintar
        self._redibujar()

    def _al_mover_sobre_canvas(self, evento) -> None:
        """Cursor de mano sobre las piezas clicables (con throttle)."""
        ahora = time.monotonic()
        if ahora - self._ultimo_chequeo_cursor < 0.06:
            return
        self._ultimo_chequeo_cursor = ahora
        cursor = ""
        if self.cotas:
            item = self.canvas.find_closest(
                self.canvas.canvasx(evento.x), self.canvas.canvasy(evento.y))
            if item and any(t in self.cotas
                            for t in self.canvas.gettags(item[0])):
                cursor = "hand2"
        if cursor != self._cursor_canvas:
            self._cursor_canvas = cursor
            self.canvas.configure(cursor=cursor)

    def _redibujar(self) -> None:
        funcion = drawings.VISTAS.get(self.var_vista.get())
        if funcion is None:
            return
        datos = self._datos_dibujo()
        if not datos and funcion is drawings.dibujar_catalogo_tema:
            datos = self._datos_tipos()   # el catálogo no necesita resultados
        try:
            self.cotas = funcion(self.canvas, datos)
        except Exception as exc:                      # nunca tumbar la GUI
            self.canvas.delete("all")
            self.canvas.create_text(20, 20, anchor="nw", fill="#a33",
                                    text=f"No se pudo generar el dibujo:\n{exc}")
            self.cotas = {}
        self._ultimo_tamano = (self.canvas.winfo_width(),
                               self.canvas.winfo_height())

    def _ir_a_vista(self, nombre: str) -> None:
        self.var_vista.set(nombre)
        self.nb.select(2)
        self._redibujar()

    def _clic_dibujo(self, evento) -> None:
        if not self.cotas:
            return
        item = self.canvas.find_closest(
            self.canvas.canvasx(evento.x), self.canvas.canvasy(evento.y))
        if not item:
            return
        for tag in self.canvas.gettags(item[0]):
            if tag in self.cotas:
                messagebox.showinfo("Cotas de fabricación", self.cotas[tag])
                return

    # --------------------------------------------------------------- archivo
    def _nuevo(self) -> None:
        self._restaurar_defecto()
        self.res_termico = self.res_mecanico = None
        self.modo, self.ruta_actual = "", None
        self.ultimo_D_s = None
        for tabla in (self.tbl_termico, self.tbl_hidraulico, self.tbl_mecanico):
            tabla.delete(*tabla.get_children())
        self.lbl_modo.configure(text="Sin resultados todavía")
        self._render_advertencias([])
        self._redibujar()
        self.title(TITULO)
        self.estado.set("Proyecto nuevo con el caso base cargado.")

    def _abrir(self) -> None:
        ruta = filedialog.askopenfilename(
            title="Abrir proyecto", defaultextension=io_state.EXTENSION,
            filetypes=io_state.TIPOS_ARCHIVO)
        if not ruta:
            return

        def accion():
            self.form.cargar(io_state.abrir(ruta))
            self.ruta_actual = ruta
            self._actualizar_limites()
            self._actualizar_designacion_tema()
            self.title(f"{TITULO}  —  {os.path.basename(ruta)}")
            self.nb.select(0)
            self.estado.set(f"Proyecto abierto: {ruta}. Pulse F5 para "
                            f"recalcular.")
        self._blindar(accion, "Apertura de archivo")

    def _guardar(self) -> None:
        if not self.ruta_actual:
            return self._guardar_como()
        self._escribir(self.ruta_actual)

    def _guardar_como(self) -> None:
        ruta = filedialog.asksaveasfilename(
            title="Guardar proyecto", defaultextension=io_state.EXTENSION,
            filetypes=io_state.TIPOS_ARCHIVO)
        if ruta:
            self._escribir(ruta)

    def _escribir(self, ruta: str) -> None:
        def accion():
            datos = {k: c.var.get() for k, c in self.form.campos.items()}
            io_state.guardar(ruta, datos)
            self.ruta_actual = ruta
            self.title(f"{TITULO}  —  {os.path.basename(ruta)}")
            self.estado.set(f"Proyecto guardado en {ruta}")
        self._blindar(accion, "Guardado de archivo")

    def _salir(self) -> None:
        if messagebox.askokcancel("Salir", "¿Cerrar la aplicación?\n"
                                           "Los datos no guardados se perderán."):
            self.destroy()

    def _acerca_de(self) -> None:
        messagebox.showinfo(
            "Acerca de",
            "Intercambiador de Tubos y Coraza\n"
            "Software educativo de diseño de intercambiadores de calor\n"
            "de tubos y coraza.\n\n"
            "• Térmico: Kern (LMTD + factor F) y Bell-Delaware opcional\n"
            "  en el lado coraza (factores Jc, Jl, Jb, Jr).\n"
            "• Mecánico: estándar TEMA Clase C.\n"
            "• Base termofísica propia (10 fluidos, 5 materiales).\n\n"
            f"• Huella de autenticidad: {marca.huella()}\n\n"
            "© 2026 Diego Nicolás Bohórquez Barón\n"
            "Todos los derechos reservados.\n"
            "Prohibida la copia o presentación de este trabajo, total o\n"
            "parcialmente, sin atribución expresa a su autor.\n\n"
            "Interfaz inspirada en Tan & Fok (2006). Condiciones de uso\n"
            "completas en el archivo LICENSE.txt.")


AYUDA = [
    ("1. Flujo de trabajo",
     "Pestaña Design → complete corrientes y geometría → F5 «Dimensionar» → "
     "los resultados aparecen en Analysis y los planos en Drawing."),
    ("2. Sizing vs. Rating",
     "Sizing (F5): usted fija la geometría del tubo y el programa itera sobre "
     "el coeficiente global U hasta hallar el área, el número de tubos y el "
     "diámetro de coraza necesarios.\n"
     "Rating (F6): usted ya tiene un equipo (N_tt y D_s conocidos) y el "
     "programa itera sobre las temperaturas de salida para predecir cuánto "
     "calor transfiere realmente."),
    ("3. La regla de la temperatura vacía",
     "El balance de energía necesita exactamente una incógnita. Si conoce las "
     "dos temperaturas del lado caliente, deje vacía la salida del lado frío "
     "(o viceversa). Si llena las cuatro, el problema queda "
     "sobre-especificado y el programa lo advertirá."),
    ("4. Lectura de las ventanas recomendadas",
     f"Lado tubos: {ctrl.V_TUBO_MIN} – {ctrl.V_TUBO_MAX} m/s. Lado coraza: "
     f"{ctrl.V_CORAZA_MIN} – {ctrl.V_CORAZA_MAX} m/s. Por debajo hay "
     "ensuciamiento; por encima, erosión y vibración. Los valores fuera de "
     "rango se resaltan en ámbar en la tabla hidráulica.\n"
     f"Factor F: por debajo de {ctrl.F_MIN_ACEPTABLE} el arreglo 1-n es "
     "inadmisible; use más pasos por coraza."),
    ("5. Pitch y layout",
     "TEMA exige P_T ≥ 1.25·d_o. El arreglo triangular (30°/60°) da más área "
     "por unidad de volumen; el cuadrado (45°/90°) permite limpieza mecánica "
     "externa, obligatorio con fluidos muy sucios del lado coraza."),
    ("6. Espaciado de baffles",
     "Buena práctica: 0.3·D_s ≤ B ≤ 1.0·D_s. Un B pequeño sube el coeficiente "
     "de coraza pero dispara la caída de presión."),
    ("7. Dibujos acotados y catálogo TEMA",
     "En la pestaña Drawing elija entre cinco vistas paramétricas. Las vistas "
     "1 y 4 dibujan el corte longitudinal y el cabezal con el diagrama "
     "correspondiente al TIPO TEMA elegido (A/B/C/D/N en el frontal, "
     "E/F/G/H/J/K/X en la coraza, L/M/N/P/S/T/U/W en el trasero). La vista 5 "
     "muestra el catálogo completo de la Fig. N-1.2 del estándar TEMA con su "
     "selección resaltada. Haga clic sobre cualquier pieza para abrir una "
     "ventana con sus cotas exactas en milímetros."),
    ("8. Archivos .bb",
     "File → Guardar almacena únicamente los datos de entrada en formato "
     "JSON. Al abrir un proyecto debe recalcular con F5: así los resultados "
     "nunca quedan desactualizados respecto del motor de cálculo."),
    ("9. Mensajes de alerta",
     "Un pop-up de «Revisión de ingeniería» significa que el modelo físico o "
     "la norma TEMA rechazó los datos. Cada mensaje responde cuatro "
     "preguntas: QUÉ PASÓ (el hecho con números), POR QUÉ (el principio "
     "físico o la norma), CÓMO LO SOLUCIONO (la acción sobre el formulario) y "
     "la REFERENCIA. No es un error del programa: es una lección de "
     "termodinámica. Corrija la entrada y recalcule."),
    ("10. Ventanas de temperatura de los fluidos",
     "Cada fluido tiene una ventana de validez (visible bajo su menú "
     "desplegable). El programa valida TODOS los puntos de temperatura "
     "(entradas y salidas), no solo la media: por ejemplo, etanol a 95 °C se "
     "rechaza aunque su media quede dentro del rango. El agua líquida está "
     "limitada a 100 °C (su ebullición a 1 atm): el modelo es monofásico y no "
     "cubre servicios presurizados ni vaporización. Excepción: metanol, "
     "aceptado hasta 100 °C como líquido presurizado, tal como trabajan los "
     "ejercicios de referencia de la literatura."),
    ("11. Régimen de flujo e incertidumbre",
     "El lado coraza puede calcularse con Kern (clásico) o con Bell-Delaware "
     "(factores Jc, Jl, Jb y Jr sobre el banco ideal; más riguroso). "
     "Las correlaciones cubren los tres regímenes: Hausen (1959) para "
     "laminar en tubos, Gnielinski (1976) para transición y turbulento "
     "(con respaldo de Dittus-Boelter), y en coraza el método de Kern con "
     "corrección de Graetz en laminar. En los intervalos de empalme "
     "(2100-2400 en tubos, 100-2000 en coraza) se mezclan ambas "
     "correlaciones de forma continua. La banda de incertidumbre estimada "
     "sobre U es ±15 % en turbulento, ±20 % en transición y ±25 % en "
     "laminar; la banda la fija el lado más incierto, y si la coraza se "
     "calcula con Bell-Delaware su aporte baja (±12/15/20 %), de modo que "
     "en laminar suele quedar fijada por el lado tubos. En los regímenes "
     "no turbulentos contraste el resultado con datos de servicio, ε-NTU "
     "o literatura antes de fabricar."),
    ("12. Método de coraza: Kern y Bell-Delaware",
     "En Design, el campo «Método coraza» elige cómo se calcula el lado "
     "coraza. «Automático» (recomendado) aplica Bell-Delaware mientras el "
     "Reynolds de coraza esté cubierto por la tabla de Taborek (1–1e6) y "
     "vuelve a Kern fuera de ese rango; el método realmente usado queda "
     "registrado en el resultado y en el proyecto .bb. Kern usa las "
     "correlaciones clásicas del capítulo 7 (LMTD con factor F). Bell-Delaware descompone el flujo del banco en "
     "cinco corrientes (cruzado ideal, fugas deflector-coraza y "
     "deflector-tubo, bypass haz-coraza y partición de paso) y corrige el "
     "banco ideal con los factores Jc, Jl, Jb y Jr; la caída de presión se "
     "calcula en tres componentes (cruzado, ventana y extremos). Ambos "
     "métodos son monofásicos: no cubren condensación ni ebullición. El "
     "método elegido se guarda dentro del proyecto .bb, así que al abrir "
     "un archivo se recupera exactamente con el que se calculó. En los "
     "ejemplos de la literatura, Bell-Delaware da h_o entre 0,87 y 1,11 "
     "veces el de Kern y caídas de presión entre 30 y 60 % menores; en el "
     "caso de Tan y Fok acerca el resultado al artículo publicado "
     "(U 433 frente a 447 W/m2K)."),
]


def main() -> None:
    Aplicacion().mainloop()


if __name__ == "__main__":
    main()
