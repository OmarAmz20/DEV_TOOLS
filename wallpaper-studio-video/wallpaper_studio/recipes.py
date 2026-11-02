"""Editable, contrast-checked colour recipes on top of Wallpaper Studio's palette."""
from __future__ import annotations
import colorsys
import re
from . import palette,skins

PRESETS = {
    "wallpaper": ("Wallpaper", "Colours sampled from your picture", None, None),
    "catppuccin": ("Catppuccin", "Pastel accents · soft, warm surfaces",
        ("#EFF1F5", "#E6E9EF", "#FAFBFE", "#4C4F69", "#6C6F85", "#8839EF"),
        ("#1E1E2E", "#181825", "#313244", "#CDD6F4", "#A6ADC8", "#CBA6F7")),
    "nord": ("Nord", "Cool slate · restrained frost blue",
        ("#ECEFF4", "#E5E9F0", "#FFFFFF", "#2E3440", "#4C566A", "#5E81AC"),
        ("#2E3440", "#272C36", "#3B4252", "#ECEFF4", "#B7C2D0", "#88C0D0")),
    "tokyo": ("Tokyo Night", "Inky indigo · electric blue",
        ("#E1E2E7", "#D6D8E0", "#F1F2F6", "#343B58", "#4C567A", "#2E7DE9"),
        ("#1A1B26", "#16161E", "#24283B", "#C0CAF5", "#9AA5CE", "#7AA2F7")),
    "gruvbox": ("Gruvbox", "Warm charcoal · amber and olive",
        ("#FBF1C7", "#F2E5BC", "#FFF8E0", "#3C3836", "#665C54", "#9D0006"),
        ("#282828", "#1D2021", "#32302F", "#EBDBB2", "#A89984", "#FABD2F")),
    "dracula": ("Dracula", "Violet charcoal · saturated highlights",
        ("#F5F2FA", "#EAE5F1", "#FFFFFF", "#343044", "#625B76", "#6829B8"),
        ("#282A36", "#21222C", "#343746", "#F8F8F2", "#BFBED2", "#BD93F9")),
    "rose": ("Rosé Pine", "Muted plum · gentle rose gold",
        ("#FAF4ED", "#F2E9E1", "#FFF8F1", "#575279", "#797593", "#B4637A"),
        ("#191724", "#15131F", "#26233A", "#E0DEF4", "#A39FB7", "#EBBCBA")),
}

PRESETS.update({
 'pixel':('Pixel Arcade','8-bit violet · chunky pixel windows',('#F4EDFF','#E6DCF5','#FFFFFF','#2A2044','#645379','#713BC4'),('#211B35','#171125','#342747','#F0E4FF','#B6A2CE','#C799FF')),
 'kingdom':('Mushroom Kingdom','Mario-inspired · brick, grass and coin gold',('#FFF4D4','#E9DDBB','#FFFCED','#332A17','#665636','#875500'),('#202A21','#141E18','#2B382A','#FFF2CE','#C1C2A4','#EAC04C')),
 'handheld':('Pocket Console','Four-tone green · vintage handheld',('#D4E5A4','#BCD187','#E5F1C3','#243A24','#4D6240','#365631'),('#1B291A','#142016','#293D24','#D5E9A9','#A6BF80','#B5D47B')),
 'retro95':('Retro Desktop 95','Bevelled controls · classic blue titlebars',('#D4D4CC','#BFBFB7','#F4F4EB','#20212A','#51525B','#153E8E'),('#282C38','#1D202B','#3B4050','#F0F1F6','#B8BED1','#8EB6FF')),
 'cyber':('Neon Grid','Cyberpunk cyan · angular luminous edges',('#F0F5FC','#DDE6F2','#FFFFFF','#172D49','#476280','#006B87'),('#111B28','#0B121E','#1D2D40','#E2F6FF','#99BCD0','#64E4F2')),
 'paper':('Paper & Ink','Warm paper · heavy ink outlines',('#F5F0E5','#E7DECB','#FFFCF4','#302C25','#696052','#715534'),('#25231F','#1A1916','#343129','#F2E9D6','#C1B69E','#DEC18D')),
 'ocean':('Ocean Glass','Deep sea blue · soft glass controls',('#EDF7FA','#DCECF1','#FCFFFF','#213E48','#4F6F79','#006D85'),('#14242F','#0D1922','#203B4B','#E0F5FC','#9FC1D0','#7ED9E8')),
 'crt':('Terminal CRT','Green phosphor · sharp console windows',('#E5F1DD','#CDDEC1','#F5FFEE','#173A1A','#3E613E','#1B6A28'),('#0D1910','#08120A','#16291A','#BFF9BE','#88B98B','#83EE91')),
 'custom':('My Custom Theme','Your own surfaces, text and accent',('#F0F1F4','#E6E8ED','#FFFFFF','#252C3A','#5E6675','#355CB8'),('#17191D','#121418','#22252A','#DFE5F1','#A0ACBF','#89B4FA')),
})
PRESETS={**{k:PRESETS[k] for k in ('kingdom','pixel','handheld','retro95','cyber','paper','ocean','crt')},**{k:v for k,v in PRESETS.items() if k not in skins.RECIPE_SKINS}}
COLOUR_KEYS=('paper','paper2','sheet','ink','muted','accent')


def valid_hex(value):
    return isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", value) is not None


def readable(colour, backgrounds, target, dark):
    """Nearest usable lightness in the appropriate direction, keeping the hue."""
    h, lightness, saturation = colorsys.rgb_to_hls(*palette.hex_to_rgb(colour))
    if min(palette.contrast(colour, b) for b in backgrounds) >= target:
        return colour.upper()
    direction = 1 if dark else -1
    for step in range(1, 101):
        light = max(0, min(1, lightness + direction * step / 100))
        candidate = palette.hsl(h * 360, saturation, light)
        if min(palette.contrast(candidate, b) for b in backgrounds) >= target:
            return candidate
    return max(("#000000", "#FFFFFF"),
               key=lambda c: min(palette.contrast(c, b) for b in backgrounds))


def mix(first, second, amount):
    a, b = palette.hex_to_rgb(first), palette.hex_to_rgb(second)
    return palette.rgb_to_hex(tuple(x * (1 - amount) + y * amount for x, y in zip(a, b)))


def finish(p, dark, accent=None, high_contrast=False):
    p = dict(p)
    surfaces = [p["paper"], p["paper2"], p["sheet"]]
    target = 7.0 if high_contrast else 4.5
    p["ink"] = readable(p["ink"], surfaces, target, dark)
    p["muted"] = readable(p["muted"], surfaces, 4.5, dark)
    raw_accent = accent or p["accent"]
    if not valid_hex(raw_accent):
        raise ValueError("Use an accent such as #89B4FA (six hexadecimal digits).")
    p["accent"] = readable(raw_accent, surfaces, 3.0, dark)
    p["accent_text"] = readable(raw_accent, surfaces, 4.5, dark)
    p["on_accent"] = max(("#000000", "#FFFFFF"),
                          key=lambda c: palette.contrast(c, p["accent"]))
    # Keep the meaning of ANSI colours: errors stay red, warnings stay amber.
    normal, bright = [], []
    for hue in (5, 135, 42, 220, 292, 182):
        normal.append(readable(palette.hsl(hue, .58, .65 if dark else .37), [p["paper"]], 4.5, dark))
        bright.append(readable(palette.hsl(hue, .72, .76 if dark else .29), [p["paper"]], 4.5, dark))
    p["ansi"] = [p["muted"], *normal, p["ink"], p["muted"], *bright, p["ink"]]
    return p


def resolve(base, config):
    preset = config.get("preset", "wallpaper")
    if preset not in PRESETS:
        preset = "wallpaper"
    result = {}
    for mode in ("light", "dark"):
        dark = mode == "dark"
        if preset == "wallpaper":
            p = dict(base[mode])
            amount = float(config.get("tint", .35))
            # The original extracted palette has more tint than the neutral
            # end of this control. Keep neutral surfaces clean at low values.
            neutral = {"paper":"#17191D", "paper2":"#121418", "sheet":"#22252A"} if dark else \
                      {"paper":"#F0F1F4", "paper2":"#E6E8ED", "sheet":"#FFFFFF"}
            for key in neutral:
                p[key] = mix(neutral[key], p[key], max(0, min(1, amount)))
        else:
            values = PRESETS[preset][3 if dark else 2]
            p = dict(zip(COLOUR_KEYS, values))
            if preset=='custom':p.update(config.get('custom_'+mode,{}))
        result[mode] = finish(p, dark, config.get("accent") or None, bool(config.get("high_contrast")))
    return result


def metrics(p):
    surfaces = [p["paper"], p["paper2"], p["sheet"]]
    return {"text": min(palette.contrast(p["ink"], b) for b in surfaces),
            "secondary": min(palette.contrast(p["muted"], b) for b in surfaces),
            "accent": palette.contrast(p["on_accent"], p["accent"])}


def gtk_css(p, dark, config):
    css = palette.gtk_css(p, dark, False)
    for role,index in (("destructive",1),("error",1),("success",2),("warning",3)):
        colour=p["ansi"][index]
        foreground=max(("#000000","#FFFFFF"),key=lambda c:palette.contrast(c,colour))
        css+=f"@define-color {role}_bg_color {colour};\n@define-color {role}_fg_color {foreground};\n"
    radius = {"soft": 14, "crisp": 5, "square": 0}.get(config.get("shape"), 14)
    css += f"""
/* Wallpaper Studio Video: consistent controls, solid reading surfaces. */
window.csd {{ border-radius: {radius}px; }}
button:not(.flat):not(.circular), entry, spinbutton {{ border-radius: {min(radius, 10)}px; }}
popover > contents, menu, .menu {{ border-radius: {radius}px; }}
selection, .view:selected, textview text selection {{ background-color: @accent_bg_color; color: @accent_fg_color; }}
button.suggested-action {{ background-image: none; background-color: @accent_bg_color; color: @accent_fg_color; }}
button.destructive-action {{ color: @destructive_color; }}
"""
    if config.get("glass"):
        css += palette.GLASS.replace("0.70", "0.90").replace("0.45", "0.82").replace("0.4)", "0.82)")
    return css+skins.css(p,config)


def sample_base():
    return palette.build([(215, .45, .35)] * 80 + [(280, .7, .6)] * 20)
