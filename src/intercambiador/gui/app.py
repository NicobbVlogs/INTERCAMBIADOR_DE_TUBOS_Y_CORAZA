# -*- coding: utf-8 -*-
"""
app.py - Ventana principal del software educativo de intercambiadores
         de tubos y coraza (Método de Kern / estándar TEMA Clase C).

Arquitectura MVC estricta:
    VISTA        -> este archivo + widgets.py + drawings.py
    CONTROLADOR  -> controller.py
    MODELO       -> intercambiador.core / .thermo / .mechanical

Esta capa NO calcula física: captura datos, delega y renderiza. Todo
`ValueError` que suba desde el modelo se atrapa y se convierte en un pop-up
educativo, sin cerrar la aplicación.

Ejecución:  uv run intercambiador   (o: uv run python -m intercambiador)
"""
from __future__ import annotations

import os
import traceback
import tkinter as tk
from importlib.resources import files
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, Optional

from intercambiador.gui import controller as ctrl
from intercambiador.gui import drawings, io_state
from intercambiador.gui.widgets import (COLOR_FONDO, COLOR_TITULO, CampoInvalido,
                                        CampoLista, CampoNumerico, Formulario,
                                        MarcoScroll, llenar_tabla,
                                        tabla_resultados)

TITULO = "Intercambiador de Tubos y Coraza · Método de Kern / TEMA"
# Proyectos .he de ejemplo, empaquetados junto al código (intercambiador/ejemplos).
DIR_EJEMPLOS = str(files("intercambiador") / "ejemplos")

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
    "cab_frontal": "A", "cab_trasero": "M",
    "p_coraza_bar": 10.0, "p_tubos_bar": 10.0,
    "mat_carcasa": "Acero al carbono", "corrosion_mm": 3.2, "d_perno_mm": 19.05,
    "n_tt": 500, "d_s_mm": 630.0,
}


class Aplicacion(tk.Tk):
    # ------------------------------------------------------------------ init
    def __init__(self) -> None:
        super().__init__()
        self.title(TITULO)
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

        self._estilo()
        self._crear_menu()

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self._tab_design()
        self._tab_analysis()
        self._tab_drawing()
        self._tab_help()

        self.estado = tk.StringVar(value="Listo. Complete los datos y pulse "
                                         "«Dimensionar (Sizing)».")
        ttk.Label(self, textvariable=self.estado, relief="sunken",
                  anchor="w", padding=(8, 3)).pack(fill="x", padx=8, pady=(0, 8))

        self._restaurar_defecto()
        self.protocol("WM_DELETE_WINDOW", self._salir)

        if not ctrl.MODULOS_OK:
            self.after(300, lambda: messagebox.showerror(
                "Módulos de cálculo no disponibles",
                "La interfaz se abrió, pero no pudo importar los módulos de "
                "cálculo:\n\n" + ctrl.ERROR_IMPORT))

    def _estilo(self) -> None:
        estilo = ttk.Style(self)
        if "clam" in estilo.theme_names():
            estilo.theme_use("clam")
        estilo.configure(".", background=COLOR_FONDO, font=("Segoe UI", 9))
        estilo.configure("TNotebook.Tab", padding=(16, 7),
                         font=("Segoe UI", 9, "bold"))
        estilo.configure("TLabelframe", background=COLOR_FONDO, borderwidth=1)
        estilo.configure("TLabelframe.Label", foreground=COLOR_TITULO,
                         font=("Segoe UI", 9, "bold"))
        estilo.configure("Accion.TButton", font=("Segoe UI", 9, "bold"),
                         padding=(12, 7))
        estilo.configure("Treeview", rowheight=21, fieldbackground="white")
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))
        estilo.configure("Titulo.TLabel", foreground=COLOR_TITULO,
                         font=("Segoe UI", 13, "bold"))
        estilo.configure("Nota.TLabel", foreground="#5a6b7b",
                         font=("Segoe UI", 8))

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
                         command=self._calcular_sizing)
        m_an.add_command(label="Evaluar equipo (Rating)  ·  F6",
                         command=self._calcular_rating)
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
        self.bind("<F5>", lambda e: self._calcular_sizing())
        self.bind("<F6>", lambda e: self._calcular_rating())

    def _menu_ejemplos(self, padre) -> tk.Menu:
        """Submenú con los proyectos .he verificados que acompañan al programa."""
        menu = tk.Menu(padre, tearoff=0)
        try:
            archivos = sorted(a for a in os.listdir(DIR_EJEMPLOS)
                              if a.endswith(io_state.EXTENSION))
        except OSError:
            archivos = []
        if not archivos:
            menu.add_command(label="(no se encontró la carpeta «ejemplos»)",
                             state="disabled")
            return menu
        for archivo in archivos:
            ruta = os.path.join(DIR_EJEMPLOS, archivo)
            etiqueta = io_state.descripcion_de(ruta) or archivo
            menu.add_command(label=etiqueta,
                             command=lambda r=ruta: self._cargar_ejemplo(r))
        return menu

    def _cargar_ejemplo(self, ruta: str) -> None:
        """Carga un ejemplo y lo calcula de inmediato (demostración directa)."""
        def accion():
            self.form.cargar(io_state.abrir(ruta))
            self.ruta_actual = None        # evita sobrescribir el ejemplo
            self._actualizar_limites()
            self.title(f"{TITULO}  —  {os.path.basename(ruta)}")
        self._blindar(accion, "Apertura del ejemplo")
        self._calcular_sizing()

    # =================================================================== tabs
    def _tab_design(self) -> None:
        contenedor = MarcoScroll(self.nb)
        self.nb.add(contenedor, text="  Design  ")
        raiz = contenedor.interior
        raiz.columnconfigure(0, weight=1, uniform="col")
        raiz.columnconfigure(1, weight=1, uniform="col")

        ttk.Label(raiz, text="Hoja de diseño térmico y mecánico",
                  style="Titulo.TLabel").grid(row=0, column=0, columnspan=2,
                                              sticky="w", padx=6, pady=(8, 2))
        ttk.Label(raiz, style="Nota.TLabel", text=(
            "Deje VACÍA una de las dos temperaturas de salida: es la incógnita "
            "que resuelve el balance de energía q = m·cp·ΔT.")
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 6))

        self._bloque_corrientes(raiz, fila=2)
        self._bloque_tubos(raiz, fila=3)
        self._bloque_coraza(raiz, fila=4)
        self._bloque_mecanico(raiz, fila=5)
        self._bloque_botones(raiz, fila=6)

    # ---------------------------------------------------------- bloques UI
    def _marco(self, padre, titulo: str, fila: int, columna: int,
               colspan: int = 1) -> ttk.LabelFrame:
        marco = ttk.LabelFrame(padre, text=titulo, padding=(8, 6))
        marco.grid(row=fila, column=columna, columnspan=colspan, sticky="nsew",
                   padx=6, pady=5)
        marco.columnconfigure(1, weight=1)
        return marco

    def _bloque_corrientes(self, padre, fila: int) -> None:
        f = self.form
        fluidos = ctrl.fluidos()

        cal = self._marco(padre, "Corriente CALIENTE", fila, 0)
        f.add("fluido_cal", CampoLista(
            cal, 0, "Fluido", fluidos, ayuda="Base de datos termofísica de "
            "alta fidelidad (intercambiador.core).", comando=self._actualizar_limites))
        self.lbl_lim_cal = ttk.Label(cal, style="Nota.TLabel", text="")
        self.lbl_lim_cal.grid(row=1, column=0, columnspan=3, sticky="w", padx=6)
        f.add("m_cal", CampoNumerico(cal, 2, "Caudal másico", "kg/s",
                                     minimo=1e-6, grupo="corriente caliente",
                                     ayuda="ṁ del lado caliente."))
        f.add("tin_cal", CampoNumerico(cal, 3, "T entrada", "°C",
                                       grupo="corriente caliente"))
        f.add("tout_cal", CampoNumerico(
            cal, 4, "T salida", "°C", opcional=True, grupo="corriente caliente",
            ayuda="Opcional: deje vacío si es la incógnita del balance."))

        fri = self._marco(padre, "Corriente FRÍA", fila, 1)
        f.add("fluido_fri", CampoLista(
            fri, 0, "Fluido", fluidos, valor="Agua",
            comando=self._actualizar_limites))
        self.lbl_lim_fri = ttk.Label(fri, style="Nota.TLabel", text="")
        self.lbl_lim_fri.grid(row=1, column=0, columnspan=3, sticky="w", padx=6)
        f.add("m_fri", CampoNumerico(fri, 2, "Caudal másico", "kg/s",
                                     minimo=1e-6, grupo="corriente fría"))
        f.add("tin_fri", CampoNumerico(fri, 3, "T entrada", "°C",
                                       grupo="corriente fría"))
        f.add("tout_fri", CampoNumerico(fri, 4, "T salida", "°C",
                                        opcional=True, grupo="corriente fría"))

    def _bloque_tubos(self, padre, fila: int) -> None:
        f = self.form
        m = self._marco(padre, "Haz de tubos", fila, 0)
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
        m = self._marco(padre, "Coraza, deflectores y cálculo", fila, 1)
        f.add("tipo_carcasa", CampoLista(m, 0, "Carcasa TEMA",
                                         ctrl.TIPOS_CARCASA, valor="E",
                                         ayuda="E = un paso por coraza."))
        f.add("cab_frontal", CampoLista(m, 1, "Cabezal frontal",
                                        ctrl.CABEZAL_FRONTAL, valor="A"))
        f.add("cab_trasero", CampoLista(m, 2, "Cabezal trasero",
                                        ctrl.CABEZAL_TRASERO, valor="M"))
        f.add("baffle_mm", CampoNumerico(
            m, 3, "Espaciado de baffles B", "mm", minimo=10.0,
            ayuda="Buena práctica: 0.3·D_s ≤ B ≤ 1.0·D_s. Como D_s es un "
                  "RESULTADO del sizing, B se ajusta iterando: use el botón "
                  "«½·D_s» tras el primer cálculo."))
        # B es dato de entrada del térmico pero su ventana válida depende de
        # D_s, que es resultado: este botón cierra el lazo a mano, sin que la
        # GUI calcule nada.
        ttk.Button(m, text="½·D_s", width=6, command=self._ajustar_baffle
                   ).grid(row=3, column=3, padx=(0, 6))
        f.add("corte_pct", CampoNumerico(m, 4, "Corte de baffle", "%",
                                         minimo=15.0, maximo=45.0,
                                         ayuda="Estándar: 25 %."))
        f.add("u_inicial", CampoNumerico(
            m, 5, "U inicial (semilla)", "W/m²K", minimo=10.0, maximo=10000.0,
            ayuda="Solo es la semilla de la iteración de Kern; no altera el "
                  "resultado convergido."))

        ttk.Separator(m, orient="horizontal").grid(
            row=6, column=0, columnspan=3, sticky="ew", pady=6)
        ttk.Label(m, text="Equipo existente (solo para Rating)",
                  style="Nota.TLabel").grid(row=7, column=0, columnspan=3,
                                            sticky="w", padx=6)
        f.add("n_tt", CampoNumerico(m, 8, "N.º total de tubos", "–",
                                    minimo=1, entero=True))
        f.add("d_s_mm", CampoNumerico(m, 9, "Ø interior de coraza", "mm",
                                      minimo=50.0))

    def _bloque_mecanico(self, padre, fila: int) -> None:
        f = self.form
        m = self._marco(padre, "Diseño mecánico (TEMA Clase C)", fila, 0, 2)
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
        ttk.Button(barra, text="▶  Dimensionar (Sizing)  F5",
                   style="Accion.TButton",
                   command=self._calcular_sizing).pack(side="left", padx=(0, 8))
        ttk.Button(barra, text="◆  Evaluar equipo (Rating)  F6",
                   style="Accion.TButton",
                   command=self._calcular_rating).pack(side="left", padx=8)
        ttk.Button(barra, text="Restaurar caso base",
                   command=self._restaurar_defecto).pack(side="right")

    # ------------------------------------------------------------- analysis
    def _tab_analysis(self) -> None:
        marco = ttk.Frame(self.nb, padding=8)
        self.nb.add(marco, text="  Analysis  ")
        marco.columnconfigure(0, weight=3, uniform="an")
        marco.columnconfigure(1, weight=2, uniform="an")
        marco.rowconfigure(1, weight=1)

        self.lbl_modo = ttk.Label(marco, text="Sin resultados todavía",
                                  style="Titulo.TLabel")
        self.lbl_modo.grid(row=0, column=0, columnspan=2, sticky="w",
                           pady=(0, 6))

        izq = ttk.LabelFrame(marco, text="Thermal Design", padding=(6, 4))
        izq.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        izq.rowconfigure(0, weight=1)
        izq.columnconfigure(0, weight=1)
        self.tbl_termico = tabla_resultados(izq, altura=18)
        self.tbl_termico.grid(row=0, column=0, sticky="nsew")

        der = ttk.Frame(marco)
        der.grid(row=1, column=1, sticky="nsew")
        der.rowconfigure(0, weight=3)
        der.rowconfigure(1, weight=2)
        der.columnconfigure(0, weight=1)

        hid = ttk.LabelFrame(der, text="Hydraulic Design", padding=(6, 4))
        hid.grid(row=0, column=0, sticky="nsew")
        hid.rowconfigure(0, weight=1)
        hid.columnconfigure(0, weight=1)
        self.tbl_hidraulico = tabla_resultados(hid, altura=9)
        self.tbl_hidraulico.grid(row=0, column=0, sticky="nsew")
        ttk.Label(hid, style="Nota.TLabel", wraplength=330, text=(
            "Caídas de presión Δp (tubos y coraza) reservadas para una versión "
            "futura. Las velocidades y Reynolds mostrados permiten verificar "
            "las ventanas recomendadas por TEMA/Kern.")
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        adv = ttk.LabelFrame(der, text="Advertencias y notas educativas",
                             padding=(6, 4))
        adv.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        adv.rowconfigure(0, weight=1)
        adv.columnconfigure(0, weight=1)
        self.txt_adv = tk.Text(adv, height=7, wrap="word", relief="solid",
                               bd=1, font=("Segoe UI", 9), bg="white")
        self.txt_adv.grid(row=0, column=0, sticky="nsew")
        self.txt_adv.configure(state="disabled")

    # -------------------------------------------------------------- drawing
    def _tab_drawing(self) -> None:
        marco = ttk.Frame(self.nb, padding=8)
        self.nb.add(marco, text="  Drawing  ")
        marco.columnconfigure(0, weight=3)
        marco.columnconfigure(1, weight=1)
        marco.rowconfigure(1, weight=1)

        cab = ttk.Frame(marco)
        cab.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ttk.Label(cab, text="Vista:").pack(side="left", padx=(2, 6))
        self.var_vista = tk.StringVar(value=list(drawings.VISTAS)[0])
        combo = ttk.Combobox(cab, textvariable=self.var_vista, width=32,
                             state="readonly", values=list(drawings.VISTAS))
        combo.pack(side="left")
        combo.bind("<<ComboboxSelected>>", lambda e: self._redibujar())
        ttk.Button(cab, text="Redibujar", command=self._redibujar).pack(
            side="left", padx=8)
        ttk.Label(cab, style="Nota.TLabel",
                  text="Dibujos paramétricos: se generan desde las cotas "
                       "calculadas en intercambiador.mechanical.").pack(side="left",
                                                             padx=10)

        self.canvas = tk.Canvas(marco, bg="white", width=760, height=470,
                                relief="solid", bd=1, highlightthickness=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        self.canvas.bind("<Button-1>", self._clic_dibujo)
        self.canvas.bind("<Configure>", lambda e: self._redibujar())

        lado = ttk.LabelFrame(marco, text="Dimensiones de fabricación",
                              padding=(6, 4))
        lado.grid(row=1, column=1, sticky="nsew")
        lado.rowconfigure(0, weight=1)
        lado.columnconfigure(0, weight=1)
        self.tbl_mecanico = tabla_resultados(lado, altura=22)
        self.tbl_mecanico.grid(row=0, column=0, sticky="nsew")
        ttk.Label(lado, style="Nota.TLabel", wraplength=300,
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
                      font=("Segoe UI", 10), bg="white", padx=14, pady=12)
        barra = ttk.Scrollbar(marco, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=barra.set)
        txt.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")

        txt.tag_configure("h1", font=("Segoe UI", 13, "bold"),
                          foreground=COLOR_TITULO, spacing3=8)
        txt.tag_configure("h2", font=("Segoe UI", 10, "bold"),
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
        except CampoInvalido as exc:
            messagebox.showwarning("Formulario incompleto", str(exc))
            self.estado.set("Formulario incompleto: revise los campos en rojo.")
        except ValueError as exc:
            messagebox.showwarning(
                f"{titulo} · revisión de ingeniería",
                f"{exc}\n\n— Corrija los datos de entrada y vuelva a calcular.")
            self.estado.set("Cálculo detenido por una condición física "
                            "inadmisible.")
        except ZeroDivisionError:
            messagebox.showwarning(
                f"{titulo} · división por cero",
                "Un dato geométrico o un caudal es nulo. Verifique que ningún "
                "campo valga 0.")
        except Exception as exc:                      # red de seguridad final
            messagebox.showerror(
                "Error inesperado",
                f"{type(exc).__name__}: {exc}\n\n"
                f"{traceback.format_exc(limit=3)}")
            self.estado.set("Error inesperado; la aplicación sigue activa.")

    # ------------------------------------------------------------- cálculos
    def _calcular_sizing(self) -> None:
        self._blindar(self._sizing, "Dimensionamiento")

    def _sizing(self) -> None:
        datos = self.form.leer()
        res = ctrl.correr_sizing(datos)
        self.res_termico, self.modo = res, "sizing"
        self.ultimo_D_s = res.D_s
        self.form.campos["n_tt"].set(res.N_tt)
        self.form.campos["d_s_mm"].set(round(res.D_s * 1000.0, 1))
        self._render_sizing(res)
        self._mecanico(datos, res.D_s, res.N_tt, res.T_h_out, res.T_c_out)
        self.nb.select(1)
        self.estado.set(
            f"Sizing convergido en {res.iteraciones} iteraciones · "
            f"U = {res.U:.1f} W/m²K · A = {res.A:.2f} m² · "
            f"{res.N_tt} tubos · D_s = {res.D_s*1000:.0f} mm")
        self._avisar_advertencias(res.advertencias)

    def _calcular_rating(self) -> None:
        self._blindar(self._rating, "Evaluación (Rating)")

    def _rating(self) -> None:
        datos = self.form.leer()
        res = ctrl.correr_rating(datos)
        self.res_termico, self.modo = res, "rating"
        self.ultimo_D_s = datos["d_s_mm"] / 1000.0
        self._render_rating(res)
        self._mecanico(datos, datos["d_s_mm"] / 1000.0, int(datos["n_tt"]),
                       res.T_h_out, res.T_c_out)
        self.nb.select(1)
        self.estado.set(
            f"Rating convergido en {res.iteraciones} iteraciones · "
            f"q = {res.q/1000:.1f} kW · ε = {res.efectividad*100:.1f} % · "
            f"T_h,out = {res.T_h_out:.1f} °C · T_c,out = {res.T_c_out:.1f} °C")
        self._avisar_advertencias(res.advertencias)

    def _mecanico(self, datos: Dict[str, Any], D_s: float, N_tt: int,
                  T_h_out: float, T_c_out: float) -> None:
        """El fallo mecánico no debe invalidar el resultado térmico."""
        try:
            T_m_cal = 0.5 * (datos["tin_cal"] + T_h_out)
            T_m_fri = 0.5 * (datos["tin_fri"] + T_c_out)
            self.res_mecanico = ctrl.correr_mecanico(
                datos, D_s, N_tt, T_m_cal, T_m_fri)
            self._render_mecanico(self.res_mecanico)
            self._redibujar()
        except ValueError as exc:
            self.res_mecanico = None
            self._redibujar()
            messagebox.showwarning(
                "Diseño mecánico no completado",
                f"El cálculo térmico sí convergió, pero el dimensionamiento "
                f"mecánico se detuvo:\n\n{exc}")

    def _avisar_advertencias(self, advertencias) -> None:
        if advertencias:
            messagebox.showinfo(
                "Advertencias de buena práctica",
                "El cálculo convergió, pero conviene revisar:\n\n• " +
                "\n\n• ".join(advertencias))

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
        # Los umbrales vienen de intercambiador.thermo.sizing via el controlador.
        llenar_tabla(self.tbl_hidraulico, [
            ("LADO TUBOS", "", "", "", "titulo"),
            ("Velocidad másica media", "v_t", f"{r.v_t:.3f}", "m/s",
             "" if ctrl.V_TUBO_MIN <= r.v_t <= ctrl.V_TUBO_MAX else "alerta"),
            ("Reynolds", "Re_t", f"{r.Re_t:,.0f}", "–"),
            ("Régimen de flujo", "–", r.regimen_tubo, ""),
            ("LADO CORAZA", "", "", "", "titulo"),
            ("Velocidad media", "v_s", f"{r.v_s:.3f}", "m/s",
             "" if ctrl.V_CORAZA_MIN <= r.v_s <= ctrl.V_CORAZA_MAX
             else "alerta"),
            ("Reynolds", "Re_s", f"{r.Re_s:,.0f}", "–"),
            ("Ø equivalente de Kern", "D_e", f"{r.D_e*1000.0:,.2f}", "mm"),
            ("CAÍDA DE PRESIÓN", "", "", "", "titulo"),
            ("Δp lado tubos", "Δp_t", "reservado", "–"),
            ("Δp lado coraza", "Δp_s", "reservado", "–"),
        ])

    def _render_advertencias(self, advertencias) -> None:
        self.txt_adv.configure(state="normal")
        self.txt_adv.delete("1.0", "end")
        if advertencias:
            for i, texto in enumerate(advertencias, 1):
                self.txt_adv.insert("end", f"⚠  {i}. {texto}\n\n")
        else:
            self.txt_adv.insert(
                "end", "✓ Sin advertencias: el diseño respeta las ventanas "
                       "de velocidad, el pitch mínimo y el factor F "
                       "recomendados por TEMA / Kern.")
        self.txt_adv.configure(state="disabled")

    def _render_mecanico(self, m) -> None:
        b, br = m.baffles, m.brida
        filas = [
            ("CARCASA", "", "", "", "titulo"),
            ("Ø interior", "D_s", f"{m.D_s*1000:,.1f}", "mm"),
            ("Espesor de pared", "t_s", f"{m.T_s*1000:,.2f}", "mm"),
            ("Ø exterior", "D_o", f"{m.D_o*1000:,.1f}", "mm"),
            ("Límite exterior del haz", "D_otl", f"{m.D_otl*1000:,.1f}", "mm"),
            ("Ø de centros periféricos", "D_ctl", f"{m.D_ctl*1000:,.1f}", "mm"),
            ("Longitud total", "L_tot", f"{m.L_total:,.3f}", "m"),
            ("ESPEJO Y CABEZAL", "", "", "", "titulo"),
            ("Espesor de espejo", "L_ts", f"{m.L_ts*1000:,.2f}", "mm"),
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
    def _datos_dibujo(self) -> Dict[str, Any]:
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
            "N_B": m.baffles.N_B, "L_bc": m.baffles.L_bc,
            "L_bi": m.baffles.L_bi, "e_baffle": m.baffles.espesor,
            "D_baffle": m.baffles.D_baffle,
            "altura_corte": m.baffles.altura_corte,
            "luz_sin_soporte": m.baffles.luz_sin_soporte,
            "f_w": m.brida.f_w, "D_F": m.brida.D_F, "D_BC": m.brida.D_BC,
            "n_pernos": m.brida.n_pernos, "d_perno": m.brida.d_perno,
            "boq_s": boq(m.boquilla_coraza), "boq_t": boq(m.boquilla_tubos),
            "N_tt": N_tt, "d_o": d["d_o_mm"] / 1000.0,
            "P_T": d["pitch_mm"] / 1000.0, "corte": d["corte_pct"] / 100.0,
            "layout": ctrl.LAYOUTS[d["layout"]], "n_pasos": int(d["n_pasos"]),
            "tipo_carcasa": d["tipo_carcasa"], "material": d["mat_carcasa"],
            "cab_frontal": d["cab_frontal"], "cab_trasero": d["cab_trasero"],
        }

    def _redibujar(self) -> None:
        funcion = drawings.VISTAS.get(self.var_vista.get())
        if funcion is None:
            return
        try:
            self.cotas = funcion(self.canvas, self._datos_dibujo())
        except Exception as exc:                      # nunca tumbar la GUI
            self.canvas.delete("all")
            self.canvas.create_text(20, 20, anchor="nw", fill="#a33",
                                    text=f"No se pudo generar el dibujo:\n{exc}")
            self.cotas = {}

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
            "Software educativo de diseño de intercambiadores de calor\n"
            "de tubos y coraza.\n\n"
            "• Térmico: Método de Kern (LMTD + factor F).\n"
            "• Mecánico: estándar TEMA Clase C.\n"
            "• Base termofísica propia (10 fluidos, 5 materiales).\n\n"
            "Interfaz inspirada en Tan & Fok (2006).")


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
    ("7. Dibujos acotados",
     "En la pestaña Drawing elija entre cuatro vistas paramétricas. Haga clic "
     "sobre cualquier pieza (carcasa, tubos, baffles, boquillas, brida) para "
     "abrir una ventana con sus cotas exactas en milímetros."),
    ("8. Archivos .he",
     "File → Guardar almacena únicamente los datos de entrada en formato "
     "JSON. Al abrir un proyecto debe recalcular con F5: así los resultados "
     "nunca quedan desactualizados respecto del motor de cálculo."),
    ("9. Mensajes de alerta",
     "Un pop-up amarillo significa que el modelo físico rechazó los datos "
     "(cruce de temperaturas, violación de la 2ª Ley, fluido fuera de su "
     "ventana de validez). No es un error del programa: es una lección de "
     "termodinámica. Corrija la entrada y recalcule."),
]


def main() -> None:
    Aplicacion().mainloop()


if __name__ == "__main__":
    main()
