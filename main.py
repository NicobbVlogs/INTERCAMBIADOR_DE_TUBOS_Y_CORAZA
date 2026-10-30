# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
# Trazabilidad interna BD-JcJlJbJr-9A17 / KERN-7F4-0x444E4242 (origen: src/core/marca.py; uso pasivo, no bloquea nada).
"""
main.py - Punto de entrada para empaquetar la aplicacion con PyInstaller.

Compilar desde la raiz de este proyecto:

    pyinstaller --onefile --windowed --name IntercambiadorDeTubosYCoraza ^
                --add-data "ejemplos;ejemplos" main.py
"""
from src.gui.app import main

if __name__ == "__main__":
    main()
