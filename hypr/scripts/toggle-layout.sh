#!/usr/bin/env bash
current=$(hyprctl getoption general:layout | awk '/str:/{print $2}')
if [ "$current" = "dwindle" ]; then
    hyprctl keyword general:layout master
    notify-send -t 1200 "Layout" "Master"
else
    hyprctl keyword general:layout dwindle
    notify-send -t 1200 "Layout" "Dwindle"
fi
