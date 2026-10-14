# GUI INSTRUCTIONS: Interfaz Gráfica y Experiencia de Usuario (UX)

## 1. OBJETIVO DEL MÓDULO
Desarrollar la interfaz visual (GUI) del software educativo. Su función es capturar los datos del usuario, enviarlos a los módulos de cálculo (`thermo` y `mechanical`) y mostrar los resultados de forma amigable.
**REGLA DE ORO:** La GUI **NO DEBE** contener lógica matemática ni de termodinámica. Su única responsabilidad es importar las funciones de `intercambiador/thermo/` y `intercambiador/mechanical/` y renderizar los resultados. (Arquitectura Modelo-Vista-Controlador estricta).

## 2. ESTRUCTURA DE LA INTERFAZ (MENÚS REQUERIDOS)
Basado en el software de referencia (Tan & Fok, 2006), la ventana principal debe tener un Menú Superior con:
- **File (Archivo):** Opciones para Nuevo, Abrir, Guardar (archivos con extensión `.he` que guarden el estado de los inputs) y Salir.
- **Design (Diseño):** Pantalla principal de captura de datos (Inputs).
  - Selección de tipo de intercambiador y cabezales (TEMA).
  - Menús desplegables para seleccionar los fluidos (conectado a `ThermoDatabase`).
  - Campos numéricos para temperaturas, caudales, y geometría básica del tubo.
- **Analysis (Análisis):** Muestra los Outputs divididos en dos paneles:
  - *Thermal Design:* Despliega LMTD, Calor $q$, Coeficiente $U$, Área $A$, y total de tubos.
  - *Hydraulic Design:* (Espacio reservado para caídas de presión en futuras versiones).
- **Drawing (Dibujos):** Generación de vistas esquemáticas 2D de las partes mecánicas.
- **Help (Ayuda):** Breve tutorial o guía educativa de uso.

## 3. DIBUJOS TÉCNICOS Y VISUALIZACIÓN
El módulo debe incluir un sistema de renderizado (ej. usando Canvas de Tkinter, QGraphicsView de PyQt, o Matplotlib integrado).
- Debe dibujar esquemas paramétricos (no imágenes estáticas) de: La Carcasa, Distribución de Tubos (Layout cuadrado/triangular), Placas deflectoras y Cabezales.
- **Interactividad:** Mostrar ventanas emergentes (pop-ups) o paneles laterales con las cotas exactas (milímetros/metros) provenientes de `intercambiador/mechanical/`.

## 4. SANITY CHECKS VISUALES Y MANEJO DE ERRORES
- **Prevención:** Usa menús desplegables (`Combobox`) en lugar de texto libre siempre que sea posible para evitar errores de tipeo en nombres de fluidos.
- **Advertencias (Pop-ups):** Si los módulos de termodinámica arrojan un `ValueError` (ej. "Cruce de temperaturas imposible" o "Agua en estado vapor a 15°C"), la GUI DEBE capturar ese error con un `try-except` y mostrar un cuadro de diálogo de Alerta (Warning) al usuario de forma educativa, SIN que el programa se cierre inesperadamente (crash).
- **Campos vacíos:** Si el usuario presiona "Calcular" dejando campos en blanco, resáltalos en rojo y pide completarlos.