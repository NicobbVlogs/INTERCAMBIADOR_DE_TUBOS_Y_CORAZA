# Diseño de Intercambiadores de Calor de Tubos y Coraza

Software educativo y profesional de alta fidelidad para el diseño térmico (**Método de Kern**) y mecánico (**estándar TEMA Clase C / ASME Sección VIII Div. 1**) de intercambiadores de calor de tubos y coraza, con interfaz gráfica interactiva, resolución termo-hidráulica acoplada y generación de planos paramétricos acotados.

---

## Cómo ejecutarlo

**Doble clic en `ejecutar.bat`** (Windows), o desde una terminal en la carpeta del proyecto:

```bash
python src/gui/app.py
```

No requiere dependencias externas para la ejecución de la aplicación: usa la librería estándar de Python 3 (`tkinter`).

Para comprobar la integridad numérica y ejecución completa de los casos de prueba:

```bash
python verificar.py
```

Ese comando ejecuta las **56 pruebas formales** sobre las cuatro capas del sistema y certifica `RESULTADO: TODO CORRECTO  (56 pruebas superadas)`.

---

## Arquitectura del Software

El sistema sigue una arquitectura Modelo-Vista-Controlador (MVC) desacoplada con 4 pilares fundamentales:

```
src/
  core/           [Pilar 1] Base de datos termofísica de alta fidelidad
    thermo_data.py          Propiedades dependientes de la temperatura (cp, mu, k, rho = f(T)),
                            ventanas de fase, ensuciamiento estandarizado TEMA (R_f) y metales.
  thermo/         [Pilar 2] Motor de cálculo térmico e hidráulico (Método de Kern)
    sizing.py               dimensionar() — Dimensionamiento iterativo sobre U acoplado con dp_t y dp_s.
    rating.py               evaluar()     — Evaluación fuera de diseño iterando sobre temperaturas de salida.
  mechanical/     [Pilar 3] Dimensionamiento mecánico y fabricación (TEMA Clase C / ASME UG-27)
    design.py               disenar_mecanico() — Espesores de carcasa, espejos, baffles, bridas y boquillas.
  gui/            [Pilar 4] Interfaz gráfica de usuario (tkinter/ttk)
    app.py                  Ventana principal, barra de menús, pestañas de resultados y diagnóstico.
    controller.py           Orquestador central entre eventos de interfaz y motores de cálculo.
    widgets.py              Componentes UI con validación de entradas numéricas, tooltips y tablas.
    drawings.py             Generación vectorial de esquemas paramétricos acotados sobre Canvas.
    io_state.py             Serialización y deserialización de proyectos en formato .he (JSON).
ejemplos/         Casos de estudio industriales y de benchmark completamente validados.
verificar.py      Suite de pruebas unitarias, integración, benchmarks y barridos de robustez.
ejecutar.bat      Lanzador rápido para entornos Windows.
```

---

## Fundamento de Cálculo (Método Canónico de Kern y Estándares TEMA)

### 1. Lado Coraza
- **Área transversal de flujo en el eje:** $A_s = \frac{D_s \cdot C \cdot B}{P_T \cdot N_{corazas}}$ (Kern Eq. 7.1, con claro $C = P_T - d_o$).
- **Diámetro equivalente ($D_e$):**
  - Arreglo cuadrado (45° o 90°): $D_e = \frac{4 (P_T^2 - \frac{\pi d_o^2}{4})}{\pi d_o}$ (Kern Eq. 7.2).
  - Arreglo triangular (30° o 60°): $D_e = \frac{4 (\frac{\sqrt{3}}{4} P_T^2 - \frac{\pi d_o^2}{8})}{\frac{\pi d_o}{2}}$ (Kern Eq. 7.3).
- **Velocidad másica y Reynolds:** $G_s = \frac{\dot{m}_s}{A_s}$, $\quad Re_s = \frac{D_e G_s}{\mu_s}$.
- **Convección:** $Nu_s = 0.36 \cdot Re_s^{0.55} \cdot Pr_s^{1/3} \cdot \left(\frac{\mu}{\mu_w}\right)^{0.14}$ (Kern Eq. 7.4).
- **Caída de presión coraza:** $\Delta p_s = \frac{N_{corazas} \cdot f_s \cdot G_s^2 \cdot D_s \cdot (N_b + 1)}{2 \rho_s D_e \phi_s}$ (Kern Eq. 7.44).

### 2. Lado Tubos
- **Área de flujo por paso:** $a_t = \frac{N_{tt} \cdot \pi d_i^2}{4 \cdot n_{pasos}}$, $\quad u_m = \frac{\dot{m}_t}{\rho_t a_t}$.
- **Convección interna ($Nu_t$):**
  - Laminar ($Re < 2100$): $Nu = \max\left(1.86 \left(Re \cdot Pr \cdot \frac{d_i}{L}\right)^{1/3} \phi_t, 3.66\right)$ (Kern Eq. 6.2).
  - Turbulento ($Re \ge 10000$): $Nu = 0.027 \cdot Re^{0.8} \cdot Pr^{1/3} \cdot \phi_t$ (Kern Eq. 6.3).
  - Transición ($2100 \le Re < 10000$): Interpolación monótona continua garantizando continuidad $C^0$.
- **Caída de presión total:** $\Delta p_t = \Delta p_L + \Delta p_r$ (Kern Eq. 7.43 y 7.45/7.46):
  $$\Delta p_t = n_{pasos} \cdot f_t \left(\frac{L}{d_i}\right) \frac{\rho_t u_m^2}{2 \phi_t^m} + 4 n_{pasos} \left(\frac{\rho_t u_m^2}{2}\right)$$

### 3. Coeficiente Global y Balances
- **Balance térmico:** $q = \dot{m}_h cp_h (T_{h,in} - T_{h,out}) = \dot{m}_c cp_c (T_{c,out} - T_{c,in})$ (Kern Cap. 5).
- **LMTD:** $\Delta T_{lm} = \frac{\Delta T_1 - \Delta T_2}{\ln(\Delta T_1 / \Delta T_2)}$ (Kern Eq. 5.14). Con remoción de singularidad $0/0$ cuando $R = 1$.
- **Factor de corrección $F$:** Bowman-Mueller-Nagle para configuraciones 1-2 y extensión a $N_s$ corazas en serie (TEMA F).
- **Resistencia global:** $\frac{1}{U_o} = \frac{1}{h_o} + R_{f,o} + \frac{d_o \ln(d_o/d_i)}{2 k_w} + \frac{d_o}{d_i} R_{f,i} + \frac{d_o}{d_i h_i}$.

---

## Registro de Estabilidad Numérica (Los 7 Conflictos Resueltos)

Durante las fases de auditoría y consolidación de parches termohidráulicos, se identificaron y solventaron 7 inconsistencias críticas para asegurar estabilidad numérica estricta:

1. **Corrección de Indentación y Sintaxis en Caídas de Presión:**
   Se corrigió el error de sangría en la definición de `exponente_m` dentro de `caida_presion_tubos`, evitando excepciones de sintaxis `IndentationError` en tiempo de carga.
2. **Orden de Definición Previa de `n_corazas`:**
   En `sizing.py`, el parche original utilizaba `n_corazas` en el cálculo del factor $F$ antes de haberlo declarado. Se reestructuró la función para definir $n_{corazas} = 2$ (para carcasas tipo F) en la etapa de validación geométrica inicial.
3. **Interpolación Continua de Nusselt en Régimen de Transición:**
   Se comprobó numéricamente que la formulación acotada con `max(Hausen, Nu_lam)` generaba discontinuidades de $+6\%$ en $Re=2100$ y $-5\%$ en $Re=10000$. Se implementó una interpolación lineal ponderada que asegura continuidad $C^0$ con un salto relativo medido $\sim 1.6 \times 10^{-7}$.
4. **Integración Estandarizada de Ensuciamiento TEMA (`db.get_fouling`):**
   Se implementó la jerarquía de ensuciamiento con orden de precedencia estricto: (1) Valor asignado por el usuario en `Stream.R_f`, (2) Tabla TEMA RGP-T-2.4 por fluido en `thermo_data.py`, (3) Respaldo del 50% de la resistencia del material sólido.
5. **Recálculo Consistente del Área Requerida con el Haz Entero:**
   Al discretizar al entero superior de tubos $N_{tt}$ múltiplo de $n_{pasos}$, la velocidad real varía ligeramente. El código recalcula $U$, $\Delta p$ y el área requerida $A = q / (U F \Delta T_{lm})$ con el $U$ del haz instalado, reportando el porcentaje de sobre-área exacto y advirtiendo cualquier déficit.
6. **Estandarización de Rating para Corazas TEMA F:**
   Se homogeneizó el módulo `rating.py` con `sizing.py`, incorporando la propiedad `n_corazas` y el factor de división del área de flujo transversal para carcasas TEMA F, así como el uso de ensuciamientos individuales por corriente (`resistencia_ensuciamiento`).
7. **Ajuste de Criterios TEMA en Boquillas Sch-40:**
   Se corrigió el límite de vibración en boquillas según TEMA RCB-4.61 ($\rho V^2 \le 1500 \text{ lb}_m/(\text{ft}\cdot\text{s}^2) = 2232.25 \text{ Pa}$, en sustitución de 3348.6 Pa). En `verificar.py`, el aviso de baja velocidad resultante de la discretización a tubería Sch-40 comercial fue tipificado como advertencia informativa.

---

## Resultados de Validación y Certificación

- **Suite de Pruebas Automatizadas:** **56 / 56 pruebas aprobadas (100% éxito)**.
- **Cierre Térmico:** Balance térmico de energía cerrado con error relativo $< 0.02\%$ (residual $|q - UAF\Delta T_{lm}| = 97.1 \text{ W}$ en carga de $610.6 \text{ kW}$).
- **Singularidad LMTD:** Comportamiento asintótico exacto en $R=1$ evaluado en $40.0000^\circ\text{C}$ sin indeterminaciones $0/0$.
- **Robustez Global:** 216 combinaciones exploradas en barrido paramétrico con cero fallos no controlados.

---

## Guía de Uso Rápido

### Ejecución de la Interfaz Gráfica
```bash
python src/gui/app.py
```

### Ejecución de Cálculos en Modo Terminal (Scripts Independientes)
```bash
# Probar Sizing térmico interactivo
python src/thermo/sizing.py

# Probar Rating térmico
python src/thermo/rating.py

# Probar Diseño mecánico TEMA Clase C
python src/mechanical/design.py
```

### Ejecución de la Batería de Pruebas de Verificación
```bash
python verificar.py
```
