# Sistema de Diseño: Tron (Bando de los Usuarios y Aliados)
## Especificación Técnica para Entorno Wayland / Hyprland

### 1. Paleta de Colores Hexadecimal
*   **#FFFFFF** (Blanco Usuario): Texto activo, títulos de ventana enfocada, prompt de terminal, iconos encendidos.
*   **#E2E8F0** (Plata Glitch): Información secundaria, texto inactivo, descripciones de menús.
*   **#00F0FF** (Cian Neón): Acento interactivo (hover, enlaces, selecciones, resplandor).
*   **#0066FF** (Azul Eléctrico): Estado, progreso, barras de carga, transiciones oscuras.
*   **#0B132B** (Azul Abismo): Fondo base de ventanas de trabajo (Terminal, Editores).
*   **#05050A** (Negro Terminal): Fondo base de componentes del sistema (Waybar, Wofi, Hyprlock).
*   **#33CCFF** (Azul Cielo): Inicio del degradado del borde activo.
*   **#00FF99** (Verde Menta): Fin del degradado del borde activo.

### 2. Opacidades y Efecto Neón (Estructura de Cristal)
*   **Ventana Activa:** 0.75
*   **Ventana Inactiva:** 0.85 *(Actualizado para garantizar contraste y legibilidad del código en segundo plano)*.
*   **Fondo del Sistema:** rgba(5, 5, 10, 0.60)
*   **Blur (Desenfoque):** Activado de forma obligatoria.
    *   Size: 8
    *   Passes: 3
    *   *Advertencia: Configuración de alto coste para la GPU.*
*   **Resplandor Neón:** Exclusivo para ventanas activas (Drop Shadow).
    *   Rango: 15
    *   Render Power: 4
    *   Color: #00F0FF**28** (alfa 0.16)

    **Este es el estándar de todo el sistema.** Se pinta de dos formas según la
    pieza, y las dos tienen que dar el mismo perfil:

    | Pieza | Cómo se pinta |
    |---|---|
    | Ventanas (CopyQ, terminal…) | `shadow` de Hyprland, `rgba(00f0ff28)` rango 15 |
    | Capas (swaync) | CSS `box-shadow: 0 0 16px rgba(0, 240, 255, 0.45)` |

    Los números no coinciden entre sí porque las matemáticas son distintas:
    Hyprland usa `render_power`, GTK una gaussiana. Lo que se iguala es el
    resultado medido, no el valor escrito.

    Para comprobarlo: captura con `grim` y mide el azul de los píxeles hacia
    fuera del marco. El perfil de referencia, a 2/4/6/8/10 px:
    `180 · 138 · 98 · 61 · 29`, muriendo a los 14 px.

    **Al medir, la ventana tiene que estar enfocada.** `color_inactive` es
    transparente: en una ventana sin foco no hay resplandor que medir y sale
    plano, lo que parece que el ajuste no ha funcionado.

### 3. Geometría Rigurosa
*   **Grosor de Bordes:** 2px
*   **Borde Activo:** Degradado lineal 45° (#33CCFF Azul Cielo a #00FF99 Verde Menta), alfa 93% (`ee`).
*   **Borde Inactivo:** Gris neutro al 67% (rgba(89, 89, 89, 0.67) / #595959AA).
*   **Gaps In:** 5px
*   **Gaps Out:** 10px
*   **Radio de Curvatura (Rounding):** 4px

---

### 4. Implementación Base (hyprland.conf)

```ini
general {
    gaps_in = 5
    gaps_out = 10
    border_size = 2
    col.active_border = rgba(33ccffee) rgba(00ff99ee) 45deg
    col.inactive_border = rgba(595959aa)
    layout = dwindle
}

decoration {
    rounding = 4
    active_opacity = 1.0
    inactive_opacity = 1.0

    blur {
        enabled = true
        size = 8
        passes = 3
    }

    shadow {
        enabled = true
        range = 15
        render_power = 4
        color = rgba(00f0ff28)
        color_inactive = rgba(00000000)
    }
}
