#!/usr/bin/env python3
# Panel de energia estilo swaync, quinto gemelo. Acciones destructivas con
# confirmacion de segundo clic; apagado programado con temporizador desacoplado
# que sobrevive al cierre del panel; reinicio a BIOS (UEFI).
# Se abre desde custom/power de la waybar y con la tecla XF86PowerOff.
# Glifos como escapes \U000f... a proposito (ver ESCRITORIO.md).

import os
import shutil
import signal
import subprocess
import threading
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib, Gdk, Pango

RUNTIME = os.environ.get('XDG_RUNTIME_DIR', '/tmp')
PIDFILE = os.path.join(RUNTIME, 'power-panel.pid')
TIMERFILE = os.path.join(RUNTIME, 'apagado-programado')
ANCHO = 360
PANTALLA = 1920
MARGEN = 16
ICONO_X_FALLBACK = 1890

I_LOCK = '\U000f033e'
I_SLEEP = '\U000f04b2'
I_LOGOUT = '\U000f05fc'
I_REBOOT = '\U000f0709'
I_BIOS = '\U000f061a'
I_POWER = '\U000f0425'

ACCIONES = [
    (I_LOCK, 'Bloquear', 'lock', False),
    (I_SLEEP, 'Suspender', 'suspend', False),
    (I_LOGOUT, 'Cerrar sesión', 'logout', True),
    (I_REBOOT, 'Reiniciar', 'reboot', True),
    (I_BIOS, 'Reiniciar a la BIOS', 'bios', True),
    (I_POWER, 'Apagar', 'poweroff', True),
]

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
.peligro { color: #ff4444; }
list, row { background: transparent; }
row { padding: 6px 8px; border-radius: 3px; }
row:hover { background: #0b132b; }
button {
    background: transparent;
    color: #E2E8F0;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 2px 8px;
    box-shadow: none;
}
button:hover { color: #00F0FF; border-bottom: 2px solid #00F0FF; }
button.rojo:hover { color: #ff4444; border-bottom: 2px solid #ff4444; }
entry {
    background: rgba(11, 19, 43, 0.9);
    color: #FFFFFF;
    border: none;
    border-radius: 3px;
    padding: 2px 6px;
    caret-color: #00F0FF;
    box-shadow: none;
}
"""


def notify(cuerpo, urgencia=None):
    cmd = ['notify-send', '--app-name=Sistema', '-t', '3500', 'Sistema', cuerpo]
    if urgencia:
        cmd += ['-u', urgencia]
    subprocess.Popen(cmd)


def timer_activo():
    # devuelve (pid, epoch_objetivo) si hay un apagado programado vivo
    try:
        with open(TIMERFILE) as f:
            pid, objetivo = int(f.readline()), float(f.readline())
        os.kill(pid, 0)
        return pid, objetivo
    except (OSError, ValueError):
        return None


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'power-panel')
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

        titulo = Gtk.Label(label=f'{I_POWER}  Sistema', xalign=0)
        titulo.get_style_context().add_class('titulo')
        self.caja.pack_start(titulo, False, False, 0)

        self.lbl_info = Gtk.Label(label='', xalign=0)
        # sin elipsis esta linea estira la caja mas alla de ANCHO y rompe el
        # clamp del margen: el panel se sale por la derecha
        self.lbl_info.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_info.get_style_context().add_class('sutil')
        self.caja.pack_start(self.lbl_info, False, False, 0)

        self.lista = Gtk.ListBox()
        self.lista.set_selection_mode(Gtk.SelectionMode.NONE)
        self.lista.connect('row-activated', self._fila_activada)
        self.filas = []
        for icono, nombre, accion, confirmar in ACCIONES:
            fila = Gtk.ListBoxRow()
            lbl = Gtk.Label(label=f'{icono}   {nombre}', xalign=0)
            fila.add(lbl)
            self.lista.add(fila)
            self.filas.append({'lbl': lbl, 'texto': f'{icono}   {nombre}',
                               'accion': accion, 'confirmar': confirmar})
        self.caja.pack_start(self.lista, False, False, 0)

        self.fila_prog = Gtk.Box(spacing=6)
        lbl_prog_a = Gtk.Label(label='Apagar en')
        lbl_prog_a.get_style_context().add_class('sutil')
        self.entrada_min = Gtk.Entry()
        self.entrada_min.set_width_chars(4)
        self.entrada_min.set_max_length(3)
        self.entrada_min.set_alignment(0.5)
        self.entrada_min.connect('activate', self._programar_entrada)
        lbl_prog_b = Gtk.Label(label='min')
        lbl_prog_b.get_style_context().add_class('sutil')
        btn_prog = Gtk.Button(label='Programar')
        btn_prog.connect('clicked', self._programar_entrada)
        self.fila_prog.pack_start(lbl_prog_a, False, False, 0)
        self.fila_prog.pack_start(self.entrada_min, False, False, 0)
        self.fila_prog.pack_start(lbl_prog_b, False, False, 0)
        self.fila_prog.pack_end(btn_prog, False, False, 0)
        self.caja.pack_start(self.fila_prog, False, False, 0)

        self.fila_cancel = Gtk.Box(spacing=6)
        self.lbl_prog = Gtk.Label(label='', xalign=0)
        self.lbl_prog.get_style_context().add_class('peligro')
        self.fila_cancel.pack_start(self.lbl_prog, True, True, 0)
        btn_cancel = Gtk.Button(label='cancelar')
        btn_cancel.get_style_context().add_class('rojo')
        btn_cancel.connect('clicked', self._cancelar)
        self.fila_cancel.pack_start(btn_cancel, False, False, 0)
        self.caja.pack_start(self.fila_cancel, False, False, 0)

        self.armada = None
        self._timer_desarmar = None
        self._pintar_info()
        self.connect('map', lambda *_: (self._pintar_timer(),
                                        GLib.idle_add(self._reclamp)))
        GLib.timeout_add_seconds(10, lambda: (self._pintar_timer(), True)[1])

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

    def _pintar_info(self):
        arriba = subprocess.run(['uptime', '-p'], capture_output=True,
                                text=True).stdout.strip()
        arriba = (arriba.replace('up ', 'encendido hace ')
                        .replace(' hours', ' h').replace(' hour', ' h')
                        .replace(' minutes', ' min').replace(' minute', ' min'))
        try:
            import json
            ventanas = len(json.loads(subprocess.run(
                ['hyprctl', '-j', 'clients'], capture_output=True,
                text=True, timeout=3).stdout))
        except (ValueError, subprocess.TimeoutExpired):
            ventanas = None
        extra = f'  ·  {ventanas} ventanas abiertas' if ventanas else ''
        self.lbl_info.set_text(f'{arriba}{extra}')

    def _pintar_timer(self):
        activo = timer_activo()
        if activo:
            restante = max(0, int((activo[1] - time.time()) / 60))
            self.lbl_prog.set_text(f'Apagado en {restante} min')
        self.fila_prog.set_visible(not activo)
        self.fila_cancel.set_visible(bool(activo))
        return False

    # ── acciones ─────────────────────────────────────────────────────────────

    def _fila_activada(self, _lista, fila):
        i = fila.get_index()
        datos = self.filas[i]
        if datos['confirmar'] and self.armada != i:
            self._desarmar()
            self.armada = i
            datos['lbl'].set_text(f"{datos['texto']}   ·  clic otra vez")
            datos['lbl'].get_style_context().add_class('peligro')
            self._timer_desarmar = GLib.timeout_add_seconds(4, self._desarmar_timeout)
            return
        self._ejecutar(datos['accion'])

    def _desarmar(self):
        if self.armada is not None:
            d = self.filas[self.armada]
            d['lbl'].set_text(d['texto'])
            d['lbl'].get_style_context().remove_class('peligro')
            self.armada = None
        if self._timer_desarmar:
            GLib.source_remove(self._timer_desarmar)
            self._timer_desarmar = None

    def _desarmar_timeout(self):
        self._timer_desarmar = None
        self._desarmar()
        return False

    def _ejecutar(self, accion):
        if accion == 'lock':
            if not shutil.which('hyprlock'):
                notify('hyprlock no está instalado', 'critical')
                return
            subprocess.Popen(['hyprlock'], start_new_session=True)
        elif accion == 'suspend':
            subprocess.Popen(['systemctl', 'suspend'])
        elif accion == 'logout':
            subprocess.Popen(['hyprctl', 'dispatch', 'exit'])
        elif accion == 'reboot':
            subprocess.Popen(['systemctl', 'reboot'])
        elif accion == 'bios':
            subprocess.Popen(['systemctl', 'reboot', '--firmware-setup'])
        elif accion == 'poweroff':
            subprocess.Popen(['systemctl', 'poweroff'])
        Gtk.main_quit()

    def _programar_entrada(self, _w):
        texto = self.entrada_min.get_text().strip()
        if not texto.isdigit() or int(texto) == 0:
            self.entrada_min.set_text('')
            return
        self.entrada_min.set_text('')
        self._programar(int(texto))

    def _programar(self, minutos):
        # proceso suelto (setsid): el apagado sigue en pie aunque el panel muera
        proc = subprocess.Popen(
            ['sh', '-c', f'sleep {minutos * 60} && systemctl poweroff'],
            start_new_session=True)
        with open(TIMERFILE, 'w') as f:
            f.write(f'{proc.pid}\n{time.time() + minutos * 60}\n')
        notify(f'Apagado programado en {minutos} min')
        self._pintar_timer()

    def _cancelar(self, _b):
        activo = timer_activo()
        if activo:
            try:
                os.killpg(activo[0], signal.SIGTERM)
            except OSError:
                try:
                    os.kill(activo[0], signal.SIGTERM)
                except OSError:
                    pass
        if os.path.exists(TIMERFILE):
            os.unlink(TIMERFILE)
        notify('Apagado programado cancelado')
        self._pintar_timer()

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
            if self.armada is not None:
                self._desarmar()
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
