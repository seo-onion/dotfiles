#!/usr/bin/env bash
# Uso de CPU por deltas de /proc/stat (el modulo nativo no deja meter procesos
# en el tooltip, de ahi el custom). Salida JSON para waybar.

STATE="${XDG_RUNTIME_DIR:-/tmp}/waybar-cpu.prev"

read -r _ u n s i w irq sirq st _ < /proc/stat
total=$((u + n + s + i + w + irq + sirq + st))
busy=$((total - i - w))

pct=0
if [[ -r $STATE ]]; then
    read -r ptotal pbusy < "$STATE"
    dt=$((total - ptotal))
    [[ $dt -gt 0 ]] && pct=$(( 100 * (busy - pbusy) / dt ))
fi
printf '%s %s\n' "$total" "$busy" > "$STATE"

# ps mide %CPU sobre UN nucleo (techo 800% con 8), pero el numero de la barra es
# sobre la maquina entera. Se divide entre los nucleos para que ambos usen la
# misma escala y el tooltip sume mas o menos lo que marca la barra.
# Ademas es la media desde que nacio el proceso, no el instante: caza al que
# lleva rato quemando nucleos, no un pico de medio segundo.
# Se descarta el propio 'ps': aparece siempre en cabeza porque es quien mide.
ncpu=$(nproc)
tip=$(ps -eo pcpu=,comm= --sort=-pcpu |
      awk -v n="$ncpu" '$2 != "ps" {
          gsub(/["\\]/, "", $2)
          printf "%5.1f%%   %s\n", $1 / n, $2
          if (++shown == 6) exit
      }')

printf '{"text":"%s%%","tooltip":"%s"}\n' "$pct" "${tip//$'\n'/\\n}"
