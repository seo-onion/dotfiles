#!/usr/bin/env bash
# F11 — toggle modo nocturno (comparte temp con display-menu.sh)

TEMP=$(cat ~/.config/hypr/.nighttemp 2>/dev/null || echo "3500")

notify() { notify-send --app-name="Brillo Nocturno" "$1" "$2" -t 2500; }

if pgrep -x wlsunset &>/dev/null; then
    pkill -x wlsunset
    notify "󰌔  Brillo Nocturno" "Desactivado — temperatura normal"
else
    wlsunset -t "$TEMP" -T 6500 -S 23:59 -s 00:01 &
    notify "󰌓  Brillo Nocturno" "Activado — ${TEMP} K"
fi
