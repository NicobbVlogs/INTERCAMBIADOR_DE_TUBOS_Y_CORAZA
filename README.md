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

Ese comando ejecuta 165 pruebas sobre todas las fases y termina diciendo
`TODO CORRECTO` o enumerando las fallas.

---

## Qué hace

| Función | Descripción |
|---|---|
| **Sizing** (F5) | Usted fija la geometría del tubo; el programa itera sobre el coeficiente global *U* hasta hallar el área, el número de tubos y el diámetro de coraza necesarios. |
| **Rating** (F6) | Usted ya tiene un equipo (N_tt y D_s conocidos); el programa itera sobre las temperaturas de salida para predecir el calor que transfiere realmente. |
| **Diseño mecánico** | A partir del resultado térmico calcula espesores, espejos, deflectores, varillas tensores, bridas, pernos y boquillas según TEMA Clase C, con las tablas reales del estándar (CB-3.1.3, RCB-4.3, CB-4.4.1, RCB-4.5.2, CB-4.7.1, C-7.1.1, C-11.1, RCB-4.6.1). |
| **Planos** | Cinco vistas paramétricas acotadas: corte longitudinal, distribución de tubos, placa deflectora, cabezal y **catálogo TEMA (Fig. N-1.2)**. El corte longitudinal y el cabezal se dibujan con el diagrama del TIPO elegido (A/B/C/D/N, E/F/G/H/J/K/X, L/M/N/P/S/T/U/W). Clic sobre cualquier pieza para ver sus cotas en milímetros. |

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
  gui/         Interfaz gráfica (CustomTkinter, paleta morado/carmesí/naranja)
    app.py                  Ventana, menú y pestañas
    controller.py           Único puente entre la vista y los módulos de cálculo
    widgets.py              Campos validados, tooltips, tablas
    drawings.py             Vistas paramétricas sobre Canvas
    io_state.py             Proyectos .he (JSON)
ejemplos/      11 proyectos .bb verificados (8 de literatura + 3 de Tan y Fok)
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

Se abren desde **File → Ejemplos** y se calculan solos. Once proyectos,
divididos por modo — ocho ejercicios resueltos de la literatura (los mismos
que se comparan en el documento final) y los tres de Tan y Fok:

| Proyecto | Modo | Fuente |
|---|---|---|
| `09_sinnott_metanol_agua_sizing.bb` | Sizing | Sinnott & Towler, Ej. 12.1 (metanol–agua salobre) |
| `10_karimi_metanol_agua_mar_sizing.bb` | Sizing | Kharaji/Karimi et al. (metanol–agua de mar, óptimo PSO) |
| `11_janna_agua_agua_sizing.bb` | Sizing | Servicio de Janna redimensionado (agua–agua) |
| `12_kern_ej74_agua_agua_sizing.bb` | Sizing | Servicio del Ejemplo 7.4 de Kern (agua–agua) |
| `13_janna_agua_agua_rating.bb` | Rating | Janna, p. 251 (196 tubos) |
| `14_kern_ej74_agua_agua_rating.bb` | Rating | Kern (1950), Ejemplo 7.4 (160 tubos) |
| `15_msubbu_metanol_agua_rating.bb` | Rating | msubbu/Sinnott (918 tubos) |
| `16_karimi_metanol_agua_mar_rating.bb` | Rating | Kharaji, geometría PSO (1238 tubos) |
| `06_tan_fok_sizing.bb` | Sizing | Tan y Fok (2006): especificación del artículo |
| `07_tan_fok_rating.bb` | Rating | Equipo del artículo (257 tubos) |
| `08_tan_fok_rating_parcial.bb` | Rating | El mismo equipo fuera de diseño |

## Sobre los mensajes de error

Cuando el programa rechaza un diseño **no es una falla del software**: es el
modelo físico o la norma TEMA haciendo su trabajo. El rechazo llega siempre
como una ventana emergente estructurada en cuatro preguntas — **QUÉ PASÓ**
(el hecho, con números), **POR QUÉ** (el principio físico o la cláusula de la
norma), **CÓMO LO SOLUCIONO** (la acción concreta sobre el formulario) y la
**REFERENCIA** — y la aplicación sigue corriendo. Casos típicos:

- *Violación de la 2ª Ley* — el fluido «caliente» entra más frío que el «frío».
- *Cruce de temperaturas* — la carga pedida es imposible en contracorriente.
- *Fluido fuera de su ventana de validez* — se valida **cada punto de
  temperatura** (entradas y salidas), no solo la media: p. ej. etanol a 95 °C
  se rechaza aunque su media quede dentro del rango 0–75 °C.
- *Agua por encima de 100 °C* — el agua líquida termina en su ebullición a
  1 atm; el modelo es monofásico y no cubre servicios presurizados.
- *Balance mal planteado* — debe dejarse vacía exactamente una temperatura de
  salida; es la incógnita de q = ṁ·cp·ΔT.
- *Empaque, boquillas o luz sin soporte fuera de TEMA* — el diseño térmico
  converge pero no es fabricable tal cual.

En un barrido de 216 combinaciones de fluidos, caudales, longitudes y pasos,
**ninguna produce un fallo no controlado**; 54 % entrega un diseño completo y
el resto son rechazos razonados como los anteriores.

---

## Tipos TEMA soportados

El estándar TEMA (Fig. N-1.2, incluida en los PDF de esta carpeta) define la
designación de tres letras **[cabezal frontal][coraza][cabezal trasero]**.
Este programa soporta **todos** los tipos:

| Posición | Tipos |
|---|---|
| Cabezal frontal | **A** canal + cubierta · **B** bonete · **C** canal integral con espejo (haz extraíble) · **D** cierre especial de alta presión · **N** canal integral con espejo (espejo fijo) |
| Coraza | **E** una pasada · **F** dos pasadas con deflector longitudinal · **G** flujo partido · **H** doble partido · **J** dividido · **K** caldera · **X** flujo cruzado |
| Cabezal trasero | **L/M/N** espejo fijo · **P** flotante empaquetado · **S** flotante con anillo de retención · **T** pull-through · **U** haz en U · **W** espejo flotante sellado |

La vista **5 · Catálogo TEMA (Fig. N-1.2)** de la pestaña Drawing reproduce el
diagrama completo del estándar con la selección actual resaltada; las vistas 1
y 4 dibujan el equipo con el símbolo correspondiente al tipo elegido.

---

## Régimen de flujo e incertidumbre de los coeficientes

El programa cubre los **tres regímenes** con correlaciones específicas en cada
lado:

1. **Lado tubos** — laminar (Re < 2100): **Hausen (1959)**, solución de Graetz
   con entrada térmica (`Nu = 3,66 + 0,0668·Gz/(1 + 0,04·Gz^2/3)`, con
   `Gz = (d_i/L)·Re·Pr`); transición y turbulento (2400 ≤ Re < 5·10⁶):
   **Gnielinski (1976)**, con factor de fricción de Petukhov
   (`f = (0,790·ln Re − 1,64)^−2`); respaldo Dittus–Boelter por encima de
   5·10⁶. Corrección por viscosidad de pared de Sieder–Tate (1936),
   `φ = (μ/μ_w)^0,14`. Entre 2100 y 2400 las ramas de Hausen y Gnielinski se
   mezclan en escala logarítmica para que `Nu(Re)` sea continua;
2. **Lado coraza** — Kern turbulento (`Nu = 0,36·Re^0,55·Pr^1/3`) y su rama
   laminar con dependencia de Graetz (`Nu = 1,72·(Re·Pr·D_e/B)^1/3`); entre
   100 y 2000 la mezcla log–log es continua en ambos extremos y conserva la
   dependencia `D_e/B`;
3. el lazo de *U* se resuelve por **bisección con bracket fijo**, de modo que
   el resultado **no depende de la semilla U inicial** ni oscila entre
   corridas;
4. se señala el régimen en la tabla hidráulica y se reporta una **banda de
   incertidumbre estimada** sobre *U* (±15 % turbulento, ±20 % transición,
   ±25 % laminar).

Las correlaciones que resolvieron los regímenes laminar y de transición —las
de **Hausen** y **Gnielinski**— se verificaron contra la documentación técnica
consultada en línea (guía de transferencia de calor de neqsim/equinor,
secciones de flujo laminar, transición y turbulento). Aun así, en
laminar/transición la dispersión es mayor que en turbulento: contrástelo con
Bell–Delaware, ε-NTU o datos de servicio antes de fabricar.

---

## El espaciado de baffles y el botón «½·D_s»

El espaciado *B* es un **dato de entrada** del cálculo térmico, pero su ventana
válida (D_s/5 ≤ B ≤ D_s) depende de D_s, que es un **resultado**. Ese lazo se
cierra a mano en dos pasadas: calcule con un *B* tentativo, pulse el botón
**½·D_s** junto al campo, y recalcule con F5.

---

## Alcance y limitaciones

- **Sin cambio de fase.** Todas las correlaciones son para líquidos y gases
  monofásicos. No modela condensadores ni evaporadores (la coraza K se calcula
  solo en su parte sensible).
- **Caída de presión (Δp): implementada por el método de Kern** (tubos:
  fricción + retorno, Eq. 7.43/7.45; coraza: Eq. 7.44). El panel *Hydraulic
  Design* muestra las Δp y los factores de fricción, y el programa advierte
  si alguna supera el límite permisible que fije el usuario. Sí
  reporta velocidades, Reynolds, régimen y diámetro equivalente, que permiten
  verificar las ventanas recomendadas por TEMA/Kern.
- **Conteo de tubos.** El sizing usa la correlación de Serth (con C_L y C_TP),
  reservando además la holgura haz–coraza del cabezal trasero elegido
  (0.011 m en espejo fijo … 0.092 m en cabezal T), y el módulo mecánico
  verifica el empaque por área sobre D_otl. Son dos estimaciones distintas;
  discrepancias menores al 5 % se reportan como advertencia (constante
  `TOL_EMPAQUE` en `design.py`).
- La base termofísica cubre cada fluido solo dentro de su ventana de validez
  declarada, visible bajo cada menú desplegable en la pestaña *Design*. El
  agua líquida termina en **100 °C** (ebullición a 1 atm).
- Las tablas mecánicas provienen de los PDF incluidos en esta carpeta
  (TEMA 10.ª ed., Sección 5 «Mechanical Standards TEMA Class R C B»); los
  diagramas de tipos siguen la Figura N-1.2.
