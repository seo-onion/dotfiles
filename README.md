# Escritorio — Zenbook (Fedora + Hyprland)

Configuración del escritorio: Hyprland (config **Lua**, 0.56+ del COPR
blacktau), waybar con 7 paneles GTK layer-shell propios, Sherlock, SwayNC,
kitty y el tema Tron transversal.

La documentación de verdad vive dentro:

- `hypr/ESCRITORIO.md` — arquitectura, decisiones y el historial de cambios
  (incluye por qué se revirtió el apilado en grupos y las trampas conocidas:
  glifos PUA, SIGUSR2 en waybar, `hyprctl keyword` vs `eval`, etc.)
- `hypr/theme.md` — paleta Tron
- `waybar/DESIGN.md` — diseño de la barra

## Los 7 paneles

Iconos de la waybar → paneles gemelos en `hypr/scripts/*-panel.py`
(GTK3 + gtk-layer-shell, misma técnica que swaync): wifi, bluetooth, audio,
batería, energía, pantalla y calendario. Toggle por pidfile, cover-screen
transparente (clic fuera cierra), animación slide-top por layer rule.

## Restaurar en una máquina nueva

```sh
git clone <este-repo> ~/.config-tmp && cp -rT ~/.config-tmp ~/.config
```

Además hace falta:

- Paquetes: hyprland (COPR blacktau), waybar, swaync, kitty, copyq, swaybg,
  wlsunset, kanshi, swayosd, grim, brightnessctl, khal, vdirsyncer, hyprlock,
  gtk-layer-shell, python3-gobject, playerctl
- JetBrainsMono Nerd Font en `~/.local/share/fonts` (los glifos de TODO)
- Sherlock compilado a mano (`~/.local/src/sherlock`)
- Fondos en `~/Imágenes/Fondos/` (el symlink `hypr/wallpaper` apunta ahí)
- `vdirsyncer/config` real: copiar de `config.example` y seguir los pasos
  comentados (credenciales OAuth de Google — **nunca commitear el real**)
