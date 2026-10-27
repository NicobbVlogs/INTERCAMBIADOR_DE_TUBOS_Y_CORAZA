REM © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
@echo off
REM ---------------------------------------------------------------
REM  Lanzador del software de intercambiadores de tubos y coraza.
REM  Haga doble clic en este archivo para abrir la aplicacion.
REM ---------------------------------------------------------------
cd /d "%~dp0"

py src\gui\app.py
if errorlevel 1 (
    echo.
    echo No se pudo iniciar con el lanzador "py". Intentando con "python"...
    python src\gui\app.py
)

if errorlevel 1 (
    echo.
    echo ===============================================================
    echo  No fue posible iniciar la aplicacion.
    echo  Verifique que Python 3 este instalado y disponible en el PATH.
    echo ===============================================================
    pause
)
