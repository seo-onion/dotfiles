#!/usr/bin/env bash
player=$(playerctl -l 2>/dev/null | head -1)
[ -z "$player" ] && exit 0

# MPV / VLC: clase directa
case "${player,,}" in
    mpv*) hyprctl dispatch focuswindow class:mpv ; exit 0 ;;
    vlc*) hyprctl dispatch focuswindow class:vlc ; exit 0 ;;
esac

# Obtener PID real del proceso dueño del servicio MPRIS en D-Bus
bus_name="org.mpris.MediaPlayer2.$player"
pid=$(dbus-send --session --dest=org.freedesktop.DBus \
    --type=method_call --print-reply \
    /org/freedesktop/DBus \
    org.freedesktop.DBus.GetConnectionUnixProcessID \
    string:"$bus_name" 2>/dev/null | grep -oP 'uint32 \K\d+')

[ -z "$pid" ] && exit 1

# Enfocar la ventana exacta por PID
addr=$(hyprctl clients -j | python3 -c "
import json, sys
for c in json.load(sys.stdin):
    if c['pid'] == $pid:
        print(c['address'])
        break
" 2>/dev/null)

if [ -n "$addr" ]; then
    hyprctl dispatch focuswindow "address:$addr"
else
    case "${player,,}" in
        firefox*)  hyprctl dispatch focuswindow class:org.mozilla.firefox ;;
        chromium*) hyprctl dispatch focuswindow class:chromium ;;
    esac
fi

# Cambiar al tab usando el modo de búsqueda de tabs de Firefox (% prefix)
title=$(playerctl metadata title 2>/dev/null)
[ -z "$title" ] && exit 0

search="${title:0:25}"

sleep 0.2
wtype -M ctrl -k l -m ctrl   # abrir barra de URL
sleep 0.15
wtype "% $search"             # % = buscar solo entre tabs abiertos
sleep 0.4                     # esperar sugerencias
wtype -k Down                 # mover foco a la primera sugerencia
sleep 0.05
wtype -k Return               # ir al tab (nunca abre tab nuevo)
