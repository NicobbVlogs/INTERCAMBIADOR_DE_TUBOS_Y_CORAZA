# -*- coding: utf-8 -*-
"""
Pruebas de la interfaz grafica (intercambiador.gui): la ventana se construye, calcula,
dibuja y guarda/abre proyectos .he. Cada prueba crea y destruye su propia
ventana, de modo que no dependan del orden de ejecucion.
"""
from __future__ import annotations

import os
import tempfile

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def capturar_avisos(monkeypatch):
    """Sustituye los dialogos de tkinter por una lista de capturas."""
    from tkinter import messagebox

    avisos = []
    for nombre in ("showinfo", "showwarning", "showerror"):
        monkeypatch.setattr(
            messagebox, nombre,
            lambda t, m, _n=nombre: avisos.append((_n, t)),
        )
    return avisos


@pytest.fixture
def ventana():
    pytest.importorskip("tkinter")
    from intercambiador.gui import app as A

    try:
        win = A.Aplicacion()
    except Exception as exc:                    # TclError sin display
        pytest.skip(f"sin display grafico: {exc}")
    win.update()
    yield win
    try:
        win.destroy()
    except Exception:
        pass


def test_ventana_con_4_pestanas(ventana):
    assert ventana.nb.index("end") == 4, "la ventana levanta con sus 4 pestanas"


def test_caso_base_calcula_sin_alertas(ventana, capturar_avisos):
    from intercambiador.gui import app as A

    ventana._calcular_sizing()
    ventana.update()
    assert len(ventana.tbl_termico.get_children()) > 10, "tabla termica poblada"
    assert len(ventana.tbl_hidraulico.get_children()) > 5, "tabla hidraulica poblada"
    assert len(ventana.tbl_mecanico.get_children()) > 20, "tabla mecanica poblada"
    assert not capturar_avisos, (
        f"el caso base no genera ninguna alerta: {capturar_avisos}"
    )
    assert A.VALORES_DEFECTO                  # referencia viva del modulo


def test_vistas_de_dibujo_con_cotas(ventana):
    from intercambiador.gui import app as A

    ventana._calcular_sizing()
    ventana.update()
    for vista in A.drawings.VISTAS:
        ventana._ir_a_vista(vista)
        ventana.update()
        assert len(ventana.canvas.find_all()) > 10 and len(ventana.cotas) > 0, (
            f"dibuja «{vista[:28]}» con cotas clicables"
        )


def test_ida_y_vuelta_de_un_proyecto_he(ventana):
    from intercambiador.gui import app as A
    from intercambiador.gui import io_state

    ruta = os.path.join(tempfile.gettempdir(), "_pytest_tmp.he")
    try:
        ventana._escribir(ruta)
        ventana.form.campos["m_cal"].set(999.0)
        ventana.form.cargar(io_state.abrir(ruta))
        assert ventana.form.campos["m_cal"].var.get() == str(A.VALORES_DEFECTO["m_cal"]), (
            "ida y vuelta de un proyecto .he"
        )
    finally:
        if os.path.exists(ruta):
            os.remove(ruta)


def test_campo_vacio_avisa_y_se_resalta(ventana, capturar_avisos):
    ventana.form.campos["m_fri"].set("")
    ventana._calcular_sizing()
    ventana.update()
    assert bool(capturar_avisos) and ventana.form.campos["m_fri"].entry.cget("bg") != "#ffffff", (
        "campo vacio: avisa y lo resalta en rojo"
    )
    ventana.form.campos["m_fri"].set("80.0")


def test_fluido_desconocido_en_un_he_se_reporta_y_no_se_aplica(ventana):
    from intercambiador.gui.widgets import CampoInvalido

    # Un valor de lista invalido debe avisar, NUNCA cargarse a medias: si el
    # combo conservara el valor previo, el usuario calcularia otro caso sin
    # enterarse.
    fluido_previo = ventana.form.campos["fluido_cal"].var.get()
    with pytest.raises(CampoInvalido):
        ventana.form.cargar({"fluido_cal": "Plutonio fundido"})
    assert ventana.form.campos["fluido_cal"].var.get() == fluido_previo, (
        "un fluido desconocido en un .he se reporta y no se aplica"
    )


def test_boton_de_ajuste_del_espaciado_de_baffles(ventana):
    ventana._calcular_sizing()
    ventana.update()
    b_antes = ventana.form.campos["baffle_mm"].var.get()
    ventana._ajustar_baffle()
    assert ventana.form.campos["baffle_mm"].var.get() != b_antes, (
        "el boton «1/2 D_s» ajusta el espaciado de baffles"
    )
