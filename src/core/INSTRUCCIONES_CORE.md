# CORE INSTRUCTIONS: Propiedades Termofísicas (thermo_data.py)

## 1. OBJETIVO DEL MÓDULO
Crear y gestionar `thermo_data.py`. Esta es la única fuente de verdad para las propiedades de los fluidos y materiales. 
**REGLA DE CONTEXTO:** Una vez que programes `thermo_data.py`, NUNCA lo vuelvas a leer completo. Para usarlo en otros módulos, asume su API.

## 2. ESPECIFICACIONES DE FLUIDOS (10)
- **Lista:** Agua, Vapor de agua, Etanol, Metanol, Etilenglicol, Benceno, Tolueno, n-Hexano, Amoníaco (líquido), Aire.
- **Implementación:** Usa correlaciones empíricas de alta fidelidad (Perry's, NIST, VDI, DIPPR). Usa la librería nativa `math` de Python para que el cálculo sea ultrarrápido.
- **Propiedades (SI):** Funciones dependientes de T (en Kelvin) para $Cp$ (J/kg·K), $\mu$ (Pa·s), $k$ (W/m·K) y $\rho$ (kg/m³).

## 3. ESPECIFICACIONES DE MATERIALES SÓLIDOS (5)
- **Lista:** Cobre, Acero al carbono, Acero inox 304, Latón Admiralty, Aluminio.
- **Propiedades:** Define constantes típicas: $k_m$ (W/m·K), $\rho_m$ (kg/m³), rugosidad $\epsilon$ (m) y factor de ensuciamiento $R_f$ (m²·K/W) según TEMA Clase "C".

## 4. ESTRUCTURA Y API REQUERIDA
1. Usa `@dataclass` pura: `FluidState` (campos: cp, mu, k, rho, Pr).
2. Usa `@dataclass` pura: `SolidMaterial` (campos: k_m, rho_m, epsilon, R_f).
3. Expone: `db = ThermoDatabase()` con los métodos `get_fluid_state(name, T, unit="K")` y `get_material(name)`.

## 5. SANITY CHECKS (VALIDACIÓN ESTRICTA)
- Programa límites de temperatura (T_min, T_max) para cada fluido.
- Si se solicita una T fuera del rango donde el fluido existe en esa fase (ej. agua líquida a 400°C a 1 atm), lanza un `ValueError` o un `UserWarning` claro. NUNCA devuelvas propiedades físicas negativas o absurdas.