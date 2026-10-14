@echo off
REM ---------------------------------------------------------------
REM  Lanzador del software de intercambiadores de tubos y coraza.
REM  Haga doble clic en este archivo para abrir la aplicacion.
REM  Requiere uv (https://docs.astral.sh/uv/).
REM ---------------------------------------------------------------
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo ===============================================================
    echo  No se encontro "uv" en el PATH.
    echo  Instalelo desde:
    echo    https://docs.astral.sh/uv/getting-started/installation/
    echo ===============================================================
    pause
    exit /b 1
)

REM uv run sincroniza el entorno (.venv) y ejecuta el gui-script del proyecto.
uv run intercambiador
if errorlevel 1 (
    echo.
    echo ===============================================================
    echo  No fue posible iniciar la aplicacion.
    echo  Pruebe primero:  uv sync
    echo  y vuelva a ejecutar este lanzador.
    echo ===============================================================
    pause
)
