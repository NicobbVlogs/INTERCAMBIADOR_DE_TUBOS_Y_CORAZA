# -*- coding: utf-8 -*-
"""
Prueba de robustez: barrido amplio de entradas. Ninguna combinacion debe
producir un fallo no controlado; las validas deben entregar un diseno completo
y las demas un rechazo razonado (ValueError educativo).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.slow

FLUIDOS = ("Agua", "Etanol", "Metanol", "Etilenglicol", "Benceno",
           "Tolueno", "Aire", "n-Hexano")
CAUDALES = (5.0, 20.0, 40.0)
LONGITUDES = (2.44, 3.66, 4.88)
PASOS = ("1", "2", "4")


def test_barrido_amplio_no_produce_crashes(caso_base):
    from intercambiador.gui import controller as ctrl

    base = dict(caso_base)
    base["tout_fri"] = None

    casos = completos = 0
    crashes = []
    for fcal in FLUIDOS:
        for m_cal in CAUDALES:
            for L in LONGITUDES:
                for pasos in PASOS:
                    casos += 1
                    d = dict(base, fluido_cal=fcal, m_cal=m_cal,
                             m_fri=2 * m_cal, long_m=L, n_pasos=pasos)
                    try:
                        r = ctrl.correr_sizing(d)
                        d["baffle_mm"] = round(r.D_s * 500.0, 1)
                        r = ctrl.correr_sizing(d)
                        ctrl.correr_mecanico(d, r.D_s, r.N_tt,
                                             r.T_h_out, r.T_c_out)
                        completos += 1
                    except ValueError:
                        pass                      # rechazo controlado: correcto
                    except Exception as exc:
                        crashes.append(f"{fcal}/{m_cal}/{L}/{pasos}: "
                                       f"{type(exc).__name__}: {exc}")

    assert not crashes, (
        f"ninguna de las {casos} combinaciones provoca un crash: "
        + "; ".join(crashes[:3])
    )
    assert completos > casos * 0.4, (
        f"al menos el 40 % de las combinaciones completa el diseno "
        f"({100 * completos / casos:.0f} %)"
    )
