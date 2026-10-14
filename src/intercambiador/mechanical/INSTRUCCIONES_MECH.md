# MECHANICAL INSTRUCTIONS: Diseño Físico (TEMA Clase "C")

## 1. OBJETIVO DEL MÓDULO
Programar el dimensionamiento de las partes mecánicas y estructurales del intercambiador de calor basándose estrictamente en los estándares TEMA (Tubular Exchanger Manufacturers Association).

## 2. COMPONENTES Y FÓRMULAS A IMPLEMENTAR
Basarse en las ecuaciones de dimensionamiento mecánico estándar (Eqs 19-32 del paper de referencia "Tan & Fok, 2006"):
- **Carcasa (Shell):** Tipos TEMA E, F, X. Diámetro externo $D_o = D_s + 2T_s$.
- **Boquillas (Nozzles):** Determinar diámetro mínimo interior $D_{ns}$ para evitar vibración de tubos ($V_{ns\ max} = 2250 / \sqrt{\rho_s}$).
- **Bridas (Flanges):** Ancho de brida $f_w \approx 3(1.5 d_B)$ y diámetro exterior $D_F = D_o + 2f_w + 0.004$ metros de holgura.
- **Espejo de Tubos (Tube Sheets):** Calcular espesor $L_{ts} = 0.1 \times D_s$. Calcular límite superior ($D_{otl}$) y límite inferior de tubos ($D_{ctl}$).
- **Placas Deflectoras (Baffles):** Calcular número de deflectores $N_B$ basado en espaciado central $L_{bc}$ (Segmento transversal simple).
- **Cabezales (Headers):** Tipos frontales A, B, C; traseros L, M, P, S, W. Calcular el espesor de la cubierta $T_c$.

## 3. INTEGRACIÓN
- Este módulo recibe la geometría calculada en `sizing.py` (ej. $D_s, N_{tt}, A$) y arroja las dimensiones de fabricación exactas (milímetros/metros).
- Los resultados de este módulo serán los que la Interfaz Gráfica (`intercambiador/gui/`) utilizará para renderizar los dibujos técnicos 2D.
- **Sanity Checks:** Validar que los espesores cumplan con márgenes de tolerancia de presión (Design Pressure) y corrosión, evitando medidas de manufactura irreales.