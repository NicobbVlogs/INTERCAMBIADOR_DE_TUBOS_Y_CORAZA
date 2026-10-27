# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
"""
main.py - Punto de entrada para empaquetar la aplicacion con PyInstaller.

Compilar desde la raiz de este proyecto:

    pyinstaller --onefile --windowed --name IntercambiadorDeTubosYCoraza ^
                --add-data "ejemplos;ejemplos" main.py
"""
from src.gui.app import main

if __name__ == "__main__":
    main()
