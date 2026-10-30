# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
"""
widgets.py - Controles reutilizables del formulario (capa VISTA).

Responsabilidad unica: capturar y validar *sintacticamente* lo que el usuario
escribe (vacios, no-numericos, rangos fisicos obvios) y resaltar en rojo los
campos problematicos. NO contiene fisica ni termodinamica: la validacion de
ingenieria vive en src/thermo y src/mechanical.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Sequence

import customtkinter as ctk

COLOR_OK = "#ffffff"
COLOR_ERROR = "#ffd1d1"
# --- Paleta de la interfaz: morado, carmesí y naranja (alto contraste) -------
COLOR_FONDO = "#f6f2fb"      # lavanda muy claro (fondo general)
COLOR_TITULO = "#4a148c"     # morado profundo (títulos y rótulos)
COLOR_ACENTO = "#7e57c2"     # morado de acento (secundarios, cabeceras)
COLOR_CARMESI = "#c2185b"    # carmesí (acción principal, selección)
COLOR_CARMESI_CLARO = "#fce4ec"   # fondo de tarjeta seleccionada
COLOR_NARANJA = "#ef6c00"    # naranja (hover, acentos, notas vivas)
COLOR_NARANJA_CLARO = "#fff3e0"   # barra de estado, fondos cálidos
COLOR_SECCION = "#ede7f6"    # morado pálido (filas de sección de tablas)
COLOR_ALTERNA = "#faf7ff"    # filas alternas muy suaves
COLOR_NOTA = "#6d5b95"       # textos secundarios
COLOR_BORDE = "#e4daf2"      # bordes suaves de tarjetas y campos


class CampoInvalido(ValueError):
    """Error de formulario: campos vacios, no numericos o fuera de rango."""


# =============================================================================
# 1. CAMPO NUMERICO
# =============================================================================
class CampoNumerico:
    """Etiqueta + caja de texto numerica + unidad, en una fila de un grid."""

    def __init__(self, parent, fila: int, etiqueta: str, unidad: str = "",
                 valor: object = "", minimo: Optional[float] = None,
                 maximo: Optional[float] = None, opcional: bool = False,
                 entero: bool = False, columna: int = 0, ancho: int = 11,
                 ayuda: str = "", grupo: str = "") -> None:
        # `grupo` desambigua etiquetas repetidas (p. ej. «Caudal másico» en las
        # dos corrientes) dentro de los mensajes de error.
        self.etiqueta = f"{etiqueta} ({grupo})" if grupo else etiqueta
        self.minimo = minimo
        self.maximo = maximo
        self.opcional = opcional
        self.entero = entero
        self.unidad = unidad

        self.var = tk.StringVar(value="" if valor is None else str(valor))

        lbl = rotulo(parent, text=etiqueta,
                     font=("Segoe UI", 12))
        lbl.grid(row=fila, column=columna, sticky="w", padx=(6, 8), pady=3)
        if ayuda:
            Tooltip(lbl, ayuda)

        self._error = False
        self.entry = ctk.CTkEntry(parent, textvariable=self.var,
                                  width=ancho * 8, justify="right",
                                  font=("Segoe UI", 12), fg_color=COLOR_OK,
                                  border_color=COLOR_BORDE, border_width=1)
        self.entry.grid(row=fila, column=columna + 1, sticky="ew", pady=3)

        rotulo(parent, text=unidad, width=9, foreground="#8a6fa8",
               font=("Segoe UI", 12)).grid(
            row=fila, column=columna + 2, sticky="w", padx=(6, 10))

        self.var.trace_add("write", lambda *_: self.limpiar_error())

    # ------------------------------------------------------------- estado
    @property
    def en_error(self) -> bool:
        """True si el campo quedó marcado como inválido."""
        return self._error

    def marcar_error(self) -> None:
        self._error = True
        self.entry.configure(fg_color=COLOR_ERROR,
                             border_color=COLOR_CARMESI)

    def limpiar_error(self) -> None:
        self._error = False
        self.entry.configure(fg_color=COLOR_OK, border_color=COLOR_BORDE)

    def set(self, valor: object) -> bool:
        self.var.set("" if valor is None else str(valor))
        self.limpiar_error()
        return True

    # ------------------------------------------------------------- lectura
    def get(self) -> Optional[float]:
        txt = self.var.get().strip().replace(",", ".")
        if not txt:
            if self.opcional:
                return None
            self.marcar_error()
            raise CampoInvalido(f"• «{self.etiqueta}» está vacío.")
        try:
            valor = float(txt)
        except ValueError:
            self.marcar_error()
            raise CampoInvalido(
                f"• «{self.etiqueta}» no es un número válido: '{txt}'.")
        if self.minimo is not None and valor < self.minimo:
            self.marcar_error()
            raise CampoInvalido(
                f"• «{self.etiqueta}» = {valor:g} {self.unidad}: debe ser "
                f"≥ {self.minimo:g} {self.unidad}.")
        if self.maximo is not None and valor > self.maximo:
            self.marcar_error()
            raise CampoInvalido(
                f"• «{self.etiqueta}» = {valor:g} {self.unidad}: debe ser "
                f"≤ {self.maximo:g} {self.unidad}.")
        return int(round(valor)) if self.entero else valor


# =============================================================================
# 2. CAMPO DE LISTA (previene errores de tipeo)
# =============================================================================
class CampoLista:
    """Etiqueta + Combobox de solo lectura."""

    def __init__(self, parent, fila: int, etiqueta: str,
                 valores: Sequence[str], valor: str = "",
                 columna: int = 0, ancho: int = 24, ayuda: str = "",
                 comando=None) -> None:
        self.etiqueta = etiqueta
        self.var = tk.StringVar(value=valor or (valores[0] if valores else ""))
        self._valores = list(valores)

        lbl = rotulo(parent, text=etiqueta,
                     font=("Segoe UI", 12))
        lbl.grid(row=fila, column=columna, sticky="w", padx=(6, 8), pady=3)
        if ayuda:
            Tooltip(lbl, ayuda)

        self.combo = ctk.CTkComboBox(
            parent, values=self._valores, state="readonly",
            width=ancho * 8, font=("Segoe UI", 12), fg_color=COLOR_OK,
            border_color=COLOR_BORDE, button_color=COLOR_ACENTO,
            button_hover_color=COLOR_CARMESI,
            dropdown_hover_color=COLOR_NARANJA_CLARO,
            command=(lambda _v: comando()) if comando is not None else None)
        self.combo.grid(row=fila, column=columna + 1, columnspan=2,
                        sticky="ew", pady=3, padx=(0, 10))
        # Un clic en el campo (no solo en la flecha) abre el desplegable.
        entrada = getattr(self.combo, "_entry", None)
        if entrada is not None:
            entrada.bind("<Button-1>",
                         lambda e: self._abrir_desplegable())
        if valor:
            self.combo.set(str(valor))
            self.var.set(str(valor))

    def marcar_error(self) -> None:
        pass

    def limpiar_error(self) -> None:
        pass

    def _abrir_desplegable(self) -> None:
        """Abre la lista de opciones al hacer clic sobre el campo."""
        try:
            self.combo._open_dropdown_menu()
        except Exception:      # noqa: BLE001 - nunca romper el formulario
            pass

    def set(self, valor: object) -> bool:
        """Aplica el valor. Devuelve False si no esta entre las opciones.

        Tambien acepta variantes de mayusculas/espacios ('agua', ' Agua ') y
        las normaliza a la opcion canonica: los proyectos .bb se escriben con
        el motor, que es insensible a mayusculas, y deben seguir abriendo.
        Nunca se descarta en silencio: `Formulario.cargar` reune los rechazos
        y los reporta. Aceptar a medias un proyecto dejaria la opcion
        anterior en el combo y produciria resultados de otro caso.
        """
        if valor is None:
            return False
        texto = str(valor).strip()
        canonico = None
        for opcion in self._valores:
            if opcion == texto:
                canonico = opcion
                break
        if canonico is None:
            plegado = texto.casefold()
            for opcion in self._valores:
                if opcion.casefold() == plegado:
                    canonico = opcion
                    break
        if canonico is None:
            return False
        self.combo.set(canonico)
        self.var.set(canonico)
        return True

    def get(self) -> str:
        return self.combo.get()


# =============================================================================
# 3. FORMULARIO (coleccion de campos)
# =============================================================================
class Formulario:
    """Agrupa campos por clave y los lee todos acumulando los errores."""

    def __init__(self) -> None:
        self.campos: Dict[str, object] = {}

    def add(self, clave: str, campo):
        self.campos[clave] = campo
        return campo

    def limpiar_errores(self) -> None:
        for c in self.campos.values():
            c.limpiar_error()

    def leer(self) -> Dict[str, object]:
        """Devuelve {clave: valor}. Marca en rojo TODOS los campos malos."""
        self.limpiar_errores()
        datos: Dict[str, object] = {}
        errores: List[str] = []
        for clave, campo in self.campos.items():
            try:
                datos[clave] = campo.get()
            except CampoInvalido as exc:
                errores.append(str(exc))
        if errores:
            raise CampoInvalido(
                "Revise los campos resaltados en rojo:\n\n" + "\n".join(errores))
        return datos

    def cargar(self, datos: Dict[str, object]) -> None:
        """Vuelca un diccionario en los campos.

        Aplica todo lo aplicable y, si algun valor no corresponde a una opcion
        valida, lanza `CampoInvalido` enumerandolo: asi un archivo .he editado
        a mano o de otra version nunca calcula con datos mezclados.
        """
        rechazados: List[str] = []
        for clave, valor in datos.items():
            campo = self.campos.get(clave)
            if campo is None:
                continue
            if not campo.set(valor):
                rechazados.append(f"• «{campo.etiqueta}»: '{valor}' no es una "
                                  f"opción válida.")
        faltantes = [c for c in self.campos if c not in datos]
        if rechazados:
            raise CampoInvalido(
                "El proyecto contiene valores que esta versión no reconoce, "
                "así que NO se cargaron:\n\n" + "\n".join(rechazados) +
                "\n\nLos campos afectados conservan su valor anterior: "
                "revíselos antes de calcular." +
                (f"\n\nAdemás faltan {len(faltantes)} campos en el archivo."
                 if faltantes else ""))


# =============================================================================
# 4. AUXILIARES DE PRESENTACION
# =============================================================================
# =============================================================================
# 5. ADAPTADORES A CUSTOMTKINTER (aspecto moderno: morado · carmesí · naranja)
# =============================================================================
_MAPA_ETIQUETAS = {
    "Titulo.TLabel": dict(font=("Segoe UI", 16, "bold"),
                          text_color=COLOR_TITULO),
    "Subtitulo.TLabel": dict(font=("Segoe UI", 12), text_color=COLOR_NOTA),
    "Nota.TLabel": dict(font=("Segoe UI", 12), text_color=COLOR_NOTA),
    "Designacion.TLabel": dict(font=("Segoe UI", 12, "bold"),
                               text_color=COLOR_CARMESI),
    "Banner.TLabel": dict(font=("Segoe UI", 16, "bold"), text_color="white",
                          fg_color=COLOR_TITULO),
    "BannerNota.TLabel": dict(font=("Segoe UI", 12), text_color="#ffcc80",
                              fg_color=COLOR_TITULO),
    "Estado.TLabel": dict(font=("Segoe UI", 12, "bold"), text_color="#bf360c",
                          fg_color=COLOR_NARANJA_CLARO),
}
_MAPA_BOTONES = {
    "Accion.TButton": dict(fg_color=COLOR_CARMESI, hover_color=COLOR_NARANJA,
                           text_color="white", font=("Segoe UI", 12, "bold"),
                           height=40, corner_radius=12),
    "Accion2.TButton": dict(fg_color=COLOR_TITULO, hover_color=COLOR_CARMESI,
                            text_color="white", font=("Segoe UI", 12, "bold"),
                            height=40, corner_radius=12),
    "Suave.TButton": dict(fg_color=COLOR_NARANJA_CLARO,
                          hover_color="#ffcc80", text_color="#bf360c",
                          font=("Segoe UI", 12), height=34, corner_radius=10),
    "Mini.TButton": dict(fg_color=COLOR_ACENTO, hover_color=COLOR_CARMESI,
                         text_color="white", font=("Segoe UI", 12, "bold"),
                         height=30, corner_radius=8),
}


def rotulo(parent, **kw):
    """Reemplaza ttk.Label con un CTkLabel de la paleta (moderno)."""
    estilo_nombre = kw.pop("style", None)
    if estilo_nombre and estilo_nombre in _MAPA_ETIQUETAS:
        for k, v in _MAPA_ETIQUETAS[estilo_nombre].items():
            kw.setdefault(k, v)
    if "foreground" in kw:
        kw["text_color"] = kw.pop("foreground")
    if "background" in kw:
        kw["fg_color"] = kw.pop("background")
    if kw.get("width") is not None:
        kw["width"] = int(kw["width"] * 8)      # caracteres -> píxeles
    kw.setdefault("fg_color", "transparent")
    return ctk.CTkLabel(parent, **kw)


def boton(parent, **kw):
    """Reemplaza ttk.Button con un CTkButton redondeado de la paleta."""
    estilo_nombre = kw.pop("style", "Accion.TButton")
    for k, v in _MAPA_BOTONES.get(estilo_nombre, {}).items():
        kw.setdefault(k, v)
    if kw.get("width") is not None:
        kw["width"] = int(kw["width"] * 8)
    kw.pop("state", None)
    return ctk.CTkButton(parent, **kw)


def bloque(parent, text="", padding=(10, 8), **kw):
    """Tarjeta moderna con título; reemplaza ttk.LabelFrame.

    Devuelve el marco interior (donde se ubican los campos). Cuando el código
    hace `.grid(...)` sobre él, se posiciona la tarjeta exterior.
    """
    externo = ctk.CTkFrame(parent, fg_color="white", corner_radius=14,
                           border_width=1, border_color=COLOR_BORDE, **kw)
    ctk.CTkLabel(externo, text=text, font=("Segoe UI", 12, "bold"),
                 text_color=COLOR_TITULO, anchor="w").pack(
        fill="x", padx=14, pady=(10, 2))
    interno = ctk.CTkFrame(externo, fg_color="transparent")
    interno.pack(fill="both", expand=True, padx=2, pady=(0, 6))
    interno.grid = lambda **g: externo.grid(**g)   # el .grid() del código
    return interno


class Tooltip:
    """Globo de ayuda educativa al pasar el cursor."""

    def __init__(self, widget, texto: str) -> None:
        self.widget = widget
        self.texto = texto
        self.ventana = None
        widget.bind("<Enter>", self._mostrar)
        widget.bind("<Leave>", self._ocultar)

    def _mostrar(self, _evt=None) -> None:
        if self.ventana or not self.texto:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.ventana = tk.Toplevel(self.widget)
        self.ventana.wm_overrideredirect(True)
        self.ventana.wm_geometry(f"+{x}+{y}")
        tk.Label(self.ventana, text=self.texto, justify="left",
                 background="#ffffe0", relief="solid", borderwidth=1,
                 font=("Segoe UI", 11), wraplength=320, padx=6, pady=4).pack()

    def _ocultar(self, _evt=None) -> None:
        if self.ventana is not None:
            self.ventana.destroy()
            self.ventana = None


class MarcoScroll(ttk.Frame):
    """Contenedor con barra de desplazamiento vertical.

    Use `.interior` como padre de los widgets hijos.
    """

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, **kw)
        self._canvas = tk.Canvas(self, highlightthickness=0, bg=COLOR_FONDO)
        barra = ttk.Scrollbar(self, orient="vertical",
                              command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=barra.set)

        barra.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self.interior = ttk.Frame(self._canvas)
        self._ventana = self._canvas.create_window(
            (0, 0), window=self.interior, anchor="nw")

        self.interior.bind("<Configure>", self._on_interior)
        self._canvas.bind("<Configure>", self._on_canvas)
        # La rueda se captura solo mientras el cursor esta sobre este marco:
        # con bind_all permanente, girar la rueda sobre el lienzo de dibujos
        # desplazaria la hoja de diseno oculta.
        for w in (self._canvas, self.interior):
            w.bind("<Enter>", lambda e: self._canvas.bind_all(
                "<MouseWheel>", self._on_rueda))
            w.bind("<Leave>", lambda e: self._canvas.unbind_all("<MouseWheel>"))

    def _on_interior(self, _evt) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas(self, evt) -> None:
        self._canvas.itemconfigure(self._ventana, width=evt.width)

    def _on_rueda(self, evt) -> None:
        try:
            self._canvas.yview_scroll(int(-evt.delta / 120), "units")
        except tk.TclError:
            pass


def tabla_resultados(parent, altura: int = 12) -> ttk.Treeview:
    """Treeview de 4 columnas para desplegar resultados de ingenieria."""
    cols = ("param", "simbolo", "valor", "unidad")
    tree = ttk.Treeview(parent, columns=cols, show="headings", height=altura)
    for col, titulo, ancho, anchor in (
            ("param", "Parámetro", 215, "w"),
            ("simbolo", "Símbolo", 62, "center"),
            ("valor", "Valor", 150, "e"),
            ("unidad", "Unidad", 72, "w")):
        tree.heading(col, text=titulo)
        tree.column(col, width=ancho, anchor=anchor, stretch=(col == "param"))
    tree.tag_configure("alerta", background="#fdecc8",
                       foreground="#8a5a00")
    tree.tag_configure("titulo", background=COLOR_SECCION,
                       foreground=COLOR_TITULO,
                       font=("Segoe UI", 12, "bold"))
    tree.tag_configure("alterna", background=COLOR_ALTERNA)
    tree.tag_configure("ok", background="#e9f7e6", foreground="#2f6b24")
    return tree


def llenar_tabla(tree: ttk.Treeview, filas: Sequence[Sequence[object]]) -> None:
    """filas = [(param, simbolo, valor, unidad[, tag]), ...]

    Las filas sin marca llevan sombreado alternado (tag «alterna») para que la
    vista sea más cómoda de leer.
    """
    tree.delete(*tree.get_children())
    alterna = False
    for fila in filas:
        tag = fila[4] if len(fila) > 4 else ""
        if tag:
            alterna = False            # una fila de seención reinicia el ciclo
        else:
            tag = "alterna" if alterna else ""
            alterna = not alterna
        tree.insert("", "end", values=tuple(fila[:4]),
                    tags=(tag,) if tag else ())
