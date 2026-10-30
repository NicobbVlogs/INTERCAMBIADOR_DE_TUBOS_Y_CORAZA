# -*- coding: utf-8 -*-
# © 2026 Diego Nicolás Bohórquez Barón · propiedad intelectual del autor.
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
  5. GUI       - la ventana se construye, calcula, dibuja y guarda/abre .bb.
  6. Ejemplos  - los proyectos .bb distribuidos siguen siendo validos.
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

    bloque("3b. Novedades v2.1 (parches 5.1-5.3 del informe de auditoria)")

    # Caídas de presión acopladas tubos/coraza (Kern, cap. 7).
    check(0 < r.dp_t < 1e6 and 0 < r.dp_s < 1e6,
          f"Δp del sizing positivas y finitas (tubos {r.dp_t:,.0f} Pa, "
          f"coraza {r.dp_s:,.0f} Pa)")
    check(0 < r.f_t < 2.0 and 0 < r.f_s < 2.0,
          f"factores de friccion fisicos (f_t = {r.f_t:.4f}, f_s = {r.f_s:.4f})")
    check(0 < rt.dp_t < 1e6 and 0 < rt.dp_s < 1e6,
          f"Δp del rating (tubos {rt.dp_t:,.0f} Pa, coraza {rt.dp_s:,.0f} Pa)")

    # Jerarquia de ensuciamiento TEMA: R_f usuario > tabla fluido > material/2.
    from src.thermo.sizing import (
        ShellGeometry, Stream, TubeGeometry, dimensionar,
        lmtd_contracorriente, resistencia_ensuciamiento)
    metal_c = db.get_material("Cobre")
    agua_s = Stream(fluido="Agua", m_dot=1.0, T_in=20.0)
    check(abs(resistencia_ensuciamiento(agua_s, metal_c.R_f)
              - db.get_fouling("Agua")) < 1e-12,
          "sin R_f del usuario, el ensuciamiento sale de la tabla TEMA")
    agua_rf = Stream(fluido="Agua", m_dot=1.0, T_in=20.0, R_f=5.0e-4)
    check(resistencia_ensuciamiento(agua_rf, metal_c.R_f) == 5.0e-4,
          "un R_f del usuario tiene prioridad sobre la tabla")
    raro = Stream(fluido="Fluido sin tabla", m_dot=1.0, T_in=20.0)
    check(abs(resistencia_ensuciamiento(raro, metal_c.R_f)
              - 0.5 * metal_c.R_f) < 1e-12,
          "sin tabla, el respaldo es la mitad del R_f del material")
    try:
        resistencia_ensuciamiento(
            Stream(fluido="Agua", m_dot=1.0, T_in=20.0, R_f=-1.0), metal_c.R_f)
        check(False, "el ensuciamiento negativo se rechaza", "no lanzo excepcion")
    except ValueError as exc:
        check(len(str(exc)) > 25,
              "el ensuciamiento negativo se rechaza explicando")

    # LMTD: singularidad R = 1 sin 0/0 y continuidad en el borde.
    check(abs(lmtd_contracorriente(100.0, 60.0, 10.0, 50.0) - 50.0) < 1e-9,
          "LMTD con R = 1 devuelve el limite dT = 50 C (sin 0/0)")
    check(abs(lmtd_contracorriente(100.0, 60.0, 10.0, 50.0 + 1e-5) - 50.0) < 1e-3,
          "LMTD es continua cuando dT1 ~ dT2")

    # Conteo de baffles robusto ante coma flotante (0.6/0.2 = 2.9999...).
    haz_p = TubeGeometry(D_o=0.01905, espesor=0.00165, P_T=0.0254, L=0.6,
                         layout=30, n_pasos=2, material="Cobre")
    agua_p = Stream(fluido="Agua", m_dot=1.0, T_in=30.0, T_out=40.0)
    caliente_p = Stream(fluido="Agua", m_dot=1.0, T_in=60.0, T_out=None)
    r_p = dimensionar(caliente=caliente_p, fria=agua_p, tubos=haz_p,
                      coraza=ShellGeometry(B=0.2, tipo="E"))
    check(r_p.N_baffles == 2,
          f"0.6 m / 0.2 m da 3 tramos -> 2 baffles (sin epsilon daba "
          f"{r_p.N_baffles + 1})")

    # Carcasas TEMA F: 2 pasadas de coraza -> A_s dividida y n_corazas = 2.
    from src.thermo.rating import ExchangerGeometry
    geom_E = ExchangerGeometry(tubos=haz_p, coraza=ShellGeometry(B=0.2, tipo="E"),
                               N_tt=50, D_s=0.4)
    geom_F = ExchangerGeometry(tubos=haz_p, coraza=ShellGeometry(B=0.2, tipo="F"),
                               N_tt=50, D_s=0.4)
    check(geom_F.n_corazas == 2 and geom_E.n_corazas == 1,
          "TEMA F cuenta 2 pasadas de coraza; E cuenta 1")
    check(abs(2.0 * geom_F.a_flujo_coraza - geom_E.a_flujo_coraza) < 1e-12,
          "en F el area de flujo cruzado se divide entre las 2 pasadas")

    # Verificacion hidraulica: limites permisibles de Δp cargados por el usuario.
    r_lim = ctrl.correr_sizing(dict(d, dp_t_max=1.0, dp_s_max=1.0))
    check(any("permisible" in a for a in r_lim.advertencias),
          "una Δp por encima del limite permisible genera advertencia")
    check(not any("permisible" in a for a in r.advertencias),
          "sin limite cargado no se emite esa advertencia")
    rt_lim = ctrl.correr_rating(dict(d2, dp_s_max=1.0))
    check(any("permisible" in a for a in rt_lim.advertencias),
          "el rating tambien advierte cuando se supera el limite")

    # Proyectos de rating (sin T de salida): F5 debe redirigir al rating.
    check(ctrl.modo_calculo(dict(d, tout_cal=None, tout_fri=None)) == "rating",
          "sin ninguna T de salida el proyecto se detecta como rating (F6)")
    check(ctrl.modo_calculo(d) == "sizing",
          "con una T de salida el proyecto sigue siendo sizing (F5)")

    # Checklist de verificacion adaptado al modo (sizing vs rating).
    ver_s = ctrl.verificaciones_diseno("sizing", d, r)
    ver_r = ctrl.verificaciones_diseno("rating", d2, rt)
    nombres_s = {n for n, _, _ in ver_s}
    nombres_r = {n for n, _, _ in ver_r}
    check(any("obre-área" in n for n in nombres_s)
          and not any("fectividad" in n for n in nombres_s),
          "el checklist de sizing valida la propuesta (sobre-área, sin efectividad)")
    check(any("fectividad" in n for n in nombres_r)
          and not any("obre-área" in n for n in nombres_r),
          "el checklist de rating valida la evaluacion (efectividad, sin sobre-área)")
    check(all(e in ("OK", "AVISO") for _, e, _ in ver_s + ver_r),
          "todas las verificaciones devuelven OK o AVISO")
    ver_dp = ctrl.verificaciones_diseno("sizing", dict(d, dp_t_max=1.0),
                                        ctrl.correr_sizing(dict(d, dp_t_max=1.0)))
    check(any("Δp en tubos" in n and e == "AVISO" for n, e, _ in ver_dp),
          "superar el limite de Δp marca AVISO en el checklist del modo")

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
# 5d. METODO DE BELL-DELAWARE (lado coraza)
# =============================================================================
def probar_bell_delaware() -> None:
    bloque("5d. Bell-Delaware: continuidad, factores y ejecucion")
    from src.thermo.bell_delaware import (j_ideal, f_ideal,
                                          lado_coraza_bell_delaware)
    from src.gui import controller as ctrl
    from src.gui.app import VALORES_DEFECTO

    PT, DO = 0.0238125, 0.01905
    saltos_j = []
    for borde in (1e4, 1e3, 1e2, 1e1):
        a = j_ideal(borde * 0.999, PT, DO, 30)
        c = j_ideal(borde * 1.001, PT, DO, 30)
        saltos_j.append(abs(c - a) / a)
    check(max(saltos_j) < 0.10,
          f"j_i continua en los bordes de la tabla Taborek "
          f"(salto maximo {max(saltos_j)*100:.1f} %)")

    r = lado_coraza_bell_delaware(
        m_dot=21.98, rho=996.0, mu=8.0e-4, cp=4180.0, k=0.61, mu_w=7.0e-4,
        D_s=0.40005, D_o=DO, P_T=PT, B=0.3048, layout=30,
        N_tt=160, N_baffles=15, corte=0.25, L_tubo=4.8768)
    check(0.53 <= r["J_c"] <= 1.15, f"J_c = {r['J_c']:.3f} en el rango 0.53-1.15")
    check(0.65 <= r["J_l"] <= 0.85, f"J_l = {r['J_l']:.3f} en el rango tipico 0.7-0.8")
    check(0.65 <= r["J_b"] <= 0.92, f"J_b = {r['J_b']:.3f} en el rango tipico 0.7-0.9")
    check(0.45 <= r["J_c"] * r["J_l"] * r["J_b"] * r["J_r"] <= 0.85,
          f"producto Jc*Jl*Jb*Jr = {r['J_c']*r['J_l']*r['J_b']*r['J_r']:.2f} "
          f"(intercambiador bien disenado ~0.6)")
    check(4000.0 < r["h_o"] < 9000.0,
          f"h_o = {r['h_o']:.0f} W/m2K coherente para agua en el Ej. 7.4")
    check(r["dp_s"] > 0.0, f"dp_s = {r['dp_s']:.0f} Pa positiva")

    base = dict(VALORES_DEFECTO, tout_fri=None, fluido_cal="Agua",
                m_cal=21.98, tin_cal=33.89, tout_cal=29.44, m_fri=35.2,
                tin_fri=23.89, long_m=4.8768, baffle_mm=304.8, n_pasos="2")
    r_kern = ctrl.correr_sizing(dict(base, metodo_coraza="kern"))
    r_bd = ctrl.correr_sizing(dict(base, metodo_coraza="bell_delaware"))
    check(r_bd.U > 0 and r_bd.h_o > 0 and r_bd.dp_s > 0,
          f"el sizing con Bell-Delaware converge: U = {r_bd.U:.0f} W/m2K, "
          f"h_o = {r_bd.h_o:.0f}, dp_s = {r_bd.dp_s:.0f} Pa")
    check(0.5 < r_bd.h_o / r_kern.h_o < 2.0,
          f"h_o Bell-Delaware/Kern = {r_bd.h_o/r_kern.h_o:.2f} "
          f"(los metodos deben coincidir en orden de magnitud)")
    check(r_bd.metodo_coraza == "bell_delaware" and r_kern.metodo_coraza == "kern",
          "el resultado registra el metodo de coraza usado")
    from src.thermo.sizing import resolver_metodo_coraza
    check(resolver_metodo_coraza("auto", 1.0e5) == "bell_delaware",
          "auto elige Bell-Delaware cuando Taborek cubre el Re de coraza")
    check(resolver_metodo_coraza("auto", 1.0e7) == "kern",
          "auto cae a Kern fuera de la tabla de Taborek")
    check(resolver_metodo_coraza("kern", 1.0e5) == "kern",
          "un metodo explicito se respeta tal cual")
    r_def = ctrl.correr_sizing(dict(base))
    check(abs(r_def.U - r_bd.U) < 1e-9 and r_def.metodo_coraza == "bell_delaware",
          f"sin metodo declarado el sizing usa el automatico: Bell-Delaware "
          f"(U = {r_def.U:.1f} W/m2K identico al explicito)")
    check(r_bd.U != r_kern.U,
          f"Bell-Delaware produce un resultado distinto de Kern "
          f"(U = {r_bd.U:.1f} vs {r_kern.U:.1f} W/m2K)")


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

    # Boton «1/2·D_s»: cierra a mano el lazo B <-> D_s (B es entrada, D_s es
    # resultado y la ventana TEMA de B depende de el).
    win.form.campos["baffle_mm"].set(250.0)
    win._ajustar_baffle()
    check(win.form.campos["baffle_mm"].get() == round(win.ultimo_D_s * 500.0, 1),
          "el boton 1/2·D_s ajusta B a 0.5·D_s tras un calculo")
    D_s_previo = win.ultimo_D_s
    win.ultimo_D_s = None
    win.form.campos["baffle_mm"].set(250.0)
    avisos.clear()
    win._ajustar_baffle()
    check(bool(avisos) and win.form.campos["baffle_mm"].get() == 250.0,
          "sin calculo previo el boton explica y no toca el campo")
    win.ultimo_D_s = D_s_previo

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

    # Guardado y lectura de un proyecto .bb.
    ruta = os.path.join(tempfile.gettempdir(), "_verificar_tmp.bb")
    win._escribir(ruta)
    win.form.campos["m_cal"].set(999.0)
    from src.gui import io_state
    win.form.cargar(io_state.abrir(ruta))
    check(win.form.campos["m_cal"].var.get() == str(A.VALORES_DEFECTO["m_cal"]),
          "ida y vuelta de un proyecto .bb")
    os.remove(ruta)

    # Validacion de formulario: campo obligatorio vacio.
    avisos.clear()
    win.form.campos["m_fri"].set("")
    win._calcular_sizing()
    win.update()
    check(bool(avisos) and win.form.campos["m_fri"].en_error,
          "campo vacio: avisa y lo resalta en rojo")
    win.form.campos["m_fri"].set(A.VALORES_DEFECTO["m_fri"])

    # Un proyecto con un valor de lista invalido debe avisar, NUNCA cargarse
    # a medias: si el combo conservara el valor previo, el usuario calcularia
    # otro caso sin enterarse.
    avisos.clear()
    fluido_previo = win.form.campos["fluido_cal"].var.get()
    try:
        win.form.cargar({"fluido_cal": "Plutonio fundido"})
        check(False, "un fluido desconocido en un .bb se reporta")
    except Exception as exc:
        check(type(exc).__name__ == "CampoInvalido"
              and win.form.campos["fluido_cal"].var.get() == fluido_previo,
              "un fluido desconocido en un .bb se reporta y no se aplica",
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
# Avisos esperados por ejemplo: 0 salvo los casos de referencia de Tan & Fok,
# cuya geometria impuesta por el articulo los provoca de forma reproducible
# (baja velocidad por continuidad, regimen no turbulento). Declararlos aqui
# permite seguir detectando cualquier aviso NUEVO en cualquier ejemplo.
AVISOS_ESPERADOS = {
    "09_sinnott_metanol_agua_sizing.bb": 2,
    "10_karimi_metanol_agua_mar_sizing.bb": 1,
    "11_janna_agua_agua_sizing.bb": 1,
    "12_kern_ej74_agua_agua_sizing.bb": 1,
    "13_janna_agua_agua_rating.bb": 2,
    "14_kern_ej74_agua_agua_rating.bb": 1,
    "15_msubbu_metanol_agua_rating.bb": 2,
    "16_karimi_metanol_agua_mar_rating.bb": 1,
    "06_tan_fok_sizing.bb": 8,
    "07_tan_fok_rating.bb": 4,
    "08_tan_fok_rating_parcial.bb": 4,
}


def probar_ejemplos() -> None:
    bloque("7. Proyectos de ejemplo (carpeta ejemplos/)")
    from src.gui import controller as ctrl, io_state
    from src.gui.app import DIR_EJEMPLOS, VALORES_DEFECTO

    if not os.path.isdir(DIR_EJEMPLOS):
        check(False, "existe la carpeta ejemplos/")
        return
    # Los ejemplos estan divididos por modo: ejemplos/sizing y ejemplos/rating.
    archivos = sorted(
        os.path.relpath(os.path.join(raiz, a), DIR_EJEMPLOS).replace("\\", "/")
        for raiz, _, nombres in os.walk(DIR_EJEMPLOS)
        for a in nombres if a.endswith(io_state.EXTENSION))
    check(len(archivos) >= 8, f"hay {len(archivos)} proyectos de ejemplo")
    check(any(a.startswith("sizing/") for a in archivos)
          and any(a.startswith("rating/") for a in archivos),
          "los ejemplos estan divididos en sizing y rating")

    for archivo in archivos:
        ruta = os.path.join(DIR_EJEMPLOS, archivo)
        try:
            crudo = io_state.abrir(ruta)
            datos = {}
            for clave, valor in crudo.items():
                if clave in ("fluido_cal", "fluido_fri", "lado_tubos", "layout",
                             "n_pasos", "mat_tubo", "tipo_carcasa",
                             "cab_frontal", "cab_trasero", "mat_carcasa",
                             "metodo_coraza"):
                    datos[clave] = valor
                else:
                    datos[clave] = (float(valor)
                    if valor is not None and str(valor).strip()
                    else None)
            faltan = set(VALORES_DEFECTO) - set(datos)
            if faltan:
                check(False, f"{archivo}: completo", f"faltan {faltan}")
                continue
            # Los casos de referencia de Tan & Fok no llevan temperatura de
            # salida: son de rating (la geometria del articulo es la entrada).
            if datos["tout_fri"] is None and datos["tout_cal"] is None:
                r = ctrl.correr_rating(datos)
                n_tt, d_s = int(datos["n_tt"]), datos["d_s_mm"] / 1000.0
            else:
                r = ctrl.correr_sizing(datos)
                n_tt, d_s = r.N_tt, r.D_s
            m = ctrl.correr_mecanico(datos, d_s, n_tt, r.T_h_out, r.T_c_out)
            adv = len(r.advertencias) + len(m.advertencias)
            esperados = AVISOS_ESPERADOS.get(os.path.basename(archivo), 0)
            check(adv == esperados,
                  f"{archivo}: q={r.q/1000:.0f} kW, {n_tt} tubos, "
                  f"D_s={d_s*1000:.0f} mm, "
                  + ("sin advertencias" if adv == 0
                     else f"{adv} advertencias esperadas"),
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
# 6b. APERTURA DE EJEMPLOS EN LA GUI Y COHERENCIA DE LOS MENSAJES
# =============================================================================
def probar_ejemplos_gui() -> None:
    bloque("6b. Apertura de los 11 ejemplos en la GUI y avisos segun el metodo")
    from tkinter import messagebox
    from src.core.errores import ErrorDiseno
    from src.gui import app as A
    from src.gui import controller as ctrl
    from src.gui import io_state

    campos_texto = ("fluido_cal", "fluido_fri", "lado_tubos", 
                    "layout", "n_pasos", "mat_tubo", "tipo_carcasa", 
                    "cab_frontal", "cab_trasero", "mat_carcasa", 
                    "metodo_coraza")

    avisos = []
    for nombre in ("showinfo", "showwarning", "showerror"):
        setattr(messagebox, nombre,
                lambda t, m, _n=nombre: avisos.append((_n, t, m)))
    A.messagebox = messagebox

    win = A.Aplicacion()
    win.update()
    cargados = 0
    for carpeta in ("sizing", "rating"):
        ruta_grupo = os.path.join("ejemplos", carpeta)
        for archivo in sorted(os.listdir(ruta_grupo)):
            if not archivo.endswith(io_state.EXTENSION):
                continue
            avisos.clear()
            win._cargar_ejemplo(os.path.join(ruta_grupo, archivo))
            win.update()
            malos = [a for a in avisos if a[0] in ("showwarning", "showerror")]
            check(not malos,
                  f"{archivo} abre y calcula sin errores de formulario",
                  str(malos[:1]))
            cargados += 1
    check(cargados == 11, f"los 11 ejemplos cargan por la ruta real de la GUI "
                          f"({cargados} cargados)")

    # Los combos aceptan variantes de mayusculas y normalizan al canonico.
    campo = win.form.campos["fluido_cal"]
    check(campo.set("agua") and campo.get() == "Agua",
          "los combos normalizan 'agua' -> 'Agua' (los .bb antiguos abren)")
    check(not campo.set("agua sucia"),
          "un valor que no existe sigue rechazandose")

    # El rating exige la geometria del equipo con un error educativo.
    base = dict(A.VALORES_DEFECTO)
    try:
        ctrl.correr_rating(dict(base, n_tt=None, d_s_mm=None))
        check(False, "el rating sin N_tt/D_s debe rechazarse")
    except ErrorDiseno as exc:
        check("geometría del equipo existente" in exc.titulo,
              "el rating sin geometria explica que falta (ErrorDiseno educativo)")

    # Los mensajes de incertidumbre nombran el metodo realmente usado.
    crudo = io_state.abrir("ejemplos/sizing/06_tan_fok_sizing.bb")
    texto = {}
    bandas = {}
    aplicado = {}
    for etiqueta in ("kern", "bell_delaware"):
        d = {}
        for k, v in crudo.items():
            d[k] = (v if k in campos_texto else
                    (float(v) if v is not None and str(v).strip() else None))
        d["metodo_coraza"] = etiqueta
        r = ctrl.correr_sizing(d)
        texto[etiqueta] = " ".join(r.advertencias)
        bandas[etiqueta] = [a for a in r.advertencias
                            if "banda de incertidumbre" in a]
        aplicado[etiqueta] = r.metodo_coraza
    check("usó el método de Kern en la coraza" in texto["kern"],
          "con Kern el aviso identifica el metodo usado sin instrucciones manuales")
    check(aplicado["bell_delaware"] == "bell_delaware",
          "el metodo Bell-Delaware llega realmente al motor")
    no_recomienda = all("viene incluido en el programa" not in a
                        for a in bandas["bell_delaware"])
    check(no_recomienda and all("ya se calcula con Bell-Delaware" in a
                                for a in bandas["bell_delaware"]),
          "con Bell-Delaware el aviso NO recomienda el metodo ya en uso "
          "(o no hay aviso porque la banda ya es la base de 15 %)",
          str(bandas["bell_delaware"]))
    check("la banda la fija el lado" in texto["kern"],
          "el aviso indica que lado fija la banda de incertidumbre")
    win.destroy()


# =============================================================================
def main() -> int:
    print("=" * 68)
    print("VERIFICACION DEL SOFTWARE DE INTERCAMBIADORES DE TUBOS Y CORAZA")
    print("=" * 68)
    for prueba in (probar_core, probar_calculo, probar_errores,
                   probar_tipos_tema, probar_laminar, probar_bell_delaware,
                   probar_gui, probar_ejemplos_gui,
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
