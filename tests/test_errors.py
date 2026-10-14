# -*- coding: utf-8 -*-
"""
Pruebas del manejo de condiciones fisicas invalidas: cada escenario debe
rechazarse con un ValueError educativo (nunca un crash silencioso).
"""
from __future__ import annotations

import pytest

ESPECIFICOS = (
    ("2a Ley: el caliente entra mas frio que el frio",
     dict(tin_cal=10.0)),
    ("balance sobre-especificado (cuatro temperaturas)",
     dict(tout_fri=45.0)),
    ("fluido fuera de su ventana de validez",
     dict(tin_fri=-50.0)),
    ("espesor de pared mayor que el radio del tubo",
     dict(esp_mm=12.0)),
    ("numero de pasos no estandar",
     dict(n_pasos="3")),
)


@pytest.mark.parametrize(
    "descripcion, cambios",
    ESPECIFICOS,
    ids=[d for d, _ in ESPECIFICOS],
)
def test_rechaza_condicion_fisica_invalida(caso_base, descripcion, cambios):
    from intercambiador.gui import controller as ctrl

    datos = dict(caso_base, **cambios)
    with pytest.raises(ValueError) as exc:
        ctrl.correr_sizing(datos)
    assert len(str(exc.value)) > 25, (
        f"rechaza {descripcion} con mensaje educativo, no: {exc.value!r}"
    )
