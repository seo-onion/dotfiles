#!/usr/bin/env python3
# Panel de pantalla estilo swaync, sexto gemelo. Modo nocturno con slider de
# temperatura (comparte ~/.config/hypr/.nighttemp con F11), selector de fondo
# de pantalla por miniaturas (administra el symlink ~/.config/hypr/wallpaper),
# lista de monitores y acciones para pantalla externa (via hyprctl eval, la
# config es Lua y 'keyword' no funciona). Sin brillo a proposito: ya vive en
# el panel de bateria y en el scroll del icono backlight.
# Glifos como escapes \U000f... a proposito (ver ESCRITORIO.md).

import glob
import json
import os
import signal
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib, Gdk, GdkPixbuf

HOME = os.path.expanduser('~')
PIDFILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'display-panel.pid')
FONDOS = os.path.join(HOME, 'Imágenes/Fondos')
SYMLINK = os.path.join(HOME, '.config/hypr/wallpaper')
NIGHTTEMP = os.path.join(HOME, '.config/hypr/.nighttemp')
ANCHO = 460
PANTALLA = 1920
MARGEN = 16
ICONO_X_FALLBACK = 1860
INTERNA = 'eDP-1'

I_MONITOR = '\U000f0379'
I_NOCHE = '\U000f0594'
I_LAPTOP = '\U000f0322'
I_EXTENDER = '\U000f037a'
I_PROYECTOR = '\U000f0433'
I_KANSHI = '\U000f0450'

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
button.accion { font-size: 17px; padding: 4px 8px; }
button.fondo {
    padding: 2px;
    border: 2px solid transparent;
    border-radius: 4px;
}
button.fondo:hover { border: 2px solid rgba(0, 240, 255, 0.5); border-bottom: 2px solid rgba(0, 240, 255, 0.5); }
button.fondo.activo { border: 2px solid #00F0FF; }
switch { background: rgba(11, 19, 43, 0.9); border: 1px solid rgba(0, 240, 255, 0.35); }
switch:checked { background: rgba(0, 240, 255, 0.35); }
switch slider { background: #E2E8F0; }
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


def notify(cuerpo, urgencia=None):
    cmd = ['notify-send', '--app-name=Pantalla', '-t', '3000', 'Pantalla', cuerpo]
    if urgencia:
        cmd += ['-u', urgencia]
    subprocess.Popen(cmd)


def temp_guardada():
    try:
        with open(NIGHTTEMP) as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 3500


def noche_activa():
    return subprocess.run(['pgrep', '-x', 'wlsunset'],
                          capture_output=True).returncode == 0


def encender_noche(temp):
    subprocess.run(['pkill', '-x', 'wlsunset'], capture_output=True)
    # -S 23:59 -s 00:01: wlsunset cree que siempre es de noche y aplica -t fijo
    subprocess.Popen(['wlsunset', '-t', str(temp), '-T', '6500',
                      '-S', '23:59', '-s', '00:01'], start_new_session=True)


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'display-panel')
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
        self.connect('map', lambda *_: GLib.idle_add(self._reclamp))

        titulo = Gtk.Label(label=f'{I_MONITOR}   Pantalla', xalign=0)
        titulo.get_style_context().add_class('titulo')
        self.caja.pack_start(titulo, False, False, 0)

        self._armar_noche()
        self._armar_fondos()
        self._armar_monitores()

        self._timers, self._pend = {}, {}
        self._actualizando = False
        self._refrescar()

    def _margen_izq(self):
        try:
            out = subprocess.run(['hyprctl', 'cursorpos'], capture_output=True,
                                 text=True, timeout=2).stdout
            x = int(out.split(',')[0])
        except (ValueError, IndexError, subprocess.TimeoutExpired):
            x = ICONO_X_FALLBACK
        return max(MARGEN, min(x - ANCHO // 2, PANTALLA - ANCHO - MARGEN))

    def _reclamp(self):
        ancho_real = self.caja.get_allocation().width
        tope = PANTALLA - ancho_real - MARGEN
        if self.caja.get_margin_start() > tope:
            self.caja.set_margin_start(max(MARGEN, tope))
        return False

    def _seccion(self, texto):
        lbl = Gtk.Label(label=texto, xalign=0)
        lbl.get_style_context().add_class('seccion')
        self.caja.pack_start(lbl, False, False, 2)

    # ── construccion ─────────────────────────────────────────────────────────

    def _armar_noche(self):
        self._seccion('Modo nocturno')
        fila = Gtk.Box(spacing=12)
        icono = Gtk.Label(label=I_NOCHE)
        self.interruptor = Gtk.Switch()
        self.interruptor.set_valign(Gtk.Align.CENTER)
        self.id_noche = self.interruptor.connect('state-set', self._toggle_noche)
        self.escala_temp = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 2500, 6500, 100)
        self.escala_temp.set_draw_value(False)
        self.escala_temp.set_hexpand(True)
        self.escala_temp.connect('value-changed',
                                 lambda e: self._debounce('temp', e.get_value()))
        self.lbl_temp = Gtk.Label(label='')
        self.lbl_temp.get_style_context().add_class('sutil')
        self.lbl_temp.set_width_chars(7)
        fila.pack_start(icono, False, False, 0)
        fila.pack_start(self.interruptor, False, False, 0)
        fila.pack_start(self.escala_temp, True, True, 0)
        fila.pack_start(self.lbl_temp, False, False, 0)
        self.caja.pack_start(fila, False, False, 0)

    def _armar_fondos(self):
        self._seccion('Fondo de pantalla')
        self.flow = Gtk.FlowBox()
        self.flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flow.set_max_children_per_line(3)
        self.flow.set_min_children_per_line(3)
        self.flow.set_column_spacing(6)
        self.flow.set_row_spacing(6)
        self.caja.pack_start(self.flow, False, False, 0)

    def _armar_monitores(self):
        self._seccion('Pantallas')
        self.caja_mon = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.caja.pack_start(self.caja_mon, False, False, 0)

        # solo visible con pantalla externa conectada (lo decide _pintar)
        self.fila_acciones = Gtk.Box(spacing=4)
        self.fila_acciones.set_no_show_all(True)
        for icono, tip, accion in (
                (I_LAPTOP, 'Solo pantalla interna', 'solo_int'),
                (I_EXTENDER, 'Extender', 'extender'),
                (I_PROYECTOR, 'Duplicar', 'duplicar'),
                (I_MONITOR, 'Solo pantalla externa', 'solo_ext'),
                (I_KANSHI, 'Recargar perfiles de kanshi', 'kanshi')):
            b = Gtk.Button(label=icono)
            b.get_style_context().add_class('accion')
            b.set_tooltip_text(tip)
            b.connect('clicked', self._accion_monitor, accion)
            self.fila_acciones.pack_start(b, True, True, 0)
        self.caja.pack_start(self.fila_acciones, False, False, 0)

    # ── datos ────────────────────────────────────────────────────────────────

    def _refrescar(self):
        threading.Thread(target=self._cargar, daemon=True).start()

    def _cargar(self):
        activa = noche_activa()
        temp = temp_guardada()
        try:
            monitores = json.loads(sh('hyprctl', '-j', 'monitors', 'all'))
        except json.JSONDecodeError:
            monitores = []
        fondos = sorted(
            f for ext in ('jpg', 'jpeg', 'png', 'webp')
            for f in glob.glob(os.path.join(FONDOS, f'*.{ext}')))
        actual = os.path.realpath(SYMLINK) if os.path.exists(SYMLINK) else ''
        GLib.idle_add(self._pintar, activa, temp, monitores, fondos, actual)

    def _pintar(self, activa, temp, monitores, fondos, actual):
        self._actualizando = True
        self.interruptor.handler_block(self.id_noche)
        self.interruptor.set_state(activa)
        self.interruptor.handler_unblock(self.id_noche)
        self.escala_temp.set_value(temp)
        self.lbl_temp.set_text(f'{temp} K')

        for hijo in self.flow.get_children():
            self.flow.remove(hijo)
        for ruta in fondos:
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(ruta, 126, 72, True)
            except GLib.Error:
                continue
            b = Gtk.Button()
            b.set_image(Gtk.Image.new_from_pixbuf(pix))
            b.get_style_context().add_class('fondo')
            if os.path.realpath(ruta) == actual:
                b.get_style_context().add_class('activo')
            b.set_tooltip_text(os.path.basename(ruta))
            b.connect('clicked', self._poner_fondo, ruta)
            self.flow.add(b)
        self.flow.show_all()

        for hijo in self.caja_mon.get_children():
            self.caja_mon.remove(hijo)
        for m in monitores:
            marca = '▶' if m.get('focused') else (' ' if not m.get('disabled') else '·')
            texto = (f"{marca}   {m['name']}   ·   {m['width']}×{m['height']} "
                     f"{m.get('refreshRate', 0):.0f}Hz   ×{m.get('scale', 1):.3g}")
            if m.get('disabled'):
                texto += '  (apagada)'
            lbl = Gtk.Label(label=texto, xalign=0)
            lbl.get_style_context().add_class(
                'verde' if m.get('focused') else 'sutil')
            self.caja_mon.pack_start(lbl, False, False, 0)
        self.caja_mon.show_all()
        if any(m['name'] != INTERNA for m in monitores):
            self.fila_acciones.show()
            for b in self.fila_acciones.get_children():
                b.show()
        else:
            self.fila_acciones.hide()
        self._actualizando = False
        return False

    # ── acciones ─────────────────────────────────────────────────────────────

    def _toggle_noche(self, _sw, activar):
        def tarea():
            if activar:
                encender_noche(temp_guardada())
            else:
                subprocess.run(['pkill', '-x', 'wlsunset'], capture_output=True)
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _debounce(self, clave, valor):
        if self._actualizando:
            return
        self._pend[clave] = valor
        if clave not in self._timers:
            self._timers[clave] = GLib.timeout_add(150, self._aplicar_temp, clave)

    def _aplicar_temp(self, clave):
        temp = int(self._pend.pop(clave))
        del self._timers[clave]
        self.lbl_temp.set_text(f'{temp} K')
        with open(NIGHTTEMP, 'w') as f:
            f.write(str(temp))

        def tarea():
            if noche_activa():
                encender_noche(temp)
        threading.Thread(target=tarea, daemon=True).start()
        return False

    def _poner_fondo(self, _b, ruta):
        def tarea():
            tmp = SYMLINK + '.nuevo'
            os.symlink(ruta, tmp)
            os.replace(tmp, SYMLINK)
            subprocess.run(['pkill', '-x', 'swaybg'], capture_output=True)
            subprocess.Popen(['swaybg', '-i', SYMLINK, '-m', 'fill'],
                             start_new_session=True)
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    def _externa(self):
        try:
            monitores = json.loads(sh('hyprctl', '-j', 'monitors', 'all'))
        except json.JSONDecodeError:
            return None
        return next((m['name'] for m in monitores if m['name'] != INTERNA), None)

    def _accion_monitor(self, _b, accion):
        if accion == 'kanshi':
            out = sh('kanshictl', 'reload')
            notify('Perfiles de kanshi recargados')
            self._refrescar()
            return

        ext = self._externa()
        if not ext:
            notify('No hay pantalla externa conectada', 'critical')
            return

        # la config es Lua: 'hyprctl keyword' no funciona, se usa eval
        if accion == 'extender':
            lua = (f'hl.monitor({{ output = "{INTERNA}", mode = "preferred", position = "auto", scale = 1 }}) '
                   f'hl.monitor({{ output = "{ext}", mode = "preferred", position = "auto" }})')
        elif accion == 'duplicar':
            lua = f'hl.monitor({{ output = "{ext}", mode = "preferred", position = "auto", mirror = "{INTERNA}" }})'
        elif accion == 'solo_ext':
            lua = (f'hl.monitor({{ output = "{ext}", mode = "preferred", position = "auto" }}) '
                   f'hl.monitor({{ output = "{INTERNA}", disabled = true }})')
        else:
            lua = (f'hl.monitor({{ output = "{INTERNA}", mode = "preferred", position = "auto", scale = 1 }}) '
                   f'hl.monitor({{ output = "{ext}", disabled = true }})')

        def tarea():
            sh('hyprctl', 'eval', lua)
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

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
