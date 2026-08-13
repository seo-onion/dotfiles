#!/usr/bin/env python3
# Panel Bluetooth estilo swaync, gemelo de wifi-panel.py: superficie
# cover-screen transparente, panel centrado en el clic del icono, toggle por
# pidfile, clic fuera cierra. La animacion la pone la layer rule de hyprland.lua.
# Los glifos van como escapes \U000f... a proposito: pegados como caracteres se
# corrompen (ver ESCRITORIO.md).

import os
import re
import signal
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib, Gdk, Pango

PIDFILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'bluetooth-panel.pid')
ANCHO = 450
PANTALLA = 1920
MARGEN = 16
ICONO_X_FALLBACK = 1720

ICONO_BT = '\U000f00af'
ICONO_SCAN = '\U000f0450'
ICONO_BATERIA = '\U000f0079'
ICONOS_TIPO = {
    'audio-headset': '\U000f02cb',
    'audio-headphones': '\U000f02cb',
    'input-keyboard': '\U000f030c',
    'input-mouse': '\U000f037d',
    'phone': '\U000f011c',
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
list, row { background: transparent; }
row {
    padding: 6px 8px;
    border-radius: 3px;
}
row:hover { background: #0b132b; }
.conectada { color: #00FF99; }
button {
    background: transparent;
    color: #E2E8F0;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 4px 10px;
    box-shadow: none;
}
button:hover { color: #00F0FF; border-bottom: 2px solid #00F0FF; }
button.olvidar { padding: 0 6px; color: rgba(226, 232, 240, 0.55); }
button.olvidar:hover { color: #ff4444; border-bottom: 2px solid #ff4444; }
switch { background: rgba(11, 19, 43, 0.9); border: 1px solid rgba(0, 240, 255, 0.35); }
switch:checked { background: rgba(0, 240, 255, 0.35); }
switch slider { background: #E2E8F0; }
scrollbar, scrollbar trough {
    background: transparent;
    border: none;
    box-shadow: none;
}
scrollbar slider {
    background: rgba(0, 240, 255, 0.25);
    border-radius: 2px;
    min-width: 4px;
    border: none;
    outline: none;
    box-shadow: none;
}
scrollbar slider:hover { background: rgba(0, 240, 255, 0.5); }
undershoot.top, undershoot.bottom, overshoot.top, overshoot.bottom { background: none; border: none; }
"""


def bt(*args, timeout=20):
    return subprocess.run(['bluetoothctl', *args], capture_output=True, text=True,
                          timeout=timeout).stdout


def notify(cuerpo, urgencia=None):
    cmd = ['notify-send', '--app-name=Bluetooth', '-t', '3500', 'Bluetooth', cuerpo]
    if urgencia:
        cmd += ['-u', urgencia]
    subprocess.Popen(cmd)


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'bluetooth-panel')
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
        self._armar_cabecera()

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_overlay_scrolling(False)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_min_content_height(200)
        self.scroll.set_max_content_height(430)
        self.lista = Gtk.ListBox()
        self.lista.set_selection_mode(Gtk.SelectionMode.NONE)
        self.lista.connect('row-activated', self._fila_activada)
        self.scroll.add(self.lista)
        self.caja.pack_start(self.scroll, True, True, 0)

        self.pie = Gtk.Label(label='', xalign=0)
        self.pie.get_style_context().add_class('sutil')
        self.caja.pack_start(self.pie, False, False, 0)

        self.dispositivos = []
        self._refrescar()

    def _margen_izq(self):
        try:
            out = subprocess.run(['hyprctl', 'cursorpos'], capture_output=True,
                                 text=True, timeout=2).stdout
            x = int(out.split(',')[0])
        except (ValueError, IndexError, subprocess.TimeoutExpired):
            x = ICONO_X_FALLBACK
        return max(MARGEN, min(x - ANCHO // 2, PANTALLA - ANCHO - MARGEN))

    def _armar_cabecera(self):
        fila = Gtk.Box(spacing=8)
        titulo = Gtk.Label(label=f'{ICONO_BT}  Bluetooth', xalign=0)
        titulo.get_style_context().add_class('titulo')
        fila.pack_start(titulo, True, True, 0)

        self.boton_scan = Gtk.Button(label=f'{ICONO_SCAN}  Buscar')
        self.boton_scan.set_tooltip_text('Buscar dispositivos nuevos (8s)')
        self.boton_scan.connect('clicked', self._escanear)
        fila.pack_start(self.boton_scan, False, False, 0)

        self.interruptor = Gtk.Switch()
        self.interruptor.set_valign(Gtk.Align.CENTER)
        self.id_radio = self.interruptor.connect('state-set', self._radio)
        fila.pack_start(self.interruptor, False, False, 0)
        self.caja.pack_start(fila, False, False, 0)

        self.estado = Gtk.Label(label='', xalign=0)
        self.estado.set_ellipsize(Pango.EllipsizeMode.END)
        self.estado.get_style_context().add_class('sutil')
        self.caja.pack_start(self.estado, False, False, 0)

    # ── datos ────────────────────────────────────────────────────────────────

    def _refrescar(self):
        threading.Thread(target=self._cargar, daemon=True).start()

    def _cargar(self):
        encendido = 'Powered: yes' in bt('show')
        dispositivos = []
        if encendido:
            emparejados = {}
            for l in bt('devices', 'Paired').splitlines():
                partes = l.split(' ', 2)
                if len(partes) == 3 and partes[0] == 'Device':
                    emparejados[partes[1]] = partes[2]

            for mac, nombre in emparejados.items():
                info = bt('info', mac)
                bateria = re.search(r'Battery Percentage:.*\((\d+)\)', info)
                tipo = re.search(r'Icon:\s*(\S+)', info)
                dispositivos.append({
                    'mac': mac, 'nombre': nombre,
                    'conectado': 'Connected: yes' in info,
                    'emparejado': True,
                    'bateria': int(bateria.group(1)) if bateria else None,
                    'icono': ICONOS_TIPO.get(tipo.group(1) if tipo else '', ICONO_BT),
                })

            for l in bt('devices').splitlines():
                partes = l.split(' ', 2)
                if len(partes) != 3 or partes[0] != 'Device':
                    continue
                mac, nombre = partes[1], partes[2]
                # sin nombre real = solo anuncia su MAC: ruido de escaneo
                if mac in emparejados or nombre == mac.replace(':', '-'):
                    continue
                dispositivos.append({'mac': mac, 'nombre': nombre, 'conectado': False,
                                     'emparejado': False, 'bateria': None,
                                     'icono': ICONO_BT})

            dispositivos.sort(key=lambda d: (-d['conectado'], -d['emparejado'],
                                             d['nombre'].lower()))
        GLib.idle_add(self._pintar, encendido, dispositivos)

    def _pintar(self, encendido, dispositivos):
        self.dispositivos = dispositivos
        self.interruptor.handler_block(self.id_radio)
        self.interruptor.set_state(encendido)
        self.interruptor.handler_unblock(self.id_radio)

        conectados = [d for d in dispositivos if d['conectado']]
        if not encendido:
            self.estado.set_text('Bluetooth apagado')
        elif conectados:
            d = conectados[0]
            bat = f"  ·  {ICONO_BATERIA} {d['bateria']}%" if d['bateria'] is not None else ''
            self.estado.set_text(f"Conectado a {d['nombre']}{bat}")
        else:
            self.estado.set_text('Sin dispositivos conectados')
        self.boton_scan.set_label(f'{ICONO_SCAN}  Buscar')

        for hijo in self.lista.get_children():
            self.lista.remove(hijo)
        for d in dispositivos:
            fila = Gtk.ListBoxRow()
            caja = Gtk.Box(spacing=10)
            marca = '✓' if d['conectado'] else ' '
            nombre = Gtk.Label(label=f"{marca}  {d['icono']}  {d['nombre']}", xalign=0)
            nombre.set_ellipsize(Pango.EllipsizeMode.END)
            if d['conectado']:
                nombre.get_style_context().add_class('conectada')
            caja.pack_start(nombre, True, True, 0)

            if d['conectado'] and d['bateria'] is not None:
                bateria = Gtk.Label(label=f"{ICONO_BATERIA} {d['bateria']}%")
                bateria.get_style_context().add_class('sutil')
                caja.pack_start(bateria, False, False, 0)
            if not d['emparejado']:
                tag = Gtk.Label(label='disponible')
                tag.get_style_context().add_class('sutil')
                caja.pack_start(tag, False, False, 0)
            else:
                olvidar = Gtk.Button(label='✕')
                olvidar.get_style_context().add_class('olvidar')
                olvidar.set_tooltip_text(f"Olvidar {d['nombre']}")
                olvidar.connect('clicked', self._olvidar, d)
                caja.pack_start(olvidar, False, False, 0)

            fila.add(caja)
            self.lista.add(fila)
        self.pie.set_text('clic conecta o desconecta  ·  ✕ olvida'
                          if dispositivos else '')
        self.lista.show_all()
        return False

    # ── acciones ─────────────────────────────────────────────────────────────

    def _radio(self, _sw, activar):
        threading.Thread(target=lambda: (
            bt('power', 'on' if activar else 'off'), self._cargar()
        ), daemon=True).start()

    def _escanear(self, _b):
        self.boton_scan.set_label('… buscando')

        def tarea():
            try:
                bt('--timeout', '8', 'scan', 'on', timeout=15)
            except subprocess.TimeoutExpired:
                pass
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _fila_activada(self, _lista, fila):
        d = self.dispositivos[fila.get_index()]
        if d['conectado']:
            threading.Thread(target=lambda: (
                bt('disconnect', d['mac']),
                notify(f"Desconectado de {d['nombre']}"),
                self._cargar()
            ), daemon=True).start()
        elif d['emparejado']:
            self._conectar(d)
        else:
            self._emparejar(d)

    def _conectar(self, d):
        notify(f"Conectando a {d['nombre']}...")

        def tarea():
            out = bt('connect', d['mac'])
            if re.search('successful', out, re.I):
                notify(f"Conectado a {d['nombre']} ✓")
                GLib.idle_add(Gtk.main_quit)
            else:
                notify(f"No se pudo conectar a {d['nombre']}", 'critical')
                self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _emparejar(self, d):
        notify(f"Emparejando con {d['nombre']}...")

        def tarea():
            try:
                out = bt('--timeout', '25', 'pair', d['mac'], timeout=30)
            except subprocess.TimeoutExpired:
                out = ''
            if re.search('successful', out, re.I):
                bt('trust', d['mac'])
                out = bt('connect', d['mac'])
                if re.search('successful', out, re.I):
                    notify(f"Conectado a {d['nombre']} ✓")
                    GLib.idle_add(Gtk.main_quit)
                    return
                notify(f"Emparejado, pero no se pudo conectar a {d['nombre']}", 'critical')
            else:
                notify(f"No se pudo emparejar con {d['nombre']}", 'critical')
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _olvidar(self, _b, d):
        threading.Thread(target=lambda: (
            bt('disconnect', d['mac']) if d['conectado'] else None,
            bt('remove', d['mac']),
            notify(f"{d['nombre']} eliminado"),
            self._cargar()
        ), daemon=True).start()

    def _clic_fuera(self, _w, evento):
        # Los clics sobre widgets hijos llegan con coordenadas relativas AL HIJO
        # y aqui parecerian "fuera": solo se evalua el cierre cuando el clic
        # cayo en la superficie de la ventana misma.
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
