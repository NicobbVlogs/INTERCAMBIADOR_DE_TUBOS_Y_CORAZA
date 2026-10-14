# Diseño de Intercambiadores de Calor de Tubos y Coraza

Software educativo de nivel universitario para el diseño térmico (**Método de
Kern**) y mecánico (**estándar TEMA Clase C**) de intercambiadores de calor de
tubos y coraza, con interfaz gráfica y generación de planos acotados.

---

## Cómo ejecutarlo

**Doble clic en `ejecutar.bat`** (Windows), o desde una terminal en la carpeta
del proyecto:

```
py src/gui/app.py
```

No requiere instalar dependencias: usa solo la librería estándar de Python 3
(`tkinter`). No necesita internet.

Para comprobar que todo funciona correctamente:

```
py verificar.py
```

Ese comando ejecuta 54 pruebas sobre las cuatro fases y termina diciendo
`TODO CORRECTO` o enumerando las fallas.

---

## Qué hace

| Función | Descripción |
|---|---|
| **Sizing** (F5) | Usted fija la geometría del tubo; el programa itera sobre el coeficiente global *U* hasta hallar el área, el número de tubos y el diámetro de coraza necesarios. |
| **Rating** (F6) | Usted ya tiene un equipo (N_tt y D_s conocidos); el programa itera sobre las temperaturas de salida para predecir el calor que transfiere realmente. |
| **Diseño mecánico** | A partir del resultado térmico calcula espesores, espejos, deflectores, bridas, pernos y boquillas según TEMA Clase C. |
| **Planos** | Cuatro vistas paramétricas acotadas: corte longitudinal, distribución de tubos, placa deflectora y cabezal. Clic sobre cualquier pieza para ver sus cotas en milímetros. |

---

## Estructura del proyecto

```
src/
  core/        Base de datos termofísica — 10 fluidos, 5 materiales
    thermo_data.py          ThermoDatabase: cp, mu, k, rho = f(T)
  thermo/      Cálculo térmico (Método de Kern)
    sizing.py               dimensionar()  — itera sobre U
    rating.py               evaluar()      — itera sobre T_out
  mechanical/  Diseño mecánico (TEMA Clase C)
    design.py               disenar_mecanico() — dimensiones de fabricación
  gui/         Interfaz gráfica (tkinter/ttk)
    app.py                  Ventana, menú y pestañas
    controller.py           Único puente entre la vista y los módulos de cálculo
    widgets.py              Campos validados, tooltips, tablas
    drawings.py             Vistas paramétricas sobre Canvas
    io_state.py             Proyectos .he (JSON)
ejemplos/      5 proyectos .he verificados
verificar.py   Suite de verificación de las 4 fases
ejecutar.bat   Lanzador para Windows
```

**Arquitectura MVC estricta:** la GUI no contiene ni una línea de física. Todo
cálculo vive en `core`, `thermo` y `mechanical`; `controller.py` es el único
punto de contacto. Hasta las ventanas de velocidad recomendada que la interfaz
resalta en ámbar se importan desde `src/thermo/sizing.py`, para que el
resaltado nunca pueda contradecir al motor de cálculo.

---

## Ejemplos incluidos

Se abren desde **File → Abrir ejemplo validado** y se calculan solos. Los cinco
convergen sin una sola advertencia:

| Proyecto | Carga | Tubos | D_s |
|---|---|---|---|
| Agua–agua (caso base) | 5020 kW | 500 | 630 mm |
| Enfriador de etanol | 660 kW | 300 | 537 mm |
| Enfriador de etilenglicol | 1375 kW | 244 | 471 mm |
| Enfriador de benceno | 568 kW | 128 | 340 mm |
| Enfriador de amoniaco líquido | 1931 kW | 644 | 736 mm |

---

## Sobre los mensajes de error

Cuando el programa rechaza un diseño **no es una falla del software**: es el
modelo físico haciendo su trabajo. El rechazo llega siempre como una ventana
emergente explicativa y la aplicación sigue corriendo. Casos típicos:

- *Violación de la 2ª Ley* — el fluido «caliente» entra más frío que el «frío».
- *Cruce de temperaturas* — la carga pedida es imposible en contracorriente.
- *Fluido fuera de su ventana de validez* — p. ej. metanol a 80 °C, por encima
  de su punto de ebullición (~65 °C).
- *Balance mal planteado* — debe dejarse vacía exactamente una temperatura de
  salida; es la incógnita de q = ṁ·cp·ΔT.
- *Empaque, boquillas o luz sin soporte fuera de TEMA* — el diseño térmico
  converge pero no es fabricable tal cual.

En un barrido de 216 combinaciones de fluidos, caudales, longitudes y pasos,
**ninguna produce un fallo no controlado**; 56 % entrega un diseño completo y
el resto son rechazos razonados como los anteriores.

---

## El espaciado de baffles y el botón «½·D_s»

El espaciado *B* es un **dato de entrada** del cálculo térmico, pero su ventana
válida (D_s/5 ≤ B ≤ D_s) depende de D_s, que es un **resultado**. Ese lazo se
cierra a mano en dos pasadas: calcule con un *B* tentativo, pulse el botón
**½·D_s** junto al campo, y recalcule con F5.

---

## Alcance y limitaciones

- **Sin cambio de fase.** Todas las correlaciones son para líquidos y gases
  monofásicos. No modela condensadores ni evaporadores.
- **Caída de presión (Δp): no implementada.** El panel *Hydraulic Design* la
  muestra como «reservado», según el alcance definido para esta versión. Sí
  reporta velocidades, Reynolds y diámetro equivalente, que permiten verificar
  las ventanas recomendadas por TEMA/Kern.
- **Conteo de tubos.** El sizing usa la correlación de Serth (con C_L y C_TP) y
  el módulo mecánico verifica el empaque por área sobre D_otl. Son dos
  estimaciones distintas; discrepancias menores al 5 % se reportan como
  advertencia (constante `TOL_EMPAQUE` en `design.py`).
- La base termofísica cubre cada fluido solo dentro de su ventana de validez
  declarada, visible bajo cada menú desplegable en la pestaña *Design*.
