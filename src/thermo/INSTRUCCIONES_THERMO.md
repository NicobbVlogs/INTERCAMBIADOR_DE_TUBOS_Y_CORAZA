# THERMO INSTRUCTIONS: Método de Kern (Sizing & Rating)

## 1. OBJETIVO DEL MÓDULO
Implementar la lógica matemática del Método de Kern. Debes separar estrictamente el código en dos archivos: `sizing.py` (Diseño) y `rating.py` (Evaluación). 
**API:** Importa siempre `from src.core.thermo_data import ThermoDatabase`. Evalúa propiedades a la $T_{media} = (T_{in} + T_{out}) / 2$.

## 2. REGLAS PARA SIZING (`sizing.py`) - ALGORITMO ITERATIVO SOBRE "U"
- **Inputs:** Caudales, temperaturas de entrada, una temperatura de salida y restricciones geométricas (ej. longitud máxima).
- **Lógica estricta:**
  1. Calcula el calor $q$ y la temperatura de salida faltante (balance de energía puro).
  2. Inicia iteración: Asume un coeficiente $U$ inicial.
  3. Calcula el Área ($A$), el número de tubos ($N_{tt}$) y diámetro de carcasa ($D_s$).
  4. Obtén $Re, Pr, Nu$ y calcula coeficientes de película $h_i$ (tubos) y $h_o$ (carcasa).
  5. Recalcula $U$ y repite el ciclo hasta que el error relativo de $U$ sea mínimo.
- **Constantes TEMA:** $C_L=1.0$ (cuadrado) o $0.87$ (triangular). $C_{TP}=0.93$ (1 paso) o $0.90$ (2 pasos).
- **Advertencia:** Verifica la velocidad real por continuidad ($U_m$); no impongas velocidades que violen la conservación de masa.

## 3. REGLAS PARA RATING (`rating.py`) - ALGORITMO ITERATIVO SOBRE TEMPERATURAS
- **Inputs:** Geometría completa y fija, caudales y temperaturas de entrada.
- **Lógica estricta (Búsqueda de Raíces):**
  1. Fija el Área y dimensiones transversales.
  2. Supón $T_{co}$ y $T_{ho}$ (temperaturas de salida).
  3. Calcula propiedades, velocidades reales y el coeficiente $U$ riguroso.
  4. Resuelve el calor iterando la raíz de la ecuación: $q(T_{co}) - U \cdot A \cdot F \cdot \Delta T_m(T_{co}) = 0$.
  5. Detente cuando la variación térmica sea menor a la tolerancia (ej. $0.01^\circ C$).

## 4. SANITY CHECKS TÉRMICOS
- Alerta violaciones a la 2da Ley de la Termodinámica (cruce de temperaturas imposible).
- Alerta velocidades de fluido excesivas (riesgo de vibración según TEMA) o muy bajas (flujo laminar ineficiente).