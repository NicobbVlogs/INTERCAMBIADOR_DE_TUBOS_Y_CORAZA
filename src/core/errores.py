# -*- coding: utf-8 -*-
"""
errores.py - Rechazos de diseno con mensaje educativo estructurado (transversal)
================================================================================
Unica fuente del tipo `ErrorDiseno`. Todos los modulos de calculo (thermo,
mechanical) lanzan este error cuando el modelo fisico o una norma TEMA/ASME
rechaza el diseno. La GUI lo muestra formateado en cuatro preguntas que el
usuario entiende sin ser experto:

    1. ¿Qué pasó?      -> el hecho concreto (números incluidos)
    2. ¿Por qué?       -> el principio fisico o la regla de la norma
    3. ¿Cómo lo soluciono? -> la accion concreta sobre el formulario
    4. Referencia      -> la clausula TEMA / ASME / fuente consultada

Hereda de `ValueError` para no romper el contrato existente: cualquier
`except ValueError` de la GUI o de la suite de verificacion sigue funcionando.

API:
    from src.core.errores import ErrorDiseno

    raise ErrorDiseno(
        titulo="Temperatura fuera de la ventana del fluido",
        que_paso="El etanol entra a 95 °C y su rango valido es 0 – 75 °C.",
        por_que="A esa temperatura el etanol ya no es liquido a 1 atm ...",
        solucion="Baje la temperatura de entrada o cambie de fluido.",
        referencia="Base termofisica src/core/thermo_data.py",
    )
"""
from __future__ import annotations

__all__ = ["ErrorDiseno", "AdvertenciaDiseno"]


class ErrorDiseno(ValueError):
    """Error de diseno: el calculo se detiene y el motivo se explica al usuario."""

    def __init__(self, titulo: str, que_paso: str, por_que: str, solucion: str,
                 referencia: str = "") -> None:
        self.titulo = " ".join(str(titulo).split())
        self.que_paso = " ".join(str(que_paso).split())
        self.por_que = " ".join(str(por_que).split())
        self.solucion = " ".join(str(solucion).split())
        self.referencia = " ".join(str(referencia).split())
        super().__init__(self.como_texto())

    # ------------------------------------------------------------- formatos
    def como_texto(self) -> str:
        """Version plana (consola, logs, str(exc))."""
        lineas = [
            f"ERROR DE DISENO: {self.titulo}",
            f"  Que paso : {self.que_paso}",
            f"  Por que  : {self.por_que}",
            f"  Solucion : {self.solucion}",
        ]
        if self.referencia:
            lineas.append(f"  Referencia: {self.referencia}")
        return "\n".join(lineas)

    def como_dialogo(self) -> str:
        """Version para cuadro de dialogo de la GUI (una pregunta por linea)."""
        lineas = [
            f"QUÉ PASÓ\n   {self.que_paso}",
            "",
            f"POR QUÉ\n   {self.por_que}",
            "",
            f"CÓMO LO SOLUCIONO\n   {self.solucion}",
        ]
        if self.referencia:
            lineas += ["", f"REFERENCIA\n   {self.referencia}"]
        lineas += ["", "El cálculo se detuvo aquí: corrija el dato y vuelva a "
                       "calcular (F5 / F6)."]
        return "\n".join(lineas)


class AdvertenciaDiseno:
    """
    Contenedor util de advertencias con nivel de severidad.

    La GUI puede pintar distinto 'info', 'cuidado' y 'atencion' para que el
    usuario distinga de un vistazo una nota informativa de un riesgo real.
    """

    NIVELES = ("info", "cuidado", "atencion")

    def __init__(self, texto: str, nivel: str = "cuidado") -> None:
        self.texto = " ".join(str(texto).split())
        self.nivel = nivel if nivel in self.NIVELES else "cuidado"

    def __str__(self) -> str:                      # compatibilidad con str()
        return self.texto
