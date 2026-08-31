# El escritorio, pieza por pieza

Última revisión: 2026-08-12

Qué hace cada programa, dónde vive su configuración y qué decisiones no son
obvias. Los colores y la geometría están en `theme.md`.

## Piezas

| Pieza | Programa | Config |
|---|---|---|
| Compositor | Hyprland 0.56.2 | `~/.config/hypr/hyprland.lua` |
| Barra | waybar | `~/.config/waybar/` — ver `DESIGN.md` |
| Lanzador | Sherlock 0.1.14 | `~/.config/sherlock/` |
| Notificaciones | SwayNC 0.12.6 | `~/.config/swaync/` |
| Portapapeles | CopyQ 16.0.0 | `~/.config/copyq/` |
| Fondo | swaybg | en el autostart de `hyprland.lua` |

## Hyprland

### La config es Lua, no `.conf`

El formato `.conf` desaparece en 0.57. Se migró a `hyprland.lua`.

`~/.config/hypr/hyprland.conf` **sigue ahí a propósito**: si algo se rompe,
`mv hyprland.lua hyprland.lua.roto` y vuelves al anterior al instante. Cuando
existen los dos, Lua gana automáticamente.

### Para validar antes de aplicar

```
Hyprland --verify-config -c ~/.config/hypr/hyprland.lua
```

Esta es la fuente fiable. Con config Lua:

- `hyprctl keyword` **ya no funciona** («keyword can't work with non-legacy parsers»)
- `hyprctl dispatch` pasa por el intérprete de Lua: la sintaxis de siempre
  (`hyprctl dispatch dpms off eDP-1`) da error de sintaxis y **no ejecuta nada**,
  aunque devuelva algo que parece un aviso menor. La forma correcta es
  `hyprctl dispatch 'hl.dsp.dpms("off eDP-1")'`
- `hyprctl configerrors` acumula además errores de `dispatch` en ejecución, así
  que puede mostrar cosas que no son del archivo. Se limpian con `hyprctl reload`

### Referencia de la API

`/usr/share/hypr/stubs/hl.meta.lua` — todas las funciones y campos válidos.
`/usr/share/hypr/hyprland.lua` — config de ejemplo oficial.

### Lo que se perdió al pasar a 0.56

- `dwindle:pseudotile` — la opción ya no existe
- `suppressevent` en formato `.conf` — **recuperado** en Lua como `suppress_event`

### Al cerrar la tapa no pasa nada

Dos capas distintas, las dos ya resueltas:

- **Suspensión:** la ignora logind, en `/etc/systemd/logind.conf.d/99-lid-ignore.conf`
  (`HandleLidSwitch=ignore` y sus dos variantes). No hay hypridle ni swayidle.
- **Pantalla:** desde el 2026-08-13 la tapa NO tiene binds: cerrarla no hace
  nada (ni dpms ni suspender) y el equipo sigue trabajando normal. Antes
  apagaba el panel con `dpms`.

Antes ese bind hacía `disabled = true` sobre eDP-1. Con un único monitor eso
manda los workspaces a una salida fantasma y las ventanas vuelven descolocadas.
`dpms` deja el monitor activo, solo sin luz.

## Sherlock (lanzador)

### Enter no lanzaba nada

Sherlock resuelve las teclas con `self.binds.get(key)`, y ese mapa sale directo
de `[keybinds]` en `config.toml`. **No rellena valores por defecto.** Con la
sección vacía, Enter no estaba asociado a nada.

```toml
[keybinds]
"return" = "exec"
```

Escape sí funciona: está cableado en `window.rs`, no depende de esa tabla.

La sección `[binds]` queda obsoleta en la 0.1.15. Al actualizar habrá que
migrar esas líneas a `[keybinds]`.

### El borde con degradado y esquinas redondeadas

`border-image` **ignora `border-radius`** y deja las esquinas cuadradas. Para
tener degradado y redondeo a la vez se pintan dos fondos superpuestos:

```css
background-image:
    linear-gradient(var(--background), var(--background)),
    linear-gradient(45deg, #33CCFF, #00FF99);
background-origin: border-box;
background-clip: padding-box, border-box;
```

Lo que asoma por los 2px del borde es el degradado.

## SwayNC (notificaciones)

Se tematiza **redefiniendo sus variables CSS**, no escribiendo reglas propias.
SwayNC carga `/etc/xdg/swaync/style.css` primero y el del usuario después, y sus
selectores son larguísimos: cualquier regla corta pierde por especificidad.

Los nombres reales no son los intuitivos:

| Lo que parece | Lo que es |
|---|---|
| `.notification` | `.notification-row .notification-background .notification` |
| `.notification-title` | *no existe* — es `.text-box .summary` |

### El blur del escritorio venía de aquí

Al abrir el panel se emborronaba **la pantalla entera**, no solo el fondo del
panel. La causa: `layer-shell-cover-screen` viene en `true`, así que la
superficie de swaync ocupa 1920×1200 aunque solo se pinte una columna. Con un
`layer_rule` de `blur` encima, Hyprland difumina todo lo que hay detrás de esa
superficie.

Se quitó el `blur` de las dos reglas y se puso `layer-shell-cover-screen: false`.

### Mismas medidas que el portapapeles

El panel es una copia exacta del de CopyQ: 450 × 1132 a 16px del borde derecho y
16px bajo la barra. Los márgenes se cuentan **desde donde acaba la waybar**, no
desde el borde de la pantalla: la barra es exclusiva y ya empuja la capa 36px,
así que `control-center-margin-top` es 16, no 52.

`control-center-height` es un mínimo, no un máximo: la ventana crece con el
contenido pero nunca baja de ese valor. Con un número pequeño el panel sale
recortado a media altura.

### El marco hay que repintarlo en CSS

swaync es una **capa**, no una ventana, y Hyprland no les pinta ni borde ni
sombra a las capas. El marco de 2px con degradado y el resplandor cian se
redibujan en `style.css` con la técnica de los dos fondos. Se ve igual que el
resto del sistema, pero si cambia la paleta hay que tocarlo aquí también.

**El margen va en el CSS, no en `control-center-margin-*`.** Con los márgenes
del config, el panel ocupa la superficie entera y GTK recorta el `box-shadow`:
el resplandor está definido y no se ve ni un píxel. Poniendo `margin: 16px` en
`.control-center`, la sombra tiene sitio donde pintarse dentro de la superficie.

Como el margen vive en el CSS, las medidas del config son **las de la
superficie**, no las del panel: `control-center-height: 1164` para un panel de
1132 (16 arriba + 16 abajo). Los márgenes del config se quedan en 0.

Medido en píxeles hacia fuera del borde, a media altura:

| | Antes | Ahora | CopyQ |
|---|---|---|---|
| a 4px | `5,7,12` | `5,58,67` | `5,69,80` |
| a 8px | `5,7,12` | `5,122,134` | `5,157,173` |

Plano contra rampa. Si el resplandor «no está», comparar así antes de tocar el
CSS: puede estar definido y simplemente recortado.

La animación sí es de Hyprland: `animation = "slide right"` en el `layer_rule`,
la misma entrada que el portapapeles.

### Las tarjetas de la lista van sin caja

Dentro del panel las notificaciones no llevan fondo, ni borde, ni sombra: el
marco ya lo pone el panel. Al pasar el ratón se enciende un fondo plano. El
**toast** sí lleva caja, porque flota sobre el escritorio y necesita separarse
de él.

**En `.notification-default-action` GTK solo hace caso a `background`.** Ese
botón ocupa la tarjeta entera y es el que recibe el `:hover`. Se probaron en él
`border`, `outline` y `box-shadow` (normal e `inset`): ninguno pinta nada, ni
siquiera con `border-image: none`. En estático el borde sí sale; en `:hover` no.
Por eso el resaltado es un color de fondo y no un marco.

Para saber qué elemento recibe de verdad el `:hover`, píntalo de amarillo un
momento. Deducirlo del árbol de widgets no funciona: aquí el fondo que parecía
hover resultó ser el `:focus` de la fila.

### El fondo azulado del `:focus` se apaga por variable

La fila seleccionada se pintaba de cian translúcido con `--noti-bg-focus`.
Pelearlo con selectores no sirve; se apaga poniendo la variable en
`transparent`, igual que el resto del tema.

### Cosas que no se pueden quitar con `display: none`

GTK3 no entiende `display: none`. Para hacer desaparecer la X de cerrar y el
icono del estado vacío hay que encogerlos: `opacity: 0` más `min-width`,
`min-height`, `margin` y `padding` a cero.

El texto del estado vacío sí es configurable: `text-empty` en `config.json`.

## CopyQ (portapapeles)

Sustituyó a `clipboard-menu.sh`. La barra lo abre con
`scripts/clipboard.sh`, no con `copyq toggle` — ver más abajo por qué.

### El tema se guarda en `copyq.conf`, no en `themes/tron.ini`

CopyQ copia los valores a la sección `[Theme]` de `copyq.conf` cuando cargas un
tema. **Los bloques CSS multilínea se corrompen en esa copia**: los saltos de
línea colapsan y las claves se comen unas a otras, dejando cosas como

```ini
cur_item_css="\nhover_item_css="
```

Resultado: los colores planos se aplican pero todo el CSS del tema queda muerto.
Al editar a mano hay que usar el escapado de QSettings (`\n` dentro de comillas).

`copyq config` **no alcanza las claves del tema**, solo las de `[Options]`.

### Sin icono en la bandeja

`disable_tray=true`. CopyQ ponía unas tijeras en la bandeja que duplicaban el
icono de portapapeles de la barra, y la bandeja no hacía falta para nada.

**Trampa: sin bandeja, CopyQ abre la ventana al arrancar el servidor.** Es su
salvavidas — se asume que sin icono no tendrías cómo llegar a él. La ventana
aparecía sola en cada arranque de sesión y ya no se cerraba nunca, porque quien
la cierra es `clipboard.sh` y ese solo corre cuando haces clic en la waybar.
Se apaga con `hide_main_window=true`; la bandeja sigue desactivada y el clic
del módulo sigue abriéndola igual. Comprobado aislando la variable: con
`disable_tray=false` la ventana no aparecía, con `true` sí.

Para comprobar que no queda ningún icono registrado:

```
busctl --user get-property org.kde.StatusNotifierWatcher /StatusNotifierWatcher \
    org.kde.StatusNotifierWatcher RegisteredStatusNotifierItems
```

### Los iconos no se pueden cambiar

La lupa y la X vienen de una FontAwesome compilada dentro del binario
(`:/images/fontawesome.ttf`) y CopyQ las colorea desde la paleta de Qt. Ninguna
de las 60 claves del tema las controla.

No es tan grave: los iconos de la waybar son de esa misma familia, porque Nerd
Font incluye FontAwesome. Coincide la forma, no el color.

### Se abre y se cierra desde un script, no desde CopyQ

`~/.config/hypr/scripts/clipboard.sh`. Dos cosas de CopyQ no funcionan aquí, las
dos comprobadas:

| Lo que debería pasar | Lo que pasa |
|---|---|
| `close_on_unfocus=true` cierra el panel al perder el foco | se queda abierto con el foco ya en otra ventana |
| `copyq hide` / `copyq toggle` ocultan la ventana | `copyq visible` sigue diciendo `true` |

Lo único que la cierra de verdad es cerrar la ventana desde Hyprland:

```
hyprctl dispatch 'hl.dsp.window.close({ window = "class:com.github.hluk.copyq" })'
```

Eso **no mata el servidor** de CopyQ, solo quita la ventana; el historial sigue
grabándose.

El script mira el **foco** cada 150 ms, las mismas reglas que el panel de
notificaciones:

- mientras tenga el foco, se queda abierto
- en cuanto el foco se va a otra ventana, se cierra
- si al abrirse no llega a recibirlo, tiene 2 segundos de gracia

El ratón no interviene. Hubo una versión que cerraba al salir el puntero y era
peor de dos maneras: el panel ocupa el 24% del ancho de la pantalla de arriba
abajo, así que apartar el ratón «a un lado» casi nunca lo saca de la zona; y al
apartarlo para escribir, se cerraba en mitad de la búsqueda.

**Al medir esto, ojo con quién mueve el ratón.** Varias conclusiones falsas
salieron de tests que movían el cursor por script mientras la persona movía el
suyo de verdad. Los saltos que parecían un warp del compositor eran una mano.

### `pin = true` en la regla, o se abre en otro workspace

CopyQ reaparecía en el workspace donde se abrió la primera vez. Estando en el 1
con la ventana en el 3, no se veía nada y encima el cursor nunca la enfocaba, lo
que despistaba mucho al depurar el cierre automático.

### Al depurarlo, ojo con las capturas

El historial suele estar lleno de capturas de pantalla (54 de 60 elementos en un
momento dado). CopyQ las muestra como miniaturas, y varias eran capturas *de la
propia CopyQ*. Eso parece un fallo de renderizado y no lo es.

## Nemo (gestor de archivos)

El menú «Abrir con» de VS Code / Sublime / Obsidian está resuelto con **dos
mecanismos distintos**, porque los tres gestos no son el mismo problema.

Clic sobre un **archivo** o una **carpeta**: Nemo ya tiene «Abrir con» nativo. Solo
faltaba que las apps estuvieran asociadas al tipo MIME. Se añaden en
`~/.config/mimeapps.list` bajo `[Added Associations]` — **no** copiando el
`.desktop` a `~/.local/share/applications/`, que lo congelaría y dejaría de
seguir las actualizaciones del paquete.

Clic en el **fondo vacío**: no existe menú nativo y no hay forma de añadirlo
salvo con acciones. Van en `~/.local/share/nemo/actions/*.nemo_action`, con
`Selection=none` — que significa literalmente «clic en el fondo», no «ninguna
acción» — y `%P`, la ruta de la carpeta actual.

### Las dos trampas

**`actions-tree.json` lleva un objeto en la raíz, no un array.** El archivo que
agrupa las acciones en el submenú «Abrir con» es
`~/.config/nemo/actions-tree.json` y su raíz tiene que ser
`{"toplevel": [ ... ]}`. Con un array suelto, Nemo lo rechaza entero con
`Structured actions couldn't be set up: … se esperaba un objeto` y las acciones
aparecen sueltas en la raíz del menú, sin agrupar. El `uuid` de cada acción es
su **nombre de archivo con extensión**.

**Una asociación añadida se convierte en el predeterminado si no hay uno fijado.**
Al añadir `text/plain=code.desktop` a `[Added Associations]`, el doble clic en un
`.txt` pasó de nvim a VS Code sin avisar. Para que solo aparezca en la lista de
«Abrir con» sin robar el predeterminado, hay que fijar el que ya había en
`[Default Applications]`.

### Obsidian es el caso raro

No abre carpetas, abre **bóvedas**, y su `.desktop` solo entiende
`x-scheme-handler/obsidian`. Pasarle una ruta no hace nada. Por eso no va por MIME
sino con `abrir-obsidian.sh`, que construye `obsidian://open?path=…` con la ruta
percent-encoded (sin eso se rompe con espacios y acentos). Si la carpeta no es una
bóveda, Obsidian pregunta si crear una: es su comportamiento normal.

### Depurar

    nemo --quit
    NEMO_DEBUG=Actions nemo --debug

Nemo solo registra las acciones que **descarta**. Si la tuya no sale en el log,
la aceptó.

## Cómo verificar que todo sigue en pie

```
Hyprland --verify-config -c ~/.config/hypr/hyprland.lua
python3 -c "import json;json.load(open('$HOME/.config/waybar/config'))"
bash -n ~/.config/hypr/scripts/*.sh
pgrep -x waybar; pgrep -x copyq; pgrep -x swaync
```

Para contar ventanas de una clase (útil al probar el portapapeles):

```
hyprctl clients -j | jq -r '[.[]|select(.class|test("copyq"))]|length'
```

## Al probar cosas, mover el cursor

Con la config en Lua, mover el ratón desde la terminal es la única forma de
provocar cambios de foco reales:

```
hyprctl dispatch 'hl.dsp.cursor.move({ x = 800, y = 500 })'
```

Guarda antes la posición con `hyprctl cursorpos` y devuélvela al terminar.

## Historial de limpieza

2026-08-12: retirados 823 líneas de scripts huérfanos (visualizador cava,
`display-panel.py` nunca conectado, y los menús de calendario y portapapeles
sustituidos por soluciones nativas). Copia en
`~/.config/hypr/scripts-retirados.tar.gz`.

2026-08-12: añadido `scripts/clipboard.sh` (~40 líneas) porque CopyQ no sabe
cerrarse solo bajo Wayland.

2026-08-13: eliminado `scripts/network-menu.sh` (wofi). Lo sustituye
`scripts/wifi-panel.py`: panel GTK3 + gtk-layer-shell (misma técnica que
swaync), namespace `wifi-panel`, animación slide-top vía layer rule en
`hyprland.lua`. Se abre desde el módulo network de la waybar y se centra en el
cursor (= el icono, aunque la barra se desplace); segunda invocación lo cierra
(pidfile en `$XDG_RUNTIME_DIR/wifi-panel.pid`, mismo patrón toggle que
clipboard.sh). La superficie cubre toda el área de trabajo (transparente) y el
panel es una caja dentro — mismo truco cover-screen que swaync — para que el
clic fuera lo cierre; por eso su layer rule tampoco debe llevar blur. Ojo con
el handler de clic fuera: los clics sobre widgets hijos llegan con coordenadas
relativas al hijo, hay que filtrar con `Gtk.get_event_widget`.

2026-08-13: eliminado `scripts/bluetooth-menu.sh` (wofi). Lo sustituye
`scripts/bluetooth-panel.py`, gemelo de wifi-panel.py (namespace
`bluetooth-panel`, pidfile propio, misma layer rule slide-top). Conserva todo
lo del menú viejo: encender/apagar, conectados con batería, emparejados,
descubiertos (emparejar+trust+conectar), olvidar (botón ✕ en la fila) y
escaneo de 8s. Los glifos van como escapes `\U000f...` en el código, no como
caracteres. Quedan en wofi: power, battery y display.

2026-08-13: añadido `scripts/audio-panel.py` (tercer panel gemelo, namespace
`audio-panel`), en el clic del módulo wireplumber de la waybar; el mute pasó
al clic derecho y el scroll sigue igual. Secciones: reproductor MPRIS
(playerctld elige el activo, pestañas si hay varios, carátula, clic en el
título foca la ventana vía `focus-player.sh` — dejó de ser huérfano),
salida/micrófono con slider + mute + selector de dispositivo (wpctl/pactl), y
mezclador por aplicación (sink-inputs). Se refresca solo con `playerctl -F`.
Ojo: pactl escribe la cadena literal `"(null)"` en `description` — el nombre
real está en `properties["device.description"]`.

2026-08-13: eliminado `scripts/battery-menu.sh` (wofi). Lo sustituye
`scripts/battery-panel.py` (cuarto panel gemelo, namespace `battery-panel`),
en el clic del módulo battery. Secciones: estado upower (%, tiempo, W en vivo,
refresco cada 5s), perfiles de energía (D-Bus UPower.PowerProfiles — es
tuned-ppd, `powerprofilesctl` no existe; escribir no pide password), límite de
carga con botón 80↔100 (sysfs vía pkexec; el servicio systemd lo devuelve a 80
al reiniciar), brillo pantalla/teclado (brightnessctl), salud, baterías de
periféricos (upower -e) y últimos picos del cpu-spike-logger (parsea las
líneas `SPIKE FIN` de /var/log/cpu-spikes.log, legible sin root). En wofi
quedan solo power y display.

2026-08-13: eliminado `scripts/power-menu.sh` (wofi). Lo sustituye
`scripts/power-panel.py` (quinto panel gemelo, namespace `power-panel`), en
custom/power de la waybar Y en la tecla física XF86PowerOff. Bloquear (lanza
hyprlock — config Tron en `hyprlock.conf`), Suspender, y con confirmación de
segundo clic: Cerrar sesión, Reiniciar, Reiniciar a la BIOS
(`--firmware-setup`, es UEFI) y Apagar. Apagado programado con minutos
personalizados: proceso suelto `sleep && systemctl poweroff` con
pid+objetivo en `$XDG_RUNTIME_DIR/apagado-programado`, sobrevive al panel y
es cancelable. Sin hibernación a propósito: el único swap es zram. Lección de
este panel: una etiqueta sin elipsis estira la caja más allá de ANCHO y rompe
el clamp del margen (el panel se salía por la derecha) — todos los paneles
llevan ahora elipsis en sus líneas de estado y este además re-clampa tras
mapear. wofi ya solo conserva el menú de display.

2026-08-13: eliminado `scripts/display-menu.sh` — **wofi ya no tiene ningún
menú; los 6 iconos son paneles gemelos**. Lo sustituye
`scripts/display-panel.py` (namespace `display-panel`). Modo nocturno con
switch + slider de temperatura en vivo (comparte `.nighttemp` y el truco
`-S 23:59` de wlsunset con el F11); fondo de pantalla por miniaturas de
`~/Imágenes/Fondos/` — administra el symlink `~/.config/hypr/wallpaper`, que
ahora es lo que usa el autostart de swaybg (los wallpaper-tron* se movieron
ahí desde Descargas; el fallback `|| hyprpaper` se quitó y hyprpaper.conf
quedó vestigial); lista de monitores (`hyprctl monitors all`) y acciones de
externa — la fila de acciones es solo iconos con tooltip y **solo aparece con
una externa conectada** (`set_no_show_all` + visibilidad en cada repintado):
Solo interna / Extender / Duplicar / Solo externa / kanshi, via `hyprctl eval`
con hl.monitor (mirror y disabled existen en el spec). Sin brillo a
propósito: ya está en el panel de batería y en el scroll del icono. Las
acciones de externa quedaron sin probar: no había monitor conectado.

2026-08-13: añadido `scripts/calendar-panel.py` (séptimo panel gemelo,
namespace `calendar-panel`), en el clic del reloj (el tooltip-calendario de
waybar sigue vivo como vista rápida). Cuadrícula del mes navegable (‹/hoy/›,
scroll cambia de mes), hoy en cian, días con evento subrayados en verde, clic
en un día filtra sus eventos. Motor: **khal** (config nueva en
`~/.config/khal/config`, calendario local en `~/.calendars/personal`, khal
parsea fechas según SU config: `%d/%m/%Y`). Crear evento rápido con sintaxis
khal («20/08 15:00 Título») y botón de sync que corre vdirsyncer. **Google
CalDAV pendiente de credenciales OAuth del usuario**: los pasos exactos están
comentados en `~/.config/vdirsyncer/config`; hasta entonces el botón de sync
avisa y todo lo demás funciona en local.

2026-08-13: dos efectos secundarios del apilado en grupos, arreglados. (1)
`movetoworkspace` sobre una ventana agrupada arrastra el grupo ENTERO: los
binds SUPER+SHIFT+numero y SHIFT+'/¿ ahora pasan por `mover_a()`, que hace
`group:remove()` antes de mover — la ventana movida llega SIN grupo al
destino (la regla solo agrupa al nacer; el Tab de alli la apila al usarla).
(2) SUPER+F con modo "maximized" quedo sin efecto visible (el mosaico ya es
pantalla completa siempre): pasado a fullscreen real, que tapa la waybar.
El dispatcher fullscreen es un toggle sin modo "none": para desatascar una
ventana se relanza el mismo modo que tiene puesto.

2026-08-13 (final del día): **apilado en grupos REVERTIDO por completo** — al
usuario le gustaba el mosaico partido de siempre y el apilado le rompió los
hábitos (mover ventanas arrastraba el grupo, SUPER+F dejó de notarse). Fuera:
la regla `apilar-en-grupo`, las funciones apilar/ciclar de Tab (vuelve a
cycle_next pelado), el bind SUPER+G, el envoltorio mover_a() y el bloque
`group{}` de colores. SUPER+F vuelve a "maximized". Las entradas anteriores
sobre grupos quedan como historia de por qué no repetirlo: si se vuelve a
intentar apilado, que sea opt-in por workspace, no global.

2026-08-13: la versión buena de la idea original, sin grupos: SUPER+Tab lleva
el estado de maximizado/fullscreen a la siguiente ventana. Con la actual
maximizada (F) o en pantalla completa (G), Tab cambia de ventana sin que
vuelva el mosaico — Hyprland des-maximiza la anterior solo, un fullscreen por
workspace. Sin nada maximizado, Tab cicla a pelo con el mosaico de siempre.
Opt-in real: el modo lo eliges tú maximizando primero. Iconos de señal = mismos glifos nf-md que la waybar; hover de
filas = `#0b132b`, el de CopyQ. Ojo: los glifos PUA se corrompen al pegarlos
en el archivo — insertarlos siempre por escape `\U000fXXXX` en Python.

2026-08-15: `hide_main_window=true` en `copyq.conf`. El portapapeles se abría
solo en cada arranque de sesión y se quedaba clavado; era efecto colateral de
`disable_tray=true` (ver «Sin icono en la bandeja»). No parecía el arranque
porque la tapa no dispara nada — el journal lo delató: sistema arriba a las
16:48, ventana abierta a las 16:48.
