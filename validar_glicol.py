# -*- coding: utf-8 -*-
"""Validacion del etilenglicol contra la TABLA DE LIBRO de Incropera.

Fuente: Incropera, Bergman, Lavine, DeWitt, *Fundamentals of Heat and Mass
Transfer*, Table A.5 "Thermophysical properties of saturated liquids -
Ethylene Glycol [C2H4(OH)2]" (valores tabulados de rho, cp, mu, k, Pr
en funcion de la temperatura).

Este es el mismo libro del que proceden los datos de aire y vapor de la base
(Tabla A.4). Se compara el ajuste del programa (fuente: Perry's 8.ª ed./DIPPR,
260-470 K) contra los valores tabulados del libro.
"""
import math

from src.core.thermo_data import ThermoDatabase

db = ThermoDatabase()

# Tabla A.5 de Incropera: T(K), rho(kg/m3), cp(kJ/kg.K), mu(N s/m2), k(W/m.K), Pr
INCR = [
    (273.15, 1130.8, 2.294, 6.51e-2, 0.242, 617.0),
    (280, 1125.8, 2.323, 4.20e-2, 0.244, 400.0),
    (290, 1118.8, 2.368, 2.47e-2, 0.248, 236.0),
    (300, 1114.4, 2.415, 1.57e-2, 0.252, 151.0),
    (310, 1103.7, 2.460, 1.07e-2, 0.255, 103.0),
    (320, 1096.2, 2.505, 0.757e-2, 0.258, 73.5),
    (330, 1089.5, 2.549, 0.561e-2, 0.260, 55.0),
    (340, 1083.8, 2.592, 0.431e-2, 0.261, 42.8),
    (360, 1074.0, 2.682, 0.278e-2, 0.261, 28.6),
    (370, 1066.7, 2.728, 0.228e-2, 0.262, 23.7),
    (373, 1058.5, 2.742, 0.215e-2, 0.263, 22.4),   # fila final de la tabla (100 C)
]

print("Etilenglicol: ajuste del programa vs Tabla A.5 de Incropera (libro)")
print(" T(K)  T(C)   rho ref/prog      cp        k         mu        Pr")
print(" " + "-" * 78)
dev = {"rho": [], "cp": [], "k": [], "mu": [], "Pr": []}
for T, rho, cp, mu, k, Pr in INCR:
    e = db.get_fluid_state("etilenglicol", float(T), "K")
    d_rho = 100 * (e.rho - rho) / rho
    d_cp = 100 * (e.cp - cp * 1000.0) / (cp * 1000.0)
    d_k = 100 * (e.k - k) / k
    d_mu = 100 * (e.mu - mu) / mu
    d_Pr = 100 * (e.Pr - Pr) / Pr
    dev["rho"].append(d_rho)
    dev["cp"].append(d_cp)
    dev["k"].append(d_k)
    dev["mu"].append(d_mu)
    dev["Pr"].append(d_Pr)
    print(f" {T:6.1f}  {T-273.15:6.1f}  {rho:7.1f}/{e.rho:7.1f} "
          f"{cp*1000:5.0f}/{e.cp:5.0f}  {k:.3f}/{e.k:.3f}  "
          f"{mu:.3e}/{e.mu:.3e}  {Pr:5.1f}/{e.Pr:5.1f}")

print()
for prop in ("rho", "cp", "k", "mu", "Pr"):
    vals = dev[prop]
    i_max = max(range(len(vals)), key=lambda i: abs(vals[i]))
    print(f" {prop:3s}: desviacion maxima {vals[i_max]:+.1f} % "
          f"a {INCR[i_max][0]} K; media {sum(vals)/len(vals):+.1f} %")
