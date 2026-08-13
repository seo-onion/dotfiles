#!/usr/bin/env python3
# Panel de bateria estilo swaync, cuarto gemelo (wifi/bluetooth/audio).
# Estado upower, perfiles de energia (tuned via D-Bus UPower.PowerProfiles),
# limite de carga (sysfs, boton 100% via pkexec), brillo pantalla/teclado,
# salud, bateria de perifericos y ultimos picos de CPU del cpu-spike-logger.
# Glifos como escapes \U000f... a proposito (ver ESCRITORIO.md).

import os
import re
import signal
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib, Gdk, Pango

PIDFILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'battery-panel.pid')
ANCHO = 460
PANTALLA = 1920
MARGEN = 16
ICONO_X_FALLBACK = 1750
THRESHOLD = '/sys/class/power_supply/BAT0/charge_control_end_threshold'
SPIKELOG = '/var/log/cpu-spikes.log'
BAT0 = '/org/freedesktop/UPower/devices/battery_BAT0'

I_BAT = '\U000f0079'
I_PANTALLA = '\U000f00e0'
I_TECLADO = '\U000f030c'
I_CHIP = '\U000f0ee0'
PERFILES = [
    ('power-saver', 'Ahorro', '\U000f0335'),
    ('balanced', 'Neutro', '\U000f0241'),
    ('performance', 'Rendimiento', '\U000f04c5'),
]
ICONOS_PERIF = {
    'headset': '\U000f02cb', 'headphone': '\U000f02cb',
    'mouse': '\U000f037d', 'keyboard': '\U000f030c', 'phone': '\U000f011c',
}
ESTADOS = {
    'charging': 'cargando', 'discharging': 'descargando',
    'fully-charged': 'cargada', 'pending-charge': 'en espera (límite)',
}

CSS = b"""
* {
    font-family: "JetBrainsMono Nerd Font", monospace;
    font-size: 14px;
    font-weight: bold;
}
window { background: transparent; }
.panel {
    background-color: transparent;
    background-image:
        linear-gradient(rgba(5, 5, 10, 0.96), rgba(5, 5, 10, 0.96)),
        linear-gradient(45deg, #33CCFF, #00FF99);
    background-origin: border-box;
    background-clip: padding-box, border-box;
    border: 2px solid transparent;
    border-radius: 4px;
    color: #E2E8F0;
    padding: 12px;
}
.titulo { color: #00F0FF; }
.sutil  { color: rgba(226, 232, 240, 0.55); font-size: 12px; }
.seccion {
    color: #33CCFF;
    font-size: 12px;
    border-bottom: 1px solid rgba(0, 240, 255, 0.25);
    padding-bottom: 2px;
}
.grande { color: #FFFFFF; font-size: 20px; }
.verde { color: #00FF99; }
button {
    background: transparent;
    color: #E2E8F0;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 2px 8px;
    box-shadow: none;
}
button:hover { color: #00F0FF; border-bottom: 2px solid #00F0FF; }
button.tab { color: rgba(226, 232, 240, 0.55); font-size: 12px; }
button.tab.activa { color: #00F0FF; border-bottom: 2px solid #00F0FF; }
scale { padding: 0; }
scale trough {
    background: rgba(11, 19, 43, 0.9);
    border: none;
    min-height: 6px;
    border-radius: 3px;
}
scale highlight { background: #00F0FF; border-radius: 3px; }
scale slider {
    background: #E2E8F0;
    border: none;
    box-shadow: none;
    min-width: 12px;
    min-height: 12px;
    margin: -5px;
    border-radius: 6px;
}
"""


def sh(*args, timeout=10):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ''


def upower(ruta):
    datos = {}
    for linea in sh('upower', '-i', ruta).splitlines():
        if ':' in linea:
            k, v = linea.split(':', 1)
            datos[k.strip()] = v.strip()
    return datos


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'battery-panel')
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        for borde in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                      GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self, borde, True)

        self.set_app_paintable(True)
        visual = self.get_screen().get_rgba_visual()
        if visual:
            self.set_visual(visual)

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.caja.get_style_context().add_class('panel')
        self.caja.set_size_request(ANCHO - 28, -1)
        self.caja.set_halign(Gtk.Align.START)
        self.caja.set_valign(Gtk.Align.START)
        self.caja.set_margin_start(self._margen_izq())
        self.caja.set_margin_top(MARGEN)
        self.add(self.caja)

        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect('button-press-event', self._clic_fuera)
        self.connect('key-press-event', self._tecla)

        titulo = Gtk.Label(label=f'{I_BAT}  Batería', xalign=0)
        titulo.get_style_context().add_class('titulo')
        self.caja.pack_start(titulo, False, False, 0)

        self._armar()
        self._timers, self._pend = {}, {}
        self._actualizando = False
        self._refrescar()
        # el consumo en W cambia todo el rato: repintar cada 5s mientras este abierto
        GLib.timeout_add_seconds(5, lambda: (self._refrescar(), True)[1])

    def _margen_izq(self):
        try:
            out = subprocess.run(['hyprctl', 'cursorpos'], capture_output=True,
                                 text=True, timeout=2).stdout
            x = int(out.split(',')[0])
        except (ValueError, IndexError, subprocess.TimeoutExpired):
            x = ICONO_X_FALLBACK
        return max(MARGEN, min(x - ANCHO // 2, PANTALLA - ANCHO - MARGEN))

    def _seccion(self, texto):
        lbl = Gtk.Label(label=texto, xalign=0)
        lbl.get_style_context().add_class('seccion')
        self.caja.pack_start(lbl, False, False, 2)

    def _armar(self):
        self._seccion('Estado')
        self.lbl_pct = Gtk.Label(label='', xalign=0)
        self.lbl_pct.get_style_context().add_class('grande')
        self.lbl_detalle = Gtk.Label(label='', xalign=0)
        self.lbl_detalle.get_style_context().add_class('sutil')
        self.caja.pack_start(self.lbl_pct, False, False, 0)
        self.caja.pack_start(self.lbl_detalle, False, False, 0)

        self._seccion('Perfil de energía')
        tabs = Gtk.Box(spacing=4)
        tabs.set_halign(Gtk.Align.CENTER)
        self.botones_perfil = {}
        for clave, nombre, icono in PERFILES:
            b = Gtk.Button(label=f'{icono}  {nombre}')
            b.get_style_context().add_class('tab')
            b.connect('clicked', self._perfil, clave)
            tabs.pack_start(b, False, False, 0)
            self.botones_perfil[clave] = b
        self.caja.pack_start(tabs, False, False, 0)

        self._seccion('Límite de carga')
        fila = Gtk.Box(spacing=8)
        self.lbl_limite = Gtk.Label(label='', xalign=0)
        fila.pack_start(self.lbl_limite, True, True, 0)
        self.btn_limite = Gtk.Button(label='')
        self.btn_limite.connect('clicked', self._toggle_limite)
        fila.pack_start(self.btn_limite, False, False, 0)
        self.caja.pack_start(fila, False, False, 0)
        self.lbl_limite_nota = Gtk.Label(label='', xalign=0)
        self.lbl_limite_nota.set_line_wrap(True)
        self.lbl_limite_nota.set_max_width_chars(48)
        self.lbl_limite_nota.get_style_context().add_class('sutil')
        self.caja.pack_start(self.lbl_limite_nota, False, False, 0)

        self._seccion('Brillo')
        self.escala_pantalla = self._fila_brillo(I_PANTALLA, 1, 100)
        self.escala_teclado = self._fila_brillo(I_TECLADO, 0, 3)

        self._seccion('Salud')
        self.lbl_salud = Gtk.Label(label='', xalign=0)
        self.lbl_salud.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_salud.get_style_context().add_class('sutil')
        self.caja.pack_start(self.lbl_salud, False, False, 0)

        self.sec_perif = Gtk.Label(label='Periféricos', xalign=0)
        self.sec_perif.get_style_context().add_class('seccion')
        self.caja.pack_start(self.sec_perif, False, False, 2)
        self.caja_perif = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.caja.pack_start(self.caja_perif, False, False, 0)

        self._seccion(f'Picos de CPU recientes')
        self.lbl_picos = Gtk.Label(label='', xalign=0)
        self.lbl_picos.get_style_context().add_class('sutil')
        self.caja.pack_start(self.lbl_picos, False, False, 0)

    def _fila_brillo(self, icono, minimo, maximo):
        fila = Gtk.Box(spacing=8)
        lbl = Gtk.Label(label=icono)
        escala = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, minimo, maximo, 1)
        escala.set_draw_value(False)
        escala.set_hexpand(True)
        clave = 'pantalla' if maximo == 100 else 'teclado'
        escala.connect('value-changed', lambda e: self._debounce(clave, e.get_value()))
        fila.pack_start(lbl, False, False, 0)
        fila.pack_start(escala, True, True, 0)
        self.caja.pack_start(fila, False, False, 0)
        return escala

    # ── datos ────────────────────────────────────────────────────────────────

    def _refrescar(self):
        threading.Thread(target=self._cargar, daemon=True).start()

    def _cargar(self):
        bat = upower(BAT0)
        perfil = ''
        m = re.search(r'"(\S+)"', sh(
            'busctl', '--system', 'get-property', 'org.freedesktop.UPower.PowerProfiles',
            '/org/freedesktop/UPower/PowerProfiles',
            'org.freedesktop.UPower.PowerProfiles', 'ActiveProfile'))
        if m:
            perfil = m.group(1)

        try:
            with open(THRESHOLD) as f:
                limite = int(f.read())
        except OSError:
            limite = None

        brillo = kbd = 0
        m = re.match(r'[^,]+,[^,]+,\d+,(\d+)%', sh('brightnessctl', '-d', 'amdgpu_bl1', '-m'))
        if m:
            brillo = int(m.group(1))
        m = re.match(r'[^,]+,[^,]+,(\d+),', sh('brightnessctl', '-d', 'asus::kbd_backlight', '-m'))
        if m:
            kbd = int(m.group(1))

        perifericos = []
        for ruta in sh('upower', '-e').splitlines():
            if 'battery_BAT0' in ruta or 'line_power' in ruta or 'DisplayDevice' in ruta:
                continue
            datos = upower(ruta)
            if 'percentage' not in datos:
                continue
            icono = next((v for k, v in ICONOS_PERIF.items() if k in ruta), I_BAT)
            perifericos.append((icono, datos.get('model', '?'), datos['percentage']))

        picos = []
        try:
            with open(SPIKELOG) as f:
                for linea in f.readlines()[-400:]:
                    m = re.match(r'\[[\d-]+ (\d\d:\d\d)[^\]]*\] . SPIKE FIN\s+cpu=(\d+%)\s+duracion=(\S+)', linea)
                    if m:
                        picos.append(f'{m.group(1)}   pico {m.group(2)}   {m.group(3)}')
        except OSError:
            pass

        GLib.idle_add(self._pintar, bat, perfil, limite, brillo, kbd,
                      perifericos, picos[-3:])

    def _pintar(self, bat, perfil, limite, brillo, kbd, perifericos, picos):
        self._actualizando = True
        estado = ESTADOS.get(bat.get('state', ''), bat.get('state', '?'))
        self.lbl_pct.set_text(f"{bat.get('percentage', '?')}  ·  {estado}")
        tiempo = bat.get('time to empty') or bat.get('time to full') or ''
        tiempo = tiempo.replace(' hours', ' h').replace(' minutes', ' min')
        consumo = bat.get('energy-rate', '').replace('W', 'W').strip()
        partes = [p for p in (tiempo and f'{tiempo} restantes', consumo) if p]
        self.lbl_detalle.set_text('  ·  '.join(partes))

        for clave, boton in self.botones_perfil.items():
            ctx = boton.get_style_context()
            (ctx.add_class if clave == perfil else ctx.remove_class)('activa')

        if limite is None:
            self.lbl_limite.set_text('sin control de límite')
            self.lbl_limite_nota.set_text('')
            self.btn_limite.set_visible(False)
        elif limite <= 80:
            self.lbl_limite.set_text(f'Cargando hasta {limite}%')
            self.lbl_limite_nota.set_text(
                'Parar al 80% alarga la vida de la batería. Usa «Cargar al '
                '100%» solo para un día largo: pide contraseña y el límite '
                'vuelve al 80% al reiniciar.')
            self.btn_limite.set_label('Cargar al 100%')
            self.btn_limite.set_visible(True)
        else:
            self.lbl_limite.set_text(f'Cargando hasta {limite}%  ·  temporal')
            self.lbl_limite_nota.set_text(
                'Modo viaje: carga completa activada. Vuelve al 80% al '
                'reiniciar, o antes con el botón.')
            self.btn_limite.set_label('Volver a 80%')
            self.btn_limite.set_visible(True)

        self.escala_pantalla.set_value(brillo)
        self.escala_teclado.set_value(kbd)

        salud = bat.get('capacity', '?')
        diseno = bat.get('energy-full-design', '?')
        tec = bat.get('technology', '?')
        self.lbl_salud.set_text(f'Capacidad: {salud} de fábrica  ·  {diseno}  ·  {tec}')

        for hijo in self.caja_perif.get_children():
            self.caja_perif.remove(hijo)
        visibles = bool(perifericos)
        self.sec_perif.set_visible(visibles)
        self.caja_perif.set_visible(visibles)
        for icono, modelo, pct in perifericos:
            lbl = Gtk.Label(label=f'{icono}  {modelo}', xalign=0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            fila = Gtk.Box()
            fila.pack_start(lbl, True, True, 0)
            pl = Gtk.Label(label=pct)
            pl.get_style_context().add_class('verde')
            fila.pack_start(pl, False, False, 0)
            self.caja_perif.pack_start(fila, False, False, 0)
        if visibles:
            self.caja_perif.show_all()

        self.lbl_picos.set_text('\n'.join(picos) if picos else 'sin picos registrados')
        self._actualizando = False
        return False

    # ── acciones ─────────────────────────────────────────────────────────────

    def _perfil(self, _b, clave):
        def tarea():
            sh('busctl', '--system', 'set-property',
               'org.freedesktop.UPower.PowerProfiles',
               '/org/freedesktop/UPower/PowerProfiles',
               'org.freedesktop.UPower.PowerProfiles', 'ActiveProfile', 's', clave)
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _toggle_limite(self, _b):
        try:
            with open(THRESHOLD) as f:
                nuevo = 100 if int(f.read()) <= 80 else 80
        except OSError:
            return

        def tarea():
            # pkexec abre el dialogo de polkit; escribir el sysfs requiere root
            subprocess.run(['pkexec', 'sh', '-c', f'echo {nuevo} > {THRESHOLD}'],
                           capture_output=True, timeout=60)
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _debounce(self, clave, valor):
        if self._actualizando:
            return
        self._pend[clave] = valor
        if clave not in self._timers:
            self._timers[clave] = GLib.timeout_add(90, self._aplicar, clave)

    def _aplicar(self, clave):
        valor = int(self._pend.pop(clave))
        del self._timers[clave]
        disp = 'amdgpu_bl1' if clave == 'pantalla' else 'asus::kbd_backlight'
        arg = f'{valor}%' if clave == 'pantalla' else str(valor)
        threading.Thread(target=lambda: sh('brightnessctl', '-d', disp, 'set', arg),
                         daemon=True).start()
        return False

    def _clic_fuera(self, _w, evento):
        if Gtk.get_event_widget(evento) is not self:
            return False
        a = self.caja.get_allocation()
        if not (a.x <= evento.x <= a.x + a.width and a.y <= evento.y <= a.y + a.height):
            Gtk.main_quit()
            return True
        return False

    def _tecla(self, _w, evento):
        if evento.keyval == Gdk.KEY_Escape:
            Gtk.main_quit()
            return True
        return False


def toggle():
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE) as f:
                pid = int(f.read())
            os.kill(pid, signal.SIGTERM)
            os.unlink(PIDFILE)
            return True
        except (ValueError, ProcessLookupError):
            os.unlink(PIDFILE)
    return False


if __name__ == '__main__':
    if toggle():
        raise SystemExit
    with open(PIDFILE, 'w') as f:
        f.write(str(os.getpid()))
    try:
        panel = Panel()
        panel.connect('destroy', Gtk.main_quit)
        panel.show_all()
        Gtk.main()
    finally:
        if os.path.exists(PIDFILE):
            os.unlink(PIDFILE)
