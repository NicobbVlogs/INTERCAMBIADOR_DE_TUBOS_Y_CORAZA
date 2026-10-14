# -*- coding: utf-8 -*-
"""
widgets.py - Controles reutilizables del formulario (capa VISTA).

Responsabilidad unica: capturar y validar *sintacticamente* lo que el usuario
escribe (vacios, no-numericos, rangos fisicos obvios) y resaltar en rojo los
campos problematicos. NO contiene fisica ni termodinamica: la validacion de
ingenieria vive en intercambiador.thermo y intercambiador.mechanical.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Dict, List, Optional, Sequence

COLOR_OK = "#ffffff"
COLOR_ERROR = "#ffd1d1"
COLOR_FONDO = "#f4f6f8"
COLOR_TITULO = "#1f3b57"


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

        lbl = ttk.Label(parent, text=etiqueta)
        lbl.grid(row=fila, column=columna, sticky="w", padx=(6, 8), pady=3)
        if ayuda:
            Tooltip(lbl, ayuda)

        self.entry = tk.Entry(parent, textvariable=self.var, width=ancho,
                              relief="solid", bd=1, bg=COLOR_OK,
                              justify="right", font=("Segoe UI", 9))
        self.entry.grid(row=fila, column=columna + 1, sticky="ew", pady=3)

        ttk.Label(parent, text=unidad, width=9, foreground="#5a6b7b").grid(
            row=fila, column=columna + 2, sticky="w", padx=(6, 10))

        self.var.trace_add("write", lambda *_: self.limpiar_error())

    # ------------------------------------------------------------- estado
    def marcar_error(self) -> None:
        self.entry.configure(bg=COLOR_ERROR)

    def limpiar_error(self) -> None:
        self.entry.configure(bg=COLOR_OK)

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

        lbl = ttk.Label(parent, text=etiqueta)
        lbl.grid(row=fila, column=columna, sticky="w", padx=(6, 8), pady=3)
        if ayuda:
            Tooltip(lbl, ayuda)

        self.combo = ttk.Combobox(parent, textvariable=self.var, width=ancho,
                                  values=list(valores), state="readonly")
        self.combo.grid(row=fila, column=columna + 1, columnspan=2,
                        sticky="ew", pady=3, padx=(0, 10))
        if comando is not None:
            self.combo.bind("<<ComboboxSelected>>", lambda e: comando())

    def marcar_error(self) -> None:
        pass

    def limpiar_error(self) -> None:
        pass

    def set(self, valor: object) -> bool:
        """Aplica el valor. Devuelve False si no esta entre las opciones.

        Nunca se descarta en silencio: `Formulario.cargar` reune los rechazos
        y los reporta. Aceptar a medias un proyecto .he dejaria la opcion
        anterior en el combo y produciria resultados de otro caso.
        """
        if valor is None or str(valor) not in self.combo["values"]:
            return False
        self.var.set(str(valor))
        return True

    def get(self) -> str:
        return self.var.get()


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
                 font=("Segoe UI", 8), wraplength=320, padx=6, pady=4).pack()

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
            ("param", "Parámetro", 230, "w"),
            ("simbolo", "Símbolo", 70, "center"),
            ("valor", "Valor", 110, "e"),
            ("unidad", "Unidad", 80, "w")):
        tree.heading(col, text=titulo)
        tree.column(col, width=ancho, anchor=anchor, stretch=(col == "param"))
    tree.tag_configure("alerta", background="#fff3cd")
    tree.tag_configure("titulo", background="#e8eef4", font=("Segoe UI", 9, "bold"))
    return tree


def llenar_tabla(tree: ttk.Treeview, filas: Sequence[Sequence[object]]) -> None:
    """filas = [(param, simbolo, valor, unidad[, tag]), ...]"""
    tree.delete(*tree.get_children())
    for fila in filas:
        tag = fila[4] if len(fila) > 4 else ""
        tree.insert("", "end", values=tuple(fila[:4]),
                    tags=(tag,) if tag else ())
