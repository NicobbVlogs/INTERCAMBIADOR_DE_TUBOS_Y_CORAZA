# -*- coding: utf-8 -*-
"""
Pruebas del calculo termico (intercambiador.thermo): sizing por Metodo de Kern y
rating del mismo equipo.
"""
from __future__ import annotations


def test_sizing_converge(resultado_sizing):
    r = resultado_sizing
    assert r.iteraciones < 50, f"el sizing converge ({r.iteraciones} iteraciones)"


def test_area_y_numero_de_tubos_positivos(resultado_sizing):
    r = resultado_sizing
    assert r.A > 0 and r.N_tt > 0, f"A = {r.A}, N_tt = {r.N_tt}"


def test_area_instalada_cubre_la_requerida(resultado_sizing):
    r = resultado_sizing
    assert r.A_real >= r.A * 0.99, (
        f"el area instalada cubre la requerida ({r.A_real:.1f} >= {r.A:.1f} m2)"
    )


def test_sin_cruce_de_temperaturas(resultado_sizing, caso_base):
    r = resultado_sizing
    assert r.T_h_out > caso_base["tin_fri"], (
        "sin cruce de temperaturas en el caliente"
    )
    assert r.T_c_out < caso_base["tin_cal"], (
        "sin cruce de temperaturas en el frio"
    )


def test_factor_de_correccion_en_rango(resultado_sizing):
    r = resultado_sizing
    assert 0 < r.F <= 1.0, f"factor de correccion F = {r.F:.3f} dentro de (0, 1]"


def test_lmtd_positiva(resultado_sizing):
    r = resultado_sizing
    assert r.LMTD > 0, f"LMTD positiva = {r.LMTD:.2f} C"


def test_U_por_debajo_de_los_coeficientes_de_pelicula(resultado_sizing):
    # Resistencias en serie: U siempre es MENOR que el menor coeficiente de
    # pelicula (pared y ensuciamiento solo pueden restar).
    r = resultado_sizing
    assert 0 < r.U < min(r.h_i, r.h_o), (
        f"U = {r.U:.0f} por debajo de h_i = {r.h_i:.0f} y h_o = {r.h_o:.0f}, "
        f"como exigen las resistencias en serie"
    )


def test_balance_de_energia_cerrado(resultado_sizing, caso_base):
    from intercambiador.core.thermo_data import ThermoDatabase

    r = resultado_sizing
    db = ThermoDatabase()
    cp_c = db.get_fluid_state(
        caso_base["fluido_cal"], 0.5 * (caso_base["tin_cal"] + r.T_h_out), "C"
    ).cp
    q_cal = caso_base["m_cal"] * cp_c * (caso_base["tin_cal"] - r.T_h_out)
    assert abs(q_cal - r.q) / r.q < 0.02, (
        f"balance de energia cerrado (q = {r.q / 1000:.1f} kW, "
        f"lado caliente {q_cal / 1000:.1f} kW)"
    )


# -----------------------------------------------------------------------------
# Rating del mismo equipo
# -----------------------------------------------------------------------------
def test_rating_reproduce_el_sizing(resultado_sizing, resultado_rating):
    r, rt = resultado_sizing, resultado_rating
    assert abs(rt.q - r.q) / r.q < 0.05, (
        f"el rating reproduce el sizing (q {rt.q / 1000:.0f} vs {r.q / 1000:.0f} kW)"
    )


def test_rating_coincide_en_T_de_salida(resultado_sizing, resultado_rating):
    r, rt = resultado_sizing, resultado_rating
    assert abs(rt.T_h_out - r.T_h_out) < 2.0, (
        f"T_h,out coincide ({rt.T_h_out:.1f} vs {r.T_h_out:.1f} C)"
    )


def test_rating_efectividad_en_rango(resultado_rating):
    rt = resultado_rating
    assert 0 < rt.efectividad <= 1.0, (
        f"efectividad = {rt.efectividad * 100:.1f} %"
    )
