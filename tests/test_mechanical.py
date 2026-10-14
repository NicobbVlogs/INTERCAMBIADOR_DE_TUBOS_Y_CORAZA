# -*- coding: utf-8 -*-
"""
Pruebas del diseno mecanico (intercambiador/mechanical/design.py): dimensionamiento
TEMA Clase C coherente con el resultado termico.
"""
from __future__ import annotations


def test_espesor_de_carcasa_positivo(resultado_mecanico):
    m = resultado_mecanico
    assert m.T_s > 0, f"espesor de carcasa = {m.T_s * 1000:.2f} mm"


def test_diametro_exterior_mayor_que_el_interior(resultado_mecanico):
    m = resultado_mecanico
    assert m.D_o > m.D_s, "diametro exterior mayor que el interior"


def test_jerarquia_del_haz(resultado_mecanico):
    m = resultado_mecanico
    assert m.D_s > m.D_otl > m.D_ctl, "D_s > D_otl > D_ctl (jerarquia del haz)"


def test_longitud_total_mayor_que_la_de_los_tubos(resultado_mecanico, caso_base):
    m = resultado_mecanico
    assert m.L_total > caso_base["long_m"], (
        "longitud total mayor que la de los tubos"
    )


def test_numero_de_baffles_no_negativo(resultado_mecanico):
    m = resultado_mecanico
    assert m.baffles.N_B >= 0, f"numero de baffles = {m.baffles.N_B}"


def test_placa_deflectora_cabe_en_la_carcasa(resultado_mecanico):
    m = resultado_mecanico
    assert m.baffles.D_baffle < m.D_s, "la placa deflectora cabe en la carcasa"


def test_brida_mas_ancha_que_la_carcasa(resultado_mecanico):
    m = resultado_mecanico
    assert m.brida.D_F > m.D_o, "brida mas ancha que la carcasa"


def test_numero_minimo_de_pernos(resultado_mecanico):
    m = resultado_mecanico
    assert m.brida.n_pernos >= 4, f"numero de pernos = {m.brida.n_pernos}"


def test_boquilla_de_coraza_dentro_de_su_velocidad_maxima(resultado_mecanico):
    m = resultado_mecanico
    if m.boquilla_coraza is None:
        return
    assert m.boquilla_coraza.V_real <= m.boquilla_coraza.V_max * 1.001, (
        f"boquilla de coraza dentro de su velocidad maxima "
        f"({m.boquilla_coraza.V_real:.2f} m/s)"
    )
