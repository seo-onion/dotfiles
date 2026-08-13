#!/usr/bin/env python3
# Panel de audio estilo swaync, gemelo de wifi-panel.py / bluetooth-panel.py.
# Reproductor MPRIS (playerctld decide el activo, pestanas si hay varios),
# volumen y seleccion de salida/entrada (wpctl/pactl), mezclador por app.
# Glifos como escapes \U000f... a proposito (ver ESCRITORIO.md).

import hashlib
import json
import os
import re
import signal
import subprocess
import threading
import urllib.request

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, GtkLayerShell, GLib, Gdk, Pango, GdkPixbuf

PIDFILE = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'audio-panel.pid')
CACHE_ART = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'audio-panel-art')
ANCHO = 460
PANTALLA = 1920
MARGEN = 16
ICONO_X_FALLBACK = 1150
SEP = '\x1e'

I_VOL = ['\U000f057f', '\U000f0580', '\U000f057e']
I_MUTE = '\U000f075f'
I_MIC = '\U000f036c'
I_MIC_MUTE = '\U000f036d'
I_PREV = '\U000f04ae'
I_NEXT = '\U000f04ad'
I_PLAY = '\U000f040a'
I_PAUSE = '\U000f03e4'
I_NOTA = '\U000f075a'

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
.cancion { color: #FFFFFF; }
list, row { background: transparent; }
row { padding: 4px 8px; border-radius: 3px; }
row:hover { background: #0b132b; }
.conectada { color: #00FF99; }
button {
    background: transparent;
    color: #E2E8F0;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 2px 8px;
    box-shadow: none;
}
button:hover { color: #00F0FF; border-bottom: 2px solid #00F0FF; }
button.control { font-size: 18px; }
button.tab { color: rgba(226, 232, 240, 0.55); font-size: 12px; }
button.tab:checked, button.tab:active {
    color: #00F0FF;
    border-bottom: 2px solid #00F0FF;
    background: transparent;
}
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
scrollbar, scrollbar trough { background: transparent; border: none; box-shadow: none; }
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


def sh(*args, timeout=10):
    try:
        return subprocess.run(args, capture_output=True, text=True,
                              timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ''


def pactl_json(clase):
    out = sh('pactl', '--format=json', 'list', clase)
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def pct_volumen(dispositivo):
    for canal in dispositivo.get('volume', {}).values():
        m = re.match(r'(\d+)%', canal.get('value_percent', ''))
        if m:
            return int(m.group(1))
    return 0


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__()
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self, 'audio-panel')
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

        titulo = Gtk.Label(label=f'{I_VOL[2]}  Audio', xalign=0)
        titulo.get_style_context().add_class('titulo')
        self.caja.pack_start(titulo, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False)
        scroll.set_propagate_natural_height(True)
        scroll.set_max_content_height(760)
        self.cont = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll.add(self.cont)
        self.caja.pack_start(scroll, True, True, 0)

        self._armar_reproductor()
        self.fila_salida, self.escala_salida, self.lbl_salida, self.btn_mute_out, \
            self.lista_sinks = self._armar_dispositivos('Salida')
        self.fila_entrada, self.escala_entrada, self.lbl_entrada, self.btn_mute_in, \
            self.lista_sources = self._armar_dispositivos('Micrófono')
        self._armar_apps()

        self.jugador = None
        self.sinks, self.sources, self.apps = [], [], []
        self._timers, self._pend = {}, {}
        os.makedirs(CACHE_ART, exist_ok=True)
        self._refrescar()
        self._seguir()

    def _margen_izq(self):
        try:
            out = subprocess.run(['hyprctl', 'cursorpos'], capture_output=True,
                                 text=True, timeout=2).stdout
            x = int(out.split(',')[0])
        except (ValueError, IndexError, subprocess.TimeoutExpired):
            x = ICONO_X_FALLBACK
        return max(MARGEN, min(x - ANCHO // 2, PANTALLA - ANCHO - MARGEN))

    # ── construccion ─────────────────────────────────────────────────────────

    def _seccion(self, texto):
        lbl = Gtk.Label(label=texto, xalign=0)
        lbl.get_style_context().add_class('seccion')
        self.cont.pack_start(lbl, False, False, 2)
        return lbl

    def _armar_reproductor(self):
        self.sec_player = self._seccion('Reproductor')
        self.tabs = Gtk.Box(spacing=4)
        self.cont.pack_start(self.tabs, False, False, 0)

        fila = Gtk.Box(spacing=10)
        self.art = Gtk.Image()
        fila.pack_start(self.art, False, False, 0)
        textos = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.lbl_cancion = Gtk.Label(label='Nada sonando', xalign=0)
        self.lbl_cancion.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_cancion.get_style_context().add_class('cancion')
        self.lbl_artista = Gtk.Label(label='', xalign=0)
        self.lbl_artista.set_ellipsize(Pango.EllipsizeMode.END)
        self.lbl_artista.get_style_context().add_class('sutil')
        textos.pack_start(self.lbl_cancion, False, False, 0)
        textos.pack_start(self.lbl_artista, False, False, 0)
        fila.pack_start(textos, True, True, 0)
        self.cont.pack_start(fila, False, False, 0)

        # clic en el titulo → focar la ventana del reproductor
        evento = Gtk.EventBox()
        fila.remove(textos)
        evento.add(textos)
        evento.connect('button-press-event', lambda *_: (
            subprocess.Popen([os.path.expanduser('~/.config/hypr/scripts/focus-player.sh')]),
            Gtk.main_quit()) and None)
        fila.pack_start(evento, True, True, 0)

        controles = Gtk.Box(spacing=20)
        controles.set_halign(Gtk.Align.CENTER)
        for icono, orden in ((I_PREV, 'previous'), (I_PLAY, 'play-pause'), (I_NEXT, 'next')):
            b = Gtk.Button(label=icono)
            b.get_style_context().add_class('control')
            b.connect('clicked', self._control, orden)
            controles.pack_start(b, False, False, 0)
            if orden == 'play-pause':
                self.btn_play = b
        self.cont.pack_start(controles, False, False, 0)

    def _armar_dispositivos(self, nombre):
        self._seccion(nombre)
        fila = Gtk.Box(spacing=8)
        lbl = Gtk.Label(label='')
        lbl.set_width_chars(7)
        escala = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        escala.set_draw_value(False)
        escala.set_hexpand(True)
        mute = Gtk.Button(label=I_MUTE)
        fila.pack_start(lbl, False, False, 0)
        fila.pack_start(escala, True, True, 0)
        fila.pack_start(mute, False, False, 0)
        self.cont.pack_start(fila, False, False, 0)

        lista = Gtk.ListBox()
        lista.set_selection_mode(Gtk.SelectionMode.NONE)
        self.cont.pack_start(lista, False, False, 0)

        es_salida = nombre == 'Salida'
        objetivo = '@DEFAULT_AUDIO_SINK@' if es_salida else '@DEFAULT_AUDIO_SOURCE@'
        escala.connect('value-changed',
                       lambda e: self._debounce(objetivo, e.get_value()))
        mute.connect('clicked', lambda *_: self._en_hilo(
            lambda: sh('wpctl', 'set-mute', objetivo, 'toggle')))
        lista.connect('row-activated',
                      self._sel_sink if es_salida else self._sel_source)
        return fila, escala, lbl, mute, lista

    def _armar_apps(self):
        self.sec_apps = self._seccion('Aplicaciones')
        self.caja_apps = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.cont.pack_start(self.caja_apps, False, False, 0)

    # ── datos ────────────────────────────────────────────────────────────────

    def _refrescar(self):
        threading.Thread(target=self._cargar, daemon=True).start()

    def _cargar(self):
        jugadores = [j for j in sh('playerctl', '-l').splitlines() if j]
        activo = self.jugador if self.jugador in jugadores else (jugadores[0] if jugadores else None)
        cancion = artista = estado = ''
        ruta_art = None
        if activo:
            sel = ['-p', activo]
            meta = sh('playerctl', *sel, 'metadata', '--format',
                      f'{{{{title}}}}{SEP}{{{{artist}}}}{SEP}{{{{mpris:artUrl}}}}')
            partes = (meta.strip('\n') + SEP * 2).split(SEP)
            cancion, artista, url_art = partes[0], partes[1], partes[2]
            estado = sh('playerctl', *sel, 'status').strip()
            ruta_art = self._bajar_art(url_art) if url_art else None

        vol_out = sh('wpctl', 'get-volume', '@DEFAULT_AUDIO_SINK@')
        vol_in = sh('wpctl', 'get-volume', '@DEFAULT_AUDIO_SOURCE@')
        sinks = pactl_json('sinks')
        sources = [s for s in pactl_json('sources')
                   if '.monitor' not in s.get('name', '')]
        apps = pactl_json('sink-inputs')
        df_sink = sh('pactl', 'get-default-sink').strip()
        df_source = sh('pactl', 'get-default-source').strip()
        GLib.idle_add(self._pintar, jugadores, activo, cancion, artista, estado,
                      ruta_art, vol_out, vol_in, sinks, sources, apps,
                      df_sink, df_source)

    def _bajar_art(self, url):
        if url.startswith('file://'):
            return url[7:]
        if not url.startswith(('http://', 'https://')):
            return None
        destino = os.path.join(CACHE_ART, hashlib.md5(url.encode()).hexdigest())
        if not os.path.exists(destino):
            try:
                with urllib.request.urlopen(url, timeout=3) as r, open(destino, 'wb') as f:
                    f.write(r.read())
            except OSError:
                return None
        return destino

    def _pintar(self, jugadores, activo, cancion, artista, estado, ruta_art,
                vol_out, vol_in, sinks, sources, apps, df_sink, df_source):
        self.sinks, self.sources, self.apps = sinks, sources, apps
        self._actualizando = True

        for hijo in self.tabs.get_children():
            self.tabs.remove(hijo)
        if len(jugadores) > 1:
            for j in jugadores:
                b = Gtk.Button(label=j.split('.')[0])
                b.get_style_context().add_class('tab')
                b.connect('clicked', self._tab, j)
                self.tabs.pack_start(b, False, False, 0)
            self.tabs.show_all()

        self.lbl_cancion.set_text(cancion or 'Nada sonando')
        self.lbl_artista.set_text(artista or (activo.split('.')[0] if activo else ''))
        self.btn_play.set_label(I_PAUSE if estado == 'Playing' else I_PLAY)
        pix = None
        if ruta_art and os.path.exists(ruta_art):
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(ruta_art, 56, 56, True)
            except GLib.Error:
                pix = None
        if pix:
            self.art.set_from_pixbuf(pix)
        else:
            self.art.set_from_icon_name('audio-x-generic', Gtk.IconSize.DIALOG)

        self._pintar_volumen(self.escala_salida, self.lbl_salida, vol_out, I_VOL, I_MUTE)
        self._pintar_volumen(self.escala_entrada, self.lbl_entrada, vol_in,
                             [I_MIC, I_MIC, I_MIC], I_MIC_MUTE)

        self._pintar_lista(self.lista_sinks, sinks, df_sink)
        self._pintar_lista(self.lista_sources, sources, df_source)

        for hijo in self.caja_apps.get_children():
            self.caja_apps.remove(hijo)
        visibles = bool(apps)
        self.sec_apps.set_visible(visibles)
        self.caja_apps.set_visible(visibles)
        for app in apps:
            props = app.get('properties', {})
            nombre = props.get('application.name') or props.get('media.name') or '?'
            fila = Gtk.Box(spacing=8)
            lbl = Gtk.Label(label=nombre, xalign=0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.set_width_chars(12)
            lbl.get_style_context().add_class('sutil')
            escala = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
            escala.set_draw_value(False)
            escala.set_hexpand(True)
            escala.set_value(pct_volumen(app))
            idx = str(app['index'])
            escala.connect('value-changed',
                           lambda e, i=idx: self._debounce(f'app{i}', e.get_value(), i))
            mute = Gtk.Button(label=I_MUTE if app.get('mute') else I_VOL[2])
            mute.connect('clicked', lambda _b, i=idx: self._en_hilo(
                lambda: sh('pactl', 'set-sink-input-mute', i, 'toggle')))
            fila.pack_start(lbl, False, False, 0)
            fila.pack_start(escala, True, True, 0)
            fila.pack_start(mute, False, False, 0)
            self.caja_apps.pack_start(fila, False, False, 0)
        self.caja_apps.show_all()
        self._actualizando = False
        return False

    def _pintar_volumen(self, escala, lbl, salida, iconos, icono_mute):
        m = re.search(r'([\d.]+)', salida)
        pct = int(float(m.group(1)) * 100) if m else 0
        muteado = 'MUTED' in salida
        escala.set_value(pct)
        icono = icono_mute if muteado else iconos[min(pct * 3 // 101, 2)]
        lbl.set_text(f'{icono} {pct}%')

    def _pintar_lista(self, lista, dispositivos, defecto):
        for hijo in lista.get_children():
            lista.remove(hijo)
        for d in dispositivos:
            fila = Gtk.ListBoxRow()
            marca = '✓' if d.get('name') == defecto else ' '
            # pactl escribe la cadena literal "(null)" cuando no hay description
            desc = d.get('description')
            if not desc or desc == '(null)':
                desc = d.get('properties', {}).get('device.description') or d.get('name')
            lbl = Gtk.Label(label=f"{marca}  {desc}", xalign=0)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            if d.get('name') == defecto:
                lbl.get_style_context().add_class('conectada')
            else:
                lbl.get_style_context().add_class('sutil')
            fila.add(lbl)
            lista.add(fila)
        lista.show_all()

    # ── acciones ─────────────────────────────────────────────────────────────

    def _tab(self, _b, jugador):
        self.jugador = jugador
        self._refrescar()

    def _control(self, _b, orden):
        sel = ['-p', self.jugador] if self.jugador else []
        self._en_hilo(lambda: sh('playerctl', *sel, orden))

    def _debounce(self, clave, valor, app=None):
        if getattr(self, '_actualizando', False):
            return
        self._pend[clave] = (valor, app)
        if clave not in self._timers:
            self._timers[clave] = GLib.timeout_add(90, self._aplicar_vol, clave)

    def _aplicar_vol(self, clave):
        valor, app = self._pend.pop(clave)
        del self._timers[clave]
        if app:
            threading.Thread(target=lambda: sh(
                'pactl', 'set-sink-input-volume', app, f'{int(valor)}%'),
                daemon=True).start()
        else:
            threading.Thread(target=lambda: sh(
                'wpctl', 'set-volume', clave, f'{valor / 100:.2f}'),
                daemon=True).start()
        return False

    def _sel_sink(self, _lista, fila):
        d = self.sinks[fila.get_index()]
        self._en_hilo(lambda: sh('pactl', 'set-default-sink', d['name']))

    def _sel_source(self, _lista, fila):
        d = self.sources[fila.get_index()]
        self._en_hilo(lambda: sh('pactl', 'set-default-source', d['name']))

    def _en_hilo(self, fn):
        def tarea():
            fn()
            self._cargar()
        threading.Thread(target=tarea, daemon=True).start()

    # ── refresco automatico ──────────────────────────────────────────────────

    def _seguir(self):
        # playerctl -F emite una linea por cada cambio de estado del reproductor
        self.proc_follow = subprocess.Popen(
            ['playerctl', '-a', '-F', 'status'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)

        def bucle():
            for _ in self.proc_follow.stdout:
                GLib.idle_add(self._refrescar)
        threading.Thread(target=bucle, daemon=True).start()

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
    panel = None
    try:
        panel = Panel()
        panel.connect('destroy', Gtk.main_quit)
        panel.show_all()
        Gtk.main()
    finally:
        if panel and getattr(panel, 'proc_follow', None):
            panel.proc_follow.terminate()
        if os.path.exists(PIDFILE):
            os.unlink(PIDFILE)
