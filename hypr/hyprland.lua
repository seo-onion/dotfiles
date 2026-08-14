-- Config de Hyprland en formato Lua (el .conf se elimina en 0.57)
-- Referencia de la API: /usr/share/hypr/stubs/hl.meta.lua

-- --- Monitores y Variables ---
hl.monitor({ output = "eDP-1", mode = "preferred", position = "auto", scale = 1 })

local terminal = "kitty"
local menu     = "/home/seo-onion/.local/bin/sherlock"
local mainMod  = "SUPER"

-- --- Autostart (Servicios) ---
hl.on("hyprland.start", function()
    hl.exec_cmd("waybar")
    -- ~/.config/hypr/wallpaper es un symlink que administra display-panel.py
    hl.exec_cmd("swaybg -i /home/seo-onion/.config/hypr/wallpaper -m fill")
    hl.exec_cmd("/usr/libexec/polkit-kde-authentication-agent-1")
    hl.exec_cmd("swaync")
    hl.exec_cmd("copyq --start-server")
    hl.exec_cmd("swayosd-server")
    hl.exec_cmd("kanshi")
    -- systemd necesita conocer la sesión gráfica para poder arrancar xdg-desktop-portal
    hl.exec_cmd("systemctl --user import-environment WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE XDG_CURRENT_DESKTOP && dbus-update-activation-environment --systemd WAYLAND_DISPLAY HYPRLAND_INSTANCE_SIGNATURE XDG_CURRENT_DESKTOP && systemctl --user start hyprland-session.target")
end)

-- --- Environment ---
hl.env("MOZ_ENABLE_WAYLAND", "1")
hl.env("XCURSOR_SIZE", "24")
hl.env("ELECTRON_OZONE_PLATFORM_HINT", "auto")

-- --- Entrada y Layout ---
hl.config({
    input = {
        kb_layout = "latam",
        kb_options = "",
        numlock_by_default = true,

        touchpad = {
            tap_to_click         = true,
            tap_and_drag         = true,
            natural_scroll       = true,
            scroll_factor        = 1.0,
            drag_lock            = true,
            disable_while_typing = false,
        },
    },

    general = {
        gaps_in     = 5,
        gaps_out    = 10,
        border_size = 2,
        col = {
            active_border   = { colors = { "rgba(33ccffee)", "rgba(00ff99ee)" }, angle = 45 },
            inactive_border = "rgba(595959aa)",
        },
        layout = "dwindle",
    },

    dwindle = {
        preserve_split = true,
        force_split    = 1,
    },

    master = {
        new_status = "slave",
        mfact      = 0.55,
    },

    misc = {
        focus_on_activate          = true,
        mouse_move_focuses_monitor = true,
    },

    cursor = {
        no_hardware_cursors = false,
    },

    animations = {
        enabled = true,
    },

    decoration = {
        rounding         = 4,
        active_opacity   = 1.0,
        inactive_opacity = 1.0,

        blur = {
            enabled = true,
            size    = 8,
            passes  = 3,
        },

        shadow = {
            enabled        = true,
            range          = 15,
            render_power   = 4,
            color          = "rgba(00f0ff28)",
            color_inactive = "rgba(00000000)",
        },
    },
})

hl.curve("smoothOut", { type = "bezier", points = { { 0.36, 0 }, { 0.66, -0.56 } } })
hl.curve("smoothIn",  { type = "bezier", points = { { 0.25, 1 }, { 0.5, 1 } } })
hl.animation({ leaf = "layers", enabled = true, speed = 3, bezier = "smoothIn", style = "slide" })

hl.layer_rule({
    name  = "waybar",
    match = { namespace = "^waybar$" },
    animation = "slide top",
    blur      = true,
})
-- Sin blur a proposito: swaync abre una superficie del tamano de la pantalla
-- (layer-shell-cover-screen), asi que difuminarla emborrona el escritorio entero.
hl.layer_rule({ name = "swaync-center", match = { namespace = "^swaync-control-center$" },      animation = "slide right" })
hl.layer_rule({ name = "wifi-panel",    match = { namespace = "^wifi-panel$" },                 animation = "slide top" })
hl.layer_rule({ name = "bt-panel",      match = { namespace = "^bluetooth-panel$" },            animation = "slide top" })
hl.layer_rule({ name = "audio-panel",   match = { namespace = "^audio-panel$" },                animation = "slide top" })
hl.layer_rule({ name = "battery-panel", match = { namespace = "^battery-panel$" },              animation = "slide top" })
hl.layer_rule({ name = "power-panel",   match = { namespace = "^power-panel$" },                animation = "slide top" })
hl.layer_rule({ name = "display-panel", match = { namespace = "^display-panel$" },              animation = "slide top" })
hl.layer_rule({ name = "calendar-panel", match = { namespace = "^calendar-panel$" },            animation = "slide top" })
hl.layer_rule({ name = "swaync-notif",  match = { namespace = "^swaync-notification-window$" }, animation = "slide right" })

-- --- Atajos de Ventanas ---
-- Ciclar ventanas. Si la actual esta maximizada (F) o en pantalla completa (G),
-- el estado viaja a la siguiente: se cambia de ventana sin que vuelva el
-- mosaico. Hyprland des-maximiza la anterior solo (un fullscreen por workspace).
-- Sin nada maximizado, cicla a pelo como siempre.
local function ciclar(prev)
    return function()
        local antes = hl.get_active_window()
        local modo = antes and antes.fullscreen or 0
        hl.dispatch(hl.dsp.window.cycle_next({ prev = prev }))
        if modo == 0 then return end
        local ahora = hl.get_active_window()
        if ahora and antes and ahora.address ~= antes.address and ahora.fullscreen == 0 then
            hl.dispatch(hl.dsp.window.fullscreen({
                window = ahora,
                mode = (modo == 2) and "fullscreen" or "maximized",
            }))
        end
    end
end

hl.bind(mainMod .. " + Tab",         ciclar(false))
hl.bind(mainMod .. " + SHIFT + Tab", ciclar(true))

-- Navegación
hl.bind(mainMod .. " + left",  hl.dsp.focus({ direction = "left" }))
hl.bind(mainMod .. " + right", hl.dsp.focus({ direction = "right" }))
hl.bind(mainMod .. " + up",    hl.dsp.focus({ direction = "up" }))
hl.bind(mainMod .. " + down",  hl.dsp.focus({ direction = "down" }))

-- Mover ventanas (Físico)
hl.bind(mainMod .. " + SHIFT + left",  hl.dsp.window.move({ direction = "left" }))
hl.bind(mainMod .. " + SHIFT + right", hl.dsp.window.move({ direction = "right" }))
hl.bind(mainMod .. " + SHIFT + up",    hl.dsp.window.move({ direction = "up" }))
hl.bind(mainMod .. " + SHIFT + down",  hl.dsp.window.move({ direction = "down" }))

-- Layout
hl.bind(mainMod .. " + space",         hl.dsp.layout("togglesplit"))
hl.bind(mainMod .. " + SHIFT + space", hl.dsp.exec_cmd("~/.config/hypr/scripts/toggle-layout.sh"))

-- Lanzadores y Acciones
hl.bind(mainMod .. " + Q", hl.dsp.exec_cmd(terminal))
hl.bind(mainMod .. " + C", hl.dsp.window.close())
hl.bind(mainMod .. " + M", hl.dsp.exit())
hl.bind(mainMod .. " + V", hl.dsp.window.float({ action = "toggle" }))
hl.bind(mainMod .. " + V", hl.dsp.window.bring_to_top())
hl.bind(mainMod .. " + F", hl.dsp.window.fullscreen({ mode = "maximized" }))
-- G = pantalla completa real: tapa waybar y gaps, la ventana ocupa todo
hl.bind(mainMod .. " + G", hl.dsp.window.fullscreen({ mode = "fullscreen" }))
hl.bind(mainMod .. " + R", hl.dsp.exec_cmd(menu))
-- Se enlaza por código de tecla (57 = N) en vez de por letra: evita cualquier
-- problema de layout latam al traducir el símbolo
hl.bind(mainMod .. " + code:57", hl.dsp.exec_cmd(terminal, { workspace = "empty" }))
-- El panel de notificaciones se movió aquí: SUPER+N ahora abre terminal
hl.bind(mainMod .. " + CTRL + N", hl.dsp.exec_cmd("swaync-client -t -sw"))
hl.bind(mainMod .. " + SUPER_L",
    hl.dsp.exec_cmd("pkill -x sherlock || { rm -f /run/user/1000/sherlock.lock; " .. menu .. "; }"),
    { release = true })

-- Workspaces — ir a escritorio (SUPER + 1-9) y mover ventana (SUPER + SHIFT + 1-9)
for i = 1, 9 do
    hl.bind(mainMod .. " + " .. i,           hl.dsp.focus({ workspace = i }))
    hl.bind(mainMod .. " + SHIFT + " .. i,   hl.dsp.window.move({ workspace = i }))
end

-- Workspaces — navegación cíclica (SUPER + ' / ¿)
hl.bind(mainMod .. " + apostrophe",   hl.dsp.focus({ workspace = "e-1" }))
hl.bind(mainMod .. " + questiondown", hl.dsp.focus({ workspace = "e+1" }))

-- Workspaces — mover ventana al anterior/siguiente
hl.bind(mainMod .. " + SHIFT + apostrophe",   hl.dsp.window.move({ workspace = "e-1" }))
hl.bind(mainMod .. " + SHIFT + questiondown", hl.dsp.window.move({ workspace = "e+1" }))

-- Workspaces — scroll del ratón sobre el escritorio
hl.bind(mainMod .. " + mouse_down", hl.dsp.focus({ workspace = "e+1" }))
hl.bind(mainMod .. " + mouse_up",   hl.dsp.focus({ workspace = "e-1" }))

-- Capturas
hl.bind("Print",         hl.dsp.exec_cmd("~/.config/hypr/scripts/screenshot.sh copy"))
hl.bind("SHIFT + Print", hl.dsp.exec_cmd([[~/.config/hypr/scripts/screenshot.sh save ~/Imágenes/Capturas_de_pantalla/SS-$(date +"%Y-%m-%d_%H-%M-%S").png]]))

-- Multimedia y Volumen
hl.bind("XF86AudioRaiseVolume", hl.dsp.exec_cmd("swayosd-client --output-volume raise"), { repeating = true })
hl.bind("XF86AudioLowerVolume", hl.dsp.exec_cmd("swayosd-client --output-volume lower"), { repeating = true })
hl.bind("XF86AudioMute",        hl.dsp.exec_cmd("swayosd-client --output-volume mute-toggle"))
hl.bind("XF86AudioMicMute",     hl.dsp.exec_cmd("swayosd-client --input-volume mute-toggle"))

-- Brillo
hl.bind("XF86MonBrightnessUp",   hl.dsp.exec_cmd("swayosd-client --brightness raise"), { repeating = true })
hl.bind("XF86MonBrightnessDown", hl.dsp.exec_cmd("swayosd-client --brightness lower"), { repeating = true })

-- Brillo Teclado (Asus)
hl.bind("XF86KbdBrightnessUp",   hl.dsp.exec_cmd("brightnessctl -d asus::kbd_backlight set +1"))
hl.bind("XF86KbdBrightnessDown", hl.dsp.exec_cmd("brightnessctl -d asus::kbd_backlight set 1-"))

-- Menú de energía
hl.bind("XF86PowerOff", hl.dsp.exec_cmd("~/.config/hypr/scripts/power-panel.py"))

-- Tapa: solo se apaga el panel (dpms). Nada de deshabilitar el monitor: eso
-- movia los workspaces a una salida fantasma y devolvia las ventanas desordenadas.
-- Tapa: sin binds a proposito — cerrar la tapa no hace NADA (ni apagar
-- pantalla ni suspender; logind ya la ignora en 99-lid-ignore.conf). El
-- equipo sigue trabajando igual con la tapa cerrada.

-- Copilot (XF86Assistant) — el hardware envía SUPER+SHIFT junto con la tecla
-- Úsala como modificador: mantén Copilot + letra para lanzar apps
hl.bind("SUPER + SHIFT + f", hl.dsp.exec_cmd("firefox"))
hl.bind("SUPER + SHIFT + t", hl.dsp.exec_cmd("kitty"))
hl.bind("SUPER + SHIFT + e", hl.dsp.exec_cmd("nemo"))
hl.bind("SUPER + SHIFT + c", hl.dsp.exec_cmd("google-chrome-stable --password-store=basic"))

-- Emoji
hl.bind(mainMod .. " + period", hl.dsp.exec_cmd(menu .. " --sub-menu emoji"))

-- Brillo nocturno
hl.bind("F11", hl.dsp.exec_cmd("~/.config/hypr/scripts/nightlight-toggle.sh"))

-- Mouse (Arrastre)
hl.bind(mainMod .. " + mouse:272", hl.dsp.window.drag(),   { mouse = true })
hl.bind(mainMod .. " + mouse:273", hl.dsp.window.resize(), { mouse = true })

-- Reglas para forzar el comportamiento de las ventanas
hl.window_rule({
    name  = "suppress-maximize-events",
    match = { class = ".*" },
    suppress_event = "maximize",
})

-- Waybar: opacity base 0.7 siempre (el hover lo maneja CSS en módulos)
hl.window_rule({ name = "waybar-opacity", match = { class = "^(waybar)$" }, opacity = "0.7 0.7" })

-- Nemo: opacidades Tron (blur viene del decoration global)
hl.window_rule({ name = "nemo-opacity", match = { class = "^(nemo)$" }, opacity = "0.75 0.85" })

-- CopyQ como panel lateral derecho. No es layer-shell (es Qt), es una ventana
-- flotante; visualmente hace el mismo papel que swaync.
--
-- Separada 16px de los bordes y de la waybar A PROPOSITO: pegada al borde, el
-- marco de 2px, el redondeo y el resplandor cian caen fuera de la pantalla.
-- pin: sin esto la ventana reaparece en el workspace donde se abrio la primera
-- vez, no en el que estas mirando.
-- Se abre y se cierra con scripts/clipboard.sh (el raton, no el foco).
hl.window_rule({
    name      = "copyq-panel",
    match     = { class = "^com\\.github\\.hluk\\.copyq$" },
    float     = true,
    pin       = true,
    animation = "slide right",
    move      = "1454 52",
    size      = "450 1132",
})
