# waybar — panel completo

Última revisión: 2026-08-12

## Qué es esto

La barra pasó de 7 módulos a 19, sin dependencias nuevas: todos los añadidos ya
venían compilados en el waybar de Fedora y no se estaban usando.

## Distribución

| Zona | Módulos |
|---|---|
| Izquierda | `hyprland/workspaces`, `custom/add-workspace`, `hyprland/window` |
| Centro | `clock`, `mpris` |
| Derecha | `privacy`, `wireplumber`, `backlight`, `temperature`, `cpu`, `power-profiles-daemon`, `network`, `bluetooth`, `battery`, `tray`, `custom/swaync`, `custom/clipboard`, `custom/display-panel`, `custom/power` |

## Decisiones que no son obvias

### El sensor de temperatura no es la CPU

El driver `k10temp` no está cargado, así que no hay lectura del núcleo (Tctl).
Se usa el hwmon de `amdgpu`: en un APU Ryzen la GPU está en el mismo dado, así
que sigue de cerca la temperatura del paquete. Es un sustituto, no el ideal.

La ruta se fija con `hwmon-path-abs` + `input-filename`, **nunca** con
`/sys/class/hwmon/hwmonN`: esa numeración cambia entre reinicios y acabaría
leyendo otro sensor.

```
hwmon-path-abs: /sys/devices/pci0000:00/0000:00:08.1/0000:63:00.0/hwmon
input-filename: temp1_input
```

### El reloj necesita el prefijo `L` para hablar español

```
"format": "{:L%H:%M  —  %d %b}"
```

Sin esa `L`, waybar usa el locale «C» de C++ e ignora `LANG`, aunque `locale`
esté puesto en la config. Salía «12 Aug» en vez de «12 ago».

### El calendario es nativo, no un script

Sustituyó a `calendar-menu.sh` (37 líneas de bash + wofi). Vive en el tooltip
del reloj:

- Rueda del ratón sobre el reloj → mes anterior / siguiente
- Clic derecho → alterna vista mes / año
- El día de hoy va en cian subrayado

### El tooltip lleva el borde estándar

El calendario vive en el tooltip del reloj, así que el tooltip usa el mismo
borde que las ventanas: 2px con degradado 45° `#33CCFF → #00FF99` y radio 4.

Se pinta con dos fondos superpuestos, igual que en Sherlock, porque
`border-image` ignoraría el `border-radius`. GTK3 lo parsea sin errores.

### Los iconos se colorean con marcado Pango, no con CSS

CSS teñiría el módulo entero (icono + texto). Con `<span color='…'>{icon}</span>`
solo se colorea el glifo y el texto se queda en plata.

**La batería en estado normal se deja sin color a propósito.** Si se le pusiera
color aquí, pisaría el rojo de «menos del 15 %» que aplica el CSS por clase.

### Paleta

| Color | Módulos |
|---|---|
| Cian Neón `#00F0FF` | volumen, red, portapapeles, botón `+` |
| Azul Cielo `#33CCFF` | brillo, bluetooth, notificaciones, pantalla |
| Verde Menta `#00FF99` | temperatura, perfil de energía, música, batería cargando |
| Azul Eléctrico `#0066FF` | CPU, volumen silenciado |
| Rojo `#ff4444` | temperatura crítica, sin conexión, batería < 15 % |
| Gris `#595959` | wifi / bluetooth apagados |

### Los glifos hay que verificarlos contra la fuente

Al reescribir el config se perdieron 7 iconos del rango bajo de Nerd Font
(`U+F0xx`–`U+F2xx`): quedaron como `<span>` vacíos y la barra tuvo huecos en
blanco durante horas sin que saltara ningún error.

Para comprobarlo, contrastar cada glifo contra el archivo de la fuente y además
verificar que ningún `<span>` esté vacío. Contar glifos presentes no basta: eso
fue justo lo que no detectó el fallo.

Al escribir glifos por script, usar `chr(0xF2C9)` en lugar del carácter literal:
los del rango bajo se corrompen al pasar por heredocs.

### La bandeja

Antes no había ninguna en el sistema, así que las apps que querían poner un
icono desaparecían en silencio. Con el módulo `tray`, waybar es el host.

Ahora mismo está **vacía a propósito**: el único inquilino era CopyQ y se le
quitó (`disable_tray=true`) porque duplicaba el icono de portapapeles. El módulo
se queda para la próxima app que lo necesite.

### El portapapeles no llama a `copyq` directamente

`custom/clipboard` ejecuta `~/.config/hypr/scripts/clipboard.sh`, no
`copyq toggle`. Bajo Wayland ni `copyq toggle` ni `copyq hide` cierran la
ventana, así que el script la abre y la cierra él mismo vigilando el foco — las
mismas reglas que el panel de notificaciones, para que los dos se comporten
igual. El porqué completo está en `~/.config/hypr/ESCRITORIO.md`.

## Coste

Solo dos módulos sondean: temperatura cada 10 s y CPU cada 5 s. El resto son
por eventos.

Medido con muestras de 60 s y la barra asentada:

| | CPU | Módulos |
|---|---|---|
| Antes | 0.033 % | 7 |
| Después | 0.383 % | 19 |

Sube ~11×, pero en absoluto es despreciable frente a los 6.86 W del equipo.

**Aviso para futuras mediciones:** un primer intento con muestras de 15 s dio
resultados imposibles (quitar un módulo salía *más* caro que dejarlo). La
ventana era demasiado corta y el arranque de waybar contaminaba la muestra.

## Pendiente

- `power-profiles-daemon` no está instalado, así que ese módulo muestra siempre
  el icono por defecto y no controla nada. Instalarlo o quitar el módulo.
- Quedan 5 menús wofi enganchados: red, bluetooth, batería, pantalla y energía.
