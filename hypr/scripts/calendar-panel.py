#!/usr/bin/env python3
# Panel de calendario estilo swaync, septimo gemelo (clic en el reloj).
# Cuadricula del mes navegable + eventos de khal (calendario local 'personal'
# + los de Google cuando vdirsyncer tenga credenciales). Crear evento rapido
# con sintaxis khal y boton de sincronizacion.
# Glifos como escapes \U000f... a proposito (ver ESCRITORIO.md).

import calendar
import datetime
import os
import signal
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib, Gdk, Pango

HOME = os.path.expanduser('~')
PIDFILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'calendar-panel.pid')
VDIRSYNCER_CONF = os.path.join(HOME, '.config/vdirsyncer/config')
ANCHO = 460
PANTALLA = 1920
MARGEN = 16
ICONO_X_FALLBACK = 830

I_CAL = '\U000f00ed'
I_SYNC = '\U000f0450'
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio',
         'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
DIAS = ['lu', 'ma', 'mi', 'ju', 'vi', 'sá', 'do']
DIAS_LARGO = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']

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
button.dia {
    padding: 3px 0;
    font-size: 13px;
    border-radius: 3px;
    border-bottom: 2px solid transparent;
}
button.dia:hover { background: #0b132b; border-bottom: 2px solid transparent; color: #E2E8F0; }
button.otro-mes { color: rgba(226, 232, 240, 0.25); }
button.hoy { color: #05050A; background: #00F0FF; }
button.hoy:hover { background: #00F0FF; color: #05050A; }
button.con-evento { border-bottom: 2px solid #00FF99; }
button.seleccionado { background: #0b132b; }
.cab-dia { color: #33CCFF; font-size: 12px; }
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


def sh(*args, timeout=15):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return '', 'timeout', 1


def notify(cuerpo, urgencia=None):
    cmd = ['notify-send', '--app-name=Calendario', '-t', '3500', 'Calendario', cuerpo]
    if urgencia:
        cmd += ['-u', urgencia]
    subprocess.Popen(cmd)


def eventos_rango(inicio, fin):
    # devuelve {date: [(hora, titulo, calendario)]}. El day-format solo trae
    # dd/mm: el anio se deduce del rango, sumando uno si el mes retrocede.
    out, _, _ = sh('khal', 'list', '--day-format', 'DIA {date}',
                   '--format', '{start-time}|{title}|{calendar}',
                   inicio.strftime('%d/%m/%Y'), fin.strftime('%d/%m/%Y'))
    eventos = {}
    fecha = None
    anio, mes_prev = inicio.year, None
    for linea in out.splitlines():
        if linea.startswith('DIA '):
            d, m = map(int, linea[4:].split('/'))
            if mes_prev is not None and m < mes_prev:
                anio += 1
            mes_prev = m
            fecha = datetime.date(anio, m, d)
            eventos.setdefault(fecha, [])
        elif fecha is not None and linea.strip():
            partes = (linea + '||').split('|')
            eventos[fecha].append((partes[0], partes[1], partes[2]))
    return eventos


def google_configurado():
    try:
        with open(VDIRSYNCER_CONF) as f:
            return 'PEGAR_CLIENT_ID_AQUI' not in f.read()
    except OSError:
        return False


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'calendar-panel')
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

        hoy = datetime.date.today()
        self.anio, self.mes = hoy.year, hoy.month
        self.sel = None
        self.eventos = {}

        self._armar_cabecera()
        self._armar_cuadricula()
        self._armar_eventos()
        self._armar_pie()
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

    # ── construccion ─────────────────────────────────────────────────────────

    def _armar_cabecera(self):
        fila = Gtk.Box(spacing=6)
        self.lbl_mes = Gtk.Label(label='', xalign=0)
        self.lbl_mes.get_style_context().add_class('titulo')
        fila.pack_start(self.lbl_mes, True, True, 0)
        for texto, paso in (('‹', -1), ('hoy', 0), ('›', 1)):
            b = Gtk.Button(label=texto)
            b.connect('clicked', self._navegar, paso)
            fila.pack_start(b, False, False, 0)
        self.caja.pack_start(fila, False, False, 0)

    def _armar_cuadricula(self):
        self.grid = Gtk.Grid()
        self.grid.set_column_homogeneous(True)
        self.grid.set_row_spacing(2)
        self.grid.set_column_spacing(2)
        caja_scroll = Gtk.EventBox()
        caja_scroll.add_events(Gdk.EventMask.SCROLL_MASK)
        caja_scroll.connect('scroll-event', self._scroll_mes)
        caja_scroll.add(self.grid)
        self.caja.pack_start(caja_scroll, False, False, 0)

    def _armar_eventos(self):
        self.sec_ev = Gtk.Label(label='Próximos', xalign=0)
        self.sec_ev.get_style_context().add_class('seccion')
        self.caja.pack_start(self.sec_ev, False, False, 2)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False)
        scroll.set_propagate_natural_height(True)
        scroll.set_min_content_height(90)
        scroll.set_max_content_height(210)
        self.caja_ev = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll.add(self.caja_ev)
        self.caja.pack_start(scroll, False, False, 0)

    def _armar_pie(self):
        fila = Gtk.Box(spacing=6)
        self.entrada = Gtk.Entry()
        self.entrada.set_placeholder_text('20/08 15:00 Título del evento')
        self.entrada.connect('activate', self._nuevo_evento)
        fila.pack_start(self.entrada, True, True, 0)
        b_add = Gtk.Button(label='Crear')
        b_add.connect('clicked', self._nuevo_evento)
        fila.pack_start(b_add, False, False, 0)
        self.b_sync = Gtk.Button(label=I_SYNC)
        self.b_sync.set_tooltip_text('Sincronizar con Google (vdirsyncer)')
        self.b_sync.connect('clicked', self._sync)
        fila.pack_start(self.b_sync, False, False, 0)
        self.caja.pack_start(fila, False, False, 0)

    # ── datos ────────────────────────────────────────────────────────────────

    def _rango_visible(self):
        primero = datetime.date(self.anio, self.mes, 1)
        inicio = primero - datetime.timedelta(days=primero.weekday())
        fin = inicio + datetime.timedelta(days=42)
        return inicio, fin

    def _refrescar(self):
        def tarea():
            inicio, fin = self._rango_visible()
            hoy = datetime.date.today()
            ev_mes = eventos_rango(inicio, fin)
            ev_prox = eventos_rango(hoy, hoy + datetime.timedelta(days=14))
            GLib.idle_add(self._pintar, ev_mes, ev_prox)
        threading.Thread(target=tarea, daemon=True).start()

    def _pintar(self, ev_mes, ev_prox):
        self.eventos = ev_mes
        self.ev_prox = ev_prox
        self.lbl_mes.set_text(f'{I_CAL}   {MESES[self.mes - 1].capitalize()} {self.anio}')

        for hijo in self.grid.get_children():
            self.grid.remove(hijo)
        for col, dia in enumerate(DIAS):
            lbl = Gtk.Label(label=dia)
            lbl.get_style_context().add_class('cab-dia')
            self.grid.attach(lbl, col, 0, 1, 1)

        hoy = datetime.date.today()
        cal = calendar.Calendar(firstweekday=0)
        for f_idx, semana in enumerate(cal.monthdatescalendar(self.anio, self.mes)):
            for c_idx, fecha in enumerate(semana):
                b = Gtk.Button(label=str(fecha.day))
                ctx = b.get_style_context()
                ctx.add_class('dia')
                if fecha.month != self.mes:
                    ctx.add_class('otro-mes')
                if fecha == hoy:
                    ctx.add_class('hoy')
                if fecha in ev_mes and ev_mes[fecha]:
                    ctx.add_class('con-evento')
                if fecha == self.sel:
                    ctx.add_class('seleccionado')
                b.connect('clicked', self._sel_dia, fecha)
                self.grid.attach(b, c_idx, f_idx + 1, 1, 1)
        self.grid.show_all()

        self._pintar_eventos()
        return False

    def _pintar_eventos(self):
        for hijo in self.caja_ev.get_children():
            self.caja_ev.remove(hijo)

        if self.sel:
            self.sec_ev.set_text(
                f'{DIAS_LARGO[self.sel.weekday()]} {self.sel.day} de {MESES[self.sel.month - 1]}')
            dias = {self.sel: self.eventos.get(self.sel, [])}
        else:
            self.sec_ev.set_text('Próximos 14 días')
            dias = self.ev_prox

        vacio = True
        for fecha in sorted(dias):
            for hora, titulo, cal_nombre in dias[fecha]:
                vacio = False
                fila = Gtk.Box(spacing=8)
                cuando = f'{fecha.day:02d}/{fecha.month:02d}' if not self.sel else ''
                pref = Gtk.Label(label=f'{cuando} {hora or "todo el día"}'.strip())
                pref.get_style_context().add_class('verde')
                pref.set_width_chars(12)
                pref.set_xalign(0)
                lbl = Gtk.Label(label=titulo, xalign=0)
                lbl.set_ellipsize(Pango.EllipsizeMode.END)
                fila.pack_start(pref, False, False, 0)
                fila.pack_start(lbl, True, True, 0)
                if cal_nombre and cal_nombre != 'personal':
                    tag = Gtk.Label(label=cal_nombre)
                    tag.get_style_context().add_class('sutil')
                    fila.pack_start(tag, False, False, 0)
                self.caja_ev.pack_start(fila, False, False, 0)
        if vacio:
            lbl = Gtk.Label(label='sin eventos', xalign=0)
            lbl.get_style_context().add_class('sutil')
            self.caja_ev.pack_start(lbl, False, False, 0)
        self.caja_ev.show_all()

    # ── acciones ─────────────────────────────────────────────────────────────

    def _navegar(self, _b, paso):
        if paso == 0:
            hoy = datetime.date.today()
            self.anio, self.mes = hoy.year, hoy.month
            self.sel = None
        else:
            m = self.mes + paso
            self.anio += (m - 1) // 12
            self.mes = (m - 1) % 12 + 1
        self._refrescar()

    def _scroll_mes(self, _w, evento):
        if evento.direction == Gdk.ScrollDirection.UP:
            self._navegar(None, -1)
        elif evento.direction == Gdk.ScrollDirection.DOWN:
            self._navegar(None, 1)
        return True

    def _sel_dia(self, _b, fecha):
        self.sel = None if fecha == self.sel else fecha
        self._pintar(self.eventos, self.ev_prox)

    def _nuevo_evento(self, _w):
        texto = self.entrada.get_text().strip()
        if not texto:
            return
        self.entrada.set_text('')

        def tarea():
            _, err, rc = sh('khal', 'new', *texto.split())
            if rc == 0:
                notify('Evento creado ✓')
            else:
                notify(f'khal no entendió el evento:\n{err.strip()[:120]}', 'critical')
            GLib.idle_add(self._refrescar)
        threading.Thread(target=tarea, daemon=True).start()

    def _sync(self, _b):
        if not google_configurado():
            notify('Google sin configurar: faltan credenciales en '
                   '~/.config/vdirsyncer/config', 'critical')
            return
        self.b_sync.set_label('…')

        def tarea():
            _, err, rc = sh('vdirsyncer', 'sync', timeout=60)
            if rc == 0:
                notify('Calendarios sincronizados ✓')
            else:
                notify(f'vdirsyncer falló:\n{err.strip()[-120:]}', 'critical')
            GLib.idle_add(self.b_sync.set_label, I_SYNC)
            GLib.idle_add(self._refrescar)
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
