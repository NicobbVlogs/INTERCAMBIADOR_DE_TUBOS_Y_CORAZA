# -*- coding: utf-8 -*-
"""Mide el arranque hasta ventana NUEVA, y limpia el arbol de procesos propio."""
import ctypes
import subprocess
import sys
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

EXE_ONEFILE = (r"C:\Users\nicol\OneDrive\Escritorio\proyecto intermedio"
               r"\02_ejecutable\IntercambiadorDeTubosYCoraza.exe")


def ventanas():
    out = {}

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if "intercambiador" in buf.value.lower():
            out[hwnd] = buf.value
        return True

    user32.EnumWindows(cb, 0)
    return out


def cerrar_todo_lo_reciente():
    recientes = []
    for hwnd in list(ventanas()):
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)
        if h:
            creacion = ctypes.c_ulonglong()
            if kernel32.GetProcessTimes(h, ctypes.byref(creacion),
                                        ctypes.byref(ctypes.c_ulonglong()),
                                        ctypes.byref(ctypes.c_ulonglong()),
                                        ctypes.byref(ctypes.c_ulonglong())):
                ahora = ctypes.c_ulonglong()
                kernel32.GetSystemTimeAsFileTime(ctypes.byref(ahora))
                edad = (ahora.value - creacion.value) / 1e7
                if edad < 1800:
                    recientes.append(pid.value)
            kernel32.CloseHandle(h)
    for pid in set(recientes):
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True)
    time.sleep(1.0)
    return len(set(recientes))


def medir(ruta):
    previas = set(ventanas())
    t0 = time.time()
    proc = subprocess.Popen([ruta])
    nueva = None
    while time.time() - t0 < 120:
        if set(ventanas()) - previas:
            nueva = time.time() - t0
            break
        time.sleep(0.02)
    subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                   capture_output=True)
    t1 = time.time()
    while (set(ventanas()) - previas) and time.time() - t1 < 30:
        time.sleep(0.1)
    return nueva


if __name__ == "__main__":
    cerrados = cerrar_todo_lo_reciente()
    print(f"ventanas huerfanas propias cerradas: {cerrados}")
    ruta = sys.argv[1] if len(sys.argv) > 1 else EXE_ONEFILE
    etiqueta = sys.argv[2] if len(sys.argv) > 2 else "onefile"
    print(f"== {etiqueta} ==")
    for i in range(3):
        t = medir(ruta)
        print(f"  lanzamiento {i+1}: {t:.2f} s" if t else "  ventana no detectada")
