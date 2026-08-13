#!/usr/bin/env bash
# Abre CopyQ y lo cierra cuando pierde el foco, igual que el panel de
# notificaciones. Si al abrirse no llega a recibir el foco, tiene 2 segundos
# de gracia.
#
# Cerrar tiene que hacerlo Hyprland: bajo Wayland copyq hide y copyq toggle no
# ocultan la ventana. Cerrarla no mata el servidor.

CLASE=com.github.hluk.copyq
GRACIA=2

estado() {
    hyprctl clients -j | jq -r --arg c "$CLASE" \
        '[.[] | select(.class == $c)]
         | if length == 0 then "no"
           elif .[0].focusHistoryID == 0 then "foco"
           else "sinfoco" end'
}

cerrar() {
    hyprctl dispatch "hl.dsp.window.close({ window = \"class:$CLASE\" })" >/dev/null
}

[ "$(estado)" != "no" ] && { cerrar; exit; }

copyq show

visto=0
tuvo_foco=0
inicio=$SECONDS

while :; do
    case "$(estado)" in
        no)      (( visto || SECONDS - inicio >= 15 )) && exit ;;
        foco)    visto=1; tuvo_foco=1 ;;
        sinfoco) visto=1
                 (( tuvo_foco || SECONDS - inicio >= GRACIA )) && { cerrar; exit; } ;;
    esac
    sleep 0.15
done
