#!/usr/bin/env python3
# Panel Wi-Fi estilo swaync: superficie layer-shell que cae desde la waybar,
# centrada en el punto donde se hizo clic (el icono de red). La animacion
# slide-top la pone la layer rule 'wifi-panel' de hyprland.lua.
# Segunda invocacion = cerrar (mismo toggle que clipboard.sh con CopyQ).

import os
import re
import signal
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib, Gdk, Pango

PIDFILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'wifi-panel.pid')
ANCHO = 450
PANTALLA = 1920
MARGEN = 16
ICONO_X_FALLBACK = 1548

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
.error  { color: #ff4444; font-size: 12px; }
list, row { background: transparent; }
row {
    padding: 6px 8px;
    border-radius: 3px;
    border-bottom: 2px solid transparent;
}
row:hover { background: #0b132b; }
.conectada { color: #00FF99; }
entry {
    background: rgba(11, 19, 43, 0.9);
    color: #FFFFFF;
    border: none;
    border-bottom: 1px solid rgba(0, 240, 255, 0.35);
    border-radius: 2px;
    padding: 6px 10px;
    caret-color: #00F0FF;
}
button {
    background: transparent;
    color: #E2E8F0;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 4px 10px;
    box-shadow: none;
}
button:hover { color: #00F0FF; border-bottom: 2px solid #00F0FF; }
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


def nm(*args, timeout=20):
    return subprocess.run(['nmcli', *args], capture_output=True, text=True,
                          timeout=timeout).stdout


def nmsplit(line):
    return [p.replace('\\:', ':') for p in re.split(r'(?<!\\):', line)]


def icono_senal(senal):
    # mismos glifos y color que el modulo network de la waybar
    iconos = ['󰤯', '󰤟', '󰤢', '󰤥', '󰤨']
    return iconos[min(senal // 20, 4)]


def notify(cuerpo, urgencia=None):
    cmd = ['notify-send', '--app-name=Wi-Fi', '-t', '3500', 'Wi-Fi', cuerpo]
    if urgencia:
        cmd += ['-u', urgencia]
    subprocess.Popen(cmd)


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'wifi-panel')
        GtkLayerShell.set_layer(self, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.ON_DEMAND)
        # Mismo truco que swaync: la superficie cubre toda el area de trabajo
        # (transparente) y el panel es una caja dentro. Un clic fuera de la caja
        # cae en la superficie vacia y cierra. Por esto la layer rule NO debe
        # llevar blur, igual que la de swaync.
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

        self.revelador = Gtk.Revealer()
        self.caja.pack_start(self.revelador, False, False, 0)

        self.scroll = Gtk.ScrolledWindow()
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_overlay_scrolling(False)
        self.scroll.set_propagate_natural_height(True)
        self.scroll.set_min_content_height(300)
        self.scroll.set_max_content_height(430)
        self.lista = Gtk.ListBox()
        self.lista.set_selection_mode(Gtk.SelectionMode.NONE)
        self.lista.connect('row-activated', self._fila_activada)
        self.scroll.add(self.lista)
        self.caja.pack_start(self.scroll, True, True, 0)

        self.pie = Gtk.Label(label='', xalign=0)
        self.pie.get_style_context().add_class('sutil')
        self.caja.pack_start(self.pie, False, False, 0)

        self.redes = []
        self._refrescar()
        # la cache de nmcli suele traer solo la red conectada: primero se pinta
        # lo que haya (rapido) y en paralelo se escanea de verdad
        self._escanear(None)

    def _margen_izq(self):
        # Centrado en el cursor: el panel se abre con un clic en el icono de
        # red, asi que el cursor ES la posicion del icono aunque la waybar se
        # desplace cuando cambia el texto de velocidades.
        try:
            out = subprocess.run(['hyprctl', 'cursorpos'], capture_output=True,
                                 text=True, timeout=2).stdout
            x = int(out.split(',')[0])
        except (ValueError, IndexError, subprocess.TimeoutExpired):
            x = ICONO_X_FALLBACK
        return max(MARGEN, min(x - ANCHO // 2, PANTALLA - ANCHO - MARGEN))

    def _armar_cabecera(self):
        fila = Gtk.Box(spacing=8)
        titulo = Gtk.Label(label='󰤨  Wi-Fi', xalign=0)
        titulo.get_style_context().add_class('titulo')
        fila.pack_start(titulo, True, True, 0)

        self.boton_scan = Gtk.Button(label='󰑐  Actualizar')
        self.boton_scan.set_tooltip_text('Buscar redes')
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
        encendida = nm('radio', 'wifi').strip() == 'enabled'
        guardadas = {nmsplit(l)[0] for l in nm('-t', '-f', 'NAME',
                     'connection', 'show').splitlines() if l}
        redes, estado = [], ''
        if encendida:
            vistos = {}
            for l in nm('-t', '-f', 'IN-USE,SSID,SIGNAL,SECURITY',
                        'device', 'wifi', 'list', '--rescan', 'no').splitlines():
                campos = nmsplit(l)
                if len(campos) < 4 or not campos[1]:
                    continue
                en_uso, ssid, senal, seg = campos[0] == '*', campos[1], int(campos[2] or 0), campos[3]
                previo = vistos.get(ssid)
                if previo is None or senal > previo['senal'] or en_uso:
                    vistos[ssid] = {'ssid': ssid, 'senal': senal,
                                    'en_uso': en_uso or (previo['en_uso'] if previo else False),
                                    'abierta': seg in ('', '--'), 'guardada': ssid in guardadas}
            redes = sorted(vistos.values(), key=lambda r: (-r['en_uso'], -r['senal']))
            activa = next((r for r in redes if r['en_uso']), None)
            if activa:
                dev = next((nmsplit(l)[0] for l in nm('-t', '-f', 'DEVICE,TYPE',
                           'device', 'status').splitlines() if 'wifi' in l), '')
                ip = ''
                if dev:
                    ip = next((nmsplit(l)[1].split('/')[0] for l in
                              nm('-t', '-f', 'IP4.ADDRESS', 'device', 'show', dev).splitlines()
                              if ':' in l), '')
                estado = f"Conectado a {activa['ssid']}" + (f'  ·  {ip}' if ip else '')
        GLib.idle_add(self._pintar, encendida, redes, estado)

    def _pintar(self, encendida, redes, estado):
        self.redes = redes
        # bloquear el handler: set_state emite state-set y sin esto cada
        # refresco volveria a llamar a nmcli radio
        self.interruptor.handler_block(self.id_radio)
        self.interruptor.set_state(encendida)
        self.interruptor.handler_unblock(self.id_radio)
        self.estado.set_text(estado if encendida else 'Wi-Fi apagado')
        self.boton_scan.set_label('󰑐  Actualizar')

        for hijo in self.lista.get_children():
            self.lista.remove(hijo)
        for red in redes:
            fila = Gtk.ListBoxRow()
            caja = Gtk.Box(spacing=10)
            marca = '✓' if red['en_uso'] else ' '
            nombre = Gtk.Label(label=f"{marca}  {red['ssid']}", xalign=0)
            nombre.set_ellipsize(Pango.EllipsizeMode.END)
            if red['en_uso']:
                nombre.get_style_context().add_class('conectada')
            caja.pack_start(nombre, True, True, 0)
            candado = ' ' if red['abierta'] else '󰌾'
            detalle = Gtk.Label()
            detalle.set_markup(
                f"<span size='9800'>{candado}</span>  "
                f"<span foreground='#00F0FF'>{icono_senal(red['senal'])}</span>")
            detalle.get_style_context().add_class('sutil')
            caja.pack_start(detalle, False, False, 0)
            fila.add(caja)
            self.lista.add(fila)
        self.pie.set_text('clic → desconectar'
                          if any(r['en_uso'] for r in redes) else '')
        self.lista.show_all()
        self.revelador.set_reveal_child(False)
        return False

    # ── acciones ─────────────────────────────────────────────────────────────

    def _radio(self, _sw, activar):
        threading.Thread(target=lambda: (
            nm('radio', 'wifi', 'on' if activar else 'off'), self._cargar()
        ), daemon=True).start()

    def _escanear(self, _b):
        self.boton_scan.set_label('… buscando')
        threading.Thread(target=lambda: (
            nm('device', 'wifi', 'list', '--rescan', 'yes', timeout=15), self._cargar()
        ), daemon=True).start()

    def _fila_activada(self, _lista, fila):
        red = self.redes[fila.get_index()]
        if red['en_uso']:
            self._en_hilo(['connection', 'down', red['ssid']],
                          f"Desconectado de {red['ssid']}", cerrar=False)
        elif red['guardada']:
            self._en_hilo(['connection', 'up', red['ssid']],
                          f"Conectado a {red['ssid']} ✓")
        elif red['abierta']:
            self._en_hilo(['device', 'wifi', 'connect', red['ssid']],
                          f"Conectado a {red['ssid']} ✓")
        else:
            self._pedir_clave(red['ssid'])

    def _pedir_clave(self, ssid):
        caja = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        etiqueta = Gtk.Label(label=f'Contraseña · {ssid}', xalign=0)
        etiqueta.get_style_context().add_class('sutil')
        entrada = Gtk.Entry()
        entrada.set_visibility(False)
        entrada.set_placeholder_text('Enter para conectar · Esc para cancelar')
        entrada.connect('activate', lambda e: self._conectar_con_clave(ssid, e.get_text()))
        ojo = Gtk.ToggleButton(label='󰈈')
        ojo.set_tooltip_text('Mostrar contraseña')
        ojo.connect('toggled', lambda b: (
            entrada.set_visibility(b.get_active()),
            b.set_label('󰈉' if b.get_active() else '󰈈')))
        linea = Gtk.Box(spacing=6)
        linea.pack_start(entrada, True, True, 0)
        linea.pack_start(ojo, False, False, 0)
        caja.pack_start(etiqueta, False, False, 0)
        caja.pack_start(linea, False, False, 0)
        viejo = self.revelador.get_child()
        if viejo:
            self.revelador.remove(viejo)
        self.revelador.add(caja)
        self.revelador.show_all()
        self.revelador.set_reveal_child(True)
        entrada.grab_focus()

    def _conectar_con_clave(self, ssid, clave):
        if not clave:
            return
        self.revelador.set_reveal_child(False)

        def tarea():
            out = subprocess.run(['nmcli', 'device', 'wifi', 'connect', ssid,
                                  'password', clave], capture_output=True, text=True).stdout
            if re.search('successfully|activated', out, re.I):
                notify(f'Conectado a {ssid} ✓')
                GLib.idle_add(Gtk.main_quit)
            else:
                # perfil a medias tras clave mala: fuera, para poder reintentar
                nm('connection', 'delete', ssid)
                notify(f'Contraseña incorrecta para {ssid}', 'critical')
                self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _en_hilo(self, args, ok, cerrar=True):
        def tarea():
            out = nm(*args)
            if re.search('successfully|activated', out, re.I) or 'down' in args:
                notify(ok)
                if cerrar:
                    GLib.idle_add(Gtk.main_quit)
                else:
                    self._cargar()
            else:
                notify(f"No se pudo: {args[-1]}", 'critical')
                self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _clic_fuera(self, _w, evento):
        # Los clics sobre widgets hijos (filas, botones) llegan con coordenadas
        # relativas AL HIJO y aqui parecerian "fuera": solo se evalua el cierre
        # cuando el clic cayo en la superficie de la ventana misma.
        if Gtk.get_event_widget(evento) is not self:
            return False
        a = self.caja.get_allocation()
        if not (a.x <= evento.x <= a.x + a.width and a.y <= evento.y <= a.y + a.height):
            Gtk.main_quit()
            return True
        return False

    def _tecla(self, _w, evento):
        if evento.keyval == Gdk.KEY_Escape:
            if self.revelador.get_reveal_child():
                self.revelador.set_reveal_child(False)
            else:
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
