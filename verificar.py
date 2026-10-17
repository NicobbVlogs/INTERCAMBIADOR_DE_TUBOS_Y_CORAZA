# -*- coding: utf-8 -*-
"""
verificar.py - Suite de verificacion del programa completo.

Ejecutar desde la raiz del proyecto:

    py verificar.py

Comprueba las cuatro fases de punta a punta y termina con codigo de salida 0
si todo pasa, o 1 si algo fallo. No requiere instalar nada: usa solo la
libreria estandar (tkinter se abre y se cierra sin mostrar ventana).

Que cubre:
  1. Core      - propiedades termofisicas en puntos de referencia conocidos.
  2. Thermo    - el caso base converge y el rating reproduce el sizing.
  3. Mechanical- el dimensionamiento TEMA se completa y es coherente.
  4. Errores   - las condiciones fisicas invalidas lanzan ValueError educativo.
  5. GUI       - la ventana se construye, calcula, dibuja y guarda/abre .he.
  6. Ejemplos  - los proyectos .he distribuidos siguen siendo validos.
  7. Robustez  - barrido amplio: ninguna entrada debe producir un crash real.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

fallos: list = []
pruebas = [0]


def check(condicion: bool, descripcion: str, detalle: str = "") -> bool:
    pruebas[0] += 1
    if condicion:
        print(f"   [OK]    {descripcion}")
        return True
    print(f"   [FALLA] {descripcion}" + (f"  -> {detalle}" if detalle else ""))
    fallos.append(descripcion)
    return False


def bloque(titulo: str) -> None:
    print(f"\n{titulo}\n" + "-" * len(titulo))


# =============================================================================
# 1. CORE
# =============================================================================
def probar_core() -> None:
    bloque("1. Base de datos termofisica (src/core)")
    from src.core.thermo_data import ThermoDatabase
    db = ThermoDatabase()

    check(len(db.list_fluids()) == 10,
          f"catalogo de 10 fluidos", str(len(db.list_fluids())))
    check(len(db.list_materials()) == 5, "catalogo de 5 materiales")

    # Agua a 20 C: valores de referencia ampliamente tabulados.
    agua = db.get_fluid_state("Agua", 20.0, "C")
    check(960 < agua.rho < 1005, f"densidad del agua a 20 C = {agua.rho:.1f} kg/m3")
    check(4150 < agua.cp < 4220, f"cp del agua a 20 C = {agua.cp:.0f} J/kg.K")
    check(0.55 < agua.k < 0.65, f"k del agua a 20 C = {agua.k:.3f} W/m.K")
    check(0.9e-3 < agua.mu < 1.1e-3,
          f"viscosidad del agua a 20 C = {agua.mu*1000:.3f} mPa.s")

    # Monotonia fisica: la viscosidad del agua cae al calentarse.
    mu80 = db.get_fluid_state("Agua", 80.0, "C").mu
    check(mu80 < agua.mu, "la viscosidad del agua disminuye con la temperatura")

    try:
        db.get_fluid_state("Mercurio", 20.0, "C")
        check(False, "rechaza un fluido inexistente")
    except ValueError:
        check(True, "rechaza un fluido inexistente con ValueError")

    # Informe PDF de procedencia de las propiedades (solo stdlib).
    from src.core.informe_propiedades import generar_informe
    import tempfile
    ruta_pdf = os.path.join(tempfile.gettempdir(), "_verificar_informe.pdf")
    generar_informe(ruta_pdf)
    with open(ruta_pdf, "rb") as fh:
        cabecera = fh.read(8)
        fh.seek(-16, 2)
        cola = fh.read()
    tam = os.path.getsize(ruta_pdf)
    check(cabecera.startswith(b"%PDF") and b"%%EOF" in cola and tam > 30000,
          f"el informe de propiedades genera un PDF valido ({tam/1024:.0f} KB)")
    os.remove(ruta_pdf)


# =============================================================================
# 2 y 3. THERMO + MECHANICAL
# =============================================================================
def probar_calculo() -> dict:
    bloque("2. Calculo termico (src/thermo)")
    from src.gui import controller as ctrl
    from src.gui.app import VALORES_DEFECTO

    d = dict(VALORES_DEFECTO)
    d["tout_fri"] = None
    r = ctrl.correr_sizing(d)

    check(r.iteraciones < 50, f"el sizing converge ({r.iteraciones} iteraciones)")
    check(r.A > 0 and r.N_tt > 0, "area y numero de tubos positivos")
    check(r.A_real >= r.A * 0.99,
          f"el area instalada cubre la requerida ({r.A_real:.1f} >= {r.A:.1f} m2)")
    check(r.T_h_out > d["tin_fri"], "sin cruce de temperaturas en el caliente")
    check(r.T_c_out < d["tin_cal"], "sin cruce de temperaturas en el frio")
    check(0 < r.F <= 1.0, f"factor de correccion F = {r.F:.3f} dentro de (0, 1]")
    check(r.LMTD > 0, f"LMTD positiva = {r.LMTD:.2f} C")
    # Resistencias en serie: U siempre es MENOR que el menor coeficiente de
    # pelicula (pared y ensuciamiento solo pueden restar).
    check(0 < r.U < min(r.h_i, r.h_o),
          f"U = {r.U:.0f} por debajo de h_i = {r.h_i:.0f} y h_o = {r.h_o:.0f}, "
          f"como exigen las resistencias en serie")

    # Balance de energia cerrado por ambos lados.
    from src.core.thermo_data import ThermoDatabase
    db = ThermoDatabase()
    cp_c = db.get_fluid_state(d["fluido_cal"],
                              0.5*(d["tin_cal"]+r.T_h_out), "C").cp
    q_cal = d["m_cal"] * cp_c * (d["tin_cal"] - r.T_h_out)
    check(abs(q_cal - r.q) / r.q < 0.02,
          f"balance de energia cerrado (q = {r.q/1000:.1f} kW, "
          f"lado caliente {q_cal/1000:.1f} kW)")

    bloque("3. Rating del mismo equipo (src/thermo/rating.py)")
    d2 = dict(d, n_tt=r.N_tt, d_s_mm=r.D_s*1000.0)
    rt = ctrl.correr_rating(d2)
    check(abs(rt.q - r.q) / r.q < 0.05,
          f"el rating reproduce el sizing (q {rt.q/1000:.0f} vs {r.q/1000:.0f} kW)")
    check(abs(rt.T_h_out - r.T_h_out) < 2.0,
          f"T_h,out coincide ({rt.T_h_out:.1f} vs {r.T_h_out:.1f} C)")
    check(0 < rt.efectividad <= 1.0, f"efectividad = {rt.efectividad*100:.1f} %")

    bloque("4. Diseno mecanico (src/mechanical)")
    m = ctrl.correr_mecanico(d, r.D_s, r.N_tt, r.T_h_out, r.T_c_out)
    check(m.T_s > 0, f"espesor de carcasa = {m.T_s*1000:.2f} mm")
    check(m.D_o > m.D_s, "diametro exterior mayor que el interior")
    check(m.D_s > m.D_otl > m.D_ctl, "D_s > D_otl > D_ctl (jerarquia del haz)")
    check(m.L_total > d["long_m"], "longitud total mayor que la de los tubos")
    check(m.baffles.N_B >= 0, f"numero de baffles = {m.baffles.N_B}")
    check(m.baffles.D_baffle < m.D_s, "la placa deflectora cabe en la carcasa")
    check(m.brida.D_F > m.D_o, "brida mas ancha que la carcasa")
    check(m.brida.n_pernos >= 4, f"numero de pernos = {m.brida.n_pernos}")
    if m.boquilla_coraza:
        check(m.boquilla_coraza.V_real <= m.boquilla_coraza.V_max * 1.001,
              f"boquilla de coraza dentro de su velocidad maxima "
              f"({m.boquilla_coraza.V_real:.2f} m/s)")
    return {"sizing": r, "mecanico": m}


# =============================================================================
# 5. ERRORES EDUCATIVOS
# =============================================================================
def probar_errores() -> None:
    bloque("5. Manejo de condiciones fisicas invalidas")
    from src.gui import controller as ctrl
    from src.gui.app import VALORES_DEFECTO
    base = dict(VALORES_DEFECTO)
    base["tout_fri"] = None

    escenarios = [
        ("2a Ley: el caliente entra mas frio que el frio",
         dict(base, tin_cal=10.0)),
        ("balance sobre-especificado (cuatro temperaturas)",
         dict(base, tout_fri=45.0)),
        ("fluido fuera de su ventana de validez",
         dict(base, tin_fri=-50.0)),
        ("espesor de pared mayor que el radio del tubo",
         dict(base, esp_mm=12.0)),
        ("numero de pasos no estandar",
         dict(base, n_pasos="3")),
        # --- defectos corregidos: exceso de temperatura por la media ---------
        ("etanol por encima de 75 C (aunque la media quede valida)",
         dict(base, fluido_cal="Etanol", tin_cal=95.0, tout_cal=45.0)),
        ("agua por encima de 100 C (limite de ebullicion a 1 atm)",
         dict(base, fluido_cal="Agua", tin_cal=105.0, tout_cal=60.0)),
        ("agua calculada por encima de 100 C en su salida",
         dict(base, fluido_cal="Etilenglicol", tin_cal=160.0, tout_cal=60.0,
              m_fri=0.01, m_cal=20.0)),
        ("corriente caliente que se estaria calentando",
         dict(base, tin_cal=50.0, tout_cal=80.0)),
        ("corriente fria que se estaria enfriando",
         dict(base, tout_cal=None, tout_fri=10.0)),
    ]
    for descripcion, datos in escenarios:
        try:
            ctrl.correr_sizing(datos)
            check(False, f"rechaza {descripcion}", "no lanzo excepcion")
        except ValueError as exc:
            check(len(str(exc)) > 25,
                  f"rechaza {descripcion} con mensaje educativo")
        except Exception as exc:
            check(False, f"rechaza {descripcion}",
                  f"lanzo {type(exc).__name__} en vez de ValueError")


# =============================================================================
# 5b. TIPOS TEMA Y ESTRUCTURA DE LOS MENSAJES
# =============================================================================
def probar_tipos_tema() -> None:
    bloque("5b. Tipos TEMA soportados (Fig. N-1.2) y mensajes estructurados")
    from src.gui import controller as ctrl
    from src.gui.app import VALORES_DEFECTO
    from src.core.errores import ErrorDiseno

    base = dict(VALORES_DEFECTO)
    base["tout_fri"] = None

    # --- todos los tipos de coraza deben calcular (termico + mecanico) -----
    for tipo in ("E", "F", "G", "H", "J", "K", "X"):
        d = dict(base, tipo_carcasa=tipo)
        try:
            r = ctrl.correr_sizing(d)
            ctrl.correr_mecanico(d, r.D_s, r.N_tt, r.T_h_out, r.T_c_out)
            check(True, f"coraza tipo {tipo}: calcula termico y mecanico")
        except Exception as exc:
            check(False, f"coraza tipo {tipo}: calcula termico y mecanico",
                  f"{type(exc).__name__}: {exc}")

    # --- todos los cabezales frontales y traseros --------------------------
    for frontal in ("A", "B", "C", "D", "N"):
        for trasero in ("L", "M", "N", "P", "S", "T", "U", "W"):
            d = dict(base, cab_frontal=frontal, cab_trasero=trasero)
            try:
                r = ctrl.correr_sizing(d)
                m = ctrl.correr_mecanico(d, r.D_s, r.N_tt, r.T_h_out,
                                         r.T_c_out)
                ok = (m.cab_frontal.tipo == frontal
                      and m.cab_trasero.tipo == trasero
                      and m.cab_frontal.descripcion
                      and m.cab_trasero.descripcion)
                check(ok, f"cabezal {frontal}-{trasero}: completo y descrito")
            except Exception as exc:
                check(False, f"cabezal {frontal}-{trasero}: completo y descrito",
                      f"{type(exc).__name__}: {exc}")

    # --- los mensajes de error van estructurados en cuatro preguntas -------
    try:
        ctrl.correr_sizing(dict(base, fluido_cal="Etanol", tin_cal=95.0,
                                tout_cal=45.0))
        check(False, "el error de temperatura viene estructurado",
              "no lanzo excepcion")
    except ErrorDiseno as exc:
        dlg = exc.como_dialogo()
        check(all(seccion in dlg for seccion in
                  ("QUÉ PASÓ", "POR QUÉ", "CÓMO LO SOLUCIONO", "REFERENCIA")),
              "el error de temperatura viene estructurado (4 preguntas)")
    except Exception as exc:
        check(False, "el error de temperatura viene estructurado",
              f"{type(exc).__name__}")

    # --- el tipo de coraza desconocido se explica con el catalogo completo --
    try:
        ctrl.correr_mecanico(dict(base, tipo_carcasa="Z"), 0.5, 100, 50, 30)
        check(False, "un tipo de coraza desconocido se rechaza explicando",
              "no lanzo excepcion")
    except ValueError as exc:
        check(all(t in str(exc) for t in ("E", "F", "G", "H", "J", "K", "X")),
              "un tipo de coraza desconocido se rechaza listando los validos")
    except Exception as exc:
        check(False, "un tipo de coraza desconocido se rechaza explicando",
              f"{type(exc).__name__}")


# =============================================================================
# 5c. DETERMINISMO EN REGIMEN LAMINAR (independencia de la semilla U)
# =============================================================================
def probar_laminar() -> None:
    bloque("5c. Convergencia determinista del sizing (semilla U inicial)")
    from src.gui import controller as ctrl
    from src.gui.app import VALORES_DEFECTO

    # Caso deliberadamente laminar: glicol caliente en coraza, agua lenta en
    # tubos con 1 paso (velocidad baja -> Re < 2100).
    base = dict(VALORES_DEFECTO, tout_fri=None,
                fluido_cal="Etilenglicol", m_cal=1.0, tin_cal=120.0,
                tout_cal=100.0, m_fri=0.25, tin_fri=25.0,
                long_m=3.66, n_pasos="1", baffle_mm=200.0)
    resultados = []
    for semilla in (50.0, 300.0, 700.0, 2500.0):
        r = ctrl.correr_sizing(dict(base, u_inicial=semilla))
        resultados.append(r)
    r0 = resultados[0]
    iguales = all(
        abs(r.U - r0.U) < 1e-6 * max(r0.U, 1.0) and r.N_tt == r0.N_tt
        and abs(r.A - r0.A) < 1e-6 * max(r0.A, 1.0) and r.D_s == r0.D_s
        for r in resultados)
    check(iguales,
          f"U = {r0.U:.2f} W/m2.K, {r0.N_tt} tubos, D_s = {r0.D_s*1000:.0f} mm "
          f"identicos con 4 semillas distintas (regimen tubos: "
          f"{r0.regimen_tubo}, coraza: {r0.regimen_coraza})",
          str([(r.U, r.N_tt) for r in resultados]))
    check(r0.regimen_tubo != "turbulento" and r0.regimen_coraza != "turbulento",
          f"el caso de prueba cae en regimen no turbulento "
          f"(tubos: {r0.regimen_tubo}, coraza: {r0.regimen_coraza})")
    check(any(a for a in r0.advertencias if "incertidumbre" in a),
          "el caso laminar reporta su banda de incertidumbre",
          "; ".join(r0.advertencias))


# =============================================================================
# 6. GUI
# =============================================================================
def probar_gui() -> None:
    bloque("6. Interfaz grafica (src/gui)")
    from tkinter import messagebox
    from src.gui import app as A

    avisos = []
    for nombre in ("showinfo", "showwarning", "showerror"):
        setattr(messagebox, nombre,
                lambda t, m, _n=nombre: avisos.append((_n, t)))
    A.messagebox = messagebox

    win = A.Aplicacion()
    win.update()
    check(win.nb.index("end") == 4, "la ventana levanta con sus 4 pestanas")

    win._calcular_sizing()
    win.update()
    check(len(win.tbl_termico.get_children()) > 10, "tabla termica poblada")
    check(len(win.tbl_hidraulico.get_children()) > 5, "tabla hidraulica poblada")
    check(len(win.tbl_mecanico.get_children()) > 20, "tabla mecanica poblada")
    check(not avisos, "el caso base no genera ninguna alerta", str(avisos))

    for vista in A.drawings.VISTAS:
        win._ir_a_vista(vista)
        win.update()
        check(len(win.canvas.find_all()) > 10 and len(win.cotas) > 0,
              f"dibuja «{vista[:28]}» con cotas clicables")

    # Los dibujos deben salir segun el TIPO TEMA elegido (Fig. N-1.2).
    avisos.clear()
    win.form.campos["cab_frontal"].set("N")
    win.form.campos["tipo_carcasa"].set("K")
    win.form.campos["cab_trasero"].set("U")
    win._calcular_sizing()
    win.update()
    graves = [a for a in avisos if a[0] in ("showwarning", "showerror")]
    win._ir_a_vista("1 · Carcasa (corte longitudinal)")
    win.update()
    check(not graves and len(win.cotas) > 3,
          "el corte longitudinal dibuja el tipo N-K-U sin errores",
          str(graves))
    check("N" in win.cotas.get("cab_front", "") and
          "U" in win.cotas.get("cab_tras", ""),
          "las cotas identifican los tipos N y U del corte longitudinal",
          str(sorted(win.cotas)))
    win._ir_a_vista("5 · Catálogo TEMA (Fig. N-1.2)")
    win.update()
    seleccion = [t for t in win.cotas if "ES LA SELECCIÓN ACTUAL" in
                 win.cotas[t]]
    check(sorted(seleccion) == ["cat_cab_frontal_N", "cat_cab_trasero_U",
                                "cat_tipo_carcasa_K"],
          "el catálogo TEMA resalta exactamente los tres tipos elegidos",
          str(sorted(seleccion)))
    # y vuelve al caso base para el resto de la prueba
    win.form.campos["cab_frontal"].set("A")
    win.form.campos["tipo_carcasa"].set("E")
    win.form.campos["cab_trasero"].set("M")

    # Guardado y lectura de un proyecto .he.
    ruta = os.path.join(tempfile.gettempdir(), "_verificar_tmp.he")
    win._escribir(ruta)
    win.form.campos["m_cal"].set(999.0)
    from src.gui import io_state
    win.form.cargar(io_state.abrir(ruta))
    check(win.form.campos["m_cal"].var.get() == str(A.VALORES_DEFECTO["m_cal"]),
          "ida y vuelta de un proyecto .he")
    os.remove(ruta)

    # Validacion de formulario: campo obligatorio vacio.
    avisos.clear()
    win.form.campos["m_fri"].set("")
    win._calcular_sizing()
    win.update()
    check(bool(avisos) and win.form.campos["m_fri"].entry.cget("bg") != "#ffffff",
          "campo vacio: avisa y lo resalta en rojo")
    win.form.campos["m_fri"].set(A.VALORES_DEFECTO["m_fri"])

    # Un proyecto con un valor de lista invalido debe avisar, NUNCA cargarse
    # a medias: si el combo conservara el valor previo, el usuario calcularia
    # otro caso sin enterarse.
    avisos.clear()
    fluido_previo = win.form.campos["fluido_cal"].var.get()
    try:
        win.form.cargar({"fluido_cal": "Plutonio fundido"})
        check(False, "un fluido desconocido en un .he se reporta")
    except Exception as exc:
        check(type(exc).__name__ == "CampoInvalido"
              and win.form.campos["fluido_cal"].var.get() == fluido_previo,
              "un fluido desconocido en un .he se reporta y no se aplica",
              f"{type(exc).__name__}")

    # Cada ejemplo distribuido debe usar las etiquetas canonicas exactas, o la
    # GUI las descartaria al cargarlas en los menus desplegables.
    from src.gui import io_state as _io
    from src.core.thermo_data import ThermoDatabase as _DB
    canon = set(_DB().list_fluids())
    malos = []
    for archivo in sorted(os.listdir(A.DIR_EJEMPLOS)):
        if not archivo.endswith(_io.EXTENSION):
            continue
        datos = _io.abrir(os.path.join(A.DIR_EJEMPLOS, archivo))
        for clave in ("fluido_cal", "fluido_fri"):
            if datos.get(clave) not in canon:
                malos.append(f"{archivo}:{clave}={datos.get(clave)!r}")
    check(not malos, "los ejemplos usan las etiquetas de fluido canónicas",
          "; ".join(malos))

    # Boton de ajuste del espaciado de baffles.
    win._calcular_sizing()
    win.update()
    B_antes = win.form.campos["baffle_mm"].var.get()
    win._ajustar_baffle()
    check(win.form.campos["baffle_mm"].var.get() != B_antes,
          "el boton «1/2 D_s» ajusta el espaciado de baffles")

    # --- fluidez: cálculo en segundo plano (botones / F5 / F6) ------------
    import time as _t
    avisos.clear()
    win.form.campos["m_cal"].set(A.VALORES_DEFECTO["m_cal"])
    win._calcular_async("sizing")
    limite = _t.monotonic() + 30.0
    while win._trabajo is not None and _t.monotonic() < limite:
        win.update()
        _t.sleep(0.02)
    win.update()
    graves = [a for a in avisos if a[0] in ("showwarning", "showerror")]
    check(win._trabajo is None and len(win.tbl_termico.get_children()) > 10,
          "el cálculo en segundo plano (F5) completa y pinta los resultados",
          str(graves))
    check(not graves, "el cálculo en segundo plano no lanza errores", str(graves))
    check(win.cget("cursor") == "",
          "el cursor vuelve a la normalidad tras el cálculo")

    # --- fluidez: redibujado del canvas con debounce ----------------------
    win._ir_a_vista("2 · Distribución de tubos")
    win.update()
    items_antes = len(win.canvas.find_all())
    win._al_redimensionar_canvas()
    win._al_redimensionar_canvas()          # dos eventos seguidos = 1 pintada
    check(win._job_redibujo is not None,
          "el redibujado por resize queda diferido (debounce)")
    _t.sleep(0.25)
    win.update()
    check(win._job_redibujo is None and len(win.canvas.find_all()) == items_antes,
          "tras el debounce se pinta una sola vez y el dibujo queda completo",
          f"items {items_antes} -> {len(win.canvas.find_all())}")

    win.destroy()


# =============================================================================
# 7. EJEMPLOS DISTRIBUIDOS
# =============================================================================
def probar_ejemplos() -> None:
    bloque("7. Proyectos de ejemplo (carpeta ejemplos/)")
    from src.gui import controller as ctrl, io_state
    from src.gui.app import DIR_EJEMPLOS, VALORES_DEFECTO

    if not os.path.isdir(DIR_EJEMPLOS):
        check(False, "existe la carpeta ejemplos/")
        return
    archivos = sorted(a for a in os.listdir(DIR_EJEMPLOS)
                      if a.endswith(io_state.EXTENSION))
    check(len(archivos) >= 4, f"hay {len(archivos)} proyectos de ejemplo")

    for archivo in archivos:
        ruta = os.path.join(DIR_EJEMPLOS, archivo)
        try:
            crudo = io_state.abrir(ruta)
            datos = {}
            for clave, valor in crudo.items():
                if clave in ("fluido_cal", "fluido_fri", "lado_tubos", "layout",
                             "n_pasos", "mat_tubo", "tipo_carcasa",
                             "cab_frontal", "cab_trasero", "mat_carcasa"):
                    datos[clave] = valor
                else:
                    datos[clave] = float(valor) if str(valor).strip() else None
            faltan = set(VALORES_DEFECTO) - set(datos)
            if faltan:
                check(False, f"{archivo}: completo", f"faltan {faltan}")
                continue
            r = ctrl.correr_sizing(datos)
            m = ctrl.correr_mecanico(datos, r.D_s, r.N_tt, r.T_h_out, r.T_c_out)
            adv = len(r.advertencias) + len(m.advertencias)
            check(adv == 0,
                  f"{archivo}: q={r.q/1000:.0f} kW, {r.N_tt} tubos, "
                  f"D_s={r.D_s*1000:.0f} mm, sin advertencias",
                  f"{adv} advertencias")
        except Exception as exc:
            check(False, f"{archivo}: calcula sin error",
                  f"{type(exc).__name__}: {exc}")


# =============================================================================
# 8. ROBUSTEZ
# =============================================================================
def probar_robustez() -> None:
    bloque("8. Robustez: barrido amplio de entradas")
    from src.gui import controller as ctrl
    from src.gui.app import VALORES_DEFECTO
    base = dict(VALORES_DEFECTO)
    base["tout_fri"] = None

    casos = completos = 0
    crashes = []
    for fcal in ("Agua", "Etanol", "Metanol", "Etilenglicol", "Benceno",
                 "Tolueno", "Aire", "n-Hexano"):
        for m_cal in (5.0, 20.0, 40.0):
            for L in (2.44, 3.66, 4.88):
                for pasos in ("1", "2", "4"):
                    casos += 1
                    d = dict(base, fluido_cal=fcal, m_cal=m_cal,
                             m_fri=2*m_cal, long_m=L, n_pasos=pasos)
                    try:
                        r = ctrl.correr_sizing(d)
                        d["baffle_mm"] = round(r.D_s * 500.0, 1)
                        r = ctrl.correr_sizing(d)
                        ctrl.correr_mecanico(d, r.D_s, r.N_tt,
                                             r.T_h_out, r.T_c_out)
                        completos += 1
                    except ValueError:
                        pass                      # rechazo controlado: correcto
                    except Exception as exc:
                        crashes.append(f"{fcal}/{m_cal}/{L}/{pasos}: "
                                       f"{type(exc).__name__}: {exc}")
    print(f"   ({completos} de {casos} combinaciones producen un diseno "
          f"completo; el resto son rechazos razonados)")
    check(not crashes, f"ninguna de las {casos} combinaciones provoca un crash",
          "; ".join(crashes[:3]))
    check(completos > casos * 0.4,
          f"al menos el 40 % de las combinaciones completa el diseno "
          f"({100*completos/casos:.0f} %)")


# =============================================================================
def main() -> int:
    print("=" * 68)
    print("VERIFICACION DEL SOFTWARE DE INTERCAMBIADORES DE TUBOS Y CORAZA")
    print("=" * 68)
    for prueba in (probar_core, probar_calculo, probar_errores,
                   probar_tipos_tema, probar_laminar, probar_gui,
                   probar_ejemplos, probar_robustez):
        try:
            prueba()
        except Exception as exc:
            import traceback
            fallos.append(prueba.__name__)
            print(f"   [FALLA] el bloque {prueba.__name__} se interrumpio:")
            print("   " + traceback.format_exc(limit=4).replace("\n", "\n   "))

    print("\n" + "=" * 68)
    if fallos:
        print(f"RESULTADO: {len(fallos)} FALLA(S) de {pruebas[0]} pruebas\n")
        for f in fallos:
            print(f"   - {f}")
        return 1
    print(f"RESULTADO: TODO CORRECTO  ({pruebas[0]} pruebas superadas)")
    print("El programa esta listo para usarse y exponerse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
