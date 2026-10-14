# -*- coding: utf-8 -*-
"""
io_state.py - Persistencia del estado del formulario en archivos `.he`.

Formato: JSON plano con una cabecera de version. Solo se guardan los INPUTS;
los resultados se recalculan al abrir, de modo que un archivo viejo nunca
muestre numeros desactualizados respecto del motor de calculo.
"""
from __future__ import annotations

import json
from typing import Any, Dict

FORMATO = "intercambiador-tubos-coraza"
VERSION = 1
EXTENSION = ".he"
TIPOS_ARCHIVO = [("Intercambiador (*.he)", "*.he"), ("Todos", "*.*")]


def guardar(ruta: str, datos: Dict[str, Any], descripcion: str = "") -> None:
    paquete = {"formato": FORMATO, "version": VERSION,
               "descripcion": descripcion, "inputs": datos}
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(paquete, fh, indent=2, ensure_ascii=False)


def descripcion_de(ruta: str) -> str:
    """Etiqueta legible del proyecto; cadena vacia si no se puede leer."""
    try:
        with open(ruta, "r", encoding="utf-8") as fh:
            return str(json.load(fh).get("descripcion", ""))
    except Exception:
        return ""


def abrir(ruta: str) -> Dict[str, Any]:
    with open(ruta, "r", encoding="utf-8") as fh:
        try:
            paquete = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"El archivo no es un proyecto .he válido (JSON corrupto).\n\n"
                f"Detalle: {exc}")
    if not isinstance(paquete, dict) or paquete.get("formato") != FORMATO:
        raise ValueError(
            "El archivo seleccionado no corresponde a un proyecto de "
            "intercambiador de tubos y coraza.")
    if paquete.get("version", 0) > VERSION:
        raise ValueError(
            f"El archivo fue creado con una versión más reciente "
            f"(v{paquete['version']}) que esta aplicación (v{VERSION}).")
    inputs = paquete.get("inputs", {})
    if not isinstance(inputs, dict):
        raise ValueError("El archivo .he no contiene un bloque de datos válido.")
    return inputs
